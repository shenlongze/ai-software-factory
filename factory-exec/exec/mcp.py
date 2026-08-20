"""factory-exec/exec/mcp.py — S10-020 Task 001 MCP Adapter Foundation。

设计依据 (S10-020-task001 用户约束 + S10-018 Tool Runtime + S10-019 Skill 侦察):
```
External MCP Server → MCP Client → MCPToolAdapter → Internal Tool → ToolRegistry
                                                                    → Skill → Agent
```
核心原则: **MCP 是 Tool Runtime 的外部扩展, 不是新的执行系统** — 所有 MCP
Tool 必须经过 ToolRegistry / Permission Check (Agent→Skill→Tool) / ToolExecutor
/ Runtime Event; 禁止 MCP 绕过内部治理。Agent 不知道 Tool 来源 (内部
filesystem.read 和 MCP github.issue.create 都是 Tool)。

**不实现** (任务约束): MCP Server / MCP Marketplace / 多 MCP 服务编排 /
自动发现所有互联网 MCP / Multi Agent / Memory / Learning Loop — 只实现
最小 MCP Client Adapter (Mock 连接, 不连公网)。

职责 (纯内部域模型 — 不绑具体 MCP SDK, Provider 风格):
- MCPConnection: id/name/server_url/transport/enabled/metadata — 描述外部
  MCP 服务连接 (transport 默认 "mock" — 本 Task 仅 Mock 可用; stdio/http
  真实协议 → MCPConnectionError 响亮拒绝, 不假装连接成功)。
- MCPClient (Protocol): connect()/disconnect()/list_tools()/call_tool() —
  接口契约不绑 SDK; MockMCPClient 是唯一实现 (echo tool, 不连公网)。
- MCPToolSchema: {name, description, input_schema} — MCP Tool 发现结果投影
  (JSON Schema 与内部 Tool.input_schema 同构, 经 adapter 无损转换)。
- MCPToolAdapter: MCP Tool Schema → 内部 Tool — id 保留 schema.name (Agent
  不知来源); source="mcp"; metadata {source, server, server_url, transport};
  handler 包装 client.call_tool; 首次调用延迟 connect → 发
  mcp_connected/mcp_tool_discovered 事件 (幂等 — 已连接不重复发); 事件
  经 event_callback (adapter 构造) 或 context["event_callback"] (执行循环
  透传) 发射; 无 → 静默 (失败安全)。
- MCPRegistry: 连接管理 + 注册编排 — register_connection (存连接 → client
  工厂 → connect → list_tools → adapter → ToolRegistry.register → 发
  mcp_tool_registered); list_connections/get_connection; 权限语义: MCP tool
  默认 permission_policy=allow_all (注册即授权声明 — 同系统 Skill 哲学:
  谁可用由 Skill 环 gate, Tool 环不重复限制), 可传白名单收窄; 冲突 →
  ToolConflictError 响亮。

依赖 (Removal Isolation): 只 import stdlib + pydantic + 本层 tool 模型
(exec.tool — Tool/ToolPermissionPolicy/ToolRegistry); 不触碰
agent_runtime.py / provider.py / execution_loop.py 主逻辑。
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import datetime
from typing import Any, Callable, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .models import utcnow
from .tool import Tool, ToolPermissionPolicy, ToolRegistry


def new_mcp_connection_id() -> str:
    """新 MCP 连接 id (mcp-<uuid4 前 8 hex>; 唯一 basename 语义)。"""
    return f"mcp-{uuid.uuid4().hex[:8]}"


class MCPError(Exception):
    """MCP 业务错误基类 (连接/调用/发现 — 响亮, 不静默)。"""


class MCPConnectionError(MCPError):
    """MCP 连接失败 (传输不支持/连接不可用 — 响亮拒绝, 不假装连接成功)。"""


class MCPToolNotFoundError(MCPError):
    """MCP Tool 不存在 (call_tool 未知 name — 响亮)。"""


class MCPToolError(MCPError):
    """MCP Tool 调用失败 (输入不完整/执行错误 — 响亮, 不吞)。"""


class MCPConnection(BaseModel):
    """MCP 连接模型 (描述外部 MCP 服务连接 — 不绑 SDK, 纯配置投影)。

    id: 唯一标识 (mcp-<hex8>); name: 人话名 (metadata.server 引用); server_url:
    服务地址 (本 Task 仅 mock:// 语义, 不解析不联网); transport: 传输方式
    (默认 "mock" — 本 Task 仅 Mock 可用; stdio/http 真实协议注册 → 响亮
    拒绝); enabled: 开关; metadata: 扩展元信息 (vendor 等); created_at:
    创建时间 (审计)。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    server_url: str
    transport: str = "mock"
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class MCPToolSchema(BaseModel):
    """MCP Tool 发现结果 (name/description/input_schema — JSON Schema 投影)。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class MCPClient(Protocol):
    """MCP Client 接口契约 (不绑具体 MCP SDK — Provider 风格, 可替换实现)。

    - connect(): 建立连接 (Mock: 仅置 connected=True, 不联网)。
    - disconnect(): 断开连接 (幂等)。
    - list_tools(): 发现 Tool → list[MCPToolSchema]。
    - call_tool(name, arguments) → Any: 调用 Tool (可 JSON 序列化输出)。
    - connected: 当前连接状态 (bool 属性)。
    """

    @property
    def connected(self) -> bool: ...

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def list_tools(self) -> list[MCPToolSchema]: ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


# ------------------------------------------------------------------ Stdio MCP Client (真连接, 增强层)


class StdioMCPClient:
    """真实 MCP stdio 客户端 (JSON-RPC 2.0 over 子进程 stdin/stdout)。

    实现 MCPClient 契约 (connect/list_tools/call_tool), 替换 Mock 的**增强层**
    实现 — 不绑定第三方 SDK, 手写最小 stdio 协议 (MCP 2024-11-05)。

    铁律 (愿景): 工具是增强层 — MCP 连接失败不阻塞 AI Factory 自身能力;
    调用方 (Agent 循环) 失败安全处理。

    - connect(): 拉起子进程 → initialize → notifications/initialized
    - list_tools(): tools/list → [MCPToolSchema]
    - call_tool(): tools/call → {content:[text...], isError}
    - 连接/协议错误 → MCPConnectionError/MCPToolError (响亮, 不假装成功)
    """

    #: MCP 协议版本 (2024-11-05 — 大部分 stdio server 兼容)
    PROTOCOL_VERSION = "2024-11-05"

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        *,
        name: str = "stdio",
    ) -> None:
        self._command = command
        self._args = list(args or [])
        self._env = dict(env or {})
        self._name = name
        self._proc: subprocess.Popen[str] | None = None
        self._request_id = 0
        self._connected = False

    # ------------------------------------------------------------ 连接

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        """建立连接 (幂等): 拉起子进程 + initialize + initialized 通知。"""
        if self._connected:
            return
        try:
            self._proc = subprocess.Popen(
                [self._command, *self._args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                env={**os.environ, **self._env},
            )
        except OSError as exc:
            raise MCPConnectionError(f"mcp stdio connect failed: {exc}") from exc
        try:
            self._request("initialize", {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "ai-factory", "version": "1.1.6"},
            })
            self._notify("notifications/initialized", {})
        except Exception:
            self.disconnect()
            raise
        self._connected = True

    def disconnect(self) -> None:
        """断开连接 (幂等 — 终止子进程)。"""
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:  # noqa: BLE001
                pass
            self._proc = None
        self._connected = False

    # ------------------------------------------------------------ JSON-RPC

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """发送请求并等待同 id 响应 (协议错误 → MCPConnectionError)。"""
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise MCPConnectionError("mcp client not connected")
        self._request_id += 1
        rid = self._request_id
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": rid, "method": method, "params": params},
            ensure_ascii=False,
        )
        try:
            self._proc.stdin.write(payload + "\n")
            self._proc.stdin.flush()
        except OSError as exc:
            raise MCPConnectionError(f"mcp write failed: {exc}") from exc
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise MCPConnectionError("mcp server closed stdout (stdin EOF)")
            try:
                msg = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(msg, dict) or msg.get("id") != rid:
                continue
            if "error" in msg:
                err = msg["error"]
                raise MCPToolError(
                    f"mcp {method} error: {err.get('message') or err}"
                )
            return msg.get("result") or {}

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        """发送通知 (无 id, 不等待响应)。"""
        if self._proc is None or self._proc.stdin is None:
            raise MCPConnectionError("mcp client not connected")
        self._proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "method": method, "params": params}
        ) + "\n")
        self._proc.stdin.flush()

    # ------------------------------------------------------------ MCPClient 契约

    def list_tools(self) -> list[MCPToolSchema]:
        """tools/list → MCPToolSchema 列表 (失败 → MCPConnectionError)。"""
        result = self._request("tools/list", {})
        tools: list[MCPToolSchema] = []
        for item in result.get("tools") or []:
            if not isinstance(item, dict):
                continue
            schema = item.get("inputSchema") or {}
            tools.append(MCPToolSchema(
                name=str(item.get("name") or ""),
                description=str(item.get("description") or ""),
                input_schema=schema if isinstance(schema, dict) else {},
            ))
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """tools/call → {content:[text...], isError} (JSON 可序列化)。"""
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        texts: list[str] = []
        for chunk in result.get("content") or []:
            if isinstance(chunk, dict) and chunk.get("type") == "text":
                texts.append(str(chunk.get("text") or ""))
        return {
            "content": texts,
            "isError": bool(result.get("isError")),
        }


# ------------------------------------------------------------------ Mock MCP Client (不连公网)


def build_mock_echo_tool_schema() -> MCPToolSchema:
    """Mock MCP 的 example Tool: echo ({message: "hello"} → {message: "hello"})
    — 不连公网, 验证完整链路 (发现→适配→注册→执行→事件)。"""
    return MCPToolSchema(
        name="echo",
        description="回显消息 (Mock MCP — 不连公网)",
        input_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    )


class MockMCPClient:
    """Mock MCP Client (example MCP Server 的客户端 — 纯内存, 不连公网)。

    实现 MCPClient 契约: connect/disconnect 仅切换 connected 状态 (无网络
    副作用); list_tools → [echo schema]; call_tool("echo", {message}) →
    {message: "hello"} 原样回显; 未知 tool → MCPToolNotFoundError; echo 缺
    message → MCPToolError (响亮 — 不假装成功)。
    """

    def __init__(self) -> None:
        self._connected = False
        self._tools = [build_mock_echo_tool_schema()]

    @property
    def connected(self) -> bool:
        """当前连接状态 (connect 后 True; disconnect 后 False)。"""
        return self._connected

    def connect(self) -> None:
        """建立连接 (幂等 — 二次连接不报错; Mock 无网络副作用)。"""
        self._connected = True

    def disconnect(self) -> None:
        """断开连接 (幂等 — 二次断开不报错)。"""
        self._connected = False

    def list_tools(self) -> list[MCPToolSchema]:
        """发现 Tool → [echo] (本 Mock Server 唯一能力)。"""
        return list(self._tools)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """调用 Tool: echo ({message} → {message}); 未知 tool / 缺 message →
        响亮错误 (不吞不伪装)。"""
        if name != "echo":
            raise MCPToolNotFoundError(f"mcp tool not found: {name!r}")
        message = arguments.get("message")
        if message is None:
            raise MCPToolError("echo tool requires 'message' argument")
        return {"message": message}


# ------------------------------------------------------------------ MCPToolAdapter (Schema → Internal Tool)


class MCPToolAdapter:
    """MCP Tool Schema → 内部 Tool (Tool Model/Registry/Executor 不变化)。

    转换规则:
    - id = schema.name 原样保留 (MCP 协议 tool name 即唯一标识 — Agent 调
      "echo"/"github.issue.create" 与调 "filesystem.read" 无差别)。
    - source = "mcp"; metadata = {source: "mcp", server: connection.name,
      server_url, transport} (Tool Metadata 扩展 — 来源可审计)。
    - handler 包装 client.call_tool: 首次调用延迟 connect (发
      mcp_connected + mcp_tool_discovered 事件 — 幂等), 然后 call_tool;
      MCP 异常原样上抛 → ToolExecutor 捕获转 ToolResult.failed (不吞)。
    - 事件发射: adapter 构造 event_callback 优先, context["event_callback"]
      兜底 (执行循环 context 透传路径); 均无 → 静默 (失败安全)。

    ensure_connected(): 显式连接 + 发现 (注册编排用 — 幂等)。
    """

    def __init__(
        self,
        client: MCPClient,
        connection: MCPConnection,
        *,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._client = client
        self._connection = connection
        self._event_callback = event_callback
        self._discovered: list[str] | None = None

    # ------------------------------------------------------------------ 事件

    def _emit(
        self, event_type: str, data: dict[str, Any], context: dict[str, Any] | None
    ) -> None:
        """发射事件 (构造 callback 优先 → context 注入兜底; 无 → 静默 —
        事件回调失败不阻断 Tool 执行)。"""
        callback = self._event_callback
        if callback is None and isinstance(context, dict):
            candidate = context.get("event_callback")
            if callable(candidate):
                callback = candidate  # type: ignore[assignment]
        if callback is None:
            return
        try:
            callback(event_type, data)
        except Exception:  # noqa: BLE001 — 事件回调失败不阻断执行
            pass

    # ------------------------------------------------------------------ 连接/发现

    def ensure_connected(self, *, context: dict[str, Any] | None = None) -> None:
        """延迟连接 + 发现 (幂等): 首次 → connect + mcp_connected 事件 +
        list_tools + mcp_tool_discovered 事件; 已连接 → 零事件零副作用。"""
        if self._client.connected:
            return
        self._client.connect()
        self._emit(
            "mcp_connected",
            {
                "connection_id": self._connection.id,
                "server": self._connection.name,
                "transport": self._connection.transport,
            },
            context,
        )
        tools = self._client.list_tools()
        self._discovered = [t.name for t in tools]
        self._emit(
            "mcp_tool_discovered",
            {
                "connection_id": self._connection.id,
                "server": self._connection.name,
                "tools": list(self._discovered),
            },
            context,
        )

    # ------------------------------------------------------------------ 转换

    def to_internal_tool(self, schema: MCPToolSchema) -> Tool:
        """MCP Tool Schema → 内部 Tool (id 保留 name; source='mcp'; handler
        包装 call_tool — 执行权仍在 ToolExecutor, 无绕过)。"""
        client = self._client
        connection = self._connection
        tool_name = schema.name

        def handler(tool_input: dict[str, Any], context: dict[str, Any]) -> Any:
            self.ensure_connected(context=context)
            return client.call_tool(tool_name, tool_input)

        return Tool(
            id=tool_name,
            name=tool_name,
            description=schema.description or "",
            input_schema=dict(schema.input_schema or {}),
            output_schema={},
            handler=handler,
            # 权限: 注册编排方经 register_connection 设置 (默认 allow_all —
            # 注册即授权声明; 收窄时由本字段覆盖)
            permission_policy=ToolPermissionPolicy(allow_all=True),
            enabled=True,
            source="mcp",
            metadata={
                "source": "mcp",
                "server": connection.name,
                "server_url": connection.server_url,
                "transport": connection.transport,
            },
        )


# ------------------------------------------------------------------ MCPRegistry (连接 + 注册编排)


class MCPRegistry:
    """MCP 连接注册表 + 注册编排 (Client → 发现 → Adapter → ToolRegistry)。

    - register_connection(connection, *, permission_policy=None): 存连接 →
      client 工厂 (mock → MockMCPClient; stdio/http 真实协议 →
      MCPConnectionError 响亮拒绝 — 本 Task 禁止连公网) → connect →
      list_tools → adapter → ToolRegistry.register (每 tool 发
      mcp_tool_registered 事件; id 冲突 → ToolConflictError 响亮) → 返回
      (tools 摘要, client)。
    - 权限语义: MCP tool 默认 permission_policy=allow_all (注册即授权声明
      — 同系统 Skill 哲学: 谁可用由 Skill 环 [Agent→Skill→Tool] gate, Tool
      环不重复限制); 传白名单 → 收窄 (Tool 最终边界仍生效, 无绕过)。
    - list_connections / get_connection: 连接查询 (API 数据源)。
    - event_callback: 注册过程事件 (mcp_tool_registered) 发射目标; 无 →
      静默 (失败安全 — API 直调路径无 session)。
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        *,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._event_callback = event_callback
        self._connections: dict[str, MCPConnection] = {}

    @property
    def tool_registry(self) -> ToolRegistry | None:
        """关联 ToolRegistry (注册目标 — None → 仅管理连接, 不注册 Tool)。"""
        return self._tool_registry

    # ------------------------------------------------------------------ 连接 CRUD

    def register_connection(
        self,
        connection: MCPConnection,
        *,
        permission_policy: ToolPermissionPolicy | None = None,
    ) -> tuple[list[dict[str, Any]], MCPClient]:
        """注册 MCP 连接: 存连接 → client → connect → 发现 → adapter →
        ToolRegistry.register (完整编排, 发 mcp_tool_registered 事件)。

        返回 (tools 摘要 [{id, name, server}], client) — 调用方可复用 client
        执行/查询。stdio/http 真实协议 → MCPConnectionError (不连公网);
        tool id 冲突 → ToolConflictError (响亮, 不静默覆盖)。
        """
        self._connections[connection.id] = connection
        client = self.client_for(connection)
        client.connect()
        # S10-020: 注册即连接 — mcp_connected (连接已建立, 可审计)
        self._emit(
            "mcp_connected",
            {
                "connection_id": connection.id,
                "server": connection.name,
            },
        )
        adapter = MCPToolAdapter(
            client, connection, event_callback=self._event_callback
        )
        tools: list[dict[str, Any]] = []
        for schema in client.list_tools():
            tool = adapter.to_internal_tool(schema)
            # mcp_tool_discovered (每 tool 一次, 发现边界可审计)
            self._emit(
                "mcp_tool_discovered",
                {
                    "connection_id": connection.id,
                    "server": connection.name,
                    "tool": tool.id,
                },
            )
            if permission_policy is not None:
                tool = tool.model_copy(update={"permission_policy": permission_policy})
            if self._tool_registry is not None:
                self._tool_registry.register(tool)
            tools.append(
                {
                    "id": tool.id,
                    "name": tool.name,
                    "server": connection.name,
                }
            )
            self._emit(
                "mcp_tool_registered",
                {
                    "connection_id": connection.id,
                    "server": connection.name,
                    "tool": tool.id,
                },
            )
        return tools, client

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """注册过程事件 (mcp_tool_registered; 无 callback → 静默 — 失败安全)。"""
        if self._event_callback is None:
            return
        try:
            self._event_callback(event_type, data)
        except Exception:  # noqa: BLE001 — 事件回调失败不阻断注册
            pass

    @staticmethod
    def client_for(connection: MCPConnection) -> MCPClient:
        """MCP Client 工厂 (不绑 SDK): mock → MockMCPClient; stdio/http 真实
        协议 → MCPConnectionError 响亮拒绝 (本 Task 禁止连公网, 不假装可用)。"""
        transport = str(connection.transport or "").strip().lower()
        if transport == "mock":
            return MockMCPClient()
        raise MCPConnectionError(
            f"unsupported MCP transport: {connection.transport!r} "
            f"(connection {connection.id!r}; only 'mock' is available — "
            "real MCP protocols are not supported in this task)"
        )

    def get_connection(self, connection_id: str) -> MCPConnection | None:
        """按 id 取连接 (不存在 → None — 查询语义)。"""
        return self._connections.get(connection_id)

    def list_connections(self) -> list[MCPConnection]:
        """全部连接 (按 id 排序 — 审计友好)。"""
        return [self._connections[cid] for cid in sorted(self._connections)]


__all__ = [
    "MCPClient",
    "MCPConnection",
    "MCPConnectionError",
    "MCPError",
    "MCPRegistry",
    "MCPToolAdapter",
    "MCPToolError",
    "MCPToolNotFoundError",
    "MCPToolSchema",
    "MockMCPClient",
    "build_mock_echo_tool_schema",
    "new_mcp_connection_id",
]
