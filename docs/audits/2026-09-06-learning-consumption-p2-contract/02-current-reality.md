# 02 — CURRENT REALITY (P2-D CONTRACT, 2026-09-06)

| 域 | 代码 | 真实数据 | writer | 触发 |
|---|---|---|---|---|
| Experience (canonical) | ExperienceRecord/Store + bridge | 84 (M3) + 0 anchor | bridge (新) + M3 AutoLearner | finalize/release 后 (P2-C) |
| Observation | learning_engine_v2.create_observation | **0** | API 手动 (intelligence_strategy adapter) | 无生产触发 |
| Candidate | learning_engine_v2.create_candidate | **0** | 同上 (run_learning) | 无 |
| Promotion | 无独立域 (PatternLearner=聚合统计非治理) | **0** | — | — |
| Profile | learning_loop refresh/load (agent_profiles.json) | **0** | refresh (显式指令, 从未跑) | "经验学习"手动 |
| Router | capability_router.route | 读 profile (0→中性) | — | select_agent 真实 (actions.py:1188) |
| RoutingDecision | 无 canonical 记录 | **0** | — | — |

**关键: Learning Consumption 全链 0 真实数据 — 代码存在 ≠ 闭环**
