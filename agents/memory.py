"""
记忆系统：采用基于文件的四分类记忆
    并以 MEMORY.md 作为索引。它复刻了 Claude Code 的记忆架构
    通过 sideQuery（侧边查询）来实现语义检索。”
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .frontmatter import parse_frontmatter, format_frontmatter
from typing import Callable
SideQueryFn = Callable[[str, str], Any]  # actually Awaitable[str]

# ─── Types ──────────────────────────────────────────────────

VALID_TYPES = {"user", "feedback", "project", "reference"}
MAX_INDEX_LINES = 200
MAX_INDEX_BYTES = 25000


class MemoryEntry:
    __slots__ = ("name", "description", "type", "filename", "content")

    def __init__(self, name: str, description: str, type: str, filename: str, content: str):
        self.name = name
        self.description = description
        self.type = type
        self.filename = filename
        self.content = content




def _project_hash() -> str:
    return hashlib.sha256(str(Path.cwd()).encode()).hexdigest()[:16]


def get_memory_dir() -> Path:
    d = Path.home() / ".BearCode" / "projects" / _project_hash() / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_index_path() -> Path:
    return get_memory_dir() / "MEMORY.md"


# ─── Slugify ────────────────────────────────────────────────


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower())
    s = s.strip("_")
    return s[:40]


# ─── CRUD ───────────────────────────────────────────────────


def list_memories() -> list[MemoryEntry]:
    d = get_memory_dir()
    entries: list[MemoryEntry] = []
    for f in sorted(d.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        try:
            result = parse_frontmatter(f.read_text())
            meta = result.meta
            if not meta.get("name") or not meta.get("type"):
                continue
            t = meta["type"] if meta["type"] in VALID_TYPES else "project"
            entries.append(MemoryEntry(
                name=meta["name"],
                description=meta.get("description", ""),
                type=t,
                filename=f.name,
                content=result.body,
            ))
        except Exception:
            pass
    # Sort by mtime desc
    entries.sort(key=lambda e: (d / e.filename).stat().st_mtime, reverse=True)
    return entries


def save_memory(name: str, description: str, type: str, content: str) -> str:
    d = get_memory_dir()
    filename = f"{type}_{_slugify(name)}.md"
    text = format_frontmatter({"name": name, "description": description, "type": type}, content)
    (d / filename).write_text(text)
    _update_memory_index()
    return filename


def delete_memory(filename: str) -> bool:
    filepath = get_memory_dir() / filename
    if not filepath.exists():
        return False
    filepath.unlink()
    _update_memory_index()
    return True




def _update_memory_index() -> None:
    memories = list_memories()
    lines = ["# Memory Index", ""]
    for m in memories:
        lines.append(f"- **[{m.name}]({m.filename})** ({m.type}) — {m.description}")
    _get_index_path().write_text("\n".join(lines))


def load_memory_index() -> str:
    index_path = _get_index_path()
    if not index_path.exists():
        return ""
    content = index_path.read_text()
    lines = content.split("\n")
    if len(lines) > MAX_INDEX_LINES:
        content = "\n".join(lines[:MAX_INDEX_LINES]) + "\n\n[... truncated, too many memory entries ...]"
    if len(content.encode()) > MAX_INDEX_BYTES:
        content = content[:MAX_INDEX_BYTES] + "\n\n[... truncated, index too large ...]"
    return content


# ─── Memory Header (lightweight scan) ──────────────────────

class MemoryHeader:
    __slots__ = ("filename", "file_path", "mtime_ms", "description", "type")

    def __init__(self, filename: str, file_path: str, mtime_ms: float,
                 description: str | None, type: str | None):
        self.filename = filename
        self.file_path = file_path
        self.mtime_ms = mtime_ms
        self.description = description
        self.type = type


MAX_MEMORY_FILES = 200
MAX_MEMORY_BYTES_PER_FILE = 4096
MAX_SESSION_MEMORY_BYTES = 60 * 1024  # 60KB cumulative per session



"""
快速扫描记忆目录中的所有 Markdown 文件
只提取每个文件的头部元信息（Frontmatter）
并返回按修改时间排序的摘要列表。
"""
def scan_memory_headers() -> list[MemoryHeader]:
    d = get_memory_dir()
    headers: list[MemoryHeader] = []
    for f in d.glob("*.md"):
        if f.name == "MEMORY.md":
            continue
        try:
            stat = f.stat()
            raw = f.read_text()
            first30 = "\n".join(raw.split("\n")[:30])
            result = parse_frontmatter(first30)
            meta = result.meta
            t = meta.get("type")
            headers.append(MemoryHeader(
                filename=f.name,
                file_path=str(f),
                mtime_ms=stat.st_mtime * 1000,
                description=meta.get("description"),
                type=t if t in VALID_TYPES else None,
            ))
        except Exception:
            pass
    headers.sort(key=lambda h: h.mtime_ms, reverse=True)
    return headers[:MAX_MEMORY_FILES]


def format_memory_manifest(headers: list[MemoryHeader]) -> str:
    lines = []
    for h in headers:
        tag = f"[{h.type}] " if h.type else ""
        ts = datetime.fromtimestamp(h.mtime_ms / 1000, tz=timezone.utc).isoformat()
        if h.description:
            lines.append(f"- {tag}{h.filename} ({ts}): {h.description}")
        else:
            lines.append(f"- {tag}{h.filename} ({ts})")
    return "\n".join(lines)


# ─── Memory Age / Freshness ────────────────────────────────

def memory_age(mtime_ms: float) -> str:
    days = max(0, int((time.time() * 1000 - mtime_ms) / 86_400_000))
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


def memory_freshness_warning(mtime_ms: float) -> str:
    days = max(0, int((time.time() * 1000 - mtime_ms) / 86_400_000))
    if days <= 1:
        return ""
    return (f"This memory is {days} days old. Memories are point-in-time observations, "
            "not live state — claims about code behavior may be outdated. "
            "Verify against current code before asserting as fact.")



SELECT_MEMORIES_PROMPT = """You are selecting memories that will be useful to an AI coding assistant as it processes a user's query. You will be given the user's query and a list of available memory files with their filenames and descriptions.

