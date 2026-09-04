# 01 — ID RELATION AUDIT (P0-F1, 2026-09-04)

> F1 后 ID 关系审计 — Task → TaskRun → EXS 在代码与持久化中的真实状态

---

## 1. 冻结关系 (F0) → 落地状态 (F1)

| 关系 | F0 契约 | F1 实现 | 状态 |
|---|---|---|---|
| TaskRun.task_id → Task | run 记录 task_id | node_runtime.create_node_run(task_id) → run["task_id"] | ✅ IMPLEMENTED |
| EXS.task_run_id → TaskRun | EXS 记录 task_run_id | record_invocation(task_id, task_run_id) → EXS 记录 | ✅ IMPLEMENTED |
| EXS.task_id → Task | EXS 记录 task_id | 同上 (task_id 一并透传) | ✅ IMPLEMENTED |
| Task.exec_ref → EXS | exec_ref = EXS-* | agent_loop 两处 _exec_fn exec_ref=result_id | ✅ IMPLEMENTED |
| Task → TaskRun 创建链 | chain 委派时建 run | _chain_task_run → create_node_run(共享 Node) | ✅ IMPLEMENTED |
| 读端: T-9 溯源 | exec_ref=EXS 直查 | fastapi_adapter EXS 优先, EXR legacy 回退 | ✅ IMPLEMENTED |

## 2. Canonical 持久化验证 (测试证据)

- nodes/runs/{run_id}.json: 含 task_id (test_node_run_created_with_task_id)
- exec/execution_records.json: 每条含 task_id/task_run_id (test_record_invocation_persists_anchors)
- exec store results.json (pydantic ExecutionResult): 支持 task_id/task_run_id (test_execution_result_model_accepts_anchors)
- 旧数据兼容: 无锚字段 EXS 反序列化 task_id="" (test_execution_result_model_old_data_compatible)

## 3. Round-trip 验证

```
EXS (result_id) → task_run_id → run-* → task_id → TASK-*   (test_full_chain_round_trip)
Task.exec_ref = EXS → T-9 溯源直查 execution_records         (fastapi _task_exec_trace)
```

## 4. Idempotency

- 同一 Task 重复执行 = 不同 run-* (每次新 TaskRun, 历史保留) (test_repeat_node_run_creates_distinct_runs_same_task)
- 同一 TaskRun 多次 EXS = append 不覆盖 (attempts 语义) (test_repeat_record_invocation_appends_not_overwrites)

## 5. 未达 / 边界

- NodeRun 状态推进 (PENDING→COMPLETED): F1 只建锚, 状态机推进留 F2
- 历史 EXS 无锚: 保留空, 不猜测 (F0 §5D)
- backlog_sweeper 手工 EXR/EXS: 未改 (独立工具, F1 范围外)
