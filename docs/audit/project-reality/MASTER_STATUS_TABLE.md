# MASTER STATUS TABLE — 项目现实基准表 (2026-09-02, STEP 8)
> 来源: STEP 7 CAPABILITY_MATURITY_REGISTRY (29 Atomic Capabilities, 全部 evidence-bound)

| Domain | Capability | Status | M | Production Evidence | Persistence | Trace | Verify | Future | Unknown |
|--------|-----------|--------|---|---------------------|-------------|-------|--------|--------|---------|
| Session | Session Entry | CLOSED_LOOP | M4 | 81 sessions + E2E | YES | YES | YES | — | — |
| Session | Intent Capture | CLOSED_LOOP | M4 | execution_truth E2E | msgs | YES | YES | — | — |
| Req | Requirement Persistence | PRODUCTION | M2 | 7 req VALIDATED | YES | PARTIAL | YES | — | — |
| Req | Requirement Traceability | ABSENT | M0 | 无下游引用 | NO | NO | NO | — | — |
| Req | Discovery | IMPLEMENTED | M1 | 模块集成 conversation | UNKNOWN | NO | NO | — | runtime |
| PRD | PRD Domain Entity | ABSENT | M0 | 无实体 | NO | NO | NO | M3 承诺 | — |
| Plan | Planning | CLOSED_LOOP | M4 | PLAN-* + E2E | YES | YES | YES | — | — |
| Task | Task Mgmt | CLOSED_LOOP | M4 | backlog 八态 + E2E | YES | YES | YES | — | — |
| Task | Dependency | CLOSED_LOOP | M4 | ExecState gate + E2E | YES | YES | YES | — | — |
| Task | Cancellation | CLOSED_LOOP | M4 | CANCELLED E2E | YES | YES | YES | — | — |
| Task | Recovery | PRODUCTION | M3 | recover E2E+10 tests | YES | YES | YES | — | 真实 crash |
| Agent | Agent Selection | PRODUCTION | M3 | router records | YES | YES | PARTIAL | — | — |
| Agent | Agent Execution | PRODUCTION | M3 | records 100 | YES | YES | PARTIAL | — | role trigger |
| LLM | LLM Invocation | CLOSED_LOOP | M4 | llm_fn→deepseek | usage | YES | YES | — | — |
| LLM | Model Selection | IMPLEMENTED | M1 | LLMRouter 消费 0 | NO | NO | NO | — | — |
| Tool | Tool Invocation | PRODUCTION | M3 | _fc + E2E | — | YES | YES | — | — |
| Skill | Skill | IMPLEMENTED | M1 | skills.json 2.5MB | YES | NO | NO | — | consumer |
| Orch | Orchestration(会话链) | CLOSED_LOOP | M4 | 多轮 E2E | YES | YES | YES | — | — |
| Orch | Replanning | ABSENT | M0 | M3 承诺 | NO | NO | NO | M3 | — |
| Exec | Execution(会话链) | CLOSED_LOOP | M4 | E2E | YES | YES | YES | — | — |
| Exec | Verification | INTEGRATED | M2 | exec test_result | YES | PARTIAL | PARTIAL | — | downstream |
| Exec | Artifact | INTEGRATED | M2 | exec ART-* | YES | PARTIAL | PARTIAL | — | 会话链关联 |
| Gov | Audit | CLOSED_LOOP | M4 | 5160 events | YES | YES | YES | — | — |
| Gov | Governance/Approval | PRODUCTION | M3 | approvals | YES | PARTIAL | YES | — | — |
| PM | Project Mgmt | CLOSED_LOOP | M4 | org + API + UI | YES | YES | YES | — | — |
| UX | WebUI | PRODUCTION | M3 | 5180 + 浏览器 E2E | — | YES | PARTIAL | — | — |
| UX | CLI | PRODUCTION | M3 | 多条 CLI | — | YES | — | — | — |
| Learn | Experience | IMPLEMENTED | M1 | 84 条写无读 | YES | NO | NO | M4 | — |
| Learn | Learning | ABSENT | M0 | 端点无闭环 | NO | NO | NO | M4 | — |
| Release | Release | ABSENT | M0 | 端点 runtime UNKNOWN | UNKNOWN | NO | NO | — | runtime |

## 未来 Sprint 引用规则
- M4 = 已有闭环, 修改需回归
- M3 = 生产运行, 扩展可做
- M2 = 已集成, 需补下游
- M1 = 实现未生产, 需验证
- M0/FUTURE = 产品承诺里程碑未到期, 不视为缺陷
- UNKNOWN = 先取证再决策
