# Skills 自进化逻辑与实现思路

本文档梳理 Bear Code 当前项目中 Skills 自进化的完整闭环：Agent 如何发现、检索、调用 Skill，如何从对话反馈中抽取可复用经验，并通过 add / merge / discard、版本快照、provenance 和使用统计把经验沉淀为可治理的 `SKILL.md`。

## 1. 核心目标

Skills 自进化不是让 Agent 随机改自己的系统提示词，而是把对话中稳定、可复用、未来同类任务仍然适用的用户偏好和工作流沉淀为独立 Skill。

它解决的问题是：

- 普通 Agent 的经验停留在当前上下文里，换一轮对话后容易丢失。
- 用户反复强调的输出风格、审查规则、写作规范、工程流程可以变成长期能力。
- 新增和演化都需要可审计、可回溯、可归档，避免能力污染。
- Skill 应该记“方法”，Memory 更适合记“事实”，两者职责分离。

当前实现的原则：

- 只沉淀用户明确表达或多轮反馈中可确认的稳定规则。
- 不沉淀一次性任务 payload、密钥、账号、URL、精确日期、临时项目事实。
- 优先合并已有 Skill，避免同类 Skill 泛滥。
- 所有写入都受权限模式约束，并保留 provenance。

## 2. 总体链路

![Skills 自进化总体链路](assets/architecture/07-skills-evolution-flow.svg)

这条链路的核心思路是：不要让 Agent 在完成任务时立即、主观地修改自己的能力库，而是把“任务执行”和“经验沉淀”拆成两条相互关联但职责独立的链路。主链路负责完成当前用户任务；沉淀链路在当前轮结束后异步观察用户反馈，再判断是否把稳定经验写入 Skill。

### 2.1 为什么要拆成四段

整体实现被拆成四段：

1. 在线使用链路：负责在当前任务中找到可能有用的 Skill，并把候选 Skill 注入上下文。
2. 在线沉淀决策链路：负责从对话和下一轮用户反馈中识别可复用经验。
3. 审计与治理产物：负责把每次新增、合并、丢弃和失败都记录下来。
4. 后续复用和质量反馈：负责让新 Skill 在后续请求中被检索，并持续统计是否真的有用。

这样拆分的原因是，Skill 自进化最容易出现两个问题：一是把一次性任务内容误写成长期规则，二是重复创建很多相似 Skill。当前实现通过 pending window、Extractor、Maintainer、provenance 和 usage stats 这几层机制，把“能不能沉淀”“沉淀到哪里”“沉淀后是否有用”分开判断。

### 2.2 第一段：当前请求先完成任务，再记录上下文

用户输入进入 Agent 后，不会直接触发 Skill 写入，而是先走正常任务执行链路：

```text
user_message
  -> retrieve_relevant_skills()
  -> format_retrieved_skill_context()
  -> Agent 正常回答或调用 skill 工具
  -> 保存 pending extraction window
```

这里有两个关键设计。

第一，Skill 检索只负责“召回候选”，不强制使用。`retrieve_relevant_skills()` 会基于用户输入匹配已有 Skill 的 `name`、`description`、`when-to-use` 和部分正文，取最多 3 个候选，再通过 `<retrieved_skills>` 注入到当前用户消息末尾。模型仍需要根据用户意图和 `when-to-use` 自己判断是否调用 `skill` 工具。

第二，当前轮结束后只保存 pending window，不立刻写 Skill。pending window 保存最近对话、当前用户输入、当前 assistant 回复、当时检索到的 top Skill 引用等信息。它相当于一个“待观察样本”，等待下一轮用户输入来判断上一轮表现是否值得沉淀。

### 2.3 第二段：用下一轮用户反馈作为沉淀证据

下一轮用户输入到来时，系统会先把它合并到上一轮 pending window 中：

```text
pending window + next_user_feedback
  -> ready_skill_extraction_window
  -> _run_online_skill_evolution()
  -> online_ingest()
```

这个设计的重点是“下一轮反馈优先”。例如用户说：

```text
以后这类报告都要更书面化，并结合国家政策。
```

