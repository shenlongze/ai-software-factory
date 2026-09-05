# 05 — LEGACY ISOLATION (P2-A ACCEPTANCE, 2026-09-06)

- rel-* (M3 release_service): 独立 releases.json, 域内 0 RELEASE-* (grep)
- release_truth 独立 release_truth.json (实现决策: 避免 rel-* 同文件
  id 混列 + M3 create KeyError)
- migration = NONE | backfill = NONE | legacy mutation = NONE
- rel-* 无 rename; 历史无 provenance 补造
- Git tag = metadata (非 truth)
- 测试 test_rel_star_untouched 实证
