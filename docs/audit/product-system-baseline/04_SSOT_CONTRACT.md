# 04 — SSOT CONTRACT (STEP 10, 2026-09-02)

## SSOT Matrix (Write Owner 唯一)

| Domain | Entity | SSOT | Identifier | Write Owner | Projection | Historical |
|--------|--------|------|-----------|-------------|-----------|-----------|
| Requirement | Requirement | requirements.json | req_* | agent_loop (req capture) | — | — |
| Product/PRD | PRD | (ABSENT, CONTRACT-ONLY) | prd_* (未来) | (未来) | — | — |
| Planning | Plan | session_plans.json | PLAN-* | PendingPlanStore | — | — |
| Execution Task | Task | backlog task.json | TASK-* | ManagementStore | ExecState (session_exec) | — |
| Runtime/Run | Run | gateway registry | EXS-*/R* | gateway_execute | — | — |
| Exec Record | ExecutionRecord | exec records | EXS-* | exec store | — | — |
| Artifact | Artifact | exec results | ART-* | exec/gateway | — | — |
| Verification | Verification | exec results + task verify | — | verify | ExecState.verify | — |
| Agent | Agent | agents.json | backend-1 等 | agent registry | — | — |
| Model/LLM | Provider/Model | providers.json | deepseek 等 | config | — | — |
| Project | Project | org/projects.json | P-* | ProjectStore | 目录 slug | — |
| Audit | Audit Event | audit_events.json | event id | AuditEmitter | — | 追加不可变 |

## 关键规则
- 每个 Domain 一个 Write Owner (INV-001)
- Projection (ExecState/Intent/WebUI) 不得反向成为事实源 (INV-014)
- 跨 Domain 引用只读 (reference/map/project/derive), 不写 (SSOT-03)
- Model Selection SSOT: 未冻结 (LLMRouter 无消费者) — 契约冻结, 实施留 Fix
