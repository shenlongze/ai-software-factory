"""S31: Everything-is-a-Plugin Foundation。

覆盖:
- Plugin Contract (plugin_id/type/capabilities/dependencies/permissions)
- Plugin Registry (register/get/list/exists/unregister)
- Plugin Lifecycle (DISCOVERED→REGISTERED→ENABLED→DISABLED→RETIRED; 非法迁移拒绝)
- 确定性 Resolution (非 LLM)
- Governance (禁用后执行拒绝; 自提升权限拒绝)
- 真实 Plugin 执行 (provider plugin + register_executor)
- **反硬编码 Architecture Test: 新增第二个 provider 不改 Core**
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

from factory_console.plugin_kernel import (  # noqa: E402
    bootstrap, list_plugins, get_plugin, register_plugin, unregister_plugin,
    plugin_status, plugin_health, register_executor, execute_plugin,
    resolve_plugin, plugin_lineage,
)


def _det_executor(input):
    return {"ok": True, "result": "det-ok", "evidence": [{"det": True}]}


# --- Bootstrap + Registry ---

def test_bootstrap_builtin(tmp_path):
    bootstrap(str(tmp_path))
    plugins = list_plugins(str(tmp_path))
    assert len(plugins) >= 4
    deepseek = get_plugin(str(tmp_path), "provider.deepseek")
    assert deepseek["type"] == "provider"
    assert deepseek["status"] == "ENABLED"  # 默认启用
    assert "llm.complete" in deepseek["capabilities"]
    assert deepseek["permissions"] == ["use_llm"]


def test_register_get_list(tmp_path):
    p = register_plugin(str(tmp_path), plugin_id="test.plugin", name="Test", version="1.0",
                        type="skill", capabilities=["analyze"],
                        dependencies=["provider.deepseek"], permissions=["read"])
    assert p["status"] == "REGISTERED"
    assert get_plugin(str(tmp_path), "test.plugin")["capabilities"] == ["analyze"]
    assert "test.plugin" in [x["plugin_id"] for x in list_plugins(str(tmp_path))]
    # 重复注册拒绝
    with pytest.raises(ValueError, match="已存在"):
        register_plugin(str(tmp_path), plugin_id="test.plugin", name="T", version="1",
                        type="skill")
    # 未知 type 拒绝
    with pytest.raises(ValueError):
        register_plugin(str(tmp_path), plugin_id="bad.type", name="B", version="1", type="nope")


# --- Lifecycle ---

def test_lifecycle(tmp_path):
    bootstrap(str(tmp_path))
    plugin_status(str(tmp_path), "provider.ollama", target="ENABLED")
    assert get_plugin(str(tmp_path), "provider.ollama")["status"] == "ENABLED"
    plugin_status(str(tmp_path), "provider.ollama", target="DISABLED")
    assert get_plugin(str(tmp_path), "provider.ollama")["status"] == "DISABLED"
    plugin_status(str(tmp_path), "provider.ollama", target="RETIRED")
    assert get_plugin(str(tmp_path), "provider.ollama")["status"] == "RETIRED"
    # 非法迁移: RETIRED → ENABLED 拒绝
    with pytest.raises(ValueError, match="非法状态迁移"):
        plugin_status(str(tmp_path), "provider.ollama", target="ENABLED")
    # append-only history
    assert len(get_plugin(str(tmp_path), "provider.ollama")["history"]) >= 3


# --- 确定性 Resolution (非 LLM) ---

def test_deterministic_resolution(tmp_path):
    bootstrap(str(tmp_path))
    res = resolve_plugin(str(tmp_path), required_capability="llm.complete")
    assert res["resolved"] is True
    assert res["plugin_id"] == "provider.deepseek"
    assert "deterministic" in res["reason"]
    # 不存在的 capability → 不解析
    res2 = resolve_plugin(str(tmp_path), required_capability="nonexistent_cap")
    assert res2["resolved"] is False


# --- Governance: 禁用拒绝 + 自提升拒绝 ---

def test_disabled_execution_rejected(tmp_path):
    bootstrap(str(tmp_path))
    register_executor("provider.deepseek", _det_executor)
    # 先禁用
    plugin_status(str(tmp_path), "provider.deepseek", target="DISABLED")
    with pytest.raises(PermissionError, match="未启用"):
        execute_plugin(str(tmp_path), "provider.deepseek", input={})
    # 重新启用 → 可执行
    plugin_status(str(tmp_path), "provider.deepseek", target="ENABLED")
    r = execute_plugin(str(tmp_path), "provider.deepseek", input={})
    assert r["ok"] is True


def test_self_elevate_rejected(tmp_path):
    """Plugin 不能自提升权限 (self_elevate 拒绝)。"""
    bootstrap(str(tmp_path))
    register_plugin(str(tmp_path), plugin_id="evil.plugin", name="Evil", version="1",
                    type="tool", capabilities=["x"], permissions=["self_elevate"])
    register_executor("evil.plugin", lambda i: {"ok": True, "result": "evil"})
    plugin_status(str(tmp_path), "evil.plugin", target="ENABLED")
    with pytest.raises(PermissionError, match="自提升"):
        execute_plugin(str(tmp_path), "evil.plugin", input={})


# --- 真实 Plugin 执行 ---

def test_plugin_execution(tmp_path):
    bootstrap(str(tmp_path))
    register_executor("executor.codex", lambda i: {"ok": True, "result": "codex-sim"})
    r = execute_plugin(str(tmp_path), "executor.codex", input={"prompt": "x"})
    assert r["ok"] is True
    assert r["plugin_id"] == "executor.codex"


# --- 反硬编码 Architecture Test (核心) ---

def test_add_second_impl_without_core_change(tmp_path):
    """Core 不修改即可注册第二个 provider 实现 (反硬编码验证)。"""
    bootstrap(str(tmp_path))
    # 新增 provider #1 (未修改 Core)
    register_plugin(str(tmp_path), plugin_id="provider.second", name="Second", version="1.0",
                    type="provider", capabilities=["llm.complete"], permissions=["use_llm"])
    plugin_status(str(tmp_path), "provider.second", target="ENABLED")
    register_executor("provider.second", lambda i: {"ok": True, "result": "second-ok"})
    r1 = execute_plugin(str(tmp_path), "provider.second", input={})
    assert r1["ok"] is True and r1["result"] == "second-ok"
    # 新增 provider #2 (仍不修改 Core)
    register_plugin(str(tmp_path), plugin_id="provider.third", name="Third", version="1.0",
                    type="provider", capabilities=["llm.complete"], permissions=["use_llm"])
    plugin_status(str(tmp_path), "provider.third", target="ENABLED")
    register_executor("provider.third", lambda i: {"ok": True, "result": "third-ok"})
    r2 = execute_plugin(str(tmp_path), "provider.third", input={})
    assert r2["ok"] is True and r2["result"] == "third-ok"
    # 两个实现独立共存
    assert get_plugin(str(tmp_path), "provider.second")["status"] == "ENABLED"
    assert get_plugin(str(tmp_path), "provider.third")["status"] == "ENABLED"


# --- Unregister ---

def test_unregister(tmp_path):
    bootstrap(str(tmp_path))
    register_plugin(str(tmp_path), plugin_id="temp.plugin", name="T", version="1",
                    type="tool", capabilities=["x"], permissions=["y"])
    unregister_plugin(str(tmp_path), "temp.plugin")
    assert get_plugin(str(tmp_path), "temp.plugin") is None
    # ENABLED 不可注销
    plugin_status(str(tmp_path), "provider.anthropic", target="ENABLED")
    with pytest.raises(ValueError, match="启用中"):
        unregister_plugin(str(tmp_path), "provider.anthropic")


# --- Lineage ---

def test_plugin_lineage(tmp_path):
    bootstrap(str(tmp_path))
    lg = plugin_lineage(str(tmp_path), "provider.deepseek")
    assert lg["type"] == "provider"
    assert lg["status"] == "ENABLED"
    assert len(lg["history"]) >= 1


# --- CLI ---

def test_cli_plugin(tmp_path):
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["plugin", "list", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["plugin", "inspect", "provider.deepseek", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["plugin", "status", "provider.deepseek", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["plugin", "health", "provider.deepseek", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["plugin", "resolve", "llm.complete", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["plugin", "enable", "provider.ollama", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["plugin", "disable", "provider.ollama", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["plugin", "inspect", "nonexistent", "--data-dir", str(tmp_path)]) == 1


# --- API ---

def test_api_plugin(tmp_path):
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.get("/api/plugins")
    assert resp.status_code == 200
    assert resp.json()["count"] >= 4
    resp = client.get("/api/plugins/provider.deepseek")
    assert resp.status_code == 200
    assert resp.json()["type"] == "provider"
    resp = client.get("/api/plugins/provider.deepseek/status")
    assert resp.status_code == 200
    resp = client.get("/api/plugins/provider.deepseek/health")
    assert resp.status_code == 200
    resp = client.post("/api/plugins/provider.ollama/enable")
    assert resp.status_code == 200
    resp = client.post("/api/plugins/provider.ollama/disable")
    assert resp.status_code == 200
    resp = client.get("/api/plugins/nonexistent")
    assert resp.status_code == 404
