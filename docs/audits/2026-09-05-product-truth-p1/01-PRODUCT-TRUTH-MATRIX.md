# 01 — PRODUCT TRUTH MATRIX (P1 AUDIT, 2026-09-05)

> Product Truth Graph — 每段状态

---

## 1. Product Truth Graph

```
User Intent (session message / title — 非 entity)
   │  PARTIAL (title/summary 仅文本, 无 intent entity; 78 sessions 无 product_intent)
   ▼
Idea (PI-*, product/ideas.json, 2 测试条 — S9 审批域)
   │  REAL (实体存在) 但 DISCONNECTED (不进主会话链)
   ▼
Discovery (service.complete_discovery 实现完整; 真实 0 产物; 27 项目零 product_defined)
   │  REAL 实现 / RUNTIME MISSING
   ▼
Requirement (req_{hex12} 内联落盘 7 条 VALIDATED; 无 domain class)
   │  REAL 数据 (session 内联) / 无 domain
   ▼
PRD (PRD.md × 6 — 规则 doc; 无 entity; 无 req 关联)
   │  LEGACY (M3 规则生成)
   ▼
Plan (session_plans.json 16 — session keyed 编排状态; 4 带 req_id; 无独立 plan ledger)
   │  ORCHESTRATION STATE
   ▼
Task (TASK-* — P0 canonical; 部分带 plan_id=PLAN-*)
   │  REAL (P0 M4)
   ▼
TaskRun → EXS → art → ver → EVD   [P0-F4 PASS, 本审计不重评]
```

## 2. 逐段标记

| 边 | 标记 | 证据 |
|---|---|---|
| User Intent → Idea | PARTIAL/UNKNOWN | session title 文本; PI-* 不由此产生 |
| Idea → Discovery | MISSING | 无 idea_id → discovery 代码 |
| Discovery → Requirement | MISSING | 无 conversation → req 链接 |
| Requirement → PRD | MISSING | PRD.md 无 requirement_id |
| PRD → Plan | MISSING | plan_development 不经 PRD |
| Plan → Task | DERIVED/REAL | chain_start plan→create_task (plan_id) |
| Task → TaskRun | REAL (P0) | 不重评 |
