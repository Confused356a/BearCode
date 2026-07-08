<div align="center">

# Bear Code

**一个 Python 实现的轻量级 Coding Agent**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-supported-2496ED?style=flat-square&logo=docker&logoColor=white)
![Anthropic](https://img.shields.io/badge/Anthropic-compatible-black?style=flat-square)
![OpenAI](https://img.shields.io/badge/OpenAI-compatible-412991?style=flat-square)

</div>

---

Bear Code 是一个简化版的 Claude Code 风格命令行智能体。它支持交互式 REPL、文件读写、代码搜索、Shell 执行、Plan Mode、Skills、多 Agent、MCP、记忆系统、会话恢复和 Docker 部署。

它的目标不是做一个完整 IDE，而是提供一个足够小、足够清晰、方便阅读和改造的 Coding Agent 实现。

## 快速开始

### 本地运行

```bash
cd /Users/xiao_xiong/Desktop/code/BearCode

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
python3 -m agents.main
```

一次性任务：

```bash
python3 -m agents.main "请 review agents/agent.py"
```

### Docker 运行

```bash
docker build -t bear-code .
```

```bash
docker run --rm -it \
  --env-file .env \
  -v "$PWD:/workspace" \
  -v bear-code-sessions:/root/.bear-code \
  -v bear-code-memory:/root/.BearCode \
  bear-code
```

详见 [部署.md](./部署.md)。

## 配置 API

在项目根目录创建 `.env`。

Anthropic 兼容接口：

```env
APIKEY=sk-your-api-key
API=https://api.deepseek.com/anthropic
MINI_CLAUDE_MODEL=claude-sonnet-4-6
```

OpenAI 兼容接口：

```env
OPENAI_API_KEY=sk-your-api-key
OPENAI_BASE_URL=https://your-openai-compatible-host/v1
MINI_CLAUDE_MODEL=gpt-4o
```

也可以通过命令行覆盖：

```bash
python3 -m agents.main --model gpt-4o --api-base https://example.com/v1 "hello"
```

## 运行参数

| 参数 | 功能 |
|------|------|
| `--yolo`, `-y` | 跳过确认，直接执行允许的操作 |
| `--plan` | Plan Mode，只读规划，不直接修改文件 |
| `--accept-edits` | 自动批准文件编辑 |
| `--dont-ask` | 自动拒绝需要确认的操作，适合 CI |
| `--thinking` | 启用 Anthropic extended thinking |
| `--model`, `-m` | 指定模型 |
| `--api-base` | 覆盖 API base URL |
| `--resume` | 恢复最近一次会话 |
| `--max-cost` | 设置费用上限 |
| `--max-turns` | 设置最大 agent loop 轮次 |

示例：

```bash
python3 -m agents.main --plan "这个模块应该怎么重构？"
python3 -m agents.main --yolo "运行测试并修复失败"
python3 -m agents.main --resume
```

## REPL 命令

| 命令 | 功能 |
|------|------|
| `/clear` | 清空对话历史 |
| `/plan` | 切换 Plan Mode |
| `/cost` | 显示 token 用量和费用估算 |
| `/compact` | 手动压缩对话 |
| `/memory` | 列出已保存记忆 |
| `/skills` | 列出可用 skills |
| `/<skill-name>` | 手动调用指定 skill |

## 核心能力

- **Agent Loop**：模型回复、工具调用、工具结果回传、继续推理的循环。
- **文件工具**：读取、写入、编辑文件，带 mtime 防护和 diff 输出。
- **搜索工具**：文件列表、内容搜索。
- **Shell 工具**：执行命令，配合权限模式和危险命令检测。
- **流式输出**：支持 Anthropic 和 OpenAI 兼容后端的流式响应。
- **并发工具执行**：只读工具可以提前执行和并发执行。
- **上下文压缩**：支持预算裁剪、旧结果清理、自动 compact。
- **Plan Mode**：只读规划、计划审批、再进入执行模式。
- **Skills**：支持用户级和项目级 skills，inline/fork 两种模式。
- **多 Agent**：支持子 Agent 执行独立任务。
- **MCP 集成**：从 `.bear/settings.json` 加载 MCP server，动态注册工具。
- **记忆系统**：支持长期记忆、语义召回和异步预取。
- **会话恢复**：自动保存会话，支持 `--resume`。

## Skills

Bear Code 会加载两类 skills。

用户级 skills，优先级最高：

```text
~/.bear/skills/<skill_name>/SKILL.md
```

项目级 skills，优先级最低：

```text
<project>/.bear/skills/<skill_name>/SKILL.md
```

当前项目示例：

```text
.bear/skills/code_review/SKILL.md
```

如果用户级和项目级存在同名 skill，用户级优先。

一个 skill 的基本结构：

```markdown
---
name: code_review
description: Review code for bugs, security issues, regressions, maintainability risks, and missing tests.
user-invocable: false
when-to-use: Use when the user asks to review code, code review a file or diff, inspect code quality, find bugs, identify security issues, evaluate maintainability, or check for missing tests.
---

# Code Review Skill

...
```

检查是否加载成功：

```text
/skills
```

## 项目结构

```text
agents/
├── main.py          # CLI 入口、参数解析、REPL
├── agent.py         # Agent Loop、模型调用、工具执行、压缩、预算
├── tools.py         # 内置工具、权限检查、文件读写、Shell
├── prompt.py        # System Prompt 构建、规则加载、上下文注入
├── skills.py        # Skills 发现、解析、执行
├── subagent.py      # 子 Agent 配置和发现
├── memory.py        # 记忆系统和语义召回
├── mcp_client.py    # MCP JSON-RPC over stdio 客户端
├── session.py       # 会话保存与恢复
├── ui.py            # 终端输出、spinner、工具展示
└── frontmatter.py   # YAML frontmatter 解析

.bear/
└── skills/          # 项目级 skills

docs/                # 设计和记忆系统文档
Dockerfile           # Docker 镜像构建
部署.md              # 本地和 Docker 部署说明
requirements.txt     # Python 依赖
```

## 架构概览

```text
用户输入
  │
  ▼
CLI / REPL
  │
  ▼
Agent Loop
  │
  ├─ 构建 system prompt
  ├─ 调用模型 API
  ├─ 流式输出文本
  ├─ 解析 tool_use
  ├─ 执行工具
  ├─ 写入 tool_result
  ├─ 压缩上下文
  └─ 自动保存会话
```

## 数据目录

本地运行时：

```text
~/.bear-code      # 会话历史、工具结果
~/.BearCode       # 长期记忆
~/.bear           # settings、skills、agents、rules
```

Docker 运行时：

```text
/root/.bear-code
/root/.BearCode
/root/.bear
```

推荐通过 volume 持久化 Docker 数据：

```bash
-v bear-code-sessions:/root/.bear-code
-v bear-code-memory:/root/.BearCode
```

## 相关文档

- [部署.md](./部署.md)：本地运行、Docker 运行、skills 路径和挂载说明
- [问题排查.md](./问题排查.md)：问题排查与修复总结
- [docs/memory-system.md](./docs/memory-system.md)：记忆系统说明
- [docs/claude-code-agent-architecture.md](./docs/claude-code-agent-architecture.md)：Agent 架构说明
