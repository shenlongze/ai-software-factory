# 07 — TASK BOUNDARY (P1 IMPL, 2026-09-05)

## 1. P1→P0 边界

- TASK-* = P0 canonical, 零修改
- Plan→Task: svc.create_task(plan_id=PLAN-*) — E2E-1 真实 task.plan_id
- P1 不操作 run/EXS/art/ver/EVD (全部经 P0 已有路径)

## 2. Legacy 任务

历史无 plan_id 任务 (156) 保持; reverse_trace 诚实返回断链 (不 backfill)。
