# AI Software Factory — Phase 4C-3: Checkpoint Recovery

> 日期: 2026-08-06
> 前置: Phase 1-4C-2 (981 tests)
> 目标: 执行中断恢复 — Event Log 是恢复来源

## 范围

- factory-core/recovery/ (models/checkpoint/replay/service)
- Checkpoint Model (id/task_id/workflow_id/event_seq/workflow_state/current_step/agents/executions)
- EventReplay (读 EventStore 按 seq 回放 → 重建 Workflow/Step/Assignment/Execution 状态)
- RecoveryService (checkpoint/recover: load events → rebuild → compare → result)
- 恢复场景: RUNNING 中断继续 Step / Execution RUNNING 可重试 / Agent WORKING 释放 / 已完成拒绝
- CLI: checkpoint list / recover TASK_ID
- Event: recovery.started/completed/failed
- 测试: 新增 ≥60, 981 不回归

## 禁止

修改 Hermes / RuntimeAdapter / 数据库 / MQ / 分布式恢复

## 约束

单进程本地恢复, Event Audit, JSON persistence, 可测试
