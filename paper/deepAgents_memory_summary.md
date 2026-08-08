# DeepAgent 论文中 Memory 部分总结

来源：`deepAgents.pdf`，主要参考 Abstract、Introduction、3.1、3.2、3.4、5.4 和 Appendix C。

## 一句话概括

DeepAgent 的 memory 机制不是传统意义上的长期用户偏好记忆，而是一个面向长任务轨迹的 **Autonomous Memory Folding**：当 agent 觉得需要“重启一轮思考”时，主动触发折叠，把之前完整交互历史压缩成结构化的 episodic memory、working memory 和 tool memory，再用这份压缩记忆替换原始历史继续推理。

## 出发点

论文针对的是长链路、开放工具集、真实环境交互任务。传统 agent 通常保留完整历史，或者用固定窗口裁剪上下文，这会带来几个问题：

1. **上下文越来越长**：长任务中工具搜索、工具调用、环境反馈会快速堆积，token 开销和注意力负担都会上升。
2. **错误路径会持续污染后续推理**：如果前面探索方向错了，完整历史会让模型不断被错误尝试牵引。
3. **普通摘要容易丢关键信息**：尤其是工具调用参数、失败原因、当前卡点、下一步计划等细节，一旦压缩成自然语言摘要，很难稳定保留。
4. **固定 workflow 缺少自主节奏**：什么时候该总结、什么时候该换策略，最好由 agent 根据任务状态自行判断，而不是外部流程硬编码。

因此 DeepAgent 把 memory folding 设计成 agent 可以自主选择的一种 action，让模型在长任务中“take a breath”：暂停、整理历史、重看当前局面、避免继续陷入错误探索。

## 核心设计

在 DeepAgent 的动作空间里，Memory Fold 和 thinking、tool search、tool call 并列，是一种显式动作：

- `Internal Thought`：内部推理。
- `Tool Search`：动态搜索可用工具。
- `Tool Call`：调用具体工具。
- `Memory Fold`：把历史交互压缩成结构化记忆，并用压缩记忆初始化下一步状态。

agent 在任意逻辑节点都可以触发 memory folding，比如：

- 完成一个子任务后，需要整理当前进展。
- 多次尝试失败后，意识到当前探索路径可能错了。
- 工具调用历史过长，需要压缩。
- 准备进入下一阶段，需要保留关键状态但丢弃噪声。

触发方式是模型生成特殊标记：

```text
<fold_thought>
```

系统检测到这个标记后，调用辅助 LLM 读取之前的完整交互历史，并行生成三类结构化记忆：

```text
(episodic_memory, working_memory, tool_memory) = compress(interaction_history)
```

随后，这三类 memory 会替换原始交互历史，让主 reasoning model 在一个更短、更干净、更结构化的上下文中继续执行任务。

## 三类 Memory 的分工

### 1. Episodic Memory：长期任务进展

负责记录高层级任务轨迹，类似“这趟任务到目前为止发生了什么”。

主要保留：

- 总任务描述。
- 关键事件。
- 关键决策点。
- 子任务完成情况。
- 每个关键步骤的结果和影响。
- 当前整体进展。

它解决的是长任务中的全局连续性问题，让 agent 不会忘记已经完成了哪些阶段、为什么走到当前状态。

### 2. Working Memory：当前局部状态

负责记录眼前最重要的状态，类似“我现在正在做什么，卡在哪里，下一步准备怎么走”。

主要保留：

- 当前 immediate goal。
- 当前遇到的挑战或障碍。
- 下一步具体行动。

这是 memory folding 后继续推理最关键的部分。因为折叠历史以后，模型需要靠 working memory 维持推理连续性，避免“压缩后断片”。

### 3. Tool Memory：工具使用经验

负责沉淀工具相关经验，类似“哪些工具试过、怎么调用、效果如何、有什么坑”。

主要保留：