这类话通常不是当前任务 payload，而是对上一轮输出的稳定偏好或修正。相比让 assistant 从自己的回答中猜测“我刚刚可能学到了什么”，用户下一轮反馈更可靠，也更适合作为 Skill 自进化证据。

沉淀入口 `online_ingest()` 做两件事：

- 调用 Extractor，从对话窗口中抽取最多一个候选 Skill。
- 调用 Maintainer，判断这个候选应该新增、合并还是丢弃。

Extractor 关注“有没有可复用经验”，Maintainer 关注“这条经验应该如何维护到 Skill 集合里”。这两个角色拆开后，模型不会一边抽取一边直接写文件，决策边界更清晰。

### 2.4 第三段：Extractor 只产出候选，不负责写入

Extractor 的输入是压缩后的对话窗口、可选 hint、以及上一轮检索到的 Skill 引用。它输出的不是最终文件，而是一个候选结构：

```json
{
  "name": "候选 Skill 名",
  "description": "能力描述",
  "when_to_use": "触发条件",
  "instructions": "可复用执行规则",
  "evidence": "来自用户反馈的证据",
  "tags": []
}
```

这里的实现约束很重要：

- 用户消息是主要证据，assistant 消息只作为上下文。
- 只抽取未来同类任务仍然适用的方法、流程、风格或约束。
- 不抽取一次性内容、隐私信息、临时事实、URL、账号、密钥、精确日期。
- 证据弱或价值低时返回空候选。

因此 Extractor 只是“提出一个可能值得沉淀的经验”，它本身不会创建或修改 `SKILL.md`。

### 2.5 第四段：Maintainer 统一处理 add / merge / discard

Maintainer 会把候选和已有 Skill 集合放在一起比较：

```text
candidate
  -> exact identity match
  -> retrieve_relevant_skills(limit=8, min_score=0.03)
  -> LLM 判断 add / merge / discard
  -> 规则兜底修正
```

它有三个可能结果：

| 结果 | 触发场景 | 后续动作 |
|------|----------|----------|
| `add` | 没有合适的已有 Skill，候选是独立可复用能力 | 调用 `create_skill_file()` 新建 `SKILL.md` |
| `merge` | 已有 Skill 能承载这条经验 | 调用 `evolve_skill_file()` 演化已有 `SKILL.md` |
| `discard` | 候选重复、低价值、证据不足或不应沉淀 | 不写 Skill，只记录 provenance |

这里的关键取舍是“优先 merge，谨慎 add”。系统会先做 exact identity match，再做相似 Skill 检索。如果候选和已有 Skill 很接近，即使模型初判为 add，也会被规则兜底改成 merge，避免 Skill 数量失控。

### 2.6 写入统一收敛到 skill_evolution.py

无论是手动 `/skill-create`、`/skill-evolve`，还是后台在线沉淀，最终都会收敛到 `agents/skill_evolution.py` 里的文件操作函数。

新增 Skill 时：

```text
create_skill_file()
  -> 检查同名 Skill
  -> 生成安全目录名
  -> 写入 .bear/skills/<slug>/SKILL.md
  -> version=0.1.0
  -> usage.jsonl 记录 create
```

演化 Skill 时：

```text
evolve_skill_file()
  -> 定位已有 SKILL.md
  -> 写入演化前完整快照 history/<skill>.jsonl
  -> bump patch version
  -> 更新 last-evolved / evolution-count
  -> 写回合并后的正文
  -> usage.jsonl 记录 evolve
```

这种收敛方式保证了版本号、快照、审计日志和缓存刷新逻辑不会散落在多个入口里。

### 2.7 Provenance 和 usage stats 让自进化可治理

每次在线沉淀判断都会记录 provenance，即使结果是 `none` 或 `discard` 也会记录。这一点很重要，因为自进化系统不仅要知道“创建了什么”，也要知道“为什么没有创建”。

主要产物包括：

```text
.bear/skill-evolution/online_provenance.jsonl
.bear/skill-evolution/online_skill_provenance.json
.bear/skill-evolution/usage.jsonl
.bear/skill-evolution/skill_usage_stats.json
.bear/skill-evolution/history/<skill_slug>.jsonl
```

