"""runtime/manager.py — RuntimeManager (进程生命周期, 实例配置)。

设计依据: phase15-runtime-design.md §1.2/§1.3/§1.6:

- 启动: 顺序 (Core → Console), 健康检查通过才报 READY
- 停止: 逆序 graceful (Console → Core), 超时强杀
- 崩溃: watchdog (runtime/watchdog.py) 检测退出码 → 自动重启 (最多 N 次)
- 状态: status → dict (pid/port/status/version/timestamps + 活进程)

架构调整 (用户确认):
- 实例配置 RuntimeManager(data_root, factory_cmd, console_port)
- 不修改 Console 实现 token middleware — 安全范围 = localhost binding +
  runtime token 文件生成 (600, 日志脱敏); 完整 API Authentication 属 Phase 18
- watchdog 独立模块, 不膨胀本文件

子进程: Core = factory CLI (设计 §1.2); Console = uvicorn fastapi_adapter
(设计 §1.3, 默认命令模板可被 console_cmd 覆盖; 测试注入 fake 脚本)。
"""

from __future__ import annotations

import os
import secrets
import shlex
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import __version__ as _pkg_version
from .errors import RuntimeError
from .health import check_console, check_core, wait_healthy
from .logging import (
    CONSOLE_LOG,
    CORE_LOG,
    log_event,
    open_child_log,
    setup_runtime_logger,
)
from .paths import ensure_data_root, chmod, FILE_MODE
from .state import RUNNING_STATUSES, RuntimeState, load_state, save_state

#: 默认 Console 启动命令 (uvicorn + factory-console fastapi_adapter, 127.0.0.1 回环)
_DEFAULT_CONSOLE_TEMPLATE = (
    "{python} -m uvicorn --host 127.0.0.1 --port {port} "
    "--app-dir {console_dir} --factory fastapi_adapter:create_app"
)

#: 默认 Console 目录 (相对本包: <repo>/factory-console/web/backend)
_CONSOLE_DIR = str(Path(__file__).resolve().parents[2] / "factory-console" / "web" / "backend")

#: token 文件相对数据根 (600)
TOKEN_RELPATH = Path("config") / "runtime_token"


def _normalize_cmd(cmd: str | list[str]) -> list[str]:
    """命令归一: str → shlex.split; list → 原样拷贝。"""
    if isinstance(cmd, str):
        return shlex.split(cmd)
    return list(cmd)


