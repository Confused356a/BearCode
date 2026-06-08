# Memory 文件代码说明

本文档说明 `agents/memory.py` 的整体作用、核心数据结构、主要函数流程，以及它和 `Agent`、工具层之间的关系。

## 1. 整体作用

`agents/memory.py` 实现的是 BearCode 的文件型持久记忆系统。

它的目标是让 Agent 可以把长期有用的信息保存成 Markdown 文件，并在后续用户提问时自动或半自动召回相关记忆，再注入到模型上下文中。

这个 memory 系统主要做五件事：

1. 为当前项目计算专属 memory 目录。
2. 用 Markdown + YAML frontmatter 保存结构化记忆。
3. 维护一个 `MEMORY.md` 索引文件。
4. 通过 side query 让模型从候选记忆中挑选相关记忆。
5. 把召回的记忆包装成 `<system-reminder>`，供主模型使用。

## 2. 存储位置

memory 目录由当前工作目录计算 hash 后生成：

```python
def _project_hash() -> str:
    return hashlib.sha256(str(Path.cwd()).encode()).hexdigest()[:16]
```

实际路径格式是：

```text
~/.bear-Code/projects/{project_hash}/memory
```

也就是说，不同项目会使用不同的 memory 目录，避免跨项目混淆。

`get_memory_dir()` 会确保目录存在：

```python
def get_memory_dir() -> Path:
    d = Path.home() / ".bear-Code" / "projects" / _project_hash() / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d
```

索引文件路径固定为：

```text
~/.bear-Code/projects/{project_hash}/memory/MEMORY.md
```

## 3. 记忆文件格式

每条 memory 是一个 `.md` 文件，文件头部使用 YAML frontmatter。

示例：

```markdown
---
name: 用户偏好
description: 用户希望回答尽量直接，并使用中文解释代码
type: user
---

用户喜欢中文解释，偏好先给结论，再展开关键代码逻辑。
```

当前支持四种类型：

```python
VALID_TYPES = {"user", "feedback", "project", "reference"}
```

含义如下：

- `user`：用户角色、偏好、知识水平。
- `feedback`：用户给过的纠正和指导。
- `project`：当前项目目标、决策、进度。
- `reference`：外部资源、URL、工具、仪表盘等引用。

## 4. 核心数据结构

### 4.1 `MemoryEntry`

`MemoryEntry` 表示完整的 memory 条目，主要用于列表、保存和索引更新。

字段：

- `name`：记忆名称。
- `description`：一句话描述。
- `type`：记忆类型。
- `filename`：文件名。
- `content`：正文内容。

它来自完整读取 memory 文件并解析 frontmatter。

### 4.2 `MemoryHeader`

`MemoryHeader` 表示轻量级 memory 摘要，主要用于语义召回前的快速扫描。

字段：

- `filename`：文件名，例如 `project_api_design.md`。
- `file_path`：完整文件路径。
- `mtime_ms`：文件修改时间，单位毫秒。
- `description`：frontmatter 中的描述。
- `type`：frontmatter 中的类型。

它不会读取完整 memory 正文，只读取文件前 30 行，用来降低召回前扫描成本。

### 4.3 `RelevantMemory`

`RelevantMemory` 表示已经被选中、准备注入模型上下文的 memory。

字段：

- `path`：文件路径。
- `content`：文件内容，可能被截断。
- `mtime_ms`：修改时间。
- `header`：注入前附加的说明头，例如保存时间或过期提醒。

### 4.4 `MemoryPrefetch`

`MemoryPrefetch` 是异步预取任务的句柄。

```python
class MemoryPrefetch:
    def __init__(self, task: asyncio.Task):
        self.task = task
        self.consumed = False

    @property
    def settled(self) -> bool:
        return self.task.done()
```

它包装了一个 `asyncio.Task`，调用方可以检查任务是否完成，并避免重复消费结果。

## 5. CRUD 和索引维护

### 5.1 `list_memories()`

`list_memories()` 会扫描 memory 目录下所有 `.md` 文件，但跳过 `MEMORY.md`。

流程：

