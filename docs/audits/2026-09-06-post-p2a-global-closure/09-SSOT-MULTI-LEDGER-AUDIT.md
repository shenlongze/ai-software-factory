# 09 — SSOT / MULTI-LEDGER AUDIT (CLOSURE AUDIT, 2026-09-06)

| Store | 角色 | 生产路径消费? |
|---|---|---|
| backlog TASK-* | canonical | ✓ |
| nodes/runs run-* | canonical | ✓ |
| exec/execution_records EXS | canonical | ✓ (P0 + exp extraction) |
| exec/results.json | mirror/legacy | 部分旧读 |
| verifications/ver-* | canonical | ✓ (release gate) |
| evidence/EVD-* | canonical | ✓ (release gate) |
| releases/release_truth RELEASE-* | canonical | (无下游 — 新) |
| releases/releases.json rel-* | M3 legacy | 无 P0/P1 消费 |
| M3 production_run | legacy | 仅 M3 release/eval (0 数据) |
| product/ideas PI-* | S9 legacy | 无 |
| requirements/req_* | legacy | 旧 API 投影 |
| session_plans | orchestration legacy | 旧 API 投影 |
| intelligence/ (decisions/experiences/recommendations) | 空壳 | 无 |
| memory/experience exp | store 真 | AutoLearner 读 (M3) |
| memory/learning_trace | 审计 | 展示 |
| audit_events.json | observation | 非 SSOT |
| factory.db | mirror | 展示 |

**无第二 canonical SSOT 出现** (P2-A 独立文件正确隔离); 无 shadow ledger。