- 已使用工具名称。
- 成功率或效果判断。
- 有效参数。
- 常见错误。
- 返回结果模式。
- 成功和失败经验。
- 可复用规则，例如某种条件下优先用哪个工具。

这点是 DeepAgent memory 设计里很有价值的部分。它没有只总结任务事实，而是单独抽出 tool memory，让 agent 在开放工具集环境里能逐步形成工具选择和调用策略，减少重复试错。

## JSON Schema 的意义

论文强调 folded memory 不是自由文本摘要，而是固定 JSON schema。这样做有两个直接收益：

1. **结构稳定**：主模型可以稳定解析和使用，不容易被长段自然语言摘要淹没。
2. **减少关键信息丢失**：schema 强制保留任务进展、当前目标、工具经验等字段，降低压缩时漏掉关键细节的概率。

附录 C 中给出的 schema 大致如下。

Episodic memory：

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

Working memory：

```json
{
  "immediate_goal": "...",
  "current_challenges": "...",
  "next_actions": [
    {
      "type": "tool_call or planning or decision",
      "description": "..."
    }
  ]
}
```

Tool memory：

```json
{
  "tools_used": [
    {
      "tool_name": "...",
      "success_rate": "float",
      "effective_parameters": ["..."],
      "common_errors": ["..."],
      "response_pattern": "...",
      "experience": "..."
    }
  ],
  "derived_rules": [
    "When X condition occurs, prefer tool Y"
  ]
}
```

## 亮点

1. **把 memory 做成 agent 自主动作**

   Memory folding 不是外部系统定时摘要，而是 agent 在推理流中自己决定何时触发。这让 memory 成为策略的一部分：模型不仅决定做什么工具调用，也决定什么时候该整理、反思、重启。

2. **压缩历史的同时支持重新规划**

   论文反复强调 “take a breath”。这说明 memory folding 的目标不只是省 token，更是让模型摆脱局部错误路径，重新审视任务状态。

3. **三层记忆结构贴合长任务需求**

   Episodic memory 管全局进度，working memory 管当前连续性，tool memory 管工具经验。三者分别对应长任务 agent 中最容易丢失的三类信息。

4. **单独设计 Tool Memory**

   在开放工具集场景里，工具使用本身就是任务的一部分。把工具调用经验单独结构化，可以帮助 agent 避免重复调用无效工具，也能复用有效参数和错误处理经验。

5. **结构化 JSON 比自然语言摘要更可控**

   固定 schema 让压缩结果更稳定，也方便后续程序校验、裁剪、拼接和注入上下文。

6. **主模型和辅助模型分工明确**

   主 reasoning model 负责高层推理和决策；辅助 LLM 负责压缩冗长历史、整理工具文档和工具返回结果。这降低了主模型上下文负担，也让系统更工程化。

## 实现思路

可以按下面的方式落地：

1. **在 agent action space 中加入 fold action**

   让主模型可以输出类似 `<fold_thought>` 的控制标记。运行时 parser 检测到该标记后暂停主推理，进入 memory folding 流程。

2. **保存完整 interaction history**

   history 至少包括：

   - user task。
   - reasoning steps。
   - tool search query 和返回工具。
   - tool call 参数。
   - tool call result。
   - 错误、失败、重试信息。

3. **调用辅助 LLM 做结构化压缩**

   给辅助 LLM 一个严格 schema，让它分别生成 episodic、working、tool 三份 JSON。可以一次生成，也可以并行生成三份，论文中是并行生成。

4. **做 schema 校验和修复**

   工程上建议对 JSON 做校验。如果字段缺失或类型错误，可以自动修复或重新请求辅助 LLM。否则 memory 一旦格式漂移，后续主模型会很难稳定使用。

5. **用 folded memory 替换原始历史**

   新上下文可以组织成：

   ```text
   User Task
   Folded Episodic Memory
   Folded Working Memory
   Folded Tool Memory
   Current Instruction
   Continue reasoning...
   ```

   原始冗长历史不再完整放入主模型上下文，只保留压缩后的结构化状态。

