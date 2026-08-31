# K4 Operational State Contract

> 日期: 2026-08-29

## Task 状态
PLANNED / READY / RUNNING / BLOCKED / WAITING_APPROVAL / FAILED / COMPLETED / CANCELLED
(映射: DRAFT→PLANNED, VALIDATED→READY, ACTIVE→RUNNING, 确定性)

## Agent 状态
ACTIVE / RUNNING / IDLE / SUSPENDED / FAILED / RETIRED

## "谁在工作" 依据 (非超时猜测)
- RUNNING: 有 RUNNING task 绑定 (task.agent_id/role)
- BLOCKED: 有 BLOCKED task
- WAITING: 有 READY/DRAFT task (waiting_dependency)
- IDLE: 无 eligible task (no_eligible_task) — 有原因, 有运营价值
