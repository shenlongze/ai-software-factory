# 05 — RELEASE TRACEABILITY (P2-A CONTRACT, 2026-09-06)

## 1. 双向 trace (纯 FK)

### Reverse (Release → Idea)
```
RELEASE-*
  → verification_ids[] → ver-* → artifact_ids[] → art-*
  → exs_id → EXS-* → task_run_id → run-* → task_id → TASK-*
  → plan_id → PLAN-* → prd_id → PRD-*@v → requirement_ids[] → REQ-*
  → discovery_id → DISC-* → idea_id → IDEA-*
```

### Forward (Idea → Release)
```
IDEA-*→DISC-*→REQ-*→PRD-*→PLAN-*→TASK-*→run-*→EXS-*→art-*→ver-*→EVD-*
  → RELEASE-*
```

## 2. 查询实现 (Implementation 期)

- release_store 存 FK 数组 (task_run_id/exs_id/artifact_ids/verification_ids/
  evidence_ids) — 直接 join
- task→plan→… 复用 P1 product_truth.reverse_trace (只读)
- 禁止: filename/session/git message/audit 推断

## 3. 状态

CONTRACT-ONLY (Implementation 后 REAL) — 契约已定义, FK 路径与 P0/P1
store 全通 (字段存在, 只待 release 写)。
