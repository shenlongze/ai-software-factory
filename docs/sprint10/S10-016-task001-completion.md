# S10-016 Task 001 Completion Report — AI Employee Runtime Foundation

> 日期: 2026-08-12 | 状态: 完成 (待人工审核) | Sprint: S10-016 AI Employee Execution Layer
> 定位: 从 "用户看到 AI 在工作" → "AI Employee 开始执行工作" 的基础

---

## 1. 设计说明

```
S10-016 目标: 让 AI 软件生产过程真正运行。
核心链路: Task → Agent Assignment → Agent Runtime → Execution → Runtime Event → Artifact → Quality Gate

Task 001 范围: 建立可靠 Runtime 基础 — 最小 Agent Runtime Domain。
未实现 (后续 Task): Agent Executor / MCP Integration / Tool Calling / Autonomous Loop

设计决策 (基于现有 Domain 侦察):
  - 复用: ExecStore 模式 (JSON 原子写) / AgentRuntime.execute() / EmployeeExecutor / timeline / registry
  - 区分: S10-004 RuntimeInstanceStore (browser|terminal 沙箱) ≠ Agent 执行会话 — 不扩展不冲突
  - 新建: 独立 Runtime Session Domain (root/runtime-sessions/sessions.json)
```

## 2. Domain 变化

```
新增 factory-exec/exec/runtime_session.py:
  RuntimeSession: session_id/agent_id/task_id/workflow_id/status/created_at/
                  started_at/finished_at/events[]
  RuntimeEvent:   event_id/session_id/type/message/created_at/data?
    7 类型: agent_started/task_received/execution_started/tool_called/
            output_generated/execution_finished/execution_failed
  状态机: PENDING → RUNNING → SUCCESS|FAILED; RUNNING → CANCELLED
          (非法转换 → RuntimeSessionError; append_event 仅 RUNNING; 终态冻结)
  RuntimeSessionStore: 原子写/损坏响亮失败/重启可查

Console 层 (service.py + api/runtime_session.py + fastapi_adapter.py):
  ConsoleService 8 方法: create/start/append_event/complete/cancel/
                        list_running/get_session/get_by_task (session_store 缺省失败安全)
  8 API 路由 + 错误映射 (400/404/409)

前端 (api/domain.ts + client.ts):
  toRuntimeSession: RuntimeSession → RuntimeActivity (兼容 S10-015 时间线)
  8 个 fetch 封装 (create/start/events/complete/cancel/list/detail/task)
```

## 3. Runtime 生命周期

```
真实联调证据 (curl 8011):
  POST /api/agents/developer-1/sessions
    → rs-1788d4b2 (PENDING, created=2026-08-12T05:22:07Z)
  POST /api/runtime-sessions/rs-1788d4b2/start
    → RUNNING, started=05:22:12Z
  POST .../events ×3 (agent_started/tool_called/output_generated) → 200
  POST .../complete {"success":true}
    → SUCCESS, finished=05:22:18Z
  GET /api/runtime-sessions/rs-1788d4b2 → 详情 + 3 事件时间线
  GET /api/runtime-sessions?status=running → 0 (正确)
  GET /api/tasks/TASK-a1/runtime → 1 session
```

## 4. API 说明

| 端点 | 方法 | 说明 |
|---|---|---|
| /api/agents/{agent_id}/sessions | POST | 创建 (body: task_id, workflow_id?) |
| /api/runtime-sessions/{id}/start | POST | → RUNNING |
| /api/runtime-sessions/{id}/events | POST | 追加事件 |
| /api/runtime-sessions/{id}/complete | POST | → SUCCESS/FAILED |
| /api/runtime-sessions/{id}/cancel | POST | → CANCELLED |
| /api/runtime-sessions?status=running | GET | 运行中 |
| /api/runtime-sessions/{id} | GET | 详情 + events |
| /api/tasks/{task_id}/runtime | GET | 某 Task 的 Runtime |

## 5. 测试结果

```
Backend pytest:  7569 passed (0 failed) — 含新增:
  tests/exec/test_exec_runtime_session.py       (40: 状态机/事件/持久化/非法转换)
  tests/console/test_console_runtime_session_api.py (22: Service 全链路/API 端到端/404-409-400)
  权限边界测试同步 (runtime-sessions 写路由入白名单)
Frontend vitest: 664 passed (56 files) — 含 runtime-session-adapter.test.ts (5)
tsc: 0 error | build: ✓
```

## 6. 限制

```
1. Runtime Session 是基础能力 — Agent Executor 尚未接入 (Task 002)
   (当前 session 由 API 手动驱动, 未绑定真实 AgentRuntime.execute())
2. 前端仅准备 Adapter (toRuntimeSession) — 未新建页面 (按用户约束)
   (S10-015 Runtime Timeline 未来可显示真实 session 事件)
3. 8011 启动需要 PYTHONPATH 含 factory-core/org/exec (events 包冲突已解决)
4. Cancel/FAILED 路径测试覆盖, 真实联调仅验证 SUCCESS 路径
```

## Commit

```
a271f8b  feat(S10-016): implement AI employee runtime foundation
```

---

> 状态: 完成 | 下一步: 等待人工审核 (Task 002 Agent Executor 不自动进入)
