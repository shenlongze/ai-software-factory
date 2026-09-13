"""factory-console/session/mcp_tools.py — MCP 工具接入会话工具面 (S10-127 P2.3).

把 MCP server 的工具暴露为 OpenAI 形状 schema (mcp__<server>__<tool>):
- mcp_tool_schemas(data_dir): 全部 MCP 工具 schema (懒启动 server, 失败跳过)
- dispatch_mcp(tool_id, args, data_dir): 解析 mcp__server__tool → call_tool
失败安全: server 启动/调用失败 → 工具不可用返回诚实错误, 不拖垮会话。
"""
from __future__ import annotations

from typing import Any


def mcp_tool_schemas(data_dir: str | None) -> list[dict[str, Any]]:
    """MCP 工具 → OpenAI 形状 schema (名称 mcp__<server>__<tool>)。"""
    out: list[dict[str, Any]] = []
    if not data_dir:
        return out
    try:
        from .mcp_client import load_mcp_servers

        for name, client in load_mcp_servers(data_dir).items():
            try:
                for t in client.list_tools():
                    tname = str(t.get("name") or "")
                    if not tname:
                        continue
                    full = f"mcp__{name}__{tname}"
                    out.append({
                        "type": "function",
                        "function": {
                            "name": full,
                            "description": f"[MCP:{name}] {t.get('description') or tname}",
                            "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
                        },
                    })
            except Exception:  # noqa: BLE001 — 单个 server 失败 → 跳过
                continue
    except Exception:  # noqa: BLE001 — MCP 整体不可用 → 空
        pass
    return out


def dispatch_mcp(tool_id: str, args: dict[str, Any], data_dir: str | None) -> dict[str, Any]:
    """调用 MCP 工具 (mcp__<server>__<tool> → server.call_tool)。"""
    parts = str(tool_id or "").split("__")
    if len(parts) < 3 or parts[0] != "mcp":
        return {"ok": False, "error": f"非法 MCP 工具名: {tool_id}"}
    server_name, tool_name = parts[1], "__".join(parts[2:])
    try:
        from .mcp_client import load_mcp_servers

        clients = load_mcp_servers(data_dir)
        client = clients.get(server_name)
        if client is None:
            return {"ok": False, "error": f"MCP server 未配置: {server_name}"}
        r = client.call_tool(tool_name, args or {})
        return r
    except Exception as exc:  # noqa: BLE001 — 失败诚实返回
        return {"ok": False, "error": f"MCP 调用失败: {exc}"}
