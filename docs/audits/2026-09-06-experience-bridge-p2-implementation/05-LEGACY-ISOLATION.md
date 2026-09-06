# 05 — LEGACY ISOLATION (P2-C IMPL, 2026-09-06)

- 84 条旧 exp: 零迁移零 backfill (F10 实证: anchor FK=0)
- ExperienceRecord.from_dict 兼容旧记录 (缺省空 anchor)
- intelligence/experiences.json (85, S9): bridge 零读零写 (test_intelligence_not_read)
- M3 AutoLearner/learning_engine 旧写路径保留 (不重构)
- learning_trace / M3 production_run: 未触碰
