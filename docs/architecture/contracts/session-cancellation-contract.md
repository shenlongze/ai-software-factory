# Session Cancellation Contract (F-01)

> 建立日期: 2026-09-01
> 触发: S-SESSION-CONTROL-AUDIT F-01 — 会话消息执行无停止/取消通道
> 前置: P0-001 (Execution Truth) CLOSED

## 1. 执行链 (Session Message → Runtime)

```
Session (sess-xxx, scope=company|project)
  └─ Message (POST /api/sessions/{id}/messages)
       ├─ [stream] _work() 线程 (fastapi_adapter ~6960)
       │     └─ run_agent_native(question, data_dir, project_id, service, session_id)
       │          ├─ 主循环 for _ in range(max_rounds)  (agent_loop ~1769)
       │          │    ├─ call_with_tools → LLM (timeout=120s, 阻塞)
       │          │    └─ dispatch → 工具 (bash_exec 等, 沙箱进程)
       │          └─ 硬收敛轮 (agent_loop ~2045)
       │          └─ → answer + calls → send_message 落库 → SSE 事件 → 前端
       └─ [sync] 同步分支 (fastapi_adapter 7142/7270)
             ├─ project: run_agent(v1) + validator
             └─ company: run_agent_native (P0-001 已统一)
```

### ID 层
| 层 | ID | 说明 |
| -- | -- | -- |
| Session | sess-xxx | 会话 |
| Message | (消息列表序号) | 无独立 ID |
| Agent | run_agent_native 调用 | 每消息一次 |
| Task/Node | chain_start → R{ts} | 仅执行链有; 普通消息无 |
| Run | R{timestamp} | 仅执行链 (agent_loop 1319) |
| Runtime | 工具沙箱进程 | bash_exec 子进程 |

## 2. 现有 Cancellation Primitive 盘点

| 层 | 能力 | 位置 | 状态 |
| -- | -- | -- | -- |
| workflow run | request_cancel / is_cancelled (内存 dict, 幂等) | factory-console/run_liveness.py:47 | ✅ 可复用模式 |
| workflow run cancel API | POST /api/runs/{project}/{run}/cancel | fastapi_adapter 6661 | ✅ |
| runtime session cancel | POST /api/runtime-sessions/{id}/cancel | fastapi_adapter 3646 | ✅ (不同概念) |
| **session message (agent_loop)** | **无** | — | ❌ **F-01 缺口** |
| LLM 调用 | timeout=120s (不可中途 abort) | agent_loop call_with_tools:145 | ⚠️ 等返回 |
| 工具进程 | 无 kill | bash_exec 沙箱 | ❌ |

**禁止重新实现已有能力**: 复用 run_liveness 的 request_cancel/is_cancelled 模式 (内存标志 + 线程内轮询)。

## 3. 状态模型 (复用现有, 不新增重复状态)

会话消息执行是同步函数调用 (无持久状态机), 取消语义用事件/返回值表达:

```
RUNNING (前端 sending=true)
  → CANCELLING (cancel API 已调用, 标志已设)
  → CANCELLED (run_agent_native 返回 cancelled=true)
  → CANCEL_FAILED (cancel API 异常 → 前端提示, 任务继续)
```

执行链 (chain_start) 已存在 CANCELLED 状态 (run_liveness + progress.json), 不重复建。

## 4. Cancellation Semantics (Stop 到底意味着什么)

对会话消息执行, Stop 明确覆盖:

| # | 语义 | 实现 |
| -- | -- | -- |
| 1 | Stop accepting new work | 发送中前端禁用发送按钮 (已有 disabled) + cancel 后新消息排队? 否 — 会话消息串行, cancel 只影响当前 |
| 2 | Stop current LLM generation | 无法中断 in-flight LLM 调用 (httpx 无 abort) → 等当前调用返回 (≤120s) |
| 3 | Stop tool execution | 无法 kill 已启动的沙箱进程 (本轮范围) → 工具返回后不再继续 |
| 4 | Stop subprocess | 同上, 记录为已知限制 |
| 5 | Stop current Node | 会话消息无 node; 执行链由 run_liveness 覆盖 |
| 6 | Stop remaining Nodes | 循环顶部检查 → 不再发起新 LLM/工具轮 |
| 7 | Stop whole Task | 会话消息 = 单任务; 返回 CANCELLED 即停止 |
| 8 | Stop Session Message | 本次目标: 用户 Stop → 后端真实停止后续轮次 → CANCELLED 回传前端 |

**明确的边界**: 当前 LLM 调用/工具调用完成后停止 (循环边界), 不是毫秒级 kill。
前端必须显示"正在停止…"直到收到 CANCELLED。

## 5. 幂等

```
Stop → Stop → Stop
```
- request_cancel 幂等 (dict 设 True, 重复无害)
- 后端 cancel API 重复调用返回当前状态, 不重复发事件
- 前端 Stop 按钮: 第一次点击后禁用/变 "停止中…"

## 6. 竞态

| Case | 处理 |
| -- | -- |
| A: RUNNING→Stop, 任务同时完成 | 完成优先: 若 LLM 已返回最终答案且未检查到 cancel → COMPLETED; 若先检查到 cancel → CANCELLED. 以后到者为准 (单线程检查点, 无竞争) |
| B: RUNNING→Stop, 工具同时启动 | 工具调用已发出则等其返回, 之后不再继续 (CANCELLED) |
| C: RUNNING→Stop, LLM 响应到达 | 同 A: 检查点在循环顶部, 响应后先查 cancel |
| D: RUNNING→Stop, Retry 触发 | 检查到 cancel 后不再触发 retry/继续 → CANCELLED |

## 7. Refresh / Reconnect

- cancel 标志在后端内存 (session_id → bool), **不依赖前端 React state**
- 刷新浏览器后 Stop 仍可调 cancel API 控制后端真实执行
- 前端从 run list / message meta 恢复 running 状态后显示 Stop 按钮

## 8. Session Isolation

- cancel 标志 key = session_id, 互不影响
- Session A Stop → 只设 A 的 flag; B 的 run_agent_native 不检查 A 的 key

## 9. 实现边界 (F-01 FIX)

1. `run_liveness.py` 扩展: `request_session_cancel(session_id)` / `session_cancelled(session_id)`
   (或复用 _CANCEL dict, key 前缀区分; 保持幂等)
2. `agent_loop.run_agent_native`: 主循环顶部 (1770 前) + 硬收敛前检查 session_cancelled(session_id)
   → 若取消: 停止循环, 返回 `{"answer": "（已停止）", "cancelled": True, "calls": calls}`
3. `fastapi_adapter`: `POST /api/sessions/{session_id}/cancel` → request_session_cancel →
   返回 {ok, status: CANCELLING}
4. 前端 `ConversationContext.send`: 发送中暴露 `cancel()` → AbortController.abort() + 调 cancel API;
   `AfConversationCenter`: sending 时显示 "⏹ 停止" 按钮 (输入区旁)
5. 前端收到 done(cancelled) → 消息标 CANCELLED (meta.status), 不追加虚假内容

## 10. 已知限制 (记录, 不阻塞)

- in-flight LLM 调用不可 abort (httpx 无原生取消) — 最坏等 120s timeout
- 已启动的沙箱工具进程不可 kill (本轮范围) — 工具返回后停止
- 这两个限制在 UI 上体现为 "正在停止…" 直到真实停止事件