其中 provenance 解决“来源可追溯”，history 解决“演化可回看”，usage stats 解决“效果可观察”。如果某个 Skill 长期被检索出来但没有被实际使用，系统会把它视为 stale candidate，并在满足阈值和权限条件时归档到 `pruned/`。

### 2.8 这条链路的实现取舍

当前实现不是一个复杂的训练系统，而是一个轻量、可审计的在线知识沉淀系统。它的关键取舍是：

- 用 `SKILL.md` 作为能力载体，便于人工阅读、编辑、版本管理。
- 用 BM25-lite 检索降低复杂度，避免引入向量库作为强依赖。
- 用下一轮用户反馈增强证据质量，减少 assistant 自我幻觉式沉淀。
- 用 Extractor / Maintainer 双阶段拆分，降低“抽取即写入”的风险。
- 用 add / merge / discard 控制 Skill 集合规模。
- 用 provenance、history、usage stats 保证自进化过程可回溯、可解释、可治理。

简化来看，这条链路的目标不是让 Agent 自动变“聪明”，而是让它把用户明确认可、反复出现、未来仍有价值的方法沉淀为可复用 Skill，并且每一次沉淀都能查清楚来源、版本和效果。

## 3. 关键模块分工

| 模块 | 职责 |
|------|------|
| `agents/agent.py` | 对话生命周期、Skill 检索注入、pending window、后台沉淀任务、usage tracking |
| `agents/skills.py` | Skill 加载、缓存、BM25-lite 检索、调用、创建和演化封装 |
| `agents/online_skill_evolution.py` | 在线抽取候选 Skill，并决策 add / merge / discard |
| `agents/skill_evolution.py` | `SKILL.md` 落盘、版本快照、provenance、usage stats、stale 归档 |
| `agents/tools.py` | 暴露 `skill`、`skill_create`、`skill_evolve` 工具，并接入权限控制 |

## 4. Skill 载体与加载规则

Skill 的物理载体是目录中的 `SKILL.md`：

```text
~/.bear/skills/<skill_name>/SKILL.md
<project>/.bear/skills/<skill_name>/SKILL.md
```

加载入口是 `agents/skills.py::discover_skills()`。

加载顺序：

1. 先加载用户级 `~/.bear/skills`。
2. 再加载项目级 `<cwd>/.bear/skills`。
3. 同名 Skill 下，用户级优先，项目级不覆盖用户级。

`SKILL.md` 由 frontmatter 和 Markdown 正文组成。当前会解析的关键字段包括：

| 字段 | 作用 |
|------|------|
| `name` | Skill 的注册名，未配置时使用目录名 |
| `description` | 简短能力描述，用于展示和检索 |
| `when-to-use` / `when_to_use` | 自动触发判断条件 |
| `user-invocable` | 是否允许用户通过 `/<skill>` 手动调用 |
| `context` | `inline` 或 `fork` |
| `allowed-tools` | fork 模式下限制子 Agent 可用工具 |

正文支持两个运行时占位符：

```text
$ARGUMENTS / ${ARGUMENTS}
${CLAUDE_SKILL_DIR}
```

前者用于注入用户调用参数，后者用于引用 Skill 自身目录下的 references、scripts 或资源文件。

## 5. 对话前：检索并注入候选 Skills

每轮用户输入进入主 Agent 时，会先检索相关 Skill：

```text
agents/agent.py::_augment_user_message_with_skill_context()
  -> agents/skills.py::format_retrieved_skill_context()
  -> agents/skills.py::retrieve_relevant_skills()
```

检索逻辑是轻量 BM25：

- query 来自当前用户消息。
- Skill 文档由 `name`、`description`、`when-to-use` 和正文前 2500 字符组成。
- metadata 权重更高，正文也参与匹配。
- 中英文都做基础 token 化，中文会补充相邻双字 token。
- 默认返回最多 3 个候选。

注入到用户消息尾部的格式类似：

