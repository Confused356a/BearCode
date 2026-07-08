# Bear Code 简历包装

## 1. 项目名称

Bear Code：基于 Python 的可进化 Coding Agent 框架

可选英文名：

Bear Code: An Evolvable Python Coding Agent with Memory, Skills, Tool Calling and MCP Integration

## 2. 一句话项目介绍

从零实现了一个 Claude Code 风格的可进化命令行 Coding Agent，通过长期记忆、Skills、自进化反馈闭环和版本快照机制，使 Agent 能在多轮使用中沉淀用户偏好、复用任务方法并持续优化行为策略，同时支持 OpenAI / Anthropic 兼容模型、工具调用、Plan Mode、MCP 和子 Agent。

## 3. 简历项目经历版本

### 版本 A：突出可进化 Agent

**Bear Code：可进化 Coding Agent 框架**  
技术栈：Python、AsyncIO、OpenAI SDK、Anthropic SDK、JSON-RPC、MCP、Docker、Rich

- 从零实现可进化 Coding Agent 主循环，支持模型流式输出、工具调用解析、工具结果回传、多轮推理、会话恢复和上下文压缩，形成完整 Agent Loop。
- 设计“长期记忆 + Skills + 反馈记录 + 版本快照”的演化闭环：Memory 负责沉淀用户偏好和项目事实，Skills 负责沉淀可复用任务策略，`skill_evolve` 负责把稳定反馈写回 Skill。
- 实现可控 Skill 自进化机制，支持 Skill 调用日志、用户反馈记录、演化前快照、patch 版本递增、`last-evolved` / `evolution-count` 元数据更新和规则追加，避免模型无约束自改 prompt。
- 设计统一工具系统，封装文件读取、文件写入、精确编辑、代码搜索、Shell 执行、Skill 调用、Skill 演化、子 Agent 调度等能力，并适配 Anthropic `input_schema` 与 OpenAI function calling 两套协议。
- 实现权限与安全控制机制，支持 `default`、`plan`、`acceptEdits`、`bypassPermissions`、`dontAsk` 等模式，对文件编辑、危险命令和 Skill 演化进行确认或阻断。
- 构建文件型长期记忆系统，按项目路径 hash 隔离记忆目录，通过 frontmatter 管理 `user`、`feedback`、`project`、`reference` 等记忆类型，并通过异步 side query 召回相关记忆。
- 自研 MCP stdio JSON-RPC 客户端，无需 MCP SDK 即可启动 MCP Server、发现工具、包装工具 schema，并将外部工具动态接入 Agent。

### 版本 B：偏 AI Agent / 大模型应用

**Bear Code：面向软件工程任务的可进化 AI Agent**  
技术栈：Python、LLM Tool Calling、OpenAI-compatible API、Anthropic API、MCP、AsyncIO、Docker

- 搭建可运行的可进化 LLM Agent 框架，将大模型推理、工具调用、长期记忆、Skills、反馈沉淀、权限控制和任务执行整合为一个可交互 CLI。
- 设计 Agent 演化闭环：任务执行产生 Skill 调用记录，用户反馈进入 feedback log，稳定规则通过 `skill_evolve` 写回 `SKILL.md`，演化前自动保存历史快照。
- 实现可复用 Skills 体系，将代码审查、写作规范、项目分析等经验沉淀为可触发 prompt 模板，支持用户级 / 项目级优先级、自动触发、手动调用、inline / fork 执行。
- 设计长期记忆系统，支持用户偏好、反馈、项目决策和外部引用等类型，并通过异步预取、召回预算和旧记忆提醒避免记忆污染上下文。
- 同时兼容 Anthropic 与 OpenAI-compatible 模型接口，自动根据 API base URL 判断协议，并将统一工具定义转换为不同模型后端需要的 tool schema。
- 引入 Plan Mode 和多层权限控制，将复杂任务拆分为“只读探索 -> 生成计划 -> 用户审批 -> 执行修改”，降低 Agent 误改代码和错误演化风险。
- 接入 MCP 外部工具协议，通过 stdio JSON-RPC 将外部 MCP Server 动态扩展为模型可调用工具。

### 版本 C：适合简历一屏展示

**Bear Code - 可进化 Python Coding Agent**

