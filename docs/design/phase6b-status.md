# AI Software Factory — Phase 6B: Workspace Operations Dashboard

> 日期: 2026-08-06
> 前置: Phase 1-6A (1498 tests)
> 目标: Workspace 级运营视图 (多项目聚合展示)

## 范围

- factory dashboard --workspace (Workspace Summary: Projects/Tasks/Agents/Executions/Workflows/Runtime Usage/Metrics)
- factory metrics --workspace (project comparison)
- Agent Utilization View (跨项目 agent/projects/assignments/success_rate)
- Runtime Usage View (runtime/execution_count/success_rate)
- factory events --workspace (跨项目事件时间线)
- Dashboard Views 扩展
- Event: workspace.dashboard.viewed/metrics.viewed/events.viewed
- 测试: 新增 ≥70, 1498 不回归

## 禁止

修改 Task 核心流程 / Execution / Runtime / Metrics 核心计算 — 只做聚合展示
