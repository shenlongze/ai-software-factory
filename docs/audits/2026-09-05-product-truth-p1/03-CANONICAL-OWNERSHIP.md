# 03 — CANONICAL OWNERSHIP (P1 AUDIT, 2026-09-05)

> 谁拥有 Product Truth 各段

---

## 1. Ownership 现状

| Object | Canonical Owner | 实际 Writer | 多 writer? |
|---|---|---|---|
| Idea | (S9 product 域 — 名义) | product service | 1 (但主链不用它) |
| Discovery | service.complete_discovery (实现) | 同上 | 1 (0 真实运行) |
| Requirement | (无) | agent_loop 内联 (859-877) | 1 (仅 session) — 无 domain owner |
| PRD | (无) | actions.generate_prd (规则) | 1 (仅 doc) — 无 domain owner |
| Plan | (无) | fastapi_adapter Web 层 + chain_start | **2** (Web 消息内联 + session 编排) |
| Task | ManagementStore (P0) | service.create_task | 1 (canonical, P0) |

## 2. Competing writer 分析

- **Plan**: fastapi_adapter:7438 (Web 消息 "制定计划" → plan_development → 存
  console_sessions/session_topics) vs agent_loop chain_start (plan 已在 context →
  create_task) — 两个写入上下文, 但都写"会话计划"非独立 plan ledger; 不构成
  双 canonical (无 canonical plan entity) — P1 (缺 owner)
- **Requirement/PRD**: 各 1 writer 但均非 domain (内联/规则) — 缺 canonical owner
- 无两套都自称 canonical 的 Product ledger (无 P0)

## 3. 结论

Product 链 (Idea→Plan) 无 canonical owner; Task 有 (P0)。P1: 需建 Product domain
ownership (Requirement/PRD/Plan entity + 唯一 writer)。
