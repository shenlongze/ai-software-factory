# 05 — LEGACY ISOLATION (P2-A IMPL, 2026-09-06)

- rel-* (M3 release_service) 完全隔离: 独立 store 文件 release_truth.json
  (rel-* 在 releases.json) — 零迁移零回填零 conversion
- governance: 仅白名单加 "release" subject (增量; M3 production_run subject 不变)
- test_rel_star_untouched: RELEASE-* 与 rel-* 文件隔离实证
- M3 release CLI/API (factory release, /api/releases*) 未动
