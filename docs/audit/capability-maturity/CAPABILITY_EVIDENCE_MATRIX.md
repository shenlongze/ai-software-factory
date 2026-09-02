# CAPABILITY EVIDENCE MATRIX — STEP 7

| Capability | Maturity | Runtime | Persistence | Trace | Verification | Evidence |
|-----------|----------|---------|-------------|-------|-------------|----------|
| C-001 Session Entry | M4 | YES | YES | YES | YES | console_sessions.json 812KB + 81 topics + E2E + F-01/F-02 测试 |
| C-002 Intent Capture | M4 | YES | YES | YES | YES | query_engine 白名单+execution_truth (1cbf8ccf/417655db) E2E |
| C-003 Requirement Persistence | M2 | PARTIAL | YES | PARTIAL | PARTIAL | agent_loop.py:795 + 7 条 VALIDATED 数据 |
| C-004 Requirement Traceability | M0 | NO/UNKNOWN | NO | NO | NO | requirements.json 无引用字段 (STEP5 G-REQ-01) |
| C-005 Discovery/Clarification | M1 | NO/UNKNOWN | NO | NO | NO | discovery_intelligence 536 行 + conversation.py:750 集成, runtime 数据 UNKNOWN |
| C-006 Planning | M4 | YES | YES | YES | YES | session_plans + PLAN-* 持久化 + E2E (85c237f0) |
| C-007 Task Management | M4 | YES | YES | YES | YES | org/management + 测试 + E2E (2da49ecc) |
| C-008 Dependency Scheduling | M4 | YES | YES | YES | YES | ExecState.next + 测试 (914bc341) |
| C-009 Agent Selection | M3 | YES | YES | PARTIAL | YES | gateway.py:18→router.py:193 + execution_records 100 |
| C-010 Agent Execution | M3 | YES | YES | PARTIAL | YES | execution_records (backend-1×48 等, 87 success) + exec/results |
| C-011 LLM Invocation | M4 | YES | YES | YES | YES | console_sessions.py:104 + providers.json deepseek + usage.json |
| C-012 Model Selection | M1 | NO/UNKNOWN | NO | NO | NO | LLMRouter 消费 0; 实际固定 provider._default_llm_fn |
| C-013 Tool Invocation | M3 | YES | YES | PARTIAL | YES | _fc 注册表 + E2E 工具调用 (create_task/execute_plan 等) |
| C-014 Skill | M1 | NO/UNKNOWN | NO | NO | NO | skills.json 2.5MB + API; 生产消费 UNKNOWN |
| C-015 Orchestration (会话链) | M4 | YES | YES | YES | YES | 多轮 E2E (85c/914/2da/4e1/d6f/9b8 commits) |
| C-016 Execution (会话链) | M4 | YES | YES | YES | YES | chain_next→gateway→finish_task_exec E2E |
| C-017 Recovery (crash) | M3 | YES | YES | PARTIAL | YES | ExecState.recover + 10 测试 + E2E 模拟 (d6f1de6b) |
| C-018 Cancellation | M4 | YES | YES | YES | YES | 45810d64 + 4e1a42e1 E2E + test_task_cancelled |
| C-019 Verification | M2 | PARTIAL | YES | PARTIAL | PARTIAL | exec test_result (ART-b97e1a72) 真实; 会话链 verify 无独立下游 |
| C-020 Artifact Lifecycle | M2 | PARTIAL | YES | PARTIAL | PARTIAL | exec ART-* patch/test_result; 会话链无 artifact_ref |
| C-021 Audit | M4 | YES | YES | YES | YES | audit_events 5160 + 查询 API + TASK_CREATED 等 |
| C-022 Governance/Approval | M3 | YES | YES | PARTIAL | YES | governance/approvals + session_approvals + approve API |
| C-023 Project Management | M4 | YES | YES | YES | YES | org projects + API + WebUI |
| C-024 WebUI | M3 | YES | YES | PARTIAL | YES | vite 服务 + 前几轮浏览器 E2E (任务/刷新/停止) |
| C-025 CLI | M3 | YES | YES | PARTIAL | YES | cli_factory 8145 / core cli / exec cli (运行过) |
| C-026 Experience | M1 | NO/UNKNOWN | NO | NO | NO | experience_store 84 条; 消费 0 (M4 承诺 L411) |
| C-027 Learning | M0 | NO/UNKNOWN | NO | NO | NO | learning 端点存在, 无闭环 (M4 承诺) |
| C-028 Replanning | M0 | NO/UNKNOWN | NO | NO | NO | orchestrator replanner (M3 承诺 L6620); 会话链无集成 |
| C-029 Release | M0 | NO/UNKNOWN | NO | NO | NO | release 端点存在, runtime UNKNOWN |
