# 01 — ARTIFACT CONTRACT (P0-F4 AUDIT, 2026-09-05, READ-ONLY)

> 不冻结新 contract (F4 NO-GO); 记录现状供架构决策

---

## 1. S2 Artifact Lifecycle (artifact_lifecycle.py) — 候选 canonical

- identity: `art-{uuid4.hex[:12]}` (artifact_lifecycle.py:117)
- 持久化: `_artifacts_dir(root) / id[:2] / {id}.json` (前缀分片, I10 不可变)
- 生命周期: GENERATED→STAGED→REVIEWED→APPROVED→APPLIED→VALIDATED→COMMITTED→RELEASED
  + FAILED/REJECTED/REPAIRING/BLOCKED/CANCELLED (失败态)
- APPROVAL_GATES: APPLIED/COMMITTED/RELEASED (I12 需 Approval)
- EVIDENCE_REQUIRED_TRANSITIONS: APPLIED/COMMITTED/RELEASED (I2)
- 12 Invariants (I1-I12): 不可变/审计/审批/证据前置/绕过禁止
- 关联: node_run_id (F1 run-* 兼容), project_id, producer, evidence_ids [], approval_ids []
- 创建点: execute_node_run (node_runtime.py:433, workflow 域) + rollback_service
- 真实数据: **0** (仅测试/E2E tmp)

## 2. exec AgentRuntime Artifact (exec/artifacts.json) — 真实但无生命周期

- identity: `ART-{hex8}` (exec/models.py:36)
- 类型: patch/report/test_result (225 = 75×3)
- 持久化: exec/artifacts.json {artifacts: {ART-*: {id, type, task_id, employee_id,
  agent_id, event_refs, path, created_at}}}
- task_id: T001-5/task-mat/task-cli/task-e1-* (exec 内部 + M3 legacy)
- 与 EXS: 仅 path (`/exec/EXS-*.patch`/`.test.txt`) 或 event_refs 隐式
- 无 run-*/TASK-* canonical 锚; 无 lifecycle

## 3. org ArtifactRegistry (org/artifacts.json) — M3/S14 项目域

- identity: `P-{project_id}-R{run_ms}-{TYPE}` (如 P-17ef31e5-R1788175215875-CODE)
- 类型: idea/design/code 等 (role 绑定: product-manager/architect/developer)
- 持久化: org/artifacts.json (24 条)
- 关联: project_id + stage_id (STG-P-…-DEV); task_id 全空
- 属 org 域 M3/S14 项目产物 (非 backlog Task 执行链)

## 4. EXS patch 文件 (exec/patches/) — 外置产物

- 75 个真实 patch 文件, 文件名 = EXS id (隐式 FK)
- 无 domain 记录 (仅文件名)

## 5. 关系现状

Artifact ↔ TaskRun: 仅 S2 有 node_run_id 字段 (但 0 真实); exec/org 无
Artifact ↔ EXS: 仅 exec path 隐式; S2/org 无
Artifact ↔ Verification: 无任何套有 ver-* 引用 (S2 evidence_ids 是给 Evidence 预留, 非 ver-*)
