# 01 — CONTRACT MATRIX D1-D18 (P2-D FINAL ACCEPTANCE, 2026-09-06)

| # | 要求 | 状态 | 证据 |
|---|---|---|---|
| D1 | obs canonical | PASS | OBS-* observations.json (code) + test_derive |
| D2 | obs provenance | PASS | source_exp/task_run/exs/release anchor; legacy 拒 (test_reject_legacy) |
| D3 | obs 幂等 | PASS | 1 exp→1 obs (test_idempotent + E2E-2) |
| D4 | cand canonical | PASS | CAND-* candidates.json (code) |
| D5 | cand provenance | PASS | observation_ids (test_propose) |
| D6 | cand 幂等 | PASS | agent+cap 唯一 (test_idempotent) |
| D7 | prom canonical | PASS | PROM-* promotions.json (code) |
| D8 | prom governance | PASS | governance approval; 低证据 BLOCK (test_gate + E2E-3) |
| D9 | prom 幂等 | PASS | 1 cand→1 prom (test_idempotent) |
| D10 | profile versioned | PASS | PROFILE-v1→v2; 历史保留 (test_versioning) |
| D11 | profile provenance | PASS | promotion_id/candidate_id (test_versioning) |
| D12 | router 消费 | PASS | select_agent→router_profiles→persona (E2E-1 决策变化) |
| D13 | RD canonical | PASS | RD-* routing_decisions.json (code) |
| D14 | RD provenance | PASS | trace_decision 全 FK (test_trace + E2E-1) |
| D15 | failure/recovery | PASS | gate BLOCK/legacy 拒/失败安全回退 (E2E-3) |
| D16 | REAL data | PASS | E2E 真实 canonical (tmp 隔离; 真实库 0 如实) |
| D17 | REAL routing impact | PASS | E2E-1 + test_profile_changes_routing (before≠after) |
| D18 | legacy isolation | PASS | intelligence 零读; 84 legacy 拒作 obs 源 |

**D1-D18 全 PASS**
