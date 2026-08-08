# DeepAgent Memory 代码实现梳理

代码目录：`/Users/xiao_xiong/Desktop/code/DeepAgent-main`

主要文件：

- `src/prompts/prompts_deepagent.py`：定义 memory folding 的触发 token、主 agent prompt、三类 memory 生成 prompt。
- `src/run_deep_agent.py`：主推理循环，负责检测 `<fold_thought>`、调用辅助模型生成 memory、重置 prompt 并继续推理。
- `README.md`：说明 Autonomous Memory Folding 的定位和运行参数。

## 1. 总体实现思路

DeepAgent 的 memory 实现是一个运行时上下文压缩机制，不是持久化长期记忆系统。

它的核心流程是：

```text
主模型推理
  |
  | 输出工具搜索 / 工具调用 / 普通推理 / <fold_thought>
  v
运行时检测输出是否以 <fold_thought> 结束
  |
  v
调用辅助模型并行生成三类 memory
  |
  | episode memory
  | working memory
  | tool memory
  v
把原始长推理历史从 prompt 中移除
  |
  v
把 folded memory 插回 original_prompt
  |
  v
主模型基于压缩记忆开启新一轮推理
```

对应论文里的 “agent takes a breath”：模型主动发出 `<fold_thought>`，系统折叠之前的交互轨迹，然后让模型带着压缩后的状态继续。

## 2. 触发入口

### 2.1 特殊 token

在 `src/prompts/prompts_deepagent.py` 中定义：

```python
FOLD_THOUGHT = "<fold_thought>"
```

主 prompt 会明确告诉模型：当 reasoning history 过长、工具调用失败过多、需要改变方向等情况出现时，可以生成 `<fold_thought>`。

### 2.2 主模型生成时把 `<fold_thought>` 作为 stop

在 `src/run_deep_agent.py` 的 `generate_main_reasoning_sequence` 中，首次生成和后续生成都设置了 stop：

```python
stop=[END_TOOL_SEARCH, END_TOOL_CALL, FOLD_THOUGHT]
```

这意味着主模型一旦生成：

- `</tool_search>`：系统进入工具搜索分支。
- `</tool_call>`：系统进入工具调用分支。
- `<fold_thought>`：系统进入 thought folding 分支。

这里的设计比较直接：memory folding 被工程上当成和 tool search、tool call 同级的可拦截动作。

## 3. 主循环中的 memory folding 分支

核心代码在 `src/run_deep_agent.py`：

```python
elif seq['output'].rstrip().endswith(FOLD_THOUGHT):
    if total_folds >= args.max_fold_limit:
        ...
    else:
        episode_memory, working_memory, tool_memory = await run_thought_folding(...)
        append_text = f"Memory of previous folded thoughts:\n\nEpisode Memory:\n{episode_memory}\n\nWorking Memory:\n{working_memory}\n\nTool Memory:\n{tool_memory}"
        seq['prompt'] = seq['original_prompt'].replace(
            "Now, begin your reasoning for",
            f"{append_text}\n\nNow, begin your reasoning for"
        )
        seq['interactions'].append({
            "type": "thought_folding",
            "episode_memory": episode_memory,
            "working_memory": working_memory,
            "tool_memory": tool_memory,
        })
        total_tokens = len(seq['prompt'].split())
        total_folds += 1
```

这个分支做了四件事：

1. 检查是否超过 `max_fold_limit`。
2. 调用 `run_thought_folding` 生成三类 memory。
3. 用 `seq['original_prompt']` 重建 prompt，并把 memory 插到 “Now, begin your reasoning for” 前面。
4. 把本次 thought folding 写入 `seq['interactions']`，最终会保存到输出 JSON 里。

关键点：它不是在旧 prompt 后面追加 memory，而是用 `original_prompt` 重建 prompt。这相当于把之前长历史清掉，只保留原始任务说明和 folded memory。

## 4. memory 生成函数

实现函数是 `run_thought_folding`：

```python
async def run_thought_folding(
    client,
    tokenizer,
    semaphore,
    args,
    question,
    current_output,
    interactions=None,
    available_tools=None,
) -> Tuple[str, str, str]:
```

