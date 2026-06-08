# Claude Code Agent 机制梳理

> 本文不结合当前项目实现，只从 Claude Code 官方机制出发，按 agent 架构视角梳理。资料基于 2026-06-08 可访问的 Anthropic/Claude Code 官方文档。

## 1. 总体定位

Claude Code 不是一个只会补全当前文件的 IDE 插件，而是一个运行在终端、IDE、桌面端、Web、CI/CD 等环境里的 agentic coding tool。

它的核心不是“模型直接回答”，而是一个 agentic harness：

```text
用户目标
  -> 模型推理
  -> 工具调用
  -> 读取反馈
  -> 再推理
  -> 再行动
  -> 验证结果
  -> 直到任务完成或需要用户介入
```

Claude Code 官方把这个循环概括为三类阶段：

- **gather context**：搜索文件、读取代码、理解错误输出、查看项目状态。
- **take action**：编辑文件、创建文件、运行命令、调用外部工具。
- **verify results**：运行测试、检查命令输出、读取变更、必要时继续修复。

这三个阶段不是严格线性的。一次 bug fix 可能反复经历“读日志 -> 找代码 -> 改代码 -> 跑测试 -> 再读失败输出 -> 再改”的循环；一次代码库问答可能只需要 context gathering。

从 agent 设计角度看，Claude Code 的关键能力来自四层：

| 层级 | 作用 |
| --- | --- |
| 模型层 | 负责推理、规划、选择下一步动作 |
| 工具层 | 让模型能读文件、改文件、跑命令、调用外部系统 |
| 上下文管理层 | 控制哪些信息进入 context window，何时压缩、何时隔离 |
| 扩展/治理层 | 通过 memory、skills、subagents、hooks、MCP、permissions 让 agent 可配置、可复用、可约束 |

## 2. Agent Loop：Claude Code 怎么“行动”

Claude Code 的单个主 agent 可以理解为一个 ReAct 风格的循环，但它被工程化成了更完整的执行环境。

典型流程如下：

```text
1. 用户提出任务
2. Claude 读取已加载上下文：系统提示、会话历史、CLAUDE.md、auto memory、技能描述、工具描述等
3. Claude 选择下一步：回答、读取文件、搜索、编辑、运行命令、调用 subagent、询问用户
4. Claude Code 执行工具调用
5. 工具结果回填上下文
6. Claude 基于新信息继续推理
7. 循环直到完成、失败、等待权限或等待用户输入
```

内置工具大致包括：

- 文件操作：Read、Edit、Write、Glob、Grep 等。
- Shell 操作：运行测试、构建、git 命令、诊断命令。
- 编排工具：调用 subagent、询问用户、进入/退出 plan mode。
- 扩展工具：MCP server 暴露的外部工具、Skill tool 等。

这里的重点是：工具调用结果会成为下一轮推理的输入。Claude Code 的 agent 能力不是一次性 prompt，而是“推理 + 执行 + 观察 + 修正”的闭环。

## 3. Context Engineering：上下文工程

Claude Code 的 context engineering 目标是：在有限 context window 内，让模型看到足够完成任务的信息，同时避免被无关内容、长日志、重复指令拖垮。

### 3.1 Context Window 里有什么

一个 Claude Code session 的上下文通常包含：

- 当前对话历史。
- 用户输入和助手回复。
- 文件内容和命令输出。
- 系统指令和环境信息。
- `CLAUDE.md`、`CLAUDE.local.md`、`.claude/rules/`。
- auto memory 的索引内容。
- 已加载 skill 的内容。
- 工具描述、MCP 工具信息。
- subagent 返回的摘要。

Claude Code 不是一开始就把整个代码库塞进上下文，而是让模型通过工具逐步读取。这样做的好处是上下文和任务相关，但代价是 agent 需要多步探索。

### 3.2 自动压缩和 `/compact`

