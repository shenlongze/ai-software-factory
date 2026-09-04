# 02 — OWNERSHIP MATRIX (P0-F0, 2026-09-04)

> Ownership Contract — 谁创建 / 谁拥有状态 / 谁只能读 / 谁可完成 / 谁可结束
> 铁律: 一个状态只能有一个 canonical owner (STEP10 INV-001 延伸); 多写者 = contract violation。

---

## 1. Entity State / Owner / Producer / Consumer 矩阵

| Entity | State 集合 | Canonical Owner (写) | Producer (创建) | Consumer (只读) | Violation 现状 |
|---|---|---|---|---|---|
| Session | active/archived | SessionStore | SessionStore | WebUI/chain | — |
| Plan | pending/approved/executed | PendingPlanStore + execute_plan | plan_development (agent_loop) | chain_start/reconcile_plan | — |
| Task (backlog) | todo/ready/in_progress/review/done/blocked/failed/cancelled | **ManagementStore 经 transition_task 唯一合法写** (service.py:3969/4378/4469) | execute_plan/chain_start (service.create_task) | ExecState/UI/API | ⚠️ ExecState 直接改自己 task 副本 (session_exec), 不回写 backlog → 两副本不同步 (实为两实体, 非单 task 双写; 见下) |
| TaskRun (NodeRun) | PENDING/RUNNING/VERIFYING/COMPLETED/FAILED/REPAIRING | **node_runtime (S2) 唯一** | create_node_run | recovery/governance | — (S2 域内干净) |
| Execution (EXS) | success/failed (记录态) | **record_invocation (executor.py)** 唯一写 | gateway/exec | T-9/监控 | — |
| Artifact (S1) | GENERATED→VALIDATED→... | **artifact_lifecycle (S1) 唯一** | create_artifact | workflow/UI | ⚠️ exec ART-* 与 S1 art-* 双体系 (F4) |
| Verification | (F3 冻结: PASS/FAIL/INCONCLUSIVE/BLOCKED/unknown) | **F3 冻结归属 TaskRun 执行者 (NodeRun)** | auto_verify/verification.py | gateway/release | 无 SSOT (多 producer) |
| Evidence | (bundle) | EvidenceStore (S23) | EvidenceBuilder | audit/release | PARTIAL |
| Audit | append-only | AuditEmitter 统一 (audit_emitter.py:70) | 各域 | audit API | **事件层唯一 owner = AuditEmitter** |

## 2. 关键 Ownership 决策 (冻结)

### 谁可以改变 Task 状态?
- **唯一合法**: ManagementStore.transition_task (经 service.start_task_exec / finish_task_exec / create_task /
  update_task — 八态机 TASK_TRANSITIONS 校验非法路径)
- **禁止**: 任何模块直接改 backlog JSON; ExecState/chain 不得绕过 service 改 backlog Task
- ⚠️ 现状 violation: session_exec 的 task 副本由 ExecState 直接改 (exec_state.py:156), 但那是
  **会话编排副本 (另一实体)**, 不是 backlog Task — 需经 finish_task_exec 单向同步 → 本契约要求
  chain 完成时**必须**经 service 回写 backlog (backlog_id 空时显式告警, 不静默跳过)

### 谁可以创建 Execution (EXS)?
- **唯一合法**: record_invocation (external_executor/executor.py:194) — 经 gateway 调用
- NodeRun executor_fn 若直接产生结果 → 经统一 adapter 转 EXS 记录 (F1)
- EXR (请求) 由 exec.store/AgentRuntime 创建 — 降为 adapter, 不再作为 canonical 入口

### 谁可以完成 Execution?
- gateway_execute (gateway.py:195-197 reg.update done/failed) — 委派路径
- node_runtime.execute_node_run (node_runtime.py:259+) — S2 路径 (state 机 owner)
- **统一**: F1 后 EXS 最终状态由"执行完成者"写, 但 TaskRun 状态机 owner = node_runtime

### 谁可以触发 Verification?
- **F3 冻结**: Verification 属 TaskRun (NodeRun 执行者), 触发者 = NodeRun 状态机 (execute_node_run
  内 VERIFYING 阶段); 委派路径 (gateway auto_verify) 挂接为同一 verification 语义
- 任何人不得绕过 NodeRun 单独写 verification 事实 (现状 gateway verify dict 内嵌 = 待 F3 落 SSOT)

### 谁可以把 Task 标记 COMPLETED?
- **TaskRun (NodeRun) COMPLETED + Verification 通过** → service.finish_task_exec(success=True)
  唯一路径 (八态 todo→in_progress→review→done)
- 禁止: 仅凭 EXS success 直接置 Task done (需 TaskRun 完成证据链)

### 谁可以结束 Session?
- SessionStore (用户操作/archive); chain deliver 只汇报不结束 session
- session_exec (编排状态) 终态由自身状态机定 (done/failed/abandoned), 不得反向改 Session

## 3. 状态机 Owner 一览 (冻结)

```
Task        : ManagementStore.transition_task        (八态, 唯一)
TaskRun     : node_runtime.transition_node_run       (PENDING→...→COMPLETED/FAILED, 唯一)
Execution   : record_invocation (结果记录创建+终态)
Artifact    : artifact_lifecycle.transition_artifact (S1, 唯一)
Verification: F3 冻结 (NodeRun 执行者; 唯一 SSOT 待建)
Audit       : AuditEmitter (唯一写入; append-only)
```

## 4. 现状 Contract Violation 清单 (取证)

| # | Violation | 位置 | 严重度 |
|---|---|---|---|
| V-1 | session_exec task 状态与 backlog 不同步 (exec_ref 空/回写跳过) | agent_loop.py:1598 if _bid 静默跳过 | P0 (F2) |
| V-2 | exec_ref 三义 (chain 写 TASK-GW / T-9 读 EXR) | agent_loop.py:1581 / fastapi_adapter.py:913 | P0 (F0 已冻结语义, F1 修) |
| V-3 | gateway verify dict 内嵌无 SSOT | gateway.py:186 | P1 (F3) |
| V-4 | Artifact 双体系 (exec ART-* vs S1 art-*) | executor.py vs artifact_lifecycle | P1 (F4) |
| V-5 | EXR 请求→结果无链接 (output_refs 0/86) | exec store | P1 (F1 标记 legacy) |
| V-6 | audit STARTED/COMPLETED 只连 legacy M3 | orchestrator.py | P1 (审计契约 §5) |
