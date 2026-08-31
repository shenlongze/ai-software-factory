# S33 — Conversation-First AI Factory WebUI 最终 Reality

> 日期: 2026-08-31 | 状态: 完成

## 完整链路 (每级标记)

```
Conversation → REAL    (sessions Runtime, SSE streaming, multi-turn history)
  ↓
Context → REAL         (ctx.projectId + intent_core + meta.project 联动)
  ↓
Project → REAL         (ProjectWorkspace: osProjects/osProjectStatus/projectRuns)
  ↓
Task → PARTIAL         (session.task_id + backlog; 无一级 UI 任务卡)
  ↓
Run → REAL             (run_ids 1:N + Execution Detail 展开)
  ↓
Artifact → PARTIAL     (通过 Run 反查; Workspace Artifact Panel)
  ↓
Verification → PARTIAL (通过 Run 反查; Evidence Panel)
  ↓
Workspace → REAL       (Dynamic: projectId + tabForIntent + deriveProfile)
  ↓
Conversation → REAL    (闭环)
```

## 最终架构

```
┌──────────────┬────────────────────────┬──────────────────────────┐
│ Context      │ Conversation           │ Dynamic Workspace        │
│ 💬 对话      │ 用户 ↔ AI (真实 LLM)    │ 当前 Context 投影         │
│ ▣ 项目       │                        │ ProjectWorkspace         │
│   + 新建     │ 多轮/流式/工具调用       │ (名称/状态/进度/Run/任务) │
│ ◷ 最近      │                        │ 或默认 Tab (意图驱动)      │
└──────────────┴────────────────────────┴──────────────────────────┘
```

## 用户最终体验

```
新建会话 → 自然语言 → AI 理解上下文 (project/task/run)
→ 真实执行 → Run 关联会话 → Workspace 自动跟随
→ 刷新恢复 → 长任务后台持续 → 回到会话继续
全程不离开 Conversation
```

## MISSING (诚实记录, P1 Backend)

```
Delete/Search Conversation
Project Path
Document 一级关联
Task 一级 UI 卡
```

## 验证证据

```
后端: 1125 passed
前端: 514/515 (af-todo-tree 历史漂移 DEFERRED)
tsc/build: PASS
真实: S30-001~004 + S32-004B + S33 联动 (浏览器实测)
```