- 基于 Python / AsyncIO 实现可进化命令行 Coding Agent，支持 OpenAI 与 Anthropic 兼容模型、流式输出、工具调用和会话恢复。
- 构建“Memory + Skills + Feedback + Snapshot”的自进化闭环，支持长期记忆召回、Skill 自动触发、反馈记录、版本快照和可控规则写回。
- 构建工具调用系统，提供文件读写、精确编辑、代码搜索、Shell 执行、子 Agent、Skill 调用、Skill 演化等能力，并实现权限控制、危险命令检测和编辑前读取保护。
- 自研 MCP stdio JSON-RPC 客户端，支持从 `.mcp.json` / settings 动态加载外部 MCP 工具并暴露给模型调用。
- 支持 Docker 部署和多种运行模式，包括 REPL、一次性任务、Plan Mode、恢复会话、费用和轮次限制。

## 4. 技术栈关键词

可以按投递方向选择性放入简历：

```text
Python, AsyncIO, LLM Agent, Tool Calling, OpenAI API, Anthropic API,
MCP, JSON-RPC, Docker, CLI, Rich, Prompt Engineering,
Evolvable Agent, Long-term Memory, Skills, Skill Evolution,
Feedback Loop, Version Snapshot, Multi-Agent, Permission Control
```

如果是中文简历：

```text
Python、AsyncIO、大模型 Agent、工具调用、OpenAI / Anthropic API、
MCP、JSON-RPC、Docker、命令行工具、可进化 Agent、长期记忆、
Skills、自进化、反馈闭环、版本快照、权限控制
```

## 5. 项目亮点拆解

### 5.0 可进化 Agent 闭环

可包装为：

- 设计可控演化链路：用户使用 Agent 完成任务后，系统记录 Skill 调用、用户反馈和演化事件。
- 将稳定、可复用的反馈通过 `skill_evolve` 写回对应 Skill，而不是临时停留在对话上下文中。
- 每次演化前保存旧版 `SKILL.md` 快照，支持后续审计和回滚。
- 使用 `version`、`last-evolved`、`evolution-count` 描述 Skill 演化状态。
- 将演化权限纳入工具权限系统，默认需要确认，Plan Mode 中阻断，避免无约束自修改。

对应代码：

```text
agents/skill_evolution.py
agents/skills.py
agents/tools.py
.bear/skill-evolution/
```

适合面试表达：

> 我这里说的可进化不是让 Agent 随机改自己，而是一个可控闭环：Memory 记住长期事实和偏好，Skills 保存可复用任务策略，用户反馈经过判断后通过 `skill_evolve` 写回 Skill，并且每次写回前都有版本快照和权限确认。

### 5.1 Agent 主循环

可包装为：

- 实现完整 Agent Loop：模型请求、流式输出、工具调用解析、工具执行、结果回传、多轮继续推理。
- 同时处理 Anthropic 和 OpenAI 两类消息结构与工具协议。
- 支持 token / cost 统计、最大轮次限制、上下文压缩和自动会话保存。

对应代码：

```text
agents/agent.py
agents/main.py
agents/session.py
```

### 5.2 多模型兼容

可包装为：

- 支持 Anthropic 原生和 OpenAI-compatible 两种模型接入方式。
- 通过环境变量和 `--api-base` 自动判断后端协议。
- 将内部统一工具定义转换为 OpenAI function calling schema。

对应能力：

```text
ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL
OPENAI_API_KEY / OPENAI_BASE_URL
APIKEY / API
MINI_CLAUDE_MODEL
```

### 5.3 工具系统

可包装为：

- 使用统一 `tool_definitions` 管理工具 schema。
- 将只读工具、写入工具、危险工具分层处理。
- 支持工具权限规则、计划模式、危险命令确认和写文件前读取。
- 支持大结果落盘，减少上下文污染。

对应代码：

```text
agents/tools.py
agents/agent.py
```

### 5.4 Plan Mode

可包装为：

- 设计只读规划模式，防止 Agent 在复杂任务中直接改代码。
- Agent 先探索项目并生成计划文件，再等待用户审批。
- 审批通过后进入执行模式。

适合面试表达：

> 我不是让 Agent 一上来就改文件，而是增加了 Plan Mode。复杂任务先进入只读模式，只允许读取文件和写计划文件，用户审批后再执行，这样能明显降低自动化编码的误操作风险。

### 5.5 长期记忆

可包装为：