def _pick_free_port() -> int:
    """绑定 127.0.0.1:0 取系统分配端口 (启动竞态可接受, 健康检查兜底)。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _mask(token: str) -> str:
    """token 脱敏 (日志只留前 8 字符)。"""
    return f"{token[:8]}…" if token else ""


def _pid_alive(pid: int | None) -> bool:
    """pid 存活探测 (跨进程 status/start 兜底)。"""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class RuntimeManager:
    """工厂 Runtime 进程管理器 (Core + Console 子进程生命周期)。"""

    def __init__(
        self,
        data_root: str | Path,
        factory_cmd: str | list[str] = "factory",
        console_cmd: str | list[str] | None = None,
        console_port: int = 0,
        *,
        health_timeout: float = 15.0,
        health_interval: float = 0.5,
        terminate_timeout: float = 5.0,
        max_restarts: int = 3,
        watchdog_interval: float = 1.0,
        version: str | None = None,
    ) -> None:
        self.data_root = Path(data_root).expanduser()
        self.factory_cmd = _normalize_cmd(factory_cmd)
        #: Console 命令; None → 默认 uvicorn 模板; 支持 {port} 占位符
        self.console_cmd = _normalize_cmd(console_cmd) if console_cmd else None
        self.console_port = int(console_port)
        self.health_timeout = float(health_timeout)
        self.health_interval = float(health_interval)
        self.terminate_timeout = float(terminate_timeout)
        self.max_restarts = int(max_restarts)
        self.watchdog_interval = float(watchdog_interval)
        self.version = version or _pkg_version

        self._core_proc: subprocess.Popen | None = None
        self._console_proc: subprocess.Popen | None = None
        self._core_log_fh = None
        self._console_log_fh = None
        self._watchdog = None  # 延迟导入 runtime.watchdog
        self._token: str | None = None

    # ------------------------------------------------------------- 生命周期

    def start(self) -> dict:
        """启动: 数据根/token → Core → Console → 健康等待 → ready。

        失败 (健康超时 / Core 启动期退出) → 清理子进程, 状态 failed, 抛 RuntimeError。
        """
        state = load_state(self.data_root)
        if state.status in RUNNING_STATUSES and _pid_alive(state.pid):
            raise RuntimeError(f"already running (status={state.status}, pid={state.pid})")
        if state.status == "stopping":
            raise RuntimeError("already stopping")

        ensure_data_root(self.data_root)
        logger = setup_runtime_logger(self.data_root)
        self._token = self._write_token()
        log_event(logger, "start", f"data_root={self.data_root} token={_mask(self._token)}")

        state.status = "starting"
        state.pid = os.getpid()
        state.started_at = _now_iso()
        state.stopped_at = None
        state.version = self.version
        save_state(state, self.data_root)

        try:
            self._start_core()
            self._start_console()
            state.port = self.console_port
            save_state(state, self.data_root)

            base_url = f"http://127.0.0.1:{self.console_port}"
            try:
                wait_healthy(
                    lambda: check_console(base_url, timeout=2.0),
                    self.health_timeout,
                    self.health_interval,
                )
            except RuntimeError as exc:
                raise self._fail("health timeout", str(exc)) from exc

            alive, code = check_core(self._core_proc)
            if not alive:
                raise self._fail("startup failed", f"core exited during startup (code={code})")

            state.status = "ready"
            save_state(state, self.data_root)
            log_event(logger, "started", f"console=http://127.0.0.1:{self.console_port}")
            self._start_watchdog()
        except RuntimeError:
            self._cleanup_children()
            raise
        except Exception as exc:  # 防御兜底: 未知异常 → 域错误 + 清理
            self._cleanup_children()
            raise RuntimeError(f"start failed: {exc}") from exc
        return self.status()

    def stop(self) -> dict:
        """停止: watchdog 先停 → 逆序 graceful (Console → Core) → stopped。

        幂等: 未运行 (idle/stopped + 无子进程 + 无 pid 文件) → 记 not running。
        跨进程视角 (CLI): 本实例无 proc 引用时, 按 config/{core,console}.pid
        终止孤儿子进程 (状态文件不含子进程 pid, 设计字段契约保持 6 键)。
        """
        state = load_state(self.data_root)
        logger = setup_runtime_logger(self.data_root)
        console_pid = self._read_pid_file("console")
        core_pid = self._read_pid_file("core")
        if (
            self._core_proc is None
            and self._console_proc is None
            and not console_pid
            and not core_pid
            and state.status in ("idle", "stopped")
        ):
            log_event(logger, "stop", "not running")
            return self.status()

        if self._watchdog is not None:
            self._watchdog.stop()
            self._watchdog = None

        state.status = "stopping"
        save_state(state, self.data_root)
        log_event(logger, "stopping")

        # 逆序: Console 先, Core 后 (设计 §1.6)
        self._terminate_one(self._console_proc, console_pid, self.terminate_timeout)
        self._terminate_one(self._core_proc, core_pid, self.terminate_timeout)
        self._core_proc = None
        self._console_proc = None
        self._remove_pid_file("console")
        self._remove_pid_file("core")
        self._close_child_logs()

        state.status = "stopped"
        state.stopped_at = _now_iso()
        save_state(state, self.data_root)
        log_event(logger, "stopped")
        return self.status()

    def restart(self) -> dict:
        """stop + start (watchdog 重启计数随新 start 重置)。"""
        self.stop()
        return self.start()

    def status(self) -> dict:
        """状态: state 文件 + 活进程 (本进程 proc 优先, 跨进程 pid 文件兜底)。"""
        state = load_state(self.data_root)
        core_alive, core_code = check_core(self._core_proc)
        console_alive, console_code = check_core(self._console_proc)
        if self._core_proc is None:
            core_alive = _pid_alive(self._read_pid_file("core")) or (
                state.status in RUNNING_STATUSES and _pid_alive(state.pid)
            )
        if self._console_proc is None:
            console_alive = _pid_alive(self._read_pid_file("console"))
        result = state.to_dict()
        result["core_alive"] = core_alive
        result["console_alive"] = console_alive
        result["core_exit_code"] = core_code
        result["console_exit_code"] = console_code
        return result

    # ------------------------------------------------------- watchdog 协作 API

    @property
    def core_proc(self) -> subprocess.Popen | None:
        return self._core_proc

    @property
    def console_proc(self) -> subprocess.Popen | None:
        return self._console_proc

    def restart_process(self, name: str) -> None:
        """watchdog 专用: 重启单个子进程 (不重跑完整生命周期/健康等待)。"""
        if name == "core":
            self._start_core()
        elif name == "console":
            self._start_console()
        else:
            raise ValueError(f"unknown process: {name}")

    def mark_failed(self, reason: str) -> None:
        """状态置 failed + 事件记录 (watchdog 超限/重启失败调用)。"""
        state = load_state(self.data_root)
        state.status = "failed"
        save_state(state, self.data_root)
        log_event(setup_runtime_logger(self.data_root), "failed", reason)

    # ------------------------------------------------------------- 内部实现

    def _write_token(self) -> str:
        """生成 runtime token (随机 64 hex), 写 config/runtime_token (600)。"""
        token = secrets.token_hex(32)
        path = self.data_root / TOKEN_RELPATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(token + "\n")
        chmod(path, FILE_MODE)
        return token

    def _start_core(self) -> None:
        self._close_core_log()
        core_log = open_child_log(self.data_root, CORE_LOG)
        self._core_log_fh = open(core_log, "ab")
        self._core_proc = subprocess.Popen(
            self.factory_cmd,
            stdout=self._core_log_fh,
            stderr=subprocess.STDOUT,
            cwd=str(self.data_root),
        )
        self._write_pid_file("core", self._core_proc.pid)
        log_event(
            setup_runtime_logger(self.data_root),
            "core started",
            f"pid={self._core_proc.pid}",
        )

    def _start_console(self) -> None:
        if self.console_port == 0:
            self.console_port = _pick_free_port()
        cmd = self._console_cmd_for_port()
        self._close_console_log()
        console_log = open_child_log(self.data_root, CONSOLE_LOG)
        self._console_log_fh = open(console_log, "ab")
        self._console_proc = subprocess.Popen(
            cmd,
            stdout=self._console_log_fh,
            stderr=subprocess.STDOUT,
            cwd=str(self.data_root),
        )
        self._write_pid_file("console", self._console_proc.pid)
        log_event(
            setup_runtime_logger(self.data_root),
            "console started",
            f"pid={self._console_proc.pid} port={self.console_port}",
        )

    def _console_cmd_for_port(self) -> list[str]:
        if self.console_cmd is not None:
            return [part.replace("{port}", str(self.console_port)) for part in self.console_cmd]
        template = _DEFAULT_CONSOLE_TEMPLATE.format(
            python=sys.executable,
            port=self.console_port,
            console_dir=_CONSOLE_DIR,
        )
        return shlex.split(template)

    def _start_watchdog(self) -> None:
        from .watchdog import Watchdog  # 延迟导入 (watchdog 独立模块)

        self._watchdog = Watchdog(
            self,
            max_restarts=self.max_restarts,
            poll_interval=self.watchdog_interval,
            logger=setup_runtime_logger(self.data_root),
        )
        self._watchdog.start()

    def _terminate(self, proc: subprocess.Popen | None, timeout: float) -> None:
        """graceful (SIGTERM) → 超时强杀 (SIGKILL)。"""
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()  # POSIX SIGTERM; Windows TerminateProcess (Phase 15 打包再细化)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)

    def _terminate_one(
        self,
        proc: subprocess.Popen | None,
        pid: int | None,
        timeout: float,
    ) -> None:
        """终止单个子进程: 有 proc 引用 → proc 路径; 否则按 pid 文件路径。"""
        if proc is not None:
            self._terminate(proc, timeout)
        else:
            self._terminate_pid(pid, timeout)

    def _terminate_pid(self, pid: int | None, timeout: float) -> None:
        """跨进程终止: SIGTERM → 轮询 → SIGKILL (pid 复用风险可接受)。"""
        if not pid or not _pid_alive(pid):
            return
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not _pid_alive(pid):
                return
            time.sleep(0.05)
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    # ------------------------------------------------------------- pid 文件

    def _pid_path(self, name: str) -> Path:
        return self.data_root / "config" / f"{name}.pid"

    def _write_pid_file(self, name: str, pid: int) -> None:
        """写子进程 pid 文件 (600) — CLI 跨进程 stop/status 依据。"""
        path = self._pid_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(f"{pid}\n", encoding="utf-8")
        os.replace(tmp, path)
        chmod(path, FILE_MODE)

    def _read_pid_file(self, name: str) -> int | None:
        try:
            return int(self._pid_path(name).read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def _remove_pid_file(self, name: str) -> None:
        try:
            self._pid_path(name).unlink()
        except OSError:
            pass

    def _cleanup_children(self) -> None:
        self._terminate_one(
            self._console_proc, self._read_pid_file("console"), self.terminate_timeout
        )
        self._terminate_one(
            self._core_proc, self._read_pid_file("core"), self.terminate_timeout
        )
        self._core_proc = None
        self._console_proc = None
        self._remove_pid_file("console")
        self._remove_pid_file("core")
        self._close_child_logs()

    def _close_core_log(self) -> None:
        if self._core_log_fh is not None:
            try:
                self._core_log_fh.close()
            except OSError:
                pass
            self._core_log_fh = None

    def _close_console_log(self) -> None:
        if self._console_log_fh is not None:
            try:
                self._console_log_fh.close()
            except OSError:
                pass
            self._console_log_fh = None

    def _close_child_logs(self) -> None:
        self._close_core_log()
        self._close_console_log()

    def _fail(self, event: str, detail: str) -> RuntimeError:
        """状态 → failed + 事件 + 返回域错误 (供 raise self._fail(...))。"""
        state = load_state(self.data_root)
        state.status = "failed"
        save_state(state, self.data_root)
        log_event(setup_runtime_logger(self.data_root), event, detail)
        return RuntimeError(f"{event}: {detail}")
