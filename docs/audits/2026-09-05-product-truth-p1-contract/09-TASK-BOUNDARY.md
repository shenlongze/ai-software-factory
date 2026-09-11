# 09 — TASK BOUNDARY (P1 CONTRACT, 2026-09-05)

> D10: Plan → TASK-* 边界 (P0 Task 不动)

---

## 1. 冻结

- TASK-* = P0 canonical Task, P1 不创建第二套
- Task 允许无 Plan 来源 (手动 create_task / 会话直接任务) — **合法** (现状
  ai-factory-self 156 任务零 plan_id 即此路径)
- Task 有 Plan 时: task.plan_id = PLAN-* (P0 已支持字段, chain_start:472 已有)
- P1 新链: Task provenance 经 plan_id → prd_id/requirement_id → discovery_id →
  idea_id 可反查

## 2. 现状区分

| 数据 | 分类 |
|---|---|
| ai-factory-self 156 任务 (0 plan_id) | LEGACY 历史任务 (手动/会话直建) — 不 backfill |
| life-e2e 9 任务 (plan_id) | CURRENT 新链样本 (plan 无 req_id — P1 补上游) |
| 未来 P1 链任务 | 全部带 plan_id → prd/req/discovery/idea FK |

## 3. Traceability 表达 (不迁移历史)

- 新 canonical 链: task.plan_id → plans store → prd/req → disc → idea
- 历史任务: 保持无 provenance; 标记 LEGACY (不伪造 FK)
- forward/reverse 查询 = P1 Implementation 的 domain 查询 (非 audit 反推)

## 4. P1→P0 唯一边界

```
Plan (P1) ──生成──→ TASK-* (P0 只接收 TASK-*)
```

P1 不得操作 run-*/EXS-*/art-*/ver-*/EVD-*; 不得建第二 Execution。