当上下文接近上限时，Claude Code 会自动管理：

- 先清理较旧的工具输出。
- 必要时总结早期对话。
- 尽量保留用户请求、关键代码片段、近期任务状态。
- 如果某个大文件或大输出导致反复压缩后马上又填满，会停止自动压缩并报错，避免无限循环。

用户也可以通过 `/compact` 主动压缩，并带上聚焦指令，例如让压缩重点保留某个 API 变更。

重要设计点：

- 早期对话里的临时指令可能在压缩后弱化或丢失。
- 应该长期保留的规则要放进 `CLAUDE.md` 或 rule/skill，而不是只在聊天里说一次。
- skill 内容在被调用后会进入会话上下文，压缩时也会按预算保留最近调用的 skill。

### 3.3 Lazy Loading

Claude Code 很多扩展都采用“描述先加载，正文按需加载”的策略。

典型例子：

- **Skills**：session 启动时主要加载 skill 描述，完整 `SKILL.md` 只在 skill 被调用时进入上下文。
- **MCP tools**：大规模工具集可以通过 tool search 延迟加载，避免所有工具定义一次性占满上下文。
- **Path-specific rules**：`.claude/rules/` 可以按路径匹配，只有处理相关文件时才加载。
- **Nested CLAUDE.md**：子目录下的 `CLAUDE.md` 不一定启动时全量加载，而是在读取对应目录文件时加载。

这是一种很重要的 context engineering 思路：让 agent 先知道“有什么能力/规则可能存在”，等任务触发时再加载细节。

### 3.4 Context 隔离

Claude Code 不只靠压缩来节省上下文，还用隔离：

- subagent 有自己的独立 context window。
- forked skill 可以在单独 subagent context 中执行。
- 多个 Claude Code session 彼此独立。
- git worktree 可以让并行 session 在文件系统上隔离。

隔离的收益是：主对话不会被大量搜索结果、日志和中间推理污染。subagent 完成后只返回摘要，主 agent 用摘要继续决策。

## 4. Memory：Claude Code 怎么“记住”

Claude Code 的 memory 分两类：人为写的持久指令，以及 Claude 自动沉淀的项目记忆。

### 4.1 `CLAUDE.md`

`CLAUDE.md` 是用户/团队显式写给 Claude 的持久上下文。它适合放：

- 项目架构概览。
- 构建、测试、运行命令。
- 代码风格和命名约定。
- 团队开发规范。
- 安全、合规、提交规范。
- “每次都应该知道”的事实。

不同位置对应不同作用域：

| 位置 | 作用域 |
| --- | --- |
| 组织级 managed `CLAUDE.md` | 全组织、由管理员下发 |
| `~/.claude/CLAUDE.md` | 当前用户的所有项目 |
| `./CLAUDE.md` 或 `./.claude/CLAUDE.md` | 当前项目，适合提交到版本库 |
| `./CLAUDE.local.md` | 当前项目的个人私有偏好，通常 gitignore |

加载方式大致是从当前工作目录向上查找，并按更广到更具体的顺序拼接进上下文。子目录里的指令可以在读取相关文件时再加载。

需要注意：

- `CLAUDE.md` 是上下文，不是硬性策略。模型会尽量遵守，但不能保证强制执行。
- 真正需要强制阻断的规则应该用 permissions 或 PreToolUse hook。
- 官方建议保持简洁，过长会消耗 context，也会降低遵循效果。

### 4.2 `.claude/rules/`

当 `CLAUDE.md` 变得太大时，可以把规则拆到 `.claude/rules/`。

它的价值是：

- 让规则模块化，便于维护。
- 可以按路径/文件类型作用域加载。
- 适合 monorepo 或大型代码库中不同子系统的差异化规则。

从 context engineering 角度看，rules 是“比全局 `CLAUDE.md` 更细粒度的上下文注入”。

### 4.3 Auto Memory

