# Context Budget (S35)

> 日期: 2026-08-29 | 冻结于 S35

## 1. Budget 默认值 (冻结)
```
max_input_tokens: 8192      (总输入上限)
max_memory_tokens: 2048     (Memory 来源上限)
max_artifact_tokens: 2048   (Artifact 来源上限)
max_history_tokens: 1024    (历史来源上限)
max_tool_tokens: 1024       (工具上下文上限)
max_output_tokens: 2048     (输出上限)
max_total_cost: 0.01        (估算成本上限 USD)
```

## 2. 预算执行 (冻结)
```
Resolver 每候选累计 token; 超来源预算 → 该来源停止检索;
超总预算 → ContextDecision = BUDGET_EXCEEDED (REJECT 或 RANK→TRUNCATE→COMPRESS)
```

## 3. Cost 记账 (冻结)
```
requested_tokens / selected_tokens / compressed_tokens / rejected_tokens / estimated_cost
无真实 token 数 → 用字符/4 估算, 明确标记 estimated (不伪装真实成本)
```

## 4. 不变量
- Resolver 永远不能无限读取 Context
- 历史 Snapshot 不受后续 Memory 变化影响
