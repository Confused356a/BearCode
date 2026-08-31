# 学习笔记：从两篇论文借到的思路

> 整理 Bear Code 项目中借鉴的两篇论文——它们分别提供了「会话记忆折叠」和「技能自进化」两条思路。记录论文出处、发表水平，以及我具体借了哪些点、落到了哪些代码。

---

## 1. DeepAgent —— 会话记忆折叠

### 论文信息

- **标题**：*DeepAgent: A General Reasoning Agent with Scalable Toolsets*
- **arXiv**：2510.21618（2025-10-24 提交）
- **发表**：The Web Conference 2026（**WWW 2026**）
- **团队**：中国人民大学 RUC-NLPIR
- **代码**：github.com/RUC-NLPIR/DeepAgent

### 发表水平

**高。** WWW 是计算机领域 CCF-A 类顶会，经过同行评审。这是很扎实的一篇。

### 借到的思路

核心思想：长对话**不是截断，而是折叠**成结构化记忆，让 agent 在长程任务里不断档、不丢关键状态。

- **结构化分层记忆**：把历史压成 episodic / working / tool 三层，而不是简单丢弃。
- **折叠而非截断**：保留任务进度、当前目标、工具经验，让 agent 能"喘口气"重新调整策略。
- **主动 + 兜底触发**：模型主动触发 + 系统阈值兜底。

### 我的落地

对应 `agents/session_memory.py`：

| 论文概念 | 项目实现 |
|---|---|
| episodic memory | `episode_memory`（任务描述 / 关键事件 / 当前进度） |
| working memory | `working_memory`（当前子目标 / 阻塞点 / 下一步动作） |
| tool memory | `tool_memory`（已用工具 / 有效参数 / 常见错误 / 经验） |
| 折叠而非截断 | 压缩成 `<session-folded-memory>`，失败走 `fallback_folded_memory` |
| 主动 + 兜底 | `compact_context` 工具 + 上下文阈值自动折叠 |

**验证**：消融实验——开折叠 GAIA Pass@1 53.3，关折叠 44.7，说明折叠不只是省 token，而是真的支撑了长程任务。

---

## 2. AutoSkill —— 技能自进化

### 论文信息

- **标题**：*AutoSkill: Experience-Driven Lifelong Learning via Skill Self-Evolution*
- **arXiv**：2603.01145（v2，2026-03-01 发布）
- **发表**：目前为 **arXiv 预印本**（未查到已接收会议）
- **团队**：华东师范大学 + 上海人工智能实验室（上海 AI Lab）

### 发表水平

**中上，但还差临门一脚。** 作者和机构（上海 AI Lab）都可靠，方向也热；但尚未经过顶会同行评审，且有评论指出它更偏"框架/架构论文"，而非跑大基准的实证系统论文。对外表述时建议说成"借鉴近期自进化框架思路"，而非"已被权威评审的结论"。

### 借到的思路

核心思想：agent 应该**自动从用户交互中沉淀可复用技能**，并**能评估技能好坏**，而不是靠人手写 prompt。

- **技能作为一等公民**：把能力外化成显式的 `SKILL.md`（结构化字段 + 版本演化），而非留在隐式记忆里。
- **双循环**：
  1. 生成时检索技能辅助回复（query 改写 → 混合检索 → 技能条件生成）。
  2. 进化时抽取 / 维护 / 合并技能（Extractor → Maintainer）。
- **混合检索**：稠密语义匹配（向量）+ 词面匹配（BM25）。
- **训练无关**：用 prompt 驱动，不改底层模型。

### 我的落地

对应 `agents/online_skill_evolution.py` + `agents/online_skill_eval.py`：

| 论文概念 | 项目实现 |
|---|---|
| 从交互中抽技能 | pending window → Extractor 抽候选 → Maintainer 决策 |
| 技能库治理 | add / merge / discard 三态，避免膨胀 |
| 可审计沉淀 | 写 `SKILL.md` + provenance + 版本快照 + usage 统计 |
| 技能质量评测 | replay 样本池 → 规则编译 → LLM judge → 候选变体 → champion |

**亮点**：`candidate variants + champion 晋级门控` 最接近论文味道——抽出来不直接信，先 replay 回放，判不过就生成改进候选，候选明显更好才记 champion，且默认**不覆盖**线上 `SKILL.md`，做到"自进化但可控"。

---

## 3. 对比小结

| | DeepAgent | AutoSkill |
|---|---|---|
| 时间 | 2025-10 | 2026-03 |
| 级别 | **WWW 2026（CCF-A 顶会）** | arXiv 预印本 |
| 借的点 | 记忆折叠（三层 schema） | 技能自进化 + SKILL.md 沉淀 |
| 可信度 | 高 | 中（未评审） |

**一句话总结**：DeepAgent 借了"记忆折叠"的骨架，AutoSkill 借了"技能自进化 + 评测"的骨架，都用工程代码落地了，并补了消融 / 对比实验。

---

## 待确认

- 项目 wiki 里用作基线的 **HiRA** 尚未确认出自哪篇论文、什么水平——需要进一步查证。
