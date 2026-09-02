# CAPABILITY REGISTRY — STEP 4 (2026-09-02)

| Capability | Level | Evidence | Runtime | Persist | Consumer |
|-----------|-------|----------|---------|---------|----------|
| Session | REAL | console_sessions + 81 | YES | YES | UI |
| Intent | REAL | query_engine 白名单+LLM | YES | msgs | agent_loop |
| Requirement | PARTIAL | requirements.json 7 | YES | YES | API 读取; 无 plan 引用 |
| Discovery | PARTIAL | discovery_intelligence (conversation 用) | UNKNOWN | conversation.json | UNKNOWN |
| Brainstorm | UNPROVEN | 模块存在 | UNKNOWN | UNKNOWN | UNKNOWN |
| PRD | ABSENT | 无实体 | NO | NO | — |
| Planning | REAL | plan_development + E2E | YES | session_plans | execute_plan |
| Task | REAL | backlog | YES | YES | ExecState |
| Agent | REAL | agents.json 8 + exec 100 | YES | YES | router |
| Agent Selection | REAL | gateway._pick_executor→route | YES | records | chain_next |
| LLM | REAL | llm_fn→deepseek | YES | usage.json | 全模块 |
| LLM Selection | ISOLATED | LLMRouter 消费 0 | NO | NO | — |
| Tool | REAL | agent_loop _fc / exec tool | YES | — | agent_loop |
| Skill | REAL | skills.json 2.5MB | YES | YES | UNKNOWN |
| Plugin | UNPROVEN | plugin_kernel | UNKNOWN | UNKNOWN | UNKNOWN |
| Orchestration | PARTIAL | ExecState 动态 + 三系统 | YES (A) | session_exec | chain |
| Execution | REAL | gateway + exec records | YES | YES | — |
| Verification | PARTIAL | verify_invocation / exec test_result | PARTIAL | results | UNKNOWN |
| Artifact | PARTIAL | exec ART-* | YES (exec) | YES | NO (backlog 无引用) |
| Recovery | REAL | ExecState.recover (A) | YES | session_exec | chain_next |
| Replanning | UNPROVEN | orchestrator replanner (M3) | UNKNOWN | UNKNOWN | UNKNOWN |
| Audit | REAL | audit_events 5160 | YES | YES | API |
| Governance | PARTIAL | approvals/approval-gates | PARTIAL | YES | UNKNOWN |
| Experience | PARTIAL | experience_store 84 | YES (写) | YES | UNKNOWN (读未证明) |
| Learning | ISOLATED | learning 端点 | UNKNOWN | learning_trace | UNKNOWN |
| Release | ISOLATED | release_service + API | UNKNOWN | UNKNOWN | UNKNOWN |
| Project Mgmt | REAL | org projects/backlog/sprint | YES | YES | UI |
| WebUI | REAL | vite 5180 | YES | — | API |
| CLI | REAL | 4 条 CLI | YES | — | — |
| Desktop | ABSENT | desktop/ 空 | NO | — | — |
