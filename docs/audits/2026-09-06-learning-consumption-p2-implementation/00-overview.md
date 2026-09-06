# 00 — OVERVIEW (P2-D IMPLEMENTATION, 2026-09-06)

> Sprint: P2-D Learning Consumption | Status: PASS (Implementation — 停等 Final Acceptance)
> 基线: 6853439c (P2-C) | 依据: P2-D Contract Freeze 22 份

## 实现 (最小, 契约驱动)
- factory-console/learning_truth.py (新): 5 canonical 域
  - OBS-* (observations.json): derive_observation (1 exp→1 obs; legacy 拒绝)
  - CAND-* (candidates.json): propose_candidate (obs 依据; 幂等)
  - PROM-* (promotions.json): propose/approve/reject (governance human-in-loop;
    auto 阈值; 低证据 gate BLOCK)
  - PROFILE-{agent}-vN (profiles.json): apply_promotion (versioned immutable;
    rollback); router_profiles() → {agent_id: {success_rate}} 兼容 shape
  - RD-* (routing_decisions.json): record_routing_decision (1 run→1); trace_decision
- governance_service.py: + "learning_promotion" subject/policy (最小增量)
- actions.py select_agent: 画像源 = governed profile 优先, legacy 回退
  (router 算法零修改 — 契约 D5/D7)
- cli_factory.py: factory learning observation/candidate/promotion/profile/decision
- tests/console/test_p2d_learning_consumption.py (20)

## 契约 compliance: D1-D18 见 17-acceptance-matrix.md
