# FACT REGISTRY STEP 3 — RUNTIME PROOF (2026-09-02)

| Fact ID | Subject | Relation | Object | Evidence Type | Status |
|---------|---------|----------|--------|--------------|--------|
| R001 | Agent backend-1 | executed | run_task (48 次) | DATA (execution_records.json) | CONFIRMED |
| R002 | Agent flutter-dev | executed | tasks (17 次) | DATA | CONFIRMED |
| R003 | Agent 执行 | succeeded | 87/100 | DATA | CONFIRMED |
| R004 | Agent 执行 | failed | 13/100 | DATA | CONFIRMED |
| R005 | Requirement | persisted | requirements.json (7 VALIDATED) | DATA | CONFIRMED |
| R006 | Requirement | written_by | agent_loop.py:795-803 | STATIC | CONFIRMED |
| R007 | Requirement | read_by | fastapi:1501/1601 | STATIC | CONFIRMED |
| R008 | Provider | configured | providers.json (deepseek) | DATA | CONFIRMED |
| R009 | LLM | usage recorded | providers/usage.json | DATA | CONFIRMED |
| R010 | LLMRouter | production consumer | 0 | STATIC | CONFIRMED_NO_PRODUCTION_CONSUMER |
| R011 | factory-core | console consumer | 0 | STATIC | CONFIRMED_NO_PRODUCTION_CONSUMER (console) |
| R012 | exec agent_runtime | integrated | service.py:445 | STATIC | CONFIRMED |
| R013 | exec sandbox | produced | exec/patches/ | DATA | CONFIRMED |
| R014 | exec approval | persisted | governance/approvals.json | DATA | CONFIRMED |
| R015 | Audit events | count | 5160 | DATA | CONFIRMED |
| R016 | Sessions | count | 81 (topics) | DATA | CONFIRMED |
| R017 | ExecState | persisted | 6 session_exec | DATA | CONFIRMED |
| R018 | Experience | persisted | memory/experience_store 84 | DATA | CONFIRMED |
| R019 | factory.db | exists | 3.3MB SQLite | DATA | UNKNOWN (写读方未验证) |
| R020 | factory-runtime | runtime trace | runtimes.json 57B | DATA | UNKNOWN (无运行痕迹) |
| R021 | 7 角色 Agent (dev/pm/arch/...) | runtime caller | UNKNOWN | — | UNKNOWN |
| R022 | execution_records 触发入口 | CLI/会话/API | UNKNOWN | — | UNKNOWN |
