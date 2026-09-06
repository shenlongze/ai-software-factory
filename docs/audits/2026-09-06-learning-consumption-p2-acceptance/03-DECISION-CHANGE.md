# 03 — DECISION CHANGE (P2-D FINAL ACCEPTANCE, 2026-09-06)

## E2E-1 fresh 实证 (同任务上下文 "实现 java 调试功能")

- baseline (无 profile, agents A/B 同 capability 同 priority):
  select_agent → agent-A (确定性, id asc)
- 学习: agent-B 3 次真实成功 → 3 anchored exp → OBS×3 → CAND → PROM
  (admin governance) → PROFILE-agent-B-v1 (success_rate 1.0)
- after: select_agent → **agent-B** (persona 高优先)
- before != after; 变化来自 governed profile (非 random/hardcode —
  test_profile_changes_routing 断言 L313-314)