```text
<retrieved_skills>
These skills were retrieved for the current user request...
1. skill_name (score=0.xxx, source=project): description
   When to use: ...
</retrieved_skills>
```

这里的 Skill 只是候选，模型仍要根据用户真实意图和 `when-to-use` 判断是否调用 `skill` 工具。注入块后续会通过 `_strip_runtime_injections()` 从历史消息中剥离，避免运行时检索信息污染长期对话窗口。

## 6. 对话中：Skill 调用与执行模式

Skill 可以通过两种方式触发：

- 模型调用 `skill` 工具。
- 用户在 REPL 中输入 `/<skill-name> [args]` 手动调用 user-invocable Skill。

执行入口：

```text
agents/agent.py::_execute_skill_tool()
agents/skills.py::execute_skill()
agents/skills.py::resolve_skill_prompt()
```

调用链路：

```text
skill tool call
  -> get_skill_by_name()
  -> record_skill_invocation()
  -> resolve_skill_prompt()
  -> inline 或 fork 执行
```

`inline` 模式会把解析后的 Skill prompt 返回给当前对话，让主 Agent 继续执行。

`fork` 模式会创建一个子 Agent，以 Skill prompt 作为子 Agent 的 system prompt 独立完成任务。若配置了 `allowed-tools`，子 Agent 只能使用指定工具；否则默认排除再次创建 agent 的能力，降低递归风险。

每次调用都会写入：

```text
.bear/skill-evolution/usage.jsonl
```

事件类型为 `invoke`，包括 skill 名、来源、context 和参数预览。

## 7. 对话后：pending window 捕获下一轮反馈

在线沉淀没有在当前回复结束后立即写 Skill，而是先保存一个 pending window，再等待下一轮用户输入作为反馈证据。

相关入口：

```text
agents/agent.py::_set_pending_skill_extraction_window()
agents/agent.py::_pop_pending_skill_extraction_window()
```

当前轮回答后保存：

```text
{
  "messages": "最近最多 8 条 user/assistant 对话",
  "latest_user": "当前轮原始用户输入",
  "latest_assistant": "当前轮 assistant 输出",
  "retrieved_reference": "本轮检索到的 top skill 引用",
  "session_id": "当前会话 ID"
}
```

下一轮用户输入到来时：

```text
pending window + next_user_feedback
  -> ready_skill_extraction_window
  -> 后台调度 _run_online_skill_evolution()
```

这样设计的价值是：用户下一轮经常会给出纠正或偏好，例如“以后这类报告要更书面化”“不要先问太多，先给初稿”“review 时必须检查调用方参数”。这些反馈比 assistant 自己从当前回复里猜测更可靠。

## 8. 在线沉淀入口：online_ingest

统一入口是：

```text
agents/online_skill_evolution.py::online_ingest()
```

核心流程：

```text
messages + retrieved_reference + hint
  -> extract_online_skill_candidate()
  -> 无候选：action=none
  -> 有候选：maintain_online_skill_candidate()
  -> record_online_provenance()
```

`online_ingest()` 不管结果如何都会记录 provenance。常见 action 包括：

| action | 含义 |
|--------|------|
| `none` | 没有抽取到值得沉淀的候选 |
| `discard` | 有候选，但重复、低价值或不应沉淀 |
| `add` | 创建新 Skill |
| `merge` | 合并进已有 Skill |
| `failed` | 链路异常 |
| `add_denied` / `merge_denied` | 权限拒绝写入 |

## 9. Extractor：抽取候选 Skill

入口：

```text
agents/online_skill_evolution.py::extract_online_skill_candidate()
```

Extractor 的目标是从 live conversation window 中抽取最多一个候选 Skill。返回 JSON 结构：

```json
{
  "skills": [
    {
      "name": "...",
      "description": "...",
      "when_to_use": "...",
      "instructions": "...",
      "evidence": "...",
      "tags": []
    }
  ]
}
```

抽取约束写在 Extractor system prompt 中，核心规则是：

