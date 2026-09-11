# 05 — TRACEABILITY (P1 AUDIT, 2026-09-05)

> 真实数据抽样 — TASK 向上反查 / Idea 向下

---

## 1. 真实抽样 (2026-09-05)

### TASK-* 向上反查

抽样: ai-factory-self backlog 156 任务 (max 抽查 8), life-e2e 9 任务。

```
TASK-0106d614 (ai-factory-self): plan_id = 无
  → Plan: 无 (断 — 无 plan_id 可反查)
  → PRD: ai-factory-self/PRD.md 存在 (但无 FK, 无法证明该 task 来自该 PRD)
  → Requirement: 无
  → Discovery/Idea: 无

TASK-0b8a1612 (life-e2e): plan_id = PLAN-d84e51ba
  → Plan: PLAN-d84e51ba 存在于 session_topics/sess-81d29078b5.json +
          session_plans.json (sess-81d29078b5) + console_sessions
  → 该 session plan: requirement_id = 无 (查 sess-81d29078b5 非 4 个带 req 之一)
  → PRD: 无 FK
  → Requirement/Discovery/Idea: 无
```

### 带 requirement_id 的 plan (4/16) 向下

```
sess-c7ec7c5aad → req_d4256a957b4f → 该 session 的 plan 有 tasks (TASK 未直接验证)
```

### Requirement → PRD → Plan 反查

7 个 req_*: 无一个能向下连到 PRD (PRD.md 无 req 字段)。
4 个 plan 带 req_id 的: 无 PRD 中间层。

## 2. 统计

| 方向 | 结果 |
|---|---|
| forward Idea→…→Task | 断 (无 Idea→Discovery→Requirement→PRD→Plan 连续链) |
| reverse TASK→Plan | PARTIAL (带 plan_id 的任务可反查 session plan; ai-factory-self 全无 plan_id 不可反查) |
| reverse TASK→PRD | BROKEN (无 FK) |
| reverse TASK→Requirement | BROKEN (仅经 plan.requirement_id 偶达 — 4/16 plan) |
| reverse TASK→Discovery/Idea | BROKEN (无任何 FK) |
| broken links | 大量 (PRD↔req, discovery↔req, idea↔req) |

## 3. 结论

Traceability **PARTIAL-BROKEN**: 仅 TASK→Plan (部分) → (偶) Requirement 可反查;
PRD/Discovery/Idea 段全断。
