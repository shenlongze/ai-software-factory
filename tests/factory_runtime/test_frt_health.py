"""tests/factory_runtime/test_frt_health.py — health 模块 (Console HTTP/Core 进程/等待)。

重点: /api/dashboard 200 判定 / 失败安全 / wait_healthy 超时抛 RuntimeError。
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


def test_check_core_alive(rt_pkg):
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        alive, code = rt_pkg.health.check_core(proc)
        assert alive is True
        assert code is None
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_check_core_exited_code(rt_pkg):
    proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(3)"])
    proc.wait(timeout=5)
    alive, code = rt_pkg.health.check_core(proc)
    assert alive is False
    assert code == 3


def test_check_core_none(rt_pkg):
    alive, code = rt_pkg.health.check_core(None)
    assert alive is False
    assert code is None


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