- 用户消息是主要证据，assistant 消息只作为上下文。
- 下一轮用户反馈可以确认、否定或修正上一轮行为。
- 不抽取 assistant-only guesses。
- 不抽取一次性任务内容、隐私、密钥、URL、账号 ID、精确日期或临时参数。
- 只抽取未来同类任务仍有价值的工作流、输出策略、实现偏好、稳定纠正或重复约束。
- 证据弱、过于泛化或价值低时返回空列表。

这一步只负责提出候选，不直接写文件。

## 10. Maintainer：add / merge / discard 决策

入口：

```text
agents/online_skill_evolution.py::maintain_online_skill_candidate()
```

Maintainer 会结合候选、已有 Skills、相似检索结果和上一轮 retrieved reference 做维护决策：

```text
candidate
  -> discover_skills()
  -> exact identity match
  -> retrieve_relevant_skills(limit=8, min_score=0.03)
  -> LLM 决策 add / merge / discard
  -> 规则兜底修正
```

规则兜底包括：

- 如果候选与已有 Skill 的 name、description 或 when-to-use 完全匹配，强制 `merge`。
- 如果 Maintainer 判定 `add`，但相似 Skill top score >= 0.55，改为 `merge`。
- 如果判定 `merge` 但没有目标 Skill，优先使用上一轮 retrieved reference。
- 如果 action 不合法，降级为 `discard`。

`merge` 时，Maintainer 要生成完整的合并后正文，而不是简单追加一句话。这样可以把已有规则和新规则重新组织成可执行的 Skill 文档。

## 11. Add：创建新 Skill

入口：

```text
agents/skills.py::create_skill()
agents/skill_evolution.py::create_skill_file()
```

落盘流程：

```text
create_skill()
  -> create_skill_file()
  -> 检查 name / description
  -> 检查 active 范围内是否已有同名 Skill
  -> 生成安全目录名
  -> 写入 .bear/skills/<slug>/SKILL.md 或 ~/.bear/skills/<slug>/SKILL.md
  -> usage.jsonl 写 create 事件
  -> reset_skill_cache()
```

默认 frontmatter：

```yaml
name: <resolved_name>
description: <description>
version: 0.1.0
created-at: <utc_time>
user-invocable: "false"
context: inline
when-to-use: <optional>
tags: <optional>
allowed-tools: <optional>
```

目录名由 `_safe_skill_slug()` 生成，支持中文名称；如果名称无法生成有效目录名，会退化为 `skill-<hash>`。

## 12. Merge：演化已有 Skill

入口：

```text
agents/skills.py::evolve_skill()
agents/skill_evolution.py::evolve_skill_file()
```

演化流程：

```text
evolve_skill()
  -> resolve_skill_file(target=active/project/user)
  -> 读取原 SKILL.md
  -> 记录演化前完整快照
  -> bump patch version
  -> 更新 last-evolved
  -> 更新 evolution-count
  -> 写回合并后的 SKILL.md
  -> usage.jsonl 写 evolve 事件
  -> reset_skill_cache()
```

快照位置：

```text
.bear/skill-evolution/history/<skill_slug>.jsonl
```

快照包含原始 `SKILL.md` 全文、原版本、lesson、rationale、actor、时间和文件路径。这样即使演化后的 Skill 出现问题，也能从 history 中回溯旧版本。

版本号只 bump patch：

```text
0.1.0 -> 0.1.1 -> 0.1.2
```

如果旧版本号格式异常，则回退为 `0.1.1`。

## 13. Provenance：来源审计

相关入口：

```text
agents/skill_evolution.py::record_online_skill_provenance()
agents/skill_evolution.py::_update_online_provenance_index()
```

每次在线沉淀判断都会追加写：

```text
.bear/skill-evolution/online_provenance.jsonl
```

同时按 Skill 聚合到：

```text
.bear/skill-evolution/online_skill_provenance.json
```

provenance 记录包括：

- `action`：`none`、`add`、`merge`、`discard`、`failed` 等。
- `skill`：目标 Skill 名。
- `messages`：压缩后的对话窗口。
- `retrieved_reference`：当时检索到的参考 Skill。
- `decision`：Maintainer 的决策 JSON。
- `result`：创建或演化结果。
- `error`：失败原因。

