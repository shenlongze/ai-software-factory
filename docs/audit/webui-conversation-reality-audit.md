# WebUI Conversation Reality Audit — TRAE Work V2 版真实调用链审计

> 日期: 2026-08-31 | 阶段: 第一阶段 (只审计, 零修改)
> 对象: TRAE Work V2 WebUI (工作区未提交, 3600 行新增) + 后端真实链路

---

## 1. 审计对象确认

工作区存在 TRAE Work 完成的新版 WebUI(未提交, `git diff` 可见):
- `AfConversationCenter.tsx` → "Command Center V2" (+260 行)
- `AfWorkspace.tsx` (+560 行)
- `AfContextNav.tsx` (+346 行)
- `AfHeader.tsx` / `AfStatusBar.tsx` / `af.css` (+2534 行)
- 总计 3600 insertions / 486 deletions

**V2 版 tsc PASS + 测试 6/6 通过。** 能编译、能跑。

---

## 2. 真实调用链 (V2 版)

### 2.1 会话链路 (V2 ConversationCenter → 后端)

```
WebUI Input (用户输入)
  ↓  AfConversationCenter: ctx.send(text)  [ConversationContext.send]
  ↓  api.sessionSendStream(session_id, text, onEvent)
  ↓  POST /api/sessions/{session_id}/messages?stream=1   [fastapi_adapter.py:6395]
  ↓  run_agent_native (agent_loop v3)   [真实 LLM 代理]
  │    ├── 清洗/护栏/W8/审计引导
  │    ├── 工具调用 (project_status/code_scan/read_code/...)
  │    ├── 真实 LLM (deepseek) + SSE 流式事件 (thinking/tool/done)
  │    └── 结果: {user, assistant, session, meta:{intent, project, data_source}}
  ↓  SSE 事件 → ConversationContext setMessages (thinking_steps/tool_calls)
  ↓  AfConversationCenter 渲染 (执行阶段文案 + 工具调用卡 + 消息)
```

**✅ 会话链路 = 真实 LLM, 非 Mock。**

### 2.2 Workspace 链路 (V2 AfWorkspace → 后端)

```
AfWorkspace 挂载
  ↓  api.artifactContent(id)     → GET /api/artifacts/{id}/content   [真实]
  ↓  api.osProjectStatus(id)     → GET /api/projects-os/{id}/status  [真实]
  ↓  api.opsDrill(id)            → GET /api/ops/drill/{project_id}   [真实]
  ↓  渲染: Task/Code/Preview/Diff/Evidence Tab
```

**✅ Workspace = 真实 API, 非 Mock。**

### 2.3 Context 链路 (V2 AfContextNav → 后端)

```
AfContextNav 挂载
  ↓  fetch('/api/projects-os')           → Project 列表 [真实]
  ↓  fetch(`/api/projects/${projectId}`) → 项目详情 [真实]
  ↓  api.opsOverview()                   → 运行概览 [真实]
```

**✅ Context = 真实 API, 非 Mock。**

---

## 3. 断链分析 (每个 ? 的真相)

| 环节 | 存在 | 代码 | 真实 | Mock | 断链 |
|------|------|------|------|------|------|
| WebUI Input | ✅ | AfConversationCenter | — | — | — |
| → send | ✅ | ConversationContext.send | ✅ (sessionSendStream) | ❌ | — |
| → Intent | ✅ | run_agent_native | ✅ 真实 LLM | ❌ | — |
| → Agent | ✅ | agent_loop v3 | ✅ | ❌ | — |
| → Task/Node | ⚠️ | run_agent_native 内部 | 部分 (tools) | — | 🔴 无独立 Task/NodeRun 实体暴露给 UI |
| → Artifact | ✅ | AfWorkspace artifactContent | ✅ | ❌ | — |
| → Verification | ⚠️ | 工具调用内 | 部分 | — | 🔴 UI 无独立 Verification 视图 |
| → Evidence | ⚠️ | opsDrill | ✅ | ❌ | 🔴 UI 无独立 Evidence 视图 |
| → WebUI 渲染 | ✅ | AfConversationCenter/AfWorkspace | ✅ | ❌ | — |

**断链结论**:
1. **会话链路是真实的**(LLM + 流式 + 工具调用)——V2 比我想象的好
2. **但 Task/NodeRun/Verification/Evidence 没有作为一级对象暴露给 UI**——用户看不到"哪个 Agent 在干什么、验证了什么"
3. **Conversation 与 Run/Task 无持久关联**——刷新后能否恢复执行状态?需验证

---

## 4. V2 版相对 K9 版的改进 (审计所见)

| 维度 | K9 版 (已提交) | V2 版 (TRAE Work, 未提交) |
|------|--------------|--------------------------|
| 会话 | conversations 规则链路 | sessions 真实 LLM + SSE 流式 ✅ |
| 执行状态 | 无 | 执行阶段文案 (Planning/Researching/...) ✅ |
| 工具调用 | 无 | 工具调用卡 + thinking_steps ✅ |
| Workspace | 5 Tab 简版 | 更丰富的 Tab + 真实数据 ✅ |
| 视觉 | 基础 | 重设计 (+2534 行 CSS) ✅ |

**V2 版明显优于 K9 版——这是应该保留并继续的方向。**

---

## 5. 下一步 (第二阶段前必须确认)

### 5.1 待验证 (需要真实运行测试)
- [ ] V2 版在 5180 真实打开 (需 build)
- [ ] 会话全链路真实执行 (发消息 → LLM → 工具 → 结果)
- [ ] **刷新后会话/执行状态恢复** (P0, 任务要求十一)
- [ ] **断线重连恢复** (P0, 任务要求十二)
- [ ] **Conversation ↔ Workspace 联动** (P0, 任务要求十三)

### 5.2 缺口 (任务要求但 V2 未覆盖)
- [ ] Conversation 作为一级对象关联 Run/Task/NodeRun/Artifact/Evidence (要求四)
- [ ] 多轮会话上下文连续 (要求六/七) — 需验证 run_agent_native 的 history
- [ ] 系统状态与自然语言分层 (要求十八) — 有执行文案但需验证状态卡
- [ ] 失败真实呈现 (要求十六) — 需故意制造失败验证

### 5.3 架构决策 (需用户拍板)
- [ ] **会话系统选择**: V2 用 sessions (真实 LLM) vs K9 用 conversations (规则)?
  - 结论建议: **保留 sessions 链路** (真实 LLM), conversations 降级或对齐
- [ ] 是否引入 SSE 事件订阅 (要求十) vs 维持流式?

---

## 6. 结论

**V2 版 WebUI 不是"空壳 Chat"——它的会话链路是真实 LLM + 流式 + 工具调用,Workspace/Context 是真实 API。** 这改变了之前"全是 Mock"的判断。

真正的缺口是:
1. **Conversation ↔ Run/Task/Artifact/Evidence 的一级关联缺失**(UI 层)
2. **刷新/断线恢复未验证**(可能缺失)
3. **任务/验证/证据无独立视图**(用户看不到执行细节)

**建议**: 保留 V2 版作为基座,补上"一级对象关联 + 刷新恢复 + 执行状态分层",而不是重写。
