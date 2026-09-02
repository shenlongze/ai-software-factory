# CAPABILITY MATURITY REGISTRY — STEP 7 (2026-09-02)

| ID | Capability | Tier | M | Evidence |
|----|-----------|------|---|----------|
| C-001 | Session Entry | CORE | M4 | console_sessions.json 812KB + 81 topics + E2E + F-01/F-02 测试 |
| C-002 | Intent Capture | CORE | M4 | query_engine 白名单+execution_truth (1cbf8ccf/417655db) E2E |
| C-003 | Requirement Persistence | CORE | M2 | agent_loop.py:795 + 7 条 VALIDATED 数据 |
| C-004 | Requirement Traceability | CORE | M0 | requirements.json 无引用字段 (STEP5 G-REQ-01) |
| C-005 | Discovery/Clarification | SUPPORTING | M1 | discovery_intelligence 536 行 + conversation.py:750 集成, runtime 数据 UNKNOWN |
| C-006 | Planning | CORE | M4 | session_plans + PLAN-* 持久化 + E2E (85c237f0) |
| C-007 | Task Management | CORE | M4 | org/management + 测试 + E2E (2da49ecc) |
| C-008 | Dependency Scheduling | CORE | M4 | ExecState.next + 测试 (914bc341) |
| C-009 | Agent Selection | CORE | M3 | gateway.py:18→router.py:193 + execution_records 100 |
| C-010 | Agent Execution | CORE | M3 | execution_records (backend-1×48 等, 87 success) + exec/results |
| C-011 | LLM Invocation | CORE | M4 | console_sessions.py:104 + providers.json deepseek + usage.json |
| C-012 | Model Selection | CORE | M1 | LLMRouter 消费 0; 实际固定 provider._default_llm_fn |
| C-013 | Tool Invocation | SUPPORTING | M3 | _fc 注册表 + E2E 工具调用 (create_task/execute_plan 等) |
| C-014 | Skill | SUPPORTING | M1 | skills.json 2.5MB + API; 生产消费 UNKNOWN |
| C-015 | Orchestration (会话链) | CORE | M4 | 多轮 E2E (85c/914/2da/4e1/d6f/9b8 commits) |
| C-016 | Execution (会话链) | CORE | M4 | chain_next→gateway→finish_task_exec E2E |
| C-017 | Recovery (crash) | CORE | M3 | ExecState.recover + 10 测试 + E2E 模拟 (d6f1de6b) |
| C-018 | Cancellation | CORE | M4 | 45810d64 + 4e1a42e1 E2E + test_task_cancelled |
| C-019 | Verification | CORE | M2 | exec test_result (ART-b97e1a72) 真实; 会话链 verify 无独立下游 |
| C-020 | Artifact Lifecycle | SUPPORTING | M2 | exec ART-* patch/test_result; 会话链无 artifact_ref |
| C-021 | Audit | CORE | M4 | audit_events 5160 + 查询 API + TASK_CREATED 等 |
| C-022 | Governance/Approval | CORE | M3 | governance/approvals + session_approvals + approve API |
| C-023 | Project Management | SUPPORTING | M4 | org projects + API + WebUI |
| C-024 | WebUI | SUPPORTING | M3 | vite 服务 + 前几轮浏览器 E2E (任务/刷新/停止) |
| C-025 | CLI | SUPPORTING | M3 | cli_factory 8145 / core cli / exec cli (运行过) |
| C-026 | Experience | FUTURE | M1 | experience_store 84 条; 消费 0 (M4 承诺 L411) |
| C-027 | Learning | FUTURE | M0 | learning 端点存在, 无闭环 (M4 承诺) |
| C-028 | Replanning | FUTURE | M0 | orchestrator replanner (M3 承诺 L6620); 会话链无集成 |
| C-029 | Release | FUTURE | M0 | release 端点存在, runtime UNKNOWN |
