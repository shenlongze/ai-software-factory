"""S32: Composable Workforce & Capability。

覆盖:
- AgentProfile → Plugin Composition (bind)
- Composition Resolution (deterministic; 6 plugins 全 ENABLED)
- Capability 统一 (S30 ↔ S31 单一语义)
- Scenario A: provider A→B 替换 (Core 不变) → 执行成功
- Scenario D: plugin DISABLED → Workforce 拒绝
- Lineage (plugin version/runtime/model 可追溯)
- CLI / API
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.workforce_os import _get_or_create_agent_profile  # noqa: E402
from factory_console.workforce_composition import (  # noqa: E402
    bind_agent_profile, resolve_agent_composition, capability_plugins,
    unified_capability_list, composition_lineage,
)
from factory_console.plugin_kernel import (  # noqa: E402
    register_plugin, plugin_status, get_plugin,
)


def _setup_dev(tmp_path) -> str:
    prof = _get_or_create_agent_profile(str(tmp_path), "software_developer")
    bind_agent_profile(str(tmp_path), agent_profile_id=prof["agent_id"])
    return prof["agent_id"]


# --- Composition Bind + Resolve ---

def test_bind_and_resolve(tmp_path):
    aid = _setup_dev(tmp_path)
    prof = _get_or_create_agent_profile(str(tmp_path), "software_developer")
    assert "composition" in prof
    assert prof["composition"]["agent_plugin_id"] == "agent.dev"
    res = resolve_agent_composition(str(tmp_path), aid)
    assert res["ok"] is True
    assert len(res["plugins"]) == 6  # agent+model+provider+runtime+skill+tool
    assert "implement" in res["capabilities"]
    assert "llm.complete" in res["capabilities"]  # 统一语义
    assert res["plugins"]["provider_plugin_id"]["status"] == "ENABLED"


# --- Capability 统一 ---

def test_unified_capability(tmp_path):
    _setup_dev(tmp_path)
    impl = capability_plugins(str(tmp_path), "implement")
    assert impl, "implement 必须可解析"
    assert any(p["plugin_id"] == "executor.codex" for p in impl)
    uc = unified_capability_list(str(tmp_path))
    assert len(uc) >= 10
    impl_uc = next(c for c in uc if c["capability"] == "implement")
    assert impl_uc["resolvable"] is True
    assert impl_uc["plugin_capability"] == "execute.code"


# --- Scenario A: provider 替换 (Core 不变) ---

def test_provider_substitution(tmp_path):
    aid = _setup_dev(tmp_path)
    # 原 provider = deepseek
    res0 = resolve_agent_composition(str(tmp_path), aid)
    assert res0["plugins"]["provider_plugin_id"]["plugin_id"] == "provider.deepseek"
    # 新增 provider.alt (不修改 Core)
    register_plugin(str(tmp_path), plugin_id="provider.alt", name="Alt", version="2.0",
                    type="provider", capabilities=["llm.complete"], permissions=["use_llm"])
    plugin_status(str(tmp_path), "provider.alt", target="ENABLED")
    bind_agent_profile(str(tmp_path), agent_profile_id=aid, provider_plugin_id="provider.alt")
    res = resolve_agent_composition(str(tmp_path), aid)
    assert res["ok"] is True
    assert res["plugins"]["provider_plugin_id"]["plugin_id"] == "provider.alt"
    assert res["plugins"]["provider_plugin_id"]["version"] == "2.0"


# --- Scenario B: skill 替换 (Core 不变) ---

def test_skill_substitution(tmp_path):
    aid = _setup_dev(tmp_path)
    register_plugin(str(tmp_path), plugin_id="skill.advanced", name="Advanced", version="2.0",
                    type="skill", capabilities=["implement", "optimize"], permissions=["execute_code"])
    plugin_status(str(tmp_path), "skill.advanced", target="ENABLED")
    bind_agent_profile(str(tmp_path), agent_profile_id=aid, skill_plugin_ids=["skill.advanced"])
    res = resolve_agent_composition(str(tmp_path), aid)
    assert res["ok"] is True
    assert any(slot.startswith("skill") and info["plugin_id"] == "skill.advanced"
               for slot, info in res["plugins"].items())
    assert "optimize" in res["capabilities"]


# --- Scenario D: disabled → Workforce 拒绝 ---

def test_disabled_rejected(tmp_path):
    aid = _setup_dev(tmp_path)
    plugin_status(str(tmp_path), "provider.deepseek", target="DISABLED")
    res = resolve_agent_composition(str(tmp_path), aid)
    assert res["ok"] is False
    assert any("未启用" in f for f in res["failures"])
    plugin_status(str(tmp_path), "provider.deepseek", target="ENABLED")
    res2 = resolve_agent_composition(str(tmp_path), aid)
    assert res2["ok"] is True


# --- 两 Workforce 不同 Plugin (Core 不变) ---

def test_two_workforces_distinct(tmp_path):
    dev = _get_or_create_agent_profile(str(tmp_path), "software_developer")
    qa = _get_or_create_agent_profile(str(tmp_path), "qa_engineer")
    bind_agent_profile(str(tmp_path), agent_profile_id=dev["agent_id"])
    bind_agent_profile(str(tmp_path), agent_profile_id=qa["agent_id"])
    r_dev = resolve_agent_composition(str(tmp_path), dev["agent_id"])
    r_qa = resolve_agent_composition(str(tmp_path), qa["agent_id"])
    assert r_dev["plugins"]["agent_plugin_id"]["plugin_id"] == "agent.dev"
    assert r_qa["plugins"]["agent_plugin_id"]["plugin_id"] == "agent.qa"
    assert "verify" in r_qa["capabilities"]
    assert "verify" not in r_dev["capabilities"]
    # Core 未修改 (两个不同 composition 共存)


# --- Lineage ---

def test_composition_lineage(tmp_path):
    aid = _setup_dev(tmp_path)
    lg = composition_lineage(str(tmp_path), aid)
    assert lg["runtime"] == "runtime.llm"
    assert lg["model"] == "model.default"
    assert lg["provider"] == "provider.deepseek"
    assert lg["plugin_versions"]["provider_plugin_id"] == "1.0.0"
    assert "agent_profile → plugins" in lg["lineage"]


# --- CLI ---

def test_cli_composition(tmp_path):
    aid = _setup_dev(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["composition", "resolve", aid, "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["composition", "capabilities", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["composition", "lineage", aid, "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["composition", "bind", aid, "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["composition", "resolve", "nonexistent", "--data-dir", str(tmp_path)]) == 1


# --- API ---

def test_api_composition(tmp_path):
    aid = _setup_dev(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.get(f"/api/agent-profiles/{aid}/composition")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    resp = client.get(f"/api/agent-profiles/{aid}/lineage")
    assert resp.status_code == 200
    assert resp.json()["runtime"] == "runtime.llm"
    resp = client.post(f"/api/agent-profiles/{aid}/bind",
                       json={"provider_plugin_id": "provider.deepseek"})
    assert resp.status_code == 200
    resp = client.get("/api/capabilities/unified")
    assert resp.status_code == 200
    assert resp.json()["count"] >= 10
