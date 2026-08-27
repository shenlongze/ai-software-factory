"""tests/console/test_external_m3.py — M3 委派+验证回路 (统一执行记录 + verify/rework)。

设计依据: 设计文档 §7-§8。
覆盖:
- record_invocation: EXS 记录 (executor/mode/host_agent/duration/first_pass/verify/rework)
  + report.md 证据包
- verify_invocation: pass → verify 回写 first_pass 保持; fail → first_pass=False + rework+1 + reason
- HTTP: run 返回 result_id + 记录落盘; POST /api/external-ai/verify 回写
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

_ee = importlib.import_module("factory-console.external_executor.executor")
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")

try:
    from fastapi.testclient import TestClient  # noqa: E402

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi 未安装")


def _records(data_dir) -> list[dict]:
    f = Path(data_dir) / "exec" / "execution_records.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


class TestRecordAndVerify:
    def test_record_invocation(self, tmp_path):
        rec = _ee.record_invocation(
            tmp_path, executor_id="claude", mode="borrowed-shell",
            host_agent="architecture-examiner", prompt="审查架构",
            project_dir="/tmp/p", exit_code=0, output="ok", error="",
            command="claude -p", duration_ms=1234, trace_id="tr-1",
        )
        assert rec["result_id"].startswith("EXS-")
        assert rec["executor_id"] == "claude"
        assert rec["mode"] == "borrowed-shell"
        assert rec["host_agent"] == "architecture-examiner"
        assert rec["first_pass"] is True
        assert rec["verify"]["result"] == "unknown"
        assert rec["rework"]["count"] == 0
        # 落盘 + 证据包
        records = _records(tmp_path)
        assert any(r["result_id"] == rec["result_id"] for r in records)
        report = tmp_path / "exec" / f"{rec['result_id']}.report.md"
        assert report.is_file() and "claude" in report.read_text()

    def test_verify_pass_keeps_first_pass(self, tmp_path):
        rec = _ee.record_invocation(tmp_path, executor_id="codex", mode="blackbox",
                                    host_agent="", prompt="p", project_dir="", exit_code=0,
                                    output="", error="", command="c", duration_ms=1)
        updated = _ee.verify_invocation(tmp_path, rec["result_id"], method="pytest",
                                        result="pass", score=0.95)
        assert updated is not None
        assert updated["verify"] == {"method": "pytest", "result": "pass", "score": 0.95}
        assert updated["first_pass"] is True
        assert updated["rework"]["count"] == 0

    def test_verify_fail_increments_rework(self, tmp_path):
        rec = _ee.record_invocation(tmp_path, executor_id="hermes", mode="blackbox",
                                    host_agent="", prompt="p", project_dir="", exit_code=0,
                                    output="", error="", command="c", duration_ms=1)
        updated = _ee.verify_invocation(tmp_path, rec["result_id"], method="test",
                                        result="fail", reason="测试挂了")
        assert updated["first_pass"] is False
        assert updated["rework"]["count"] == 1
        assert "测试挂了" in updated["rework"]["reasons"]

    def test_verify_missing_honest(self, tmp_path):
        assert _ee.verify_invocation(tmp_path, "EXS-nope", method="m", result="pass") is None


@requires_fastapi
class TestCost:
    def test_record_cost_attach(self, tmp_path):
        rec = _ee.record_invocation(tmp_path, executor_id="claude", mode="blackbox",
                                    host_agent="", prompt="p", project_dir="", exit_code=0,
                                    output="", error="", command="c", duration_ms=1,
                                    cost_usd=0.42)
        assert rec["cost_usd"] == 0.42
        # 默认 None (unknown)
        rec2 = _ee.record_invocation(tmp_path, executor_id="codex", mode="blackbox",
                                     host_agent="", prompt="p", project_dir="", exit_code=0,
                                     output="", error="", command="c", duration_ms=1)
        assert rec2["cost_usd"] is None
        # 回填成本
        updated = _ee.record_cost(tmp_path, rec2["result_id"], 0.99)
        assert updated is not None and updated["cost_usd"] == 0.99
        # 不存在 → None
        assert _ee.record_cost(tmp_path, "EXS-nope", 1.0) is None


class TestAutoVerify:
    def test_pytest_verify_test_task(self, tmp_path, monkeypatch):
        (tmp_path / "tests").mkdir(parents=True)
        (tmp_path / "pytest.ini").write_text("[pytest]", encoding="utf-8")
        captured: dict[str, Any] = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["cwd"] = kwargs.get("cwd")
            class R:
                returncode = 0
                stdout = "5 passed"
                stderr = ""
            return R()

        monkeypatch.setattr(_ee.subprocess, "run", fake_run)
        v = _ee.auto_verify(str(tmp_path), "test")
        assert v["result"] == "pass" and v["method"] == "pytest"
        assert captured["cwd"] == str(tmp_path)

    def test_verify_hook_explicit(self, tmp_path, monkeypatch):
        def fake_run(cmd, **kwargs):
            class R:
                returncode = 1
                stdout = ""
                stderr = "FAILED"
            return R()
        monkeypatch.setattr(_ee.subprocess, "run", fake_run)
        v = _ee.auto_verify(str(tmp_path), "review",
                            verify_hook={"name": "schema-check", "command": ["check", "--strict"]})
        assert v["method"] == "schema-check" and v["result"] == "fail"
        assert "FAILED" in v["reason"]

    def test_no_hook_unknown_honest(self, tmp_path):
        # 空目录 + review 任务 → 无自动钩子 → unknown
        v = _ee.auto_verify(str(tmp_path), "review")
        assert v["result"] == "unknown"
        assert "不编造" in v["reason"]


class TestM3Http:
    def _app(self, tmp_path):
        service = _adapter.build_console_service(tmp_path, event_logger=None)
        return _adapter.build_app(service, event_logger=None, factory_root=tmp_path)

    def test_run_records_and_verify(self, tmp_path, monkeypatch):
        from factory_console.external_executor.registry import build_registry

        # 注册一个用假二进制的适配器 (invoke 走 mock)
        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
                stdout = "done\n"
                stderr = ""
            return R()

        monkeypatch.setattr(_ee.subprocess, "run", fake_run)
        monkeypatch.setattr(_ee.shutil, "which", lambda name: "/usr/bin/fake")
        reg = build_registry(tmp_path)
        reg.save(reg.get("codex").model_copy(update={"discovery": ["PATH"]}))
        with TestClient(self._app(tmp_path)) as c:
            r = c.post("/api/external-ai/codex/run", json={"prompt": "hi", "project_dir": "/tmp/p"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["exit_code"] == 0
            assert body["result_id"] and body["result_id"].startswith("EXS-")
            # 记录落盘
            records = _records(tmp_path)
            assert any(x["result_id"] == body["result_id"] and x["executor_id"] == "codex" for x in records)
            # verify pass
            r = c.post("/api/external-ai/verify", json={"result_id": body["result_id"], "method": "test", "result": "pass", "score": 1.0})
            assert r.status_code == 200, r.text
            assert r.json()["verify"]["result"] == "pass"
            # verify 不存在 → 404
            r = c.post("/api/external-ai/verify", json={"result_id": "EXS-nope", "result": "pass"})
            assert r.status_code == 404
