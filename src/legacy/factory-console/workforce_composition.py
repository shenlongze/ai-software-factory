"""factory-console/workforce_composition.py — S32 Composable Workforce & Capability.

AgentProfile = Plugin references + policy (非实现):
  agent_plugin_id / skill_plugin_ids[] / tool_plugin_ids[] /
  model_plugin_id / provider_plugin_id / runtime_plugin_id

- Capability 统一: S30 capabilities ↔ S31 plugin capabilities (单一语义)
- Composition Resolution: agent→skill→tool→model/provider→runtime→permission→policy (deterministic)
- 替换: provider/skill/runtime A→B 不修改 Core; disabled 拒绝执行
- Lineage: artifact → node_run → task → agent_profile → plugin version → runtime → model

复用: S31 Plugin Kernel + S30 Workforce + S17 governance
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .plugin_kernel import (bootstrap, get_plugin, resolve_plugin, list_plugins)
from .workforce_os import _get_or_create_agent_profile, list_agent_profiles
from .workforce import ROLE_CAPABILITIES

#: Capability → plugin capability 映射 (统一 S30/S31 语义)
CAPABILITY_PLUGIN_MAP: dict[str, str] = {
    "implement": "execute.code",
    "repair": "execute.code",
    "verify": "execute.code",
    "release_prepare": "execute.code",
    "discover_product": "llm.complete",
    "create_prd": "llm.complete",
    "design_architecture": "llm.complete",
    "technical_decision": "llm.complete",
    "quality_decision": "llm.complete",
    "market_research": "llm.complete",
    "design_ux": "llm.complete",
}

#: 默认 plugin binding (角色 → plugin refs; 确定性)
ROLE_PLUGIN_BINDINGS: dict[str, dict[str, Any]] = {
    "product_manager": {"agent_plugin_id": "agent.pm", "provider_plugin_id": "provider.deepseek",
                        "model_plugin_id": "model.default", "runtime_plugin_id": "runtime.llm"},
    "market_analyst": {"agent_plugin_id": "agent.market", "provider_plugin_id": "provider.deepseek",
                       "model_plugin_id": "model.default", "runtime_plugin_id": "runtime.llm"},
    "ux_designer": {"agent_plugin_id": "agent.ux", "provider_plugin_id": "provider.deepseek",
                    "model_plugin_id": "model.default", "runtime_plugin_id": "runtime.llm"},
    "software_architect": {"agent_plugin_id": "agent.arch", "provider_plugin_id": "provider.deepseek",
                           "model_plugin_id": "model.default", "runtime_plugin_id": "runtime.llm"},
    "software_developer": {"agent_plugin_id": "agent.dev", "provider_plugin_id": "provider.deepseek",
                           "model_plugin_id": "model.default", "runtime_plugin_id": "runtime.llm"},
    "qa_engineer": {"agent_plugin_id": "agent.qa", "provider_plugin_id": "provider.deepseek",
                    "model_plugin_id": "model.default", "runtime_plugin_id": "runtime.llm"},
    "release_engineer": {"agent_plugin_id": "agent.release", "provider_plugin_id": "provider.deepseek",
                         "model_plugin_id": "model.default", "runtime_plugin_id": "runtime.llm"},
}

#: 内置 Agent/Skill/Tool/Model/Runtime Plugins (真实, 与 S31 provider 同构)
BUILTIN_COMPOSITION_PLUGINS: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "composition" / f"{name}.json"


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
            trace_id=payload.get("agent_profile_id") or "",
            actor_type="system", actor_id="composition",
            action=f"composition.{event_type.lower()}",
            source="workforce_composition", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"composition": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ Composition Plugins bootstrap

def _ensure_composition_plugins(root: Path | str) -> None:
    """注册内置 Agent/Skill/Tool/Model/Runtime Plugins (与 S31 provider 同构, 不改 Core)。"""
    from .plugin_kernel import register_plugin, plugin_status

    specs = {
        "agent.dev": ("agent", "Developer Agent", ["implement", "repair"], ["execute.code"]),
        "agent.qa": ("agent", "QA Agent", ["verify", "test"], ["execute.code"]),
        "agent.arch": ("agent", "Architect Agent", ["design_architecture"], ["llm.complete"]),
        "agent.pm": ("agent", "PM Agent", ["create_prd"], ["llm.complete"]),
        "skill.coding": ("skill", "Coding Skill", ["implement"], ["execute.code"]),
        "skill.testing": ("skill", "Testing Skill", ["verify"], ["execute.code"]),
        "skill.analysis": ("skill", "Analysis Skill", ["create_prd"], ["llm.complete"]),
        "tool.codex": ("tool", "Codex Tool", ["execute.code"], []),
        "model.default": ("model", "Default Model", ["llm.complete"], []),
        "runtime.llm": ("runtime", "LLM Runtime", ["llm.complete"], []),
    }
    for pid, (ptype, name, caps, _) in specs.items():
        if get_plugin(root, pid) is None:
            try:
                register_plugin(root, plugin_id=pid, name=name, version="1.0.0",
                                type=ptype, vendor="ai-factory",
                                capabilities=caps, permissions=["use_llm"] if "llm" in " ".join(caps) else ["execute_code"])
                plugin_status(root, pid, target="ENABLED")
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------------------------ AgentProfile Composition

def bind_agent_profile(root: Path | str, *, agent_profile_id: str,
                       agent_plugin_id: str = "", skill_plugin_ids: list[str] | None = None,
                       tool_plugin_ids: list[str] | None = None,
                       model_plugin_id: str = "", provider_plugin_id: str = "",
                       runtime_plugin_id: str = "") -> dict[str, Any]:
    """给 AgentProfile 绑定 Plugin Composition (Plugin references, 非实现)。"""
    _ensure_composition_plugins(root)
    # 复用 S30 AgentProfile 存储 (SSOT)
    from .workforce_os import list_agent_profiles as _list_profiles, _file as _wfos_file
    import json as _json
    profs_path = _wfos_file(root, "agent_profiles")
    try:
        profs = _json.loads(profs_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        profs = []
    for p in profs:
        if p["agent_id"] == agent_profile_id:
            # 从 role 默认 binding 填充未指定的
            role_bind = ROLE_PLUGIN_BINDINGS.get(p["role"], {})
            p["composition"] = {
                "agent_plugin_id": agent_plugin_id or role_bind.get("agent_plugin_id", ""),
                "skill_plugin_ids": skill_plugin_ids or ["skill.coding" if p["role"] in ("software_developer", "qa_engineer") else "skill.analysis"],
                "tool_plugin_ids": tool_plugin_ids or ["tool.codex"],
                "model_plugin_id": model_plugin_id or role_bind.get("model_plugin_id", "model.default"),
                "provider_plugin_id": provider_plugin_id or role_bind.get("provider_plugin_id", "provider.deepseek"),
                "runtime_plugin_id": runtime_plugin_id or role_bind.get("runtime_plugin_id", "runtime.llm"),
            }
            profs_path.write_text(_json.dumps(profs, ensure_ascii=False, indent=2), encoding="utf-8")
            _audit(root, "AGENT_PROFILE_BOUND",
                   {"agent_profile_id": agent_profile_id, "composition": p["composition"]})
            return p
    raise ValueError(f"AgentProfile 不存在: {agent_profile_id}")


def _get_profile(root: Path | str, agent_profile_id: str) -> dict[str, Any]:
    from .workforce_os import list_agent_profiles
    for p in list_agent_profiles(root):
        if p["agent_id"] == agent_profile_id:
            return p
    raise ValueError(f"AgentProfile 不存在: {agent_profile_id}")


def resolve_agent_composition(root: Path | str, agent_profile_id: str) -> dict[str, Any]:
    """确定性 Composition Resolution: agent→skill→tool→model/provider→runtime→permission→policy。"""
    _ensure_composition_plugins(root)
    p = _get_profile(root, agent_profile_id)
    comp = p.get("composition") or {}
    # 逐 plugin resolve (ENABLED 检查 + permission)
    resolved: dict[str, Any] = {"agent_profile_id": agent_profile_id, "role": p["role"],
                                "ok": True, "plugins": {}, "failures": []}
    required = {
        "agent_plugin_id": comp.get("agent_plugin_id", ""),
        "model_plugin_id": comp.get("model_plugin_id", ""),
        "provider_plugin_id": comp.get("provider_plugin_id", ""),
        "runtime_plugin_id": comp.get("runtime_plugin_id", ""),
    }
    for key, pid in required.items():
        plugin = get_plugin(root, pid)
        if plugin is None:
            resolved["failures"].append(f"{key}: plugin 不存在 {pid}")
            resolved["ok"] = False
            continue
        if plugin["status"] != "ENABLED":
            resolved["failures"].append(f"{key}: plugin 未启用 {pid} (status={plugin['status']})")
            resolved["ok"] = False
            continue
        resolved["plugins"][key] = {"plugin_id": pid, "type": plugin["type"],
                                    "version": plugin["version"], "status": plugin["status"]}
    for i, sid in enumerate(comp.get("skill_plugin_ids", []) or []):
        plugin = get_plugin(root, sid)
        if plugin is None or plugin["status"] != "ENABLED":
            resolved["failures"].append(f"skill_plugin_ids[{i}]: {sid} 不可用")
            resolved["ok"] = False
            continue
        resolved["plugins"][f"skill_{i}"] = {"plugin_id": sid, "type": "skill",
                                             "version": plugin["version"], "status": plugin["status"]}
    for i, tid in enumerate(comp.get("tool_plugin_ids", []) or []):
        plugin = get_plugin(root, tid)
        if plugin is None or plugin["status"] != "ENABLED":
            resolved["failures"].append(f"tool_plugin_ids[{i}]: {tid} 不可用")
            resolved["ok"] = False
            continue
        resolved["plugins"][f"tool_{i}"] = {"plugin_id": tid, "type": "tool",
                                            "version": plugin["version"], "status": plugin["status"]}
    # capabilities = agent_plugin + skill_plugins + tool_plugins (统一语义)
    caps: list[str] = []
    for slot, info in resolved["plugins"].items():
        plugin = get_plugin(root, info["plugin_id"])
        if plugin:
            for c in plugin["capabilities"]:
                if c not in caps:
                    caps.append(c)
    resolved["capabilities"] = caps
    resolved["permissions"] = p.get("policies", []) or [f"permission:{p['role']}"]
    resolved["policy"] = "governance.production"
    if not resolved["failures"]:
        resolved["explain"] = f"AgentProfile {agent_profile_id} 组成 {len(resolved['plugins'])} 个 plugin 全部 ENABLED"
    else:
        resolved["explain"] = f"Composition 失败: {resolved['failures']}"
    return resolved


# ------------------------------------------------------------------ Capability 统一

def capability_plugins(root: Path | str, capability: str) -> list[dict[str, Any]]:
    """S30 capability → 满足的 plugins (统一语义)。"""
    _ensure_composition_plugins(root)
    plugin_cap = CAPABILITY_PLUGIN_MAP.get(capability)
    if not plugin_cap:
        return []
    return [{"plugin_id": p["plugin_id"], "type": p["type"], "status": p["status"],
             "version": p["version"]} for p in list_plugins(root)
            if p["status"] == "ENABLED" and plugin_cap in p["capabilities"]]


def unified_capability_list(root: Path | str) -> list[dict[str, Any]]:
    """统一 capability 视图 (S30 capabilities ↔ plugin capability + plugins)。"""
    out = []
    for role, caps in ROLE_CAPABILITIES.items():
        for cap in caps:
            plugins = capability_plugins(root, cap)
            out.append({"capability": cap, "role": role, "plugin_capability": CAPABILITY_PLUGIN_MAP.get(cap),
                        "plugins": [p["plugin_id"] for p in plugins],
                        "resolvable": bool(plugins)})
    return out


# ------------------------------------------------------------------ Composition Lineage

def composition_lineage(root: Path | str, agent_profile_id: str) -> dict[str, Any]:
    """AgentProfile → plugin composition → version → runtime → model 全链。"""
    p = _get_profile(root, agent_profile_id)
    comp = p.get("composition") or {}
    resolved = resolve_agent_composition(root, agent_profile_id)
    return {"agent_profile_id": agent_profile_id, "role": p["role"],
            "composition": comp,
            "resolved": resolved,
            "plugin_versions": {slot: info["version"] for slot, info in resolved["plugins"].items()},
            "runtime": comp.get("runtime_plugin_id", ""),
            "model": comp.get("model_plugin_id", ""),
            "provider": comp.get("provider_plugin_id", ""),
            "lineage": "agent_profile → plugins → runtime/model/provider"}
