# 04 — IDEMPOTENCY / FAILURE / RECOVERY (P2-C IMPL, 2026-09-06)

- 幂等: (source, source_id) — 测试 test_idempotent_source_id +
  E2E-2 (重复触发 → 仍 2 条) 实证
- failure: ver FAIL → FAILURE_PATTERN (不伪装) — test_ver_fail_not_fake_success
  + E2E-3 实证; RELEASE REJECTED → FAILURE exp (含 gate missing 理由)
- recovery: run-2 新 exp, run-1 FAIL 保留 — test_recovery_new_run_new_exp +
  E2E-4 实证
- 无 anchor → 不记录 (test_no_anchor_no_record) — 禁字符串推断
