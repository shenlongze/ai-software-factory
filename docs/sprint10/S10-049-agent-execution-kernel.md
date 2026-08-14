# S10-049 — Agent Execution Kernel

> 日期:2026-08-15 | Sprint: S10-049 | 架构 + 执行流 + 扩展
> 状态: 实现完成 (Phase 1-5), 真实执行验证通过

---

## 1. 架构

```
User Intent ("帮我实现登录功能")
    ↓
IntentParser → IntentObject {type: run_task, params: {objective: "登录功能"}}
    ↓
IntentRouter (run_task → agent.execute_task)
    ↓
ActionRegistry.get("agent.execute_task")
    ↓
ConfirmationGate (run_task 敏感 → 用户确认 y/N)
    ↓
AgentExecutionContext {session_id, project_id, task_id, agent_id, workspace, intent}
    ↓
Agent Selector (前端→flutter-dev / 默认 backend-1 / 显式 agent_id)
    ↓
execute_task → 薄调 exec.cli.cmd_exec_run (Service Layer, 不复制业务)
    ↓
AgentRuntime (真实 LLM → 沙箱 → patch → 产物)
    ↓
AgentExecutionResult {success, agent, artifact, cost, duration, result_id}
    ↓
Execution Record (审计: intent/action/agent/task/result/timestamp)
    ↓
Renderer 展示
```

## 2. 模块

| 模块 | 职责 | 状态 |
|---|---|---|
| actions.py | +execute_task +select_agent +AgentExecutionResult +AgentExecutionContext | ✅ |
| router.py | run_task → agent.execute_task 映射 | ✅ |
| audit.py | record_execution / load_records (execution_records.json) | ✅ |
| conversation.py | run_task 缺参 → CLARIFICATION | ✅ |
| intent.py | +"实现" 关键词 → run_task | ✅ |
| session.py | 执行结果展示集成 | ✅ |

## 3. 执行流示例(真实验证)

### 用户: "给 main.py 加一个 hello 函数"

```
[1] parse → run_task {objective: "给 main.py 加 hello"}
[2] route → agent.execute_task
[3] confirm → "将执行: run_task (...)" → y
[4] select_agent → backend-1 (默认)
[5] execute_task → cmd_exec_run(root=~/.factory, args={project, objective, agent})
[6] AgentRuntime → 真实 DeepSeek 调用 → patch 产物
[7] 结果: ok=True, success=True, cost=847 tokens, artifact=EXS-91f7abfe.patch
[8] 审计: {intent: run_task, action: agent.execute_task, agent: backend-1, result: success}
```

**真实执行耗时 1.2s(简单任务), 审计记录已落盘。**

## 4. 测试

```
新增 (S10-049): test_session_agent_execution.py 54 测试
覆盖: Action 注册 / Router / Context / Runtime 薄调 / 成功流 / 失败流 / 确认门 / Selector / 审计 / 澄清
全量: 8390 passed, 0 failed (基线 8336 → 8390, +54, 零回归)
```

## 5. 未来扩展

### Multi Agent
```
Agent Selector 升级: 基于 task 类型/技能匹配多 Agent (当前: 关键词 + 默认)
AgentRegistry: 能力注册表 (非硬编码 select_agent)
```

### MCP / Skill
```
MCP: 新 Action 类型 → MCP tool (ActionRegistry.register, 注册式)
Skill: intent 参数携带 skill 偏好 → 传给 Agent (agent_policy 层)
```

### Cost Control / Permission
```
Cost: AgentExecutionResult.cost → 会话累计 (future /cost 真实统计)
Permission: AgentExecutionContext 扩展 user_id/role → RBAC (当前 require("user") 基线)
Audit: execution_records.json → audit/cost/replay 数据源 (已建立)
```

### Conversation 深化
```
当前: run_task 缺参 → CLARIFICATION
未来: 多轮澄清 (缺 project → 追问 → 补齐 → 执行) — LLMIntentParser (v0.3)
```

## 6. 边界

- 薄调 exec.cli.cmd_exec_run — 零复制执行逻辑
- 不制造假 Agent — 真实 AgentRuntime + LLM
- 确认门最小化 — run_task/create_project 敏感
- Core 零改动 — ExecutionLoop/Router/AgentRuntime/Provider 未触碰

---

> S10-049 文档完毕 | Agent Execution Kernel 落地 | 54 新测试 | 真实执行验证通过
