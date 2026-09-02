# AGENT CONTROL FORENSICS — STEP 4 (2026-09-02)

## 选择决策点 (代码证据)

```
gateway.py:18 _pick_executor(data_dir, agent_id, task, project_id)
  → registry build (external executor adapters)
  → agents.json 读取 (host_agent 映射)
  → router.py:193 route(task, adapters, agents, explicit_agent)
    → classify_task (router.py:54)
    → score_candidate (router.py:93, 基于 history_stats)
    → 选择 executor_id[.host_agent]
```

## AGENT_CONTROL_MATRIX

| Agent | Registered (agents.json) | Selectable | Selection | Runtime Entry | Real Exec | Persistence |
|-------|------------------------|-----------|-----------|---------------|-----------|-------------|
| backend-1 | YES (8 agents) | YES (router) | route() | gateway | execution_records 48 | YES |
| flutter-dev | YES | YES | route() | gateway | 17 | YES |
| pm-agent | YES | YES | route() | gateway | 6 | YES |
| architect-agent | YES | YES | route() | gateway | 6 | YES |
| qa-agent | YES | YES | route() | gateway | 8 | YES |
| claude.* | (external adapters) | YES | route() | gateway | 9 | YES |
| codex.* | YES | YES | route() | gateway | 1 | YES |

## 事实

- Agent 选择 = gateway._pick_executor → external_ai/router.route (classify + score, 真实决策)
- 显式 agent_id 优先 (explicit_agent 参数)
- 执行记录真实 (execution_records 100 条, 87 success)
- 角色 Agent (developer/pm/architect/tester) 注册于 agents.json, 经 router 可选;
  execution_records agent=pm-agent/architect-agent/qa-agent 有真实执行
- 选择持久化: execution_records (agent 字段)
- 会话链 (agent_loop) 是否使用 router/gateway Agent 选择: 经 chain_next→gateway_execute (E2E 验证过 gateway 路径)
