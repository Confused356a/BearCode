# Bear Code 项目介绍文档

## 1. 项目概述

Bear Code 是一个使用 Python 实现的轻量级 Coding Agent 命令行项目。它借鉴 Claude Code 一类终端智能体的工作方式，将大模型对话、工具调用、文件编辑、Shell 执行、长期记忆、Skills、子 Agent、MCP 工具扩展和会话恢复整合在一个相对清晰的小型代码库中。

项目的核心目标不是替代 IDE，而是提供一个可阅读、可改造、可扩展的 Coding Agent 实现。它适合用于学习 Agent Loop 架构、二次开发个人编码助手、实验多模型兼容、扩展 MCP 工具链，以及构建带长期记忆和可进化 Skill 的本地 AI 开发助理。

## 2. 项目定位

Bear Code 的定位可以概括为：

- 面向软件工程任务的命令行智能体。
- 支持 OpenAI 兼容接口和 Anthropic 兼容接口。
- 具备文件读写、代码搜索、命令执行等基础工具能力。
- 支持 Plan Mode，把“先规划、后执行”作为安全工作流。
- 支持项目级和用户级 Skills，并具备可控自进化能力。
- 支持长期记忆和会话恢复，能够跨会话延续项目上下文。
- 支持 MCP，把外部工具服务动态注册为 Agent 可调用工具。

## 3. 核心亮点

### 3.1 清晰的 Agent Loop

核心逻辑集中在 `agents/agent.py`。Agent 会执行如下循环：

1. 构建 system prompt。
2. 注入项目规则、记忆、Skills、子 Agent 配置和 MCP 工具。
3. 调用 Anthropic 或 OpenAI 兼容模型接口。
4. 流式输出模型文本。
5. 解析模型返回的 tool call。
6. 执行本地工具、Skill、子 Agent 或 MCP 工具。
7. 将 tool result 回写给模型。
8. 持续循环，直到任务完成。
9. 自动保存会话，支持后续恢复。

这种结构足够接近真实 Coding Agent 的运行方式，同时代码量较小，适合阅读和改造。

### 3.2 同时兼容 OpenAI 和 Anthropic

项目内置两套客户端：

- `anthropic.AsyncAnthropic`
- `openai.AsyncOpenAI`

启动时会根据环境变量和 `--api-base` 自动判断使用哪种协议：

- base URL 路径包含 `/anthropic` 时，按 Anthropic 兼容接口处理。
- 配置 OpenAI API key 或 OpenAI base URL 时，按 OpenAI-compatible Chat Completions 工具调用格式处理。
- 也支持通用环境变量 `APIKEY` 和 `API`，方便接入 DeepSeek、代理服务或其他兼容网关。

### 3.3 工具系统完整

内置工具包括：

- `read_file`：读取文件并带行号返回。
- `write_file`：写入文件。
- `edit_file`：基于精确字符串替换编辑文件。
- `list_files`：按 glob 列出文件。
- `grep_search`：搜索代码内容。
- `run_shell`：执行 Shell 命令。
- `skill`：调用已注册 Skill。
- `skill_evolve`：将可复用反馈沉淀进 Skill。
- `agent`：启动子 Agent 处理独立任务。
- `tool_search`：激活延迟加载工具。

工具层还实现了权限检查、危险命令检测、写文件前读取检查、大结果持久化和输出截断。

### 3.4 Plan Mode 安全工作流

Plan Mode 用于只读规划，适合处理重构、复杂修复、架构调整等高风险任务。

进入 Plan Mode 后：

- Agent 只能读取文件。
- 不允许直接修改项目文件。
- 计划会写入 `~/.bear/plans/plan-<session>.md`。
- 用户审批后再切换到执行阶段。

相关入口：

```bash
python3 -m agents.main --plan "请分析这个项目该如何重构"
```

REPL 中也可以输入：

```text
/plan
```

### 3.5 Skills 与自进化能力

Bear Code 支持两类 Skill：

- 用户级：`~/.bear/skills/<skill_name>/SKILL.md`
- 项目级：`<project>/.bear/skills/<skill_name>/SKILL.md`

Skill 可以是：

- `inline`：把 Skill prompt 注入当前对话。
- `fork`：启动一个隔离子 Agent 来执行 Skill。

当前项目还加入了可控自进化机制，核心文件是：

```text
agents/skill_evolution.py
```

自进化能力包括：

- 记录每次 Skill 调用到 `.bear/skill-evolution/usage.jsonl`。
- 记录用户对 Skill 的反馈。
- 在用户给出明确、可复用、未来同类任务也适用的规则时，调用 `skill_evolve` 修改对应 Skill。
- 每次演化前保存旧版 `SKILL.md` 快照到 `.bear/skill-evolution/history/`。
- 自动更新 `version`、`last-evolved` 和 `evolution-count`。
- 在 Skill 正文追加 `## Evolution Notes`。

