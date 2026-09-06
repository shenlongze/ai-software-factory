# 08 — ROUTER CONSUMPTION CONTRACT (P2-D CONTRACT, 2026-09-06)

## D5/D7: Router = Learning 单向消费者

- 现有 capability_router (actions.py select_agent 调用) = 真实路由决策点
  (纯规则 + persona_score 排序键 + 失败安全 backend-1)
- 契约: Router 读 profile (persona_score), 经 D7 单向影响 (Learning 不改
  router 代码/规则; 只经 profile 数据)
- Profile stale/unavailable → 失败安全中性 (不 fake success, 不称 learning)
- **契约补: profile_version 必须随路由决策记录** (可审计当时用了哪个版本)
