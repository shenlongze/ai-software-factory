# 02 — STATE OWNERSHIP (P0-F2, 2026-09-04)

> 状态所有权矩阵 — 一个状态只能有一个 canonical owner

---

## 1. Ownership Matrix (F2 后)

| 状态 | Canonical Owner | Producer | Consumer | F2 证据 |
|---|---|---|---|---|
| Task 八态 (todo/ready/in_progress/review/done/blocked/failed/cancelled) | ManagementStore.transition_task | service.create_task/start_task_exec/finish_task_exec | UI/API/chain | 唯一 (F1/F2 未改) |
| TaskRun 状态 (PENDING/RUNNING/VERIFYING/COMPLETED/FAILED) | node_runtime (NodeRun) | create_node_run + finalize_node_run / execute_node_run | recovery/governance | ✅ F2 收敛 |
| External execution result (EXS) | record_invocation (gateway) | gateway_execute | T-9 溯源/监控 | 唯一 (写入即终态) |
| Orchestration transient (session_exec) | ExecState | chain_start/next | chain_next/recover | 非 canonical (不持真相) |
| Audit fact | audit_events.json | AuditEvent.create (node_runtime/service) | audit API | 观察层 (非 state owner) |
| Legacy execution | legacy stores (EXR/TASK-GW/task-e1-*) | 旧代码 | 只读 | 隔离 |

## 2. 禁止事项确认

- session_exec ≠ TaskRun (exec_state.py 未改其语义; 仍为会话编排状态)
- EXS ≠ TaskRun (finalize 在 node_runtime; EXS 是结果记录)
- 无第二套 TaskRun / run identity (复用 NodeRun)
- audit 不推断状态 (state change → audit event, 非反向)

## 3. Contract Violations (F2 后扫描)

| # | 潜在冲突 | 判定 |
|---|---|---|
| V-1 | execute_node_run (workflow) vs finalize_node_run (chain) 双路径 | 不冲突: workflow 路径执行+finalize 一体; chain 路径外部已执行, finalize 只吸收。两路径均经 NODERUN_TRANSITIONS 合法转换 |
| V-2 | recover 查 NodeRun/EXS/TASK-GW | NodeRun canonical 优先, EXS 次, TASK-GW legacy 兜底 — 无多 owner 写 |
| V-3 | finish_task_exec 直接改 Task 状态 | 经 transition_task (org.management) 唯一合法写 — 保持 |
