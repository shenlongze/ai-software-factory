# 12 — SSOT / MULTI-LEDGER (P2-C CONTRACT, 2026-09-06)

| Domain | Canonical SSOT | Writer | Legacy Store | Observer |
|---|---|---|---|---|
| Task | backlog TASK-* | service.create_task | — | audit |
| TaskRun | nodes/runs run-* | node_runtime | M3 production_run | audit |
| EXS | exec/execution_records | record_invocation | exec/results.json | audit |
| Artifact | artifacts art-* | create_artifact | exec ART-*/org | audit |
| Verification | verifications ver-* | materialize_verification | — | audit |
| Evidence | evidence EVD-* | materialize_evidence | ev-* M3 | audit |
| Release | releases/release_truth RELEASE-* | release_truth | rel-* | audit |
| Experience | memory/experience_store exp-* | **ExperienceBridge (未来)** | M3 AutoLearner 路径 | learning_trace |

- Experience 现唯一 SSOT (memory/experience_store.json); 未来 writer 收敛至
  ExperienceBridge (仍写同 store — 单 SSOT 不变)
- intelligence/experiences (空壳 1) = 非 SSOT (future learning 域, 未用)
- events = observers (无 exp event 作为 truth)