REPL 命令：

```text
/skills
/skill-stats
/skill-feedback <skill-name> <rating> [note]
/skill-evolve <skill-name> <durable lesson>
```

### 3.6 长期记忆系统

记忆系统位于 `agents/memory.py`。它使用文件型记忆：

- 每个项目独立 memory 目录。
- 当前项目路径会被 hash，避免不同项目之间的记忆串扰。
- 每条记忆是一个带 frontmatter 的 Markdown 文件。
- `MEMORY.md` 自动生成索引。
- 对话时先扫描记忆摘要，再通过 side query 选择相关记忆注入当前上下文。

默认目录：

```text
~/.BearCode/projects/<project_hash>/memory
```

REPL 中查看记忆：

```text
/memory
```

### 3.7 MCP 工具扩展

MCP 客户端位于 `agents/mcp_client.py`。项目不依赖 MCP SDK，而是直接通过 stdio JSON-RPC 与 MCP Server 通信。

支持配置来源：

- `~/.bear/settings.json`
- `.bear/settings.json`
- `.mcp.json`

MCP 工具会被包装为：

```text
mcp__<serverName>__<toolName>
```

这样可以避免外部工具和内置工具重名。

### 3.8 会话恢复与上下文压缩

项目支持自动保存会话和恢复最近会话：

```bash
python3 -m agents.main --resume
```

同时具备上下文压缩策略：

- 旧工具结果裁剪。
- 大结果持久化到文件。
- 接近上下文窗口上限时自动 compact。
- 支持手动 `/compact`。

### 3.9 多 Agent 扩展

Bear Code 支持通过 `agent` 工具启动子 Agent：

- `explore`：只读探索。
- `plan`：只读规划。
- `general`：完整工具能力。

子 Agent 拥有隔离上下文，适合做并行搜索、复杂分析、局部任务拆分。

## 4. 技术架构

### 4.1 运行链路

```text
用户输入
  |
  v
agents/main.py
  |
  v
Agent
  |
  +-- prompt.py        构建 system prompt
  +-- memory.py        召回长期记忆
  +-- skills.py        发现和执行 Skills
  +-- tools.py         执行内置工具
  +-- mcp_client.py    调用 MCP 工具
  +-- subagent.py      启动子 Agent
  +-- session.py       保存和恢复会话
  |
  v
OpenAI-compatible 或 Anthropic-compatible 模型
```

### 4.2 主要目录

```text
BearCode/
├── agents/
│   ├── main.py              # CLI 入口、参数解析、REPL
│   ├── agent.py             # Agent Loop、模型调用、工具调度
│   ├── tools.py             # 内置工具和权限系统
│   ├── prompt.py            # System prompt 构建
│   ├── skills.py            # Skill 发现、解析、执行
│   ├── skill_evolution.py   # Skill 自进化、版本快照、统计
│   ├── memory.py            # 长期记忆系统
│   ├── mcp_client.py        # MCP stdio JSON-RPC 客户端
│   ├── subagent.py          # 子 Agent 配置
│   ├── session.py           # 会话保存与恢复
│   ├── ui.py                # 终端 UI 输出
│   └── frontmatter.py       # frontmatter 解析和格式化
├── .bear/
│   └── skills/              # 项目级 Skills
├── docs/                    # 设计文档
├── Dockerfile               # Docker 镜像构建
├── requirements.txt         # Python 依赖
├── README.md                # 快速说明
├── 部署.md                  # 部署说明
└── PROJECT_INTRO.md         # 当前项目介绍文档
```

## 5. 环境要求

推荐环境：

- Python 3.11+
- pip
- Git
- macOS / Linux / Windows WSL

Docker 运行需要：

- Docker
- 可访问模型 API 的网络环境

Python 依赖见 `requirements.txt`：

```text
anthropic>=0.25.0
openai>=1.0.0
python-dotenv>=1.0.0
rich>=13.0.0
tqdm>=4.66.0
```

## 6. 本地启动方式

### 6.1 创建虚拟环境

