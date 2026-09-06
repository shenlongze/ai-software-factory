# 11 — SSOT (P2-D CONTRACT, 2026-09-06)

| Domain | Canonical SSOT (P2-D 后) | Writer | Legacy |
|---|---|---|---|
| Experience | memory/experience_store.json | ExperienceBridge | M3 AutoLearner 路径 |
| Observation | learning/observations.json (新) | ObservationService | learning_engine_v2 (intelligence/) |
| Candidate | learning/candidates.json (新) | CandidateService | learning_engine_v2 |
| Promotion | learning/promotions.json (新) | PromotionService | (无) |
| Profile | memory/agent_profiles.json | **PromotionService** (收敛 refresh) | refresh 直写 (禁) |
| RoutingDecision | learning/routing_decisions.json (新) | Router | (无) |
| intelligence/experiences | LEGACY (S9, 不碰) | — | factory-core |

- 无 JSON dual-write/mirror/event-store-as-truth
- PatternLearner/learning_loop 保留为计算组件 (非 writer authority)