追溯某个 Skill 的来源时，可以按以下顺序排查：

```text
online_skill_provenance.json
  -> 找 skill 对应 sources
  -> 回到 online_provenance.jsonl 查看原始事件
  -> 如果是 merge，再看 history/<skill_slug>.jsonl
  -> 最后查看 .bear/skills/<skill>/SKILL.md 当前版本
```

## 14. Usage Judge：统计使用效果与归档噪声

沉淀系统不仅新增能力，也会监控 Skill 是否真的有用。

相关入口：

```text
agents/agent.py::_run_skill_usage_tracking()
agents/online_skill_evolution.py::judge_retrieved_skill_usage()
agents/skill_evolution.py::record_skill_usage_judgments()
```

每轮回复后，如果本轮检索过 Skills，会判断：

- 检索出的 Skill 是否和用户请求相关。
- assistant 回复是否实际遵循了该 Skill 的独特工作流或策略。

统计写入：

```text
.bear/skill-evolution/skill_usage_stats.json
```

典型字段：

| 字段 | 含义 |
|------|------|
| `retrieved` | 被检索出来的次数 |
| `relevant` | 被判断为相关的次数 |
| `used` | 被判断为实际使用的次数 |
| `last_retrieved` | 最近一次被检索时间 |
| `last_used` | 最近一次实际使用时间 |
| `last_reason` | 最近一次判断原因 |
| `last_score` | 最近一次检索分数 |

长期被检索但从未使用的 Skill 会被视为 stale。默认阈值：

```bash
BEAR_SKILL_USAGE_PRUNE_MIN_RETRIEVED=40
BEAR_SKILL_USAGE_PRUNE_MAX_USED=0
```

默认只自动归档用户级 Skill。项目级 Skill 需要显式开启：

```bash
BEAR_SKILL_PRUNE_PROJECT=1
```

归档位置：

```text
.bear/skill-evolution/pruned/
```

## 15. 权限、开关与安全边界

在线自进化开关：

```bash
BEAR_AUTO_SKILL_EVOLUTION=1
```

关闭：

```bash
BEAR_AUTO_SKILL_EVOLUTION=0
```

新 Skill 默认写入项目级：

```bash
BEAR_AUTO_SKILL_TARGET=project
```

也可以写入用户级：

```bash
BEAR_AUTO_SKILL_TARGET=user
```

权限模式影响：

| 模式 | 行为 |
|------|------|
| `plan` | 不调度后台 Skill 自进化和 usage tracking，不写入 |
| `default` | 写操作需要确认，后台沉淀通常不会打断用户 |
| `acceptEdits` | 编辑类操作自动允许，后台 add / merge 可自动写入 |
| `bypassPermissions` | 跳过确认 |
| `dontAsk` | 需要确认的写操作自动拒绝 |

`skill_create` 和 `skill_evolve` 在 `agents/tools.py` 中被归类为编辑类工具：

```text
EDIT_TOOLS = {"write_file", "edit_file", "skill_evolve", "skill_create"}
```

同时在权限检查中会生成明确的确认消息：

```text
create skill: <name>
evolve skill: <skill_name>
```

## 16. 手动维护入口

REPL 命令：

```text
/skills
/skill-stats
/extract_now [hint]
/skill-feedback <skill> <rating> [note]
/skill-evolve <skill> <durable lesson>
/skill-create <name> | <description> | <when-to-use> | <instructions>
/<skill-name> [args]
```

工具入口：

```text
skill
skill_create
skill_evolve
```

使用建议：

- 想从当前对话窗口立即尝试沉淀：使用 `/extract_now [hint]`。
- 已明确知道要新增稳定工作流：使用 `/skill-create`。
- 已有 Skill 需要吸收新规则：使用 `/skill-evolve`。
- 只是记录主观反馈而不改 Skill：使用 `/skill-feedback`。

## 17. 当前项目可观察状态

当前项目已有项目级 Skills：

