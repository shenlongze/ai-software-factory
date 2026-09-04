# 00 — F2 GAP AUDIT (2026-09-04)

> 状态: AUDIT COMPLETE → 进入最小实现
> 依据: P0-F0 Contract + P0-F1 (2577 passed) + 本审计 (只读)

---

## 1. 审计方法

真实代码调用链 + ~/.factory 数据只读核对 (F1 后无新生产委派: 带锚 EXS=0)。

## 2. Call Graph (现状, F1 后)

```
agent_loop chain_next / _chain_auto_worker
  └─ _chain_task_run(root, task, project_id)          # F1: 建 NodeRun 锚
  │    ├─ register_node("task-execution") (首次)
  │    └─ create_node_run(task_id=backlog) → run-* PENDING
  └─ gateway_execute(title, task_id, task_run_id)     # F1: 透传
       ├─ ExternalTaskRegistry.create → TASK-GW-*     # adapter 控制面
       ├─ executor.run(claude/codex/hermes)           # 真实外部执行
       ├─ record_invocation(task_id, task_run_id)     # F1: EXS 带锚
       │    → EXS-* + execution_records.json          # result=success/failed (终态=写入时定)
       └─ 返回 {ok, task_id, result_id=EXS, verify}
  ├─ ExecState.next: task 副本 status=done/failed, exec_ref=EXS   # 会话编排副本
  └─ service.finish_task_exec(success, exec_ref=EXS)  # backlog Task → done/failed
```

## 3. 10 问回答 (F2 §4)

| # | 问题 | 事实 |
|---|---|---|
| 1 | EXS 在哪创建? | gateway 循环内 record_invocation (每次 attempt 都写; exit_code≠0 → result=failed) |
| 2 | EXS 何时终态? | 写入即终态 (无状态机; result=success/failed 由 exit_code 定) |
| 3 | 谁知道执行已结束? | gateway_execute 同步返回 (subprocess 完成) → _exec_fn 拿到 r.ok + r.result_id |
| 4 | 谁负责 NodeRun finalize? | **无人** ← 核心缺口: run-* 创建 PENDING 后永不推进 |
| 5 | 谁负责 Task writeback? | service.finish_task_exec (chain 两处已调; 幂等, Task 八态合法路径) |
| 6 | Task 状态唯一写入点? | ManagementStore.transition_task (经 service) — 无第二写者 |
| 7 | failure 如何传播? | r.ok=False → _exec_fn 返回 ok=False → st.next 副本 failed → finish_task_exec(success=False) → Task failed |
| 8 | retry/recovery? | gateway 内 max_retry (TASK-GW 控制面); ExecState.recover 用 registry 查 (F1 后 exec_ref=EXS 查 registry 会 miss → UNKNOWN 重排队) — **recover 语义待修 (F2 边界内)** |
| 9 | cancellation? | 用户 cancel = LLM 循环级 (agent_loop 2033); Task 级 cancelled 经 finish_task_exec(cancelled=True); ExecState 无 cancel 方法 — 会话停止后 run 停 PENDING |
| 10 | "EXS 完成但 run/task 仍 RUNNING" 窗口? | **存在且是常态**: run-* 永远 PENDING (NodeRun 未 finalize); Task 副本 running 直到 finish_task_exec |

## 4. 核心缺口 (F2 要解决的)

**Gap-1 (P0): NodeRun finalization 缺失。**
- F1 只建锚 (PENDING), 委派完成后无人推进 run-* → COMPLETED/FAILED
- execute_node_run 会触发第二次外部执行 (P0-1 STOP) — 不可用于委派完成后的 finalize
- 需要: 一个 **幂等 finalize 函数** (基于 EXS 结果推进 NodeRun 终态, 合法转换, 零执行)

**Gap-2 (P1): 失败路径 exec_ref 丢失。**
- _exec_fn 在 r.ok=False 时返回 {"ok": False} — 不带 result_id (EXS failed 已写但未回传)
- 修复: 失败也返回 exec_ref=result_id (EXS), Task.exec_ref=EXS 在失败时同样成立

**Gap-3 (P1): recover 用 EXS 查 registry 会 miss。**
- recover(_run_status_fn) 查 ExternalTaskRegistry (TASK-GW); F1 后 exec_ref=EXS → miss → UNKNOWN → 重排队
- 修复 (F2 边界): recover 应优先查 NodeRun (canonical TaskRun); 若无 run 证据 → 查 EXS 记录; 保持 UNKNOWN 不伪造

**Gap-4 (P2): Task 终态应反映 canonical TaskRun 终态, 而非仅副本 status。**
- 现在 finish_task_exec(success=副本 status==done); 副本 status 由 _exec_fn ok 决定 (与 EXS 一致)
- F2: 保持 (副本与 EXS 一致性已由 _exec_fn 保证); TaskRun finalize 先行, Task 回写跟随

## 5. State Ownership (F2 §5)

| 状态 | Canonical Owner | 现状 |
|---|---|---|
| Task lifecycle (八态) | ManagementStore.transition_task | ✅ 唯一 |
| TaskRun lifecycle (PENDING→…→COMPLETED/FAILED) | node_runtime (NodeRun) | ⚠️ 无人 finalize → F2 补 |
| External execution result | EXS (record_invocation) | ✅ 唯一 |
| Orchestration transient | ExecState/session_exec | ✅ (非 canonical) |
| Audit fact | audit_events.json | ✅ |
| Legacy execution | legacy stores | ✅ 隔离 |

## 6. 最小实现设计 (不越界)

1. **node_runtime.py**: 新增 `finalize_node_run(root, run_id, *, success, verification=None, failure_reason="", note="", actor="execution")`
   - 幂等: run 已 COMPLETED/FAILED → 返回现状 (不重复转换)
   - 合法推进: 从当前 state 经 NODERUN_TRANSITIONS 走到终态 (PENDING→RUNNING→VERIFYING→COMPLETED | RUNNING→FAILED)
   - 记录 verification 元数据 (gateway verify dict; 不建 F3 SSOT), failure_reason
   - **绝不调用 executor_fn / execute_node_run** (P0-1 安全)
   - audit: NODE_RUN_COMPLETED / NODE_RUN_FAILED (既有 event types)
2. **agent_loop.py** chain_next + auto worker `_exec_fn`:
   - 委派返回后调用 finalize_node_run(run_id, success=r.ok, verification=r.verify, failure_reason=r.error)
   - 失败路径也返回 exec_ref=result_id (EXS) (Gap-2)
3. **recover 语义 (chain_next 内 _run_status_fn)**: 优先查 NodeRun; 无 → 查 EXS 结果; 无 → None (UNKNOWN 重排队) (Gap-3)
4. 测试: 新增 tests/console/test_p0_f2_writeback.py (finalize 幂等/成功/失败/无二次执行/合法转换) + 真实 E2E 脚本

## 7. 禁止 (F2 §3 确认)

- 不做 Verification SSOT (仅 metadata) / Artifact / Evidence / Release / Learning / Replanning / Legacy migration
- 不迁移 ~/.factory; 不修改历史 session_exec/EXR/task-e1-*
- 不把 session_exec 当 TaskRun; EXS 不是 TaskRun

## 8. E2E 可行性

真实 external CLI 可用: codex (/opt/homebrew/bin), claude (/opt/homebrew/bin), hermes (~/.local/bin)。
历史证据: 15 条 external_ai.invoke (8/26-8/31, claude/codex/hermes) — 真实委派可达。
E2E 用隔离 tmp 工作区 + 真实 hermes/codex CLI 委派 (极简任务, 避免消耗); 验证全链持久化。
