# 02 — RELEASE GATE (P2-A IMPL, 2026-09-06)

## gate_release 检查 (MUST 全过 → GATED; 否则 REJECTED 诚实)

1. artifact_ids 非空 (canonical art-* 存在)
2. verification_ids 非空 且 全 ver-* status==PASS
3. evidence completeness: 每 PASS ver 有 ≥1 EVD-* (verification_refs)
4. task_run_id / exs_id 非空 (provenance)

- gate 消费 verification_domain/evidence_domain store (canonical ver-*/EVD-*)
- 不自跑 pytest (release_truth 源码无 verify_pytest 调用 — 测试断言)
- NodeRun.verification snapshot 不消费

## execute_release

- require_approval (默认 True): governance approval (subject_type=release,
  subject_id=RELEASE-*) decision==APPROVED — 否则 BLOCK
- 先重跑 gate (确保最新 ver/EVD) → RELEASED
