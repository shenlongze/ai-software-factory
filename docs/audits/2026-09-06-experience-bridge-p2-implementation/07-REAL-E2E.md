# 07 — REAL E2E (P2-C IMPL, 2026-09-06)

4/4 PASS (fresh, 真实 service, 隔离 tmp):

E2E-1 Positive: IDEA→…→PLAN→TASK→run→EXS→art→ver PASS→EVD→RELEASE RELEASED
  → exp-a4dc7f26541e (execution) + exp-71881c7ffa30 (release);
  reverse exp→RELEASE→TASK→PLAN→PRD→IDEA 全 FK; canonical store 实证 2 条
E2E-2 Idempotency: 重复触发 → 仍 2 条 (execution+release 各 1)
E2E-3 Failure: ver FAIL → FAILURE exp; RELEASE REJECTED → FAILURE exp
  (含 verification 理由, 不伪装成功)
E2E-4 Recovery: run1 FAIL + run2 SUCCESS 独立共存 (旧不覆盖)
