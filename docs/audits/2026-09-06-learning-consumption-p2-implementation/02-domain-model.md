# 02 — DOMAIN MODEL (P2-D IMPL, 2026-09-06)

| Domain | ID | SSOT | Writer |
|---|---|---|---|
| Observation | OBS-{hex12} | learning/observations.json | derive_observation |
| Candidate | CAND-{hex12} | learning/candidates.json | propose_candidate |
| Promotion | PROM-{hex8} | learning/promotions.json | propose/approve/reject_promotion |
| Profile | PROFILE-{agent}-v{N} | learning/profiles.json | apply_promotion (唯一) |
| RoutingDecision | RD-{hex8} | learning/routing_decisions.json | record_routing_decision |

- Profile lifecycle: ACTIVE (current) / 历史版本保留; rollback 切 current
- Prom lifecycle: PROPOSED→APPROVED→APPLIED; REJECTED/REVOKED/FAILED
- RD: CREATED (1 run→1 幂等)
- 全 store 独立 <root>/learning/ (与 legacy intelligence/learning_engine_v2 隔离)
