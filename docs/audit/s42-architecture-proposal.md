# S42 Architecture Proposal — Intelligence Strategy Kernel

> 日期: 2026-08-29 | 状态: CONTRACT FREEZE

## 1. IntelligenceStrategy Contract (冻结)
```
strategy_id / strategy_type(LEARNING|HEALING|OPTIMIZATION) / version /
capabilities[] / input_contract(payload schema) / output_contract(candidate schema) /
context_requirements / cost_budget / execution_policy / governance_policy / lifecycle
注册: S31 Plugin Kernel (type=strategy) — 唯一 Registry
```

## 2. Strategy Lifecycle (冻结)
复用 Plugin Lifecycle: DISCOVERED→REGISTERED→ENABLED→DISABLED→RETIRED (不建第二套)

## 3. Strategy Execution (冻结)
```
StrategyRequest (strategy_id/payload)
→ 经 Plugin Kernel 解析 (ENABLED + permission)
→ Adapter 执行 (Learning/Healing/Optimization 各自薄代理)
→ Candidate
→ Evaluation (S38 或 Learning [STOP])
→ Decision
→ StrategyExecutionEvidence (strategy/version/input/candidate/evaluation/governance/result/cost)
→ Evidence/Lineage/Audit
```

## 4. Shared Pipeline 验证 (冻结)
Candidate/Evaluation/Experiment/Governance/Canary/Promotion 只有一套 (S38)
Learning 例外: [STOP] 语义 (S37 设计, 不 Promotion)

## 5. 替换测试 (冻结)
learning.default→learning.v2 / healing.default→healing.alt / optimization.default→optimization.alt
Core 零修改; DISABLED → 拒绝

## 6. 治理 (冻结)
Strategy 不能 self-elevate / bypass governance / 直接改 Production / 改 Evidence history
Cost budget 强制 (estimated, NOT_AVAILABLE 诚实)
