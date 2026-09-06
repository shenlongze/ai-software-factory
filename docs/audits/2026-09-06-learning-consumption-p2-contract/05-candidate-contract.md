# 05 — CANDIDATE CONTRACT (P2-D CONTRACT, 2026-09-06)

## D2: Canonical Learning Candidate (冻结)

- ID: CAND-{hex8}; SSOT: <root>/learning/candidates.json
- Writer: CandidateService (唯一; 从 Observation 推导, 非生产路径直写)

## 语义
- Candidate = proposed change (建议, 非生效)
- 字段: capability (建议能力/画像变更) + observation_ids[] + experience_ids[]
  + confidence + evidence_count + quality/cost/latency delta (可空) + risk
  + recommendation + status (OPEN/PROMOTED/REJECTED/EXPIRED)
- **Candidate 不得直接改 Agent/Profile/生产** (只经 Promotion)

## Reality: 现有 learning_engine_v2 create_candidate (0 数据, hypothesis 驱动)
= legacy 基础; 新 CandidateService 收敛
