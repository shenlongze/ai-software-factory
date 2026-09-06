# 01 — CANONICAL WRITER (P2-C IMPL, 2026-09-06)

- canonical writer = experience_bridge (record/record_execution/record_release)
- 唯一新写入口; CLI execute / agent_loop 全经它
- ExperienceStore.add 仍可被 M3 AutoLearner/learning_engine 调 (legacy 路径
  保留 — 契约 11-LEGACY-ISOLATION)
- F8 审计: 无第二新 writer; intelligence/experiences (S9) 零读零写
