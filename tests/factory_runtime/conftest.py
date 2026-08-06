"""tests/factory_runtime/conftest.py — Phase 15A-1 factory-runtime 测试装配。

★ 包名冲突 (关键): factory-core/runtime/ (Phase 5A, 含 registry/store/models/
adapters) 已占用顶层名 `runtime` — 既有 tests/runtime/ 依赖 `import runtime`
解析到 factory-core/runtime。本目录**绝不**把 factory-runtime 插到 sys.path[0];
改经 importlib spec 把 factory-runtime/runtime/ 加载为唯一别名
`factory_runtime_pkg` (sys.modules 注册 + __path__ 指向真实目录), 相对导入
(manager → .state 等) 全部照常工作, 零污染既有测试。

子进程注入: fake 脚本 (写脚本文件 + [sys.executable, ...]) — 测试不依赖真实
factory/uvicorn 慢启动; fake console 是真实 HTTP 服务器 (/api/dashboard → 200),
manager 的健康等待走真实 end-to-end 路径。
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "factory-runtime" / "runtime"


def _load_runtime_pkg():
    if "factory_runtime_pkg" in sys.modules:
        return sys.modules["factory_runtime_pkg"]
    spec = importlib.util.spec_from_file_location(
        "factory_runtime_pkg",
        _RUNTIME_DIR / "__init__.py",
        submodule_search_locations=[str(_RUNTIME_DIR)],
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["factory_runtime_pkg"] = mod
    spec.loader.exec_module(mod)
    importlib.import_module("factory_runtime_pkg.cli")  # 预载 cli (rt_pkg.cli 属性)
    return mod


runtime_pkg = _load_runtime_pkg()

# --------------------------------------------------------------- fake 脚本

FAKE_CORE = """
# Core 命令执行器 fake (架构裁决 B: Core 非 daemon, 命令语义):
#   --help/-h → 0 (命令可用性检查); status → 0; echo <...> → 0 (回显);
#   fail/bogus → 2 (命令失败); 其他 → 常驻 (旧 daemon 语义测试兼容)
import sys, time
args = sys.argv[1:]
if "--help" in args or "-h" in args:
    print("fake factory core help")
    sys.exit(0)
if args and args[0] == "status":
    print("fake status: ok")
    sys.exit(0)
if args and args[0] == "echo":
    print(" ".join(args[1:]))
    sys.exit(0)
if args and args[0] in ("fail", "bogus", "badcmd"):
    print("fake core failure", file=sys.stderr)
    sys.exit(2)
time.sleep(600)
"""

FAKE_CORE_FAIL = """
# Core 命令一律失败 (exit 2) — 测"Core 命令不可用 ≠ runtime 崩溃"
import sys
sys.exit(2)
"""

FAKE_CORE_CRASH_ONCE = """
# argv[1] = marker 路径: 首次运行写 marker 后退出 1 (模拟崩溃), 之后常驻
import sys, time, pathlib
marker = pathlib.Path(sys.argv[1])
if marker.exists():
    time.sleep(600)
else:
    marker.write_text("1")
    time.sleep(0.3)
    sys.exit(1)
"""

FAKE_CORE_CRASH_LOOP = """
import sys, time
time.sleep(0.6)
sys.exit(1)
"""

FAKE_CORE_EXIT_NOW = """
import sys
sys.exit(0)
"""

FAKE_CORE_IGNORE_TERM = """
import signal, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
time.sleep(600)
"""

FAKE_CONSOLE = """
import sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
port = 8011
args = sys.argv[1:]
for i, a in enumerate(args):
    if a == "--port" and i + 1 < len(args):
        port = int(args[i + 1])
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/dashboard":
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *args):
        pass
server = HTTPServer(("127.0.0.1", port), Handler)
threading.Timer(600, server.shutdown).start()
server.serve_forever()
"""

FAKE_CONSOLE_CRASH = """
# 服务 0.6s 后退出 2 (模拟 Console 崩溃)
import sys, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
port = 8011
args = sys.argv[1:]
for i, a in enumerate(args):
    if a == "--port" and i + 1 < len(args):
        port = int(args[i + 1])
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/dashboard":
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *args):
        pass
server = HTTPServer(("127.0.0.1", port), Handler)
threading.Timer(0.6, server.shutdown).start()
server.serve_forever()
sys.exit(2)
"""

FAKE_CONSOLE_SLOW = """
# 永不监听 → 健康检查超时 (启动失败路径)
import time
time.sleep(600)
"""

FAKE_CONSOLE_CRASH_ONCE = """
# argv[1] = marker 路径: 首次运行服务 0.6s 后退出 2 (模拟崩溃), 之后常驻
import sys, threading, time, pathlib
from http.server import BaseHTTPRequestHandler, HTTPServer
marker = pathlib.Path(sys.argv[1])
port = 8011
args = sys.argv[2:]
for i, a in enumerate(args):
    if a == "--port" and i + 1 < len(args):
        port = int(args[i + 1])
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/dashboard":
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *args):
        pass
