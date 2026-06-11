# Bear Code

**从零造一个 Claude Code** — 一个轻量级的 AI 编码助手 CLI，使用 Python 实现。

Bear Code 是 Claude Code 的简化复刻实现。它通过命令行与大语言模型交互，可以作为你的 AI 结对编程助手，帮助完成代码搜索、修改、重构等软件工程任务。

---

## 项目结构

```
├── agents/                    # 核心代码
│   ├── main.py                # CLI 入口，参数解析、REPL 循环
│   ├── agent.py               # 核心 Agent 类，管理与大模型的对话与工具调用
│   ├── tools.py               # 工具定义（读/写文件、搜索、执行命令等）
│   ├── prompt.py              # 系统提示词构建，注入上下文（git、记忆、规则等）
│   ├── session.py             # 会话持久化，保存/加载对话历史
│   ├── memory.py              # 记忆系统（基于文件的四分类记忆）
│   ├── mcp_client.py          # MCP 客户端，连接外部 MCP 服务器
│   ├── subagent.py            # 子代理系统（explore/plan/general 三种内置类型）
│   ├── skills.py              # 技能系统，从 SKILL.md 加载可复用 prompt
│   ├── frontmatter.py         # YAML frontmatter 解析/格式化
│   └── ui.py                  # 终端 UI（颜色输出、旋转动画、工具调用展示）
├── docs/                      # 技术文档
├── .env.example               # 环境变量配置示例
├── Dockerfile                 # Docker 部署
├── requirements.txt           # Python 依赖
└── README.md                  # 项目简介
```

---

## 核心架构

Bear Code 采用 **Agent-工具-模型** 三层架构：

1. **Agent** (`agents/agent.py`): 核心调度器，负责维护与 LLM 的对话上下文，解析模型返回的 tool use 请求并执行对应工具，将结果反馈给模型。

2. **工具系统** (`agents/tools.py`): 定义了一组编程助手常用的工具，如读写文件、搜索代码、执行命令等。支持延迟工具（deferred tools）按需激活。

3. **多模型后端**: 支持 Anthropic 原生 API（Claude 系列）和 OpenAI 兼容 API（GPT 系列、DeepSeek 等）。

---

## 主要功能

### 交互式 REPL
启动后进入命令行交互模式，支持内置命令：

| 命令 | 功能 |
|------|------|
| `/clear` | 清空对话历史 |
| `/plan` | 切换计划模式（只读） |
| `/cost` | 查看 Token 用量和费用 |
| `/compact` | 手动压缩对话上下文 |
| `/memory` | 列出已保存的记忆 |
| `/skills` | 列出可用技能 |
| `/<skill-name>` | 调用技能 |

### 记忆系统
基于文件的四分类记忆（user / feedback / project / reference），支持自动语义检索和预取。记忆通过 `write_file` 工具保存，项目自动维护索引。

### MCP 客户端
支持通过 Model Context Protocol 连接外部工具服务器。配置读取自 `.claude/settings.json` 或 `~/.claude/settings.json` 中的 `mcpServers` 字段。

### 子代理系统
支持三种内置子代理类型：
- **explore**: 只读模式，用于快速代码库搜索
- **plan**: 只读模式，用于分析代码并生成实现计划
- **general**: 可使用全部工具（除 agent 外），独立完成任务

同时支持通过 `.claude/agents/*.md` 定义自定义代理类型。

### 技能系统
通过 `.claude/skills/<name>/SKILL.md` 文件定义可复用的 prompt 模板，支持 inline 和 fork 两种执行上下文。

### 权限模式
| 模式 | 说明 |
|------|------|
| `default` | 每次操作询问用户 |
| `bypassPermissions` | 跳过所有确认（--yolo） |
| `plan` | 只读计划模式 |
| `acceptEdits` | 自动批准文件编辑 |
| `dontAsk` | 自动拒绝所有确认 |

### 对话上下文管理
- 支持上下文窗口监测和自动压缩
- 支持会话持久化和恢复（`--resume`）
- 长结果自动截断
- 空闲 5 分钟自动微压缩

---

## 快速开始

### 配置
复制 `.env.example` 为 `.env`，填入 API 密钥：

```bash
# Anthropic 原生
ANTHROPIC_API_KEY=sk-ant-xxx

# 或 OpenAI 兼容
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://your-host/v1

# 或通用配置（兼容 Anthropic 格式的代理）
APIKEY=sk-xxx
API=https://api.deepseek.com/anthropic
```

### 安装与运行

```bash
pip install -r requirements.txt

# 交互式模式
python -m agents.main

# 一次性模式
python -m agents.main "请帮我修复这个 bug"

# YOLO 模式（自动确认）
python -m agents.main --yolo "运行所有测试"

# 计划模式（只读）
python -m agents.main --plan "如何重构这段代码？"
```

### Docker

```bash
docker build -t bear-code .
docker run -it --rm -v $(pwd):/workspace bear-code
```

---

## 支持的模型

- **Claude**: claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001 等
- **OpenAI**: gpt-4o, gpt-4o-mini 等
- **DeepSeek**: deepseek-chat 等
- 任何 OpenAI 兼容接口的模型

---

## 设计特点

- **简约**: 代码量小，核心功能完整，适合学习和二次开发
- **兼容**: 支持 Anthropic 原生 API 和 OpenAI 兼容 API
- **可扩展**: 通过 MCP、自定义子代理、技能系统等机制支持功能扩展
- **安全**: 完善的权限确认机制，对危险操作有明确的审批流程
