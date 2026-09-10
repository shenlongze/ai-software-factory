"""factory-console/api/flow.py — Flow Views 纯函数 API 路由 (S1 第 9 刀)。

仿 api/audit.py 风格: 无 Web 依赖纯函数, 未来 FastAPI 薄层做 HTTP 绑定。
与 CLI/shell 同一 build_flow_for (同源, 渲染结果一致 — 验收 K)。

- flow_route: GET  /api/flow/{scope}/{id}?format=md|todo|mermaid:<kind>|
              echarts:<kind>|html  (kind 单独参数, 兼容手术单签名)
  → {ok, format, content, view, scope, id}
- 失败安全铁律: 异常 → {"ok": False, "error": str} — 绝不裸抛。

设计: /Users/agentdev/ai-company-os-planning/s1-cut9-flow-views-final.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..flow_views import ALL_FORMATS, build_flow_for

__all__ = [
    "ALL_FORMATS",
    "flow_route",
]


def _default_root() -> str:
    try:
        from factory_console.config import ConfigProvider
        return str(ConfigProvider().get_data_dir())
    except Exception:  # noqa: BLE001
        return str(Path.home() / ".factory")


def flow_route(scope: str, flow_id: str, format: str = "md",  # noqa: A002
               kind: str = "", root: str | Path | None = None,
               ) -> dict[str, Any]:
    """GET /api/flow/{scope}/{id} — 渲染 flow 视图。

    {scope: conversation|project, id, format?, kind?, root?} → {ok, format,
    content, view, scope, id, error}。kind 是 mermaid:/echarts: 前缀短写:
    flow_route(scope, id, "gantt", kind="mermaid") == format="mermaid:gantt"。
    """
    try:
        fmt = format
        if kind and not fmt.startswith(f"{kind}:"):
            fmt = f"{kind}:{fmt}" if ":" not in fmt else fmt
        if fmt not in ALL_FORMATS:
            return {"ok": False, "error": f"未知 format: {fmt} "
                    f"(可用: {', '.join(ALL_FORMATS)})",
                    "format": fmt, "content": "", "view": {},
                    "scope": scope, "id": flow_id}
        base = str(root) if root is not None else _default_root()
        return build_flow_for(base, scope, flow_id, fmt)
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return {"ok": False, "error": str(exc), "format": format,
                "content": "", "view": {}, "scope": scope, "id": flow_id}


#: 失败安全: 异常不裸抛 (与 api/*.py 语义一致)。