Auto memory 是 Claude 自动写给自己的项目记忆。它会记录未来可能有用的信息，例如：

- 构建/测试经验。
- 调试发现。
- 架构习惯。
- 代码风格偏好。
- 用户反复纠正过的行为。

官方描述的存储位置是：

```text
~/.claude/projects/<project>/memory/
├── MEMORY.md
├── debugging.md
├── api-conventions.md
└── ...
```

其中 `MEMORY.md` 是索引，Claude 会在每个 session 启动时读取其前 200 行或 25KB，以较小成本知道记忆目录里有什么。更详细的 memory 文件可以在会话中按需读取和更新。

Auto memory 的几个特点：

- 默认开启，可通过 `/memory` 或配置关闭。
- 是本机本地的，不自动跨机器或云环境同步。
- project 维度通常基于 git repository，因此同一 repo 的 worktree/subdirectory 共享记忆。
- 记忆文件是 Markdown，可以人工审计、编辑、删除。
- 用户说“remember ...”时，Claude 会把信息写入 auto memory；如果想写入 `CLAUDE.md`，要明确要求。

### 4.4 Memory 的本质

Claude Code 的 memory 不是“无限聊天历史回放”，而是把长期有价值的信息转成持久上下文入口。

它大致分工如下：

| 机制 | 适合保存 | 不适合保存 |
| --- | --- | --- |
| `CLAUDE.md` | 每次都应遵守的稳定规则和事实 | 临时探索结果、大段流程文档 |
| `.claude/rules/` | 特定路径/技术栈的规则 | 全局必须知道的核心指令 |
| auto memory | Claude 从工作中总结出的可复用经验 | 需要团队强一致执行的硬规则 |
| skills | 多步骤流程、可复用工作法、长参考材料 | 简短项目事实 |

## 5. 单 Agent 与多 Agent

Claude Code 默认是一个主 agent 在当前 session 中工作。但它提供多种“多 agent”形态，不同形态解决的问题不同。

### 5.1 单 Agent

单 agent 适合：

- 小范围代码修改。
- 问答和解释。
- 连续上下文很重要的任务。
- 不需要大量并行探索的工作。

优点是上下文连续、状态简单、沟通成本低。缺点是长任务会积累大量上下文，搜索和日志容易污染主对话。

### 5.2 Subagents

Subagent 是 Claude Code 内部最核心的 agent 分工机制。

官方定义里，每个 subagent 都有：

- 独立 context window。
- 自己的 system prompt。
- 可配置工具权限。
- 可配置模型。
- 可配置 permission mode。
- 可配置 hooks、MCP servers、skills。
- 可选 persistent memory。

主 agent 在遇到匹配任务时把工作委托给 subagent；subagent 独立执行后返回结果摘要。

内置 subagent 包括：

| Subagent | 典型用途 |
| --- | --- |
| Explore | 只读探索代码库，避免搜索结果进入主上下文 |
| Plan | plan mode 中的只读研究 |
| general-purpose | 复杂、多步骤、可能需要读写的通用任务 |

自定义 subagent 用 Markdown + YAML frontmatter 定义，例如：

```markdown
---
name: code-reviewer
description: Reviews code for quality and best practices
tools: Read, Glob, Grep
model: sonnet
---

You are a focused code reviewer. Find correctness risks, regressions, and missing tests.
```

Subagent 的关键价值：

- **保上下文**：把大规模探索、日志读取、调研留在子上下文。
- **控能力**：给某些 agent 只读工具，或限制 MCP server。
- **控成本**：简单任务可以路由到更便宜/更快模型。
- **复用角色**：把 reviewer、debugger、researcher 等角色固化。
- **持久积累**：特定 subagent 可以有自己的 memory 目录。

限制也很明确：

- subagent 工作在单个 session 内；它不是天然的长期后台服务。
- subagent 默认返回摘要，不会把所有内部细节带回主上下文。
- subagent 不能无限嵌套；官方文档提到 subagents 不能再 spawn subagents。

