"""factory-console/tools/executor.py — 统一工具执行链 (U-2, v1.1.169)。

Founder 2026-08-26: 工具要和 CLI/WebUI 连接正确调用 — 统一执行链全覆盖。

调用链 (docs/tools-selection-rules.md 第三层):
  Registry(查定义) → Permission(权限) → Schema(参数校验) → Execute(执行函数)

- Registry: tools.registry (唯一事实源, 39 工具)
- Permission: 本地默认放行; 敏感工具 (git_push/删除类) 需 context.confirm
- Schema: 按工具 params 定义校验 (required/类型)
- Execute: fn 为 "module.func" 动态导入调用 (context 透传: root/project_id/service)
失败安全: 任何一步失败 → {ok:False, error}, 不伪造成功。
"""

from __future__ import annotations

import importlib
from typing import Any

from .registry import get_tool

#: 敏感工具: 执行需 context.confirm=True (防误操作)
SENSITIVE_TOOLS = {"git_ops", "deploy_auto", "rollback", "data_govern"}


def _resolve_fn(fn: str | None) -> Any | None:
    """"module.func" 动态解析 (失败 → None)。"""
    if not fn or "." not in fn:
        return None
    mod_name, _, func_name = fn.rpartition(".")
    candidates = [mod_name]
    if mod_name.startswith("tools."):
        candidates.insert(0, "factory_console." + mod_name)
    for cand in candidates:
        try:
            mod = importlib.import_module(cand)
            return getattr(mod, func_name, None)
        except Exception:  # noqa: BLE001 — 尝试下一个
            continue
    return None


def _check_schema(tool: dict[str, Any], params: dict[str, Any] | None) -> str | None:
    """参数校验 (required + 类型 str/int; 无 params 定义 → 放行)。"""
    p = params or {}
    spec = tool.get("params")
    if not isinstance(spec, dict):
        return None
    for key, rule in spec.items():
        if isinstance(rule, str):
            rule = {"type": rule}
        if rule.get("required") and key not in p:
            return f"缺少必填参数: {key}"
        if key in p and rule.get("type") == "int":
            try:
                int(p[key])
            except (TypeError, ValueError):
                return f"参数 {key} 应为整数"
    return None


def execute_tool(
    tool_id: str,
    params: dict[str, Any] | None = None,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """统一执行链: Registry → Permission → Schema → Execute。"""
    ctx = context or {}
    tool = get_tool(tool_id)
    if tool is None:
        return {"ok": False, "error": f"工具未注册: {tool_id} (registry 看清单)"}
    if tool["status"] != "implemented":
        return {"ok": False, "error": f"工具 {tool_id} 为规划中 (未实现)"}
    # Permission
    if tool_id in SENSITIVE_TOOLS and not ctx.get("confirm"):
        return {"ok": False, "error": f"敏感工具 {tool_id} 需确认 (context.confirm=True)"}
    # Schema
    schema_err = _check_schema(tool, params)
    if schema_err:
        return {"ok": False, "error": f"参数校验失败: {schema_err}"}
    # Execute (module.func)
    fn = _resolve_fn(tool.get("fn"))
    if fn is None:
        return {"ok": False, "error": f"工具 {tool_id} 未绑定执行函数 (fn)"}
    # 统一签名: fn(root, project_id, params) — context 提供 root/project_id
    try:
        result = fn(ctx.get("root"), ctx.get("project_id"), params or {})
    except TypeError as exc:
        return {"ok": False, "error": f"工具签名不匹配 (需 fn(root, project_id, params)): {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"执行失败: {exc}"}
    if isinstance(result, dict) and result.get("ok") is False:
        return result
    return {"ok": True, "tool": tool_id, "output": result}
