# 03 — IMPLEMENTATION (P2-D IMPL, 2026-09-06)

- learning_truth.py: 5 域 services + 幂等 (obs: source_exp; cand: agent+cap
  PROPOSED/APPROVED; prom: cand; profile: prom; rd: run) + trace_decision
  (RD→profile→PROM→CAND→OBS→exp 纯 FK)
- derive_observation 拒绝无 anchor exp (legacy 84 禁作学习输入 — 契约 D12)
- propose_candidate 需 obs (禁凭空建议)
- approve_promotion: governance approval (subject learning_promotion, policy
  learning_promotion medium, human); auto_allowed 仅 ≥10 obs + rate≥0.8
- apply_promotion: 1 prom → 1 version; success_rate = capability score 均值
  (router persona 消费字段); 幂等 APPLIED 短路
- router 消费: select_agent → router_profiles() (governed) → 无则 legacy
  agent_profiles → CapabilityRouter (persona_score 从 success_rate 映射 —
  零算法修改)
- RD 接线: record_routing_decision (显式; 幂等 1 run→1)
- CLI: learning 5 list 视图 (只读 canonical)
