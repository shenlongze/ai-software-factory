# 14 — FAILURE / RECOVERY (P2-D CONTRACT, 2026-09-06)

- exp 创建后 obs 失败 → 不污染生产 (obs 独立 store, 失败重试幂等)
- cand 创建后 promotion 失败 → 不改 profile
- promotion 成功但 router 消费失败 → 可观测 (RD fallback=true 记录)
- profile stale/unavailable → router 中性回退 (不 fake success)
- 每层失败安全 + 重试幂等 ((source,source_id) 或实体幂等键)
