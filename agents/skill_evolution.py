from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .frontmatter import format_frontmatter, parse_frontmatter


USAGE_LOG = "usage.jsonl"
HISTORY_DIR = "history"


def get_evolution_dir() -> Path:
    return Path.cwd() / ".bear" / "skill-evolution"


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _safe_skill_slug(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(name or "").strip()).strip("-")
    return slug or "unknown"


def _preview(value: object, limit: int = 500) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def record_skill_invocation(
    *,
    skill_name: str,
    source: str,
    context: str,
    args: object = "",
) -> None:
    row = {
        "event": "invoke",
        "time": _utc_now(),
        "skill": skill_name,
        "source": source,
        "context": context,
        "args_preview": _preview(args),
    }
    _append_jsonl(get_evolution_dir() / USAGE_LOG, row)


def record_skill_feedback(
    *,
    skill_name: str,
    rating: str,
    note: str = "",
) -> None:
    row = {
        "event": "feedback",
        "time": _utc_now(),
        "skill": skill_name,
        "rating": str(rating or "").strip(),
        "note": _preview(note, 1200),
    }
    _append_jsonl(get_evolution_dir() / USAGE_LOG, row)


def _parse_int(value: str | None, default: int = 0) -> int:
    try:
        return int(str(value or "").strip())
    except Exception:
        return default


def _bump_patch(version: str | None) -> str:
    raw = str(version or "0.1.0").strip()
    parts = raw.split(".")
    if len(parts) < 3 or not all(p.isdigit() for p in parts[:3]):
        return "0.1.1"
    parts[2] = str(int(parts[2]) + 1)
    return ".".join(parts[:3])


def _find_skill_file_by_name(base_dir: Path, skill_name: str) -> Path | None:
    if not base_dir.is_dir():
        return None
    wanted = str(skill_name or "").strip()
    for entry in base_dir.iterdir():
        if not entry.is_dir():
            continue
        skill_file = entry / "SKILL.md"
        if not skill_file.is_file():
            continue
        try:
            parsed = parse_frontmatter(skill_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        name = parsed.meta.get("name") or entry.name
        if name == wanted:
            return skill_file
    return None


def resolve_skill_file(skill_name: str, *, target: str = "active", active_dir: str = "") -> Path | None:
    target = (target or "active").strip().lower()
    if target == "active" and active_dir:
        skill_file = Path(active_dir) / "SKILL.md"
        if skill_file.is_file():
            return skill_file

    if target in ("project", "active"):
        found = _find_skill_file_by_name(Path.cwd() / ".bear" / "skills", skill_name)
        if found:
            return found

    if target in ("user", "active"):
        found = _find_skill_file_by_name(Path.home() / ".bear" / "skills", skill_name)
        if found:
            return found

    return None


def _append_evolution_note(body: str, lesson: str, rationale: str = "") -> str:
    lesson = re.sub(r"\s+", " ", str(lesson or "").strip())
    rationale = re.sub(r"\s+", " ", str(rationale or "").strip())
    if not lesson:
        raise ValueError("lesson is required")

    bullet = f"- {_today()}: {lesson}"
    if rationale:
        bullet += f" Reason: {rationale}"

    body = str(body or "").rstrip()
    marker = "## Evolution Notes"
    if marker in body:
        if lesson in body:
            return body + "\n"
        return body + "\n" + bullet + "\n"
    return body + "\n\n" + marker + "\n\n" + bullet + "\n"


def evolve_skill_file(
    *,
    skill_name: str,
    lesson: str,
    rationale: str = "",
    target: str = "active",
    active_dir: str = "",
    actor: str = "agent",
) -> dict[str, Any]:
    skill_file = resolve_skill_file(skill_name, target=target, active_dir=active_dir)
    if not skill_file:
        return {"ok": False, "error": f"Skill not found: {skill_name}"}

    raw = skill_file.read_text(encoding="utf-8")
    parsed = parse_frontmatter(raw)
    meta = dict(parsed.meta)
    resolved_name = meta.get("name") or skill_file.parent.name

    snapshot = {
        "time": _utc_now(),
        "event": "snapshot",
        "actor": actor,
        "skill": resolved_name,
        "file": str(skill_file),
        "version": meta.get("version", "0.1.0"),
        "lesson": _preview(lesson, 1200),
        "rationale": _preview(rationale, 1200),
        "content": raw,
    }
    history_path = get_evolution_dir() / HISTORY_DIR / f"{_safe_skill_slug(resolved_name)}.jsonl"
    _append_jsonl(history_path, snapshot)

    meta["name"] = resolved_name
    meta["version"] = _bump_patch(meta.get("version"))
    meta["last-evolved"] = _utc_now()
    meta["evolution-count"] = str(_parse_int(meta.get("evolution-count"), 0) + 1)

    new_body = _append_evolution_note(parsed.body, lesson, rationale)
    skill_file.write_text(format_frontmatter(meta, new_body), encoding="utf-8")

    event = {
        "event": "evolve",
        "time": _utc_now(),
        "actor": actor,
        "skill": resolved_name,
        "file": str(skill_file),
        "version": meta["version"],
        "target": target,
        "lesson": _preview(lesson, 1200),
        "rationale": _preview(rationale, 1200),
        "history": str(history_path),
    }
    _append_jsonl(get_evolution_dir() / USAGE_LOG, event)
    return {"ok": True, **event}


def load_skill_stats() -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    usage_path = get_evolution_dir() / USAGE_LOG
    if usage_path.is_file():
        for line in usage_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            skill = str(row.get("skill") or "").strip()
            if not skill:
                continue
            item = stats.setdefault(skill, {"invocations": 0, "feedback": 0, "evolutions": 0})
            event = row.get("event")
            if event == "invoke":
                item["invocations"] = int(item.get("invocations", 0)) + 1
                item["last_invoked"] = row.get("time")
            elif event == "feedback":
                item["feedback"] = int(item.get("feedback", 0)) + 1
                item["last_feedback"] = row.get("time")
            elif event == "evolve":
                item["evolutions"] = int(item.get("evolutions", 0)) + 1
                item["last_evolved"] = row.get("time")
                item["version"] = row.get("version")
                item["file"] = row.get("file")

    history_root = get_evolution_dir() / HISTORY_DIR
    if history_root.is_dir():
        for path in history_root.glob("*.jsonl"):
            count = len([line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()])
            skill = path.stem
            item = stats.setdefault(skill, {"invocations": 0, "feedback": 0, "evolutions": 0})
            item["snapshots"] = count
    return stats


def format_skill_stats() -> str:
    stats = load_skill_stats()
    if not stats:
        return "No skill evolution events recorded yet."

    lines = ["Skill evolution stats:"]
    for name in sorted(stats):
        item = stats[name]
        parts = [
            f"invoked={item.get('invocations', 0)}",
            f"feedback={item.get('feedback', 0)}",
            f"evolved={item.get('evolutions', 0)}",
            f"snapshots={item.get('snapshots', 0)}",
        ]
        if item.get("version"):
            parts.append(f"version={item['version']}")
        if item.get("last_invoked"):
            parts.append(f"last_invoked={item['last_invoked']}")
        lines.append(f"  {name}: " + ", ".join(parts))
    return "\n".join(lines)
