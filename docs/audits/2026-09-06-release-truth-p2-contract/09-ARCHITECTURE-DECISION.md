# 09 — ARCHITECTURE DECISION (P2-A CONTRACT, 2026-09-06)

## AD-1: rel-* 保留 vs RELEASE-* 新 ID → **Option B**

| 维度 | Option A (rel-* 升级) | Option B (RELEASE-* 新) |
|---|---|---|
| compatibility | 与 M3 语义纠缠 (production_run) | 干净 (P0/P1 风格) |
| semantics | rel = M3 run release (域错) | Release = canonical outcome |
| provenance | 无 P0/P1 FK 可加? (字段缺) | 全新 FK 设计 |
| P0/P1 integration | 需改写上游语义 | 直接 consume |
| legacy isolation | rel-* 被污染 | rel-* 原样 LEGACY |
| migration | 需改历史 | 零 (新 ID) |
| traceability | 绑 M3 | 完整 |
| 清晰度 | 混 | 唯一 canonical |
**Chosen: Option B** — RELEASE-* 新 ID; rel-* 0 条真实 → 零迁移成本。
rel-* 的执行机制 (apply+governance) 作为新 Release action 参考。

## AD-2: Store 同文件分区 (releases.json)

rel-* + RELEASE-* 同文件前缀分区 (rel-* 保留, create 只产 RELEASE-*) —
最小侵入; 无迁移。

## AD-3: Gate 用 ver-*/EVD-* (非自跑)

废弃 release 自跑 pytest (_run_verification) — 验证已由 P0 verifier 产生
ver-*/EVD-*; gate 只消费 canonical。

## AD-4: Release 触发点 (未来)

execute 由谁触发: 人工 (governance approval, release risk=high) — 保持人工
门; 自动化 optional (POLICY-DEPENDENT)。
