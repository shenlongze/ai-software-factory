# S10-020 Task 001 Completion Report — MCP Adapter Foundation

> 日期: 2026-08-13 | 状态: 完成 (待人工审核) | Sprint: S10-020 MCP Adapter
> 定位: 让 AI Software Factory 支持外部 MCP Tool 接入 — MCP 是 Tool Runtime 的外部扩展, 不是新的执行系统

---

## 1. MCP Adapter 架构

```
External MCP Server → MCP Adapter → Internal Tool Model → Tool Registry → Skill → Agent
所有 MCP Tool 必须经过: Tool Registry / Permission Check / ToolExecutor / Runtime Event
禁止: MCP 绕过内部治理

新增 factory-exec/exec/mcp.py:
  MCPConnection (id/name/server_url/transport/enabled/metadata)
  MCPClient Protocol (connect/disconnect/list_tools/call_tool — 不绑 SDK)
  MockMCPClient (echo 往返, 不连公网)
  MCPToolSchema / MCPToolAdapter (Schema → Internal Tool, source="mcp", handler 包装 call_tool)
  MCPRegistry (register_connection: 存连接 → client → connect → 发现 → adapter →
               ToolRegistry.register; 注册即连接发 mcp_connected→mcp_tool_discovered→
               mcp_tool_registered; stdio/http → MCPConnectionError 响亮拒绝)
```

## 2. MCP 与 Tool Runtime 关系

```
MCP Tool 转换后 = 内部 Tool (Agent 不知道来源):
  内部 filesystem.read 和 MCP echo 都是 Tool
扩展 tool.py: Tool.source (internal|mcp) + Tool.metadata {server} — 兼容
ToolExecutor ctx 透传 event_callback (MCP adapter 事件 → session 记录)
```

## 3. 数据模型

```
MCPConnection: id/name/server_url/transport/enabled/metadata
MCPToolAdapter: MCP Tool Schema → Internal Tool (id 保留 name, source="mcp",
                handler 包装 call_tool — 执行权仍在 ToolExecutor, 无绕过)
```

## 4. API

```
GET  /api/mcp/connections     → {connections: [...]} (内部 store)
POST /api/mcp/connections     → 创建 (body: name/server_url/transport) → {id, tools}
GET  /api/mcp/tools           → {tools: [...]} (内部 ToolRegistry source=mcp 过滤)
错误映射: 400 (transport 不支持/空字段) / 404 (未装配)
```

## 5. Permission

```
MCP Tool 遵守现有权限链 (Agent→Skill→Tool→Permission):
  注册即授权声明 (默认 allow_all) — Skill 环是 MCP tool 的实际 gate
  测试证明: Skill 不含 echo → 拒绝; 含 → tool 白名单收窄仍生效 (环3 无绕过)
禁止: MCP Tool 自带权限绕过
```

## 6. 测试结果

```
Backend pytest:  7775 passed (0 failed) — 含新增:
  tests/exec/test_exec_mcp.py              (30: Model/Client/Adapter/注册/权限链/Mock echo/ToolExecutor/11 事件链)
  tests/exec/test_exec_runtime_session.py  (51: 事件 20→23)
  tests/console/test_console_mcp_api.py    (18: API 端到端/创建/查询/400/404)
  tests/console/test_console_api.py        (42: 导出 3 新增)
  tests/console/test_console_web_adapter.py (29: 权限边界 +mcp 写面)
Frontend vitest: 669 passed (56 files) — 含 MCPConnection/MCPTool 类型 + mcp_* 人话映射
tsc: 0 error | build: ✓
```

## 7. curl 真实证据 (8011)

```
1. POST /api/mcp/connections {name: demo-mcp, server_url: mock://demo, transport: mock}
   → {id: mcp-121d1c6d, tools: [{id: echo, name: echo, server: demo-mcp}]}
     (创建连接 + echo 自动注册)

2. GET /api/mcp/connections
   → 1 连接: mcp-121d1c6d: demo-mcp (mock://demo)

3. GET /api/mcp/tools
   → echo: server=demo-mcp (MCP 工具进内部 Registry)

4. Agent 调 MCP echo tool:
   POST /api/tools/echo/execute {agent_id: backend-1, input: {message: hello}}
   → success=True, output: {message: "hello"} (Agent→Skill→MCP Tool→ToolExecutor→Result)
```

## 8. 后续 Multi Agent 规划

```
MCP Tool 已进内部 ToolRegistry — Multi Agent 场景各 Agent 经 Skill 门共享 MCP 工具;
SkillContext.available_tools 可展示 MCP 能力; 权限链对多 Agent 同一 Tool 不同授权;
未来: 真实 MCP Server 接入 (stdio/http 适配器 — 当前 Mock 验证链路)。
```

## Commit

```
c61fccf  feat(S10-020): implement mcp adapter foundation
```

---

> 状态: 完成 | 下一步: 等待人工审核 (Multi Agent / Memory / Learning 不自动进入)
