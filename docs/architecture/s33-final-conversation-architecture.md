# S33 — Conversation Model (Target)

> 日期: 2026-08-31 | 依据: S33-001 审计 (真实代码)

## 1. 核心模型

```
Conversation (语义层, conversation_os)
  ├── id / title / created_at / updated_at / status
  ├── project_id (长期上下文)
  └── decisions / summary
        │
        └── Session (LLM Runtime, console_sessions)
              ├── id / scope / project_id / title / status
              ├── run_ids[] (S30-003, 1:N)
              ├── feature_id / task_id
              └── messages[]
                    └── run_agent_native (真实 LLM + SSE)
```

## 2. 职责分离

```
Production Truth:  Backend (sessions/conversations/production_run)
UI Selection:      Frontend (ctx.projectId / activeId)
Conversation Context: Backend 持久化 (project_id)
三者不混 — 无三套事实
```

## 3. Context Assembly (已实现, 保留)

```
Recent Messages (max_turns=4)
+ compact_context (压缩 → build_context → Spine 交接卡)
+ Project Context (project_id)
+ 工具结果回写
```

## 4. Workspace Context (目标)

```
WorkspaceContext {
  type: default | project | task | run | artifact | document | verification
  object_id: string
}
由 Conversation/Run 驱动 → AfWorkspace 渲染对应视图
```

## 5. Production Graph (目标)

```
Conversation
  ├── Project
  │     ├── Tasks
  │     ├── Documents
  │     └── Artifacts
  ├── Session
  ├── Run (1:N via run_ids)
  │     ├── NodeRun
  │     ├── Agent
  │     ├── Artifact
  │     └── Verification
  └── Decisions
```

## 6. P0/P1 路线

```
P0 (S33-003/004): Multi-session + Project Context 已 REAL
P0 (S33-005):     Conversation → Run/Task 关联 (Task PARTIAL→REAL)
P0 (S33-006):     WorkspaceContext 统一模型
P0 (S33-007):     Refresh + Multi-window 完善
P1:               Delete/Search (Backend)
P1:               Project Path (Backend 加字段)
P1:               Document 关联
```
