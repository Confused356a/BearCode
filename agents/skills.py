from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .frontmatter import parse_frontmatter
from .skill_evolution import (
    evolve_skill_file,
    format_skill_stats,
    record_skill_feedback,
    record_skill_invocation,
)


@dataclass
class SkillDefinition:
    # 一个 skill 在程序内的统一表示，由 SKILL.md 的 frontmatter 和正文解析得到。
    name: str
    description: str
    when_to_use: str | None = None
    allowed_tools: list[str] | None = None
    user_invocable: bool = True
    context: str = "inline"  # "inline" or "fork"
    prompt_template: str = ""
    source: str = "project"  # "project" or "user"
    skill_dir: str = ""


# skills 只在首次读取时扫描磁盘，后续复用缓存；修改 skill 后需要重启或 reset。
_cached_skills: list[SkillDefinition] | None = None


def execute_skill(skill_name:str, args:object)-> dict | None:
    # skill 工具的执行入口：按名字找到 skill，并返回解析后的 prompt 和执行配置。
    skill = get_skill_by_name(skill_name)
    if not skill:
        return None

    record_skill_invocation(
        skill_name=skill.name,
        source=skill.source,
        context=skill.context,
        args=args,
    )

    return {
        "prompt": resolve_skill_prompt(skill, args),
        "allowed_tools": skill.allowed_tools,
        "context": skill.context,
        "source": skill.source,
        "skill_dir": skill.skill_dir,
    }



def resolve_skill_prompt(skill: SkillDefinition, args: object) -> str:
    import re
    prompt = skill.prompt_template
    # 支持在 SKILL.md 正文中使用 $ARGUMENTS 或 ${ARGUMENTS} 引用用户参数。
    prompt = re.sub(r"\$ARGUMENTS|\$\{ARGUMENTS\}", str(args or ""), prompt)
    # 支持 skill 引用自己的目录，例如读取同目录下的 references/scripts。
    prompt = prompt.replace("${CLAUDE_SKILL_DIR}", skill.skill_dir)
    return prompt

def get_skill_by_name(skill_name:str)->SkillDefinition | None:
    # 通过 name 查找 skill；name 来自 frontmatter，没有写时使用目录名。
    for s in discover_skills():
        if s.name == skill_name:
            return s
    return None

def discover_skills() -> list[SkillDefinition]:
    global _cached_skills
    if _cached_skills is not None:
        return _cached_skills

    skills: dict[str,SkillDefinition] = {}
    # 用户级 skills 优先级最高：~/.bear/skills/<name>/SKILL.md
    user_dir = Path.home() / ".bear" / "skills"
    _load_skills_from_dir(user_dir, "user", skills)
    # 项目级 skills 优先级较低：<cwd>/.bear/skills/<name>/SKILL.md
    project_dir = Path.cwd() / ".bear" / "skills"
    _load_skills_from_dir(project_dir, "project", skills, overwrite=False)

    _cached_skills = list(skills.values())
    return _cached_skills

def _load_skills_from_dir( base_dir: Path, source: str, skills:dict[str, SkillDefinition], overwrite: bool = True) -> None:
    # 只加载目录形式的 skill，不加载 .bear/skills/foo.md 这种单文件形式。
    if not base_dir.is_dir():
        return
    for entry in base_dir.iterdir():
        if not entry.is_dir():
            continue
        # 文件名必须是 SKILL.md，大小写要一致。
        skill_file = entry/  "SKILL.md"
        if not skill_file.exists():
            continue
        skill = _parse_skill_file(skill_file, source, str(entry))
        if skill:
            # 项目级加载时 overwrite=False，避免覆盖同名用户级 skill。
            if not overwrite and skill.name in skills:
                continue
            skills[skill.name] = skill