```text
.bear/skills/Chinese-WebNovel-Skill/SKILL.md
.bear/skills/code_review/SKILL.md
.bear/skills/zhangxuefeng-skill-main/SKILL.md
.bear/skills/政府报告撰写-正式书面化与政策结合/SKILL.md
```

当前已有自进化审计产物：

```text
.bear/skill-evolution/usage.jsonl
.bear/skill-evolution/online_provenance.jsonl
.bear/skill-evolution/online_skill_provenance.json
.bear/skill-evolution/skill_usage_stats.json
```

其中 `政府报告撰写-正式书面化与政策结合` 是在线沉淀链路创建出来的项目级 Skill。当前未看到 `history/` 目录，说明已经发生过在线新增 `add`，但还没有看到已有 Skill 的 `merge/evolve` 快照。

## 18. 实现思路总结

这套自进化机制可以概括为四个闭环。

第一，召回闭环：

```text
discover_skills()
  -> retrieve_relevant_skills()
  -> retrieved_skills 注入
  -> 模型按 when-to-use 判断是否调用
```

第二，经验沉淀闭环：

```text
当前轮任务和回答
  -> pending window
  -> 下一轮用户反馈
  -> Extractor 抽取候选
  -> Maintainer 决策 add / merge / discard
  -> SKILL.md 落盘
```

第三，治理审计闭环：

```text
create / evolve / discard / failed
  -> usage.jsonl
  -> online_provenance.jsonl
  -> online_skill_provenance.json
  -> history snapshot
```

第四，质量反馈闭环：

```text
retrieved skills
  -> judge relevance and used
  -> skill_usage_stats.json
  -> stale prune
```

这个设计的核心取舍是：把“是否值得沉淀”从普通任务执行中拆出来，用独立 Extractor 和 Maintainer 处理；把“写入 Skill”收敛到 `skill_evolution.py`，统一版本、快照和审计；把“是否好用”通过 usage judge 继续观察，避免 Skill 集合只增不减。

## 19. 后续可优化方向

当前实现已经形成可运行闭环，后续可以继续增强：

- 增加 Skill diff 预览，让用户在确认前看到即将写入的规则变化。
- 对 Extractor 候选增加本地规则评分，先过滤低价值候选再调用模型。
- 给 Skill 增加来源置信度和适用范围字段，辅助检索和治理。
- 为 `history/*.jsonl` 增加恢复命令，支持一键回滚到某个版本。
- 对 usage stats 做周期性报告，展示高价值 Skill、低价值 Skill 和候选归档建议。
- 将 Skill 检索从 BM25-lite 扩展为 hybrid retrieval，但保留当前轻量实现作为 fallback。

## 20. 关键代码定位

| 逻辑 | 代码入口 |
|------|----------|
| 加载 Skills | `agents/skills.py::discover_skills()` |
| 解析 `SKILL.md` | `agents/skills.py::_parse_skill_file()` |
| 检索 Skills | `agents/skills.py::retrieve_relevant_skills()` |
| 注入 retrieved context | `agents/skills.py::format_retrieved_skill_context()` |
| Skill 工具执行 | `agents/agent.py::_execute_skill_tool()` |
| 保存 pending window | `agents/agent.py::_set_pending_skill_extraction_window()` |
| 合并下一轮反馈 | `agents/agent.py::_pop_pending_skill_extraction_window()` |
| 在线沉淀入口 | `agents/online_skill_evolution.py::online_ingest()` |
| 抽取候选 | `agents/online_skill_evolution.py::extract_online_skill_candidate()` |
| add / merge / discard | `agents/online_skill_evolution.py::maintain_online_skill_candidate()` |
| 新建 Skill | `agents/skill_evolution.py::create_skill_file()` |
| 演化 Skill | `agents/skill_evolution.py::evolve_skill_file()` |
| 记录 provenance | `agents/skill_evolution.py::record_online_skill_provenance()` |
| usage judge | `agents/online_skill_evolution.py::judge_retrieved_skill_usage()` |
| 写 usage stats | `agents/skill_evolution.py::record_skill_usage_judgments()` |
| stale 归档 | `agents/skill_evolution.py::_maybe_prune_stale_skill()` |
