from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, List

SideQueryFn = Callable[[str, str], Any]  # actually Awaitable[str]


MAX_SESSION_MEMORY_BYTES = 60 * 1024  # 60KB cumulative per session


#相关的内存记忆
class RelevantMemories:
    __slots__ = ("path", "content", "mtime_ms", "header")

    def __init__(self, path: str, content: str, mtime_ms: float, header: str):
        self.path = path
        self.content = content
        self.mtime_ms = mtime_ms
        self.header = header

async def select_relevant_memories(
        query: str,
        side_query: SideQueryFn,
        already_surfaced: set[str],
)-> List[RelevantMemories]:
    headers = scan_memory_headers()


    if not headers:
        return []

    candidates = [ h for h in headers if  h.file_path not in already_surfaced]
    if not candidates:
        return []

    manifest = format_memory_manifest(candidates)

    try:




#预取操作的句柄

class MemoryPrefetch:
    def __init__(self, task: asyncio.Task):
        self.task = task
        self.consumed = False

    @property
    def settled(self) -> bool:
        return self.task.done()

# 异步启动内存预取任务
def start_memory_prefetch(
        query:str,
        side_Query:SideQueryFn,
        session_memory_bytes: int
)->MemoryPrefetch | None:
    #仅限于输入多个单词的时候才进行内存的预取
    if not re.search(r"\s", query.strip()):
        return None

    #话内存预算检查
    if session_memory_bytes >MAX_SESSION_MEMORY_BYTES:
        return None

    #记忆必须存在才能预取
    d = get_memory_dir()
    has_memories = any(f.suffix == ".md" and f.name != "MEMORY.md" for f in d.iterdir())

    if not has_memories:
        return None

    task = asyncio.create_task(
        select_relevant_memories(query, side_query, already_surfaced)
    )

    return MemoryPrefetch(task)





#---------------路径----------------------
def get_memory_dir() -> Path:
    d = Path.home() / ".bear-code" / "projects" / _project_hash() / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _project_hash() -> str:
    return hashlib.sha256(str(Path.cwd()).encode()).hexdigest()[:16]