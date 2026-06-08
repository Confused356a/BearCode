# Mem0 记忆管理机制说明

本文说明两件事：

1. Mem0 这类长期记忆系统通常如何管理记忆生命周期。
2. 本仓库当前 `agents/memory.py` 中的项目记忆实现是怎么工作的，以及还缺哪些闭环。

## 1. Mem0 的核心目标

Mem0 的目标不是把完整聊天历史无限塞回上下文，而是把对后续任务有长期价值的信息沉淀为结构化、可检索、可更新的记忆。

它解决的主要问题是：

- **上下文窗口有限**：历史对话越来越长时，不能每次都全量传给模型。
- **重要信息分散**：用户偏好、项目约定、业务事实、历史决策可能散落在多轮交互中。
- **记忆需要维护**：旧信息可能被新信息覆盖，错误记忆需要删除，重复记忆需要合并。
- **召回要相关**：每次请求只应该取回真正有帮助的少量记忆。

## 2. 记忆生命周期

Mem0 的记忆管理可以拆成五个阶段：

```text
用户输入 / 对话历史
        |
        v
  记忆抽取与判断
        |
        v
  写入 / 更新 / 删除
        |
        v
  向量库或数据库持久化
        |
        v
  查询时检索与重排
        |
        v
  注入模型上下文
```

### 2.1 记忆抽取

系统会从用户输入、助手回复或完整对话中判断哪些内容值得长期保存。

典型可保存的信息包括：

- 用户偏好，例如“以后回答尽量用中文”。
- 项目事实，例如“这个项目使用 Anthropic 和 OpenAI 双后端”。
- 代码约定，例如“工具定义集中在 `agents/tools.py`”。
- 业务规则，例如“计划模式需要先生成 Markdown 计划再执行”。
- 用户明确要求记住的内容。

不适合保存的信息包括：

- 临时命令输出。
- 一次性的错误日志。
- 没有长期价值的闲聊。
- 敏感信息，除非系统明确允许且有安全策略。

### 2.2 记忆结构化

一条记忆通常不只是纯文本，还会带元数据。

常见字段包括：

| 字段 | 作用 |
| --- | --- |
| `memory` / `content` | 记忆正文 |
| `user_id` | 归属用户 |
| `agent_id` | 归属 Agent |
| `run_id` / `session_id` | 归属会话或任务 |
| `metadata` | 项目、标签、来源、时间等附加信息 |
| `created_at` / `updated_at` | 生命周期管理 |
| `score` | 检索相关度 |

结构化的价值是让记忆可以按用户、项目、会话、类型隔离，避免不同上下文互相污染。

### 2.3 写入、更新与删除

长期记忆不能只追加，否则会出现重复、矛盾和过期信息。一个可用的记忆系统通常需要四种操作：

- **Add**：新增一条记忆。
- **Update**：当新信息覆盖旧信息时，更新已有记忆。
- **Delete**：用户撤销、信息错误或不再需要时删除。
- **Merge / Deduplicate**：相似记忆合并，减少重复召回。

例如：

```text
旧记忆：用户喜欢使用 Python 3.9。
新输入：这个项目已经升级到 Python 3.12。
结果：更新旧记忆，而不是再新增一条冲突记忆。
```

### 2.4 存储

Mem0 一般会把记忆存到可检索的后端中。常见组合是：

- **向量存储**：用于语义检索，找到和当前问题语义接近的记忆。
- **结构化数据库**：用于按用户、项目、标签、时间过滤。
- **图关系存储**：用于表达实体关系，例如用户、项目、偏好、文件之间的关联。

实际部署时可以选择托管服务或自建存储。关键点不是具体后端，而是记忆需要具备“可持久化、可过滤、可更新、可检索”的能力。

### 2.5 查询召回

当用户发起新请求时，系统不会取回所有记忆，而是执行检索：

1. 根据当前用户问题生成查询。
2. 在记忆库中按用户、项目、会话等条件过滤。
3. 做语义检索，得到候选记忆。
4. 可选地进行重排，保留最相关的少量结果。
5. 把召回的记忆注入到模型上下文。

一个好的召回策略要控制三件事：

- **相关性**：只返回对当前任务有帮助的内容。
- **数量**：避免把上下文塞满。
- **新鲜度**：更近、更明确的信息优先于旧信息。

## 3. 本仓库当前的记忆实现

本仓库目前没有直接使用官方 Mem0 SDK，而是在 `agents/memory.py` 中实现了一套项目级 Markdown 记忆机制。

相关文件：

- `agents/memory.py`：负责记忆目录、候选选择、异步预取。
- `agents/agent.py`：在聊天前启动记忆预取。
- `agents/tools.py`：写入记忆文件后自动维护索引文件。
- `agents/utils/frontmatter.py`：提供 YAML frontmatter 的简单解析与格式化。

### 3.1 记忆存储位置