### 5.3 多 Session / Parallel Agents

除了 subagents，Claude Code 还支持多 session 形态：

- 多个终端 session。
- git worktrees 上的并行 session。
- Desktop/Agent View 管理多个 session。
- background agents。
- agent teams。

这类机制适合真正独立的任务，例如：

- 同时修多个 issue。
- 多个候选方案并行探索。
- 不同分支上并行实现。
- 一个 agent 做实现，另一个做审查。

和 subagent 的区别：

| 形态 | 上下文关系 | 文件系统关系 | 适合 |
| --- | --- | --- | --- |
| Subagent | 主 session 内部委托，独立 context，返回摘要 | 通常共享当前工作目录，可配置 worktree isolation | 局部探索、角色化任务、节省主上下文 |
| 多 session | session 彼此独立 | 通常建议用不同 worktree 隔离 | 多个独立任务并行推进 |
| Agent teams | 多 session 可协作通信 | 需要更明确的任务分配和协调 | 团队式协作、复杂并行工作流 |

### 5.4 Agent Teams

Agent teams 是更高级的多 agent 协作。它关注的是“多个 Claude Code session 如何像团队一样协作”。

常见思路包括：

- 一个 lead/coordinator 分配任务。
- 多个 teammate 负责不同子任务。
- 使用共享任务、消息、状态来协调。
- 可以复用 subagent definitions 作为 teammate 类型。

从架构角度看，subagent 更像“主 agent 的临时专家工具”，agent teams 更像“多个 agent 实例组成的协作系统”。

## 6. Skills：可复用能力与流程

Skills 是 Claude Code 的一等扩展机制。它们把一段专门能力、流程、参考资料或命令封装成 `SKILL.md`。

### 6.1 Skill 解决什么问题

当你反复给 Claude 粘贴同一段说明时，就适合做成 skill：

- 代码审查 checklist。
- 发布流程。
- PR 总结格式。
- 某个框架的迁移步骤。
- 项目运行和验证方法。
- 复杂 API 或领域知识参考。

Skill 和 `CLAUDE.md` 的区别：

| 机制 | 加载方式 | 适合 |
| --- | --- | --- |
| `CLAUDE.md` | session 启动时加载 | 每次都需要的稳定事实和规则 |
| Skill | 描述常驻，正文按需加载 | 多步骤流程、长参考资料、特定任务 |

因此 skill 是一种更经济的上下文组织方式：让模型知道“有这个能力”，但不在每个 session 启动时塞入完整说明。

### 6.2 Skill 结构

一个 skill 是目录加 `SKILL.md`：

```text
my-skill/
├── SKILL.md
├── references/
├── scripts/
└── templates/
```

`SKILL.md` 包含 YAML frontmatter 和正文：

```markdown
---
name: summarize-changes
description: Summarize uncommitted git changes and flag risky edits
allowed-tools: Bash(git diff *) Bash(git status *)
---

Summarize the current change set. Focus on behavior changes, risks, and missing tests.
```

常见 frontmatter：

| 字段 | 作用 |
| --- | --- |
| `description` | 让 Claude 判断什么时候调用 |
| `when_to_use` | 更详细的触发条件 |
| `disable-model-invocation` | 禁止 Claude 自动调用，只能用户手动调用 |
| `user-invocable` | 是否显示给用户作为 slash command |
| `allowed-tools` | skill 激活时预批准的工具 |
| `disallowed-tools` | skill 激活时禁用的工具 |
| `model` / `effort` | skill 激活时切换模型或推理强度 |
| `context: fork` | 在隔离 subagent context 中运行 |
| `agent` | fork 时指定使用哪个 subagent |
| `paths` | 限制只在相关路径下自动触发 |

### 6.3 Skill 的加载生命周期

默认情况下：

