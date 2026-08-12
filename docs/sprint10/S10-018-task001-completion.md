# S10-018 Task 001 Completion Report — Tool Runtime Foundation

> 日期: 2026-08-12 | 状态: 完成 (待人工审核) | Sprint: S10-018 Tool Runtime
> 定位: AI Employee 从 Decision 升级到 Decision → Tool → Result → Observation

---

## 1. 架构变化

```
新增 factory-exec/exec/tool.py:
  Tool (id/name/description/input_schema/output_schema/handler/
        permission_policy/enabled/created_at — 纯内部, 不绑 OpenAI/MCP)
  ToolResult ({success, output, error, metadata})
  ToolPermissionPolicy (默认全部禁止; backend-1 → filesystem.read 白名单)
  ToolRegistry (register 冲突/validate/unregister/get/list/with_system_tools)
  validate_against_schema (最小 JSON Schema 校验)
  ToolExecutor (Lookup → Enabled → Permission → Schema → Execute;
                失败返回明确 ToolResult.failed, 不吞异常)

新增 factory-exec/exec/tools/filesystem.py:
  filesystem.read (workspace 沙箱: 相对路径强制/../穿越拒绝/绝对路径拒绝/
                  ~ 和盘符拒绝/%2F %5C 编码分隔符拒绝/symlink 逃逸拒绝)

扩展 execution_loop.py: tool_executor kwarg + ACTION_REQUIRED Tool 分支
扩展 runtime_session.py: RuntimeEvent 14→18 (+tool_requested/started/completed/failed)

新增 API: GET /api/tools + POST /api/tools/{tool_id}/execute
```

## 2. Tool Runtime 设计

```
Planner → Decision (ACTION_REQUIRED)
  ↓ Action {type: "tool", tool_id, input}
  ↓ ToolExecutor: Lookup → Permission Check → Input Validation → Execute
  ↓ tool_requested / tool_started / tool_completed (或 tool_failed)
  ↓ ToolResult → observation_received → Continue (再次 Planner) 或 Complete
S10-017 兼容: noop Action → MockActionExecutor 旧流程不变
```

## 3. Tool Model

```
Tool: id/name/description/input_schema/output_schema/handler/
      permission_policy/enabled/created_at
ToolResult: success/output/error/metadata (失败必须有 error)
设计: Tool 是独立能力, 不绑定 OpenAI function calling / MCP / 任何第三方协议
未来兼容: Internal Tool / MCP Tool / Skill Tool / API Tool
```

## 4. Permission

```
最小权限表: backend-1 → [filesystem.read]; 其他 Agent 默认禁止
权限失败 → ToolResult.failed ("permission denied") + tool_failed 事件
真实验证: flutter-dev 调 filesystem.read → HTTP 403
```

## 5. API

```
GET  /api/tools                    → {tools: [{id, name, description, enabled}]}
POST /api/tools/{tool_id}/execute  → {success, output?, error?}
  body: {agent_id, input, context?}
  错误映射: 404 (not found) / 403 (permission) / 400 (schema/输入)
```

## 6. 测试结果

```
Backend pytest:  7688 passed (0 failed 修复后) — 含新增:
  tests/exec/test_exec_tool.py              (35: Model/Registry/Executor/Permission/Schema/Sandbox)
  tests/exec/test_exec_execution_loop.py    (33: 含 TOOL_ROUND_CHAIN 9 事件链保序 7 tests)
  tests/exec/test_exec_runtime_session.py   (51: 事件 14→18)
  tests/console/test_console_tool_api.py    (15: API 端到端/403/404/400)
  tests/console/test_console_web_adapter.py (29: 权限边界 +tool 写面)
Frontend vitest: 667 passed (56 files) — 含 Tool 类型 + tool_* 人话映射
tsc: 0 error | build: ✓
```

## 7. curl 证据 (真实, 8011)

```
1. GET /api/tools
   → {tools: [{id: "filesystem.read", name: "Filesystem Read", enabled: true}]}
     (Tool Registry 证明)

2. POST /api/tools/filesystem.read/execute {agent_id: backend-1, input: {path: "tasks/T-001.json"}}
   → success=True, output: {content: '{"id": "T-001", "title": "Fix markdown parser", ...}'}
     (Tool Runtime 真实执行证明)

3. 权限: POST ... {agent_id: flutter-dev} → HTTP 403 (backend-1 白名单生效)

4. 沙箱: POST ... input: {path: "../../etc/passwd"} → "path outside workspace" (穿越拦截)

5. Runtime Session 完整 9 事件链 (单元测试 TOOL_ROUND_CHAIN 保序锁住):
   agent_started → task_received → thinking_started → decision_created →
   tool_requested → tool_started → tool_completed → observation_received →
   execution_completed
   (无 LLM key → POST /api/runtime/execute 诚实 FAILED 于 ANALYZE —
    不伪造 tool 决策; tool 决策路径由单测覆盖)
```

## 8. MCP 后续规划

```
S10-018 已预留 (不实现 MCP):
  Tool 纯内部模型 — MCP Tool 可作适配器接入 (handler 包装)
  ToolRegistry — 未来注册 MCP Client 暴露的工具
  ToolExecutor — Permission/Schema 校验对 MCP 工具同样生效
  filesystem.read — 沙箱模式可扩展为 MCP filesystem 服务器
后续: MCP Client 适配器 → 注册外部工具 → Skill 解析 → Multi Agent 共享工具
```

## Commit

```
12cdffe  feat(S10-018): implement tool runtime foundation
```

---

> 状态: 完成 | 下一步: 等待人工审核 (MCP / Skills / Multi Agent / Memory / Learning 不自动进入)