1. 遍历 memory 目录中的 Markdown 文件。
2. 使用 `parse_frontmatter()` 解析 frontmatter。
3. 必须存在 `name` 和 `type`，否则跳过。
4. 如果 `type` 不在合法类型里，默认当成 `project`。
5. 构造 `MemoryEntry`。
6. 按文件修改时间倒序排序。

它主要服务于索引生成和列表展示。

### 5.2 `save_memory()`

`save_memory()` 负责保存一条 memory。

```python
def save_memory(name: str, description: str, type: str, content: str) -> str:
```

流程：

1. 根据 `type` 和 `name` 生成文件名。
2. 用 `format_frontmatter()` 生成 Markdown 内容。
3. 写入 memory 目录。
4. 调用 `_update_memory_index()` 更新 `MEMORY.md`。
5. 返回写入的文件名。

文件名生成规则：

```python
filename = f"{type}_{_slugify(name)}.md"
```

`_slugify()` 只保留小写英文字母和数字，把其他字符替换成 `_`，最多保留 40 个字符。

注意：如果 `name` 主要是中文，当前 `_slugify()` 可能生成空字符串，最终文件名可能变成类似 `user_.md`。这是当前实现的一个限制。

### 5.3 `delete_memory()`

`delete_memory()` 根据文件名删除 memory 文件。

流程：

1. 拼出 memory 文件路径。
2. 文件不存在则返回 `False`。
3. 删除文件。
4. 更新 `MEMORY.md` 索引。
5. 返回 `True`。

### 5.4 `_update_memory_index()`

`_update_memory_index()` 会根据当前所有 memory 文件重新生成 `MEMORY.md`。

索引格式：

```markdown
# Memory Index

- **[记忆名称](filename.md)** (type) — description
```

这个索引不是给用户手动维护的，而是由系统自动生成。

### 5.5 `load_memory_index()`

`load_memory_index()` 读取 `MEMORY.md`，用于后续拼接进系统提示词。

它有两层限制：

```python
MAX_INDEX_LINES = 200
MAX_INDEX_BYTES = 25000
```

如果索引太长，会按行数或字节数截断，避免 prompt 太大。

## 6. 轻量扫描和 manifest 生成

### 6.1 `scan_memory_headers()`

`scan_memory_headers()` 用于快速扫描可召回的 memory 摘要。

它和 `list_memories()` 的区别是：

- `list_memories()` 读取完整文件正文。
- `scan_memory_headers()` 只读取每个文件前 30 行。

流程：

1. 遍历 memory 目录下的 `.md` 文件。
2. 跳过 `MEMORY.md`。
3. 读取文件状态，拿到修改时间。
4. 读取前 30 行并解析 frontmatter。
5. 构造 `MemoryHeader`。
6. 按修改时间倒序排序。
7. 最多返回 `MAX_MEMORY_FILES` 条。

限制：

```python
MAX_MEMORY_FILES = 200
```

### 6.2 `format_memory_manifest()`

`format_memory_manifest()` 把 `MemoryHeader` 列表转换成给 side query 使用的文本清单。

示例格式：

```text
- [project] project_api_design.md (2026-06-08T03:00:00+00:00): API 设计决策
- [user] user_answer_style.md (2026-06-07T10:00:00+00:00): 用户回答风格偏好
```

这个 manifest 不包含正文，只包含文件名、类型、时间和描述，用来让模型低成本判断哪些 memory 可能相关。

## 7. 时间和新鲜度提示

### 7.1 `memory_age()`

`memory_age()` 根据 `mtime_ms` 返回人类可读的保存时间：

- 今天：`today`
- 昨天：`yesterday`
- 更早：`N days ago`

### 7.2 `memory_freshness_warning()`

`memory_freshness_warning()` 用来提醒模型：旧 memory 可能已经过期。

如果 memory 是今天或昨天保存的，不返回提醒。

如果超过 1 天，会生成类似含义的提醒：

```text
This memory is N days old. Memories are point-in-time observations...
```

这点很重要：memory 是“过去某个时间点的观察”，不能直接当成当前事实。特别是代码结构、行为、接口等信息，使用前应该重新核对当前代码。

