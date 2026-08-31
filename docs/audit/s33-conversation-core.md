# S33-002~008 — Conversation Core 建设 (State/Context/Workspace 联动)

> 日期: 2026-08-31 | 状态: 实施完成

## S33-002 Conversation State Foundation

```
已有 (审计确认):
  Session { id/scope/project_id/title/status/run_ids/messages } — REAL
  ConversationContext (前端): activeId/projectId/messages/workspaceTab — REAL
Context 表达: current_project (ctx.projectId) + current_run (run_ids) 已有
```

## S33-003 多轮自然会话

```
已有 (REAL):
  run_agent_native: 真实 LLM + history (max_turns=4) + compact_context
  意图: intent_core.understand_intent (create_project/deep_analyze/task_continue)
非关键词正则 — conversation_os 规则未重入 LLM Runtime ✅
```

## S33-004 Conversation Management

```
已有 (REAL): 新建/切换/重命名/归档 (S32-002)
MISSING (记录): Delete/Search — 无 Backend API, 不做假
```

## S33-005 Project Context

```
已有 (REAL): ctx.projectId + ProjectWorkspace (S32-004B)
MISSING (记录): Project Path — 后端无字段
```

## S33-006/007 Conversation → Production Graph + Context Resolution

```
已有 (REAL):
  后端 agent_result.meta = {intent, project, data_source, target, tool_calls, evidence}
  前端 SSE done 事件 → 本次新增: meta.project → setProjectId (自动联动)
  intent_core 后端意图解析 (S33-007 Context Resolution 底层)
```

## S33-008 Dynamic Workspace

```
已有 (REAL):
  tabForIntent(intent) → task/code/preview (意图→Tab)
  deriveProfile(sending, message) → prd/coding/debug/qa (消息→Profile)
  ctx.projectId → ProjectWorkspace (项目 Context)
本次新增: done 事件 project 联动 (执行后右栏自动跟随)
```

## 本次改动

```
ConversationContext.tsx: SSE done → meta.project → setProjectIdState (自动联动)
AfWorkspace.tsx: deriveProfile 导出 (测试用)
k9-workspace.test.tsx: +2 测试 (tabForIntent/deriveProfile, 14/14)
```

## 验证

```
后端 1125 passed
前端 514/515 (af-todo-tree 历史漂移)
k9 14/14
tsc PASS
```
