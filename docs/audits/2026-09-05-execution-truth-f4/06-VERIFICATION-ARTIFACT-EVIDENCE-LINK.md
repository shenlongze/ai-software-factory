# 06 — VERIFICATION-ARTIFACT-EVIDENCE LINK (P0-F4 AUDIT, 2026-09-05, READ-ONLY)

> 三者真实链接现状

---

## 1. 目标链 vs 现状

```
目标:  Task → TaskRun → EXS → Artifact → Verification → Evidence → Audit
现状:  Task → run-* → EXS ──(断)── Artifact ──(断)── ver-* ──(断)── Evidence
                                        (4 套)     (F3 建)     (M3 包)
```

## 2. 关键断点

### 断点 1: EXS → Artifact

- exec ART-*: path 含 EXS-*.patch (隐式, 非 FK); task_run_id 无
- S2 art-*: 无 exs_id 字段 (只有 node_run_id)
- EXS patch 文件: 文件名 = EXS id (隐式)

### 断点 2: Artifact → Verification (ver-*)

- node_runtime.execute_node_run: create_artifact (先) → _materialize_verify (后)
  同函数内, 但 **artifact 无 verification_id 字段, ver-* 无 artifact_id 字段**
- finalize_node_run (chain): 无 Artifact 创建 (gateway 委派产物 = EXS patch, 非 art-*)

### 断点 3: Verification → Evidence

- ver-* evidence_ref: [] (F3 预留, 无人写)
- ev-*: 无 verification_id (M3 域)

## 3. S2 已预留的桥

- artifact.evidence_ids: [] (I2: Applied/Committed/Released 需 Evidence) — 字段在, 无写入方
- artifact.approval_ids: [] (I12 gates) — 同
- EVIDENCE_REQUIRED_TRANSITIONS = (APPLIED, COMMITTED, RELEASED): 定义了"何时需证据"
  — 但 transition_artifact 的 evidence 参数是 dict (内嵌), 非 evidence_ids FK 校验

## 4. 结论

- S2 契约 (I2/I12) 声明 Artifact 需 Evidence/Approval, 但无真实数据/无写入链
- exec ART-*/EXS patch (真实产物) 完全绕过 S2 lifecycle (I8 违反: 外部 Executor
  产物必须走 GENERATED→…→COMMITTED — 现状 gateway/agent_runtime 产物未走)
- ver-* (F3) 与 Artifact 零 FK

三者 = 三个独立事实, 链接全断 — F4 需先定 Artifact canonical 才能桥接。
