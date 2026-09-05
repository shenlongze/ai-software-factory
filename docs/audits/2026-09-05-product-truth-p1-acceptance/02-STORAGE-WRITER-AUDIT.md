# 02 — STORAGE / WRITER AUDIT (P1 FINAL ACCEPTANCE, 2026-09-05)

> 每域 store/writer/read/path 全景 — 无竞争 canonical store

---

## 1. Canonical stores (product_truth/*.json)

| Entity | Store | Writer (唯一) | 外部调用者 | API | CLI |
|---|---|---|---|---|---|
| Idea | product_truth/ideas.json | create_idea | (无 — CLI/未来 API 经此) | (无新) | factory product idea |
| Discovery | product_truth/discoveries.json | create_discovery / complete_discovery | (无) | (无新) | factory product discovery |
| Requirement | product_truth/requirements.json | create_requirement / transition_requirement | agent_loop:885 (REQ-* 收敛, 幂等) | (无新) | factory product requirement |
| PRD | product_truth/prds.json (+versions) | create_prd / approve_prd | (无) | (无新) | factory product prd |
| Plan | product_truth/plans.json | create_plan / approve_plan | fastapi_adapter:7451 (PLAN-* 收敛, 幂等) | (无新) | factory product plan |

## 2. 无竞争 canonical store 证明

- product_truth store 文件仅被 product_truth.py 读写 (grep 外部直写零命中)
- 各域只有一个 store 文件 + 一个 writer 函数族
- legacy store 分离: product/ideas.json (PI-*), requirements/requirements.json
  (req_*), session_plans.json — product_truth 不读不写 (模块 docstring + 测试
  test_store_isolation_from_legacy / test_legacy_stores_untouched)

## 3. Read paths

- forward_trace / reverse_trace (FK join, 只读)
- list_*/get_* per domain
- CLI product/ptrace 读 canonical
- 旧 M3 API (fastapi 1554/1657) 读 legacy requirements/session_plans = legacy
  projection (见 07-FINDINGS F2)

## 4. Event path

product_truth 无 event emission (最小实现; domain→store 直接)。未用 event 作 SSOT。

**PASS — 每域唯一 canonical store + writer**
