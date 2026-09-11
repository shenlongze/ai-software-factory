# 04 — LIFECYCLE CONTRACT (P1 CONTRACT, 2026-09-05)

> D4: 各 Entity 生命周期 (不套同一状态机)

---

## 1. 冻结 Lifecycle (领域事实 vs workflow state)

| Entity | Lifecycle | 说明 |
|---|---|---|
| Idea | created → refined → validated → approved → rejected/archived | approved = 进入 Discovery 的门 |
| Discovery | pending → running → completed → product_defined | product_defined = 领域事实 (现状 lifecycle 已有: draft→discovery→product_defined→design→architecture→confirmed) |
| Requirement | draft → validated → approved → superseded → rejected | VALIDATED 是领域事实 (来自 Discovery); approved = 可生成 PRD |
| PRD | draft → approved → superseded → archived | approved = 可生成 Plan 的门; version 递增 |
| Plan | pending → approved → executing → completed → cancelled | approved = 可生成 Task 的门 (现状 ask_approval=true) |
| Task | P0 冻结 (todo→in_progress→done/failed…) | 不动 |

## 2. 审计现有字符串 (不得视为 canonical)

- DISCOVERY_CONFIRMED = event (非 domain state) — 观察
- product_defined = lifecycle 事实 (org ProjectState) — **保留为 Discovery 完成态**
- VALIDATED requirements = 无 transition 来源 (硬编码) — P1 需真实 transition
- product.json status (development) = M3 legacy, 不并入

## 3. 原则

- lifecycle 状态 = 领域事实 (持久化 + 受控转换 + 事件观察)
- 每段有独立门 (Idea→approved / PRD→approved / Plan→approved), 不套统一状态机
