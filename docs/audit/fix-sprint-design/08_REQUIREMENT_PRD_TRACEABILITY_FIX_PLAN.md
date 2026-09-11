# 08 — REQUIREMENT / PRD TRACEABILITY FIX PLAN (STEP11)

## 目标语义 (D-4 C→A→B, INV-010)
```
Requirement (req_*) → Product Intent/PRD (未来 prd_*) → Plan (PLAN-*) → Task (TASK-*)
```

## 当前
- requirements.json 7 条 (SSOT 真实) — capture/validate ✅
- 无 version/change/下游引用

## C 阶段 Fix (FX-03, 当前可做)
- plan (session_plans) 增加 requirement_id 只读引用 (来源 req)
- 需求捕获时保留 id (已存在 req_*)
- 不跳过 PRD 位置: 引用语义设计为 requirement_id → [Product Intent/PRD] → plan 链上的一环,
  而非 requirement_id 直接语义化替换 PRD

## M3 后 (C→A→B)
- PRD 实体 (prd_*, 独立 Domain, 版本+审批) → PRD 持有 requirement_id, Plan 引用 prd_id
- 本 STEP11 不实现

## 验收 (C 阶段)
- 从 Plan 可回溯 requirement_id → requirements.json 原始需求
- requirements.json 无 schema 破坏
- 未来加 PRD 层不改变 C 阶段引用语义
