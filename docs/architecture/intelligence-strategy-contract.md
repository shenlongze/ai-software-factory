# IntelligenceStrategy Contract (S42)

> 日期: 2026-08-29 | 冻结于 S42

## Contract
```
strategy_id / strategy_type(LEARNING|HEALING|OPTIMIZATION) / version /
capabilities[] / input_contract / output_contract / context_requirements /
cost_budget / execution_policy / governance_policy / lifecycle
```

## 执行模型
```
StrategyRequest → Resolution (Plugin Kernel: ENABLED+permission, 非 LLM)
→ Adapter 执行 → Candidate → Evaluation → Decision
→ StrategyExecutionEvidence (strategy/version/input/candidate/evaluation/result/cost)
→ Evidence/Lineage/Audit
```

## 成本
estimated_cost / actual_cost / budget / remaining / stop_reason
真实 billing 未具备 → NOT_AVAILABLE (诚实)
