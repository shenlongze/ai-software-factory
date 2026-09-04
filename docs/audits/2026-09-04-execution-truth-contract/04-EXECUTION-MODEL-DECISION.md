# 04 — EXECUTION MODEL DECISION (P0-F0, 2026-09-04)

> 执行模型选型 + Audit Contract + Verification/Artifact 归属 + Recursive Task 兼容
> 只冻结契约, 不实现。

---

## 1. 执行模型决策: Task → NodeRun(TaskRun) → EXS(结果)

### 为什么 NodeRun = TaskRun canonical (不是 EXS / 不是新造)

1. **NodeRun 已经是"运行生命周期事实"**: node_runtime.py:6 "NodeRun: Node 的一次不可变执行事实
   (状态机 PENDING→RUNNING→VERIFYING→COMPLETED/FAILED)"; history append-only; attempts/repair 循环
   (node_runtime.py:259-340) — 这正是 TaskRun 应有的语义。
2. **audit 事件已冻结**: NODE_RUN_CREATED/STARTED/VERIFYING/COMPLETED/FAILED (audit_event.py:68-72)
   — AI Factory 已为 TaskRun 事件预留类型, 只是未接 backlog Task。
3. **EXS 语义 = 结果记录**: 无状态机/无 attempts; record_invocation 一次性写; 放"运行层"会丢失
   生命周期 (何时开始/结束/修复/验证) — EXS 放结果层, 挂 TaskRun 之下。
4. **与 STEP10 05 契约兼容**: "Task → Run → {ExecutionRecord, Artifact, Verification}" —
   本契约把 Run 细化为 TaskRun(NodeRun) + Execution(EXS 结果) 两层, 不推翻冻结方向。

### 单 Task 多执行 (repair/retry/重跑) 语义

```
Task (TASK-*)
  └─ TaskRun v1 (run-*)   attempts: [A(FAIL, art-a), B(PASS, art-b)]  ← NodeRun repair loop
       └─ EXS-* (结果记录, 最终)
  └─ TaskRun v2 (run-*)   (用户重跑) → 新 run + 新 EXS
```
Task 状态由最近 TaskRun 终态 + Verification 决定; 历史 runs 保留 (不可变)。

## 2. Audit Contract (冻结)

### 原则: Domain State ≠ Audit Event ≠ Observation

- **Domain State**: 实体当前状态 (Task.status, NodeRun.state) — 由各域 Owner 维护 (见 02)
- **Audit Event**: 状态/动作的 append-only 事件记录 (谁/何时/做了什么/证据) — AuditEmitter 唯一写
- **Observation**: 只读投影/镜像 (factory.db, session_exec 展示) — 非事实源

### Canonical Task 生命周期事件 (谁产生)

| 事件 | 产生者 | 触发 |
|---|---|---|
| TASK_CREATED | service.create_task | backlog 创建 (已实现 service.py:4035) |
| TASK_STARTED | (缺) — 契约: service.start_task_exec 或 NodeRun RUNNING 桥 | F1/F2 补: TaskRun 启动时发 |
| TASK_RUN_CREATED | NodeRun create | F1 接入 backlog 后 |
| TASK_RUN_COMPLETED | NodeRun COMPLETED | 经桥 |
| TASK_VERIFICATION_* | Verification (F3) | NodeRun VERIFYING 阶段 |
| TASK_COMPLETED | **service.finish_task_exec(success=True)** | TaskRun 完成 + Verify 通过 → 唯一合法 (F2) |
| TASK_FAILED / TASK_BLOCKED / TASK_CANCELLED | service.finish_task_exec | F2 |

- **禁止**: M3 orchestrator 继续对当前 TASK-* 发 STARTED/COMPLETED (legacy 隔离)
- 现有 audit 的 legacy STARTED/COMPLETED 保持只读

## 3. Verification Contract (F3 冻结归属)

### Verification 属于谁?

**决策: Verification 属于 TaskRun (NodeRun), 由 TaskRun 执行者拥有与触发。**