## 8. 语义召回流程

语义召回由 `select_relevant_memories()` 完成。

```python
async def select_relevant_memories(
    query: str,
    side_query: SideQueryFn,
    already_surfaced: set[str],
) -> list[RelevantMemory]:
```

它的作用是：根据当前用户 query，从 memory 文件中选择最多 5 个明显相关的 memory，并读取其内容。

完整流程：

1. 调用 `scan_memory_headers()` 获取所有 memory 摘要。
2. 如果没有 memory，返回空列表。
3. 用 `already_surfaced` 过滤已经展示过的 memory，避免重复召回。
4. 调用 `format_memory_manifest()` 构造候选清单。
5. 调用 `side_query()`，让辅助模型判断哪些 memory 相关。
6. 从 side query 响应中用正则提取 JSON。
7. 解析 JSON 中的 `selected_memories`。
8. 按文件名匹配候选 memory，最多取 5 个。
9. 读取被选中文件的正文。
10. 如果文件过大，按 `MAX_MEMORY_BYTES_PER_FILE` 截断。
11. 生成新鲜度说明头。
12. 返回 `RelevantMemory` 列表。

side query 使用的系统提示词是 `SELECT_MEMORIES_PROMPT`，它要求返回 JSON：

```json
{
  "selected_memories": ["project_api_design.md", "user_answer_style.md"]
}
```

如果没有明确相关的 memory，应返回：

```json
{
  "selected_memories": []
}
```

异常处理：

- 如果异常信息包含 `cancel`，静默返回空列表。
- 其他异常会打印 `[memory] semantic recall failed: ...`，然后返回空列表。

## 9. 异步预取流程

`start_memory_prefetch()` 用来提前启动 memory 召回，但不等待结果。

```python
def start_memory_prefetch(
    query: str,
    side_query: SideQueryFn,
    already_surfaced: set[str],
    session_memory_bytes: int,
) -> MemoryPrefetch | None:
```

它有三道 gate：

### 9.1 只处理多词输入

```python
if not re.search(r"\s", query.strip()):
    return None
```

只有 query 中包含空白字符才会触发预取。

例如：

- `hello`：不触发。
- `hello world`：触发。
- `这段代码什么意思`：不触发，因为没有空格。

这对中文输入不太友好，是当前实现需要注意的地方。

### 9.2 session memory 预算不能超限

```python
if session_memory_bytes >= MAX_SESSION_MEMORY_BYTES:
    return None
```

当前限制：

```python
MAX_SESSION_MEMORY_BYTES = 60 * 1024
```

即每个会话最多累计注入约 60KB memory。

### 9.3 memory 目录里必须有可用文件

```python
has_memories = any(f.suffix == ".md" and f.name != "MEMORY.md" for f in d.iterdir())
```

如果只有 `MEMORY.md` 索引，没有实际 memory 文件，则不启动预取。

### 9.4 启动后台任务

所有 gate 通过后，函数会创建异步任务：

```python
task = asyncio.create_task(
    select_relevant_memories(query, side_query, already_surfaced)
)
return MemoryPrefetch(task)
```

调用方拿到的是 `MemoryPrefetch`，不是 memory 内容本身。

## 10. 注入格式

`format_memories_for_injection()` 把召回的 memory 转成可注入模型上下文的文本。

```python
def format_memories_for_injection(memories: list[RelevantMemory]) -> str:
```

每条 memory 会被包成：

```xml
<system-reminder>
Memory (saved today): /path/to/memory.md:

memory content
</system-reminder>
```

如果 memory 较旧，header 中会先出现新鲜度提醒，提醒模型核对当前代码，不要把旧记忆直接当事实。

## 11. 系统提示词生成

`build_memory_prompt_section()` 生成一段 memory 相关的系统提示词。

它会包含：

1. 当前 memory 目录路径。
2. 支持的 memory 类型。
3. 如何保存 memory。
4. 哪些内容不应该保存。
5. 什么时候召回 memory。
6. 当前 `MEMORY.md` 索引内容。

保存格式示例也会写进 prompt：

