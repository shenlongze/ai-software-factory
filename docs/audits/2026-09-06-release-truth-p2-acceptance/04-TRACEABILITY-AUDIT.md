# 04 — TRACEABILITY AUDIT (P2-A ACCEPTANCE, 2026-09-06)

## 1. Release→P0 (release 字段直连 FK)

RELEASE → exs_id → EXS-* → task_run_id → run-* → artifact_ids[] → art-* →
verification_ids[] → ver-* → evidence_ids[] → EVD-*

## 2. Release→Product (复用 P1 reverse_trace)

TASK-* → PLAN-* → PRD-*@v → REQ-* → DISC-* → IDEA-*

## 3. E2E-1 实证 (fresh)

RELEASE-b70e9fad RELEASED → chain [release, exs, task_run, artifact,
verification, evidence, plan...] + task/plan/prd/req/disc/idea 全对象 —
纯 canonical FK, 零推断 (测试 test_trace_release_chain + E2E-1 assert)