def _parse_skill_file(file_path: Path, source: str, skill_dir: str) -> SkillDefinition:
    try:
        # SKILL.md = frontmatter 配置 + markdown 正文。
        raw = file_path.read_text()
        result = parse_frontmatter(raw)
        meta = result.meta

        # name 没写时用目录名；user-invocable 默认 true；context 默认 inline。
        name = meta.get("name") or file_path.parent.name or "unknown"
        user_invocable = meta.get("user-invocable", "true") != "false"
        context = "fork" if meta.get("context") == "fork" else "inline"

        allowed_tools: list[str] | None = None
        if "allowed-tools" in meta:
            raw_tools = meta["allowed-tools"]
            # allowed-tools 支持 JSON 数组字符串，也支持逗号分隔。
            if raw_tools.startswith("["):
                try:
                    allowed_tools = json.loads(raw_tools)
                except Exception:
                    allowed_tools = [s.strip() for s in raw_tools.strip("[]").split(",")]
            else:
                allowed_tools = [s.strip() for s in raw_tools.split(",")]

        return SkillDefinition(
            name=name,
            description=meta.get("description", ""),
            when_to_use=meta.get("when_to_use") or meta.get("when-to-use"),
            allowed_tools=allowed_tools,
            user_invocable=user_invocable,
            context=context,
            prompt_template=result.body,
            source=source,
            skill_dir=skill_dir,
        )

    except Exception:
        return None


def build_skill_descriptions() -> str:
    # 把已加载的 skills 写进 system prompt，让模型知道哪些 skill 可用。
    skills = discover_skills()
    if not skills:
        return ""

    lines = ["# Available Skills", ""]
    # user_invocable=True 的 skill 主要给用户通过 /<name> 手动调用。
    invocable = [s for s in skills if s.user_invocable]
    # user_invocable=False 的 skill 作为自动调用候选，模型根据 when_to_use 决定是否调用 skill 工具。
    auto_only = [s for s in skills if not s.user_invocable]

    if invocable:
        lines.append("User-invocable skills (user types /<name> to invoke):")
        for s in invocable:
            lines.append(f"- **/{s.name}**: {s.description}")
            if s.when_to_use:
                lines.append(f"  When to use: {s.when_to_use}")
        lines.append("")

    if auto_only:
        lines.append("Auto-invocable skills:")
        lines.append("When the user's request matches a skill's When to use, call the `skill` tool with that skill name before continuing. Do not ask the user to invoke it manually.")
        for s in auto_only:
            lines.append(f"- **{s.name}**: {s.description}")
            if s.when_to_use:
                lines.append(f"  When to use: {s.when_to_use}")
        lines.append("")

    lines.append("To invoke a skill programmatically, use the `skill` tool with the skill name and optional arguments.")
    lines.append("")
    lines.append("# Skill Evolution")
    lines.append("Bear Code tracks skill invocations and can evolve skill prompts when durable feedback appears.")
    lines.append("Call `skill_evolve` only when the user gives explicit reusable feedback, a stable correction, or a persistent workflow preference that should affect future similar tasks.")
    lines.append("Do not evolve skills from one-off task content, private secrets, temporary project facts, or assistant-only guesses.")
    return "\n".join(lines)


def reset_skill_cache() -> None:
    # 测试或运行中刷新 skills 时使用；普通用户通常重启程序即可。
    global _cached_skills
    _cached_skills = None


def evolve_skill(
    skill_name: str,
    lesson: str,
    rationale: str = "",
    target: str = "active",
) -> dict:
    skill = get_skill_by_name(skill_name)
    result = evolve_skill_file(
        skill_name=skill_name,
        lesson=lesson,
        rationale=rationale,
        target=target,
        active_dir=skill.skill_dir if skill else "",
    )
    if result.get("ok"):
        reset_skill_cache()
    return result


def record_feedback(skill_name: str, rating: str, note: str = "") -> None:
    record_skill_feedback(skill_name=skill_name, rating=rating, note=note)


def skill_stats() -> str:
    return format_skill_stats()





