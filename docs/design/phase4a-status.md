# AI Software Factory — Phase 4A: Workflow Engine

> 日期: 2026-08-05
> 前置: Phase 1-3B (ceb5f40/f4e96f3/b213a14/1590c57, 335 tests)
> 目标: Workflow Engine — AI Factory 流程控制层

## 范围

- factory-core/workflows/ (models/engine/store/definitions)
- Workflow Model + WorkflowStep (required_skill/required_role)
- 状态机: Workflow CREATED/RUNNING/COMPLETED/FAILED; Step PENDING/RUNNING/COMPLETED/FAILED; 禁止非法转换
- WorkflowEngine (create/start/start_step/complete_step/fail_workflow)
- Task 集成: task.workflow 关联 (不自动分配/执行)
- Event 集成: workflow.* 六类事件 (含 workflow_id/task_id/step_id/result)
- JSON 持久化 (.factory/workflows/workflows.json, 原子写)
- CLI: workflow list/add/run/status
- 测试: 新增 ≥50, 335 不回归

## 禁止 (后续 Phase)

Agent Runtime / 自动调度 / Hermes 调用 / 代码执行 / 测试执行 / Checkpoint Recovery / Dashboard

## 约束

- 不修改 Event/Task/Validation/Agent/Skill API
- 单进程本地 JSON 持久化, 可审计 Event Flow
- 设计冲突 → 记录 ADR
