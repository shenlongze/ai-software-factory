# 00 — F1 PRE-IMPLEMENTATION AUDIT (2026-09-04)

> 状态: AUDIT COMPLETE — STOP (P0 contract conflict, 待人工决策)
> 本文件是 F1 实施前审计, 不是完成报告; 未修改任何代码。

---

## 1. 审计结论摘要

F1 目标 (F0 冻结): 形成 `Task(TASK-*) → TaskRun(NodeRun/run-*) → EXS(EXS-*)` 显式身份链,
`Task.exec_ref = EXS.execution_id`。

审计发现 **生产委派链 (chain→gateway) 从未创建 NodeRun**, 且 **NodeRun 与 backlog Task 之间
无桥接设计**。F0 将 TaskRun 冻结为 NodeRun, 但代码现实是:

```
生产主链 (Web 会话):  Task(TASK-*) → chain_next → gateway_execute → TASK-GW registry → EXS
NodeRun 域 (S2/S3):   workflow → register_node → create_node_run → execute_node_run
                        ↑ 从不被 gateway/chain 路径创建; 绑定 Node 定义 (非 backlog Task)
```

两条执行路径的 run 语义不同, 若不先定 bridge 策略, 直接给 NodeRun 加 task_id 字段 =
"给断链打补丁" (F0 明令禁止)。

---

## 2. 关键代码事实

### 2.1 NodeRun (node_runtime.py, S2)

- ID: `run-{uuid12}` (node_runtime.py:136)
- 字段: run_id/node_id/state/input/trigger/executor/agent/model/artifact_id/verification/
  failure_reason/started_at/completed_at/created_at/history (**无 task_id**)
- 状态机: PENDING→RUNNING→VERIFYING→COMPLETED/FAILED (+REPAIRING), NODERUN_TRANSITIONS
- 创建前置: **必须 register_node (get_node 不存在 → NodeError)** (node_runtime.py:133-135)
- 创建路径: 仅 production_run.execute_production_run (production_run.py:457-474)
- 消费: recovery/governance/workforce/effectiveness/health (均 S2 workflow 域)

### 2.2 Backlog Task (org.management.Task)

- ID: TASK-{hex10}; 字段含 plan_id/exec_ref/exec_result/history (management.py:141-166)
- 唯一写者: ManagementStore 经 transition_task (service.create_task/start_task_exec/finish_task_exec)
- exec_ref 语义: model 注释="exec request id EXR-*/引擎任务 id" (management.py:148) — 与 F0 (=EXS) 冲突

### 2.3 EXS — 两个存储、两种格式

| 存储 | 格式 | 写者 | 数量 |
|---|---|---|---|
| exec/execution_records.json | 扁平 dict (record_invocation) | gateway (external_executor/executor.py:194) | 100 |
| exec/results.json | pydantic ExecutionResult (exec store) | AgentRuntime (factory-exec) | 85 (与上 85 重叠) |

- ExecutionResult model (exec/models.py:171): id/request_id/status/artifacts/usage/report/error/
  duration/context_score/evaluation/created_at (**无 task_run_id; 无 task_id 直接字段**)
- ExecutionRequest model: 有 task_id (可空) (exec/models.py:102-130)
- record_invocation 记录: 无 task_id/task_run_id (只有 task=prompt 文本)
- Artifact model: 有 task_id (exec/models.py:140-167)

### 2.4 gateway (external_executor/gateway.py)

- `gateway_execute(task, data_dir, project_id, agent_id, skills, max_retry, verify_hook, timeout)`
  — **无 task_id / task_run_id 参数** (gateway.py:91-101)
- 内部: ExternalTaskRegistry.create → TASK-GW-* (gateway.py:126-129) → executor.run →
  record_invocation → EXS (176-184) → verify → reg.update
- 生产调用: agent_loop.py:595 (_chain_auto_worker), agent_loop.py:1572 (chain_next _exec_fn)

### 2.5 agent_loop chain (生产主链)

- chain_start (agent_loop.py:1409): 建 backlog TASK (backlog_id 映射) + ExecState.start
- chain_next (agent_loop.py:1530): ExecState.next(_exec_fn) → gateway_execute
- **_exec_fn 返回 exec_ref = r.task_id = TASK-GW-*** (agent_loop.py:1581) → 违反 F0
- 回写: finish_task_exec (仅 backlog_id 非空; 1605) exec_ref=_exec_ref (TASK-GW 或 _bid)

### 2.6 exec_ref 全量写点 (生产, 违反 F0)

