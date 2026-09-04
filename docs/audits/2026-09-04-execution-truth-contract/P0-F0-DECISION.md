# P0-F0 — FINAL DECISION STATEMENT (2026-09-04)

> 本文件是 00-04 契约的决策摘要 — 供人工批准 (CTO/架构 Owner)
> 纯文档冻结; 批准前零代码; 批准后 F1-F4 才能进入设计/实施

---

==================================================
P0-F0 CANONICAL IDENTITY CONTRACT FREEZE
==================================================

Canonical Task:
  org.management.Task — ID TASK-*, SSOT workspace/projects/*/management/backlog/task.json,
  唯一状态写者 ManagementStore.transition_task (八态机)。(已是最完整层, 保持不变)

Canonical TaskRun:
  NodeRun (S2 Production Primitive) — ID run-*, 状态机
  PENDING→RUNNING→VERIFYING→COMPLETED/FAILED (+REPAIRING), 不可变执行事实,
  含 history/attempts/repair/artifact_id/verification; owner = node_runtime。
  ⚠️ 需 F1 补 task_id 锚点并接入 backlog 链 (CONTRACT-ONLY 至 F1)。

Canonical Execution:
  ExecutionResult (EXS-*) — 结果记录层 (record_invocation 唯一写), 挂 TaskRun 之下;
  不是运行生命周期 (那是 TaskRun), 是"一次运行的结果事实"。exec_ref 语义指向它。
  ⚠️ 需 F1 补 task_run_id/task_id 规范化锚点。

Canonical Artifact:
  Artifact (S1 artifact_lifecycle) — ID art-*, 已带 node_run_id 锚点, owner = artifact_lifecycle。
  exec ART-* 标记 ADAPTER/DERIVED (F4 投影)。org/product artifacts 属其他域, 不并入。

Canonical Verification:
  (F3 冻结归属, 实体待建) — 属于 TaskRun (NodeRun), ver-* ID, 触发者 = NodeRun 执行者
  (VERIFYING 阶段); gateway auto_verify 挂接同一语义。现状 verify dict 内嵌 = 临时, 非 SSOT。

Canonical Evidence:
  EvidenceBundle (S23 EvidenceStore) — ID ev-*, 挂 TaskRun; 现状仅旧 production_run 域使用,
  F4 接新链。

Canonical Audit:
  AuditEvent (audit_events.json) — 事件观察层 (非 domain state), AuditEmitter 唯一写,
  append-only; factory.db events = EVENT MIRROR (非 canonical authority)。

exec_ref semantics:
  REDEFINE → EXS-* (execution_id)。禁止 TASK-GW-* / EXR-* 写入 exec_ref。
  旧数据 (exec_ref=TASK-GW) 只读保留, 不迁移不清除。

EXS semantics:
  CANONICAL (Execution 结果记录层; 挂 TaskRun) — 非 TaskRun 本身
EXR semantics:
  ADAPTER → LEGACY (请求视图; output_refs 0/86 无链接; 只读保留, 不再 canonical 入口)
TASK-GW semantics:
  ADAPTER (委派控制面; 保留 gateway 控制面职责; 不是 canonical execution identity)
session_exec semantics:
  ORCHESTRATION STATE (会话编排状态; 不持有执行真相; 6 个 E2E 遗留待用户处置)

Legacy Boundary:
  M3 orchestrator (task-e1-* / 数字 project / 8-18 TASK_STARTED·COMPLETED) = LEGACY·HISTORICAL,
  只读保留, 不迁移/不重连当前 TASK-*; execution_plan T-* = HISTORICAL (STEP10 D-9 已冻)。
  禁止为"完整链路"把 legacy 硬接 canonical。

Primary Contract Decision:
  执行模型 = Model B (Task → TaskRun(NodeRun) → Execution(EXS) → Artifact → Verify → Evidence),
  其中 TaskRun canonical 载体 = 已实现的 NodeRun (S2), Execution = EXS 结果层。
  冻结链: TASK-* → run-* → EXS-* → art-* → ver-* → ev-* → audit_id。
  exec_ref = EXS (唯一语义)。session_exec 不得再被当作执行真相源。

FX-01:
  NO-GO until F0 frozen (本契约经人工批准后)
  → 批准后 F1 起可实施 (见 04 依赖图)

Next Safe Implementation:
  F1 Execution Record Normalization (run 锚 task; EXS 锚 run; exec_ref=EXS; EXR/TASK-GW 降 adapter)
  → F2 Writeback Closure → F3 Verification SSOT → F4 Artifact/Evidence Traceability

==================================================
END
==================================================

---

## 批准区 (待 shenlongze)

- [ ] 批准 Canonical Task = backlog TASK-* (无变化)
- [ ] 批准 Canonical TaskRun = NodeRun (run-*) + F1 补 task_id 锚点
- [ ] 批准 Canonical Execution = EXS-* (结果层) + F1 补 task_run_id
- [ ] 批准 exec_ref = EXS-* (REDEFINE)
- [ ] 批准 EXR/TASK-GW = ADAPTER/LEGACY; session_exec = ORCHESTRATION STATE
- [ ] 批准 Verification 归属 TaskRun (F3); Artifact canonical = S1 art-* (F4)
- [ ] 批准 Audit = audit_events.json canonical; factory.db = mirror
- [ ] 批准 Legacy Boundary (M3/8-18/task-e1-* 只读不重连)
- [ ] 批准 FX-01 NO-GO 直至本契约冻结; F1-F4 依赖次序
