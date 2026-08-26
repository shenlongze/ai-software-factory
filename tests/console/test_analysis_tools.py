"""tests/console/test_analysis_tools.py — 会话工具调用 (v1.1.166)。

Founder: 会话"详细分析"必须调专业工具, 结论可溯源, 不靠 LLM 脑补。
覆盖:
- run_analysis: 工具真实执行 (scan/list_tasks/git_status) → 证据块带来源
- list_tasks: 按优先级过滤
- deep_analyze 意图触发 (优先于 任务/文档 等泛词)
- HTTP: deep_analyze 分发 (证据注入 facts)
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
_qe = importlib.import_module("factory-console.session.query_engine")
_at = importlib.import_module("factory-console.session.analysis_tools")


def _seed(root: Path):
    """建 workspace + backlog 任务 (2 个 P0 + 1 个 P2)。"""
    pdir = root / "workspace" / "projects" / "p" / "management" / "backlog"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "task.json").write_text(
        '{"tasks": {"A": {"id":"A","title":"会话继续意图","status":"todo","priority":"P0"},'
        ' "B": {"id":"B","title":"上下文注入","status":"done","priority":"P0"},'
        ' "C": {"id":"C","title":"双轨对齐","status":"todo","priority":"P2"}}}',
        encoding="utf-8",
    )


class TestAnalysisTools:
    def test_list_tasks_by_priority(self, tmp_path):
        _seed(tmp_path)
        tasks = _at.list_tasks(tmp_path, "p", priority="P0")
        assert len(tasks) == 2
        assert all(t["priority"] == "P0" for t in tasks)
        assert {t["id"] for t in tasks} == {"A", "B"}

    def test_run_analysis_evidence(self, tmp_path):
        _seed(tmp_path)
        ev = _at.run_analysis(tmp_path, "p", "详细分析一下P0任务")
        assert "【工具 · list_tasks(P0)】" in ev
        assert "会话继续意图" in ev
        assert "任务树" in ev  # scan_project 证据
        # tmp 无 git 仓库 → git_status 诚实不追加 (不强制)

    def test_deep_analyze_intent_priority(self):
        assert _qe.parse_intent("你可以帮忙详细分析一下P0任务")["intent"] == "deep_analyze"
        assert _qe.parse_intent("分析一下当前项目状态")["intent"] == "deep_analyze"
        assert _qe.parse_intent("有哪些任务")["intent"] == "project_tasks"


try:
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except Exception:  # noqa: BLE001
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi 未安装")


@requires_fastapi
class TestDeepAnalyzeHttp:
    def test_deep_analyze_dispatch(self, tmp_path, monkeypatch):
        _seed(tmp_path)
        service = _adapter.build_console_service(tmp_path, event_logger=None)
        app = _adapter.build_app(service, event_logger=None, factory_root=tmp_path)
        proj = service.create_project("分析演示", name="分析项目")
        # patch intent: deep_analyze
        orig = _adapter._console_import
        real = orig("session.query_engine")

        class _Proxy:
            def __getattr__(self, name):
                if name == "parse_intent_llm":
                    return lambda q, llm: {"intent": "deep_analyze", "project": proj.name, "task": None}
                return getattr(real, name)

        monkeypatch.setattr(
            _adapter, "_console_import",
            lambda name: _Proxy() if name == "session.query_engine" else orig(name),
        )
        with TestClient(app) as c:
            r = c.post("/api/sessions", json={"scope": "company"})
            sid = r.json()["id"]
            r = c.post(f"/api/sessions/{sid}/messages", json={"message": "详细分析一下任务"})
        assert r.status_code == 200, r.text
        assert r.json()["meta"]["intent"] == "deep_analyze"
        assert r.json()["meta"]["data_source"] == "tools"
