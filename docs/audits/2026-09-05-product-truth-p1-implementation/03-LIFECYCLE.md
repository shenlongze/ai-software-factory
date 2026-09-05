# 03 — LIFECYCLE (P1 IMPL, 2026-09-05)

## 1. 受控转换

每域独立转换表 (product_truth.py _*_T): Idea/Discovery/Requirement/PRD/Plan。
非法转换 → ValueError; 同态转换 → 幂等返回。

## 2. 实现语义 vs 契约

- Discovery completed = product_defined (契约 D4; 允许 pending→completed 直接)
- Requirement validated→approved (真实 transition, 非硬编码 VALIDATED)
- PRD approve → 新 version (D7)
- Plan approve → immutable (无原地语义 update API; 修改 = 新 PLAN-*)

## 3. 测试

test_idea_lifecycle / test_requirement_lifecycle / test_prd_versioning /
test_plan_lifecycle_and_immutable
