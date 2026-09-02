# EXEC CAPABILITY PROOF — STEP 3 (2026-09-02)

> 逐模块状态。证据: 代码(consumer) + 运行时数据(~/.factory exec/)

| 模块 | 代码 | 调用者 (console) | 运行时 | 状态 |
|------|------|------------------|--------|------|
| runtime_session | exec/runtime_session.py:480 | service.py:412 (_runtime_session_mod) | runtime-sessions/ 目录 | INTEGRATED (console 懒装配) |
| agent_executor | exec/agent_executor.py:170 | service.py:422 | execution_records (action=agent.execute_task) | RUNTIME_PROVEN |
| agent_runtime (AgentRuntime) | exec/agent_runtime.py:704 | service.py:445 | execution_records (result_id EXS-*) | RUNTIME_PROVEN |
| tool | exec/tool.py:397 | service.py:539 | tools 端点 | INTEGRATED |
| skill | exec/skill.py:420 | service.py:671 | skills.json 2.5MB | INTEGRATED |
| mcp | exec/mcp.py:615 | service.py:818 | mcp 端点 | INTEGRATED |
| developer/pm/architect/tester/release/uxui | 各 400-760 行 | console 未直接 import (6 个延迟导入点不含) | execution_records agent=backend-1 等 | CALLABLE (agents.json 注册), runtime 调用者 UNKNOWN |
| execution_loop | 878 行 | UNKNOWN | UNKNOWN | UNKNOWN |
| sandbox | 249 行 | UNKNOWN | exec/patches/ (patch 产物) | RUNTIME_PROVEN (patches) |
| approval | 242 行 | UNKNOWN | governance/approvals.json 5652B | RUNTIME_PROVEN (approvals) |
| store | 260 行 | 自用 | exec/*.json | RUNTIME_PROVEN |

## 结论 (证据级)

- exec 系统整体: RUNTIME_PROVEN (execution_records 100 + artifacts + patches)
- console 集成面: 仅 6 个延迟导入点 (runtime_session/agent_executor/AgentRuntime/tool/skill/mcp)
- developer/pm/architect 等角色 Agent: agents.json 注册 + execution_records 有 agent=backend-1 执行,
  但 7 类角色 Agent 的独立运行时调用链 UNKNOWN (可能经 CLI/旧系统)
