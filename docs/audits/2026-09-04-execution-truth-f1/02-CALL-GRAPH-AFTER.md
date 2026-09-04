# 02 — CALL GRAPH AFTER (P0-F1, 2026-09-04)

> F1 后的生产创建链 — Task → TaskRun → EXS

---

## 1. Web 生产主链 (chain, 8011)

```
POST /api/sessions/{id}/messages → run_agent_native (agent_loop.py)
  └─ dispatch("chain_start")                     agent_loop.py:1446 (post-F1 行号)
       ├─ service.create_task × N → backlog TASK-* (backlog_id 映射)
       └─ ExecState.start → session_exec/<sid>.json (ORCHESTRATION STATE — 不持执行真相)

  └─ dispatch("chain_next") / _chain_auto_worker
       └─ _exec_fn(task)                         agent_loop.py (×2: chain_next + auto worker)
            ├─ _chain_task_run(root, task, project_id)   [NEW P0-F1]
            │    ├─ get_node("task-execution") 无 → register_node(共享 Node)
            │    └─ create_node_run(root, "task-execution", task_id=backlog_id)
            │         → nodes/runs/run-{hex}.json  (TaskRun: task_id=TASK-*, state=PENDING)
            │         → NODE_RUN_CREATED audit
            ├─ gateway_execute(title, task_id=TASK-*, task_run_id=run-*, ...)  [task_id/task_run_id NEW]
            │    ├─ ExternalTaskRegistry.create → TASK-GW-* (ADAPTER 控制面, 不迁移)
            │    ├─ executor.run → claude/codex (真实委派)
            │    ├─ record_invocation(..., task_id, task_run_id)   [NEW]
            │    │    → EXS-{hex} + exec/execution_records.json  (task_id/task_run_id 持久化)
            │    │    → EXS-{hex}.report.md 证据
            │    ├─ verify (auto_verify; project_dir 空 → unknown 诚实)
            │    └─ reg.update(TASK-GW done/failed, result_id=EXS)
            └─ 返回 {exec_ref: EXS-{hex}, verify, output}    [exec_ref 语义修正]
       └─ ExecState.next → task.exec_ref = EXS-{hex} (session_exec 副本)
       └─ finish_task_exec(backlog_id, exec_ref=EXS-{hex})   [回写 backlog Task.exec_ref=EXS]
```

## 2. 关键节点状态

| 步骤 | 实体 | ID | 持久化 |
|---|---|---|---|
| 1 | Task (backlog) | TASK-* | workspace backlog task.json |
| 2 | TaskRun (NodeRun) | run-* | nodes/runs/*.json (task_id 锚) |
| 3 | Execution (EXS) | EXS-* | exec/execution_records.json (task_id/task_run_id) |
| 4 | 委派控制面 (Adapter) | TASK-GW-* | exec/external_tasks.json (result_id=EXS) |
| 5 | 会话编排状态 | session_exec | session_exec/<sid>.json (exec_ref=EXS) |

## 3. 断点状态 (F1 后)

| 原断点 | F1 处理 | 状态 |
|---|---|---|
| chain 不建 TaskRun | _chain_task_run 创建 run-* 锚 | ✅ 闭合 |
| EXS 无 task/task_run 锚 | record_invocation 透传持久化 | ✅ 闭合 |
| exec_ref=TASK-GW | _exec_fn exec_ref=result_id (EXS) | ✅ 闭合 |
| T-9 按 EXR 读 | EXS 直查优先, EXR legacy 回退 | ✅ 闭合 |
| TaskRun 状态推进 | 留 F2 | ⏳ F2 |
| session_exec 收敛 | 留 F2 | ⏳ F2 |
