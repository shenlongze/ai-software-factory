# BASELINE MATRIX — STEP 9 (2026-09-02)
> 未来 Sprint 基础表 (完整版: MASTER_STATUS_TABLE.md)

| Capability | Domain | Status | M | SSOT | Upstream | Downstream | User Visible | E2E |
|-----------|--------|--------|---|------|----------|------------|--------------|-----|
| Session Entry | Session | CLOSED_LOOP | M4 | console_sessions.json | User | Intent | YES | YES |
| Intent Capture | Session | CLOSED_LOOP | M4 | (消息) | Session | Plan/Req | YES | YES |
| Req Persistence | Req | PRODUCTION | M2 | requirements.json | Intent | (无) | YES | YES |
| Req Traceability | Req | ABSENT | M0 | — | — | — | NO | NO |
| Planning | Plan | CLOSED_LOOP | M4 | session_plans.json | Intent | Task | YES | YES |
| Task Mgmt | Task(A) | CLOSED_LOOP | M4 | backlog | Plan | ExecState | YES | YES |
| Dependency | Task(A) | CLOSED_LOOP | M4 | backlog.dep | Task | Scheduling | YES | YES |
| Cancel | Task(A) | CLOSED_LOOP | M4 | backlog | Execution | — | YES | YES |
| Recovery | Task(A) | PRODUCTION | M3 | session_exec(投影) | crash | Execution | YES | YES(模拟) |
| Agent Selection | Agent | PRODUCTION | M3 | agents.json+router | Task | Agent Exec | 部分 | YES |
| Agent Execution | Agent | PRODUCTION | M3 | exec records | Selection | Artifact | YES | YES |
| LLM Invocation | LLM | CLOSED_LOOP | M4 | providers.json | Agent | Response | 隐 | YES |
| Model Selection | LLM | IMPLEMENTED | M1 | (LLMRouter 未接) | — | — | NO | NO |
| Tool | Tool | PRODUCTION | M3 | _fc | Agent | Execution | 隐 | YES |
| Skill | Skill | IMPLEMENTED | M1 | skills.json | — | — | NO | UNKNOWN |
| Orchestration | Orch | CLOSED_LOOP | M4 | session_exec | Task | Execution | 隐 | YES |
| Execution | Exec | CLOSED_LOOP | M4 | backlog+registry | Scheduling | Writeback | YES | YES |
| Verification | Exec | INTEGRATED | M2 | exec results | Execution | (无) | 部分 | 部分 |
| Artifact | Exec | INTEGRATED | M2 | exec results | Execution | (无) | 部分 | 部分 |
| Audit | Gov | CLOSED_LOOP | M4 | audit_events.json | 全部 | API | YES | YES |
| Governance | Gov | PRODUCTION | M3 | approvals | Execution | — | YES | 部分 |
| Project Mgmt | PM | CLOSED_LOOP | M4 | org/projects | — | 全部 | YES | YES |
| WebUI | UX | PRODUCTION | M3 | (View) | API | User | YES | 部分 |
| CLI | UX | PRODUCTION | M3 | — | User | Service | YES | YES |
| Discovery | PI | IMPLEMENTED | M1 | conversation | Intent | Req | 部分 | UNKNOWN |
| PRD | PI | ABSENT | M0 | — | Req | Plan | NO | NO |
| Experience | Learn | IMPLEMENTED | M1 | experience_store | Execution | (无读) | NO | NO |
| Learning | Learn | ABSENT→FUT | M0 | — | — | — | NO | NO |
| Release | Release | ABSENT→FUT | M0 | — | — | — | NO | NO |
