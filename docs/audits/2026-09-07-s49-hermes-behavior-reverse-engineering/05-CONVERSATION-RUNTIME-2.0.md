# 05 — CONVERSATION RUNTIME 2.0 (候选, 不实现)

## 设计原则 (从 Hermes 行为归纳, 非模板)
- LLM 是理解/推理/合成引擎 — 给它完整事实 + 一致指令, 少做中间判定
- 状态显式化只在"跨轮可靠"需要处 (生产 gate/阶段) — 会话语义不叠层
- 已查事实 = 对话资产, 永不因截断丢失 (引用 > 重查)

## 候选架构 (单通道, 少层)
```
User Message
   ↓
① Context Window (最近 N=8 轮全量含工具结果; 超长智能摘要保事实)
   + ConvState (topic/active_work/stage — 轻, 作提示头)
   ↓
② Single LLM Decision (一次推理):
   - 用户这句是什么 (要结论/继续/深化/提问/反馈/新目标 — LLM 判)
   - 已有事实够吗 (历史/上轮结果)
   - 本轮动作: ANSWER | ANSWER+1工具 | EXECUTE(经gate) | ASK
   ↓
③ 动作执行 (工具/写经 Lifecycle Gate + authorization)
   ↓
④ Evidence → Synthesis (工具结果回上下文)
   ↓
⑤ Answer (先结论/答用户 → 证据 → 不确定性 → 下一步一句话)
   ↓
⑥ ConvState 更新 (topic/active_work/stage/last_fact_refs)
   ↓
下一轮
```

## 与现状差异 (最小迁移路径)
1. run_agent_native 上下文: 4 轮扁平 → 8 轮含工具结果 (最大单项收益)
2. 引导降噪: 执行/综合指令一条贴 user; 其余 system 合并精简
3. 追问轮: 检测"上轮有工具结果 + 用户短追问/要结论" → 注入
   "直接用上轮结果回答, 0 工具" (修轮2 型重查)
4. 每轮答案结构: 结论先行 (修无结论循环)
5. gate/authorization/exec_state 全部保留不动 (生产正确性层)
6. Governor 语义表保留但输出只做 (a) 轻提示头 (b) 冲突时裁决,
   不再注入多段互相竞争的 system 块

## 判断
AF 缺的不是"另一个 Conversation Runtime 组件", 而是:
- 上下文完整性 (系统)
- 提示组织纪律 (单指令/少冲突) (系统)
- 回答合成约束 (结论先行/禁空转) (系统+prompt)
- 已查事实复用约束 (系统)
LLM intrinsic 能力两边相同 — 差异在把这些喂给 LLM 的方式。
