# 02 — VERIFICATION CALL GRAPH (P0-F3, 2026-09-04)

> F3 后真实调用链 (代码验证)

---

## 1. TaskRun 执行路径 (chain — 真实外部执行)

```
gateway_execute (外部 CLI) → record_invocation → EXS-* (execution_records.json)
    ↓ 返回 {ok, result_id, verify}
agent_loop._exec_fn
    ↓ finalize_node_run(success=r.ok, verification=r.verify)
node_runtime.finalize_node_run
    ↓ _materialize_verify (兼容 result/status 字段, ok 判定)
verification_domain.materialize_verification
    ↓ ver-* 落盘 (verifications/verifications.json) + run.verification 引用
NodeRun COMPLETED/FAILED
    ↓ finish_task_exec (service)
Task done/failed
```

## 2. NodeRun 执行路径 (workflow — S2/S3)

```
execute_node_run (executor_fn)
    ↓ result.verification
_materialize_verify (ok = v_result == PASS)
    ↓ ver-* 落盘 + run.verification 引用 + attempts 历史
NodeRun COMPLETED (PASS) / FAILED→repair (FAIL)
```

## 3. 查询路径

```
CLI:  factory verification list|get --task-run/--exs/--data-dir
        → verification_domain.list_verifications / get_verification
API:  T-9 _task_exec_trace → EXS 记录 → task_run_id → ver-* 投影 (只读)
```

## 4. 真实验证执行 (S5 执行器复用, 非新引擎)

```
verification.py: verify_pytest (subprocess pytest -q) / verify_python_syntax (ast.parse)
professional_workflow.verify_code_with_pytest (临时目录真实 pytest)
external executor auto_verify (verify_hook / pytest, gateway 委派后)
```

## 5. 唯一写者路径

所有 ver-* 创建 → materialize_verification (加锁原子写)。
node_runtime._materialize_verify 是唯一调用适配器 (finalize ×2 + execute ×1)。
