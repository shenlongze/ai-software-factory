# 01 — CALL GRAPH (Execution Truth Root Cause)

> 取证日期: 2026-09-04 | READ ONLY | 代码路径 factory-console/factory-exec/factory-org

---

## 1. Web 生产主链 (8011, SSE)

```
POST /api/sessions/{session_id}/messages            fastapi_adapter.py:6980 api_session_send
  └─ stream=True → _on_event 队列 + StreamingResponse
       └─ run_agent_native(question, data_dir, project_id=session.project_id,
                           service, session_id, history, ...)   fastapi_adapter.py:7040
            └─ agent_loop.py:1779 run_agent_native
                 ├─ understand_intent(...)  (LLM 意图软参考)
                 ├─ LLM 工具循环 (fc tool_calls)
                 │    └─ dispatch(tid, args, root=data_dir,
                 │                  project_id=_resolved_project_id or project_id,
                 │                  service, ctx)               agent_loop.py:2198
                 │         (S34/S35-P0-5: 项目查询类自动补 project_id 2184-2213)
                 │         ├─ chain_start                        agent_loop.py:1409
                 │         ├─ chain_next                        agent_loop.py:1530
                 │         ├─ execute_plan                      (经 dispatch 720-903)
                 │         ├─ plan_development / gateway_status / chain_status ...
                 └─ answer 回写会话
```

## 2. chain_start 详细 (agent_loop.py:1409-1529)

```
plan = ctx.pending_plan
_cs_project_id = args.project_id or plan.project_id or project_id or ""   1414
for task in plan.tasks:
    _c = service.create_task(_cs_project_id, ...)  → backlog TASK-*       1428-1436
    _t2["backlog_id"] = _bid                                              1439
    (dependency: plan.order → prev backlog id)                             1444-1473
st = ExecState.load(root, session_id)                                      1474
st.start({goal, tasks: _enriched, acceptance})  → status=running           1475-1477
st.state["run_id"] = R{ms}; ["project_id"]=_cs_project_id;
["plan_id"]=...; ["session_id"]=...                                        1481-1497
sync_from_exec(...) → progress_card                                        1505
if args.auto: daemon thread _chain_auto_worker(...)                        1510-1523
```

## 3. chain_next 详细 (agent_loop.py:1530-1631)

```
st = ExecState.load(root, session_id)
if st.status != running: return error                                      1534
recover():  (9/2+ 版本; ExternalTaskRegistry status → 恢复)                1539-1565
_exec_fn(task):                                                           1567-1581
    gateway_execute(title, data_dir=root, project_id=project_id, max_retry=1)
    return {ok, output, verify, exec_ref: r.task_id (TASK-GW-*)}
r = st.next(_exec_fn, on_started=save)                                    1583
    → exec_state.py:115-169 (8/28 版无 exec_ref; 9/2 版写 task["exec_ref"] = result.exec_ref)
if backlog_id: service.finish_task_exec(...)  ← 仅 backlog_id 非空         1595-1617
reconcile_plan(...)                                                       1619-1624
if finished: deliver()
```

## 4. gateway_execute 详细 (external_executor/gateway.py:91-205)

```
_pick_executor(data_dir, agent_id, task, project_id)     117  → (executor_id, host_agent)
registry = build_registry(data_dir)                      120
adapter = next(a.id==executor_id)                        121
tid = ExternalTaskRegistry.create(task, owner, project_id)  126-129  → TASK-GW-*
project_dir = locate_repo(data_dir, project_id)          133-148  ← project_id 空 → ""
   if _perm.allowed_project_dirs and not ok_dir: deny                    141-148
for attempt in max_retry+1:
    r = executor.run(adapter, prompt, project_dir, agent, ...)  166-167
    rec = record_invocation(data_dir, executor_id, mode, prompt,
                            project_dir=project_dir, ...)    176-181  → EXS-* + execution_records.json
    result_id = rec.result_id                                 182
    verify = _verify_output(data_dir, result_id, project_dir, ...) 186-187 → auto_verify
    passed = exit_code==0 and verify != fail
reg.update(tid, done/failed, result_id, verify)            195-197
_write_back(data_dir, project_id, tid, task, ok, verify, output)  200 (Spine/记忆)
return {ok, task_id: TASK-GW-*, result_id: EXS-*, verify, executor, output}  201-205
```

## 5. CLI 路径 (旧执行体系, 仍在 cli_factory)

```
factory (cli_factory.py:8111 main) → InteractiveSession (8133)
  → session.py → intent → action_registry
       ├─ execute_task   (actions.py:1355 → exec.cli.cmd_exec_run)  ← employee/EXR 域
       └─ execute_project (actions.py:1645 → ExecutionOrchestrator)
            └─ orchestrator.py execute_project (M3)
                 ├─ TASK_STARTED audit  orchestrator.py:3223   ← task-e1-core / project_dir.name 数字
                 ├─ runner(task) → _default_execute_fn → execute_task
                 └─ TASK_COMPLETED/TASK_FAILED audit  orchestrator.py:2174/2869
```

## 6. conversation_os 路径 (另一 Web 旧体系)

```
POST /api/conversations/{id}/messages → conversation_os.send_message (fastapi_adapter 6105)
  → workforce.create_task / production_run.create_production_run / execute_production_run
    (conversation_os.py:314-383; S14 NodeRun 体系; evidence ev-*.json 属此域)
```

## 7. 断点定位汇总

| 断点 | 位置 | 类型 |
|---|---|---|
| project_id 未传 gateway | agent_loop.py:1572 用 dispatch 闭包 project_id, 弃 st.state["project_id"] (1486 已存) | D — context propagation |
| backlog_id 空 → 回写跳过 | agent_loop.py:1598 `if _bid:`; E2E create_task 因 project 空失败 | C/E — identity |
| exec_ref 三义 | agent_loop.py:1581 写 TASK-GW; fastapi_adapter.py:913-918 按 EXR 读; management.py:148 注释=EXR | C — contract |
| session_exec 不收敛 | exec_state.py:99-169 无超时/事件; 需人工 chain_next | B — state machine |
| audit 不连 backlog | orchestrator.py:3223/2174 (M3) vs service.py:4035 (TASK_CREATED only) | E — dual model |
| 8/31 done 无 exec_ref | 8/28 版 exec_state.next() 无该字段 (9/2 d6f1de6b 加) | 版本时序 |
