# Skills 加载逻辑

本文档说明 Bear Code 当前的 skills 加载、优先级、注册、触发和执行流程。

## 1. Skill 文件结构

一个 skill 必须是一个目录，并且目录下必须存在 `SKILL.md`：

```text
<skills_root>/<skill_name>/SKILL.md
```

例如：

```text
.bear/skills/code_review/SKILL.md
~/.bear/skills/code_review/SKILL.md
```

当前加载器不会加载这种单文件形式：

```text
.bear/skills/code_review.md
```

因为 `agents/skills.py` 只遍历 skills 根目录下的子目录，然后查找子目录中的 `SKILL.md`。

## 2. 加载路径

入口函数是：

```python
discover_skills()
```

位置：

```text
agents/skills.py
```

当前会扫描两个目录：

```text
~/.bear/skills
Path.cwd()/.bear/skills
```

含义：

- `~/.bear/skills`：用户级 skills。
- `Path.cwd()/.bear/skills`：项目级 skills。

本地运行时，`Path.home()` 是当前系统用户目录，例如：

```text
/Users/xiao_xiong/.bear/skills
```

Docker 运行时，容器内 `Path.home()` 通常是：

```text
/root/.bear/skills
```

Docker 中 `Path.cwd()` 是：

```text
/workspace
```

所以项目级 skills 在 Docker 中对应：

```text
/workspace/.bear/skills
```

## 3. 加载优先级

加载顺序是：

1. 用户级 skills：`~/.bear/skills`
2. 项目级 skills：`Path.cwd()/.bear/skills`

用户级优先级更高。

代码逻辑是：

```python
_load_skills_from_dir(user_dir, "user", skills)
_load_skills_from_dir(project_dir, "project", skills, overwrite=False)
```

项目级加载时使用 `overwrite=False`。如果用户级和项目级存在同名 skill，项目级不会覆盖用户级。

例如同时存在：

```text
~/.bear/skills/code_review/SKILL.md
.bear/skills/code_review/SKILL.md
```

最终生效的是：

```text
~/.bear/skills/code_review/SKILL.md
```

## 4. 发现规则

加载函数是：

```python
_load_skills_from_dir(base_dir, source, skills, overwrite=True)
```

规则：

1. 如果 `base_dir` 不存在，直接跳过。
2. 遍历 `base_dir` 下的一级子项。
3. 只处理目录，忽略普通 `.md` 文件。
4. 每个目录下必须存在 `SKILL.md`。
5. 解析成功后，以 skill 的 `name` 作为 key 保存。

有效结构：

```text
.bear/skills/code_review/SKILL.md
```

无效结构：

```text
.bear/skills/code_review.md
.bear/skills/code_review/readme.md
.bear/skills/code_review/skill.md
```

文件名必须是大写：

```text
SKILL.md
```

## 5. Frontmatter 字段

`SKILL.md` 使用 YAML frontmatter：

```markdown
---
name: code_review
description: Review code for bugs, security issues, regressions, maintainability risks, and missing tests.
user-invocable: false
when-to-use: Use when the user asks to review code, code review a file or diff, inspect code quality, find bugs, identify security issues, evaluate maintainability, or check for missing tests.
context: inline
allowed-tools: read_file,grep_search
---

# Skill body
...
```

当前解析的字段：

| 字段 | 是否必需 | 默认值 | 说明 |
|------|----------|--------|------|
| `name` | 否 | skill 目录名 | skill 名称 |
| `description` | 否 | 空字符串 | 展示给模型和 `/skills` 的简介 |
| `when-to-use` / `when_to_use` | 否 | `None` | 自动调用提示条件 |
| `user-invocable` | 否 | `true` | 是否允许用户通过 `/<skill>` 手动调用 |
| `context` | 否 | `inline` | `inline` 或 `fork` |
| `allowed-tools` | 否 | `None` | fork 模式下限制子 Agent 可用工具 |

注意：frontmatter 解析器只支持简单的 `key: value` 形式，不支持复杂 YAML 嵌套结构。

## 6. 缓存机制

skills 会被进程内缓存：

```python
_cached_skills: list[SkillDefinition] | None = None
```

