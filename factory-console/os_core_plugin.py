"""factory-console/os_core_plugin.py — OS Core Boundary: Plugin (MU-CORE-13).

Plugin = 提供某种可治理能力实现的可注册扩展单元 (Extension Layer)。

Capability ≠ Plugin；Plugin 不拥有 Execution/TaskNode/Scheduler/Verification/Evidence/Outcome。
本模块是 **OS Boundary/Adapter**, 复用现有 `plugin_kernel` (不建第二 registry):
    - register_capability_plugin: 注册 plugin, capability_refs 校验到 Capability SSOT (CAP-*),
      implementation_ref 形如 "provider:claude"/"provider:codex" (Extension 实现引用);
    - resolve_capability_plugin: 确定性解析 (capability match + ENABLED + scope/company + 稳定排序);
    - get_plugin_contract / set_plugin_lifecycle: 归一化视图与生命周期。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

SCOPES: tuple[str, ...] = ("global", "company")
CONTRACT_KEYS = ("implementation_ref", "scope", "company_id", "provider")

_IMPLEMENTATION_DEFAULT = "provider:local"


def _kernel() -> Any:
    from . import plugin_kernel

    return plugin_kernel


def _contract(rec: dict[str, Any]) -> dict[str, Any]:
    cfg = rec.get("configuration_schema") or {}
    if not isinstance(cfg, dict):
        cfg = {}
    impl = str(cfg.get("implementation_ref") or _IMPLEMENTATION_DEFAULT)
    provider = str(cfg.get("provider") or (impl.split(":", 1)[1] if ":" in impl else ""))
    return {"plugin_id": rec["plugin_id"], "name": rec.get("name", ""),
            "version": rec.get("version", ""), "type": rec.get("type", ""),
            "status": rec.get("status", ""), "capability_refs": list(rec.get("capabilities") or []),
            "implementation_ref": impl, "provider": provider,
            "scope": str(cfg.get("scope") or "global"),
            "company_id": str(cfg.get("company_id") or ""),
            "permissions": list(rec.get("permissions") or [])}


# ---------------------------------------------------------------- registration / lifecycle

def register_capability_plugin(root: str | Path, *, plugin_id: str, name: str,
                               capability_refs: list[str], implementation_ref: str,
                               scope: str = "global", company_id: str = "",
                               version: str = "1.0", type: str = "provider",
                               description: str = "", permissions: list[str] | None = None,
                               status: str = "active") -> dict[str, Any]:
    """注册 plugin 并把 OS Capability (CAP-*) 绑定到 Extension 实现。

    - capability_refs 逐条校验到 Capability SSOT (active);
    - scope=company 时 company 必须存在 (MU-CORE-01 边界);
    - 通过 plugin_kernel.register_plugin 落盘 (不复制 registry);
    - status="active" → ENABLED。
    """
    from .os_core_capability import validate_capability_ref
    from .os_core_company_organization import get_company

    if scope not in SCOPES:
        raise ValueError(f"未知 scope: {scope} (可选: {SCOPES})")
    if scope == "company":
        if not company_id:
            raise ValueError("scope=company 必须提供 company_id")
        if get_company(root, company_id) is None:
            raise ValueError(f"Company 不存在: {company_id}")
    elif company_id:
        raise ValueError("scope=global 不接受 company_id")
    impl = str(implementation_ref or "")
    if not impl.startswith(("provider:", "executor:", "tool:")):
        raise ValueError(f"implementation_ref 需以 provider:/executor:/tool: 开头: {impl!r}")
    caps = [validate_capability_ref(root, c) for c in capability_refs]
    kernel = _kernel()
    rec = kernel.register_plugin(root, plugin_id=plugin_id, name=name, version=version,
                                 type=type, vendor="os-core", description=description,
                                 capabilities=caps,
                                 permissions=list(permissions or []),
                                 configuration_schema={"implementation_ref": impl,
                                                       "scope": scope,
                                                       "company_id": str(company_id or ""),
                                                       "provider": impl.split(":", 1)[1]})
    if status == "active":
        rec = kernel.plugin_status(root, plugin_id, target="ENABLED", actor="os-core")
    return _contract(rec)


def get_plugin_contract(root: str | Path, plugin_id: str) -> dict[str, Any] | None:
    rec = _kernel().get_plugin(root, plugin_id)
    return _contract(rec) if rec else None


def list_capability_plugins(root: str | Path) -> list[dict[str, Any]]:
    return [_contract(r) for r in _kernel().list_plugins(root)]


def set_plugin_lifecycle(root: str | Path, plugin_id: str, target: str) -> dict[str, Any]:
    """生命周期: REGISTERED→ENABLED→DISABLED→RETIRED (复用 plugin_kernel 状态机)。"""
    rec = _kernel().plugin_status(root, plugin_id, target=str(target).upper(), actor="os-core")
    return _contract(rec)


# ---------------------------------------------------------------- resolution (deterministic)

def resolve_capability_plugin(root: str | Path, capability_ref: str, *,
                              company_id: str = "") -> dict[str, Any]:
    """Capability → Plugin 确定性解析 (不执行)。

    规则: canonical CAP-* → ENABLED → capability 命中 → scope/company 合法 → 按 plugin_id 稳定排序取首个。
    """
    from .os_core_capability import validate_capability_ref

    try:
        cap_id = validate_capability_ref(root, capability_ref)
    except ValueError as exc:
        return {"resolved": False, "reason": f"capability 不可解析: {exc}", "plugin_id": ""}
    candidates: list[dict[str, Any]] = []
    for contract in list_capability_plugins(root):
        if contract["status"] != "ENABLED":
            continue
        if cap_id not in contract["capability_refs"]:
            continue
        if contract["scope"] == "company":
            if not company_id or contract["company_id"] != str(company_id):
                continue
        candidates.append(contract)
    candidates.sort(key=lambda c: c["plugin_id"])
    if not candidates:
        return {"resolved": False, "plugin_id": "", "capability_id": cap_id,
                "reason": f"无 ENABLED plugin 提供 {cap_id}" + (f" @ company {company_id}" if company_id else "")}
    chosen = candidates[0]
    return {"resolved": True, "plugin_id": chosen["plugin_id"],
            "capability_id": cap_id, "implementation_ref": chosen["implementation_ref"],
            "provider": chosen["provider"], "scope": chosen["scope"],
            "reason": (f"capability {cap_id} matched; plugin {chosen['plugin_id']} ENABLED; "
                       f"scope {chosen['scope']}"
                       + (f" company {company_id}" if company_id else "")),
            "candidate_count": len(candidates)}


__all__ = ["CONTRACT_KEYS", "SCOPES", "get_plugin_contract", "list_capability_plugins",
           "register_capability_plugin", "resolve_capability_plugin", "set_plugin_lifecycle"]
