# 05 — RELATION CONTRACT (STEP 10, 2026-09-02)

| Relation | Cardinality | Direction | Identifier | Status |
|----------|-------------|-----------|-----------|--------|
| Requirement → Product Intent/PRD | 1:N | Req 引用下游 | requirement_id → prd_id | CONTRACT-ONLY (PRD 未来) |
| PRD → Plan | 1:N | PRD 产出计划 | prd_id → plan_id | CONTRACT-ONLY |
| Plan → Task | 1:N | Plan produces | plan_id (当前已实现, E2E) | CURRENT |
| Task → Run | 1:N | Task creates | task_id/exec_ref | CURRENT (会话链) |
| Run → ExecutionRecord | 1:1 | Run records | run_id → EXS-* | CURRENT (exec 域) |
| Run → Artifact | 1:N | Run produces | run_id → ART-* | CURRENT (exec 域) |
| Run → Verification | 1:N | Run verifies | run_id → verify | CURRENT (exec) / CONTRACT (会话链) |
| Task → Capability Constraint | 1:1 | Task 声明能力需求 | task_id → capability | CONTRACT-ONLY (语义冻结) |
| Capability Constraint → Agent Selection | N:1 | Router 选择 | capability → agent_id | CURRENT (gateway router) |
| Task/Agent → Model Policy | N:1 | 治理选择依据 | task/agent → policy | CONTRACT-ONLY |
| Model Policy → Model Selection | 1:1 | Policy 决定模型 | policy → model | CONTRACT-ONLY (LLMRouter 未接) |
| 核心实体 → Audit | 1:N | 全部动作审计 | entity_id → event | CURRENT (audit_events) |

## 规则
- 无 ID Contract 的关系 = UNPROVEN/UNKNOWN, 不假设存在 (TRACE-02)
- 字段未存在 → 标记 CONTRACT-ONLY / IMPLEMENTATION-FUTURE
