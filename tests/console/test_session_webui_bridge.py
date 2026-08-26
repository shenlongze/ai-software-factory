"""tests/console/test_session_webui_bridge.py — S 会话×软件打通 (v1.1.163)。

Founder: 会话和软件多功能断了 (S-1~S-6), 不能只修测到的那一个。
覆盖 (adapter api_session_send 意图分发, 代理 _console_import mock LLM 意图):
- create_idea: '记录个想法 XX' → 建 idea feature (maturity=idea)
- task_action: '把 XX 标记完成' → 任务逐步到 done; '改成 P0' → priority
- project_action: 收藏 → starred=True
- project_artifacts: 产出物清单 / monitor: 系统监控 / settings: 设置概况
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core", _ROOT / "factory-org"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")

try:
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except Exception:  # noqa: BLE001
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi 未安装")


@pytest.fixture
def app(tmp_path):
    """真实装配 (tmp root, 不污染 ~/.factory) + 建项目/任务。"""
    service = _adapter.build_console_service(tmp_path, event_logger=None)
    app = _adapter.build_app(service, event_logger=None, factory_root=tmp_path)
    proj = service.create_project("会话桥演示", name="会话桥")
    task = service.create_task(proj.id, title="语音记账", priority="P2")
    with TestClient(app) as c:
        yield {"client": c, "root": tmp_path, "service": service, "proj": proj, "task": task}


def _patch_intent(monkeypatch, intent, project=None, task=None):
    """代理 _console_import: session.query_engine 的 parse_intent_llm 返回指定意图。"""
    orig = _adapter._console_import
    real = orig("session.query_engine")

    class _Proxy:
        def __getattr__(self, name):
            if name == "parse_intent_llm":
                return lambda q, llm: {"intent": intent, "project": project, "task": task}
            return getattr(real, name)

    def proxy(name):
        if name == "session.query_engine":
            return _Proxy()
        return orig(name)

    monkeypatch.setattr(_adapter, "_console_import", proxy)


def _send(client, message):
    r = client.post("/api/sessions", json={"scope": "company"})
    sid = r.json()["id"]
    return client.post(f"/api/sessions/{sid}/messages", json={"message": message})


@requires_fastapi
class TestSessionWebuiBridge:
    def test_create_idea(self, app, monkeypatch):
        c = app["client"]
        svc = app["service"]
        proj = app["proj"]
        _patch_intent(monkeypatch, "create_idea", project=proj.name, task="语音速记")
        r = _send(c, "记录个想法：做一个语音速记")
        assert r.status_code == 200, r.text
        assert r.json()["meta"]["intent"] == "create_idea"
        backlog = svc.list_backlog(proj.id) or {}
        ideas = [f for f in backlog["features"] if f.get("maturity") == "idea"]
        assert ideas and "语音速记" in ideas[0]["name"]

    def test_task_action_complete(self, app, monkeypatch):
        c = app["client"]
        svc = app["service"]
        proj = app["proj"]
        task = app["task"]
        _patch_intent(monkeypatch, "task_action", project=proj.name, task="语音记账")
        r = _send(c, "把 语音记账 任务标记完成")
        assert r.status_code == 200, r.text
        assert svc.get_task(proj.id, task["id"])["status"] == "done"

    def test_task_action_priority(self, app, monkeypatch):
        c = app["client"]
        svc = app["service"]
        proj = app["proj"]
        task = app["task"]
        _patch_intent(monkeypatch, "task_action", project=proj.name, task="语音记账")
        r = _send(c, "把 语音记账 改成 P0")
        assert r.status_code == 200, r.text
        assert svc.get_task(proj.id, task["id"])["priority"] == "P0"

    def test_project_action_star(self, app, monkeypatch):
        c = app["client"]
        svc = app["service"]
        proj = app["proj"]
        _patch_intent(monkeypatch, "project_action", project=proj.name)
        r = _send(c, "收藏这个项目")
        assert r.status_code == 200, r.text
        p = next(pp for pp in svc.list_projects() if pp.id == proj.id)
        assert getattr(p, "starred", False)

    def test_project_artifacts(self, app, monkeypatch):
        c = app["client"]
        proj = app["proj"]
        _patch_intent(monkeypatch, "project_artifacts", project=proj.name)
        r = _send(c, "项目产出物有哪些")
        assert r.status_code == 200, r.text
        # 分发正确 (测试环境 LLM 挂 → fallback 文案, 但意图已处理无 500)
        assert r.json()["meta"]["intent"] == "project_artifacts"
        assert r.json()["assistant"]["content"]

    def test_monitor(self, app, monkeypatch):
        c = app["client"]
        proj = app["proj"]
        _patch_intent(monkeypatch, "monitor", project=proj.name)
        r = _send(c, "系统监控怎么样")
        assert r.status_code == 200, r.text
        assert r.json()["meta"]["intent"] == "monitor"

    def test_task_continue_anchor(self, app, monkeypatch):
        """T-1: 说'继续做 XX' → 定位任务 + 会话锚定 task_id + 任务详情。"""
        c = app["client"]
        svc = app["service"]
        proj = app["proj"]
        task = app["task"]
        _patch_intent(monkeypatch, "task_continue", project=proj.name, task="语音记账")
        r = c.post("/api/sessions", json={"scope": "project", "project_id": proj.id})
        sid = r.json()["id"]
        r = c.post(f"/api/sessions/{sid}/messages", json={"message": "继续做 语音记账"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["meta"]["intent"] == "task_continue"
        # 会话已锚定 task_id (T-1 核心副作用: 跨会话继续的任务锚点)
        assert body["session"]["task_id"] == task["id"]

    def test_task_context_injected(self, app, monkeypatch):
        """T-2: 任务上下文注入 (状态/历史/下一步/exec绑定)。"""
        c = app["client"]
        svc = app["service"]
        proj = app["proj"]
        task = app["task"]
        # 锚定任务会话 → 发消息不破坏
        r = c.post("/api/sessions", json={"scope": "project", "project_id": proj.id, "task_id": task["id"]})
        sid = r.json()["id"]
        assert r.json()["task_id"] == task["id"]
        r = c.post(f"/api/sessions/{sid}/messages", json={"message": "继续聊聊这个任务"})
        assert r.status_code == 200, r.text
        # helper: 任务上下文块 (状态/下一步)
        block = _adapter._task_context_facts(svc, proj.id, task["id"])
        assert block is not None
        assert "当前任务" in block and "语音记账" in block
        assert "下一步" in block and "状态" in block

    def test_settings(self, app, monkeypatch):
        c = app["client"]
        proj = app["proj"]
        _patch_intent(monkeypatch, "settings", project=proj.name)
        r = _send(c, "查看设置")
        assert r.status_code == 200, r.text
        assert r.json()["meta"]["intent"] == "settings"