### 4.1 输入

它接收：

- `question`：原始任务。
- `current_output`：截至当前的完整主模型输出，包括推理、工具搜索结果、工具调用结果、`<fold_thought>`。
- `interactions`：结构化交互记录。
- `available_tools`：当前可用工具列表。

### 4.2 把当前输出切成 step

代码把 `current_output` 按空行切分：

```python
previous_thoughts = current_output.split("\n\n")
previous_thoughts = [f"Step {i+1}: {step}" for i, step in enumerate(previous_thoughts)]
previous_thoughts = "\n\n".join(previous_thoughts)
```

这不是严格的 action parser，而是一个轻量格式化：把长文本分块后编号，方便辅助模型摘要。

### 4.3 提取 tool call history

tool memory 需要工具调用记录，因此函数从 `interactions` 中筛出包含 `tool_call_query` 的项：

```python
tool_call_history.append({
    "tool_call": interaction["tool_call_query"],
    "tool_response": interaction["tool_response"]
})
```

注意：这里不会纳入 tool search 的 returned tools，只纳入真正的 tool call 和 response。

### 4.4 并行生成三类 memory

代码里定义了三个异步函数：

- `generate_episode_memory`
- `generate_working_memory`
- `generate_tool_memory`

然后用：

```python
episode_memory, working_memory, tool_memory = await asyncio.gather(
    generate_episode_memory(),
    generate_working_memory(),
    generate_tool_memory()
)
```

这和论文描述一致：三类 memory 并行生成，降低 folding 的额外延迟。

## 5. 三类 memory prompt 的实现

三类 prompt 都在 `src/prompts/prompts_deepagent.py`。

### 5.1 Episode Memory

函数：

```python
get_episode_memory_instruction(question, prev_reasoning, available_tools="")
```

定位：把 agent 的历史推理压缩成高层任务轨迹。

prompt 要求抽取：

- major milestones。
- subgoal completions。
- strategic decisions。
- long-term goals 相关的关键事件。

输出 schema：

```json
{
  "task_description": "...",
  "key_events": [
    {
      "step": "step number",
      "description": "...",
      "outcome": "..."
    }
  ],
  "current_progress": "..."
}
```

### 5.2 Working Memory

函数：

```python
get_working_memory_instruction(question, prev_reasoning, available_tools="")
```

定位：只保留当前正在做什么、卡在哪里、下一步做什么。

prompt 明确要求：

- Extract ONLY immediate goals, current challenges, and next steps。
- Ignore completed/historical information。

输出 schema：

```json
{
  "immediate_goal": "...",
  "current_challenges": "...",
  "next_actions": [
    {
      "type": "tool_call/planning/decision",
      "description": "..."
    }
  ]
}
```

### 5.3 Tool Memory

函数：

```python
get_tool_memory_instruction(question, prev_reasoning, tool_call_history, available_tools="")
```

定位：把工具使用经验单独压缩出来。

prompt 要求分析：

- successful/unsuccessful tool patterns。
- effective parameter combinations。
- common failure modes。
- typical response structures。

输出 schema：

```json
{
  "tools_used": [
    {
      "tool_name": "string",
      "success_rate": "float",
      "effective_parameters": ["param1", "param2"],
      "common_errors": ["error_type1", "error_type2"],
      "response_pattern": "...",
      "experience": "..."
    }
  ],
  "derived_rules": [
    "When X condition occurs, prefer tool Y"
  ]
}
```

代码层面最有价值的是 tool memory 使用了专门的 `tool_call_history`，而不是只依赖全文摘要。这更容易保留工具名、参数、结果、错误信息。

## 6. interactions 在 memory 中的作用

`seq['interactions']` 是贯穿整个推理过程的结构化日志。

工具搜索时写入：

```python
{
    "type": "tool_search",
    "tool_search_query": tool_search_query,
    "returned_tools": helpful_tools,
}
```

工具调用成功时写入：

```python
{
    "type": "tool_call",
    "tool_call_query": tool_call_query,
    "tool_response": tool_response
}
```

工具调用失败时写入：

```python
{
    "type": "tool_call",
    "tool_call_query": tool_call_query,
    "tool_response": {"error": "..."}
}
```

