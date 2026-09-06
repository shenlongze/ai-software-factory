# 05 — REAL DATA (P2-C FINAL ACCEPTANCE, 2026-09-06)

## memory/experience_store.json (canonical)
- 总记录: 84 (全 M3 legacy — AutoLearner 产物)
- exp-*: 84 | anchored (run/exs/release FK): 0 (零迁移零 backfill — 符合 C22)
- success: 54 | failure: 30
- P2-C 新 anchored exp: E2E 在隔离 tmp (未污染真实库) — 符合隔离纪律

## intelligence/experiences.json (LEGACY S9)
- 85 条 (独立域, 不混算)

## P2-D Contract dir 也在 working tree (untracked — 前阶段产物, 不属 P2-C commit)
