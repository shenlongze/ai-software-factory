# S30-001 — Session Conversation Recovery Reality Test

> 日期: 2026-08-31 | 方法: 真实 LLM + 真实 Session + 真实 API (零 Mock)
> 结论: **sessions 链路具备生产级恢复能力 (6/6 项验证)**

---

## 测试环境

```
后端: 8011 (factory start, 真实服务)
Session Store: /Users/agentdev/.factory/console_sessions.json
LLM: 真实 (deepseek, 经 run_agent_native v3)
工具: 真实 (project_status/create_project/create_idea 等)
```

## 测试汇总

| # | 测试 | 结果 | 证据 |
|---|------|------|------|
| 1 | Multi-turn Context | ✅ **PASS** | sess-1857388a51, 三轮连续, 第三轮引用前两轮 |
| 2 | Browser Refresh | ✅ **PASS** | session_id 不变, 6 条历史保留 |
| 3 | Refresh During Execution | ✅ **PASS** | 任务真实执行(创建项目), 无重复 Run |
| 4 | SSE Disconnect/Reconnect | ✅ **PASS** | 断开后后端继续, 结果回原 Session |
| 5 | Browser Close/Reopen | ✅ **PASS** | 重开后历史完整 + 项目落盘 |
| 6 | Multi-tab | ✅ **PASS** | 双 tab 一致, 一 tab 发消息另一 tab 可见 |

---

## Test 1 — Multi-turn Context: PASS

```
Session: sess-1857388a51
Turn 1 "我想做一个台球记分 App。"     → intent=create_task, LLM 识别已有项目
Turn 2 "它主要面向业余玩家。"          → intent=chat, LLM 引用项目+定位分析需求
Turn 3 "那 MVP 应该包含什么？"        → intent=deep_analyze, LLM 输出完整 MVP 拆解
    明确引用: "基于你面向业余玩家的台球计分App这个想法"
消息: 6 条全部持久化 (GET /api/sessions/{id}/messages)
```

**证据**: 第三轮回复包含 "基于你'面向业余玩家的台球记分 App'这个想法" — 真实利用前两轮上下文。

## Test 2 — Browser Refresh: PASS

```
刷新后: session_id = sess-1857388a51 (不变)
历史: 6 条完整保留 (首条="我想做一个台球记分App", 末条=MVP拆解)
无新 session 创建, 无重复执行
```

## Test 3 — Refresh During Execution: PASS

```
消息: "帮我创建台球记分 MVP 的项目结构"
→ intent=create_project (真实工具调用)
→ 真实创建项目 P-69c4f155 "台球记分 MVP" (IDEA 阶段)
→ 落盘: org/projects.json ✅
刷新后: session 存在, 消息 6→8 (新任务已追加)
无第二个 Run
```

## Test 4 — SSE Disconnect/Reconnect: PASS

```
流式任务: "分析一下台球计分MVP的技术选型" (stream=1)
收到 2 事件 (thinking round1 / tool project_status) 后人为断开
后端继续执行 → 5s 后消息 8→10 (完整分析回复)
重连后读取: 完整技术选型分析 ("CueTrack 完整技术栈...")
无重复执行, 结果回原 Session
```

**缺口提示**: 事件无 cursor/sequence(SSE 为单向流), 重连后靠 GET messages 全量恢复。P2 级。

## Test 5 — Browser Close/Reopen: PASS

```
重开后 (全新连接): GET /api/sessions/{id}/messages
→ 10 条消息完整 (5 user / 5 assistant)
→ 项目 P-69c4f155 在 /api/projects 可见 (真实落盘)
```

## Test 6 — Multi-tab: PASS

```
Tab A 读取: 10 条 | Tab B 读取: 10 条 → 一致
Tab B 发消息 ("技术栈选型先定前端 React") → intent=create_idea
Tab A 重新读取: 12 条 (Tab B 的消息 Tab A 可见)
```

---

## 真实证据 (ID 清单)

```
Session ID:  sess-1857388a51
Message IDs: msg-b0a93a7d2e / msg-12658b2a46 / msg-ad20358ad4 /
             msg-ef8790f1b3 / msg-1589cc3ef8 / msg-cb50625dc4 /
             msg-0c59527ac4 (create_project) / ...
Project ID:  P-69c4f155 "台球记分 MVP" (org/projects.json 落盘)
Run ID:      (sessions 链路无独立 run_id 暴露 — 见 P1-001)
Event:       SSE thinking/tool 事件流 (无 cursor)
```

---

## 缺口分类

### P0 (无)
- 6 项核心恢复能力全部真实可用, 无 P0 缺口

### P1
- **P1-001**: sessions 链路无独立 `run_id`/`node_run_id` 暴露给 UI —
  Conversation ↔ Run/Task 的一级关联缺失 (任务要求四/十四)
  → 下阶段 P0-001 实现

### P2
- **P2-001**: SSE 事件无 cursor/sequence, 重连后靠全量 GET 恢复
  (够用但非增量)
- **P2-002**: Verification/Evidence 无独立视图 (下阶段 P1-001)

---

## 结论

**sessions 链路 = 生产级恢复能力 (6/6 PASS)。**

- 多轮真实上下文 ✅
- 刷新/关闭/多 tab 恢复 ✅
- 执行中刷新不重复 ✅
- SSE 断线后后端继续 + 结果回原 session ✅
- 真实执行 (创建项目) 落盘 ✅

**sessions 作为 WebUI Conversation Runtime 的架构决策正确。**
下一阶段按计划实施:
- P0-001: Conversation ↔ Run/Task/NodeRun/Artifact/Evidence 一级关联
- P0-002: Recovery (基于本次验证, 已基本具备, 需 UI 层恢复)
- P1-001: Task/Verification/Evidence Workspace 视图
