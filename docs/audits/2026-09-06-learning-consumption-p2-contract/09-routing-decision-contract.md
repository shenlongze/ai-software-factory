# 09 — ROUTING DECISION CONTRACT (P2-D CONTRACT, 2026-09-06)

## D6: RoutingDecision 必须成为可审计事实 (现无 canonical — MISSING)

- ID: RD-{hex8}; SSOT: <root>/learning/routing_decisions.json
- Writer: Router (route 执行时记录 — 唯一)
- 字段: task_id/task_run_id + objective/task_class + selected_agent +
  profile_version (当时) + persona_score + candidates[] + fallback (bool) +
  reason + timestamp
- **MOST IMPORTANT**: 回答 "为什么选这个 Agent" — 可回溯:
  RD → profile_version → PROM → CAND → OBS → exp → EXS/run/RELEASE

## Reality: MISSING (现 route 只返回 resource_id, 无持久化) — P2-D 新建
