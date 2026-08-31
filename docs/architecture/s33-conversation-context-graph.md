# S33 — Conversation Context Graph (Target)

> 日期: 2026-08-31 | 依据: S33-001 审计

## 1. 目标图 (用户可理解)

```
Conversation A (台球记分 MVP)
  │
  ├── Project: P-69c4f155 (台球记分 MVP)
  │     ├── Tasks: backlog (PARTIAL 关联)
  │     ├── Documents: (MISSING 关联)
  │     └── Artifacts: (PARTIAL 通过 Run)
  │
  ├── Session: sess-1857388a51
  │
  ├── Run A: R1788175174725 (RUNNING)
  │     ├── NodeRun (stages)
  │     ├── Agent: product-manager/uxui/...
  │     ├── Artifact: (通过 Run)
  │     └── Verification: (通过 Run)
  │
  └── Run B: R1788174921245 (RUNNING)
        └── ...
```

## 2. 当前已实现边 (REAL)

```
Conversation → Session: 1:1 (Session 是 Runtime)
Session → Run: 1:N (run_ids, S30-003)
Session → Project: project_id
Conversation → Decision: conversation_os
```

## 3. 待补齐边 (P1)

```
Conversation → Task: session.task_id/feature_id (PARTIAL → REAL)
Conversation → Document: 需后端文档关联 (MISSING)
Conversation → Artifact: 通过 Run 反查 (PARTIAL)
Conversation → Verification: 通过 Run 反查 (PARTIAL)
```

## 4. 数据流 (目标)

```
用户输入
  → run_agent_native (history + context)
  → 工具调用 (create_task / start_workflow / compact_context)
  → Run 创建 → session.run_ids += run_id (S30-003)
  → Workspace 读取: projectRuns / osProjectStatus / artifacts
  → UI 投影: Conversation + Workspace
```

## 5. 跨会话项目共享 (目标)

```
Conversation A (产品设计) ──┐
                            ├── Project ScorePocket (共享 Production Context)
Conversation B (开发) ──────┘
历史不混合, 项目事实共享
```

## 6. Context Awareness 目标

```
用户说 "这个为什么失败?"
  → AI 读当前 WorkspaceContext {type: run, object_id: R...}
  → 定位 Run → 失败原因 → 回复
用户说 "继续"
  → AI 读当前 Production Graph 状态
  → 定位未完成任务 → 继续
```

## 7. 实施序 (S33-002+)

```
S33-002: State Model (Conversation/Session/Message 明确)
S33-003: Multi-Conversation Management (已 REAL, 补 Delete/Search gap 记录)
S33-004: Project Context (已 REAL, 补 Project Path gap)
S33-005: Production Object Association (Task/Artifact/Verification)
S33-006: Dynamic Workspace Context (WorkspaceContext 统一模型)
S33-007: Refresh / Multi-window (完善 SCOPE_KEY 隔离)
S33-008: Natural Conversation E2E
```
