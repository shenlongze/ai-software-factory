# 07 — REQUIREMENT → PRODUCT → EXECUTION CONTRACT (STEP 10, 2026-09-02)

## 未来完整语义 (冻结, 不因 PRD 未实现而设计死)
```
Requirement (req_*)
   ↓ requirement_id (引用契约, C 阶段)
Product Intent / PRD (prd_*, 独立 Domain Entity, 结构化承诺+版本+审批)
   ↓ prd_id
Plan (PLAN-*)
   ↓ plan_id
Task (TASK-*)
   ↓ task_id
Run (EXS-*/R*)
   ↓
Artifact / Verification
   ↓
Audit
```

## 当前允许 (C — 引用契约)
- Requirement capture 持续 (requirements.json)
- 冻结: 新增引用时使用 requirement_id, 保留 → Product Intent/PRD 演进空间 (INV-010)
- 禁止: 冻结成 "Requirement 永远直接等于 Plan"

## 禁止
- 跳过 PRD 语义位置直接 Req→Plan 作为唯一路径设计 (允许临时引用, 但保留 PRD 挂载点)
