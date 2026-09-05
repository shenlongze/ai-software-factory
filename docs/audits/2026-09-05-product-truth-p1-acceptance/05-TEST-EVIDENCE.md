# 05 — TEST EVIDENCE (P1 FINAL ACCEPTANCE, 2026-09-05)

> 测试证据 — 分类汇报

---

## 1. P1 测试

test_p1_product_truth.py 15/15 PASS:
- Identity (test_ids_unique_prefix / test_store_isolation_from_legacy)
- Lifecycle (idea/requirement/prd_versioning/plan_immutable)
- FK/Trace (forward / reverse_from_task / reverse_no_plan_legacy)
- Idempotency (idea_key / discovery_per_idea / transition / no_duplicate_chain)
- PRD boundary (test_prd_truth_not_document)
- Legacy (test_legacy_stores_untouched)

## 2. P0 回归

F1 16 + F2 8 + F3 17 + F4 14 = 55/55 PASS (fresh)

## 3. Combined

70/70 (P1 + F1-F4) PASS
核心相关套件: 2534 passed, 4 failed (workflow_start 4)

## 4. Attribution

4 failed (test_console_s10_workflow_start) = stash 对照决定性预存
(P1 前后 4=4 零差异) → **P1-attributable = 0**
其它预存 (agent_loop 11 / s10 系 22 / console_cli 15 / console_events 3) 同前证。

**不称 2534+4 "all green"** — 4 为预存失败, 已分离归因。

## 5. E2E 4/4 (fresh 复跑 2026-09-05)

| Case | Input | Canonical IDs | 结果 |
|---|---|---|---|
| E2E-1 | user-intent → idea | IDEA→DISC→REQ→PRD@v2→PLAN→TASK→run→EXS→art→ver→EVD + reverse trace | PASS |
| E2E-2 | pytest fail project | EXS SUCCESS + ver FAIL | PASS |
| E2E-3 | duplicate create | idempotent 单 canonical | PASS |
| E2E-4 | recovery | 新 TaskRun; Product 单套 | PASS |

证据: /tmp/p1_e2e.py (隔离 tmp, 真实 service)
