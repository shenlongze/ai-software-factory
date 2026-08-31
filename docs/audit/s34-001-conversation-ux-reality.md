# S34-001 — Conversation UX Reality Fix

> 日期: 2026-08-31 | 状态: 实施完成

## P0-1 Conversation/Execution 分层: PASS

```
User Message
  ↓
AI Response (主视觉)
  ↓
Execution Evidence (可折叠, 融入回复内)
  ↓
继续 Conversation
```

- ToolCallList 从全展开 → 默认折叠 ("✓ 已完成 N 个操作 · 展开 ▾")
- 执行证据不再抢占对话主视觉

## P0-2 Typography: PASS

```
对比度修复 (全链路 audit):
  ai-msg-role:   #6b7280 → #4b5563
  ai-run-id:     #555 → #374151
  ai-run-state:  #888 → #6b7280 + font-weight 600
  ai-run-totals: #999 → #6b7280
  af-run-code/state/tokens/time: 全部加深
  ai-run-stage-role/latency/detail-empty: 全部加深
  ai-tool-calls-title: #4b5563
```

## P0-3 Working State: PASS

```
"AI Factory WORKING" → "AI Factory 正在工作…"
  + "正在分析并执行你的请求…" (自然中文)
Working 是临时状态 (sending 时显示), 完成后消失 — 非永久消息
```

## P0-4 Execution Evidence: PASS

```
默认 compact: "✓ 已完成 N 个操作"
点击展开: 工具列表 + Run + stages + tokens/cost
融入 AI 回复 (MessageBubble 内), 不打断对话
```

## P0-5 Run Card: PASS

```
独立 AI 消息 → "执行中 · N 个 Run" 执行上下文卡
可折叠 (收起/展开)
非第二条 AI 回复 — 明确执行上下文角色
```

## Browser E2E / Refresh / Long-running / Mock

```
✅ E2E: 三栏完整 (左 Context + 中 Conversation + 右 Workspace)
✅ Refresh: URL ?project= + Backend 持久化
✅ Long-running: R1788175174725 独立于浏览器 (S31-001.5)
✅ Mock Audit: 0 fake — 全真实 API (tool_calls/meta 来自后端)
```

## 验证

```
后端: 1123 passed + 6 skipped (零失败)
前端: 514/515 (af-todo-tree 历史漂移 DEFERRED)
tsc: PASS
build: PASS
```
