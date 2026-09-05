# 00 — F4 IMPLEMENTATION (2026-09-05)

> Sprint: P0-F4 Artifact/Evidence/I8 Production Closure | Status: PASS
> 基线: 794e24d7 (F3) | 依据: F4 Decision Freeze (D1-D4 APPROVED)

---

## 1. Objective

把真实生产链从 Verification 闭合到 canonical Artifact (art-*) 与 canonical
Evidence (EVD-*), 落实 I8 Production Core Hard Constraint。

## 2. Before

- S2 art-* 完整 domain 但 0 真实数据 (外部产物走旁路: exec ART-*/EXS patch)
- finalize_node_run (chain 生产路径) 不产 art-*, 只物化 ver-*
- ver-* (F3) 无 artifact 关联; Evidence 仅 M3 ev-* (approval package)

## 3. Changes

- artifact_lifecycle.py: create_artifact + exs_id + 幂等 (exs_id 提供时
  同 run+exs+type → 同 art-*; node_run_id-only 保持 I10 每 attempt 新)
- node_runtime.py: +_absorb_execution_artifact (I8: finalize 成功时收纳 EXS
  产物为 art-* report; 幂等); +_attach_verify_evidence (真实 verifier 输出 →
  EVD-*; 无内容不伪造); finalize_node_run +exs_id/output/artifact_root 参数;
  execute_node_run ver↔art + EVD attach
- evidence_domain.py (新): EVD-* Evidence SSOT (materialize/list/get/count/attach)
- verification_domain.py: materialize_verification +artifact_ids (D3 ver↔art)
- agent_loop.py: 两处 finalize 调用传 exs_id/output/artifact_root (I8 接线)
- cli_factory.py: +artifact/evd 子命令 (list/get)
- tests/console/test_p0_f4_artifact_evidence.py (新, 14)

## 4. Canonical chain (达成)

```
TASK-* → run-* → EXS-* → art-* → ver-* → EVD-* → Audit
```

每级真实持久化 (E2E-1 实证全 ID 反查)。

## 5. 报告目录

docs/audits/2026-09-05-execution-truth-f4-implementation/ (本目录 00-09)
