# S31-006 — Command Center & Goal-first Home

> 日期: 2026-08-31 | 状态: 实施完成

## 1. Information Architecture

```
Home (中栏, 无会话时):
┌─────────────────────────────┐
│ ◆ What do you want          │
│     to accomplish?          │
│                             │
│ [ Natural Language Input ]  │
│                             │
│ 建议提示 (Build a ScorePocket│
│ / Analyze competitors / ...)│
│                             │
│ 正在进行 (Active Work)      │  ← opsOverview.projects.running
│ ● 1 个任务运行中            │
│                             │
│ 最近 (Recent Results)       │  ← opsOverview.recent_activity
│ ✓ TOOL_CALL  11:00          │
└─────────────────────────────┘
```

## 2. Command Center UX

- Goal-first 输入 (What do you want to accomplish?) — 已有, 保留
- Active Work: 真实运行中任务 (opsOverview.projects.running)
- Recent Results: 真实事件流 (opsOverview.recent_activity)
- 全部来自真实 Backend, 无 fake

## 3. Goal-first Interaction

用户输入自然语言 → ctx.send → 真实 Session → LLM Runtime (S30-004 已验证)。
**不创建第二套 Home Chat。**

## 4. API reuse

```
复用: /api/ops/overview (已有) — 无新增端点
无 HomeService/DashboardBackend/HomeRuntime
```

## 5. Real data evidence

```
opsOverview.projects.running → Active Work 卡
opsOverview.recent_activity → Recent Results 卡
```

## 6. Active Run evidence

```
浏览器实测: ● 1 个任务运行中 (真实 running)
Run 卡: R1788175174725 RUNNING (S30-004)
```

## 7. Refresh evidence

opsOverview 挂载时拉取 — 刷新后重新加载 (真实状态)。

## 8. E2E evidence

Home → 输入 → Conversation → Session → Run → Workspace (S30-004 已验证全链)。

## 9. Mock audit

```
0 fake active work / 0 fake recent result / 0 fake progress
Active Work 只在 running>0 时显示, Recent 只在有事件时显示
```

## 10. Performance

- 单次 opsOverview 请求 (无轮询/无 N+1)
- 无 Active Run 时不开 SSE
- 仅 2 个轻量数据块

## 11. Remaining P1/P2

```
P1: Recent Results 点击进入对应 Conversation/Artifact
P1: Active Work 点击进入 Workspace
P2: 项目 Context 卡 (点击进 Conversation-first)
```
