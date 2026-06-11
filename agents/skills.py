from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .frontmatter import parse_frontmatter


@dataclass
class SkillDefinition:
    name: str
    description: str
    when_to_use: str | None = None
    allowed_tools: list[str] | None = None
    user_invocable: bool = True
    context: str = "inline"  # "inline" or "fork"
    prompt_template: str = ""
    source: str = "project"  # "project" or "user"
    skill_dir: str = ""


_cached_skills: list[SkillDefinition] | None = None


def execute_skill(skill_name:str, args:dict)-> dict | None:
    skill = get_skill_by_name(skill_name)
    if not skill:
        return None

    return {
        "prompt": resolve_skill_prompt(skill, args),
        "allowed_tools": skill.allowed_tools,
        "context": skill.context,
    }



def resolve_skill_prompt(skill: SkillDefinition, args: str) -> str:
    import re
    prompt = skill.prompt_template
    prompt = re.sub(r"\$ARGUMENTS|\$\{ARGUMENTS\}", args, prompt)
    prompt = prompt.replace("${CLAUDE_SKILL_DIR}", skill.skill_dir)
    return prompt

def get_skill_by_name(skill_name:str)->SkillDefinition | None:
    for s in discover_skills():
        if s.name == skill_name:
            return s
    return None

def discover_skills() -> list[SkillDefinition]:
    global _cached_skills
    if _cached_skills is not None:
        return _cached_skills

    skills: dict[str,SkillDefinition] = {}
    user_dir = Path.home() / ".bear" / "skills"
    _load_skills_from_dir(user_dir, "user", skills)
    project_dir = Path.cwd() / ".bear" / "skills"
    _load_skills_from_dir(project_dir, "project", skills, overwrite=False)

    _cached_skills = list(skills.values())
    return _cached_skills

def _load_skills_from_dir( base_dir: Path, source: str, skills:dict[str, SkillDefinition], overwrite: bool = True) -> None:
    if not base_dir.is_dir():
        return
    for entry in base_dir.iterdir():
        if not entry.is_dir():
            continue
        skill_file = entry/  "SKILL.md"
        if not skill_file.exists():
            continue
        skill = _parse_skill_file(skill_file, source, str(entry))
        if skill:
            if not overwrite and skill.name in skills:
                continue
            skills[skill.name] = skill

def _parse_skill_file(file_path: Path, source: str, skill_dir: str) -> SkillDefinition:
    try:
        raw = file_path.read_text()
        result = parse_frontmatter(raw)
        meta = result.meta

        name = meta.get("name") or file_path.parent.name or "unknown"
        user_invocable = meta.get("user-invocable", "true") != "false"
        context = "fork" if meta.get("context") == "fork" else "inline"

        allowed_tools: list[str] | None = None
        if "allowed-tools" in meta:
            raw_tools = meta["allowed-tools"]
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
    skills = discover_skills()
    if not skills:
        return ""

    lines = ["# Available Skills", ""]
    invocable = [s for s in skills if s.user_invocable]
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
    return "\n".join(lines)


def reset_skill_cache() -> None:
    global _cached_skills
    _cached_skills = None