memory folding 后写入：

```python
{
    "type": "thought_folding",
    "episode_memory": episode_memory,
    "working_memory": working_memory,
    "tool_memory": tool_memory,
}
```

这份 `interactions` 最终会保存在结果文件中，方便复盘 agent 在哪里搜索、调用、折叠。

## 7. 与论文描述一致的地方

1. **agent 自主触发**

   论文说 agent 可以在任意逻辑点触发 memory folding。代码里通过 prompt 引导模型生成 `<fold_thought>`，运行时检测该标记。

2. **三类 memory**

   代码实现了论文中的 episode、working、tool 三类 memory，schema 基本和附录 C 一致。

3. **辅助模型压缩**

   memory 生成使用 `aux_client` 和 `args.aux_model_name`，主模型不自己压缩历史。这个分工和论文一致。

4. **并行生成**

   三类 memory 用 `asyncio.gather` 并行生成，符合论文中的 parallel memory generation。

5. **替换原始历史**

   代码用 `original_prompt` 重建 prompt，把 folded memory 插入原始任务 prompt 前段，从而清除冗长历史。

## 8. 代码实现中的注意点和偏差

### 8.1 `enable_thought_folding` 参数没有真正控制 folding

代码定义了参数：

```python
parser.add_argument('--enable_thought_folding', action='store_true', default=False)
```

但主 prompt 默认都会包含 thought folding 指令，生成 stop 也始终包含 `FOLD_THOUGHT`。主循环进入 folding 分支时也没有判断 `args.enable_thought_folding`。

实际生效的限制主要是：

```python
--max_fold_limit
```

如果想让开关真正生效，应在 prompt 构建、stop list、fold 分支至少一处显式判断该参数。

### 8.2 `available_tools` 在 `run_thought_folding` 中被覆盖

函数参数里传入了 `available_tools`，但内部写了：

```python
available_tools = ""
if available_tools:
    available_tools = json.dumps(available_tools, indent=2)
```

这里先把参数覆盖成空字符串，导致 `if available_tools` 永远为 false。结果是三类 memory prompt 实际拿不到 available tools。

更合理的写法应该类似：

```python
available_tools_text = ""
if available_tools:
    available_tools_text = json.dumps(available_tools, indent=2)
```

然后把 `available_tools_text` 传入三个 prompt。

### 8.3 没有 JSON schema 校验

`extract_json_from_response` 只做了代码块剥离：

```python
pattern = r'```json\s*(.*?)\s*```'
```

它没有执行：

- `json.loads`。
- 字段完整性校验。
- 类型校验。
- 失败重试。

因此辅助模型如果输出非法 JSON，系统仍会把它作为字符串插回 prompt。论文强调 JSON schema 的稳定性，但代码没有做严格 schema enforcement。

### 8.4 fold 后不会保留之前多次 fold 的 memory

fold 时 prompt 被设置为：

```python
seq['prompt'] = seq['original_prompt'].replace(...)
```

这会基于最初 prompt 重建上下文。当前这次生成的 memory 会插入进去，但之前 prompt 中的旧 folded memory 不会自动累积，除非当前 `current_output` 已经把旧 memory 或后续推理写进了 `seq['output']` 并被新一轮压缩进来。

这是一种“每次重新折叠当前可见轨迹”的策略，不是持久 memory store。

### 8.5 token 统计很粗略

代码用：

```python
len(text.split())
```

近似统计 token，并设置：

```python
MAX_TOKENS = 40000
```

这不是 tokenizer 级别的准确 token 统计。实际生产实现最好使用 tokenizer 计算上下文长度。

### 8.6 被注释掉的系统提醒

代码中有两个注释块：

```python
# if seq['action_count'] % 20 == 0 and total_folds < args.max_fold_limit:
#     append_text += "<system_message>You have made 20 actions..."

# if seq['action_count'] >= 30 and total_folds < args.max_fold_limit:
#     append_text += "<system_message>You have made 30 actions..."
```

说明作者曾考虑过“系统级提醒模型可以 fold”，但当前版本主要依赖模型自主判断。