```bash
cd /Users/xiao_xiong/Desktop/code/BearCode

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### 6.2 配置 `.env`

在项目根目录创建 `.env`，配置模型 API。下面几种方式任选一种。

## 7. Anthropic 兼容配置

### 7.1 Anthropic 官方接口

```env
ANTHROPIC_API_KEY=sk-ant-your-api-key
ANTHROPIC_BASE_URL=https://api.anthropic.com
MINI_CLAUDE_MODEL=claude-sonnet-4-6
```

启动：

```bash
python3 -m agents.main
```

一次性任务：

```bash
python3 -m agents.main "请 review agents/agent.py"
```

### 7.2 Anthropic 兼容网关

例如 DeepSeek 或其他提供 Anthropic-compatible endpoint 的服务：

```env
APIKEY=sk-your-api-key
API=https://api.deepseek.com/anthropic
MINI_CLAUDE_MODEL=claude-sonnet-4-6
```

也可以使用别名：

```env
MINI_CLAUDE_API_KEY=sk-your-api-key
MINI_CLAUDE_API_BASE=https://api.deepseek.com/anthropic
MINI_CLAUDE_MODEL=claude-sonnet-4-6
```

如果 `API` 或 `MINI_CLAUDE_API_BASE` 的路径包含 `/anthropic`，项目会按 Anthropic 协议创建客户端。

## 8. OpenAI 兼容配置

### 8.1 OpenAI 官方接口

```env
OPENAI_API_KEY=sk-your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
MINI_CLAUDE_MODEL=gpt-4o
```

启动：

```bash
python3 -m agents.main
```

一次性任务：

```bash
python3 -m agents.main --model gpt-4o "解释 agents/tools.py 的权限系统"
```

### 8.2 OpenAI-compatible 网关

适用于兼容 OpenAI Chat Completions 的代理服务、聚合 API 或本地模型网关：

```env
OPENAI_API_KEY=sk-your-api-key
OPENAI_BASE_URL=https://your-openai-compatible-host/v1
MINI_CLAUDE_MODEL=gpt-4o
```

也可以通过命令行临时覆盖：

```bash
python3 -m agents.main \
  --api-base https://your-openai-compatible-host/v1 \
  --model gpt-4o \
  "hello"
```

注意：如果 `--api-base` 不包含 `/anthropic`，Bear Code 会按 OpenAI-compatible 协议处理。

## 9. 常用启动命令

### 9.1 交互式 REPL

```bash
python3 -m agents.main
```

### 9.2 一次性任务

```bash
python3 -m agents.main "帮我阅读这个项目并总结架构"
```

### 9.3 指定模型

```bash
python3 -m agents.main --model gpt-4o "修复测试失败"
```

### 9.4 Plan Mode

```bash
python3 -m agents.main --plan "分析 memory 系统如何重构"
```

### 9.5 自动批准文件编辑

```bash
python3 -m agents.main --accept-edits "把 README 中的启动方式补充完整"
```

### 9.6 跳过确认

```bash
python3 -m agents.main --yolo "运行测试并修复失败"
```

### 9.7 恢复上次会话

```bash
python3 -m agents.main --resume
```

### 9.8 限制费用和轮次

```bash
python3 -m agents.main --max-cost 0.50 --max-turns 20 "实现一个小功能"
```

## 10. CLI 参数说明

| 参数 | 说明 |
|------|------|
| `--yolo`, `-y` | 跳过确认，使用 bypassPermissions 模式 |
| `--plan` | 进入只读 Plan Mode |
| `--accept-edits` | 自动批准文件编辑，但危险 shell 仍会按规则处理 |
| `--dont-ask` | 自动拒绝需要确认的操作，适合 CI |
| `--thinking` | 为支持的 Anthropic Claude 模型启用 extended thinking |
| `--model`, `-m` | 指定模型名称 |
| `--api-base` | 覆盖 `.env` 中的 API base URL |
| `--resume` | 恢复最近一次会话 |
| `--max-cost` | 设置估算费用上限 |
| `--max-turns` | 设置最大 Agent 轮次 |
| `--help`, `-h` | 显示帮助 |

## 11. REPL 命令

| 命令 | 说明 |
|------|------|
| `/clear` | 清空当前对话历史 |
| `/plan` | 切换 Plan Mode |
| `/cost` | 显示 token 和费用估算 |
| `/compact` | 手动压缩上下文 |
| `/memory` | 查看长期记忆 |
| `/skills` | 查看可用 Skills |
| `/skill-stats` | 查看 Skill 使用和演化统计 |
| `/skill-feedback <skill> <rating> [note]` | 记录某个 Skill 的反馈 |
| `/skill-evolve <skill> <lesson>` | 将可复用规则写入 Skill |
| `/<skill-name>` | 手动调用 user-invocable Skill |
| `exit` / `quit` | 退出 REPL |

## 12. Docker 启动方式

### 12.1 构建镜像

```bash
cd /Users/xiao_xiong/Desktop/code/BearCode
docker build -t bear-code .
```

### 12.2 运行容器

```bash
docker run --rm -it \
  --env-file .env \
  -v "$PWD:/workspace" \
  -v bear-code-sessions:/root/.bear-code \
  -v bear-code-memory:/root/.BearCode \
  bear-code
