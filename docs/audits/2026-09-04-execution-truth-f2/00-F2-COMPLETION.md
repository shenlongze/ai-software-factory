# 00 — F2 COMPLETION (2026-09-04)

> Sprint: P0-F2 Execution Completion → Canonical Writeback Closure | Status: PASS
> 依据: P0-F0 Contract (人工批准) + P0-F1 (2577 passed) + F2 Gap Audit + 真实 E2E

---

## 1. F2 Objective

真实 External Execution 完成事实 → EXS → TaskRun (NodeRun) 终态 → Task 终态,
幂等、零二次执行、可追溯, 不污染 legacy。

## 2. Before State

- F1 建了 NodeRun 锚 (task_id) + EXS 锚 (task_id/task_run_id), 但 **run-* 创建 PENDING 后无人 finalize**
- gateway 委派完成 → EXS 写入, 但 TaskRun 状态永不推进 (Gap-1, P0)
- 失败路径 exec_ref 丢失: _exec_fn 在 ok=False 时只返回 {ok:False, error}, 不带 result_id (Gap-2)
- recover 用 exec_ref 查 TASK-GW registry — F1 后 exec_ref=EXS, registry miss → UNKNOWN 重排队 (Gap-3)
- 结论: "EXS 已完成但 TaskRun/Task 不收敛" 是常态, 不是偶发

## 3. Root Cause

Production chain (chain_next/auto worker) 只做委派 + Task 回写 (finish_task_exec),
从不推进 canonical TaskRun (NodeRun) 生命周期 — F1 遗留的"建锚不收敛"。

## 4. Canonical Writeback Path (F2 后)

```
TASK-* ──task_id──► run-* (NodeRun PENDING, F1 锚)
                      │ gateway_execute (真实外部 CLI: hermes/codex/claude)
                      ▼
                     EXS-* (record_invocation, task_id/task_run_id 锚)
                      │ finalize_node_run (F2: 幂等, 零二次执行)
                      ▼
              COMPLETED (success) / FAILED (failure)
                      │ finish_task_exec (幂等, 八态合法路径)
                      ▼
                   done / failed / cancelled
```

## 5. Changes

| 文件 | 改动 |
|---|---|
| factory-console/node_runtime.py | **finalize_node_run** (F2 核心): PENDING→RUNNING→VERIFYING→COMPLETED (success) 或 PENDING→RUNNING→FAILED (failure); 幂等 (终态不可逆/不重复转换); 零 executor_fn 调用 (P0 STOP 安全); 记录 verification metadata (非 F3 SSOT) + failure_reason + completed_at |
| factory-console/session/agent_loop.py | 两处 _exec_fn (chain_next + auto worker): 委派后 finalize_node_run; 失败路径回传 exec_ref=EXS (Gap-2); recover _run_status: NodeRun→EXS→TASK-GW 三级证据 (Gap-3) |
| tests/console/test_p0_f2_writeback.py | 8 个 F2 测试 (finalize 成功/失败/幂等/零二次执行/从 RUNNING·VERIFYING 恢复/链级 writeback/失败 exec_ref/recover 语义) |

## 6. State Ownership (F2 §5)

| 状态 | Canonical Owner | F2 后 |
|---|---|---|
| Task lifecycle (八态) | ManagementStore.transition_task (经 service) | ✅ 唯一 |
| TaskRun lifecycle | node_runtime (NodeRun) — finalize_node_run 吸收外部结果 | ✅ 收敛 |
| External execution result | EXS (record_invocation) | ✅ 唯一 |
| Orchestration transient | ExecState/session_exec | ✅ 非 canonical |
| Audit fact | audit_events.json | ✅ (NODE_RUN_COMPLETED/FAILED 由 node_runtime 发) |
| Legacy execution | legacy stores | ✅ 隔离 |

## 7. Success Path (E2E-1)

真实 hermes CLI: TASK-fb7f3653 → run-eb5884c5eb0b → EXS-712fff12 →
TaskRun COMPLETED → Task done (exec_ref=EXS-712fff12)。全链持久化证据。

## 8. Failure Path (E2E-2)

无执行器分支 (真实 gateway): TaskRun FAILED → Task failed, 无错误 COMPLETED。

## 9. Idempotency (E2E-3)

4 次 finalize (含 success=False 尝试): 终态保持 COMPLETED, 无重复转换,
EXS 记录数=1, 不逆转 (F2 §9 P0 满足)。

## 10. Recovery (E2E-4)

attempt1 失败 (TaskRun FAILED / Task failed) → failed→ready→in_progress 重试 →
attempt2 真实 hermes 成功 (TaskRun COMPLETED / Task done / exec_ref=最终 EXS)。
最终 Task 反映最终 canonical TaskRun outcome。

## 11. Cancellation Boundary

未改动 cancellation 架构 (F2 §11): 用户 cancel 仍为 LLM 循环级; Task 级 cancelled
经 finish_task_exec(cancelled=True) 既有路径; ExecState 无新 cancel 方法。
若 run 已 COMPLETED/FAILED → finalize 幂等不逆转 (cancel 不会误写终态)。

## 12. Real E2E Evidence

E2E-1/2/3/4 全部 PASS (隔离 tmp 工作区, 真实 hermes CLI, 无 mock 执行)。
证据: /tmp/f2_e2e.py + /tmp/f2_e2e_fail.py 输出 (04-TEST-EVIDENCE.md 记录)。

## 13. Test Results

- F1 regression: 16/16 PASS
- F2 tests: 8/8 PASS
- org+exec+console+llm 相关: 2357 passed (独立重跑 concurrency 5/5 — 偶发非回归)
- test_agent_loop.py: 11 failed = 预存 (stash 对照 before==after, F2 零新增)
- 总: 24 (F1+F2) + 2357 = 2381 passed, 0 F2-attributable regression

## 14. Remaining Gaps

1. **F3 (Verification SSOT)**: finalize 记录 verification metadata, 但不建 ver-* SSOT / policy
2. **F4 (Artifact/Evidence)**: NodeRun artifact_id 未由委派路径填充 (exec ART-* 独立)
3. **NodeRun 状态推进的 execute_node_run 语义**: 委派路径用 finalize (外部已执行); workflow 路径仍用 execute_node_run — 双路径并存, F2 未合并
4. **历史 session_exec (6 E2E)**: 未处置 (用户决策项)
5. **gateway verify 依赖 project_dir**: project_dir 空时 verify=unknown (诚实降级), 不伪造
6. **Task 状态名**: 现有八态 done/failed (无 COMPLETED 字面) — 遵循现有 canonical enum (F2 §6)

## 15. F3 Prerequisites

- Verification 归属 TaskRun (F0 已冻结) — finalize 已预留 verification metadata 字段
- ver-* SSOT + policy + pytest convergence 需 F3 新建 (F2 未触碰)
