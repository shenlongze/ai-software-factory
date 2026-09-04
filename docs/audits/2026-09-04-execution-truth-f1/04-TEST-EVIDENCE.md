# 04 — TEST EVIDENCE (P0-F1, 2026-09-04)

> F1 测试证据 — 关系测试 + 回归

---

## 1. 新增关系测试 (16 passed)

文件: tests/console/test_p0_f1_identity_relations.py

| Test | F1 §9 | 验证 |
|---|---|---|
| TestTaskRunAnchorsTask.test_node_run_created_with_task_id | A | NodeRun.task_id==TASK-* 且持久化 |
| TestTaskRunAnchorsTask.test_node_run_without_task_id_backward_compatible | A | 旧 S2 调用 (无 task_id) 兼容 |
| TestTaskRunAnchorsTask.test_task_run_requires_node | A | S2 不变 (未注册 node → NodeError) |
| TestEXSAnchorsTaskRun.test_record_invocation_persists_anchors | B | EXS.task_run_id==run-* 持久化 |
| TestEXSAnchorsTaskRun.test_exs_backward_compatible_no_anchors | B | 旧调用空锚兼容 |
| TestEXSAnchorsTaskRun.test_execution_result_model_accepts_anchors | B | pydantic model 支持锚 |
| TestEXSAnchorsTaskRun.test_execution_result_model_old_data_compatible | B | 旧 JSON 反序列化默认空 |
| TestExecRefSemantics.test_chain_task_run_anchors_and_persists | C | _chain_task_run 锚 + Node 自动注册 |
| TestExecRefSemantics.test_chain_task_run_no_backlog_no_run | C | 无 backlog → 不建 run (失败安全) |
| TestExecRefSemantics.test_exec_fn_source_uses_result_id | C | 源码级: 两处 exec_ref=result_id (EXS) |
| TestExecRefSemantics.test_exec_ref_never_gw_or_run | C | exec_ref ≠ run-* ≠ TASK-GW |
| TestRoundTrip.test_full_chain_round_trip | D | EXS→run→Task 反查 |
| TestIdempotency.test_repeat_node_run_creates_distinct_runs_same_task | E | 同 Task 多 run, 无第二 SSOT |
| TestIdempotency.test_repeat_record_invocation_appends_not_overwrites | E | EXS append 不覆盖 |
| TestLegacyIsolation.test_legacy_ids_not_valid_task_run_anchors | F | task-e1/EXR/TASK-GW 非 canonical 格式 |
| TestLegacyIsolation.test_exec_ref_semantics_docstring_frozen | F | management.Task 注释 = EXS |

## 2. 回归

| 套件 | 结果 | 时间 |
|---|---|---|
| tests/org + tests/exec + exec_state/writeback + F1 新测试 | **2228 passed** | 39s |
| node/gateway/external/trace 相关 | **52 passed** | 2s |
| 旧 exec_ref 测试 (test_task_exec_writeback / exec_state_recovery / s7_role) | **53 passed** | 3s |
| test_agent_loop.py | 11 failed / 66 passed | — **预先存在失败** (git stash 验证无我的改动时同样 11 failed; topic_ledger/project_list 行为, 与 F1 无关) |

## 3. 执行命令

```bash
.venv/bin/python -m pytest tests/console/test_p0_f1_identity_relations.py   # 16 passed
.venv/bin/python -m pytest tests/org tests/exec \
    tests/console/test_exec_state_recovery.py tests/console/test_task_exec_writeback.py \
    tests/console/test_p0_f1_identity_relations.py                            # 2228 passed
.venv/bin/python -m pytest tests/llm/test_node_runtime.py tests/llm/test_executor_gateway.py \
    tests/llm/test_node_artifact_e2e.py tests/llm/test_executor_gateway_permissions.py \
    tests/llm/test_gateway_session_integration.py tests/llm/test_llm_gateway_agent_integration.py \
    tests/console/test_external_executor.py tests/console/test_s10_120_trace_chain.py          # 52 passed
```
