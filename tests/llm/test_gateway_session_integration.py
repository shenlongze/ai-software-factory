"""网关接入会话集成单测 (chain_next 走 gateway + gateway_status 工具)。

覆盖:
- dispatch("gateway_status") 空注册表 → 诚实输出
- dispatch("gateway_status", project) 列任务
- chain_next 走 gateway (monkeypatch gateway_execute)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def test_gateway_status_empty(tmp_path):
    from factory_console.session import agent_loop as _al

    r = _al.dispatch("gateway_status", {}, root=str(tmp_path), project_id="p", service=None, ctx={})
    assert r.get("ok") is True
    assert "外部任务控制面" in r["output"]


def test_gateway_status_lists_tasks(tmp_path):
    from factory_console.session import agent_loop as _al
    from factory_console.external_executor.task_registry import ExternalTaskRegistry

    reg = ExternalTaskRegistry.load(str(tmp_path))
    tid = reg.create(task="写代码", owner="codex", project_id="p1")
    reg.update(tid, status="done", verify={"result": "pass"})
    reg.save()

    r = _al.dispatch("gateway_status", {"project": "p1"}, root=str(tmp_path), project_id="p", service=None, ctx={})
    assert r.get("ok") is True
    assert tid in r["output"]
    assert "pass" in r["output"]


def test_chain_next_uses_gateway(tmp_path, monkeypatch):
    from factory_console.session import agent_loop as _al
    from factory_console.session.exec_state import ExecState

    # 建一个 running 执行链
    st = ExecState.load(str(tmp_path), "sess-1")
    st.start({"goal": "目标", "tasks": [{"title": "任务1", "priority": "P0"}],
              "acceptance": []})
    st.save(str(tmp_path))

    # stub gateway_execute
    import factory_console.external_executor.gateway as _gw
    called = {"n": 0}
    def fake_gw(task, **kw):
        called["n"] += 1
        assert "任务1" in task
        # 模拟真实 gateway: 写任务注册表
        from factory_console.external_executor.task_registry import ExternalTaskRegistry
        reg = ExternalTaskRegistry.load(str(tmp_path))
        reg.create(task=task, owner="codex", project_id="p")
        reg.save()
        return {"ok": True, "task_id": "TASK-GW-x", "executor": "codex",
                "verify": {"result": "pass"}, "output": "完成", "error": ""}
    monkeypatch.setattr(_gw, "gateway_execute", fake_gw)

    r = _al.dispatch("chain_next", {}, root=str(tmp_path), project_id="p", service=None,
                     ctx={"session_id": "sess-1"})
    assert called["n"] == 1, "chain_next 必须走 gateway_execute"
    assert r.get("ok") is True
    # 最后任务完成 → 交付汇报 (证明 gateway 执行被标记完成)
    assert "交付完成" in r["output"]
    # 网关任务注册表有记录
    from factory_console.external_executor.task_registry import ExternalTaskRegistry
    assert ExternalTaskRegistry.load(str(tmp_path)).stats()["total"] >= 1