- 使用文件型 memory，而不是黑盒数据库，方便审计和手动维护。
- 按项目路径 hash 隔离记忆，避免不同项目记忆串扰。
- 用 frontmatter 管理 `user`、`feedback`、`project`、`reference` 等记忆类型。
- 通过异步 side query 召回相关记忆，并以 `<system-reminder>` 形式注入当前上下文。

对应代码：

```text
agents/memory.py
```

### 5.6 Skills 与自进化

可包装为：

- 实现类似 Claude Skills 的能力扩展系统。
- 支持用户级和项目级 Skill，并通过优先级解决同名覆盖问题。
- 支持 `inline` 和 `fork` 两种执行模式。
- 加入 Skill 自进化机制：调用记录、反馈记录、版本快照、规则追加和缓存刷新。

对应代码：

```text
agents/skills.py
agents/skill_evolution.py
.bear/skills/
```

适合面试表达：

> Tools 解决 Agent 能做什么，Skills 解决 Agent 遇到某类任务应该怎么做。我把常见任务策略抽象成 SKILL.md，并通过用户反馈把稳定规则追加进 Skill，实现了可控的自进化，而不是让模型随意改 prompt。

### 5.7 MCP 外部工具扩展

可包装为：

- 实现 MCP stdio JSON-RPC 客户端。
- 从 `~/.bear/settings.json`、`.bear/settings.json`、`.mcp.json` 加载 MCP Server。
- 为每个 MCP Server 启动子进程，完成 initialize、tools/list、tools/call。
- 将 MCP 工具包装为 `mcp__server__tool`，避免和本地工具冲突。

对应代码：

```text
agents/mcp_client.py
```

适合面试表达：

> 我没有直接依赖 MCP SDK，而是自己实现了 stdio JSON-RPC 通信：启动 server 子进程、维护请求 id、后台读取 stdout、管理 pending future，并把外部工具转换成 Agent 内部统一工具 schema。

### 5.8 子 Agent

可包装为：

- 支持通过 `agent` 工具派生子 Agent。
- 子 Agent 拥有独立上下文，可执行探索、规划或通用任务。
- 适合将复杂任务拆分为并行分析、局部搜索和隔离执行。

对应代码：

```text
agents/subagent.py
agents/agent.py
```

## 6. 面试讲述版本

### 6.1 30 秒版本

Bear Code 是我用 Python 从零实现的一个可进化 Coding Agent。它不只是能调用工具完成代码任务，还能通过长期记忆保存用户偏好和项目事实，通过 Skills 沉淀可复用工作流，并把稳定反馈经过版本快照和权限确认后写回 Skill。项目同时支持 OpenAI / Anthropic 兼容模型、Plan Mode、MCP 外部工具和子 Agent。

### 6.2 1 分钟版本

这个项目的核心是一个可进化 Agent 闭环。底层是完整 Agent Loop：模型流式输出，遇到工具调用后由本地执行工具，再把结果回传给模型继续推理。在此基础上，我把 Memory 和 Skills 分成两层：Memory 负责保存用户偏好、项目事实和历史反馈；Skills 负责保存可复用任务策略。用户给出稳定反馈后，系统可以通过 `skill_evolve` 写回对应 Skill，写回前保存版本快照，并受权限系统控制。除此之外，项目还兼容 OpenAI 和 Anthropic 两套协议，支持 Plan Mode、MCP 外部工具和子 Agent。

### 6.3 3 分钟版本

Bear Code 是一个面向软件工程任务的可进化本地 Coding Agent。我做这个项目主要是为了验证一个思路：Agent 不应该只完成当前任务，还应该能把用户偏好、稳定反馈和任务方法沉淀下来，让后续同类任务做得更好。

第一部分是 Agent Loop。CLI 收到用户输入后，会构建 system prompt，把项目规则、记忆索引、可用 Skills、子 Agent 和工具定义注入进去，然后调用模型接口。模型返回文本时流式输出；如果返回 tool call，Agent 会检查权限、执行工具、把 tool result 回写给模型，让模型继续推理。

第二部分是工具系统。我实现了文件读取、写入、精确编辑、代码搜索、Shell 执行、Skill 调用和子 Agent。为了避免 Agent 误操作，我加了权限模式、危险命令检测、Plan Mode、编辑前读取和 mtime 检查。也就是说，Agent 修改一个已有文件前必须先读文件，如果读取后文件被外部修改，它会要求重新读取。

