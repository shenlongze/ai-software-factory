"""tests/console/test_local_ai.py — U-6 本机 AI 发现与调度 (v1.1.188)。

Founder 2026-08-27: 扫描 codex/claude/hermes 安装 → 注册为 Agent → exec 可委派真实执行。
覆盖:
- detect_local_ais: PATH 发现 (mock which) → 记录 binary/path/版本 (探测失败 → None 诚实)
- register_local_ais: 幂等注册进 agents.json (已存在 → 刷新 path/version, 不覆盖 role/name)
- run_local_ai: 委派真实执行 (mock subprocess), 参数映射 codex/claude/hermes
- HTTP: GET /api/local-ai (只读扫描) · POST /api/local-ai/register · POST /api/local-ai/{id}/run
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_local_ai = importlib.import_module("factory-console.local_ai")
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")

try:
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except Exception:  # noqa: BLE001
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装"
)


class TestDetect:
    def test_detect_finds_installed(self, tmp_path, monkeypatch):
        fake_bin = tmp_path / "codex"
        fake_bin.write_text("#!/bin/sh\necho fake\n", encoding="utf-8")
        fake_bin.chmod(0o755)

        def fake_which(name: str):
            if name == "codex":
                return str(fake_bin)
            return None

        monkeypatch.setattr(_local_ai.shutil, "which", fake_which)
        # 版本探测: 假二进制 --version 输出 "fake" → 诚实记录
        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
                stdout = "codex fake 1.0\n"
                stderr = ""
            return R()

        monkeypatch.setattr(_local_ai.subprocess, "run", fake_run)
        found = _local_ai.detect_local_ais()
        codex = next((f for f in found if f["id"] == "local-codex"), None)
        assert codex is not None
        assert codex["path"] == str(fake_bin)
        assert codex["version"] == "codex fake 1.0"
        # 只扫描到 codex (claude/hermes which=None); 本机额外目录可能装了 → 只验 codex

    def test_detect_none_honest(self, monkeypatch):
        monkeypatch.setattr(_local_ai.shutil, "which", lambda name: None)
        monkeypatch.setattr(
            _local_ai, "_EXTRA_DIRS", ["/nonexistent-dir-xyz"]
        )
        assert _local_ai.detect_local_ais() == []


class TestRegister:
    def test_register_idempotent(self, tmp_path):
        af = tmp_path / "agents.json"
        detected = [
            {
                "id": "local-codex", "name": "本机 Codex", "role": "developer",
                "skills": ["codex"], "binary": "codex", "path": "/usr/bin/codex",
                "version": "v1.0", "description": "d",
            }
        ]
        r1 = _local_ai.register_local_ais(af, detected)
        assert len(r1) == 1 and r1[0]["id"] == "local-codex"
        # 已存在 → 刷新 path/version, 保留用户 role
        d2 = [dict(detected[0], path="/opt/codex", version="v2.0")]
        r2 = _local_ai.register_local_ais(af, d2)
        rec = json.loads(af.read_text(encoding="utf-8"))["agents"]["local-codex"]
        assert rec["path"] == "/opt/codex"
        assert rec["version"] == "v2.0"
        assert rec["role"] == "developer"


class TestRun:
    def test_run_codex_arg_mapping(self, monkeypatch):
        captured: dict[str, Any] = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["cwd"] = kwargs.get("cwd")
            class R:
                returncode = 0
                stdout = "done\n"
                stderr = ""
            return R()

        monkeypatch.setattr(_local_ai.subprocess, "run", fake_run)
        rec = {"id": "local-codex", "binary": "codex", "path": "/usr/bin/codex"}
        r = _local_ai.run_local_ai(rec, "改 bug", project_dir="/tmp/p")
        assert r["exit_code"] == 0 and r["output"] == "done\n"
        assert captured["cmd"][0] == "/usr/bin/codex"
        assert captured["cmd"][1] == "exec"
        assert "--cd" in captured["cmd"]

    def test_run_missing_binary_honest(self):
        r = _local_ai.run_local_ai({"id": "local-x", "binary": "", "path": ""}, "p")
        assert r["exit_code"] == -1
        assert "未找到" in r["error"]


@requires_fastapi
class TestLocalAiHttp:
    def _app(self, tmp_path):
        service = _adapter.build_console_service(tmp_path, event_logger=None)
        app = _adapter.build_app(service, event_logger=None, factory_root=tmp_path)
        return app

    def test_scan_read_only_and_register(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            _local_ai, "detect_local_ais",
            lambda: [{
                "id": "local-codex", "name": "本机 Codex", "role": "developer",
                "skills": ["codex"], "binary": "codex", "path": "/usr/bin/codex",
                "version": "v1", "description": "d",
            }],
        )
        with TestClient(self._app(tmp_path)) as c:
            r = c.get("/api/local-ai")
            assert r.status_code == 200
            assert r.json()["count"] == 1
            r = c.post("/api/local-ai/register")
            assert r.status_code == 200
            body = r.json()
            assert body["count"] == 1
            assert body["registered"][0]["id"] == "local-codex"
            # agents.json 已注册
            r = c.get("/api/agents")
            agents = r.json()["agents"]
            assert any(a["id"] == "local-codex" for a in agents)

    def test_run_endpoint_delegates(self, tmp_path, monkeypatch):
        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
                stdout = "real output\n"
                stderr = ""
            return R()

        monkeypatch.setattr(_local_ai.subprocess, "run", fake_run)
        (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
        (tmp_path / "agents" / "agents.json").write_text(
            json.dumps({"agents": {
                "local-codex": {
                    "id": "local-codex", "name": "本机 Codex", "role": "developer",
                    "binary": "codex", "path": "/usr/bin/codex",
                }
            }}),
            encoding="utf-8",
        )
        with TestClient(self._app(tmp_path)) as c:
            r = c.post("/api/local-ai/local-codex/run", json={"prompt": "改 bug", "project_dir": "/tmp/p"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["exit_code"] == 0
            assert body["output"] == "real output\n"
            # 不存在 → 404
            r = c.post("/api/local-ai/nope/run", json={"prompt": "x"})
            assert r.status_code == 404
