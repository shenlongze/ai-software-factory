"""factory-console/api/tool_api.py — S10-018 Task 001 Tool API 路由函数。

AI Employee Tool Runtime Foundation: Tool 清单 + 执行入口 — GET /api/tools
(ToolRegistry 当前可用 Tool) + POST /api/tools/{tool_id}/execute (直调
ToolExecutor: Lookup→Permission→Schema→Execute)。Domain (exec.tool 已
GREEN: Tool/ToolRegistry/ToolExecutor + 沙箱 filesystem.read); Service 层
(ConsoleService.list_tools/execute_tool) 做失败安全装配 + 输入校验 + 结果
语义归一 (tool not found → 404 / permission denied → 403 / 其余 → 400);
本模块只做路由函数 (无 Web 依赖, FastAPI 薄层做 HTTP 绑定 — 同
api/agent_executor.py 模式)。

路由函数 (HTTP 端点由 fastapi_adapter 绑定):
- list_tools: GET /api/tools — {tools: [{id, name, description, enabled}]}
- execute_tool: POST /api/tools/{tool_id}/execute — {success, output?, error?}

错误语义 (Service 层抛出, HTTP 层映射):
- ValueError → 400 (空 tool_id/agent_id; schema 非法 / disabled / handler 错误)
- ToolExecuteNotFoundError → 404 (Tool 不存在)
- ToolExecutePermissionError → 403 (最小权限表拒绝)
- None → 404 (store/exec 未装配 — 失败安全)

审计: 端点命中 → console.viewed (view=tools/tool_execute) — ADR-0002 读审计
同语义; logger=None 静默 (失败安全)。
"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed

__all__ = ["execute_tool", "list_tools"]


def list_tools(service: Any, *, logger: Any = None) -> dict[str, Any]:
    """GET /api/tools — Tool 清单 (ToolRegistry 当前可用 Tool)。

    → {tools: [{id, name, description, enabled}]} (id 排序); 未装配 → []
    (失败安全 — GET 永不失败)。审计: console.viewed (view=tools)。
    """
    record_console_viewed(logger, view="tools", count=1)
    return {"tools": service.list_tools()}


def execute_tool(
    service: Any,
    tool_id: str,
    agent_id: str,
    tool_input: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
    logger: Any = None,
) -> dict[str, Any] | None:
    """POST /api/tools/{tool_id}/execute — 执行 Tool (直调 ToolExecutor)。

    {agent_id, input, context?} → {success, output?, error?}:
    - 成功 → {success: true, output} (ToolResult 输出原样透传)
    - 空 tool_id/agent_id → ValueError (HTTP 400 — 工具标识/执行者必填)
    - Tool 不存在 → ToolExecuteNotFoundError (HTTP 404)
    - 权限拒绝 → ToolExecutePermissionError (HTTP 403 — 最小权限表)
    - 其余执行失败 → ValueError (HTTP 400 — schema/disabled/handler)
    - store/exec 未装配 → None (HTTP 404 — 失败安全)
    审计: console.viewed (view=tool_execute)。
    """
    record_console_viewed(logger, view="tool_execute", count=1)
    return service.execute_tool(tool_id, agent_id, tool_input, context=context)
