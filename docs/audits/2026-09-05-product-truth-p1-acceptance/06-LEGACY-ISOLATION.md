# 06 — LEGACY ISOLATION (P1 FINAL ACCEPTANCE, 2026-09-05)

---

## 1. Legacy 保持隔离 (零迁移/零回填/零重建)

| Legacy | 状态 | 证据 |
|---|---|---|
| PI-* (S9 ideas 2 条) | 未触碰 | product/ideas.json 未被 product_truth 读写 |
| req_{hex12} (7 条) | 保留 (legacy API 仍投影) | requirements/requirements.json 未迁移; 新 REQ-* 独立 |
| 旧 PLAN-* 快照 | 保留 (orchestration) | session_plans.json 未迁移; 新 plans store 独立 |
| 历史 PRD.md (6) | 保留 (legacy doc) | 未转 PRD-* |
| 历史 TASK-* 无 provenance (156) | 保留 | reverse_trace 诚实断链; 无合成 plan_id |
| DISCOVERY_CONFIRMED events | 保留 (观察) | 未重建 DISC-* |

## 2. 无 silent relabel

- product_truth store 全新 (product_truth/*.json), 无旧数据复制
- 旧数据继续由旧 reader 读取 (fastapi M3 投影) — 未标 canonical
- 新链只写新 canonical (测试 test_legacy_stores_untouched: P1 操作不创建
  legacy store)

**PASS — Legacy 完全隔离**