```

说明：

- `/workspace` 是容器内工作目录。
- `bear-code-sessions` 保存会话和大型工具结果。
- `bear-code-memory` 保存长期记忆。
- `.env` 提供模型 API 配置。

### 12.3 Docker 一次性任务

```bash
docker run --rm -it \
  --env-file .env \
  -v "$PWD:/workspace" \
  -v bear-code-sessions:/root/.bear-code \
  -v bear-code-memory:/root/.BearCode \
  bear-code \
  "请总结这个项目的架构"
```

### 12.4 Docker 中使用用户级 Skills

如果要把本机 `~/.bear` 中的 Skills、settings 和 agents 带入容器：

```bash
docker run --rm -it \
  --env-file .env \
  -v "$PWD:/workspace" \
  -v "$HOME/.bear:/root/.bear" \
  -v bear-code-sessions:/root/.bear-code \
  -v bear-code-memory:/root/.BearCode \
  bear-code
```

## 13. 配置加载优先级

API key 来源：

1. `APIKEY`
2. `MINI_CLAUDE_API_KEY`
3. `OPENAI_API_KEY`
4. `ANTHROPIC_API_KEY`

API base 来源：

1. 命令行 `--api-base`
2. `API`
3. `MINI_CLAUDE_API_BASE`
4. `OPENAI_BASE_URL`
5. `ANTHROPIC_BASE_URL`

协议判断规则：

- base URL 包含 `/anthropic`：使用 Anthropic-compatible 客户端。
- 否则只要有 base URL：使用 OpenAI-compatible 客户端。
- 没有 base URL 但配置了 Anthropic key：使用 Anthropic 客户端。
- 没有 base URL 但配置了 OpenAI key：使用 OpenAI 客户端。
- 只有 `APIKEY`：默认使用 Anthropic 客户端。

## 14. 数据目录

本地运行常用目录：

```text
~/.bear-code/                         # 会话、工具结果等运行数据
~/.BearCode/projects/<hash>/memory/   # 项目级长期记忆
~/.bear/skills/                       # 用户级 Skills
~/.bear/agents/                       # 用户级子 Agent 配置
~/.bear/rules/                        # 用户级或项目规则
```

项目内目录：

```text
.bear/skills/                         # 项目级 Skills
.bear/settings.json                   # 项目级权限/MCP 配置
.bear/skill-evolution/                # Skill 使用日志和演化快照，已加入 .gitignore
.mcp.json                             # Claude Code 风格 MCP 配置
```

## 15. 适合展示的项目亮点

如果用于简历、答辩或项目展示，可以重点强调：

1. 从零实现 Coding Agent 主循环，覆盖模型调用、工具调用、结果回传和多轮推理。
2. 同时兼容 Anthropic 和 OpenAI 两类工具调用协议，支持多模型和代理网关。
3. 实现文件编辑安全机制，包括编辑前读取、mtime 检查、危险命令确认和 Plan Mode。
4. 实现长期记忆系统，支持项目隔离、索引、召回和上下文注入。
5. 实现 Skills 系统，支持用户级和项目级 Skill，以及 inline/fork 两种执行模式。
6. 加入 Skill 自进化机制，具备使用记录、反馈记录、版本快照和可控演化能力。
7. 支持 MCP，无需 SDK 即可通过 stdio JSON-RPC 动态接入外部工具。
8. 支持子 Agent，能够隔离上下文处理探索、规划和通用任务。
9. 支持 Docker 部署，镜像内置 Python、Node.js、Playwright Chromium 和常用搜索工具。
10. 支持会话恢复和上下文压缩，能处理较长周期的软件工程任务。

## 16. 典型使用场景

- 阅读陌生代码库并生成架构说明。
- Review 某个文件、模块或 diff。
- 修改小型 bug，并运行测试验证。
- 先规划复杂重构，再按计划执行。
- 总结项目知识并沉淀到长期记忆。
- 为常见任务创建 Skill，例如代码审查、文档生成、小说写作、项目分析。
- 通过 MCP 接入浏览器、数据库、文件系统或其他外部工具。
- 在 Docker 中运行隔离的本地 Coding Agent。

## 17. 最小可用示例

### 17.1 使用 OpenAI-compatible 模型

`.env`：

```env
OPENAI_API_KEY=sk-your-api-key
OPENAI_BASE_URL=https://your-openai-compatible-host/v1
MINI_CLAUDE_MODEL=gpt-4o
```

运行：

```bash
python3 -m agents.main "请介绍这个项目的核心模块"
```

### 17.2 使用 Anthropic-compatible 模型

`.env`：

```env
APIKEY=sk-your-api-key
API=https://api.deepseek.com/anthropic
MINI_CLAUDE_MODEL=claude-sonnet-4-6
```

运行：

```bash
python3 -m agents.main "请帮我 review agents/skills.py"
```

### 17.3 使用 Plan Mode

```bash
python3 -m agents.main --plan "请给出 skill 系统重构方案，不要直接改代码"
```

### 17.4 使用 Skill 自进化

```text
/skills
/skill-feedback code_review good 能发现 API 契约问题
/skill-evolve code_review Review 时必须检查调用方和被调用方的参数格式是否一致。
/skill-stats
```

## 18. MCP / Skills / Tools / Memory 实现详解

这一章补充 Bear Code 中四个核心扩展系统的知识背景和项目实现方式。它们共同决定了这个 Agent 是否能从普通聊天助手变成真正能做工程任务的编码智能体。

### 18.1 Tools：Agent 行动能力层

#### 18.1.1 Tools 是什么

在 Agent 系统中，Tools 是模型和真实环境之间的动作接口。模型本身只能生成文本，不能直接读取文件、修改代码、运行测试或调用外部服务。工具系统把这些动作封装成结构化函数，模型只需要按 schema 生成参数，Agent 负责执行并把结果返回给模型。

在 Bear Code 中，工具系统承担四类职责：

1. 给模型暴露可调用工具 schema。
2. 校验和执行工具调用。
3. 根据权限模式决定是否放行、拒绝或请求用户确认。
4. 将工具结果转换成模型可继续推理的文本。

#### 18.1.2 本项目内置工具

当前内置工具定义在 `agents/tools.py` 的 `tool_definitions` 中：

```text
read_file        读取文件，返回带行号内容
write_file       写入文件
edit_file        基于 old_string / new_string 精确替换
list_files       按 glob 模式列出文件
grep_search      搜索文件内容
run_shell        执行 shell 命令
skill            调用已注册 Skill
skill_evolve     把可复用反馈沉淀进 Skill
enter_plan_mode  进入 Plan Mode
exit_plan_mode   退出 Plan Mode
agent            启动子 Agent
tool_search      激活延迟工具
```

当前项目不再暴露网页抓取类内置工具；工具 schema、权限列表和并发安全列表均以当前实际可用工具为准。

#### 18.1.3 工具 schema 如何暴露给模型

Bear Code 使用统一的工具定义结构：

```python
{
    "name": "read_file",
    "description": "...",
    "input_schema": {
        "type": "object",
        "properties": {...},
        "required": [...]
    }
}
```

Anthropic 接口可以直接使用这种 `input_schema` 风格。OpenAI-compatible 接口需要转换成 function calling 格式，因此 `agents/agent.py` 中有 `_to_openai_tools()`，会把工具转换成：

```python
{
    "type": "function",
    "function": {
        "name": "...",
        "description": "...",
        "parameters": {...}
    }
}
```

这就是 Bear Code 能同时兼容 Anthropic 和 OpenAI 工具调用协议的关键之一。

#### 18.1.4 工具执行流程

工具执行主入口是 `agents/tools.py` 中的：

```python
execute_tool(name, inp, read_file_state)
```

执行流程大致是：

1. Agent 收到模型返回的 tool call。
2. `agents/agent.py` 先做权限检查。
3. 特殊工具由 Agent 自己处理：
   - `agent`
   - `skill`
   - MCP 工具
   - Plan Mode 工具
4. 普通内置工具交给 `execute_tool()`。
5. 工具返回字符串结果。
6. Agent 把结果包装成 tool result，再发回模型。

#### 18.1.5 权限系统

权限检查由 `check_permission()` 完成。它综合考虑：

- 当前 permission mode。
- 用户级和项目级 settings。
- 工具类型。
- 是否危险命令。
- 是否写入新文件。
- 是否处于 Plan Mode。

支持的权限模式：

```text
default             默认模式，需要时询问用户
bypassPermissions   跳过确认
plan                只读规划模式
acceptEdits         自动接受文件编辑
dontAsk             需要确认时自动拒绝
```

只读工具：

```text
read_file
list_files
grep_search
```

写入类工具：

```text
write_file
edit_file
skill_evolve
```

在 Plan Mode 中，普通写入工具会被阻断，只有写计划文件这一类受控操作会被允许。

#### 18.1.6 文件编辑安全机制

Bear Code 对文件写入做了两层保护：

第一层是“编辑前读取”：

- `read_file` 成功后会记录文件的绝对路径和 mtime。
- `write_file` / `edit_file` 修改已有文件前，会检查该文件是否已被读过。
- 如果没读过，会拒绝编辑。

第二层是“外部修改检测”：

- 如果文件在读取后被其他进程或用户修改，mtime 会变化。
- Bear Code 会要求重新读取，避免基于旧内容覆盖用户改动。

这套机制让 Agent 在修改代码前必须先看当前文件，并且减少误覆盖风险。

#### 18.1.7 大结果处理

工具结果过大时，`agents/agent.py` 会调用 `_persist_large_result()`：

- 小结果直接进入上下文。
- 超过阈值的大结果会保存到 `~/.bear-code/tool-results/`。
- 对话中只保留路径、大小和前几百行预览。

这样可以避免一次命令输出或大文件读取撑爆上下文窗口。

#### 18.1.8 延迟工具机制

`enter_plan_mode` 和 `exit_plan_mode` 是 deferred tools。默认不直接暴露给模型，需要通过 `tool_search` 激活。

设计目的：

- 减少模型默认工具列表的噪音。
- 让不常用或高语义负载的工具按需加载。
- 保留未来扩展更多工具的空间。

### 18.2 Skills：可复用任务策略层

#### 18.2.1 Skills 是什么

Tools 解决“能做什么动作”，Skills 解决“遇到某类任务应该按什么方法做”。一个 Skill 本质上是一段可复用 prompt，加上触发条件、权限范围和执行上下文。

例如：

- 代码审查 Skill：规定 review 时优先找 bug、风险和缺失测试。
- 中文网文写作 Skill：规定写作流程、节奏控制和专项模块。
- 项目介绍文档 Skill：规定输出结构和重点。

#### 18.2.2 Skill 文件结构

Bear Code 只加载目录形式的 Skill：

```text
<skills_root>/<skill_name>/SKILL.md
```

例如：

```text
.bear/skills/code_review/SKILL.md
~/.bear/skills/code_review/SKILL.md
```

一个典型 Skill：

```markdown
---
name: code_review
description: Review code for bugs, security issues, regressions, maintainability risks, and missing tests.
user-invocable: false
when-to-use: Use when the user asks to review code.
context: inline
allowed-tools: read_file,grep_search
---

