# 02 — ARTIFACT / VERIFICATION / EVIDENCE (P2 GAP AUDIT, 2026-09-06)

## 1. P0 域 (已验收 REAL)

- Artifact = art-* (S2 lifecycle, I8 收纳) → TaskRun/EXS FK
- Verification = ver-* (F3, artifact_ids) → 真实 verifier
- Evidence = EVD-* (F4, verification_refs) → 真实 verifier 输出

## 2. 后半环缺口 (P2)

- EVD-* 无下游消费者 (Release/evaluation 不读 EVD)
- release_service 不读 art-*/ver-*/EVD-* (只读 M3 run.artifacts + run.state)
- production_evaluation 读 M3 run 内嵌 verification (非 P0 ver-*)
- 断链: P0 E2E 产生的 art/ver/EVD 无法进入任何 release/evaluation

## 3. 结论

Artifact→Verification→Evidence 链 REAL 但**止于 Evidence** — 无消费端。
