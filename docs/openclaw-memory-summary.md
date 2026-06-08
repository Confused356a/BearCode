# OpenClaw Memory 部分总结

本文总结 OpenClaw 当前 memory 机制的整体设计思路、模块职责、运行流程和现阶段状态。

## 1. Memory 的定位

OpenClaw 的 memory 不是把完整聊天记录永久保存后每次全部塞回上下文，而是想做一套“项目级长期记忆”机制。

它的目标是：

- 把对后续开发任务有长期价值的信息沉淀下来。
- 按项目隔离记忆，避免不同代码库之间互相污染。
- 在用户提出新问题时，只召回少量和当前任务明确相关的记忆。
- 控制记忆注入上下文的大小，避免挤占主模型上下文窗口。

因此，它更接近一个轻量版的项目知识库，而不是完整的聊天历史回放系统。

## 2. 当前实现方式

OpenClaw 当前采用的是 Markdown 文件式 memory，而不是向量数据库或外部记忆服务。

核心思路是：

```text
当前项目路径
  -> 计算项目 hash
  -> 找到该项目专属 memory 目录
  -> 扫描 Markdown 记忆文件
  -> 让小模型/side query 判断哪些记忆相关
  -> 将相关记忆注入主模型上下文
```

记忆目录位于用户目录下：

```text
~/.bear-code/projects/<project_hash>/memory
```

其中 `<project_hash>` 来自当前工作目录路径的 SHA-256 前 16 位。这样不同项目默认拥有不同的 memory 空间。

这种方案的优点是简单、透明、容易人工维护；缺点是它不具备真正的向量检索、自动去重、自动冲突解决和跨设备同步能力。

## 3. 相关模块职责

### 3.1 `agents/memory.py`

这是 memory 机制的核心模块，主要负责：

- 获取当前项目的 memory 目录。
- 定义记忆召回时使用的选择 prompt。
- 定义被召回记忆的数据结构。
- 根据用户问题选择相关记忆。
- 启动异步 memory 预取任务。
- 控制单个会话中 memory 注入的累计字节预算。

其中比较关键的常量是：

```python
MAX_SESSION_MEMORY_BYTES = 60 * 1024
```

含义是单个会话累计注入的 memory 内容最多约 60KB。

### 3.2 `agents/agent.py`

Agent 负责在正式对话前触发 memory 预取。

它会构建一个 `side_query`，也就是一个轻量模型调用函数，用来让模型先判断“哪些 memory 文件和当前用户问题有关”。这个调用独立于主模型回答流程，设计上是为了减少主流程阻塞。

同时 Agent 里保存了两个和 memory 有关的状态：

- 已经注入过的 memory：避免同一个记忆在同一会话里重复出现。
- 当前会话 memory 字节数：避免 memory 内容持续膨胀。

### 3.3 `agents/tools.py`

工具层主要负责 memory 索引的自动维护。

当写入的文件位于当前项目的 memory 目录下，并且是 `.md` 文件，同时文件名不是 `MEMORY.md` 时，系统会自动更新索引文件：

```text
MEMORY.md
```

这个索引文件会收集各个 memory 文件的元数据，并生成类似下面的 Markdown 列表：

```markdown
# Memory Index

- **[项目结构](project-structure.md)** (project) - 记录项目核心模块和职责
```

### 3.4 `agents/utils/frontmatter.py`

这个模块提供了简单的 YAML frontmatter 解析和格式化能力。

memory 文件通常可以长这样：

```markdown
---
name: 项目结构
type: project
description: 记录 OpenClaw 的核心模块和职责边界
---

这里是具体记忆内容。
```

frontmatter 的作用是让系统不用读取全文，也能先通过 `name`、`type`、`description` 判断某个记忆是否可能相关。

## 4. Memory 文件结构

OpenClaw 的 memory 文件本质上是带元数据的 Markdown。

推荐字段包括：

| 字段 | 含义 |
| --- | --- |
| `name` | 记忆名称，用于索引展示 |
| `type` | 记忆类型，例如 `project`、`preference`、`decision`、`workflow` |
| `description` | 简短描述，用于召回选择 |
| 正文 | 具体长期记忆内容 |

这种结构有两个作用：

- 元数据用于快速筛选和索引展示。
- 正文用于真正注入模型上下文，帮助模型延续项目知识。

## 5. 召回流程

memory 召回大致分为五步。

