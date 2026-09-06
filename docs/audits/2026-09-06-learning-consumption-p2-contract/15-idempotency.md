# 15 — IDEMPOTENCY (P2-D CONTRACT, 2026-09-06)

- obs: (source_type, source_id, window) 唯一 — 同批 exp 重算 → 1 obs
- cand: (observation_ids 排序哈希) 唯一 — 同 obs 组 → 1 cand
- promo: (candidate_id) 唯一 — 同 cand → 1 promo
- profile 变更: (candidate_id) — 同 promo 不重复 bump version
- RD: (task_run_id) 唯一 (一次路由一记录)
- 禁 timestamp-only/random/array-position 作幂等键
