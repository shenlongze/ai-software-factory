# 02 — IDENTITY MODEL (P1 AUDIT, 2026-09-05)

> Product 对象 Identity 现状 — 不猜, 实测

---

## 1. Identity Graph

| Object | ID | Store | Writer | Parent FK | Child FK | Domain? |
|---|---|---|---|---|---|---|
| Idea | PI-{3-digit} | product/ideas.json (2 条) | product service (S9) | (无) | approval artifact | 是 (S9 product 域) — 但与主链脱节 |
| Discovery | (无独立 id) | discovery/conversation.json + product-definition.md | service.complete_discovery | project_id (org) | (无) | 实现存在 / 0 真实数据 / 无独立 entity id |
| Requirement | req_{hex12} | requirements/requirements.json (7) | agent_loop:859-877 (内联) | session_id / project_id | (无 PRD FK) | **否** (无 class) |
| PRD | (无 id) | projects/{slug}/PRD.md (6) | actions.generate_prd (规则 doc) | (无 — 不关联 req/plan) | (无) | **否** (纯 markdown) |
| Plan | (session keyed) | session_plans.json (16) | fastapi_adapter:7438 (Web) + chain_start | session_id; 4/16 req_id | → Task plan_id (PLAN-*) | **否** (编排状态; PLAN-* 存 console_sessions/session_topics) |
| Task | TASK-* | backlog task.json (156+53+…) | service.create_task | plan_id (部分) | exec_ref (P0) | 是 (P0 M4) |

## 2. 关键缺口

- Discovery/PRD/Plan 无独立 canonical entity id (Plan 的 PLAN-* 是 Web 层临时生成,
  非 domain ledger 主键)
- Requirement 无 class (内联 dict)
- Idea (PI-*) 与 Requirement (req_*) **两套 id 体系不互通**

## 3. 无 P0 ID 冲突

无同一 ID 在不同 domain 表示不同事实 (req_* vs PI-* vs PLAN-* 前缀各异) —
但结构性断链 (P1)。
