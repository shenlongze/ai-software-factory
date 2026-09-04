# 01 — EXECUTION TRUTH CLOSURE (P0-FINAL, 2026-09-04)

> 真实闭环 — 基于代码重新绘制 (非旧报告复制)

---

## 1. 真实闭环 (代码验证)

```
┌──────────────────────────────┐
│ Task TASK-* (backlog)        │  org.management.Task
│ SSOT: workspace backlog      │  writer: service.create_task → ManagementStore
│ task.json                    │  state: transition_task 唯一 (八态)
└──────────────┬───────────────┘
               │ task_id (create_node_run task_id=backlog)
               ▼
┌──────────────────────────────┐
│ TaskRun run-* (NodeRun)      │  node_runtime.create_node_run — 纯创建 (PENDING)
│ SSOT: nodes/runs/*.json      │  零 executor_fn (无自动执行 — double-exec 安全)
│ task_id = TASK-*             │
└──────────────┬───────────────┘
               │ gateway_execute(task_id, task_run_id) → 真实外部 CLI (hermes/codex/claude)
               ▼
┌──────────────────────────────┐
│ EXS-* (execution result)     │  record_invocation (executor.py) — 唯一 EXS 写者
│ SSOT: exec/execution_records │  task_id/task_run_id 锚 (F1) + result/verify
│ .json                        │
└──────────────┬───────────────┘
               │ finalize_node_run(success=r.ok, verification=r.verify) (agent_loop ×2)
               ▼
┌──────────────────────────────┐
│ TaskRun 终态                 │  COMPLETED (success) / FAILED (failure)
│                              │  幂等; 零二次执行; NODE_RUN_* audit
└──────────────┬───────────────┘
               │ finish_task_exec (service — Task 唯一写者)
               ▼
┌──────────────────────────────┐
│ Task 终态                    │  done / failed / cancelled
│ exec_ref = EXS-*             │
└──────────────────────────────┘
```

## 2. 关键身份链 (唯一, 可追溯)

```
TASK-a60181f2 (Task)
  └─ NodeRun.task_id = TASK-a60181f2
       └─ EXS.task_run_id = run-713d9b6903a2  (E2E-1 真实持久化证据)
            └─ Task.exec_ref = EXS-* (EXS-... E2E-1)
```

## 3. 双路径确认 (无竞争)

| 路径 | 触发者 | 执行 | finalize |
|---|---|---|---|
| chain (Web 会话) | agent_loop chain_next/auto | gateway_execute (外部 CLI) | finalize_node_run (只吸收) |
| workflow (S3) | production_run.execute | execute_node_run (executor_fn) | execute_node_run 一体 |

execute_node_run 只在 production_run.py:474 被调用; agent_loop/session 零调用
→ 无 double execution。

## 4. 完成写者清单 (单一)

Task 终态写者: **service.finish_task_exec → transition_task** (唯一)
  - agent_loop auto worker (actor=session-chain-auto)
  - agent_loop chain_next (actor=session-chain)
  - cli bridge / backlog_sweeper (独立工具链, 经 service)

TaskRun 终态写者: **node_runtime.finalize_node_run / execute_node_run** (域内唯一)
EXS 写者: **record_invocation** (唯一)
