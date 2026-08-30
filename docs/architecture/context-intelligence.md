# Context Intelligence — Contract (S36)

> 日期: 2026-08-29 | 冻结于 S36

## 1. ContextUtility Contract (冻结)
```
score = w1*relevance + w2*evidence_strength + w3*freshness + w4*confidence
        + w5*scope_match - w6*token_cost
权重 (冻结): relevance=0.4, evidence=0.25, freshness=0.15, confidence=0.1, scope=0.1, cost_penalty=0.05
目标: Maximize useful information per token (非 max context)
```

## 2. Budget-aware Selection (冻结)
```
候选按 utility desc 排序 → 累计 token 至 budget 上限 → 选最优组合
(候选 A=3000+B=1000 且 budget=4000 → 选 A+B, 非全读)
溢出 → REJECTED (记录 rejected_tokens)
```

## 3. Progressive Context (冻结)
```
Initial Context → Execute → Context insufficient → Additional ContextRequest
→ Policy → Budget Remaining → Retrieve → Continue
总 ContextCost <= Budget; 所有追加进入 ContextSnapshot + Audit
```

## 4. ContextFeedback (冻结)
```
feedback_id / context_snapshot_id / node_run_id / selected_context /
execution_result(PASS|FAIL) / verification_result / usefulness(USEFUL|NOT_USEFUL|UNKNOWN)
无法证明 → UNKNOWN (不伪造)
```

## 5. Context Efficiency Metrics (冻结)
```
context_tokens_per_node_run / context_cost_per_successful_run /
retrieval_hit_rate / context_rejection_rate / context_budget_exhaustion_rate
无法真实计算 → 不实现伪指标
```

## 6. ContextStrategy Plugin (冻结)
```
rank 策略 plugin 化 (type=strategy): 替换不修改 Core
Core 管: Permission/Policy/Budget/Governance/Lineage/Audit
Plugin 管: Ranking/Compression/Optimization
```
