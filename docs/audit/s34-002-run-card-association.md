# S34-002 — Run Card Message-Level Association

> 日期: 2026-08-31 | 状态: 实施完成

## 核心变化

```
之前: Run 卡 = Conversation 全局区域 (所有 Run 堆在底部)
现在: Run 卡 = AI Response 的执行证据 (归属触发它的那条回复)

Conversation Message
  ├── User Message
  └── AI Message
       ├── MessageContent
       ├── Tool Calls (折叠)
       └── Execution Evidence
            └── Run Card (真实, 归属本条)
```

## 实现机制(不伪造, 不破坏 Production Truth)

### 后端 (fastapi_adapter.py)

```
_work() 开头: _before_run_ids = session_runs(session_id)   ← 本轮前快照
assistant_meta.run_ids = 完成后 session_runs - before      ← 差集 = 本条触发的 Run
→ 持久化到 console_sessions.json (append_message meta)
→ GET messages 返回 → 刷新后归属不丢 (P0-5)
```

### 前端 (AfConversationCenter.tsx)

```
MessageBubble: meta.run_ids 非空 → 在该回复气泡内渲染 Run 卡
  runs 从全局真实 sessionRuns 按 run_ids 过滤 (状态真实, RUNNING→COMPLETED 只更新)
全局 Run 面板 (ai-run-context 底部) → 移除
```

## 验收

| Case | 结果 |
|------|------|
| A: 你好 → Run 在回复下 | ✅ meta.run_ids 归属 |
| B: 连续两轮不串 | ✅ 每消息独立 run_ids |
| C: 长任务刷新后原位置 | ✅ meta 持久化, 刷新后仍归属原消息 |
| D: Run 完成状态更新 | ✅ 真实 sessionRuns 过滤, 只更新状态不重建 |

## 验证

```
后端: 1126 passed (+1 run_ids 绑定测试)
前端: 515/516 (af-todo-tree 历史漂移)
tsc/build: PASS
```

## Mock Audit

```
✅ run_id 来自真实 session_runs 差集 (不伪造)
✅ 状态/tokens/cost 来自真实 production_run
✅ meta.run_ids 后端持久化 (非前端猜测)
```
