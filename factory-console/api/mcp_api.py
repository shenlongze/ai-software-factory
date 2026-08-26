"""factory-console/api/mcp_api.py — S10-020 Task 001 MCP API 路由函数。

AI Employee 工具能力外部扩展 (MCP Adapter Foundation): MCP 连接清单 +
注册 + MCP Tool 清单 — GET /api/mcp/connections (MCPRegistry 当前连接)
+ POST /api/mcp/connections (注册即连接: Mock 不连公网, Tool 注册进内部
ToolRegistry, 执行权仍在 ToolExecutor 最小权限表) + GET /api/mcp/tools
(内部 ToolRegistry source=mcp 过滤)。Domain (exec.mcp 已 GREEN:
MCPConnection/MockMCPClient/MCPToolAdapter/MCPRegistry); Service 层
(ConsoleService.mcp_connections/create_mcp_connection/mcp_tools) 做失败
安全装配 + 输入校验 + 错误语义归一 (空 name/server_url / stdio/http 真实
协议 → ValueError → 400; store/exec 未装配 → None → 404); 本模块只做路由
函数 (无 Web 依赖, FastAPI 薄层做 HTTP 绑定 — 同 api/tool_api.py 模式)。

路由函数 (HTTP 端点由 fastapi_adapter 绑定):
- list_mcp_connections: GET /api/mcp/connections — {connections: [...]}
- create_mcp_connection: POST /api/mcp/connections — 连接摘要 + tools
- list_mcp_tools: GET /api/mcp/tools — {tools: [...]}

错误语义 (Service 层抛出, HTTP 层映射):
- ValueError → 400 (空 name/server_url; stdio/http 真实协议响亮拒绝)
- None → 404 (store/exec 未装配 — 失败安全)

审计: 端点命中 → console.viewed (view=mcp_connections / mcp_connection_create
/ mcp_tools) — ADR-0002 读审计同语义; logger=None 静默 (失败安全)。
"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed

__all__ = ["create_mcp_connection", "list_mcp_connections", "list_mcp_tools", "remove_mcp_connection"]


def list_mcp_connections(service: Any, *, logger: Any = None) -> dict[str, Any]:
    """GET /api/mcp/connections — MCP 连接清单 (MCPRegistry 当前连接)。

    → {connections: [{id, name, server_url, transport, enabled, created_at}]}
    (id 排序); 未装配 → {connections: []} (失败安全 — GET 永不失败)。
    审计: console.viewed (view=mcp_connections)。
    """
    record_console_viewed(logger, view="mcp_connections", count=1)
    return {"connections": service.mcp_connections()}


def create_mcp_connection(
    service: Any,
    name: str,
    server_url: str,
    *,
    transport: str = "mock",
    logger: Any = None,
) -> dict[str, Any] | None:
    """POST /api/mcp/connections — 创建 MCP 连接 (注册即连接 + Tool 注册)。

    {name, server_url, transport?} → {id, name, server_url, transport,
    enabled, created_at, tools: [{id, name, server}]}:
    - 空 name/server_url → ValueError (HTTP 400 — 连接标识/地址必填)
    - stdio/http 真实协议 → ValueError (HTTP 400 — MCPConnectionError 归一,
      本 Task 仅 mock 可用, 响亮拒绝不假装连接成功)
    - store/exec 未装配 → None (HTTP 404 — 失败安全)
    审计: console.viewed (view=mcp_connection_create)。
    """
    record_console_viewed(logger, view="mcp_connection_create", count=1)
    return service.create_mcp_connection(name, server_url, transport=transport)


def list_mcp_tools(service: Any, *, logger: Any = None) -> dict[str, Any]:
    """GET /api/mcp/tools — MCP Tool 清单 (内部 ToolRegistry source=mcp 过滤)。

    → {tools: [{id, name, description, server}]} (id 排序; 内部 Tool 不
    混入 MCP 视图); 未装配 → {tools: []} (失败安全 — GET 永不失败)。
    审计: console.viewed (view=mcp_tools)。
    """
    record_console_viewed(logger, view="mcp_tools", count=1)
    return {"tools": service.mcp_tools()}


def remove_mcp_connection(
    service: Any,
    connection_id: str,
    *,
    logger: Any = None,
) -> bool:
    """DELETE /api/mcp/connections/{id} — 移除 MCP 连接 (S10-116 A-3 Web 化)。

    复用 ConsoleService.remove_mcp_connection (直接操作 MCPRegistry 连接存储,
    与 CLI `factory mcp remove` 同源)。连接不存在 / registry 未装配 → False
    (HTTP 层 404 — 幂等失败安全)。审计: console.viewed (view=mcp_connection_remove)。
    """
    record_console_viewed(logger, view="mcp_connection_remove", count=1)
    return service.remove_mcp_connection(connection_id)
