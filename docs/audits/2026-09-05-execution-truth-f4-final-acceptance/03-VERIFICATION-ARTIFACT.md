# 03 — VERIFICATION-ARTIFACT (P0-F4 ACCEPTANCE, 2026-09-05)

> F3 保持 + F4 关联验收

---

## 1. F3 未改变 (ver-* canonical 保持)

- verification_domain.materialize_verification: 唯一 writer (F3)
- 语义 PASS/FAIL/UNKNOWN 未改
- 幂等键 (task_run_id, attempt, verification_type) 未改
- NodeRun.verification = 内部快照 (F2 未升级, 仍非 SSOT)

F4 仅**增加** artifact_ids 参数 (向后兼容, 默认 [] — 旧调用不传不变)。

## 2. Verification 关系 (明确)

```
ver.task_run_id → run-*    (F3 已有)
ver.exs_id      → EXS-*    (F3 已有)
ver.artifact_ids → [art-*] (F4 新增 — 来自 canonical 收纳返回值, 非 legacy)
ver.evidence_ref → [EVD-*] (F3 预留; F4 EVD 经 verification_refs 反向可达)
```

## 3. Verification 读 canonical Artifact (非 legacy)

- ver.artifact_ids 填充来源: _absorb_execution_artifact 返回的 art-* id
  (node_runtime:448 chain / :574 execute) — 均为 create_artifact canonical 产物
- Verification 不读 legacy ART-* / EXS patch file / NodeRun.verification snapshot

## 4. EXS/Verification 独立 (合法状态)

| 状态 | 证据 |
|---|---|
| EXS SUCCESS + ver PASS | E2E-1 |
| EXS SUCCESS + ver FAIL | E2E-2 (真实 pytest 失败; 不自动 PASS) |
| EXS SUCCESS + ver UNKNOWN | F3 语义 (缺省→UNKNOWN, 不默认 PASS) |
| EXS FAILED + ver 相关 | finalize 失败分支物化 (F3) |

## 5. 结论

**Verification relation PASS | F3 保持 PASS | EXS/ver 独立 PASS**
