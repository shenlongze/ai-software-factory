# ORCHESTRATION FORENSICS — STEP 4 (2026-09-02)

## 决策点 (WHO/WHERE/WHAT)

| Decision | WHO | WHERE (代码) | 固定/动态 |
|----------|-----|-------------|-----------|
| Task 生成 | execute_plan / plan_development | agent_loop.py | plan_development LLM 计划 |
| Task 顺序 | ExecState.next (dependency gate) | exec_state.py:111 | 动态 (依赖驱动) |
| Agent 选择 | gateway._pick_executor | gateway.py:18 → router.route | 动态 (classify+score) |
| Model 选择 | provider._default_llm_fn | console_sessions.py:110 | 固定默认 (providers.json) |
| Tool 选择 | agent_loop _fc 注册 | agent_loop.py:212+ | 固定分支 (工具名) |
| Retry | gateway max_retry / FAILED→ready | gateway.py:155 | 固定次数/人工 |
| Recovery | ExecState.recover | exec_state.py:171 | 动态 (Run 证据) |
| Replan | orchestrator replanner | orchestrator.py | UNKNOWN (M3 侧) |
| Human approval | ApprovalGate / approve API | exec/approval.py / session_approvals | 人工 |

## 事实

- 会话链执行: 依赖感知 (ExecState.next) + Agent 选择 (gateway router) — 动态成分真实
- 计划生成: plan_development (LLM) — 计划内容动态, 结构 (tasks/order) 固定模板
- 工具调用: agent_loop _fc 注册表 (固定枚举), LLM 选工具名 — 半动态
- Model: 无动态选择 (LLMRouter 未接入, 固定 provider 默认)
- 三执行系统各有编排: 会话链 (ExecState) / M3 (orchestrator _run_queue) / exec (execution_loop)