1. 用户发起请求。
2. Agent 判断当前请求是否适合触发 memory 预取。
3. 系统扫描项目 memory 目录下的 Markdown 文件。
4. side query 根据用户请求和 memory 文件清单，选择最多 5 个明确相关的 memory。
5. 主模型在生成回答前拿到这些相关 memory，作为额外上下文。

选择 memory 的 prompt 设计比较保守：

- 最多选择 5 个。
- 只有明确有用才选择。
- 不确定时不选择。
- 没有相关 memory 时返回空数组。

这说明 OpenClaw 不希望 memory 召回过度激进，避免无关记忆干扰主任务。

## 6. 触发条件和预算控制

当前设计里，memory 预取不是每次都触发。

它会检查：

- 用户输入是否像一个正常查询，而不是单个词。
- 当前会话累计 memory 大小是否还在 60KB 预算内。
- 当前项目 memory 目录下是否存在可用的 Markdown 记忆文件。
- 当前 Agent 是否不是子 Agent。

这些限制的目的主要是节省模型调用、减少无效召回，并避免长期记忆不断挤占上下文。

## 7. 和传统 Mem0 / 向量记忆的区别

OpenClaw 当前 memory 更轻量，和 Mem0 这类标准长期记忆系统有明显区别。

| 能力 | 标准长期记忆系统 | OpenClaw 当前设计 |
| --- | --- | --- |
| 存储方式 | 数据库、向量库、图存储 | 项目目录下的 Markdown 文件 |
| 隔离方式 | 用户 ID、Agent ID、Session ID | 当前项目路径 hash |
| 检索方式 | embedding 语义检索、过滤、重排 | LLM 根据文件名和描述选择 |
| 自动抽取 | 从对话自动提取长期事实 | 当前主要依赖手动写入 memory 文件 |
| 更新机制 | add、update、delete、merge | 文件覆盖和索引重建 |
| 可解释性 | 取决于系统实现 | 很强，文件可直接查看 |
| 部署复杂度 | 较高 | 很低 |

也就是说，OpenClaw 的 memory 更像“本地项目记忆文件夹 + LLM 路由选择”，而不是完整的向量记忆平台。

## 8. 当前状态

从现有设计看，OpenClaw 的 memory 已经有了清晰的骨架：

- 有项目级 memory 目录。
- 有 Markdown 记忆文件格式。
- 有 `MEMORY.md` 索引思路。
- 有 side query 选择相关记忆的 prompt。
- 有异步预取任务结构。
- 有会话级 memory 字节预算。

但它还处在未完全闭环的阶段。

主要缺口包括：

- memory 文件扫描和 manifest 生成逻辑需要补齐。
- side query 返回 JSON 后，需要完成解析、校验和文件读取。
- 预取函数的参数和调用方需要统一。
- Agent 内部记录“已注入 memory”的变量名需要统一。
- 召回到的 memory 还需要真正注入主模型上下文。
- 注入后需要更新已注入集合和会话 memory 字节数。

因此，当前 memory 更准确地说是“设计骨架已经搭好，但召回到上下文的闭环还没完全打通”。

## 9. 推荐补全方向

如果要继续完善 OpenClaw memory，建议按下面顺序推进：

1. 补齐 memory 文件扫描能力。

   扫描 `memory` 目录下所有 `.md` 文件，跳过 `MEMORY.md`，读取 frontmatter，生成候选 memory 清单。

2. 补齐 manifest 格式化。

   把候选 memory 转成简洁文本，交给 side query 判断相关性。

3. 补齐 JSON 解析和文件读取。

   side query 返回 `selected_memories` 后，只允许读取候选清单中真实存在的文件，避免任意路径读取。

4. 打通上下文注入。

   将召回结果整理为类似下面的上下文片段：

   ```markdown
   # Relevant project memories

   ## project-structure.md

   ...
   ```

5. 更新会话状态。

   每次注入后记录文件路径，并累加 memory 字节数，避免重复注入和超预算。

6. 增加容错。

   memory 召回失败不应该影响主对话。任何解析失败、文件缺失、模型选择失败都应该降级为空 memory。

## 10. 总结

OpenClaw 的 memory 机制走的是轻量、本地、项目级路线。

它不依赖数据库和向量检索，而是用项目 hash 做隔离，用 Markdown 保存长期记忆，用 frontmatter 描述记忆内容，用 `MEMORY.md` 建索引，再通过 side query 让模型选择和当前任务相关的记忆。

这个方案的优势是简单透明，适合个人开发工具和本地 coding agent。它的短板是自动化程度和检索能力有限，目前代码层面也还需要补齐扫描、解析、读取、注入和状态更新，才能形成完整可用的 memory 闭环。
