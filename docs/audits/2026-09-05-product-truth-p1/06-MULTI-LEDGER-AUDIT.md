# 06 — MULTI-LEDGER AUDIT (P1 AUDIT, 2026-09-05)

> 主动寻找多账本问题 (类似 P0 发现)

---

## 1. 每对象账本清单

| Object | JSON/MD | SQLite | Event | Session | WebUI | 判定 |
|---|---|---|---|---|---|---|
| Idea | product/ideas.json (PI-*, 2) | — | product.* | — | 可显示 | **单账本** (S9) — 但主链不用 |
| Discovery | discovery/conversation.json + product-definition.md (0) | — | DISCOVERY_* (learning_engine_v2/service) | discovery 会话 | 状态显示 | **2 类**: 域文件 (0) + event 观察 — domain 非 SSOT (无真实数据); event 非事实 |
| Requirement | requirements/requirements.json (req_*, 7) | — | (无专门) | session ctx.requirement_id | 可显示 | **单账本** — 内联, 非 domain |
| PRD | projects/*/PRD.md (6) | — | (无) | — | has('PRD.md') | **单账本** — 纯文件 |
| Plan | session_plans.json (16, session keyed) | — | PLAN-* 引用 | console_sessions + session_topics 也存 PLAN-* | 显示 plan 卡片 | **3 处存 PLAN-***: session_plans / session_topics / console_sessions (同一 dict 快照多写?) — **投影重复**, 无 canonical plan ledger |
| Task | backlog task.json (TASK-*) | factory.db mirror | TASK_CREATED | session 显示 | API 投影 | **canonical 单账本** (P0) — db 是 mirror |

## 2. 分类

| Object | Canonical | Projection | Orchestration | Legacy | Unknown |
|---|---|---|---|---|---|
| Idea | product/ideas.json (S9) | — | — | — | 主链脱节 |
| Discovery | (实现无数据) | product-definition.md (doc) | DISCOVERY events | — | — |
| Requirement | requirements.json (内联) | — | session ctx | — | 无 class |
| PRD | — | PRD.md (doc) | — | M3 规则生成 | — |
| Plan | — | — | session_plans (编排) | PLAN-* 3 处快照 | — |
| Task | backlog (P0) | API/WebUI | session | — | — |

## 3. 结论

- **无两个都自称 canonical 的 Product ledger** (无 P0)
- Plan 状态 3 处快照 (session_plans/session_topics/console_sessions) = 编排投影
  多写 — 缺 canonical plan entity (P1)
- Requirement/PRD 无 domain class (P1)
- PLAN-* 出现在 session_topics (sess-81d29078b5 内) — 需确认是否同 plan 实体
  多存储或不同 plan
