# S33-001 — Conversation Reality Audit

> 日期: 2026-08-31 | 纯审计 (零修改) | 依据: 真实代码

---

## 1. Current Architecture (真实)

```
WebUI ConversationCenter
  ↓ POST /api/sessions/{id}/messages?stream=1
sessions (console_sessions.py — SessionStore)
  ↓ run_agent_native (agent_loop.py)
  → call_with_tools → DeepSeek OpenAI 兼容 tool_calls
  → SSE (thinking → tool → thinking → tool → done)
  ↓ 工具调用
production_run (workflow_runner) → workflow_runs/{project}/{run}/
  ↓ 关联
session.run_ids[] (S30-003 1:N)
```

## 2. Conversation / Session 边界

```
sessions (console_sessions.py)      = LLM Runtime (REAL)
  ├── SessionStore: create/list/get/add_run/session_runs
  ├── create_session(scope, project_id, title, feature_id, task_id)
  └── 持久化 console_sessions.json

conversations (conversation_os.py)  = Semantic Layer (KEEP, 非 Runtime)
  ├── create/get/decision
  └── 长期语义/上下文层
```

**边界正确**: sessions = Runtime, conversations = 语义层。**无 DUPLICATE**。

## 3. Multi-turn 能力 (REAL)

```
_history_text(history, max_turns=4)  → 最近 4 轮传入 LLM
compact_context 工具 (v1.1.244)      → 压缩 → build_context → Spine 交接卡
                                     → 新会话可续接 (P1 Summary 已实现!)
```

## 4. Multi-session 能力 (REAL)

```
前端: createSession/selectSession/renameSession/archiveSession/truncate
      (ConversationContext, 全部真实 PATCH/GET)
左栏: 会话列表 (S32-002 重命名/归档 UI)
后端: GET/POST/PATCH /api/sessions + messages + runs
```

## 5. Project Context (REAL)

```
session.project_id (scope=project 时必填)
前端: ctx.projectId (S32-004B, 唯一 Selection State)
右栏: ProjectWorkspace (真实 osProjects/osProjectStatus/projectRuns)
```

## 6. Project Path (MISSING)

```
后端 Project Model 无 path 字段
→ 不能显示真实路径 → MISSING (不做假路径)
```

## 7-11. Conversation → Production Objects

| 关联 | 状态 | 机制 |
|------|------|------|
| → Run | REAL | session.run_ids (S30-003, 1:N) |
| → Task | PARTIAL | session.feature_id/task_id; 工具回写 backlog |
| → Document | MISSING | 无文档关联字段 |
| → Artifact | PARTIAL | 通过 Run → artifact (无一级关联) |
| → Verification | PARTIAL | 通过 Run → verification (无一级关联) |

## 12. Workspace Context (PARTIAL)

```
当前: activeTabId (task/code/preview/diff/evidence) + ctx.projectId
缺:   统一 WorkspaceContext {type: default|project|task|run|artifact|document|verification, object_id}
→ PARTIAL (S33-006 建模型)
```

## 13. Refresh (REAL)

```
URL #/workspace?project=id → initialProjectId → ctx.projectId 恢复
会话历史: GET /api/sessions/{id}/messages (Backend 持久化)
Run: GET /api/sessions/{id}/runs
```

## 14. Multi-window (PARTIAL)

```
仅 collapsed/pinned/SCOPE_KEY 用 localStorage (共享)
UI selection (activeId/projectId) 是 React state → 每 tab 独立
SCOPE_KEY 共享 → 潜在污染 (低风险, 仅 scope)
→ PARTIAL (S33-007 完善)
```

## 15. Natural Conversation (REAL 基础)

```
run_agent_native: 真实 LLM + 工具 + 多轮 history
compact_context: 长会话续接
意图识别: create_task/task_continue (K9 已验证)
```

## 16. Gap Matrix

| 能力 | 状态 |
|------|------|
| Multi-turn | REAL |
| Multi-session | REAL |
| Rename/Archive | REAL |
| Delete | MISSING (无 API) |
| Search | MISSING (无 API) |
| Project Context | REAL |
| Project Path | MISSING |
| → Run | REAL |
| → Task | PARTIAL |
| → Document | MISSING |
| → Artifact | PARTIAL |
| → Verification | PARTIAL |
| Workspace Context | PARTIAL |
| Refresh | REAL |
| Multi-window | PARTIAL |
| Context Assembly | REAL (max_turns=4 + compact) |
| 标题自动生成 | PARTIAL (会话 title 可指定) |
