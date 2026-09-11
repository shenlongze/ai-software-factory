# 01 — DOMAIN MODEL (P1 CONTRACT, 2026-09-05)

> D1: 六层 Product Domain Entity 判断

---

## 1. 逐对象判断 (代码 + 真实数据)

| Object | Domain Entity? | 现状 | 理由 |
|---|---|---|---|
| User Intent | **否 (输入事实)** | session title/message + intent.py 路由标签 | 是 conversation-derived input, 非持久 domain fact; 不应实体化 (INTENT-* 不必要) |
| Idea | **是** | 三语义并存: S9 ProductIdea (PI-*, product service) / Web create_feature idea (任务树) / M3 product.json | 需收敛为唯一 Idea entity (产品意图), 但当前三处多义 → 冻结唯一语义: 产品概念 (problem/user/platform), 非任务 feature |
| Discovery | **是** | complete_discovery 实现完整 (service:1598) 但 0 真实产物 | 领域事实 = discovery 会话收敛出的产品定义 (structured), 非 product-definition.md (投影) |
| Requirement | **是** | req_{hex12} 内联 dict (agent_loop:859) | 需 domain class + store + lifecycle |
| PRD | **是** | PRD.md 规则 doc (generate_prd) | PRD-* entity + version; PRD.md 降为 projection |
| Plan | **是** | session_plans (session keyed) + PLAN-* 3 处快照 | 需唯一 Plan entity/store/writer; session_plans 降为 orchestration state |
| Task | **是 (P0 冻结)** | TASK-* canonical | 保持不动 |

## 2. 冻结

六层 Product Domain: Idea / Discovery / Requirement / PRD / Plan / Task
(Task 由 P0 拥有, P1 只定义 Plan→Task 边界)。

## 3. 不强求实体化对象

- User Intent: 输入事实 (存于 session message; 经 intent 路由进入 domain 创建)
- session_plans / session_topics / console_sessions: orchestration state / projection
- PRD.md / product-definition.md: document projection
- DISCOVERY_CONFIRMED / product_defined: event / lifecycle 观察