- skill 描述会进入上下文，让 Claude 知道可用技能。
- 完整 `SKILL.md` 只有在用户或 Claude 调用 skill 时才加载。
- 加载后的 skill 内容会作为一条消息留在会话中。
- 自动压缩后，最近调用的 skill 会在预算内被重新附加。

如果设置：

```yaml
disable-model-invocation: true
```

则 Claude 不会自动调用该 skill，它也不会把描述放入模型上下文。适合部署、提交、发消息这类用户必须明确触发的动作。

### 6.4 Skill 与 Subagent 的组合

Claude Code 里 skill 和 subagent 可以双向组合：

- **skill 使用 subagent**：`context: fork`，把 skill 内容交给某个 subagent 在隔离上下文中执行。
- **subagent 预加载 skill**：subagent frontmatter 里配置 `skills`，启动时把完整 skill 注入子 agent 上下文。

这让复杂流程可以被拆成：

```text
主 agent
  -> 调用 skill
  -> skill fork 到 Explore subagent
  -> subagent 做只读调研
  -> 返回摘要
  -> 主 agent 继续决策
```

## 7. Hooks：确定性控制点

Hooks 是 Claude Code 的确定性扩展点。和 `CLAUDE.md`、skills 这类“给模型看的上下文”不同，hooks 是客户端在特定事件发生时执行的命令或逻辑。

它适合：

- 在工具调用前拦截危险命令。
- 在文件编辑后自动格式化。
- 在任务结束后发送通知。
- 在加载指令时记录实际加载了哪些文件。
- 对 MCP 工具或 Bash 命令做额外校验。

典型事件包括：

- `PreToolUse`
- `PostToolUse`
- `UserPromptSubmit`
- `Stop`
- `SubagentStart`
- `InstructionsLoaded`

从 agent 设计角度看：

- `CLAUDE.md` / skills 是“影响模型怎么想”。
- permissions / hooks 是“限制系统实际能做什么”。

这一区分很重要。安全、合规、权限类要求不应该只写进 prompt。

## 8. MCP：外部工具生态

MCP（Model Context Protocol）让 Claude Code 连接外部工具和数据源，例如：

- GitHub/GitLab。
- 数据库。
- 文档系统。
- 浏览器自动化。
- 内部业务 API。
- 监控/CI 系统。

MCP server 暴露工具给 Claude Code，Claude 可以像调用内置工具一样调用它们。

context engineering 上，MCP 的挑战是工具描述可能很多。Claude Code 支持延迟加载和 tool search，让模型先看到工具名称或概要，真正需要时再加载具体工具定义。

MCP 也可以 scoped 到 subagent。这样外部工具不必暴露给主 session，减少上下文成本和权限面。

## 9. Permissions 与安全边界

Claude Code 的 agent 能行动，所以必须有权限系统。

典型控制包括：

- 对 Bash 命令是否需要用户确认。
- 是否允许写文件。
- 是否允许修改敏感目录。
- 是否允许某些 MCP tool。
- 是否允许某些 Skill。
- 是否允许 spawn 某些 subagent。

常见 permission mode 包括：

- `default`：标准权限检查。
- `acceptEdits`：自动接受文件编辑。
- `auto`：用分类器判断命令和写入是否可信。
- `dontAsk`：自动拒绝需要询问的权限。
- `bypassPermissions`：跳过大部分权限提示，风险较高。
- `plan`：只分析和计划，不直接编辑。

核心原则：

- 用 prompt 指导行为。
- 用 permissions 和 hooks 强制边界。
- 对有副作用的 skill 设置 `disable-model-invocation: true`。
- 对 subagent 使用最小工具权限。

## 10. 插件化：把 Skills、Agents、Hooks、MCP 打包

Claude Code 还支持 plugins。插件可以把多个扩展组合起来：

- skills
- subagents
- hooks
- MCP servers
- output styles

