# 01 — IDENTITY MODEL (P0-F0, 2026-09-04)

> Canonical Identity Contract — ID 前缀 / 关系方向 / FK / 反方向 / 现状

---

## 1. 冻结 ID 关系图

```
Session            sess-{hex}
  │ session_id (console_sessions)
  ▼
Plan               PLAN-{hex} | plan_{hex}      (双格式待收敛 → PLAN-* 唯一)
  │ plan_id (session_plans.json; Task.plan_id)
  ▼
Task               TASK-{hex}
  │ task_id (backlog SSOT, org.management.Task)
  ▼
TaskRun            run-{hex}        ← canonical = NodeRun (S2)
  │ task_run_id (node_runtime; 新增 task_id 锚点 = F1)
  ▼
Execution          EXS-{hex}
  │ execution_id (execution_records.json; 挂 task_run_id = F1)
  ├─► Artifact     art-{hex}        (S1 artifact_lifecycle; node_run_id 锚点已存在)
  ├─► Verification ver-{hex}        (F3 冻结; 挂 task_run_id)
  └─► Evidence     ev-{hex}         (S23 EvidenceBundle; 挂 task_run_id)
       ▼
Audit              audit_id         (audit_events.json; 只观察不拥有)
```

## 2. FK 契约 (冻结方向)

| From | To | FK 字段 | 状态 |
|---|---|---|---|
| Plan | Session | plan.session_id | CURRENT (session_plans key=session) |
| Task | Plan | task.plan_id | CURRENT (53 tasks 数据证据) |
| TaskRun | Task | **run.task_id** (NodeRun 缺 → F1 加) | CONTRACT-ONLY |
| TaskRun | Plan | run.plan_id (派生: 经 task) | CONTRACT-ONLY (不直接存) |
| Execution | TaskRun | **EXS.task_run_id** (现缺 → F1 加) | CONTRACT-ONLY |
| Execution | Task | EXS.task_id (exec models.py:114 已声明, 但数据=exec 内部 id) | CONTRACT-ONLY (需规范化) |
| Artifact | TaskRun | art.node_run_id (S1 已存在) | CURRENT (S1 域) |
| Verification | TaskRun | ver.task_run_id | CONTRACT-ONLY (F3) |
| Evidence | TaskRun | ev.task_run_id | CONTRACT-ONLY |
| Audit | 所有 | entity_id → audit event | CURRENT (但 STARTED/COMPLETED 只连 legacy) |

## 3. exec_ref 语义 (三义废除)

| 方案 | 语义 | 判定 |
|---|---|---|
| exec_ref == TASK-GW-* | chain 现写 (agent_loop.py:1581) | ✗ 错误 (委派控制面 id, 非执行事实) |
| exec_ref == EXR-* | T-9 溯源现读 (fastapi_adapter.py:913) | ✗ 错误 (请求 id, 非执行事实) |
| exec_ref == EXS-* | 本契约 | **✓ REDEFINE** |
| exec_ref == run-* | NodeRun id | 备选; 但 Task 应只关心最近结果 → EXS 更合适 |

**决策: exec_ref = REDEFINE → EXS-* (execution_id)**。
理由: Task 的"我最近一次执行结果"应指向结果事实 (EXS), 完整运行生命周期经 EXS.task_run_id → run-* 可达。
禁止再写 TASK-GW/EXR 进 exec_ref; 旧数据 exec_ref=TASK-GW 标记 legacy 不清除 (只读不改)。

## 4. 四类对象判定 (ID/Lifecycle/Producer/Consumer/Persistence)

| 对象 | ID | Lifecycle | Producer | Consumer | Persistence | Canonical? | 角色 |
|---|---|---|---|---|---|---|---|
| EXS-* | EXS-hex | 单次调用记录 (无 state 机) | record_invocation (executor.py:194) | T-9/监控 | execution_records.json (100) | **Execution 结果层** | RESULT RECORD (挂 TaskRun) |
| EXR-* | EXR-hex | 请求→无 output_refs 链接 (0/86) | exec.store / AgentRuntime | 无 | requests.json (86) | ✗ | ADAPTER (请求视图, legacy 化) |
| TASK-GW-* | TASK-GW-hex | running→done/failed | ExternalTaskRegistry (gateway.py:126) | gateway 控制面 | external_tasks.json (9) | ✗ | ADAPTER (委派控制面, 非执行事实) |
| session_exec | (无独立 id, 内嵌) | idle→running→done (无收敛) | ExecState (chain_start) | chain_next/status | session_exec/<sid>.json (6) | ✗ | ORCHESTRATION STATE (会话编排状态, 非 canonical Execution; 不持有执行真相) |
| ExecutionRecord | EXS-* | = EXS | = EXS | = EXS | = EXS | 同 EXS | RESULT RECORD (本契约: Execution=EXS 结果层; ExecutionRecord 一词并入 EXS 语义, 消除 06 契约 E 实体混淆) |
| NodeRun | run-* | PENDING→RUNNING→VERIFYING→COMPLETED/FAILED (不可变, repair loop) | node_runtime (S2) | recovery/governance/workforce | node_runtime runs/ | **✓ TaskRun CANONICAL** | EXECUTION LIFECYCLE FACT |
| ProductionRun | prun-* | PENDING→RUNNING→... | production_run (S3) | control_tower/effectiveness | production_run | 上层工作流编排 | WORKFLOW ORCHESTRATION (TaskRun 容器可选) |

## 5. 关键区分 (防再次混淆)

- **EXS = 一次执行的"结果记录"** (做过什么, 花了多少, 验证如何) — 结果层
- **NodeRun(run-*) = 一次执行的"运行事实"** (何时开始/结束, 状态迁移, attempts/repair) — 生命周期层
- 契约链: Task → NodeRun(run) → EXS(结果) → art/ver/ev
- Task.exec_ref → EXS (最近结果); 完整追溯: exec_ref(EXS).task_run_id → run-* → .task_id → TASK-*
- EXR 与 TASK-GW = 历史/适配层, 保留但 **不是 canonical execution identity**
- session_exec = 会话编排状态 (可投影 Task/TaskRun, 不持真相)
