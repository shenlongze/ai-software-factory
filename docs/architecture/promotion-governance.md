# Promotion Governance & Canary (S38)

> 日期: 2026-08-29 | 冻结于 S38

## 1. Governance Pipeline (冻结)
```
Evaluation → Risk Classification → Policy → Approval Mode:
  LOW + 充分 evidence → AUTO_APPROVE
  MEDIUM → REVIEW_REQUIRED (policy review)
  HIGH/CRITICAL → HUMAN_APPROVAL_REQUIRED (不可绕过)
```

## 2. Risk Classification (冻结)
```
risk = f(blast_radius, permission_scope, production_impact, capability_change)
LOW: 单 node scope, 无 production 影响
MEDIUM: workforce/project scope, 有限影响
HIGH: 跨 workforce / 生产能力改变 → Human Gate
CRITICAL: Core/全局 → Human Gate + Canary 强制
```

## 3. Canary Contract (冻结)
```
canary_id / promotion_candidate_id / scope / max_runs / max_cost / max_duration
canary_result: PASS (Canary > Baseline) | FAIL (Regression)
FAIL → ROLLBACK (复用 S21 rollback_service) 或 REJECT
Canary Evidence 进入 PromotionSnapshot
```

## 4. 安全不变量 (冻结)
```
Learning 不能直接修改 Production (一切经 Promotion Contract)
Evaluation 不能绕过 Governance (evidence 不足 → INCONCLUSIVE, 不 PASS)
High-risk 不能绕过 Human Approval
Experiment 不能超 budget (max_runs/max_cost/max_duration → STOP)
Historical Evidence immutable (Replay 不修改)
Rollback 复用 S21 (不建第二套)
```