# Code Review Skill

...
```

#### 18.2.3 Skill frontmatter 字段

`agents/skills.py` 会解析这些字段：

| 字段 | 说明 |
|------|------|
| `name` | Skill 名称；缺省时使用目录名 |
| `description` | 简短描述，展示给模型和 `/skills` |
| `when-to-use` / `when_to_use` | 自动触发条件 |
| `user-invocable` | 是否允许用户用 `/<skill>` 手动调用 |
| `context` | `inline` 或 `fork` |
| `allowed-tools` | fork 模式下允许子 Agent 使用的工具 |

frontmatter 解析器在 `agents/frontmatter.py`，当前只支持简单的 `key: value` 形式，不支持复杂 YAML 嵌套。

#### 18.2.4 Skill 加载优先级

Skill 发现入口：

```python
discover_skills()
```

加载顺序：

1. 用户级：`~/.bear/skills`
2. 项目级：`Path.cwd()/.bear/skills`

用户级优先级更高。如果用户级和项目级存在同名 Skill，项目级不会覆盖用户级。

实现上使用一个 dict 保存 Skill：

```python
skills[name] = SkillDefinition(...)
```

项目级加载时 `overwrite=False`，因此同名用户级 Skill 会保留。

#### 18.2.5 Skill 如何注入 system prompt

`agents/prompt.py` 构建 system prompt 时，会调用：

```python
build_skill_descriptions()
```

它会把 Skill 分成两类：

- `user_invocable=True`：用户手动调用候选。
- `user_invocable=False`：模型自动调用候选。

对自动调用 Skill，system prompt 会告诉模型：

```text
When the user's request matches a skill's When to use, call the `skill` tool with that skill name before continuing.
```

因此 Skill 不是直接硬塞进上下文的全部内容，而是先把“有哪些 Skill、何时使用”告诉模型；真正需要时再调用 `skill` 工具展开完整 prompt。

#### 18.2.6 inline 和 fork 两种执行模式

`inline` 模式：

- `execute_skill()` 返回解析后的 prompt。
- Agent 把该 prompt 放回当前对话。
- 当前主 Agent 继续执行。
- 适合代码审查、文档写作、风格约束这类轻量任务策略。

`fork` 模式：

- Skill 不直接污染主上下文。
- Agent 创建一个子 Agent。
- 子 Agent 使用 Skill prompt 作为 system prompt。
- 子 Agent 完成任务后把结果返回主 Agent。
- 适合长任务、隔离探索、专项生成。

#### 18.2.7 Skill 参数替换

Skill 正文中可以使用：

```text
$ARGUMENTS
${ARGUMENTS}
${CLAUDE_SKILL_DIR}
```

实现位置：

```python
resolve_skill_prompt()
```

含义：

- `$ARGUMENTS` / `${ARGUMENTS}`：替换成用户调用 Skill 时传入的参数。
- `${CLAUDE_SKILL_DIR}`：替换成当前 Skill 目录，方便引用同目录下的 scripts、references、assets。

#### 18.2.8 Skill 自进化实现

自进化能力由 `agents/skill_evolution.py` 提供，`agents/skills.py` 负责接入。

核心数据：

```text
.bear/skill-evolution/usage.jsonl
.bear/skill-evolution/history/<skill>.jsonl
```

调用 Skill 时：

```python
record_skill_invocation(...)
```

记录内容：

- 调用时间
- Skill 名称
- 来源：user / project
- 执行上下文：inline / fork
- 参数预览

演化 Skill 时：

```python
evolve_skill(...)
```

执行步骤：

1. 找到目标 Skill 文件。
2. 读取当前 `SKILL.md`。
3. 把旧内容写入 history JSONL 作为快照。
4. bump patch 版本号。
5. 更新 `last-evolved` 和 `evolution-count`。
6. 在正文 `## Evolution Notes` 下追加可复用规则。
7. 重置 Skill 缓存。

