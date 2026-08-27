"""执行器网关编排测试 (S10-127 网关 G1/G2/G4)。

覆盖:
- task_registry: create/update/audit/list/stats
- gateway_execute 成功: 执行 → 验证 pass → 任务 done + Spine closure + 记忆
- gateway_execute 失败重试: 首次 fail → 重试 → 仍 fail → 任务 failed
- 无执行器 → 诚实错误
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


@pytest.fixture(scope="module")
def gateway():
    from factory_console.external_executor import gateway as _gw
    return _gw


@pytest.fixture(scope="module")
def registry():
    from factory_console.external_executor.task_registry import ExternalTaskRegistry as _r
    return _r


def test_task_registry_crud(registry, tmp_path):
    reg = registry.load(str(tmp_path))
    tid = reg.create(task="写代码", owner="codex", project_id="p1", verify_plan="pytest")
    assert reg.get(tid)["status"] == "running"
    reg.update(tid, status="done", retry_count=1)
    reg.audit(tid, "finished", "ok")
    reg.save()

    reg2 = registry.load(str(tmp_path))
    t = reg2.get(tid)
    assert t["status"] == "done"
    assert t["retry_count"] == 1
    assert any(a["event"] == "finished" for a in t["audit"])
    assert len(reg2.list(project_id="p1")) == 1
    assert reg2.stats()["total"] == 1


def _fake_registry():
    from factory_console.external_executor.schema import (CapabilitiesSpec,
                                                          ExternalExecutorAdapter,
                                                          InvocationSpec)
    adapter = ExternalExecutorAdapter(
        id="fake", name="fake", binary="echo",
        invocation=InvocationSpec(non_interactive=["{prompt}"], project_dir="none"),
        capabilities=CapabilitiesSpec(),
    )

    class FakeReg:
        def list(self):
            return [adapter]
    return FakeReg()


def test_gateway_success(gateway, tmp_path, monkeypatch):
    from factory_console.external_executor import executor as _exec
    import factory_console.external_executor.registry as _reg

    monkeypatch.setattr(gateway, "_pick_executor", lambda *a, **k: ("fake", ""))
    monkeypatch.setattr(_reg, "build_registry", lambda *a, **k: _fake_registry())
    # stub executor.run 成功
    monkeypatch.setattr(_exec, "run", lambda *a, **k: {"exit_code": 0, "output": "done!", "error": "", "command": "fake"})
    # stub record_invocation 返回 result_id
    monkeypatch.setattr(_exec, "record_invocation", lambda *a, **k: {"result_id": "EXS-test"})
    # stub auto_verify pass
    monkeypatch.setattr(_exec, "auto_verify", lambda *a, **k: {"method": "pytest", "result": "pass", "score": 1.0, "reason": ""})
    monkeypatch.setattr(_exec, "verify_invocation", lambda *a, **k: None)

    r = gateway.gateway_execute("写个函数", data_dir=str(tmp_path), project_id="p1", max_retry=1)
    assert r["ok"] is True
    assert r["result_id"] == "EXS-test"
    assert r["verify"]["result"] == "pass"
    assert r["retry_count"] == 0

    # 任务注册 done + Spine closure + 记忆回填
    from factory_console.external_executor.task_registry import ExternalTaskRegistry
    t = ExternalTaskRegistry.load(str(tmp_path)).get(r["task_id"])
    assert t["status"] == "done"
    from factory_console.session.handoff import ProjectSpine
    sp = ProjectSpine.load(str(tmp_path), "p1")
    assert len(sp.data["closure_memory"]) == 1
    from factory_console.session.project_memory import MemoryStore
    mem = MemoryStore.load(str(tmp_path), "p1")
    assert len(mem.entries) >= 1


def test_gateway_failure_retry_then_fail(gateway, tmp_path, monkeypatch):
    from factory_console.external_executor import executor as _exec
    import factory_console.external_executor.registry as _reg

    monkeypatch.setattr(gateway, "_pick_executor", lambda *a, **k: ("fake", ""))
    monkeypatch.setattr(_reg, "build_registry", lambda *a, **k: _fake_registry())
    monkeypatch.setattr(_exec, "run", lambda *a, **k: {"exit_code": 1, "output": "", "error": "boom", "command": "fake"})
    monkeypatch.setattr(_exec, "record_invocation", lambda *a, **k: {"result_id": "EXS-x"})
    monkeypatch.setattr(_exec, "auto_verify", lambda *a, **k: {"method": "", "result": "unknown", "score": None, "reason": ""})
    monkeypatch.setattr(_exec, "verify_invocation", lambda *a, **k: None)

    r = gateway.gateway_execute("写个函数", data_dir=str(tmp_path), project_id="p1", max_retry=2)
    assert r["ok"] is False
    assert r["retry_count"] == 2
    from factory_console.external_executor.task_registry import ExternalTaskRegistry
    t = ExternalTaskRegistry.load(str(tmp_path)).get(r["task_id"])
    assert t["status"] == "failed"


def test_gateway_no_executor(gateway, tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "_pick_executor", lambda *a, **k: ("", ""))
    r = gateway.gateway_execute("任务", data_dir=str(tmp_path), project_id="p1")
    assert r["ok"] is False
    assert "无可用外部执行器" in r["error"]
