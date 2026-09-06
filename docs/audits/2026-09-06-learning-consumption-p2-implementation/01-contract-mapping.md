# 01 — CONTRACT MAPPING (P2-D IMPL, 2026-09-06)

D1 obs canonical → OBS-* store (unique writer) | D2 obs provenance (exp anchor 必
须; legacy 拒) | D3 obs 幂等 (1 exp→1) | D4 cand canonical | D5 cand provenance
(observation_ids) | D6 cand 幂等 | D7 prom canonical | D8 prom governance
(human-in-loop; auto 阈值 ≥10 obs + rate ≥0.8) | D9 prom 幂等 | D10 profile
canonical/versioned | D11 profile provenance (promotion_id/candidate_id) |
D12 router 消费 (governed profile→persona) | D13 RD canonical | D14 RD
provenance (trace_decision 全 FK) | D15 failure/recovery | D16 REAL data
(真实 E2E) | D17 REAL learning-triggered routing impact (决策变化实证) |
D18 legacy isolation (intelligence 零读; 84 legacy exp 拒作 obs 源)