`skill_evolve` 被视为写操作，在默认模式下需要用户确认，在 Plan Mode 中会被阻断。

### 18.3 Memory：长期上下文层

#### 18.3.1 Memory 是什么

Memory 解决的是“跨会话记住稳定信息”的问题。普通上下文只存在于当前会话，窗口满了还会被压缩；Memory 则以文件形式持久化，后续会话可以按需召回。

Bear Code 的 Memory 不是数据库，也不是向量库，而是文件型记忆系统。这样实现简单、可检查、容易手动修改，也方便和 git / 文件工具配合。

#### 18.3.2 Memory 存储路径

Memory 路径由当前项目目录 hash 得到：

```text
~/.BearCode/projects/<project_hash>/memory/
```

实现函数：

```python
get_memory_dir()
```

这样做的好处：

- 不同项目的记忆隔离。
- 同一个项目下多次启动可以复用记忆。
- 不需要在项目目录里写入用户个人长期数据。

#### 18.3.3 Memory 文件格式

每条记忆是一个 Markdown 文件，头部带 frontmatter：

```markdown
---
name: memory name
description: one-line description
type: user|feedback|project|reference
---

Memory content here.
```

支持四种类型：

| 类型 | 用途 |
|------|------|
| `user` | 用户身份、偏好、知识水平 |
| `feedback` | 用户纠正、反馈、输出偏好 |
| `project` | 项目目标、决策、长期任务状态 |
| `reference` | 外部资源、工具、链接、仪表盘 |