第三部分是模型兼容。项目同时支持 Anthropic 和 OpenAI-compatible 接口。内部工具定义保持统一，然后针对 OpenAI 转成 function calling schema；Anthropic 则使用 input_schema。API 配置支持官方 key，也支持代理网关和 DeepSeek 这类兼容接口。

第四部分是可进化闭环。Memory 是文件型长期记忆，按项目路径 hash 隔离，用 frontmatter 区分 user、feedback、project、reference。Skills 则是可复用任务策略，支持项目级和用户级，支持 inline 和 fork 执行。我实现了 Skill 自进化：调用 Skill 时记录 usage，用户可以记录 feedback；当反馈具有复用价值时，通过 `skill_evolve` 写回 `SKILL.md`，演化前保存历史快照，并自动更新 version、last-evolved 和 evolution-count。这样 Agent 的能力不是只停留在当前上下文里，而是能沉淀到可复用资产中。

第五部分是 MCP。我自己实现了 MCP stdio JSON-RPC 客户端，能读取 `.mcp.json` 和 settings，启动外部 MCP Server，完成 initialize、tools/list 和 tools/call，然后把工具包装成 `mcp__server__tool` 暴露给模型。

这个项目的价值在于它覆盖了可进化 Coding Agent 的核心工程问题：工具调用、权限安全、上下文管理、长期记忆、技能复用、反馈沉淀、版本快照、外部工具扩展和多模型兼容。

## 7. STAR 面试回答

### 问题：你这个项目解决了什么问题？

**S：背景**  
普通 LLM 聊天只能回答问题，不能稳定执行软件工程任务，更不能把用户反馈和任务经验沉淀成长期能力；而真实 Coding Agent 需要读代码、改文件、运行命令、记住项目上下文、复用任务策略，并在安全边界内持续改进。

**T：任务**  
我希望从零实现一个可进化 Coding Agent，不仅复现 Claude Code 类产品的工具调用链路，还要让它能通过 Memory、Skills 和反馈写回机制持续沉淀能力。

**A：行动**  
我实现了 Agent Loop、工具系统、OpenAI / Anthropic 协议适配、Plan Mode、长期记忆、Skills 系统、Skill 自进化闭环、版本快照、MCP stdio JSON-RPC 客户端和 Docker 部署。

**R：结果**  
最终项目可以在命令行中完成代码阅读、文件修改、命令执行、项目总结、代码审查和 Skill 复用，并能把稳定反馈沉淀为可演化 Skill，具备权限控制、会话恢复和可扩展工具生态。

### 问题：项目中最有技术含量的部分是什么？

可以回答：

1. 可控 Skill 自进化闭环。
2. Agent Loop 和工具调用协议适配。
3. 安全工具执行和文件编辑保护。
4. MCP stdio JSON-RPC 客户端。

推荐答案：

> 我觉得最有技术含量的是可控自进化闭环。普通 Agent 只是调用工具完成任务，我这里把用户反馈、长期记忆和 Skills 连接起来：Memory 保存长期事实和偏好，Skills 保存可复用任务策略，稳定反馈通过 `skill_evolve` 写回 Skill；写回前会保存版本快照，并且走权限系统。这样 Agent 能持续改进，但不是无约束地自我修改。

### 问题：你怎么保证 Agent 不乱改文件？

可以回答：

- Plan Mode：复杂任务先只读规划。
- 权限模式：default / acceptEdits / bypassPermissions / dontAsk。
- 危险命令检测：如 `rm`、`sudo`、`git reset`、`kill` 等。
- 编辑前读取：没读过的文件不能改。
- mtime 检查：读后被外部修改则要求重新读取。
- 新文件写入和 Skill 演化默认需要确认。

### 问题：Memory 和 Skills 有什么区别？

可以回答：

> Memory 保存事实和偏好，比如用户喜欢中文、某个项目的长期目标、之前做过的决策。Skills 保存方法和流程，比如代码审查时怎么输出、写项目文档时包含哪些部分。Memory 让 Agent 记住信息，Skills 让 Agent 复用能力。

### 问题：你说的“可进化”具体是什么？

可以回答：

> 我这里的可进化是可控演化，不是完全自主改代码。Agent 在使用 Skill 时会记录调用，用户可以记录反馈；当反馈是稳定、可复用的任务规则时，系统通过 `skill_evolve` 把规则写回对应 `SKILL.md`。写回前会保存旧版本快照，并更新 version、last-evolved、evolution-count，同时这个工具默认需要权限确认，Plan Mode 中会被阻断。

