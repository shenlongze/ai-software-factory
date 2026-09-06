# 04 — OBSERVATION CONTRACT (P2-D CONTRACT, 2026-09-06)

## D1: Canonical Observation (冻结)

- ID: OBS-{hex8} (新; 现有 learning_engine_v2 无 obs 真实数据, uuid 风格 —
  契约采用 canonical 前缀, 与 P0-P2-C 一致)
- SSOT: <root>/learning/observations.json (新独立 store)
- Writer: ObservationService (唯一; 从 anchored exp 聚合)

## 语义
- Experience ≠ Observation: exp=事实记录; obs=可分析观察 (从 ≥1 exp 形成)
- Obs 引用: experience_ids[] (≥1) + agent/model/skill/tool/workflow/task_type
  (可空) + 统计窗口 (window/sample_count) + confidence
- 必带 evidence: 每条 obs 的 exp 必须带 anchor FK (禁无证据 obs)
- 来源触发: 定时/批量 (如每 N finalize 或手动 gate) — P2-D Impl 定

## Reality: 现有 learning_engine_v2 obs = legacy (0 数据, 手动 API) —
新 ObservationService 替代 (不迁移)
