# 01 — DOMAIN IMPLEMENTATION (P1 IMPL, 2026-09-05)

## 1. 实现域 (factory-console/product_truth.py)

| Entity | ID | Store | Lifecycle | 唯一 writer |
|---|---|---|---|---|
| Idea | IDEA-{hex8} | product_truth/ideas.json | created→refined→validated→approved→rejected/archived | create_idea |
| Discovery | DISC-{hex8} | product_truth/discoveries.json | pending→completed (product_defined) | create_discovery / complete_discovery |
| Requirement | REQ-{hex8} | product_truth/requirements.json | draft→validated→approved→superseded/rejected | create_requirement |
| PRD | PRD-{hex8} | product_truth/prds.json (+versions) | draft→approved→superseded→archived | create_prd / approve_prd |
| Plan | PLAN-{hex8} | product_truth/plans.json | pending→approved→executing→completed→cancelled | create_plan / approve_plan |

## 2. 与 legacy 隔离

- store 在 product_truth/ (全新); 不写 product/ideas.json (PI-*), requirements.json
  (req_*), session_plans.json
- 测试 test_store_isolation_from_legacy 实证

## 3. 无 P0 修改

Task/run/EXS/art/ver/EVD 零代码改动。