Return a JSON object with a "selected_memories" array of filenames for the memories that will clearly be useful (up to 5). Only include memories that you are certain will be helpful based on their name and description.
- If you are unsure if a memory will be useful, do not include it.
- If no memories would clearly be useful, return an empty array."""


class RelevantMemory:
    __slots__ = ("path", "content", "mtime_ms", "header")

    def __init__(self, path: str, content: str, mtime_ms: float, header: str):
        self.path = path
        self.content = content
        self.mtime_ms = mtime_ms
        self.header = header


"""
already_surfaced 是已经给用户/模型看过的 memory 路径集合，避免重复召回。

函数会扫描 memory 文件，过滤掉已经用过的，然后让一个辅助模型从候选 memory 
里挑选和当前 query 相关的文件，读取这些文件内容，包装成 RelevantMemory 返回。

"""
async def select_relevant_memories(
    query: str,
    side_query: SideQueryFn,
    already_surfaced: set[str],
) -> list[RelevantMemory]:

    #扫描所有 memory 文件头信息
    headers = scan_memory_headers()

    if not headers:
        return []

    #排除已经展示过的 memory：
    candidates = [h for h in headers if h.file_path not in already_surfaced]
    if not candidates:
        return []

    #把候选 memory 格式化成 manifest
    # manifest 通常是给 LLM 看的摘要列表，比如文件名、标题、更新时间等。

    manifest = format_memory_manifest(candidates)

    #调用 side_query，让另一个模型判断哪些 memory 相关：
    try:
        text = await side_query(
            SELECT_MEMORIES_PROMPT,
            f"Query: {query}\n\nAvailable memories:\n{manifest}",
        )

        # Extract JSON from response
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return []

        #解析 JSON，拿到被选中的 memory 文件名：

        parsed = json.loads(match.group(0))
        selected_filenames = set(parsed.get("selected_memories", []))
        #根据文件名筛选候选 memory，最多取 5 个：
        selected = [h for h in candidates if h.filename in selected_filenames][:5]

        result: list[RelevantMemory] = []
        for h in selected:
            #读取每个选中的 memory 文件内容：
            content = Path(h.file_path).read_text()
            #如果文件太大，就截断：
            if len(content.encode()) > MAX_MEMORY_BYTES_PER_FILE:
                content = content[:MAX_MEMORY_BYTES_PER_FILE] + "\n\n[... truncated, memory file too large ...]"

            #根据 memory 修改时间生成提示头：
            freshness = memory_freshness_warning(h.mtime_ms)
            header_text = (
                f"{freshness}\n\nMemory: {h.file_path}:" if freshness
                else f"Memory (saved {memory_age(h.mtime_ms)}): {h.file_path}:"
            )
            #返回 RelevantMemory 列表：
            result.append(RelevantMemory(
                path=h.file_path, content=content,
                mtime_ms=h.mtime_ms, header=header_text,
            ))
        return result
    except Exception as e:
        if "cancel" in str(e).lower():
            return []
        print(f"[memory] semantic recall failed: {e}")
        return []


# 预取句柄类 MemoryPrefetch，用于封装一个异步任务并提供状态跟踪
class MemoryPrefetch:
    def __init__(self, task: asyncio.Task):
        self.task = task
        self.consumed = False

    @property
    def settled(self) -> bool:
        return self.task.done()


"""
在合适的条件下，提前异步启动 memory 召回任务。
它不会马上返回 memory 内容，而是返回一个 MemoryPrefetch 句柄
后面可以用这个句柄检查任务是否完成、取结果。


