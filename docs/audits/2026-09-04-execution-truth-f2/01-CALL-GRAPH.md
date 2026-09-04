# 01 — CALL GRAPH (P0-F2, 2026-09-04)

> F2 后的完成传播链 — EXS → TaskRun → Task

---

## 1. 真实生产链 (F2 后)

```
Task(TASK-*)  backlog task.json
  │
  ▼
run-*(NodeRun)  nodes/runs/*.json          ← _chain_task_run (F1): task_id 锚, PENDING
  │
  ▼ 真实外部执行 (gateway_execute → executor.run: hermes/codex/claude subprocess)
EXS-*  exec/execution_records.json         ← record_invocation (F1): task_id/task_run_id 锚
  │ result=success/failed (写入即终态)
  │
  ▼ finalize_node_run (F2 新增)
COMPLETED/FAILED                            ← run 终态 (合法转换, 零二次执行)
  │
  ▼ finish_task_exec (幂等, 八态)
done/failed/cancelled                       ← Task 终态 (exec_ref=EXS)
```

## 2. 关键函数与行号

| 函数 | 位置 | 职责 |
|---|---|---|
| _chain_task_run | agent_loop.py (F1) | 建 TaskRun 锚 (共享 Node "task-execution" + create_node_run) |
| finalize_node_run | node_runtime.py:251 (F2) | 吸收外部结果 → TaskRun 终态 (幂等/零执行) |
| gateway_execute | external_executor/gateway.py | 委派 + EXS 记录 + TASK-GW 控制面 |
| finish_task_exec | service.py:4469 | backlog Task 回写 (八态合法路径, 幂等) |
| _run_status (recover) | agent_loop.py (F2) | NodeRun→EXS→TASK-GW 三级证据 |

## 3. 断点 (F2 后)

| 原断点 | F2 处理 | 状态 |
|---|---|---|
| NodeRun 永不 finalize | finalize_node_run (两处 _exec_fn 调用) | ✅ 闭合 |
| 失败 exec_ref 丢失 | _exec_fn 失败路径回传 _exs | ✅ 闭合 |
| recover 按 TASK-GW 查 EXS miss | NodeRun→EXS→TASK-GW 三级 | ✅ 闭合 |
| session_exec 收敛 | 留 F2 边界外 (真实执行已收敛; E2E 历史不动) | ⏳ 用户决策 |