## 9. 可以抽象出的工程模式

如果要在自己的 agent 中复用，可以按下面接口设计：

```python
class MemoryFolder:
    async def should_fold(self, output, stats) -> bool:
        return output.rstrip().endswith("<fold_thought>")

    async def fold(self, task, transcript, interactions, available_tools):
        episode, working, tool = await asyncio.gather(
            self.make_episode_memory(task, transcript, available_tools),
            self.make_working_memory(task, transcript, available_tools),
            self.make_tool_memory(task, transcript, interactions, available_tools),
        )
        return {
            "episode_memory": episode,
            "working_memory": working,
            "tool_memory": tool,
        }

    def rebuild_prompt(self, original_prompt, memory):
        return inject_memory(original_prompt, memory)
```

关键原则：

1. 把 fold 做成 agent action，而不是只做后台摘要。
2. 保留结构化 `interactions`，尤其是 tool call 参数和结果。
3. memory 生成用辅助模型，主模型继续负责策略推理。
4. fold 后重建上下文，而不是无限追加摘要。
5. JSON 必须解析和校验，失败要修复或重试。
6. `available_tools`、`tool_call_history`、`current_output` 要分开传，避免只给辅助模型一坨自然语言历史。

## 10. 推荐改进点

如果要把这份代码改成更稳的生产实现，优先级可以这样排：

1. **修复 `available_tools` 覆盖 bug**

   让三类 memory prompt 能看到当前工具集，尤其是 open-set 动态检索出来的工具。

2. **让 `enable_thought_folding` 真正生效**

   关闭时不在 prompt 中暴露 `<fold_thought>`，stop list 也不包含该 token，主循环也不执行 folding。

3. **增加 JSON schema 校验**

   对 episode、working、tool memory 分别 `json.loads`，并校验必要字段。失败时可以用辅助模型做 JSON repair。

4. **把 token 统计改成 tokenizer 统计**

   避免 `split()` 低估或高估实际上下文长度。

5. **区分 hard trigger 和 soft trigger**

   除模型主动输出 `<fold_thought>` 外，可以增加系统阈值：

   - 上下文 token 超阈值。
   - 连续工具失败次数超阈值。
   - action count 到达某个阶段。
   - 完成明确子目标。

6. **保留 memory 版本历史**

   当前 `interactions` 会保存 thought folding 记录，但 prompt 重建时不显式管理多版本 memory。可以额外维护 `memory_snapshots`，供调试和回滚。

## 11. 最小实现伪代码

```python
while not finished:
    response = await main_model.generate(
        prompt,
        stop=["</tool_search>", "</tool_call>", "<fold_thought>"]
    )

    output += response

    if response.endswith("</tool_search>"):
        tools = retrieve_tools(parse_search(response))
        interactions.append({"type": "tool_search", ...})
        prompt += format_tool_search_result(tools)

    elif response.endswith("</tool_call>"):
        result = call_tool(parse_tool_call(response))
        interactions.append({"type": "tool_call", ...})
        prompt += format_tool_result(result)

    elif response.endswith("<fold_thought>"):
        memory = await memory_folder.fold(
            task=question,
            transcript=output,
            interactions=interactions,
            available_tools=available_tools,
        )
        validate(memory)
        interactions.append({"type": "thought_folding", **memory})
        prompt = rebuild_from_original_prompt(question, tools, memory)

    else:
        finished = True
```

## 12. 总结

代码里的 memory folding 是一个“主模型主动触发 + 辅助模型结构化压缩 + prompt 重建”的机制。它没有复杂的外部 memory database，也不做长期跨任务记忆，而是专注解决单个长任务中的上下文膨胀、错误路径累积和工具经验丢失问题。

从工程角度看，这套实现最值得借鉴的是两个点：

1. 把 memory fold 当成和 tool call 同级的 agent action。
2. 把 memory 拆成 episode、working、tool 三类，特别是把 tool experience 从通用摘要里单独拿出来。

但当前代码也有明显可改进处：`available_tools` 传参 bug、`enable_thought_folding` 开关未生效、缺少 JSON schema 校验。这些如果修掉，才更接近论文里描述的稳定结构化 memory folding。
