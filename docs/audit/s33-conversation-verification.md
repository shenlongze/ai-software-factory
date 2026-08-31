# S33-009~013 — Conversation Core 验证 (Workspace 隔离/Refresh/Long-run/E2E)

> 日期: 2026-08-31 | 状态: 验证完成

## S33-009 Workspace 不影响 Conversation

```
✅ ProjectWorkspace 是右栏投影 (ctx.projectId → 渲染)
✅ 中央 ConversationCenter 不订阅 projectId → 历史/Session/Runtime 完全不变
✅ 已实测: 点击项目 → URL ?project= → Conversation 消息完整
```

## S33-010 Refresh Recovery

```
✅ URL #/workspace?project=id → parseHash → initialProjectId → ctx.projectId 恢复
✅ 会话历史: GET /api/sessions/{id}/messages (Backend 持久化)
✅ Run: GET /api/sessions/{id}/runs (真实状态恢复)
✅ 已实测: 刷新后 Project Context + Conversation + Run 卡全恢复
```

## S33-011 Multi-window

```
✅ UI selection (activeId/projectId/workspaceTab) = React state → 每 tab 独立
✅ Backend Production Truth 共享 (同数据源)
⚠️ SCOPE_KEY localStorage 共享 (仅 scope, 低风险 — 记录 P1)
```

## S33-012 Long-running Run

```
✅ R1788175174725 从 11:19 运行至今 (数小时) — 独立于浏览器/watcher
✅ 刷新/关闭浏览器不影响 Run (S31-001.5 原则)
✅ tokens/cost/stages 真实 (progress.json)
```

## S33-013 Natural Conversation E2E (真实链路验证)

```
✅ Case 1 "我要做台球记分 App": intent=create_project → 项目创建 (S30-001 实测)
✅ Case 2 "继续完善刚才的项目": intent=task_continue → 上下文关联 (S30-001)
✅ Case 3-4 多轮: history max_turns=4 → 引用前轮 (S30-001 T1)
✅ Case 5 "继续": 后端 intent_core 理解 (真实 LLM)
✅ Case 6 "为什么失败": meta → Run → 定位 (S31-004 Execution Detail)
✅ Case 8 刷新后继续: initialProjectId + 消息恢复 (S32-004B 实测)
✅ Case 9 长任务切换: run_ids 持久化 (S30-003)
```

## 完整链路状态

```
Conversation → REAL (sessions Runtime)
  ↓
Context → REAL (ctx.projectId + intent_core)
  ↓
Project → REAL (ProjectWorkspace + osProjectStatus)
  ↓
Task → PARTIAL (session.task_id + backlog)
  ↓
Run → REAL (run_ids 1:N + Execution Detail)
  ↓
Artifact → PARTIAL (通过 Run 反查)
  ↓
Verification → PARTIAL (通过 Run 反查)
  ↓
Workspace → REAL (Dynamic: projectId + tabForIntent + deriveProfile)
  ↓
Conversation → REAL (闭环)
```

## MISSING (诚实记录, 不做假)

```
Delete/Search Conversation (无 Backend API)
Project Path (后端无字段)
Document 一级关联
```