理由:
- verification 验证的是"这次运行 (run) 的产物" — 不是 Task (任务可多 run), 不是 Artifact (产物先于验证)
- NodeRun 状态机已含 VERIFYING 阶段 (execute_node_run), 天然 owner
- gateway 委派路径 (auto_verify) 应挂接为同一 verification 语义 (不建第二事实源)

### Verification 记录契约 (F3 待建)

```
verification_id: ver-{hex}
subject: task_run_id (run-*)
result: PASS | FAIL | INCONCLUSIVE | BLOCKED | unknown
method: pytest | syntax | verify_hook | manual | auto
evidence: 指向 test_result artifact / logs
timestamp / executor
```
SSOT: 待 F3 建 (NodeRun verification 字段扩展 或 独立 store); 现状 gateway verify dict = 临时。

## 4. Artifact Contract (F4 归属)

### 决策: Artifact 属于 TaskRun (NodeRun), 由 Execution (EXS) 结果挂接

```
TaskRun (run-*) ──produces──► Artifact (art-*, S1 artifact_lifecycle, node_run_id 已存在)
    ▲
Execution (EXS) ──result──► (EXS 记录引用 art; 每次 repair 尝试新 art — NodeRun attempts)
```

- Canonical Artifact id = **art-*** (S1 artifact_lifecycle), 已带 node_run_id 锚点 → 契约缺口最小
- exec ART-* (225) = EXS 附产物记录 → 标记 ADAPTER/DERIVED; F4 将其映射/投影到 S1 art-* 语义
  (不迁移历史, 只冻结新写方向)
- org/product artifacts (24/10) = 其他域 (org 工作流/产品智能), 不并入 canonical 执行链

## 5. Recursive Task 兼容

### 决策: 父任务 = 编排/汇总, 叶子任务 = 执行

```
Parent Task (TASK-*)
  ├─ 策略: decompose → 子 Task (子树)
  └─ TaskRun: 若父任务自身有执行 → 用 Coordinator TaskRun (编排型: 不产代码产物,
      产计划/汇总/验证报告) — 语义复用 NodeRun, executor=decomposer/aggregator
Child Task (TASK-*)  → 各自 TaskRun → EXS → art/ver/ev
```

- 一个 Task 可有 TaskRun 序列 (重跑/多轮); 子任务完成后父任务经 reconcile 聚合
- 契约不要求"只 leaf 执行": parent 可作编排运行 (coordinator execution), 但产物类型区分
  (code_change vs report/aggregation)
- 现状 task_tree.py 只支持 2 层扁平 → 递归 Tree 是 FUTURE (能力矩阵已标), 本契约保证身份模型
  向上兼容 (每层 Task 同构, 每 TaskRun 独立)

## 6. 依赖图 (F1→F4)

```
F1 Execution Record Normalization
   ├─ NodeRun 增 task_id 锚点 (run → TASK-*)
   ├─ EXS 增 task_run_id/task_id 规范化 (结果挂 run)
   ├─ EXR/TASK-GW 标记 adapter/legacy (不写 canonical)
   └─ exec_ref 写 EXS (废除 TASK-GW/EXR 写入)

F2 Execution Writeback Closure        ← 依赖 F1
   ├─ chain_next/auto worker: gateway 返回 → 建/挂 NodeRun → 回写 EXS → st.task.exec_ref=EXS
   ├─ finish_task_exec 只在 TaskRun 完成 + verify 后 (backlog_id 空 → 响亮告警)
   ├─ session_exec 收敛 (终态事件/超时/abandoned)
   └─ Task 生命周期 audit 补齐 (STARTED/RUN_COMPLETED/COMPLETED)

F3 Verification SSOT                  ← 依赖 F1 (run 身份稳定)
   ├─ Verification 归属 TaskRun; ver-* SSOT
   └─ gateway auto_verify → 同一 verification 事实源

F4 Artifact/Evidence Traceability     ← 依赖 F1/F3
   ├─ exec ART-* 投影到 S1 art-* (新写方向)
   ├─ Evidence ev-* 挂 TaskRun
   └─ T-9 溯源按新链 (Task→run→EXS→art/ver/ev)
```
