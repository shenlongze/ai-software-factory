# 12 — VERSIONING (P2-D CONTRACT, 2026-09-06)

- Experience: immutable (P2-C; 无 version)
- Observation/Candidate/Promotion: immutable facts (各自 ID; 无 version 语义)
- **Profile: versioned** — 每 APPLIED promotion → profile_version++
  (agent_profiles.json 存 current_version; 历史版本快照于 promotion 记录)
- Routing policy: 版本随 profile (router 读 current; RD 快照当时 version)
- RD 必须有 profile_version — 否则生产审计无法回答 "当时用的哪个版本"