当前实现把记忆保存在当前项目专属目录中：

```python
Path.home() / ".bear-code" / "projects" / _project_hash() / "memory"
```

其中 `_project_hash()` 使用当前工作目录路径的 SHA-256 前 16 位作为项目 ID：

```python
hashlib.sha256(str(Path.cwd()).encode()).hexdigest()[:16]
```

也就是说，不同项目目录会对应不同的记忆目录。

这种设计的好处是：

- 项目之间默认隔离。
- 不需要数据库即可持久化。
- Markdown 文件可人工查看和编辑。

局限是：

- 目录路径变化会导致项目 hash 变化。
- 没有跨设备同步。
- 没有语义向量检索，只能依赖文件元数据和模型选择。

### 3.2 记忆文件与索引

`agents/tools.py` 中的 `_write_file()` 在写文件后会调用 `_auto_update_memory_index()`。

如果写入路径满足以下条件，就会自动更新记忆索引：

- 文件在当前项目的 memory 目录下。
- 文件后缀是 `.md`。
- 文件名不是 `MEMORY.md`。

索引文件路径：

```text
~/.bear-code/projects/<project_hash>/memory/MEMORY.md
```

索引内容格式：

```markdown
# Memory Index

- **[名称](file.md)** (类型) — 描述
```

索引生成依赖每个记忆 Markdown 文件中的 frontmatter 字段：

```yaml
---
name: 项目结构
type: project
description: 记录 BearCode 的核心模块和职责边界
---

正文内容...
```

当前索引逻辑会读取：

- `name`
- `type`
- `description`

### 3.3 记忆选择 Prompt

`agents/memory.py` 中定义了 `SELECT_MEMORIES_PROMPT`。

它要求模型根据当前用户问题和可用记忆清单，返回 JSON：

```json
{
  "selected_memories": ["project-structure.md"]
}
```

选择策略比较保守：

- 最多选择 5 个文件。
- 只有明确有用才选择。
- 不确定时不要选择。
- 没有明显相关记忆时返回空数组。

这相当于使用 LLM 作为“记忆路由器”，先看文件名和描述，再决定哪些 Markdown 记忆值得读入上下文。

### 3.4 异步预取

`MemoryPrefetch` 是一个很小的任务句柄：

```python
class MemoryPrefetch:
    def __init__(self, task: asyncio.Task):
        self.task = task
        self.consumed = False

    @property
    def settled(self) -> bool:
        return self.task.done()
```

它的作用是让记忆选择可以和主流程并行执行。

在 `agents/agent.py` 的 Anthropic 聊天路径中，非子 Agent 会尝试启动记忆预取：

```python
if not self.is_sub_agent:
    sq = self._build_side_query()
    if sq:
        memory_prefetch = start_memory_prefetch(...)
```

`_build_side_query()` 会构造一个轻量模型调用函数：

- Anthropic 后端使用 `client.messages.create(...)`。
- OpenAI 后端使用 `client.chat.completions.create(...)`。
- 返回模型输出文本，供记忆选择逻辑解析。

这个设计避免主对话模型在正式回答前同步阻塞太久。

### 3.5 预算控制

当前记忆预取有一个会话级预算：

```python
MAX_SESSION_MEMORY_BYTES = 60 * 1024
```

`start_memory_prefetch()` 会检查：

- 用户输入必须包含空白字符，也就是看起来像多词查询。
- 当前会话已注入的记忆字节数不能超过 60KB。
- memory 目录下必须存在非 `MEMORY.md` 的 `.md` 文件。

这些限制的目的是减少不必要的模型调用，并控制长期记忆对上下文窗口的占用。

## 4. 当前代码中的未完成点

从现有代码看，记忆系统的设计骨架已经有了，但还没有完全闭环。

### 4.1 `agents/memory.py` 中缺少函数

`select_relevant_memories()` 调用了：

```python
scan_memory_headers()
format_memory_manifest(...)
```

但当前文件中没有定义这两个函数，仓库内也没有搜到实现。

预期职责应该是：

- `scan_memory_headers()`：扫描 memory 目录下的 Markdown 文件，解析 frontmatter，返回文件路径、名称、类型、描述、修改时间等摘要。
- `format_memory_manifest()`：把候选记忆摘要格式化成传给 LLM 的清单。

### 4.2 JSON 解析后没有完成读取逻辑

`select_relevant_memories()` 当前只做到：

```python
match = re.search(r"\{[\s\S]*\}", text)
if not match:
    return []
```

后续应该继续：

1. `json.loads(match.group(0))`
2. 读取 `selected_memories`
3. 校验文件名必须来自候选列表
4. 读取对应 Markdown 正文
5. 返回 `RelevantMemories`

当前函数在 `try` 块后没有完整返回逻辑，因此还不能真正完成召回。

### 4.3 `start_memory_prefetch()` 参数不匹配

当前定义是：

