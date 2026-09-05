# 06 — PLAN CANONICALIZATION (P1 IMPL, 2026-09-05)

## 1. Canonical

PLAN-* + plans store (product_truth/plans.json) — 唯一 canonical Plan。
create_plan 幂等 (idempotency_key); approve_plan 受控。

## 2. 收敛 (不破坏 legacy)

- fastapi_adapter 生成计划: PendingPlanStore (session orchestration) 保留 +
  同步写 canonical PLAN-* (idempotency_key=session:plan)
- session_plans.json 数据未动 (legacy)

## 3. Immutable

无 update_plan 函数; approved/executing plan 语义不可原地改 (契约 D9/D11)。