| 位置 | 写入值 | 语义 |
|---|---|---|
| agent_loop.py:603 (_chain_auto_worker) | r.task_id = TASK-GW-* | ✗ |
| agent_loop.py:1581 (chain_next) | r.task_id = TASK-GW-* | ✗ |
| cli_factory.py:2598 (bridge) | f"bridge:{tid}" | ✗ (自有格式) |
| cli_factory.py:2624 (bridge) | result.request_id = EXR-* | ✗ |
| service.start_task_exec/finish_task_exec | 透传 (由调用方给) | 中性 |
| exec_state.py:160 (session_exec 副本) | result.exec_ref 透传 | 取决于 _exec_fn |

### 2.7 exec_ref 读点 (T-9 溯源按 EXR 读)

- fastapi_adapter.py:913-918 `_task_exec_trace`: exec_ref → requests.json (EXR-*) → output_refs → EXS
  — 与 F0 (exec_ref=EXS) 冲突, 需改为 exec_ref → execution_records/EXS 直查

---

## 3. F0→F1 集成冲突 (P0, 需人工决策)

### 冲突 1: 生产委派链无 NodeRun, NodeRun 需 Node 定义

F0 冻结 TaskRun=NodeRun。但 chain→gateway 委派路径不创建 NodeRun; 且 create_node_run
强制要求 Node 定义存在 (register_node), 而 backlog Task 不是 S2 Node。

→ F1 若要"创建阶段形成 run-* 锚", 必须决策 bridge 方式:
  A. 每个 backlog task 委派时自动注册共享 Node (如 type="task-execution") → create_node_run(task_id)
  B. 保持 gateway 委派路径现状 (TASK-GW registry 为运行控制面 + EXS 为结果),
     NodeRun 作为 TaskRun 契约实体由 F2 convergence 接入 — F1 仅冻结字段/语义层

### 冲突 2: TaskRun 是否应替换 TASK-GW registry 的"运行控制面"角色?

TASK-GW registry (ExternalTaskRegistry) 实际承担运行状态 (running→done/failed + retry)。
F0 定其为 ADAPTER。F1 需明确: ADAPTER 是否继续由 gateway 内部使用 (推荐), 不迁移为 canonical。

### 冲突 3: 执行记录双存储 (execution_records.json vs results.json)

同一 EXS-* 事实写两处、格式不同。F1 需决策 canonical 持久化点 (推荐 execution_records.json =
gateway 委派链; results.json = factory-exec AgentRuntime 域, 标 ADAPTER), 但**不动历史数据**。

---

## 4. F1 最小变更设计 (待批准, 未实施)

### 4.1 node_runtime.py
- create_node_run 增 `task_id: str = ""` 参数 → run["task_id"] (向后兼容, 空=未锚)
- 若 bridge 选 A: 增加辅助 `ensure_task_node` 或允许 task-anchored run (需决策)

### 4.2 exec models (factory-exec/exec/models.py)
- ExecutionResult 增 `task_run_id: str = ""` (+ `task_id` 透传可选) — 默认空, 旧数据兼容

### 4.3 record_invocation (external_executor/executor.py)
- 增 task_id/task_run_id 可选参 → EXS 扁平记录加字段 (向后兼容)

### 4.4 gateway_execute (gateway.py)
- 增 `task_id: str = ""` / `task_run_id: str = ""` 可选参 → 透传 record_invocation

### 4.5 agent_loop chain (生产主链)
- _exec_fn (1581/603): exec_ref 改 `r.result_id` (EXS-*) 而非 r.task_id (TASK-GW)
- chain_next/auto worker: 若 bridge A — 委派前 create_node_run(task_id=backlog_id)
  → gateway_execute(task_id, task_run_id=run_id) → st.task.exec_ref=EXS

### 4.6 fastapi_adapter T-9 溯源
- _task_exec_trace: exec_ref 先按 EXS (execution_records/results) 直查; EXR 查询仅 legacy 兼容

### 4.7 测试 (关系测试 A-F)
- NodeRun.task_id==Task.task_id / EXS.task_run_id==NodeRun.run_id /
  Task.exec_ref==EXS.execution_id / round-trip / idempotency / legacy isolation

### 4.8 不改
- 历史数据 / EXR 提升 / TASK-GW 删除 / orchestrator M3 / WebUI / session_exec convergence /
  Verification / Artifact lifecycle / Release / Learning

---

## 5. 停止条件触发

按 F1 任务书 §14: 发现 "P0 contract conflict (TaskRun 载体与生产链无桥)" →
STOP, REPORT, 不做代码修改。本文件为审计产物。

待决策项 (见汇报):
1. NodeRun bridge 策略: A (chain 自动注册共享 Node + create_node_run) vs B (F1 仅冻结字段/语义,
   NodeRun 生产接入留 F2)
2. canonical EXS 持久化点确认 (execution_records.json vs results.json)
3. exec_ref=TASK-GW 现存写入 (agent_loop/cli bridge) 是否 F1 一并修正 (推荐是 — 属 exec_ref 语义清理)