第一次调用 `discover_skills()` 时扫描磁盘。

后续调用会直接返回缓存：

```python
if _cached_skills is not None:
    return _cached_skills
```

如果运行中修改了 skill 文件，当前进程不会自动重新加载。需要：

- 重启 Bear Code；或
- 调用 `reset_skill_cache()`，然后重新 `discover_skills()`。

普通用户场景下，重启程序最直接。

## 7. 注入 System Prompt

System Prompt 构建时会调用：

```python
build_skill_descriptions()
```

调用位置：

```text
agents/prompt.py
```

它会把已发现的 skills 整理成文本，注入到 system prompt 的 `{{skills}}` 占位符。

分类规则：

```python
invocable = [s for s in skills if s.user_invocable]
auto_only = [s for s in skills if not s.user_invocable]
```

### 7.1 用户手动调用 skills

如果：

```yaml
user-invocable: true
```

或省略该字段，就会出现在：

```text
User-invocable skills
```

用户可以在 REPL 中输入：

```text
/code_review agents/agent.py
```

### 7.2 自动调用候选 skills

如果：

```yaml
user-invocable: false
```

会出现在：

```text
Auto-invocable skills
```

当前 system prompt 会提示模型：

```text
When the user's request matches a skill's When to use, call the `skill` tool with that skill name before continuing.
Do not ask the user to invoke it manually.
```

这意味着自动调用不是 Python 代码硬匹配关键词，而是模型根据 system prompt 和 `when-to-use` 判断是否调用 `skill` 工具。

## 8. 手动调用流程

REPL 中以 `/` 开头的输入会进入 skill 命令分支。

相关逻辑在：

```text
agents/main.py
```

流程：

1. 用户输入：

   ```text
   /code_review agents/agent.py
   ```

2. 解析命令名：

   ```text
   code_review
   ```

3. 调用：

   ```python
   get_skill_by_name(cmd_name)
   ```

4. 如果 skill 存在且 `user_invocable=True`，执行：

   - `inline`：解析 skill prompt 后直接 `agent.chat(resolved)`。
   - `fork`：让主 Agent 使用 `skill` 工具调用该 skill。

如果 `user-invocable: false`，用户不能通过 `/<skill>` 手动调用它。

## 9. 自动调用流程

自动调用依赖模型调用 `skill` 工具。

工具定义在：

```text
agents/tools.py
```

工具名：

```text
skill
```

工具参数：

```json
{
  "skill_name": "code_review",
  "args": "agents/agent.py"
}
```

当模型调用 `skill` 工具时，Agent 会进入：

```python
_execute_skill_tool()
```

位置：

```text
agents/agent.py
```

然后调用：

```python
execute_skill(skill_name, args)
```

返回内容包括：

```python
{
    "prompt": resolved_prompt,
    "allowed_tools": skill.allowed_tools,
    "context": skill.context,
}
```

## 10. inline 与 fork 执行模式

### 10.1 inline

默认模式：

```yaml
context: inline
```

执行结果是：

```text
[Skill "xxx" activated]

<skill prompt>
```

这段内容会作为 tool result 返回给模型。模型随后继续按照 skill prompt 完成任务。

### 10.2 fork

如果设置：

```yaml
context: fork
```

Agent 会创建一个子 Agent 执行 skill：

```python
sub_agent = Agent(...)
sub_result = await sub_agent.run_once(...)
```

如果配置了：

```yaml
allowed-tools: read_file,grep_search
```

子 Agent 的工具会被限制在这些工具内。

如果没有配置 `allowed-tools`，默认会给子 Agent 除 `agent` 以外的工具，避免子 Agent 无限递归创建 Agent。

## 11. 路径与 Docker 注意事项

本地运行时：

```text
~/.bear/skills
<project>/.bear/skills
```

Docker 运行时：

```text
/root/.bear/skills
/workspace/.bear/skills
```

如果只挂载项目目录：

```bash
-v "$PWD:/workspace"
```

项目级 skills 会自动可见：

```text
/workspace/.bear/skills
```

如果还想使用本机用户级 skills，需要额外挂载：

```bash
-v "$HOME/.bear:/root/.bear"
```

