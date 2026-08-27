"""tests/console/test_external_router.py — M5 路由层。

设计依据: 设计文档 §9。
覆盖:
- classify_task: 任务文本 → 工作类型 (架构/测试/安全/开发…)
- score_candidate: 历史加权 (4/3/2/1); 无历史 → 能力匹配分 (诚实标注 basis)
- route: 能力匹配选对 agent / 用户显式优先 / 兜底无候选 / 成本分级建议
- HTTP: POST /api/external-ai/route
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core", _ROOT / "factory-exec"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_router = importlib.import_module("factory-console.external_executor.router")
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")
_schema = importlib.import_module("factory-console.external_executor.schema")

try:
    from fastapi.testclient import TestClient  # noqa: E402

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi 未安装")


def _make_adapter(aid: str, role: str, tier: str = "medium", *, agent_flag: bool = False):
    invocation: dict = {"non_interactive": ["{prompt}"], "project_dir": "cwd"}
    if agent_flag:
        invocation["agent_flag"] = ["--agent", "{agent}"]
    return _schema.ExternalExecutorAdapter(
        id=aid, name=aid, binary=aid,
        invocation=invocation,
        capabilities={"roles": [role], "cost_tier": tier},
    )


def _seed_history(data_dir: Path):
    exec_dir = data_dir / "exec"
    exec_dir.mkdir(parents=True)
    records = [
        # architecture-examiner: 好历史 (2 pass / 1 fail)
        {"agent": "claude.architecture-examiner", "result_id": "E1", "result": "success", "first_pass": True,
         "verify": {"result": "pass"}, "cost_usd": 0.1, "duration_ms": 5000},
        {"agent": "claude.architecture-examiner", "result_id": "E2", "result": "success", "first_pass": True,
         "verify": {"result": "pass"}, "cost_usd": 0.1, "duration_ms": 4000},
        {"agent": "claude.architecture-examiner", "result_id": "E3", "result": "failed", "first_pass": True,
         "verify": {"result": "unknown"}, "cost_usd": 0.05, "duration_ms": 3000},
        # developer: 差历史 (全 fail)
        {"agent": "codex", "result_id": "E4", "result": "failed", "first_pass": False,
         "verify": {"result": "fail"}, "cost_usd": 0.5, "duration_ms": 90000},
        {"agent": "codex", "result_id": "E5", "result": "failed", "first_pass": False,
         "verify": {"result": "fail"}, "cost_usd": 0.5, "duration_ms": 90000},
    ]
    (exec_dir / "execution_records.json").write_text(json.dumps(records), encoding="utf-8")


class TestClassify:
    def test_work_types(self):
        assert _router.classify_task("帮我审查一下这个架构") == "arch"
        assert _router.classify_task("写 100 个单元测试") == "test"
        assert _router.classify_task("做一次安全渗透测试") == "security"
        assert _router.classify_task("实现登录接口") == "backend"
        assert _router.classify_task("随便聊聊") == "developer"  # 兜底


class TestScore:
    def test_history_weighting(self, tmp_path):
        _seed_history(tmp_path)
        good = _router.score_candidate(
            {"key": "claude.architecture-examiner", "role": "architect", "cost_tier": "medium"},
            "arch", tmp_path,
        )
        bad = _router.score_candidate(
            {"key": "codex", "role": "developer", "cost_tier": "medium"},
            "arch", tmp_path,
        )
        # 好历史 + 能力命中 → 分更高
        assert good["score"] > bad["score"]
        assert good["basis"] == "history+capability"
        assert good["history"]["runs"] == 3

    def test_no_history_capability_only(self, tmp_path):
        c = _router.score_candidate(
            {"key": "hermes", "role": "developer", "cost_tier": "medium"},
            "developer", tmp_path,
        )
        assert c["basis"] == "capability-only (无历史, 诚实)"
        assert c["history"]["runs"] == 0


class TestRoute:
    def test_pick_by_capability_and_history(self, tmp_path):
        _seed_history(tmp_path)
        adapters = [_make_adapter("codex", "developer"), _make_adapter("claude", "architect")]
        imported = [{"id": "claude.architecture-examiner", "name": "架构审查", "role": "architect", "source": "claude"},
                    {"id": "codex.backend-dev", "name": "后端", "role": "backend", "source": "codex"}]
        r = _router.route("帮忙审查系统架构", adapters, imported, tmp_path)
        assert r["work_type"] == "arch"
        assert r["pick"] == "claude.architecture-examiner"  # 能力命中 + 好历史
        assert r["tier_advice"] == "medium|high"

    def test_user_explicit_priority(self, tmp_path):
        _seed_history(tmp_path)
        adapters = [_make_adapter("codex", "developer"), _make_adapter("claude", "architect")]
        imported = [{"id": "codex.backend-dev", "name": "后端", "role": "backend", "source": "codex"}]
        r = _router.route("审查架构", adapters, imported, tmp_path, explicit_agent="codex.backend-dev")
        assert r["pick"] == "codex.backend-dev"
        assert r["explicit"] is True

    def test_no_candidates_fallback(self, tmp_path):
        r = _router.route("审查架构", [], [], tmp_path)
        assert r["pick"] is None
        assert r["basis"] == "fallback-no-candidates"


@requires_fastapi
class TestAutoHttp:
    def test_auto_full_loop(self, tmp_path, monkeypatch):
        """M6 自动闭环: 路由 → 委派 → 记录 (mock 执行器)。"""
        from factory_console.external_executor.registry import build_registry
        from factory_console.external_executor import executor as _ee_exec

        reg = build_registry(tmp_path)
        reg.save(_make_adapter("claude", "architect", agent_flag=True))
        (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
        (tmp_path / "agents" / "agents.json").write_text(json.dumps({"agents": {
            "claude.architecture-examiner": {"id": "claude.architecture-examiner", "name": "架构审查",
                                              "role": "architect", "source": "claude",
                                              "host": {"cli": "claude", "file": "x"}}
        }}), encoding="utf-8")

        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
                stdout = "审查报告"
                stderr = ""
            return R()

        monkeypatch.setattr(_ee_exec.subprocess, "run", fake_run)
        monkeypatch.setattr(_ee_exec.shutil, "which", lambda name: "/usr/bin/claude")
        service = _adapter.build_console_service(tmp_path, event_logger=None)
        app = _adapter.build_app(service, event_logger=None, factory_root=tmp_path)
        with TestClient(app) as c:
            r = c.post("/api/external-ai/auto", json={"task": "审查系统架构", "project_dir": "/tmp/p"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["route"]["pick"] == "claude.architecture-examiner"
            assert body["execution"]["executor_id"] == "claude"
            assert body["execution"]["host_agent"] == "architecture-examiner"
            assert body["execution"]["result_id"].startswith("EXS-")
            # 记录落盘
            records = json.loads((tmp_path / "exec" / "execution_records.json").read_text(encoding="utf-8"))
            assert any(x["result_id"] == body["execution"]["result_id"] for x in records)

    def test_auto_internal_honest(self, tmp_path):
        """选到内部员工 → 诚实标注不代跑。"""
        from factory_console.external_executor.registry import build_registry

        reg = build_registry(tmp_path)
        (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
        (tmp_path / "agents" / "agents.json").write_text(json.dumps({"agents": {
            "tester-1": {"id": "tester-1", "name": "tester-1", "role": "测试工程师"}
        }}), encoding="utf-8")
        service = _adapter.build_console_service(tmp_path, event_logger=None)
        app = _adapter.build_app(service, event_logger=None, factory_root=tmp_path)
        with TestClient(app) as c:
            r = c.post("/api/external-ai/auto", json={"task": "给登录写单元测试"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["execution"] is None
            assert "内部员工" in (body.get("note") or "")


@requires_fastapi
class TestRouteHttp:
    def test_route_endpoint(self, tmp_path):
        from factory_console.external_executor.registry import build_registry

        reg = build_registry(tmp_path)
        reg.save(_make_adapter("claude", "architect", agent_flag=True))
        # 导入一个外部 agent
        (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
        (tmp_path / "agents" / "agents.json").write_text(json.dumps({"agents": {
            "claude.architecture-examiner": {"id": "claude.architecture-examiner", "name": "架构审查",
                                              "role": "architect", "source": "claude"}
        }}), encoding="utf-8")
        service = _adapter.build_console_service(tmp_path, event_logger=None)
        app = _adapter.build_app(service, event_logger=None, factory_root=tmp_path)
        with TestClient(app) as c:
            r = c.post("/api/external-ai/route", json={"task": "审查系统架构"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["work_type"] == "arch"
            assert body["pick"] in ("claude", "claude.architecture-examiner")
            assert len(body["alternatives"]) > 0
