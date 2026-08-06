"""tests/factory_runtime/test_frt_health.py — health 模块。

架构裁决 B: ServiceHealth (长期组件) vs CommandHealth (短命令) 明确区分。
重点: /api/dashboard 200 判定 / check_process / service_health /
command_health (命令可用性) / wait_healthy 超时抛 RuntimeError。
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from frt_helpers import wait_until


class _OKHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"ok": true}'
        self.send_response(200 if self.path == "/api/dashboard" else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args, **kwargs):
        pass


class _SlowHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(1.0)
        body = b"{}"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args, **kwargs):
        pass


@pytest.fixture
def live_server(tmp_path: Path):
    server = HTTPServer(("127.0.0.1", 0), _OKHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join(timeout=2)


@pytest.fixture
def slow_server(tmp_path: Path):
    server = HTTPServer(("127.0.0.1", 0), _SlowHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join(timeout=2)


def test_check_console_ok(rt_pkg, live_server):
    assert rt_pkg.health.check_console(live_server, timeout=2.0) is True


def test_check_console_404_false(rt_pkg, live_server):
    # 错误路径 → 404 → False
    assert rt_pkg.health.check_console(live_server + "/wrong", timeout=2.0) is False


def test_check_console_connection_refused_false(rt_pkg):
    assert rt_pkg.health.check_console("http://127.0.0.1:1", timeout=1.0) is False


def test_check_console_timeout_false(rt_pkg, slow_server):
    assert rt_pkg.health.check_console(slow_server, timeout=0.2) is False


def test_check_process_alive(rt_pkg):
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        alive, code = rt_pkg.health.check_process(proc)
        assert alive is True
        assert code is None
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_check_process_exited_code(rt_pkg):
    proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(3)"])
    proc.wait(timeout=5)
    alive, code = rt_pkg.health.check_process(proc)
    assert alive is False
    assert code == 3


def test_check_process_none(rt_pkg):
    alive, code = rt_pkg.health.check_process(None)
    assert alive is False
    assert code is None


# ------------------------------------------------------------ ServiceHealth

def test_service_health_alive(rt_pkg):
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        h = rt_pkg.health.service_health("console", proc)
        assert h.name == "console"
        assert h.alive is True
        assert h.checked_at
        d = h.to_dict()
        assert d["name"] == "console" and d["alive"] is True
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_service_health_down_for_none(rt_pkg):
    h = rt_pkg.health.service_health("console", None)
    assert h.alive is False


def test_service_health_with_http_probe(rt_pkg, live_server):
    """ServiceHealth 叠加 HTTP 探针: 进程存活 + /api/dashboard 200。"""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        h = rt_pkg.health.service_health("console", proc, base_url=live_server, timeout=2.0)
        assert h.alive is True
        assert "http=True" in h.detail
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_service_health_http_probe_down(rt_pkg, live_server):
    """进程存活但 HTTP 探针失败 → ServiceHealth alive False (服务不可用)。"""
    h = rt_pkg.health.service_health("console", None, base_url=live_server, timeout=2.0)
    assert h.alive is False
    assert "http=True" in h.detail  # probe 本身通, 但无进程


# ------------------------------------------------------------ CommandHealth

def test_command_health_available(rt_pkg):
    h = rt_pkg.health.command_health(
        "core", [sys.executable, "-c", "import sys; sys.exit(0)"], timeout=5.0
    )
    assert h.name == "core"
    assert h.available is True
    assert h.returncode == 0


def test_command_health_failure(rt_pkg):
    """命令非零退出 → available False (命令失败, 非异常)。"""
    h = rt_pkg.health.command_health(
        "core", [sys.executable, "-c", "import sys; sys.exit(7)"], timeout=5.0
    )
    assert h.available is False
    assert h.returncode == 7


def test_command_health_missing_binary(rt_pkg):
    h = rt_pkg.health.command_health("core", ["definitely-missing-bin-xyz"], timeout=2.0)
    assert h.available is False
    assert "not found" in h.detail


def test_command_health_timeout(rt_pkg):
    h = rt_pkg.health.command_health(
        "core", [sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.3
    )
    assert h.available is False
    assert "timed out" in h.detail


def test_command_health_to_dict(rt_pkg):
    h = rt_pkg.health.CommandHealth(name="core", available=True, returncode=0)
    d = h.to_dict()
    assert d["name"] == "core"
    assert d["available"] is True
    assert d["returncode"] == 0


def test_wait_healthy_immediate(rt_pkg):
    assert rt_pkg.health.wait_healthy(lambda: True, timeout=2.0, interval=0.05) is True


def test_wait_healthy_after_retries(rt_pkg):
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        return calls["n"] >= 3

    assert rt_pkg.health.wait_healthy(flaky, timeout=2.0, interval=0.05) is True
    assert calls["n"] == 3


def test_wait_healthy_timeout_raises(rt_pkg):
    with pytest.raises(rt_pkg.RuntimeError, match="timed out"):
        rt_pkg.health.wait_healthy(lambda: False, timeout=0.3, interval=0.05)


def test_wait_healthy_uses_injected_clock(rt_pkg, monkeypatch):
    """确定性时钟: 超时按 monotonic 推进, 不依赖真实时间。"""
    fake = {"t": 0.0}
    monkeypatch.setattr(rt_pkg.health.time, "monotonic", lambda: fake["t"])
    monkeypatch.setattr(rt_pkg.health.time, "sleep", lambda s: None)

    def advance():
        fake["t"] += 1.0

    result = []
    monkeypatch.setattr(
        rt_pkg.health.time,
        "sleep",
        lambda s: (advance(), None),
    )
    with pytest.raises(rt_pkg.RuntimeError):
        rt_pkg.health.wait_healthy(lambda: False, timeout=1.0, interval=0.1)
    assert fake["t"] >= 1.0
