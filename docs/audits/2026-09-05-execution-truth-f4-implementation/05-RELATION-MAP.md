# 05 — RELATION MAP (P0-F4 IMPL, 2026-09-05)

> D3 M:N 关系落地

---

## 1. Canonical relations (达成)

```
Task (TASK-*)          task_id
  → TaskRun (run-*)     node_run_id (create_node_run task_id=)
     ├── EXS-*          (EXS.task_run_id = run-*)
     ├── Artifact[]     art.node_run_id = run-* (workflow execute 每 attempt)
     └── Verification[] ver.task_run_id = run-*
EXS-* → Artifact[]      art.exs_id = EXS-* (F4 chain 收纳)
Verification ↔ Artifact[]  ver.artifact_ids = [art-*] (D3 ver↔art)
Verification → Evidence[]  EVD.verification_refs ⊇ ver-*
Evidence 共享             attach_evidence 追加 refs
```

## 2. 非 1:1 验证

- 1 TaskRun → 多 Artifact: execute_node_run 多 attempt 多 art (E2E-4: run2/art2 +
  run3/art3); contract 允许同 EXS 多 type
- 1 Verification → 多 Evidence: EVD[] (list_evidence by ver)
- 1 Verification → 多 Artifact: artifact_ids[] (数组字段)
- Evidence 多 Verification: verification_refs[] 共享 (测试实证)
- 1 TaskRun → 多 Verification: ver.attempt 区分 (F3/F4)

## 3. FK 方向

art(→run,→exs) | ver(→run,→exs,→art[]) | EVD(→ver refs[]) — 全部显式 FK,
无 filename/audit/时间隐式关系。

## 4. 反查 (E2E-1 实证)

art → run → task (node_run_id → run.task_id); ver → art → exs;
EVD → ver → art → exs → run → task — 全链可反向追踪。
