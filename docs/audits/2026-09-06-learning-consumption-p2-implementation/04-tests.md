# 04 — TESTS (P2-D IMPL, 2026-09-06)

test_p2d_learning_consumption.py 20/20 PASS:
- Observation: derive/FAILURE signal/1exp→1obs 幂等/legacy 拒绝/missing exp
- Candidate: propose/幂等/requires obs
- Promotion: 低证据 BLOCK/approve+apply/reject/idempotent
- Profile: versioning+provenance (v1→v2)/apply 幂等/rollback/router shape
- RD: record/幂等/requires run/trace 全链 (→3 exp)
- Router consumption: **决策变化实证** (baseline agent-1 → learning agent-2)
