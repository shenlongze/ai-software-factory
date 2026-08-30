"""factory-console/plugin_kernel.py — S31 Everything-is-a-Plugin Foundation.

统一 Plugin Kernel:
- PluginRecord: plugin_id/name/version/type/vendor/capabilities/dependencies/permissions/status/health
- PluginRegistry: register/unregister/get/list/exists/enable/disable/health (SSOT)
- PluginResolver: deterministic (capability → eligible → permission → policy; 非 LLM)
- PluginLifecycle: DISCOVERED→REGISTERED→ENABLED→DISABLED→RETIRED (audit + append-only)
- 真实 Provider Plugin: 把 llm provider 适配成 Production Plugin (deepseek/ollama/anthropic)
- 反硬编码: Core 不修改即可注册第二个 provider 实现

原则:
- Core = Kernel, Plugin = Capability
- Plugin 不得通过自身执行路径修改权限/治理/Core Contract
- 复用 S17 governance 的 permission 边界
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

#: Plugin types
PLUGIN_TYPES = ("agent", "skill", "tool", "mcp", "provider", "model",
                "runtime", "executor", "workflow", "artifact_type", "domain",
                "memory", "retriever", "reranker", "compressor", "evaluator",
                "experimenter", "observer", "repairer", "strategy", "learning",
                "repair", "optimization")

#: Lifecycle
PL_STATES = ("DISCOVERED", "REGISTERED", "ENABLED", "DISABLED", "RETIRED")
PL_TRANSITIONS = {
    "DISCOVERED": ("REGISTERED", "RETIRED"),
    "REGISTERED": ("ENABLED", "DISABLED", "RETIRED"),
    "ENABLED": ("DISABLED", "RETIRED"),
    "DISABLED": ("ENABLED", "RETIRED"),
    "RETIRED": (),
}

#: 内置 Provider Plugins (真实能力, 与用户新增同构)
BUILTIN_PROVIDER_PLUGINS: dict[str, dict[str, Any]] = {
    "provider.deepseek": {
        "plugin_id": "provider.deepseek", "name": "DeepSeek Provider", "version": "1.0.0",
        "type": "provider", "vendor": "deepseek",
        "description": "DeepSeek LLM provider (OpenAI-compatible)",
        "capabilities": ["llm.complete", "llm.embedding"], "dependencies": [],
        "permissions": ["use_llm"], "configuration_schema": {"base_url": "str", "api_key_env": "str"},
    },
    "provider.ollama": {
        "plugin_id": "provider.ollama", "name": "Ollama Provider", "version": "1.0.0",
        "type": "provider", "vendor": "ollama",
        "description": "Local Ollama LLM provider",
        "capabilities": ["llm.complete"], "dependencies": [],
        "permissions": ["use_llm"], "configuration_schema": {"base_url": "str"},
    },
    "provider.anthropic": {
        "plugin_id": "provider.anthropic", "name": "Anthropic Provider", "version": "1.0.0",
        "type": "provider", "vendor": "anthropic",
        "description": "Anthropic Claude provider",
        "capabilities": ["llm.complete"], "dependencies": [],
        "permissions": ["use_llm"], "configuration_schema": {"api_key_env": "str"},
    },
    "executor.codex": {
        "plugin_id": "executor.codex", "name": "Codex Executor", "version": "1.0.0",
        "type": "executor", "vendor": "openai",
        "description": "Codex CLI external executor (S4 适配)",
        "capabilities": ["execute.code"], "dependencies": [],
        "permissions": ["execute_code"], "configuration_schema": {"binary": "str"},
    },
}

#: 真实 provider 执行器 (适配 llm_gateway, 不硬编码于 Core)
PROVIDER_EXECUTORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "plugins" / f"{name}.json"


def _load(root: Path | str, name: str) -> list[dict[str, Any]]:
    try:
        d = json.loads(_file(root, name).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(root: Path | str, name: str, data: list[dict[str, Any]]) -> None:
    p = _file(root, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _audit(root: Path | str, event_type: str, payload: dict[str, Any]) -> None:
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            event_type,
            trace_id=payload.get("plugin_id") or "",
            actor_type="system", actor_id="plugin_kernel",
            action=f"plugin.{event_type.lower()}",
            source="plugin_kernel", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"plugin": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


def _next_state(current: str, target: str) -> str:
    if target not in PL_STATES:
        raise ValueError(f"未知状态: {target}")
    if target == current:
        return target
    if target not in PL_TRANSITIONS.get(current, ()):
        raise ValueError(f"非法状态迁移: {current} → {target}")
    return target


# ------------------------------------------------------------------ Registry

def bootstrap(root: Path | str) -> None:
    """内置 Plugins 注册 (DISCOVERED → REGISTERED, 不自动 ENABLE 除默认)。"""
    data = _load(root, "plugins")
    existing = {p["plugin_id"] for p in data}
    for pid, spec in BUILTIN_PROVIDER_PLUGINS.items():
        if pid not in existing:
            rec = {"plugin_id": pid, "name": spec["name"], "version": spec["version"],
                   "type": spec["type"], "vendor": spec["vendor"],
                   "description": spec["description"], "capabilities": spec["capabilities"],
                   "dependencies": spec["dependencies"], "permissions": spec["permissions"],
                   "configuration_schema": spec["configuration_schema"],
                   "status": "ENABLED" if pid in ("provider.deepseek", "executor.codex") else "REGISTERED",
                   "health": "OK", "history": [],
                   "created_at": _now_iso(), "updated_at": _now_iso()}
            rec["history"].append({"from": "DISCOVERED", "to": rec["status"], "at": _now_iso(),
                                   "note": "bootstrap"})
            data.append(rec)
    _save(root, "plugins", data)


def register_plugin(root: Path | str, *, plugin_id: str, name: str, version: str,
                    type: str, vendor: str = "", description: str = "",
                    capabilities: list[str] | None = None,
                    dependencies: list[str] | None = None,
                    permissions: list[str] | None = None,
                    configuration_schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """注册 Plugin (DISCOVERED → REGISTERED)。"""
    if type not in PLUGIN_TYPES:
        raise ValueError(f"未知 plugin type: {type}")
    bootstrap(root)
    data = _load(root, "plugins")
    if any(p["plugin_id"] == plugin_id for p in data):
        raise ValueError(f"Plugin 已存在: {plugin_id}")
    rec = {"plugin_id": plugin_id, "name": name, "version": version, "type": type,
           "vendor": vendor, "description": description,
           "capabilities": list(capabilities or []), "dependencies": list(dependencies or []),
           "permissions": list(permissions or []), "configuration_schema": configuration_schema or {},
           "status": "REGISTERED", "health": "OK", "history": [],
           "created_at": _now_iso(), "updated_at": _now_iso()}
    rec["history"].append({"from": "DISCOVERED", "to": "REGISTERED", "at": _now_iso(),
                           "note": "register"})
    data.append(rec)
    _save(root, "plugins", data)
    _audit(root, "PLUGIN_REGISTERED", {"plugin_id": plugin_id, "type": type})
    return rec


def unregister_plugin(root: Path | str, plugin_id: str) -> dict[str, Any]:
    """注销 (仅 RETIRED 或 REGISTERED/DISABLED)。"""
    data = _load(root, "plugins")
    for p in data:
        if p["plugin_id"] == plugin_id:
            if p["status"] == "ENABLED":
                raise ValueError(f"Plugin 启用中不可注销: {plugin_id} (先 disable)")
            data.remove(p)
            _save(root, "plugins", data)
            _audit(root, "PLUGIN_UNREGISTERED", {"plugin_id": plugin_id})
            return {"plugin_id": plugin_id, "status": "UNREGISTERED"}
    raise ValueError(f"Plugin 不存在: {plugin_id}")


def get_plugin(root: Path | str, plugin_id: str) -> dict[str, Any] | None:
    bootstrap(root)
    for p in _load(root, "plugins"):
        if p["plugin_id"] == plugin_id:
            return p
    return None


def list_plugins(root: Path | str, *, type: str | None = None) -> list[dict[str, Any]]:
    bootstrap(root)
    data = _load(root, "plugins")
    if type:
        data = [p for p in data if p["type"] == type]
    return data


def plugin_status(root: Path | str, plugin_id: str, *, target: str,
                  actor: str = "system") -> dict[str, Any]:
    """Lifecycle 迁移 (enable/disable/retire; audit + 非法迁移拒绝)。"""
    bootstrap(root)
    data = _load(root, "plugins")
    for p in data:
        if p["plugin_id"] == plugin_id:
            new = _next_state(p["status"], target)
            p["history"].append({"from": p["status"], "to": new, "at": _now_iso(),
                                 "actor": actor, "note": "status change"})
            p["status"] = new
            p["updated_at"] = _now_iso()
            _save(root, "plugins", data)
            _audit(root, "PLUGIN_STATUS_CHANGED",
                   {"plugin_id": plugin_id, "from": p["history"][-2]["from"], "to": new})
            return p
    raise ValueError(f"Plugin 不存在: {plugin_id}")


def plugin_health(root: Path | str, plugin_id: str) -> dict[str, Any]:
    """Plugin health (状态 OK + 执行器存在性检查)。"""
    p = get_plugin(root, plugin_id)
    if p is None:
        raise ValueError(f"Plugin 不存在: {plugin_id}")
    executor_ok = plugin_id in PROVIDER_EXECUTORS or p["type"] in ("agent", "skill", "tool", "model")
    return {"plugin_id": plugin_id, "type": p["type"], "status": p["status"],
            "health": "OK" if executor_ok else "NO_EXECUTOR",
            "dependencies_ok": all(get_plugin(root, d) is not None for d in p["dependencies"]),
            "checked_at": _now_iso()}


# ------------------------------------------------------------------ 执行器注册 (真实执行, 非 mock)

def register_executor(plugin_id: str, executor: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    """注册 Plugin 的真实执行器 (Core 不修改即可增加新实现)。"""
    PROVIDER_EXECUTORS[plugin_id] = executor


def execute_plugin(root: Path | str, plugin_id: str, *, input: dict[str, Any],
                   actor: str = "system") -> dict[str, Any]:
    """Plugin 执行 (ENABLED + 权限检查 + 真实执行器)。"""
    p = get_plugin(root, plugin_id)
    if p is None:
        raise ValueError(f"Plugin 不存在: {plugin_id}")
    if p["status"] != "ENABLED":
        raise PermissionError(f"Plugin 未启用 (status={p['status']}): {plugin_id}")
    # 权限检查 (复用 S17 边界: 不能自提升)
    for perm in p["permissions"]:
        if perm == "self_elevate":
            raise PermissionError(f"Plugin 禁止自提升权限: {plugin_id}")
    executor = PROVIDER_EXECUTORS.get(plugin_id)
    if executor is None:
        raise ValueError(f"Plugin 无执行器: {plugin_id} (type={p['type']} 元数据插件)")
    result = executor(input)
    _audit(root, "PLUGIN_EXECUTED", {"plugin_id": plugin_id, "actor": actor,
                                     "result": result.get("ok")})
    return {"plugin_id": plugin_id, "ok": result.get("ok", False),
            "result": result.get("result"), "evidence": result.get("evidence", [])}


# ------------------------------------------------------------------ Resolution (deterministic)

def resolve_plugin(root: Path | str, *, required_capability: str,
                   type: str | None = None) -> dict[str, Any]:
    """确定性 Resolution: capability → eligible → permission → policy → 首个 ENABLED。

    非 LLM (测试断言)。
    """
    bootstrap(root)
    eligible = [p for p in _load(root, "plugins")
                if required_capability in p["capabilities"]
                and p["status"] == "ENABLED"]
    if type:
        eligible = [p for p in eligible if p["type"] == type]
    if not eligible:
        return {"resolved": False, "reason": f"无 ENABLED plugin 具备 capability: {required_capability}"}
    # permission: 默认 use_llm/execute_code 可解析 (非 self_elevate)
    for p in eligible:
        if any(perm == "self_elevate" for perm in p["permissions"]):
            continue
        return {"resolved": True, "plugin_id": p["plugin_id"], "type": p["type"],
                "capability": required_capability,
                "reason": f"deterministic resolution (capability match + ENABLED + permission)"}
    return {"resolved": False, "reason": "无满足 permission 的 plugin"}


def plugin_lineage(root: Path | str, plugin_id: str) -> dict[str, Any]:
    """Plugin 生命周期 lineage (append-only)。"""
    p = get_plugin(root, plugin_id)
    if p is None:
        raise ValueError(f"Plugin 不存在: {plugin_id}")
    return {"plugin_id": plugin_id, "type": p["type"], "status": p["status"],
            "capabilities": p["capabilities"], "dependencies": p["dependencies"],
            "history": p["history"]}
