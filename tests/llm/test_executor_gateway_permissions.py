"""网关 G3 配置化适配器+权限单测。

覆盖:
- registry 加载 *.json 声明 (新增执行器=加 JSON, 不改代码)
- gateway: project_dir 白名单拒绝 → failed + denied
- gateway: 任务含命令黑名单片段 → 拒绝
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def test_registry_loads_json_adapter(tmp_path):
    from factory_console.external_executor.registry import build_registry

    d = tmp_path / "external-ais"
    d.mkdir(parents=True)
    (d / "myexec.json").write_text(json.dumps({
        "id": "myexec", "name": "My Executor", "binary": "mycli",
        "discovery": ["PATH"],
        "invocation": {"non_interactive": ["{prompt}"], "project_dir": "none", "timeout": 60},
        "permissions": {"allowed_project_dirs": ["/work"], "disallowed_commands": ["rm -rf"]},
    }), encoding="utf-8")

    reg = build_registry(str(tmp_path))
    a = reg.get("myexec")
    assert a is not None
    assert a.permissions.allowed_project_dirs == ["/work"]
    assert a.permissions.disallowed_commands == ["rm -rf"]


def test_gateway_project_dir_whitelist(tmp_path, monkeypatch):
    from factory_console.external_executor import gateway as _gw
    from factory_console.external_executor.schema import (CapabilitiesSpec,
                                                          ExternalExecutorAdapter,
                                                          InvocationSpec,
                                                          ExecutorPermissions)

    adapter = ExternalExecutorAdapter(
        id="safe", name="safe", binary="echo",
        invocation=InvocationSpec(non_interactive=["{prompt}"], project_dir="none"),
        capabilities=CapabilitiesSpec(),
        permissions=ExecutorPermissions(allowed_project_dirs=["/only/this"]),
    )

    class FakeReg:
        def list(self):
            return [adapter]

    import factory_console.external_executor.registry as _reg
    _reg.build_registry = lambda *a, **k: FakeReg()
    _gw._pick_executor = lambda *a, **k: ("safe", "")

    # project_id 指向 /elsewhere (不在白名单) → denied
    r = _gw.gateway_execute("task", data_dir=str(tmp_path), project_id="p1")
    assert r["ok"] is False
    assert "白名单" in r["error"]

    # 注册表里任务 failed
    from factory_console.external_executor.task_registry import ExternalTaskRegistry
    t = ExternalTaskRegistry.load(str(tmp_path)).get(r["task_id"])
    assert t["status"] == "failed"
    assert any(a["event"] == "denied" for a in t["audit"])


def test_gateway_command_blacklist(tmp_path, monkeypatch):
    from factory_console.external_executor import gateway as _gw
    from factory_console.external_executor.schema import (CapabilitiesSpec,
                                                          ExternalExecutorAdapter,
                                                          InvocationSpec,
                                                          ExecutorPermissions)

    adapter = ExternalExecutorAdapter(
        id="safe2", name="safe2", binary="echo",
        invocation=InvocationSpec(non_interactive=["{prompt}"], project_dir="none"),
        capabilities=CapabilitiesSpec(),
        permissions=ExecutorPermissions(disallowed_commands=["rm -rf"]),
    )

    class FakeReg:
        def list(self):
            return [adapter]

    import factory_console.external_executor.registry as _reg
    _reg.build_registry = lambda *a, **k: FakeReg()
    _gw._pick_executor = lambda *a, **k: ("safe2", "")

    # 任务包含黑名单片段 → 拒绝 (run 不被调用)
    from factory_console.external_executor import executor as _exec
    calls = {"n": 0}
    def fake_run(*a, **k):
        calls["n"] += 1
        return {"exit_code": 0, "output": "", "error": "", "command": ""}
    _exec.run = fake_run

    r = _gw.gateway_execute("执行 rm -rf 操作", data_dir=str(tmp_path), project_id="p1")
    assert r["ok"] is False
    assert "黑名单" in r["error"]
    assert calls["n"] == 0, "黑名单命中时不得调用执行器"
