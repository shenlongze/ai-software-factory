"""tests/console/test_external_executor.py — M1 外部执行器通用适配层。

设计依据: docs/sprint10/外部执行器通用适配层-设计.md §4-§5。
覆盖:
- schema: 适配器校验 (缺 {prompt} 拒绝 / 非法 project_dir 拒绝 / id 非法拒绝)
- registry: 内置 codex/claude/hermes + 用户 yaml 覆盖/新增
- executor: discover (PATH/路径) / probe (诚实) / build_invocation (占位符+转义)
- run: 委派执行 (mock subprocess), project_dir cwd/flag 两种模式
- HTTP: GET/POST/DELETE /api/external-ai + scan/probe/run
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

_schema = importlib.import_module("factory-console.external_executor.schema")
_reg = importlib.import_module("factory-console.external_executor.registry")
_exec = importlib.import_module("factory-console.external_executor.executor")
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")

try:
    from fastapi.testclient import TestClient  # noqa: E402

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi 未安装")


def _minimal_adapter(**over):
    base = {
        "id": "fake", "name": "Fake", "binary": "fake",
        "discovery": ["/usr/local/bin"],
        "invocation": {"non_interactive": ["-z", "{prompt}"], "project_dir": "cwd"},
    }
    base.update(over)
    return _schema.ExternalExecutorAdapter(**base)


class TestSchema:
    def test_requires_prompt_placeholder(self):
        with pytest.raises(Exception):
            _schema.ExternalExecutorAdapter(
                id="x", name="x", binary="x",
                invocation={"non_interactive": ["echo", "hi"], "project_dir": "cwd"},
            )

    def test_invalid_project_dir(self):
        with pytest.raises(Exception):
            _schema.ExternalExecutorAdapter(
                id="x", name="x", binary="x",
                invocation={"non_interactive": ["{prompt}"], "project_dir": "bogus"},
            )

    def test_invalid_id(self):
        with pytest.raises(Exception):
            _schema.ExternalExecutorAdapter(
                id="bad id", name="x", binary="x",
                invocation={"non_interactive": ["{prompt}"], "project_dir": "cwd"},
            )

    def test_flag_project_dir_ok(self):
        a = _schema.ExternalExecutorAdapter(
            id="codex", name="x", binary="x",
            invocation={"non_interactive": ["exec", "{prompt}"], "project_dir": "flag:-C"},
        )
        assert a.invocation.project_dir == "flag:-C"


class TestRegistry:
    def test_builtin_three(self, tmp_path):
        r = _reg.build_registry(tmp_path)
        ids = {a.id for a in r.list()}
        assert {"codex", "claude", "hermes"} <= ids

    def test_user_yaml_overrides_and_adds(self, tmp_path):
        r = _reg.build_registry(tmp_path)
        # 新增用户适配器
        a = _minimal_adapter(id="openclaw", name="OpenClaw", binary="openclaw")
        r.save(a)
        r2 = _reg.build_registry(tmp_path)  # 重载
        assert r2.get("openclaw") is not None
        assert r2.get("openclaw").name == "OpenClaw"
        # 删除
        assert r2.remove("openclaw") is True
        assert _reg.build_registry(tmp_path).get("openclaw") is None


class TestExecutor:
    def test_discover_path_and_dir(self, tmp_path, monkeypatch):
        fake_bin = tmp_path / "fake"
        fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
        fake_bin.chmod(0o755)
        monkeypatch.setattr(_exec.shutil, "which", lambda name: None)
        a = _minimal_adapter(discovery=[str(tmp_path)])
        assert _exec.discover_binary(a) == str(fake_bin)
        # PATH
        a2 = _minimal_adapter(discovery=["PATH"])
        monkeypatch.setattr(_exec.shutil, "which", lambda name: "/usr/bin/fake")
        assert _exec.discover_binary(a2) == "/usr/bin/fake"

    def test_probe_honest(self, monkeypatch):
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            class R:
                returncode = 0
                stdout = "Fake v1.0\n"
                stderr = ""
            return R()

        monkeypatch.setattr(_exec.subprocess, "run", fake_run)
        a = _minimal_adapter()
        pr = _exec.probe(a, "/usr/bin/fake")
        assert pr["ok"] is True
        assert "Fake v1.0" in pr["version"]

    def test_build_invocation_flag_project_dir(self):
        a = _schema.ExternalExecutorAdapter(
            id="codex", name="x", binary="x",
            invocation={"non_interactive": ["exec", "{prompt}"], "project_dir": "flag:-C"},
        )
        cmd = _exec.build_invocation(a, "hello", "/tmp/p")
        assert cmd == ["exec", "hello", "-C", "/tmp/p"]

    def test_build_invocation_cwd_and_agent(self):
        a = _schema.ExternalExecutorAdapter(
            id="claude", name="x", binary="x",
            invocation={"non_interactive": ["-p", "{prompt}"], "project_dir": "cwd",
                        "agent_flag": ["--agent", "{agent}"]},
        )
        cmd = _exec.build_invocation(a, "hi", "/tmp/p", agent="arch")
        assert cmd == ["-p", "hi", "--agent", "arch"]

    def test_run_mock(self, tmp_path, monkeypatch):
        captured: dict[str, Any] = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["cwd"] = kwargs.get("cwd")
            class R:
                returncode = 0
                stdout = "done\n"
                stderr = ""
            return R()

        monkeypatch.setattr(_exec.subprocess, "run", fake_run)
        monkeypatch.setattr(_exec.shutil, "which", lambda name: "/usr/bin/fake")
        a = _minimal_adapter(discovery=["PATH"])
        r = _exec.run(a, "hi", project_dir=str(tmp_path))
        assert r["exit_code"] == 0 and r["output"] == "done\n"
        assert captured["cmd"][0] == "/usr/bin/fake"  # 二进制路径必须在前 (防 -p 被当可执行)
        assert captured["cwd"] == str(tmp_path)  # cwd 模式 + 目录存在 → 用 cwd


@requires_fastapi
class TestExternalAiHttp:
    def _app(self, tmp_path):
        service = _adapter.build_console_service(tmp_path, event_logger=None)
        return _adapter.build_app(service, event_logger=None, factory_root=tmp_path)

    def test_list_and_save_custom(self, tmp_path):
        with TestClient(self._app(tmp_path)) as c:
            r = c.get("/api/external-ai")
            assert r.status_code == 200, r.text
            ids = [a["id"] for a in r.json()["adapters"]]
            assert "codex" in ids and "claude" in ids and "hermes" in ids
            # 保存自定义适配器
            r = c.post("/api/external-ai", json={
                "id": "openclaw", "name": "OpenClaw", "binary": "openclaw",
                "invocation": {"non_interactive": ["-z", "{prompt}"], "project_dir": "cwd"},
            })
            assert r.status_code == 200, r.text
            r = c.get("/api/external-ai")
            assert any(a["id"] == "openclaw" and not a["builtin"] for a in r.json()["adapters"])
            # 非法 → 400
            r = c.post("/api/external-ai", json={"id": "bad", "binary": "b"})
            assert r.status_code == 400, r.text
            # 删除自定义
            r = c.delete("/api/external-ai/openclaw")
            assert r.status_code == 200
            # 内置不可删
            r = c.delete("/api/external-ai/codex")
            assert r.status_code == 404

    def test_scan_and_probe(self, tmp_path):
        with TestClient(self._app(tmp_path)) as c:
            r = c.post("/api/external-ai/scan", json={})
            assert r.status_code == 200, r.text
            assert r.json()["count"] >= 3
            r = c.post("/api/external-ai/codex/probe", json={})
            assert r.status_code == 200, r.text
            assert "id" in r.json()
