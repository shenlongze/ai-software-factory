# 02 — STATE OWNERSHIP (P0-FINAL, 2026-09-04)

> 最终 ownership matrix — 无 competing canonical writer

---

## 1. Matrix

| Object | Canonical ID | Canonical Store | Writer | Not Canonical |
|---|---|---|---|---|
| Task | TASK-* | workspace/projects/*/management/backlog/task.json | service.create_task → ManagementStore; transition_task 唯一状态写 | T-*(execution_plan/M3) / task-chg-*(change_control) / task-e1-*(M3 legacy) / TASK-GW-*(adapter) |
| TaskRun | run-* (NodeRun) | nodes/runs/*.json | node_runtime.create_node_run / finalize_node_run / execute_node_run | WorkflowInstance / ProductionRun (prun-*) / R{ms}(workflow_runner) / RuntimeSession |
| EXS | EXS-* | exec/execution_records.json | record_invocation (gateway/executor) | EXR-*(exec 请求域) / TASK-GW-*(委派控制面) |
| session_exec | (会话编排状态) | session_exec/*.json | ExecState (chain_start/next/recover) | **不持有 domain truth** (backlog_id 引用副本, 不写 backlog) |
| Audit | audit_id | audit_events.json | AuditEvent.create (node_runtime/service/orchestrator) | **事件观察, 非 domain SSOT** |
| Legacy | EXR/TASK-GW/task-e1-*/历史 | 各自存储 | 旧代码 | 隔离, 不进入 canonical |

## 2. 竞争写者验证 (无)

- Task 状态: service.py 11 处 transition_task (create/start/finish/update 路径);
  org/execution.py 的 ExecutionEngine 门面 (transition_task_locked) 未被生产主链调用
  (grep: 仅 cli observability import) — 非竞争。
- exec_state.py: 直接改的是 session_exec 副本 (status running/done/failed 于副本内),
  不 import management / 不写 backlog; 最终经 finish_task_exec 单向同步。**副本 ≠ Task**。
- chain 两处 finalize (auto worker + chain_next) 写同一 NodeRun 文件 — 同一域,
  幂等, 非 competing writer。

## 3. 结论

不同对象不同层级 = 不同职责, 无两个对象同时拥有同一业务状态。
Task 终态唯一写者 = service; TaskRun 终态唯一写者 = node_runtime; EXS 唯一写者 = record_invocation。
