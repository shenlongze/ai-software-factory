# 02 — ID / LEDGER MAP (Execution Truth Root Cause)

> 取证日期: 2026-09-04 | READ ONLY | 数据根 ~/.factory 实读 + 代码定位

---

## 1. Ledger Matrix

| Domain | Storage | ID 示例 | Producer (代码) | Consumer | Canonical? |
|---|---|---|---|---|---|
| Session | ~/.factory/console_sessions.json | sess-134c852dbd | console_sessions.py SessionStore | WebUI/chain | 是 (会话域) |
| Plan | ~/.factory/session_plans.json | PLAN-2a99826c / plan_9f475cf2d526 | agent_loop.py:780-830 (plan_development) | chain_start/execute_plan | 部分 (双 ID 格式; 16 sessions 有 plan) |
| Requirement | ~/.factory/requirements/requirements.json | req_bb2e8521ff37 | agent_loop.py:795-827 | 4/16 plans 引用 | 部分 |
| Backlog Task | workspace/projects/*/management/backlog/task.json | TASK-9d6b9101 | service.create_task (service.py:3969) → org.management.Task | WebUI/chain/finish_task_exec | **是 (Task 域唯一)**, 235 条 |
| Session Exec | ~/.factory/session_exec/<sid>.json | (无独立 id; 内嵌 plan/tasks) | ExecState (agent_loop chain_start) | chain_next/chain_status | 否 (session 级编排状态) |
| Run (会话) | console_sessions run_ids / session_exec.run_id | R1787861863011 | agent_loop.py:1484 | Run 卡/进度 | 部分 |
| 委派 Task | ~/.factory/exec/external_tasks.json | TASK-GW-47d2c100 | ExternalTaskRegistry (gateway.py:126) | gateway 控制面/gateway_status | 否 (委派控制面, 9 条) |
| Exec Request | ~/.factory/exec/requests.json | EXR-d606d3a1 | exec.store.save_request (AgentRuntime/EmployeeExecutor) | AgentRuntime | 否 (86 条) |
| Exec Result | ~/.factory/exec/execution_records.json | EXS-2f301554 | executor.record_invocation (executor.py:194) | T-9 溯源/监控 | **是 (execution 事实最全记录, 100 条)** |
| Exec Result 投影 | ~/.factory/exec/results.json | EXS-* (85) | ? (execution_records 子集投影 85/100) | CLI/API | 否 (投影) |
| Artifact | ~/.factory/exec/artifacts.json | ART-00d12545 | record_invocation 附件 (patch/report/test_result) | T-9 | 否 (挂 EXS 数字 event_refs) |
| Artifact (org) | ~/.factory/org/artifacts.json | id (24) | org workflow | org UI | 另一域 |
| Artifact (product) | ~/.factory/product/artifacts.json | id (10) | product_intelligence | product UI | 另一域 |
| Verification | 无独立存储 (verify dict 内嵌) | — | auto_verify/verification.py | gateway/chain | **无 (SSOT 未冻结)** |
| Evidence | ~/.factory/projects/ai-factory-self/evidence/ev-*.json | ev-688ab19c (9) | production_run (S14) | release/audit | 旧域 (ai-factory-self only) |
| M3 Orchestrator Task | (execution_state.json / memory) | task-e1-core | orchestrator.py (旧 CLI) | 无 (历史) | **Legacy** |
| Audit | ~/.factory/audit/audit_events.json | audit_id (5172) | AuditEmitter (service/orchestrator/agent_loop) | audit API | 最接近 canonical 事件层 |
| factory.db | ~/.factory/factory.db events | event_id (7825) | events 层 (console.viewed/org.execution/intelligence.*) | ? | **镜像/次要, canonical 待定** |

## 2. ID 方向实测 (真实数据)

```
session_id  → plan_id          16/78 sessions 有 plan (session_plans.json)
plan_id     → requirement_id   4/16 plans (session_plans 数据)
plan_id     → backlog TASK-*   53/235 tasks 带 plan_id (E2E/orch 项目; ai-factory-self 0)
backlog TASK-* → exec_ref      ai-factory-self: 0/53 done 有 exec_ref; 全仓 0/235
session_exec task → exec_ref   6 文件全部无 exec_ref 字段 (8/28 版代码) 或 None
TASK-GW-* → EXS result_id      external_tasks: 6/9 有 (真实委派完成)
EXR → EXS                      requests.json output_refs = 0/86 (无链接!)
EXS → Artifact                 artifacts event_refs = 数字序列 (audit seq), 非 EXS id 直接 FK
Artifact → Task                exec artifacts task_id = T001/T002 (exec 内部), 非 backlog TASK-*
Audit TASK_* → current TASK-*  TASK_CREATED 52 条 (创建); STARTED/COMPLETED = 0 条
Audit TASK_* → legacy task-e1* TASK_STARTED 29 / COMPLETED 30 / FAILED 5 (8/18, M3)
```

## 3. 关键结论

1. **唯一具备 "model + 独立 SSOT + CRUD API + 创建审计" 的 Task 层 = backlog TASK-*** (org.management.Task)。
2. **Execution 层无 canonical**: EXR (请求) / EXS (结果) / TASK-GW (委派控制面) / run_id (会话) 四分,
   且 EXR.output_refs 0/86 → 连 "请求→结果" 都没有链接。
3. **Artifact 有两个归属体系**: exec ART-* (挂 EXS 数字 event_refs) 与 org/product artifacts — 均不经 backlog TASK-*。
4. **Verification 无存储/无 id** — verify dict 内嵌于 gateway/exec 记录。
5. **Audit 是最接近 canonical 的事件层**, 但其 STARTED/COMPLETED 只覆盖 M3 legacy (task-e1-*), 当前 TASK-* 从未进入执行审计生命周期。
6. **factory.db** = events 镜像 (7825), 与 audit_events.json 并存, canonical authority 未声明。
