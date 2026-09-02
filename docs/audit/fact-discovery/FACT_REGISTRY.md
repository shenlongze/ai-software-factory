# FACT REGISTRY — FACT DISCOVERY (2026-09-02)

| Fact ID | Subject | Relation | Object | Evidence |
|---------|---------|----------|--------|----------|
| F001 | Task | stored_in | backlog/task.json | org.management.ManagementStore |
| F002 | ExecState | projection_of | Task | session/exec_state.py (backlog_id+dependency) |
| F003 | Plan | stored_in | session_plans.json | PendingPlanStore (agent_loop.py:2700+) |
| F004 | Run | stored_in | ExternalTaskRegistry | external_executor/task_registry.py:create |
| F005 | gateway | executes | external executor CLI | external_executor/gateway.py:91 |
| F006 | ExecState.next | gates | dependency | exec_state.py:111-116 |
| F007 | finish_task_exec | writes | Task status (done/failed/cancelled) | service.py:4469+ |
| F008 | recover | resolves | stale running | exec_state.py:171+ |
| F009 | reconcile_plan | aggregates | Plan terminal from Task | agent_loop.py:2582+ |
| F010 | run_agent_native | is_entry | session messages | agent_loop.py |
| F011 | actions registry | separate | from agent_loop | grep: agent_loop import actions = 0 |
| F012 | factory-core | NOT imported | by factory-console | grep: from factory_core in console = 0 |
| F013 | factory-exec | NOT imported | by factory-console | import 矩阵空 |
| F014 | factory-runtime | NOT imported | by factory-console | import 矩阵空 |
| F015 | factory-org | imported | by factory-console | from org.management (E2E 运行链) |
| F016 | product_intelligence | returns | markdown (not persisted) | actions.py:2864-2893 (无 save) |
| F017 | LLM calls | mostly direct | llm_fn/llm_raw/chat_completion | 154/175 处 (88%) |
| F018 | API surface | = 371 endpoints | fastapi_adapter.py | @app.get/post/... 提取 |
| F019 | requirement/PRD | UNKNOWN persistence | ? | 未定位结构化实体 |
| F020 | release/learning | endpoints exist | /api/releases /api/learning | 端点存在; 持久化未验证 |
