# AGENT REALITY MAP — STEP 7

| Agent | Entity | Registered | Selection | Executed | 分类 |
|-------|--------|-----------|-----------|----------|------|
| backend-1 | exec + agents.json | YES | router (execution_records) | 48 runs | PRODUCTION (exec 域) |
| flutter-dev | agents.json | YES | router | 17 runs | PRODUCTION |
| pm-agent | agents.json | YES | router | 6 runs | PRODUCTION (exec 域) |
| architect-agent | agents.json | YES | router | 6 runs | PRODUCTION |
| qa-agent | agents.json | YES | router | 8 runs | PRODUCTION |
| claude.*/codex.* | external adapters | YES | router | 9/1 runs | PRODUCTION (external) |
| developer/pm/architect 独立 Agent 类 (exec/*.py) | exec 模块 | 模块存在 | 触发入口 UNKNOWN | 模块级 UNKNOWN | IMPLEMENTED/UNPROVEN |

## 结论
- Agent 执行域 (exec): 5+ agents PRODUCTION (records+artifacts)
- Agent 角色类 (developer.py 等独立执行器): 模块存在, 生产触发入口 UNKNOWN
- 会话链 Agent 绑定: gateway route (默认/显式) — 有选择真实