server = HTTPServer(("127.0.0.1", port), Handler)
if marker.exists():
    threading.Timer(600, server.shutdown).start()
    server.serve_forever()
else:
    marker.write_text("1")
    threading.Timer(0.6, server.shutdown).start()
    server.serve_forever()
    sys.exit(2)
"""

FAKE_CONSOLE_IGNORE_TERM = """
# 服务 HTTP + 忽略 SIGTERM → 测 stop 超时强杀 (SIGKILL)
import sys, signal, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
signal.signal(signal.SIGTERM, signal.SIG_IGN)
port = 8011
args = sys.argv[1:]
for i, a in enumerate(args):
    if a == "--port" and i + 1 < len(args):
        port = int(args[i + 1])
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/dashboard":
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *args):
        pass
server = HTTPServer(("127.0.0.1", port), Handler)
threading.Timer(600, server.shutdown).start()
server.serve_forever()
"""


def _write_script(tmp_path: Path, name: str, src: str) -> str:
    path = tmp_path / name
    path.write_text(textwrap.dedent(src), encoding="utf-8")
    return str(path)


# --------------------------------------------------------------- fixtures


@pytest.fixture(scope="session")
def rt_pkg():
    """factory_runtime_pkg 模块对象 (importlib 别名加载)。"""
    return runtime_pkg


@pytest.fixture(autouse=True)
def _reset_runtime_logger(rt_pkg):
    """每个测试后重置 runtime logger 单例 (跨测试隔离)。"""
    yield
    rt_pkg.logging.reset_runtime_logger()


@pytest.fixture
def frt_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    return root


@pytest.fixture
def fake_core_cmd(tmp_path: Path) -> list[str]:
    return [sys.executable, _write_script(tmp_path, "fake_core.py", FAKE_CORE)]

@pytest.fixture
def fake_core_fail_cmd(tmp_path: Path) -> list[str]:
    return [sys.executable, _write_script(tmp_path, "fake_core_fail.py", FAKE_CORE_FAIL)]


@pytest.fixture
def fake_core_crash_once(tmp_path: Path) -> list[str]:
    return [sys.executable, _write_script(tmp_path, "fake_core_crash_once.py", FAKE_CORE_CRASH_ONCE)]


@pytest.fixture
def fake_core_crash_loop(tmp_path: Path) -> list[str]:
    return [sys.executable, _write_script(tmp_path, "fake_core_crash_loop.py", FAKE_CORE_CRASH_LOOP)]


@pytest.fixture
def fake_core_exit_now(tmp_path: Path) -> list[str]:
    return [sys.executable, _write_script(tmp_path, "fake_core_exit_now.py", FAKE_CORE_EXIT_NOW)]


@pytest.fixture
def fake_core_ignore_term(tmp_path: Path) -> list[str]:
    return [sys.executable, _write_script(tmp_path, "fake_core_ignore.py", FAKE_CORE_IGNORE_TERM)]


@pytest.fixture
def fake_console_cmd(tmp_path: Path) -> list[str]:
    return [sys.executable, _write_script(tmp_path, "fake_console.py", FAKE_CONSOLE), "--port", "{port}"]


@pytest.fixture
def fake_console_crash_cmd(tmp_path: Path) -> list[str]:
    return [
        sys.executable,
        _write_script(tmp_path, "fake_console_crash.py", FAKE_CONSOLE_CRASH),
        "--port",
        "{port}",
    ]


@pytest.fixture
def fake_console_slow_cmd(tmp_path: Path) -> list[str]:
    return [sys.executable, _write_script(tmp_path, "fake_console_slow.py", FAKE_CONSOLE_SLOW)]

@pytest.fixture
def fake_console_crash_once_cmd(tmp_path: Path) -> list[str]:
    marker = tmp_path / "console_crash_marker"
    return [
        sys.executable,
        _write_script(tmp_path, "fake_console_crash_once.py", FAKE_CONSOLE_CRASH_ONCE),
        str(marker),
        "--port",
        "{port}",
    ]

@pytest.fixture
def fake_console_ignore_term_cmd(tmp_path: Path) -> list[str]:
    return [
        sys.executable,
        _write_script(tmp_path, "fake_console_ignore_term.py", FAKE_CONSOLE_IGNORE_TERM),
        "--port",
        "{port}",
    ]


@pytest.fixture
def manager_factory(rt_pkg):
    """RuntimeManager 工厂 + 测试后统一 stop (防子进程泄漏)。"""

    managers = []

    def _factory(root: Path, **kwargs) -> Any:
        mgr = rt_pkg.manager.RuntimeManager(root, **kwargs)
        managers.append(mgr)
        return mgr

    yield _factory
    for mgr in managers:
        try:
            mgr.stop()
        except Exception:
            pass


@pytest.fixture
def cli_root(tmp_path: Path, rt_pkg) -> Iterator[Path]:
    """CLI 测试数据根 (teardown 兜底 stop)。"""
    root = tmp_path / "cliroot"
    root.mkdir()
    yield root
    try:
        rt_pkg.manager.RuntimeManager(root).stop()
    except Exception:
        pass