```markdown
---
name: memory name
description: one-line description
type: user|feedback|project|reference
---
Memory content here.
```

需要注意：`build_memory_prompt_section()` 当前定义在 `agents/memory.py` 中，但从搜索结果看，`agents/prompt.py` 当前没有调用它，所以默认系统提示词可能还没有真正包含这段 memory 说明。

## 12. 和其他模块的关系

### 12.1 `agents/tools.py`

工具层的 `write_file` 写文件后会调用 `_auto_update_memory_index()`。

当写入路径满足以下条件时，会自动更新 memory 索引：

- 文件路径位于 `get_memory_dir()` 下。
- 文件后缀是 `.md`。
- 文件不是 `MEMORY.md`。

这意味着 Agent 即使用普通写文件工具创建 memory，也能触发索引更新。

### 12.2 `agents/agent.py`

`Agent._chat_anthropic()` 中有启动 memory 预取的代码：

```python
memory_prefetch = start_memory_prefetch(
    user_message, sq,
    self._already_surfaced_memories, self._session_memory_bytes,
)
```

设计意图是：

1. 用户消息进入后，先追加到消息历史。
2. 如果不是 sub-agent，就构造 side query。
3. 用 side query 异步启动 memory 召回。
4. 后续在合适时机消费 `memory_prefetch` 的结果并注入上下文。

但当前搜索结果只看到启动预取，没有看到消费 `memory_prefetch`、调用 `format_memories_for_injection()`、更新 `_session_memory_bytes` 或更新 already surfaced 集合的完整逻辑。

## 13. 当前代码注意点

下面是阅读当前代码时发现的几个实现注意点。

### 13.1 import 路径可能不一致

`agents/memory.py` 中写的是：

```python
from utils.frontmatter import parse_frontmatter, format_frontmatter
```

但仓库中的实际文件是：

```text
agents/utils/frontmatter.py
```

如果运行环境没有额外把 `agents` 加到 `PYTHONPATH`，这个 import 可能失败。更稳妥的写法通常是：

```python
from agents.utils.frontmatter import parse_frontmatter, format_frontmatter
```

具体是否需要修改，要看项目实际启动方式。

### 13.2 already surfaced 变量名不一致

`Agent.__init__` 中初始化的是：

```python
self._already_surfaced_memorized: set[str] = set()
```

但 `_chat_anthropic()` 中使用的是：

```python
self._already_surfaced_memories
```

这两个名字不一致。按当前代码，运行到这里可能出现 `AttributeError`。

### 13.3 中文 query 可能不会触发预取

`start_memory_prefetch()` 使用 `re.search(r"\s", query.strip())` 判断是否是“多词输入”。

中文自然句通常没有空格，例如：

```text
这段代码什么意思
```

这种输入不会触发 memory prefetch。

### 13.4 截断逻辑按字节判断但按字符截断

当前代码：

```python
if len(content.encode()) > MAX_MEMORY_BYTES_PER_FILE:
    content = content[:MAX_MEMORY_BYTES_PER_FILE]
```

判断使用的是字节数，截断使用的是字符数。英文基本没问题，但中文、emoji 等多字节字符会导致实际截断结果和字节限制不完全一致。

### 13.5 `_slugify()` 对中文名称支持有限

`_slugify()` 只保留 `[a-z0-9]`，中文会被替换掉。

如果 memory 名称是中文，文件名可能不够可读，甚至只剩类型前缀。

## 14. 总结

`agents/memory.py` 是一个基于文件的长期记忆模块。

核心链路可以概括为：

```text
保存 memory
  -> 写入 Markdown + frontmatter
  -> 自动更新 MEMORY.md 索引

用户发起 query
  -> 扫描 memory header
  -> side query 挑选相关文件
  -> 读取文件正文
  -> 加入新鲜度提醒
  -> 包装成 system-reminder
  -> 注入模型上下文
```

当前代码已经具备 memory 存储、索引、扫描、召回和格式化能力，但从调用链看，召回结果的实际消费和系统提示词接入可能还没有完全打通，需要结合后续实现继续确认。
