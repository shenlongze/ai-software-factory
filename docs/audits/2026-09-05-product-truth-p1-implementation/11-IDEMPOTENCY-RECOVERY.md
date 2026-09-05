# 11 — IDEMPOTENCY / RECOVERY (P1 IMPL, 2026-09-05)

## 1. Idempotency

- create_idea/create_requirement/create_plan: idempotency_key → 返回已有 (锁内)
- create_discovery: (idea_id, title) 隐式键
- transition 同态 → 幂等返回
- E2E-3 / 单测 test_*_idempotency 实证

## 2. Recovery

- TaskRun-2 = 新 run (P0 recovery); Product Truth 单套不重复 (E2E-4)
- reverse_trace 对 recovery task 仍指向同一 PLAN/PRD/REQ/IDEA (provenance 保持)