6. **给主模型明确使用规则**

   例如：

   - 先读 working memory 判断当前子目标。
   - 查 tool memory 避免重复调用失败工具。
   - 用 episodic memory 保持全局任务方向。
   - 如果遇到新阶段或错误路径，可以再次触发 fold。

7. **控制触发时机**

   可以让模型自主触发，也可以加系统级保护条件，例如：

   - history token 超过阈值。
   - 连续 N 次工具调用失败。
   - 完成一个明确子目标。
   - 工具返回过长。
   - 当前 plan 明显变化。

## 实验效果

论文在消融实验中报告，去掉 memory folding 后性能明显下降：

| 方法 | ToolBench | ToolHop | WebShop | GAIA | 平均 |
| --- | ---: | ---: | ---: | ---: | ---: |
| DeepAgent-32B-RL | 64.0 | 40.6 | 34.4 | 53.3 | 48.1 |
| w/o Memory Folding | 63.0 | 36.6 | 32.4 | 44.7 | 44.2 |

最明显的是 GAIA，从 53.3 降到 44.7。GAIA 属于长链路、多步骤、需要工具协作的任务，这说明 memory folding 对长程交互稳定性很关键。

## 对我们实现 Agent Memory 的启发

1. 不要只做“聊天历史摘要”，而要围绕 agent 执行过程设计 memory schema。
2. memory 至少应区分：任务进展、当前状态、工具经验。
3. memory folding 应该支持主动触发，而不是只在上下文满了以后被动压缩。
4. 折叠后的 memory 应该能直接指导下一步行动，而不是只供人类阅读。
5. 工具型 agent 尤其需要 tool memory，因为工具调用错误和参数经验是长任务成功率的关键。
6. memory 生成后要做结构校验，否则 JSON schema 的优势会被格式漂移抵消。
7. 触发过早会丢细节，触发过晚会让错误路径和 token 压力继续累积，最好结合模型自主判断和系统阈值。

## 可以复用的最小工程方案

如果要在现有 agent 框架里快速实现一个简化版，可以这样做：

```text
主模型推理中允许输出 <fold_thought>
        |
        v
运行时拦截该 token
        |
        v
读取完整 interaction history
        |
        v
辅助 LLM 按固定 JSON schema 生成三类 memory
        |
        v
校验 JSON，必要时修复
        |
        v
用 folded memory 替换旧 history
        |
        v
主模型继续推理、搜索工具、调用工具
```

最小 schema 可以保留为：

```json
{
  "episodic_memory": {
    "task_description": "",
    "key_events": [],
    "current_progress": ""
  },
  "working_memory": {
    "immediate_goal": "",
    "current_challenges": "",
    "next_actions": []
  },
  "tool_memory": {
    "tools_used": [],
    "derived_rules": []
  }
}
```

## 潜在风险

1. **压缩损失**：辅助 LLM 如果漏掉关键观察，后续推理会建立在错误状态上。
2. **错误记忆固化**：如果 folded memory 把错误结论写得很确定，agent 可能更难纠偏。
3. **触发策略难调**：太频繁会增加延迟和丢细节，太少则无法解决长历史问题。
4. **工具经验可能过时**：某次工具失败可能是参数问题、环境问题或临时异常，不应简单固化成“工具不可用”。
5. **schema 需要随业务演化**：不同 agent 的关键状态不同，不能完全照搬论文 schema，需要根据任务域补充字段。

## 总结

DeepAgent 的 memory 设计最值得借鉴的是：它把 memory 从“被动压缩上下文”提升成了“agent 自主调度的认知动作”。通过 episodic、working、tool 三类结构化记忆，模型既能保留长任务的全局进展，又能维持当前行动连续性，还能复用工具调用经验。对于需要长链路、多工具、开放环境探索的 agent，这种 memory folding 比简单历史摘要更稳定，也更接近可工程化落地的方案。
