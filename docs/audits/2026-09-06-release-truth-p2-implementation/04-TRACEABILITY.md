# 04 — TRACEABILITY (P2-A IMPL, 2026-09-06)

## reverse (RELEASE → IDEA) — 真实 E2E-1 全 FK

RELEASE-f34b0729 → exs → task_run → artifact → verification → evidence
→ TASK-6278e6a2 → PLAN-93eb1cf5 → PRD-d6dc0878@v → REQ-d5a9fff6
→ DISC-f099e5f6 → IDEA-4c4a9d85

- P0 段: release 字段直连 (exs/run/art/ver/evd)
- Product 段: task→plan→prd→req→disc→idea 复用 P1 product_truth.reverse_trace
- 纯 FK; 无 filename/session/audit 推断
