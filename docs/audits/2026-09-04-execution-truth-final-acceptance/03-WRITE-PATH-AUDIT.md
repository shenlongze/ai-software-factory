# 03 — WRITE-PATH AUDIT (P0-FINAL, 2026-09-04)

> 逐写路径审计 — SUCCESS / FAILURE / 边缘窗口

---

## 1. SUCCESS 路径 (严格)

```
外部 CLI exit_code==0 AND verify!=fail
  → gateway final_ok=True (gateway.py:198)
  → record_invocation: EXS.result="success" (executor.py:211)
  → gateway 返回 {ok:True, result_id:EXS}
  → agent_loop _exec_fn: finalize_node_run(success=True)
  → NodeRun: PENDING→RUNNING→VERIFYING→COMPLETED (+completed_at)
  → st.next: 副本 done
  → finish_task_exec(success=True): Task → done, exec_ref=EXS
✓ EXS SUCCESS → TaskRun COMPLETED → Task done (E2E-1 实证)
```

## 2. FAILURE 路径 (严格)

```
外部 CLI exit_code!=0 (或无执行器)
  → record_invocation: EXS.result="failed" (或无 EXS: 无执行器分支 result_id="")
  → gateway 返回 {ok:False, error, result_id}
  → agent_loop: finalize_node_run(success=False, failure_reason=error)
  → NodeRun: PENDING→RUNNING→FAILED (+failure_reason)
  → st.next: 副本 failed
  → finish_task_exec(success=False): Task → failed
✓ EXS FAILED → TaskRun FAILED → Task failed (E2E-2 实证; 无错误 COMPLETED)
```

## 3. CANCELLATION (边界)

用户 cancel → finish_task_exec(cancelled=True) → Task cancelled (既有路径)。
TaskRun 若已在 COMPLETED/FAILED → finalize 幂等不逆转。
不新造 cancellation architecture (F2 §11 遵守)。

## 4. 边缘窗口 (P2 观察 O-1, 诚实记录)

```
exit_code==0 AND verify=fail:
  EXS.result = "success" (executor.py:211 — 仅 exit_code 判定)
  EXS.verify  = {result:"fail"} (verify_invocation 回写)
  gateway final_ok = False → finalize(success=False) → TaskRun FAILED → Task failed

分歧: EXS.result 字面 "success" 但 TaskRun/Task = FAILED。
不产生第二真相: TaskRun/Task 终态由同一 gateway 判定 (含 verify) 驱动;
EXS.verify=fail 元数据完整保留 (可解释)。EXS 无状态机, 非 canonical TaskRun。
建议 F3 (Verification SSOT) 统一 EXS.result 判定语义 (纳入 verify 或明确双字段语义)。
```

## 5. 完成写者清单 (重复确认)

| 状态 | 写者 | 幂等 |
|---|---|---|
| NodeRun 终态 | finalize_node_run (chain) / execute_node_run (workflow) | 终态短路 |
| Task 终态 | service.finish_task_exec (actor: session-chain / session-chain-auto / cli / e2e) | 同态仅审计 |
| EXS | record_invocation (gateway) | append (attempts 历史) |
