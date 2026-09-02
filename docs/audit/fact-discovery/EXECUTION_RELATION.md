# EXECUTION RELATION — STEP 4 (2026-09-02)

| 维度 | A 会话链 | B M3 production_run | C factory-exec |
|------|---------|---------------------|----------------|
| Entry | agent_loop chain_next | actions.execute_project | exec cli / console 集成 |
| Task | backlog TASK-* | execution_plan.json T-* | exec T001/T002 |
| Run | gateway registry | ProductionRun | EXS-* records |
| Artifact | (无 artifact_ref) | UNKNOWN | ART-* (patch/test_result) |
| Agent | gateway router | orchestrator | exec agents |
| SSOT | backlog + session_plans | execution_plan.json | exec/*.json |
| Recovery | ExecState.recover | recovery_service | UNKNOWN |
| Audit | audit_events | audit_events | exec events |

## 关系

| Pair | Shared Task | Shared Run | Shared Artifact | 状态 |
|------|------------|-----------|----------------|------|
| A↔B | NO (TASK-* vs T-*) | NO | NO | ISOLATED |
| A↔C | NO (TASK-* vs T00x) | NO (registry vs EXS-*) | NO (无 vs ART-*) | PARALLEL (console 集成部分模块) |
| B↔C | NO | NO | NO | ISOLATED/UNKNOWN |

→ 三套独立 execution truth (backlog / execution_plan.json / exec records) 并存。
