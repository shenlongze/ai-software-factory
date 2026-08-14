# S10-048 — Intent Execution Kernel

> 日期:2026-08-15 | Sprint: S10-048 | 架构 + 执行流 + 示例 + 扩展
> 状态: 实现完成 (Phase 1-4), 文档记录

---

## 1. 架构

```
User Intent (自然语言)
    ↓
Session._dispatch
    ↓
IntentParser (KeywordIntentParser → IntentObject)
    ↓
IntentRouter (声明式映射, 无 if/else)
    ↓
ActionRegistry.get(action_name)
    ↓
ConfirmationGate (敏感 action → 用户确认)
    ↓
ExecutionContext (workspace/session/user/project/intent)
    ↓
Action.execute(context) → 调 Service Layer (org/exec/读 projects.json)
    ↓
ActionResult → Renderer (Human/Json)
    ↓
Factory Runtime
```

## 2. 模块

| 模块 | 职责 | 状态 |
|---|---|---|
| intent.py | IntentObject + IntentParser(ABC) + Keyword mock | ✅ (S10-047 扩展) |
| action.py | Action + ActionRegistry + ExecutionContext + ActionResult | ✅ |
| router.py | IntentRouter (type→action 声明式映射) | ✅ |
| actions.py | create_project / list_projects / show_status | ✅ |
| conversation.py | ConversationState + ConversationManager (基础 flow) | ✅ |
| confirm.py | ConfirmationGate (敏感 action 确认流) | ✅ |
| session.py | InteractiveSession 集成 (slash + intent 双入口) | ✅ |

## 3. 执行流示例

### 用户: "创建一个台球计分APP"

```
[1] KeywordIntentParser.parse → IntentObject
    {type: create_project, params: {name: "一个台球计分APP"}, confidence: 0.9}
[2] IntentRouter.route → create_project action (声明式映射)
[3] ConfirmationGate (敏感) → "将执行: create_project (...)" → y/N
[4] 确认通过 → ExecutionContext → action.execute
[5] 调 org.cli.cmd_project_register (Service Layer, 不复制业务)
[6] ActionResult → Renderer 展示
```

### 用户: "看看状态"

```
[1] parse → show_status (非敏感)
[2] route → show_status action → 直接执行 (无确认门)
[3] 显示: workspace / session_id / current_project / project_count
```

## 4. 测试

```
新增 (S10-048): test_session_action 10 + test_session_router 6 + test_session_intent_execution 8 + test_session_conversation 11 + test_session_confirm 18 = 53
全量: 8336 passed, 0 failed (基线 8283 → 8336, +53, 零回归)
```

## 5. 未来扩展

### Intent Layer 连接 Agent / Skill / MCP / Runtime

```
[现状]  Intent → Action → Service Layer (org/exec)

[未来]  Intent → Action → Agent/Skill/MCP/Runtime

连接点:
- Agent:    run_task intent → action 调 exec.cli.cmd_exec_run (已复用)
- Skill:    intent 参数携带 skill 偏好 → 传给 Agent (agent_policy 层)
- MCP:      IntentRouter 新增 action 类型 → MCP tool (注册式扩展)
- Runtime:  action 直接调 AgentRuntime (未来, 需权限强化)

扩展机制 (全部注册式):
- ActionRegistry.register(new_action) — 新能力即新 Action
- IntentRouter.register_route(intent_type, action_name) — 新意图映射
- KeywordIntentParser.keywords 扩展 / 未来 LLMIntentParser (ABC 已定义)
```

### ExecutionContext 扩展

```
未来: user_id (身份) / workspace (多租户) / permission (RBAC) / audit (审计)
现状: user="user" (基线) / workspace / session / project / intent
```

## 6. 边界

- CLI 不含业务逻辑: Action 只薄调 Service Layer
- 不制造假能力: 3 个 Action 全部连真实 Service
- 确认门最小化: 敏感 action (create_project/run_task) 走确认, 其余放行
- Core 零改动: ExecutionLoop/Router/AgentRuntime/Provider 未触碰

---

> S10-048 文档完毕 | Intent Execution Kernel 落地 | 53 新测试 | 8336 全绿
