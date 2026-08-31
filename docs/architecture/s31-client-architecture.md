# S31 — Client Architecture (Target)

> 日期: 2026-08-31 | 依据: S31-005 审计 (真实代码)

## 1. Client Architecture

```
Production Core (Backend :8011)
      ↓ API Contract (client.ts 模式)
  ┌────┼────┐
 Web  Desktop  Mobile (未来)
```

- 一个 Backend 足够 ✅
- Web/Desktop/Mobile 共享同一 Backend Contract ✅
- 当前: Web = 唯一实现; Desktop = Shell (launcher); Mobile = 未来

## 2-4. Client Boundary

| Client | 共享 | 专属 |
|--------|------|------|
| Web | Conversation/Workspace/API Contract | Browser Preview, UI 渲染 |
| Desktop | 同上 (未来复用 Web UI) | 窗口管理, Native FS, 系统集成 |
| Mobile | 同上 (未来) | Touch UI, 移动能力 |

**原则**: Client 只负责 Query/Subscribe/Project/Interact, 不拥有 Production Truth。

## 5. Shared Layer (未来, 非现在)

```
ui/shared/ (仅当 Mobile 出现时)
├── api/ (client 契约)
├── models/ (DTO)
├── workspace-model/
├── conversation-model/
└── formatting/
```

**当前单 Client 不抽共享** — 避免为架构漂亮强行抽象。

## 6. Workspace Boundary

- **Model 共享**: WorkspaceView/ViewType/Context (纯类型, 可放 models/)
- **Renderer client-specific**: React (Web) / Tauri (Desktop) / Flutter (Mobile 未来)
- 当前: AfWorkspace (React) 已实现, 模型在 models/types.ts — 边界已正确

## 7. Conversation Boundary

- **Backend**: Session/Run/Messages (Production Truth)
- **Shared Client Contract**: SessionSummary/SessionRunSummary (types.ts)
- **Client UI**: AfConversationCenter (React)
- **无事实分裂**: 8 组件共用 ConversationContext ✅

## 8. Production Object Boundary

```
Run/Task/NodeRun/Artifact/Verification/Evidence
  = Backend Production Truth (绝对)
Client = Query/Subscribe/Project (只读投影)
```

**无第二套 Production State** ✅

## 9. API Boundary

- 唯一 client.ts (115 方法), 无 Web/Desktop-specific production API
- Desktop 不调用业务 API (无业务层)

## 10. Event/SSE Boundary

```
Backend Event → Client Transport (EventSource) → Client State → UI
```
runtimeClient.subscribeEvents 是纯传输封装, 无 Production semantics ✅

## 11. State Boundary

- AppState (轻量 UI 状态) + ConversationContext (会话)
- 不承载 Production Truth

## 12. Repository Boundary (推荐, 不迁移)

```
当前 (健康):
  factory-console/web/frontend/  (Web UI)
  desktop/                       (Desktop Shell)
  factory-console/web/backend/   (Backend)

未来 (Mobile 时):
  ui/web + ui/desktop + ui/mobile (迁移 P1)
```

## 13. Module Boundary (与 Client 的关系)

```
S30-002 已确认 (不变):
  sessions = Runtime (WebUI 消费)
  conversations = semantic layer
  conversation_os = Application/Context Layer
  workflow_runner = orchestration
  professional_workflow = executor factory
  workforce.py = orchestrator

Client 只与 sessions/API 交互, 不触碰内部模块边界 ✅
```

## 14. Port/Runtime Boundary

```
8011 Backend | 5180 Production Static | 5173 Dev Server
Desktop/Web/Mobile 全部消费 8011 同一 Contract ✅
```

## 15. Migration Plan (未来)

```
P0: 无 (当前无阻塞)
P1 (Mobile 立项时): ui/web + ui/desktop 迁移 + ui/shared 抽取
P2: shell/ 死组件清理 (AgentTimeline/ExplorerNav 等半死)
```

## 16. 最终回答

```
一个 Backend 足够?              ✅ 是 (8011)
Web/Desktop/Mobile 共享 Backend? ✅ 是 (同一 Contract)
哪些 Client 能力共享?            API Contract/DTO/Workspace Model (Mobile 时抽)
哪些 UI client-specific?        Renderer (React/Tauri/Flutter)
Workspace Model 放哪?           models/types.ts (共享) + AfWorkspace (Web renderer)
Conversation Model 放哪?        Backend (Truth) + types.ts (Contract) + Context (UI)
Production Object 放哪?         Backend (绝对 Truth)
API Contract 放哪?              api/client.ts (Web) / 未来 ui/shared/api
SSE/Event 放哪?                 runtimeClient (传输) + Backend (事实)
State 放哪?                     AppState (UI) + ConversationContext (会话)
ui/ 目录如何组织?               当前保持, Mobile 时 ui/web+desktop+mobile
Module Boundary 如何定义?        S30-002 已定义, Client 只走 API
```

## 结论

**当前 Client Architecture 健康, 无需立即重构。** 唯一建议: 未来 Mobile 立项时再建 ui/shared 并迁移目录。本阶段零代码变更。