## 12. 当前项目示例

当前项目中有：

```text
.bear/skills/code_review/SKILL.md
```

它的 frontmatter 类似：

```yaml
name: code_review
description: Review code for bugs, security issues, regressions, maintainability risks, and missing tests.
user-invocable: false
when-to-use: Use when the user asks to review code, code review a file or diff, inspect code quality, find bugs, identify security issues, evaluate maintainability, or check for missing tests.
```

因此它是自动调用候选 skill，不是手动 `/code_review` skill。

用户提出类似请求时：

```text
请 review agents/agent.py
```

模型应该根据 system prompt 调用：

```json
{
  "skill_name": "code_review",
  "args": "agents/agent.py"
}
```

然后根据返回的 skill prompt 继续审查代码。

## 13. 排查 checklist

如果 skill 没有加载：

- 确认路径是 `<root>/skills/<skill_name>/SKILL.md`。
- 确认文件名是 `SKILL.md`，大小写一致。
- 确认当前运行目录是项目根目录，否则 `Path.cwd()/.bear/skills` 会指向别处。
- Docker 中确认项目已挂载到 `/workspace`。
- 运行 `/skills` 检查是否出现在列表中。
- 修改 skill 后重启进程，避免缓存仍使用旧内容。

如果 skill 加载了但没有自动调用：

- 确认 `user-invocable: false`。
- 确认 `when-to-use` 写得足够明确。
- 确认 system prompt 中能看到 `Auto-invocable skills`。
- 确认模型确实有 `skill` 工具可用。
- 如果希望强制执行，可以手动调用对应 user-invocable skill，或把用户请求写得更贴近 `when-to-use`。

## 14. Skill 自进化机制

Bear Code 现在参考 AutoSkill 的 usage tracking、version snapshot 和 gated update 思路，为 skill 增加了可控自进化能力。

核心文件：

```text
agents/skill_evolution.py
```

### 14.1 使用记录

每次通过 `skill` 工具或 REPL 调用 skill 时，会写入：

```text
.bear/skill-evolution/usage.jsonl
```

记录内容包括：

- `event`: `invoke`
- `time`: UTC 时间
- `skill`: skill 名称
- `source`: `user` 或 `project`
- `context`: `inline` 或 `fork`
- `args_preview`: 参数预览

查看统计：

```text
/skill-stats
```

### 14.2 反馈记录

REPL 支持手动记录 skill 反馈：

```text
/skill-feedback <skill-name> <rating> [note]
```

例如：

```text
/skill-feedback code_review bad 以后 review 要先看调用方，不要只看单文件
```

这只记录反馈，不直接修改 skill。

### 14.3 演化写入

当用户给出明确、可复用、未来同类任务也适用的规则时，可以把它沉淀到 skill：

```text
/skill-evolve <skill-name> <durable lesson>
```

例如：

```text
/skill-evolve code_review Review 时必须检查调用方和被调用方的 API 契约是否一致。
```

模型也可以调用工具：

```text
skill_evolve
```

但 system prompt 约束它只能在用户给出明确可复用反馈、稳定纠正或持久工作流偏好时调用。不要从一次性任务内容、隐私信息、临时项目事实或 assistant 自己猜测中演化 skill。

### 14.4 版本快照

每次演化写入前，都会把旧版 `SKILL.md` 保存到：

```text
.bear/skill-evolution/history/<skill>.jsonl
```

随后修改目标 `SKILL.md`：

- frontmatter 中 `version` patch 位加 1。
- 写入 `last-evolved`。
- 写入或更新 `evolution-count`。
- 在正文的 `## Evolution Notes` 下追加规则。

### 14.5 权限边界

`skill_evolve` 被视为写操作：

- plan mode 中会被阻断。
- default mode 中需要确认。
- accept-edits / bypassPermissions 会按对应权限策略放行。

默认演化目标是当前生效 skill；也可以指定：

```text
target: active | project | user
```

### 14.6 回滚方式

当前没有自动回滚命令。需要回滚时，从 history JSONL 中取出对应 snapshot 的 `content` 字段，写回目标 `SKILL.md`，然后重启 Bear Code 或调用 `reset_skill_cache()`。