函数参数：
query: 当前用户输入的问题。
side_query: 用来做辅助查询的异步函数，通常是调用模型判断哪些 memory 相关。
already_surfaced: 已经展示过的 memory 路径集合，避免重复召回。
session_memory_bytes: 当前 session 已经使用的 memory 字节数。
返回值：可能是 MemoryPrefetch，也可能是 None。
"""

def start_memory_prefetch(
    query: str,
    side_query: SideQueryFn,
    already_surfaced: set[str],
    session_memory_bytes: int,
) -> MemoryPrefetch | None:


    #只有多词输入才触发 memory 预取。
    # 它检查 query.strip() 里有没有空白字符，比如空格、换行、tab。

    if not re.search(r"\s", query.strip()):
        return None

    # 当前 session 的 memory 使用量不能超过预算。
    if session_memory_bytes >= MAX_SESSION_MEMORY_BYTES:
        return None

    # memory 目录里必须真的有 memory 文件。
    d = get_memory_dir()
    has_memories = any(f.suffix == ".md" and f.name != "MEMORY.md" for f in d.iterdir())
    if not has_memories:
        return None

    #如果前面三个条件都通过，就创建一个异步任务。
    task = asyncio.create_task(
        select_relevant_memories(query, side_query, already_surfaced)
    )
    return MemoryPrefetch(task)


def format_memories_for_injection(memories: list[RelevantMemory]) -> str:
    """格式化召回的记忆，以便作为用户消息内容注入."""
    parts = []
    for m in memories:
        parts.append(f"<system-reminder>\n{m.header}\n\n{m.content}\n</system-reminder>")
    return "\n\n".join(parts)


# ─── System prompt 生成一段结构化的系统提示文本
# 用于指导大语言模型如何与持久化的文件型记忆系统进行交互（保存、召回、类型划分等）
# 它会动态加载当前已有的记忆索引，并将所有规则和示例嵌入返回的字符串中。 ──────────────────────────────────


def build_memory_prompt_section() -> str:
    index = load_memory_index()
    memory_dir = str(get_memory_dir())

    return f"""# Memory System

You have a persistent, file-based memory system at `{memory_dir}`.

## Memory Types
- **user**: User's role, preferences, knowledge level
- **feedback**: Corrections and guidance from the user (include Why + How to apply)
- **project**: Ongoing work, goals, deadlines, decisions
- **reference**: Pointers to external resources (URLs, tools, dashboards)

## How to Save Memories
Use the write_file tool to create a memory file with YAML frontmatter:

```markdown
---
name: memory name
description: one-line description
type: user|feedback|project|reference
---
Memory content here.
```

Save to: `{memory_dir}/`
Filename format: `{{type}}_{{slugified_name}}.md`

The MEMORY.md index is auto-updated when you write to the memory directory — do NOT update it manually.

## What NOT to Save
- Code patterns or architecture (read the code instead)
- Git history (use git log)
- Anything already in CLAUDE.md
- Ephemeral task details

## When to Recall
When the user asks you to remember or recall, or when prior context seems relevant.
{chr(10) + "## Current Memory Index" + chr(10) + index if index else chr(10) + "(No memories saved yet.)"}"""