从产品化角度看，plugin 是“分发一套 agent 能力包”的方式。团队可以把特定工作流、专用 agent、工具连接和权限辅助逻辑组合成插件，而不是让每个项目手工配置。

## 11. Claude Code Agent 架构总结

可以把 Claude Code 的 agent 架构抽象成下面这张图：

```text
                         用户目标
                            |
                            v
                    主 Claude Code Agent
                            |
        +-------------------+-------------------+
        |                   |                   |
   Context Layer        Tool Layer        Governance Layer
        |                   |                   |
 CLAUDE.md/rules       Read/Edit/Bash       permissions
 auto memory           MCP tools            hooks
 skills metadata       Skill tool           checkpoints
 compact summary       Agent tool
        |
        v
   按需加载上下文
        |
        v
   模型选择下一步行动
        |
        v
   工具执行并回填观察结果
        |
        v
   验证、修正、继续循环

额外分支：

主 Agent
  -> Subagent 独立 context
       -> 工具执行
       -> 返回摘要

多个 Session
  -> worktree/agent view/agent teams
       -> 并行任务
       -> 协调结果
```

如果用一句话概括：

> Claude Code 做 agent 的核心，是把大模型放进一个可读写项目、可调用工具、可管理上下文、可持久记忆、可委托子 agent、可被 hooks/permissions 约束的工程执行闭环里。

## 12. 对自研 Agent 的启发

如果要借鉴 Claude Code 的设计，可以按优先级拆成几类能力。

### 12.1 最小可用 Agent

- 主循环：think -> tool call -> observe -> continue。
- 基础工具：读文件、搜索、编辑、运行命令。
- 权限提示：至少对 shell 和写文件做确认。
- 简单上下文管理：记录会话、截断长输出、避免重复注入。

### 12.2 上下文工程

- 不要全量塞代码库，使用按需读取。
- 对大输出做截断、摘要、结构化。
- 把稳定指令和临时对话分开。
- 支持显式 compact。
- 给工具和扩展做 lazy loading。

### 12.3 Memory

- 人写 memory：类似 `CLAUDE.md`，保存稳定规则。
- 自动 memory：保存长期有用的经验，而不是聊天历史。
- memory 要可审计、可编辑、可删除。
- memory 要有索引，避免每次加载所有细节。

### 12.4 Skills

- 把重复 prompt 做成技能。
- 技能描述常驻，正文按需加载。
- 长参考资料放 supporting files。
- 有副作用的技能只能手动触发。

### 12.5 Subagents

- 给探索、审查、调试、计划等角色单独 context。
- 只把摘要带回主 agent。
- 给 subagent 配最小工具权限。
- 简单任务可以用便宜模型，复杂任务用强模型。

### 12.6 Governance

- prompt 只负责指导。
- hooks/permissions 负责强制。
- 重要边界不要依赖模型“自觉遵守”。
- 所有自动写入、自动运行、外部 API 调用都要有可审计记录。

## 13. 参考资料

- Claude Code Overview: https://code.claude.com/docs/en/overview.md
- How Claude Code works: https://code.claude.com/docs/en/how-claude-code-works.md
- Explore the context window: https://code.claude.com/docs/en/context-window.md
- How Claude remembers your project: https://code.claude.com/docs/en/memory.md
- Create custom subagents: https://code.claude.com/docs/en/sub-agents.md
- Extend Claude with skills: https://code.claude.com/docs/en/skills.md
- Extend Claude Code overview: https://code.claude.com/docs/en/features-overview.md
- Run agents in parallel: https://code.claude.com/docs/en/agents.md
- Orchestrate teams of Claude Code sessions: https://code.claude.com/docs/en/agent-teams.md
- Hooks reference: https://code.claude.com/docs/en/hooks.md
- Connect Claude Code to tools via MCP: https://code.claude.com/docs/en/mcp.md
- Configure permissions: https://code.claude.com/docs/en/permissions.md