```python
def start_memory_prefetch(query, side_Query, session_memory_bytes)
```

但 `agents/agent.py` 的调用是：

```python
start_memory_prefetch(
    user_message, sq,
    self._already_surfaced_memories, self._session_memory_bytes,
)
```

这里调用传了 4 个参数，定义只接收 3 个参数。

同时函数体里实际调用：

```python
select_relevant_memories(query, side_query, already_surfaced)
```

但局部变量名是 `side_Query`，并且 `already_surfaced` 没有作为参数传入。

### 4.4 Agent 状态变量命名不一致

`Agent.__init__()` 中定义的是：

```python
self._already_surfaced_memorized: set[str] = set()
```

但聊天路径中使用的是：

```python
self._already_surfaced_memories
```

这会导致属性不存在。

### 4.5 预取结果尚未注入上下文

当前 `_chat_anthropic()` 中创建了 `memory_prefetch`，但后续代码片段里没有看到消费该任务结果、拼接记忆文本、更新 `_session_memory_bytes` 和 `_already_surfaced_*` 的逻辑。

完整闭环应包含：

1. 等待或检查 `memory_prefetch.task`。
2. 把返回的 `RelevantMemories` 格式化成上下文片段。
3. 注入到主模型消息中。
4. 标记这些记忆已经 surfaced。
5. 累加本会话记忆字节数。
6. 避免同一记忆重复注入。

## 5. 和标准 Mem0 的对照

| 能力 | 标准 Mem0 思路 | 本仓库当前实现 |
| --- | --- | --- |
| 记忆存储 | 数据库 / 向量库 / 图存储 | 项目目录下 Markdown 文件 |
| 用户隔离 | `user_id`、`agent_id`、`run_id` | 当前工作目录 hash |
| 记忆抽取 | 从对话中自动提取长期事实 | 当前未看到自动抽取入口 |
| 记忆索引 | 元数据和 embedding | `MEMORY.md` Markdown 索引 |
| 语义检索 | 向量搜索、过滤、重排 | LLM 根据文件名和描述选择 |
| 记忆更新 | 支持 update/delete/merge | 依赖文件写入覆盖 |
| 上下文注入 | 检索后注入模型提示词 | 预取框架存在，注入逻辑未完成 |
| 预算控制 | top_k、score、token 限制 | 会话 60KB 字节预算 |

## 6. 推荐补全方案

如果要把当前实现补成可用版本，建议按下面顺序做。

### 6.1 补齐文件扫描

新增一个记忆头结构，例如：

```python
@dataclass
class MemoryHeader:
    file_path: str
    filename: str
    name: str
    type: str
    description: str
    mtime_ms: float
```

`scan_memory_headers()` 负责：

- 遍历 `get_memory_dir().glob("*.md")`
- 跳过 `MEMORY.md`
- 解析 frontmatter
- 缺少 `name` / `type` / `description` 的文件可以跳过

### 6.2 补齐候选清单格式化

`format_memory_manifest()` 可以输出：

```text
- filename: project-structure.md
  name: 项目结构
  type: project
  description: 记录 BearCode 的核心模块和职责边界
```

这样 LLM 有足够信息做保守选择。

### 6.3 修正预取函数签名

推荐签名：

```python
def start_memory_prefetch(
    query: str,
    side_query: SideQueryFn,
    already_surfaced: set[str],
    session_memory_bytes: int,
) -> MemoryPrefetch | None:
```

同时把函数体内变量名统一为 `side_query`。

### 6.4 修正 Agent 属性名

统一使用一个名字，例如：

```python
self._already_surfaced_memories: set[str] = set()
```

### 6.5 补齐召回结果消费

在正式调用主模型前，把召回结果加入上下文：

```text
# Relevant project memories

## project-structure.md
...
```

然后更新：

```python
self._already_surfaced_memories.add(memory.path)
self._session_memory_bytes += len(memory.content.encode("utf-8"))
```

### 6.6 增加错误保护

记忆召回失败不应该影响主对话。推荐所有召回解析错误都降级为空记忆：

- JSON 解析失败：返回 `[]`
- 选中文件不存在：跳过
- 文件读取失败：跳过
- side query 超时：返回 `[]`

## 7. 总结

Mem0 的本质是把“长期有价值的信息”从完整对话中抽取出来，独立持久化，并在后续请求中按相关性少量召回。

本仓库当前实现选择了一条轻量路线：用项目 hash 做隔离，用 Markdown 文件做存储，用 `MEMORY.md` 做索引，用 LLM 根据文件描述选择相关记忆。这种方案简单、透明、便于调试，但目前代码还缺少扫描、解析、读取、注入和状态更新几个关键环节。

如果继续沿用这个方案，优先修复 `agents/memory.py` 的未定义函数和参数不匹配问题，再补齐预取结果注入主模型上下文，就可以形成一个可工作的项目记忆系统。
