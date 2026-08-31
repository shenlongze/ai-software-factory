# S30-ARCH — Module Boundary Audit

> 日期: 2026-08-31 | 方法: 纯审计 | 依据: 代码依赖 (非目录名)

---

## 一、当前真实 Module Map (业务能力)

| Module | 位置 | 边界质量 | 说明 |
|--------|------|---------|------|
| Conversation (会话) | conversation_os.py | ⚠️ PARTIAL | 规则链路 (conversations) vs LLM 链路 (sessions 在 console_sessions.py) — **两套** |
| Session (会话运行时) | console_sessions.py | ✅ GOOD | 真实 LLM 链路, sessions_store |
| Intent | conversation_os.py (规则) + run_agent_native (LLM) | ⚠️ DUPLICATED | 两套 intent 检测 |
| Project | project_os.py + org/projects.json | ✅ GOOD | 真实落盘 |
| Task | task_tree.py + workforce.py | ⚠️ PARTIAL | task_tree (OS) vs workforce task (旧) 并存 |
| Run/NodeRun | production_run.py + node_runtime.py | ✅ GOOD | 执行实体 |
| Execution | workflow_runner.py + professional_workflow.py | ⚠️ PARTIAL | 两套执行链 (workflow_runner 旧, professional_workflow 新) |
| Artifact | artifact_lifecycle.py | ✅ GOOD | 统一生命周期 |
| Verification | verification.py | ✅ GOOD | 真实验证 |
| Evidence | (集成于 run/artifact) | ⚠️ WEAK | 无独立模块 |
| Recovery | recovery_service.py + self_healing.py | ⚠️ PARTIAL | 两套恢复 |
| Governance | governance_service.py | ✅ GOOD | 审批链路 |
| Agent/Workforce | workforce.py + workforce_os.py + agent_kernel.py | ⚠️ DUPLICATED | 3 个 agent 相关模块 |
| LLM | llm_router.py + llm_control.py | ⚠️ PARTIAL | 路由+控制分离 |
| Experience/Learning | learning_engine_v2.py + production_experience.py | ⚠️ PARTIAL | 多套 |
| 不存在的 | Discovery/Market/Competitive/UX/Design | ❌ MISSING | 生命周期阶段是字符串, 非模块 |

## 二、依赖图 (真实跨模块 import)

```
unified_contract (底座, 0 依赖)
  ↑
conversation_os ← project_os ← task_tree
  ↑                ↑
  └── workforce / production_run / governance / self_healing
operational_state ← production_run / project_os / control_tower
governance ← artifact_lifecycle / production_run / node_runtime
workflow_runner ← config / llm_control / llm_router
professional_workflow ← agent_kernel / artifact_lifecycle / verification / production_guidance
```

**好的**: unified_contract 是干净底座, 依赖方向清晰。
**问题**: 无严格分层 — 任何模块可直接 import 任何模块 (平铺), 无 domain/application/api 分层。

## 三、Module Boundary Problems

| # | 问题 | 严重度 | 证据 |
|---|------|--------|------|
| 1 | **双会话事实来源**: sessions (LLM) vs conversations (规则) | 🔴 P0 | console_sessions.py + conversation_os.py |
| 2 | **双 Intent**: 规则正则 vs LLM | 🟡 P1 | INTENT_PATTERNS vs run_agent_native |
| 3 | **双执行链**: workflow_runner vs professional_workflow | 🟡 P1 | 两套 executor |
| 4 | **3 个 Agent 模块**: workforce/workforce_os/agent_kernel | 🟡 P1 | 角色定义分散 |
| 5 | **双恢复**: recovery_service vs self_healing | 🟢 P2 | 职责重叠 |
| 6 | **无 module 分层**: 平铺在 factory-console/ | 🟡 P1 | 68 个平铺 py |
| 7 | **生命周期阶段非模块**: Discovery/Market/UX 是字符串 | 🟡 P1 | 无独立模块 |

## 四、UI Module Mapping

| Module | Web | Desktop | CLI | API |
|--------|-----|---------|-----|-----|
| Conversation | ✅ V2 Center | (Tauri 复用 web) | ✅ sessions CLI | ✅ /api/sessions |
| Project | ✅ AfContextNav/Workspace | 同 | ✅ project CLI | ✅ /api/projects-os |
| Task | ⚠️ AfWorkspace Task Tab | 同 | ✅ | ✅ |
| Artifact | ✅ Code/Preview Tab | 同 | ✅ | ✅ /api/artifacts |
| Verification | ⚠️ 无独立视图 | 同 | ✅ | ✅ |
| Governance | ✅ 审批卡 | 同 | ✅ | ✅ |

**UI 无业务逻辑重复** (前端零 import 后端模块, 只走 API)。✅

## 五、目标 Module Architecture

```
Client Layer (Web/Desktop/Mobile — 只走 API)
    ↓
Application/API Layer (fastapi_adapter — 统一 Backend :8011)
    ↓
Domain Modules (业务能力, 每个有 domain/api/cli/events/tests)
    │  Conversation  Session  Project  Task  Run  Execution
    │  Artifact  Verification  Evidence  Governance  Agent  LLM
    ↓
Platform (unified_contract / events / persistence)
    ↓
Runtime (executors / sandbox / MCP — 不复制 Backend)
```

**核心原则**: 
- Module = 能力边界, 不是独立 Server
- Client = Web/Desktop/Mobile, 不是业务 Module
- Runtime = 执行环境, 不复制 API
- Backend = 统一 API Host (8011), 不被每个 Module 重复实现

## 六、结论

**当前没有 Backend duplication (8011 唯一), 没有多 Orchestrator, 没有 UI 强耦合。**
真正的问题是:
1. **模块内部分裂** (sessions/conversations, workflow_runner/professional_workflow)
2. **无分层** (68 模块平铺)
3. **生命周期阶段非模块**

**是否进入 Repository Refactor**: 建议**暂缓** — 先解决 P0 (会话事实来源统一), 再考虑目录重组。