#### 18.3.4 MEMORY.md 索引

Memory 目录中会生成：

```text
MEMORY.md
```

它是所有记忆的索引，包含记忆名称、类型和描述。每次写入 memory 文件后，`_auto_update_memory_index()` 或 `_update_memory_index()` 会刷新索引。

system prompt 中不会默认塞入所有 memory 正文，而是先放入索引和使用说明。这样可以让模型知道“有哪些记忆”，但不让记忆正文无条件占用上下文。

#### 18.3.5 Memory 召回流程

Memory 召回的关键函数：

```python
start_memory_prefetch()
select_relevant_memories()
format_memories_for_injection()
```

流程如下：

1. 用户输入到来。
2. 如果输入太短、没有 memory、或本会话 memory 注入量已超预算，则不触发召回。
3. 扫描 memory 文件头部，而不是读取所有正文。
4. 生成 memory manifest。
5. 通过 side query 让模型选择最多 5 条相关记忆。
6. 读取被选中的 memory 正文。
7. 对过大的 memory 进行截断。
8. 包装成 `<system-reminder>` 注入当前对话。

#### 18.3.6 为什么使用异步预取

Memory 召回是通过 side query 完成的，如果同步执行，会增加每轮对话延迟。Bear Code 使用 `MemoryPrefetch`：

- 主请求前启动异步召回任务。
- 主 Agent 后续轮询任务是否完成。
- 完成后再把 memory 注入对话。

这样可以减少等待时间，也避免 memory 召回失败影响主对话。

#### 18.3.7 Memory 预算与过期提醒

项目里有三类限制：

```text
MAX_MEMORY_FILES = 200
MAX_MEMORY_BYTES_PER_FILE = 4096
MAX_SESSION_MEMORY_BYTES = 60 * 1024
```

同时旧记忆会附带 freshness warning。因为 memory 是某个时间点保存的观察，不一定代表当前代码状态，所以模型会被提醒先核对当前代码。

#### 18.3.8 Memory 和 Skill 的区别

Memory 保存“事实、偏好、历史决策”。

Skill 保存“可复用做事方法”。

例如：

- “用户喜欢中文回答，少写废话”：Memory。
- “写项目介绍文档时必须包含启动方式、模型兼容、亮点和架构图”：Skill。
- “这个项目当前使用 OpenAI-compatible 网关”：Memory。
- “代码审查时优先列 bug 和风险，不要先写总结”：Skill。

### 18.4 MCP：外部工具扩展层

#### 18.4.1 MCP 是什么

MCP 可以理解为一种外部工具协议。它让 Agent 不需要把所有工具都写进主项目，而是通过标准协议连接外部工具服务。

例如：