### 问题：MCP 是怎么实现的？

可以回答：

> 项目里没有直接使用 MCP SDK，而是通过 stdio JSON-RPC 实现。每个 MCP Server 是一个子进程，客户端发送 initialize、tools/list、tools/call 请求，用递增 id 管理 pending future，后台读取 stdout 响应。发现到的 MCP 工具会被包装成 `mcp__server__tool`，再加入模型的工具列表。

## 8. 简历可量化表达

如果需要压缩到 3-4 条：

- 实现 10+ 个内置工具和完整 tool calling 执行链路，覆盖文件读写、代码搜索、Shell、Skill、子 Agent、MCP 路由等场景。
- 支持 5 种权限模式和多层安全控制，包括 Plan Mode、危险命令检测、编辑前读取、mtime 外部修改检查。
- 支持 OpenAI-compatible 和 Anthropic-compatible 两类模型协议，统一内部工具 schema 并按后端自动转换。
- 实现可进化 Agent 闭环，支持长期记忆、Skill 调用统计、用户反馈记录、版本快照、规则写回和演化权限控制。

如果不想写具体数量，可以写：

- 构建覆盖模型调用、工具执行、权限控制、长期记忆、技能复用、反馈沉淀和外部工具扩展的可进化 Coding Agent 架构。

## 9. 适合投递的岗位方向

这个项目适合包装到以下方向：

- 大模型应用开发工程师
- AI Agent 工程师
- LLM 应用工程师
- Python 后端开发工程师
- AI Infra / Tooling 工程师
- DevTools / IDE AI 插件方向
- MCP / 大模型工具生态方向

## 10. 简历放置建议

### 10.1 校招 / 实习简历

建议放在“项目经历”的第一或第二个项目。重点突出：

- 从零实现 Agent 框架。
- 可进化 Agent 闭环。
- Memory / Skills / Feedback / Snapshot 这些差异化亮点。
- 多模型兼容、工具调用和权限控制。

### 10.2 社招 / 高阶项目描述

建议减少“仿 Claude Code”表述，强调工程抽象：

- 统一工具协议层。
- 权限与执行沙箱思路。
- 长期上下文管理和反馈沉淀。
- 可插拔外部工具协议。
- 可复用任务策略、版本快照和可控自进化。

### 10.3 GitHub README / 项目主页

可以使用更产品化表达：

> Bear Code is an evolvable local coding agent that turns tool calling, long-term memory, reusable skills, feedback loops, MCP tools and safe execution workflows into a Python CLI.

## 11. 可直接复制的最终简历条目

```text
Bear Code：基于 Python 的可进化 Coding Agent 框架
技术栈：Python、AsyncIO、OpenAI SDK、Anthropic SDK、MCP、JSON-RPC、Docker

- 从零实现 Claude Code 风格可进化命令行 Agent，支持流式对话、工具调用解析、工具执行、结果回传、多轮推理、会话恢复和上下文压缩。
- 设计“Memory + Skills + Feedback + Snapshot”演化闭环，支持长期记忆召回、Skill 自动触发、用户反馈记录、版本快照、规则写回和演化权限控制。
- 构建统一工具调用系统，支持文件读写、精确编辑、代码搜索、Shell 执行、Skill 调用、Skill 演化、子 Agent 调度，并适配 OpenAI / Anthropic 两类工具协议。
- 实现权限与安全控制，包括 Plan Mode、危险命令检测、编辑前读取、mtime 外部修改检查和多种 permission mode，降低 Agent 误操作和无约束演化风险。
- 自研 MCP stdio JSON-RPC 客户端，支持动态启动外部 MCP Server、发现工具、封装 schema，并将外部工具接入模型调用链路。
```

## 12. 不建议夸大的点

为了简历可信，不建议写：

- “完全自主进化”。
- “生产级替代 Claude Code”。
- “支持所有 MCP 协议细节”。
- “拥有 IDE 级完整代码理解能力”。
- “实现通用智能体平台”。

更稳妥的表述：

- “可控自进化”。
- “可进化 Coding Agent 框架”。
- “MCP stdio JSON-RPC 基础客户端”。
- “面向软件工程任务的本地 Agent 实验项目”。
