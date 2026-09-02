# RELATION REGISTRY — STEP 4 (2026-09-02)

| EDGE | FROM | TO | TYPE | EVIDENCE | RUNTIME | STATUS |
|------|------|----|------|----------|---------|--------|
| E01 | User | Session | session msg | POST /messages → console_sessions.json | 81 sessions | PROVEN |
| E02 | Session | Requirement | req capture | agent_loop.py:795-803 → requirements.json | 7 req VALIDATED | PROVEN |
| E03 | Requirement | Plan | ? | requirements.json 无 plan_id 字段 | 无 | ABSENT (未发现引用) |
| E04 | Requirement | Task | ? | requirements.json 无 task 引用 | 无 | ABSENT |
| E05 | Plan | Task | plan_id | execute_plan create_task plan_id (agent_loop.py:476) | E2E | PROVEN |
| E06 | Task | Run | exec_ref | finish_task_exec exec_ref | E2E | PROVEN |
| E07 | Task | Artifact | task_id | exec/results artifacts task=T001/T002 | DATA | PROVEN (exec 系统) |
| E08 | Task | Artifact | ? | 会话链 backlog 无 artifact_ref | 无 | ABSENT (会话链) |
| E09 | Run | Artifact | result_id | gateway result_id → exec/results | DATA | PROVEN (exec) |
| E10 | Agent | Execution | agent_id | gateway._pick_executor → router.route | execution_records | PROVEN |
| E11 | Task | Verification | verify | ExecState verify + finish | E2E | PROVEN |
| E12 | Execution | Audit | event | audit_events 5160 | DATA | PROVEN |
| E13 | Execution | Experience | ? | experience_store 84 条 | DATA 写入 | PARTIAL (consumer 未证明) |
| E14 | Experience | Future Decision | ? | learning_loop.py 存在 | ? | UNKNOWN |
| E15 | Requirement | PRD | ? | PRD 实体未定位 | 无 | ABSENT |
| E16 | Session | Plan | pending | plan_development → session_plans | E2E | PROVEN |
| E17 | console | exec | import | from exec import 79 处 (全仓) | runtime_session 等 | PROVEN |
| E18 | console | core | import | 0 处 | 0 | ABSENT |
| E19 | exec | core | import | 0 处 (未扫, 推断 UNKNOWN) | — | UNKNOWN |
