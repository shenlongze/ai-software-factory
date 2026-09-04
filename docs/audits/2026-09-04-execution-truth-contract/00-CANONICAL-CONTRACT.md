# 00 — CANONICAL CONTRACT (P0-F0 Freeze, 2026-09-04)

> 性质: Canonical Identity & Ownership Contract Freeze — 纯文档, ZERO CODE
> 前置: docs/audits/2026-09-04-execution-truth-root-cause/ (Forensic 证据)
> 依据: STEP10 Domain Freeze (2026-09-02, 人工批准) + Production Core 代码 (S2-S5) + Runtime 取证
> 决策类型: F0 — 谁是谁 / 谁拥有谁 / 谁能改谁 / 谁是唯一事实来源
> 注意: 本文件是契约, 不是实现; 所有"未来接入"= CONTRACT-ONLY, 不视为已实施

---

## 0. 契约目标

在确认 ≥6 套 Task/Execution ledger 并存后, 冻结唯一正确的
`Session → Plan → Task → TaskRun → Execution → Artifact → Verification → Evidence → Audit`
身份链与 ownership。

冻结前禁止 FX-01 直接实施 (会给未冻结身份打补丁)。

---

## 1. Canonical Domain Model 决策

### 评估 (Forensic + Production Core 代码)

| 候选 | 描述 | 证据 | 判定 |
|---|---|---|---|
| Model A: Task→Execution | 两层, 无 run | STEP10 05 契约 Task→Run 已有 | 缺 run 层语义, 与 S2 NodeRun 冲突 |
| Model B: Task→TaskRun→Execution | 三层 | 需新建 TaskRun | **采用 (TaskRun = NodeRun 语义统一)** |
| Model C: Task→NodeRun→Execution | NodeRun 为 run | node_runtime.py (S2) 已实现 run-* | TaskRun 概念落地=NodeRun |
| Model D: +Artifact 链 | 完整 | artifact_lifecycle (S1) 已实现 | 契约含此链 |

### 决策: **Model B, 其中 TaskRun 的 canonical 实现载体 = NodeRun (S2)**

理由 (不是"因为 EXS 最完整"):
1. **NodeRun 已是 AI Factory 自己冻结的 Production Primitive #2**: node_runtime.py:1-13 明示
   "NodeRun: Node 的一次不可变执行事实", 状态机 PENDING→RUNNING→VERIFYING→COMPLETED/FAILED,
   且 audit event 类型已注册 (NODE_RUN_CREATED/STARTED/VERIFYING/COMPLETED/FAILED, audit_event.py:68-72)。
2. **NodeRun 是执行生命周期事实 (execution lifecycle)**: 含 started_at/completed_at/history/attempts/repair
   (node_runtime.py:259-340 Repair Loop), 语义 = "一次任务执行运行" = TaskRun。
3. **EXS 是执行结果记录 (result record)**, 不是运行生命周期: EXS-* 无 attempts/repair/state 机,
   是 record_invocation 一次调用产出 (executor.py:194-230) — 结果层, 非 run 层。
4. NodeRun 缺 task_id 锚点 / 未接 backlog → 这是 F1 要补的契约缺口 (CONTRACT-ONLY 标记), 不是选型缺陷。

### Canonical Chain (冻结)

```
Session (sess-*)                会话事实
  └─ Plan (PLAN-*/plan_*)       计划事实 (SSOT: session_plans.json)
       └─ Task (TASK-*)         执行任务事实 (SSOT: backlog, org.management.Task)
            └─ TaskRun (run-*)  一次运行事实  ← canonical = NodeRun (S2)
                 ├─ Execution (EXS-*)   执行结果记录 (结果层, 挂 TaskRun)
                 ├─ Artifact (art-*)    产物 (S1 artifact_lifecycle, 挂 NodeRun/Execution)
                 ├─ Verification (ver-*) 验证 (挂 NodeRun/Execution, F3 冻结归属)
                 └─ Evidence (ev-*)     证据包 (S23, 挂 TaskRun/NodeRun)
                     └─ Audit (audit_id) 事件观察 (所有域动作落 audit_events.json)
```

### 关键语义声明

- **Task ≠ TaskRun ≠ Execution**: Task = 要做什么 (意图/状态), TaskRun = 一次运行 (生命周期/事实),
  Execution = 运行结果 (产出/记录)。三者在 STEP10 03 契约中曾被合并进 "Run" 一词, 本契约显式拆分。
- **ExecutionRecord (EXS) = 结果层**: canonical 归属 TaskRun; 一个 TaskRun 可有多次 Execution 尝试
  (repair loop attempts), 但 canonical 只认最终状态链。
- **exec_ref 三义废除**: 见 §4。

---

## 2. Canonical Truth 表 (谁是谁)

| Domain | Canonical Entity | Canonical ID | SSOT/Storage | 现状 |
|---|---|---|---|---|
| Session | Session | sess-* | console_sessions.json | CURRENT |
| Plan | Plan | PLAN-* | session_plans.json | CURRENT (双格式待收敛: PLAN-*/plan_*) |
| Requirement | Requirement | req_* | requirements/requirements.json | PARTIAL (无下游全链) |
| Task | org.management.Task | TASK-* | workspace backlog task.json | **CANONICAL (唯一完整)** |
| TaskRun | NodeRun | run-* | node_runtime runs/ | **DECLARED CANONICAL (F1 接入 backlog)** |
| Execution | ExecutionResult | EXS-* | exec execution_records.json | RESULT-RECORD (挂 TaskRun 后成链) |
| Artifact | Artifact (S1) | art-* | artifact_lifecycle | PARTIAL (exec 域 ART-* 需迁移语义) |
| Verification | Verification (F3) | ver-* (待建) | 无独立 SSOT (冻结归属) | **MISSING (F3)** |
| Evidence | EvidenceBundle | ev-* | EvidenceStore (S23) | PARTIAL (仅旧 production_run 域) |
| Audit | AuditEvent | audit_id | audit_events.json | OBSERVATION (事件投影, 非 domain state) |

> 注意: 现有 exec/artifacts.json 的 ART-* (225) 是 Execution 结果附产物 (挂 EXS 数字 event_refs);
> 契约声明 canonical Artifact 以 S1 artifact_lifecycle 的 art-* 为准 (挂 NodeRun), exec ART-* 标记
> ADAPTER/DERIVED (F4 处理), 不得双写 canonical。