- 浏览器工具
- 数据库工具
- 文件系统工具
- GitHub 工具
- 内部业务系统工具

Bear Code 中的 MCP 实现目标是：读取配置、启动 MCP Server 子进程、发现工具、包装工具 schema、路由模型调用。

#### 18.4.2 本项目 MCP 实现特点

MCP 客户端在：

```text
agents/mcp_client.py
```

实现特点：

- 不依赖 MCP SDK。
- 使用 stdio 连接 MCP Server。
- 使用 JSON-RPC 2.0 消息格式。
- 每个 MCP Server 对应一个子进程。
- 每个请求都有自增 id，用 `_pending` 字典等待响应。
- 后台任务持续读取 server stdout。
- 单个 MCP Server 初始化失败不会影响主 Agent 启动。

#### 18.4.3 MCP 配置来源

Bear Code 会合并三个位置的配置：

```text
~/.bear/settings.json
<project>/.bear/settings.json
<project>/.mcp.json
```

支持两种 JSON 格式：

格式一：

```json
{
  "mcpServers": {
    "browser": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-example"],
      "env": {}
    }
  }
}
```

格式二：

```json
{
  "browser": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-example"],
    "env": {}
  }
}
```

只要配置对象中包含 `command`，就会被识别为 MCP Server。

#### 18.4.4 MCP 初始化流程

MCP 管理器入口：

```python
McpManager.load_and_connect()
```

流程：

1. 读取并合并 MCP 配置。
2. 为每个 server 创建 `McpConnection`。
3. 用 `asyncio.create_subprocess_exec()` 启动子进程。
4. 发送 `initialize` JSON-RPC 请求。
5. 发送 `notifications/initialized` 通知。
6. 调用 `tools/list` 获取工具列表。
7. 保存连接和工具定义。

每个 server 初始化和工具发现有超时保护，避免坏配置卡住整个 Agent。

#### 18.4.5 MCP 工具命名和路由

MCP 工具会被包装成：

```text
mcp__<serverName>__<toolName>
```

例如：

```text
mcp__browser__navigate
mcp__github__create_issue
```

这样做有两个目的：

1. 避免 MCP 工具和本地工具重名。
2. 调用时可以从工具名反解析 server 和 tool。

路由逻辑：

```python
McpManager.call_tool(prefixed_name, args)
```

它会：

1. 拆分 `mcp__server__tool`。
2. 找到对应 `McpConnection`。
3. 发送 `tools/call` JSON-RPC 请求。
4. 把 MCP content block 转成字符串返回给 Agent。

#### 18.4.6 MCP 工具如何暴露给模型

MCP Server 返回的工具一般使用 `inputSchema`。Bear Code 会转换成项目内部工具格式：

```python
{
    "name": "mcp__server__tool",
    "description": "...",
    "input_schema": inputSchema
}
```

随后这些工具会和内置工具一起进入当前模型调用的工具列表。对模型来说，MCP 工具和本地工具没有本质区别；对 Agent 来说，只要工具名以 `mcp__` 开头，就交给 MCP Manager 路由。

### 18.5 四个系统之间的关系

Tools、Skills、Memory、MCP 分别解决不同问题：

| 系统 | 解决的问题 | 本项目实现 |
|------|------------|------------|
| Tools | Agent 如何行动 | `agents/tools.py` + `agents/agent.py` 调度 |
| Skills | Agent 如何复用方法 | `agents/skills.py` + `.bear/skills` |
| Memory | Agent 如何记住长期信息 | `agents/memory.py` + `~/.BearCode/.../memory` |
| MCP | Agent 如何扩展外部工具 | `agents/mcp_client.py` + `.mcp.json` / settings |

它们在一次真实任务中的配合方式通常是：

1. 用户提出需求。
2. Memory 系统召回相关历史偏好或项目决策。
3. Skills 系统提示模型是否有适合该任务的方法。
4. 模型调用本地 Tools 阅读、搜索、编辑和运行命令。
5. 如果需要外部能力，模型调用 MCP 工具。
6. 如果用户给出稳定反馈，Skill 自进化系统把规则沉淀回 Skill。

这也是 Bear Code 相比普通聊天脚本更像 Coding Agent 的原因：它不仅能回答，还能行动、记忆、复用方法，并通过 MCP 接入更大的工具生态。

## 19. 后续可扩展方向

- 增加更完整的测试覆盖，特别是 Agent Loop、权限系统和 Skill 演化。
- 为 Skill 演化增加自动回滚命令。
- 增加更精细的费用估算，区分不同模型价格。
- 增加 MCP Server 健康检查和热加载。
- 增加 Web UI 或 TUI 面板展示会话、记忆和 Skill 统计。
- 引入向量索引提升长期记忆召回质量。
- 为 Docker 镜像增加更多运行模式和示例 compose 文件。
