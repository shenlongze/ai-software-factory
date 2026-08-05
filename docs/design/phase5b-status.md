# AI Software Factory — Phase 5B: Metrics Intelligence Layer

> 日期: 2026-08-06
> 前置: Phase 1-5A.1 (1335 tests)
> 目标: 从事件和状态生成生产指标 (只读)

## 范围

- factory-core/metrics/ (models/collectors/calculators/reports/store)
- FactoryMetrics (tasks/executions/agents/workflows/validation/failures)
- 指标: Task total/completed/failed/success_rate; Execution total/success/failed/first_attempt_success_rate; Agent assignment_count/success_rate; Workflow run_count/success_rate; Validation pass_rate; Failure failure_reason_count
- CLI: factory metrics (--json)
- Dashboard Metrics View
- Event: metrics.viewed
- 测试: 新增 ≥60, 1335 不回归

## 禁止

AI 分析 / ML / 自动优化 / 修改任务/Agent 状态 — Metrics 只读
