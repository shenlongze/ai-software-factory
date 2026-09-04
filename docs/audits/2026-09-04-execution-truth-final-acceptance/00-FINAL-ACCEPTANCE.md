# 00 — FINAL ACCEPTANCE (P0-FINAL, 2026-09-04)

> 性质: F0/F1/F2 Execution Truth Closure 最终验收 — READ ONLY
> 权威顺序: F0 Contract → F1 Identity → F2 Writeback → 代码 → 测试/E2E → 旧报告
> 日期: 2026-09-04 | HEAD: 1e993dec + working tree (F1+F2 未提交)

---

## 1. 验收判定

| 验收项 | 判定 | 证据摘要 |
|---|---|---|
| A. Task SSOT | **PASS** | Task=TASK-* (org.management.Task), service.create_task 唯一创建, transition_task 唯一状态写 |
| B. TaskRun SSOT | **PASS** | TaskRun=NodeRun run-*; create_node_run 纯创建 (零 executor_fn); chain 路径无 execute_node_run |
| C. EXS SSOT | **PASS** | EXS=record_invocation 唯一写; EXR 仅在 exec/员工域内部; TASK-GW/session_exec 非 canonical |
| D. finalize 事实源 | **PASS w/ edge note** | finalize 由 gateway 返回吸收; 边缘: EXS.result(仅 exit_code) vs gateway.final_ok(含 verify) 分歧窗口 |
| E. Idempotency | **PASS** | finalize 终态短路 (字段写入前 return); finish_task_exec 同态仅审计; E2E-3 实证 |
| F. Recovery | **PASS** | failed→ready→in_progress 合法; 新 TaskRun=新 attempt; 最终=最终 TaskRun outcome |
| G. Failure Truth | **PASS** | EXS failed + run failure_reason + Task failed; 无错误 COMPLETED |
| H. Write Ownership | **PASS** | Task 状态唯一写者 service (11 处 transition_task); exec_state 副本不写 backlog |
| I. Legacy Boundary | **PASS** | 零 execution-truth 迁移; EXR/TASK-GW/task-e1-*/session_exec 未接入 |
| J. WebUI/CLI/Audit | **PASS** | WebUI 纯投影; localStorage 仅 UI 偏好; audit 非 SSOT |

**总体: PASS (1 个 P2 边缘观察, 见 §4)**

---

## 2. 唯一问题的回答 (§二十)

> 当一个真实外部 Agent 执行一个 canonical TASK-* 后, AI Factory 是否能够仅凭自己的持久化事实, 准确回答: 这个 Task 是什么、由哪个 TaskRun 执行、对应哪个 EXS、执行最终成功还是失败、当前 TaskRun 状态是什么、当前 Task 状态是什么, 并且不会因为重复回调、失败重试或历史记录而产生第二个真相?

**YES** (真实 E2E 证据: TASK-a60181f2 → run-713d9b6903a2 → EXS (task_id/task_run_id 持久化) → TaskRun COMPLETED → Task done; 4×finalize 幂等; attempt1 FAILED→attempt2 SUCCESS 最终=最终 outcome)。

## 3. 已确认 Done / Not Done

**DONE**: F0 Contract Freeze / F1 Identity Closure / F2 Completion Writeback
**NOT DONE** (不混入): F3 Verification SSOT / F4 Artifact-Evidence / Release / Learning / Replanning / Requirement→PRD→Plan / Model Policy production / Agent ecosystem / Productization

## 4. P2 边缘观察 (非阻塞)

**O-1 (P2)**: EXS.result 字段仅由 exit_code 判定 (executor.py:211); gateway final_ok =
exit_code==0 AND verify!=fail (gateway.py:198)。边缘: exit_code==0 + verify=fail →
EXS.result=success 但 TaskRun=FAILED (verify 经 verify_invocation 回写 EXS.verify=fail)。
不产生第二真相 (TaskRun/Task 终态仍由同一 gateway 判定驱动, verify 元数据完整保留),
但 EXS.result 字面与 TaskRun 终态在 verify-fail 窗口不一致。→ F3 (Verification SSOT)
应统一判定语义。**不阻塞 F0/F1/F2 验收** (EXS 无独立状态机, 不是 canonical TaskRun 竞争者)。

**O-2 (P2)**: workflow_runner (S14) 自建 T-*/R{ms} run 体系 (workflow_runner.py:208/886),
是并行执行域 (项目级自驱动), 不写 backlog TASK-*, 不构成 TaskRun 竞争;
标记观察, F4/产品链治理时确认边界。

**O-3 (P2)**: Task 终态字面 = done/failed (org.management.TaskStatus), TaskRun 终态 =
COMPLETED/FAILED (NODERUN_STATES) — 两域各自 canonical enum (F2 §6 遵循现有 enum),
非语义冲突。
