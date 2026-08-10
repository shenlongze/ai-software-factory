"""factory-console/cli_factory.py — S10-007 阶段二: factory CLI MVP (start/stop/status)。

用户需求 (S10-007): 一条 `./bin/factory` 命令即可启动本地开发环境, 不要求
用户懂 uvicorn/vite/PYTHONPATH/npm:

    factory start   环境检查 (python ≥3.10 / node ≥18) → 依赖检查 (.venv /
                    node_modules, 缺失给 install 提示) → 配置检查 (LLM key
                    缺失仅提示 .env.example 指引, 不阻断) → 后端 (uvicorn,
                    后台, pid 文件) → 前端 (vite --strictPort, 后台, pid
                    文件) → 健康检查 (轮询 /api/projects 200) → 打开浏览器
    factory stop    读 pid 文件杀前后端 (干净); 无 pid → 按端口 (lsof) 找
    factory status  端口 / 进程 / 数据目录 / LLM provider 状态

架构预留: init/config/project/run 注册为 argparse stub (阶段三实现), 未来
可加子子命令 (project list 等) — 不限制扩展。

设计:
- 纯标准库 (argparse/subprocess/socket/urllib) — 零新增依赖。
- 模块级 IO 函数 (测试可 monkeypatch) + FactoryCLI 类 (流程编排)。
- pid 文件 / 日志: <data_dir>/run/{backend,frontend}.pid 与 *.log。
- 后端启动: importlib 加载 factory-console.web.backend.fastapi_adapter
  (包名含连字符, 唯一导入方式) → create_app(factory_root=<data_dir>) →
  uvicorn.run — bootstrap 经 base64 传给子进程, 免引号转义。
- 幂等: pid 文件 + kill(0) 判活 → 已运行提示, 不重复起。
- 错误处理: 端口预检 (占用 → 明确提示, 含修改配置指引); 启动失败 →
  打印日志尾部 + 回滚已起服务。
- 铁律: 不打印 API key 明文 (status 只显示 已配置/未配置); 不读取任何
  ~/.hermes 路径 (S10-007 P0, 同 config.py); 不修改 Core / fastapi_adapter。

basename: cli_factory.py 全仓库唯一 (tests/console 用 importlib 加载)。
"""

from __future__ import annotations

import argparse
import base64
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence

from .config import ConfigProvider

# ------------------------------------------------------------------ 常量

#: 最低 Python 版本 (环境检查)
MIN_PYTHON = (3, 10)
#: 最低 Node.js 版本 (环境检查; vite 5 要求 ≥18)
MIN_NODE = (18, 0)
#: 后端 FastAPI adapter (包名含连字符 — 唯一导入方式是 importlib)
BACKEND_MODULE = "factory-console.web.backend.fastapi_adapter"
#: 打开浏览器默认路径 (SPA 工作台)
FRONTEND_PATH = "/#/workspace"
#: pid/日志子目录 (相对数据目录)
RUN_SUBDIR = "run"
#: 后端健康检查端点 (GET → 200 即就绪)
HEALTH_PATH = "/api/projects"
#: 健康检查总超时 (秒)
HEALTH_TIMEOUT = 30.0
#: 前端就绪总超时 (秒, vite 冷启动较快)
FRONTEND_TIMEOUT = 15.0
#: 健康检查轮询间隔 (秒)
HEALTH_INTERVAL = 0.5
#: 架构预留子命令 (阶段三实现; 注册为 stub 不限制扩展)
STUB_COMMANDS = ("init", "config", "project", "run")


# ------------------------------------------------------------------ 模块级 IO (可 monkeypatch)


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """TCP 连接测试: 端口已被监听 → True (预检/status/stop 兜底共用)。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


def _capture(cmd: Sequence[str]) -> str:
    """运行命令并捕获 stdout (失败/超时/缺失 → 空串; 永不抛)。"""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except Exception:  # noqa: BLE001 — 环境探测失败安全
        return ""
    return (proc.stdout or "").strip()


def _node_version() -> tuple[int, int] | None:
    """`node --version` → (major, minor); node 缺失/解析失败 → None。"""
    out = _capture(["node", "--version"])  # 形如 v26.4.0
    if not out.startswith("v"):
        return None
    parts = out[1:].split(".")
    try:
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None


def _lsof_pids(port: int) -> list[int]:
    """lsof -ti tcp:<port> → 监听该端口的 PID 列表 (stop 兜底, 无 pid 文件时)。"""
    out = _capture(["lsof", "-ti", f"tcp:{port}"])
    return [int(line.strip()) for line in out.splitlines() if line.strip().isdigit()]


def _pid_alive(pid: int) -> bool:
    """kill(pid, 0) 判活 (进程不存在 → False; 存在 → True)。"""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _kill_pid(pid: int, grace: float = 2.0) -> None:
    """SIGTERM → 等待 grace → SIGKILL (进程已退出/无权限 → 静默容错)。"""
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _open_url(url: str) -> None:
    """打开浏览器 (macOS `open`; 其他平台打印 URL 提示手动打开)。"""
    if sys.platform == "darwin":
        subprocess.run(["open", url], check=False)
    else:
        print(f"  请手动打开浏览器: {url}")


def _read_pid(path: Path) -> int | None:
    """读 pid 文件 (缺失/损坏/非数字 → None, 失败安全)。"""
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:  # noqa: BLE001
        return None


def _write_pid(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n", encoding="utf-8")


def _http_status(url: str, timeout: float = 2.0) -> int:
    """GET url → 状态码; 网络错误/超时 → 0 (健康检查轮询用)。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:  # noqa: BLE001
        return 0


# ------------------------------------------------------------------ 检查 (环境/依赖/配置)


def _env_problems() -> list[str]:
    """环境检查: python ≥3.10 + node ≥18 (缺失/过低 → 清晰提示列表)。"""
    problems: list[str] = []
    if sys.version_info[:2] < MIN_PYTHON:
        problems.append(
            f"Python 版本过低: {sys.version_info.major}.{sys.version_info.minor}"
            f" (需要 ≥{MIN_PYTHON[0]}.{MIN_PYTHON[1]})"
        )
    node = _node_version()
    if node is None:
        problems.append(f"未找到 Node.js — 请安装 ≥{MIN_NODE[0]} (https://nodejs.org)")
    elif node < MIN_NODE:
        problems.append(f"Node.js 版本过低: {node[0]}.{node[1]} (需要 ≥{MIN_NODE[0]})")
    return problems


def _dep_problems(root: Path) -> list[str]:
    """依赖检查: .venv 存在? 前端 node_modules 存在? (缺失 → install 指引)。"""
    problems: list[str] = []
    venv_py = root / ".venv" / "bin" / "python"
    if not venv_py.is_file():
        problems.append(
            f"未找到虚拟环境: {venv_py}\n"
            "  请先安装依赖: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'"
        )
    frontend = root / "factory-console" / "web" / "frontend"
    if not (frontend / "node_modules").is_dir():
        problems.append(
            f"前端依赖缺失: {frontend / 'node_modules'}\n  请先安装: cd {frontend} && npm install"
        )
    return problems


def _config_hints(config: ConfigProvider) -> list[str]:
    """配置检查: LLM key 缺失 → .env.example 指引 (仅提示, 不阻断启动)。"""
    llm = config.get_llm()
    if llm["api_key"]:
        return []
    return [
        f"LLM API key 未配置 (provider={llm['provider']}, model={llm['model']}) — "
        "继续启动, 但项目执行功能不可用。\n"
        "  配置方法: 复制 factory-console/.env.example 为 factory-console/.env "
        "并填写 LLM_API_KEY (或编辑 ~/.factory/config.json)"
    ]


# ------------------------------------------------------------------ FactoryCLI (流程编排)


class FactoryCLI:
    """CLI 命令编排: start / stop / status (+ 预留 stub)。"""

    def __init__(self, config: ConfigProvider, *, root: Path | None = None) -> None:
        self.config = config
        # cli_factory.py 位于 <root>/factory-console/ 下 → parents[1] 即仓库根
        self.root = (root or Path(__file__).resolve().parents[1]).resolve()
        self.data_dir = config.get_data_dir()
        self.run_dir = self.data_dir / RUN_SUBDIR
        self.backend_pid = self.run_dir / "backend.pid"
        self.frontend_pid = self.run_dir / "frontend.pid"
        self.backend_log = self.run_dir / "backend.log"
        self.frontend_log = self.run_dir / "frontend.log"

    # ------------------------------------------------------------- 入口

    def run(self, args: argparse.Namespace) -> int:
        if args.command == "start":
            return self.start(
                no_browser=args.no_browser,
                port=args.port,
                frontend_port=args.frontend_port,
            )
        if args.command == "stop":
            return self.stop()
        if args.command == "status":
            return self.status()
        if args.command in STUB_COMMANDS:
            return self._stub(args.command)
        print(f"未知命令: {args.command}", file=sys.stderr)
        return 2

    # ------------------------------------------------------------- start

    def start(
        self,
        *,
        no_browser: bool = False,
        port: int | None = None,
        frontend_port: int | None = None,
    ) -> int:
        backend_port = port or self.config.get_port()
        frontend_port = frontend_port or self.config.get_frontend_port()
        print("=== AI Factory 启动 ===")

        # 1. 环境检查 (python / node)
        problems = _env_problems()
        if problems:
            for problem in problems:
                print(f"  ✗ {problem}", file=sys.stderr)
            print("  环境检查未通过, 请先修复上述问题。", file=sys.stderr)
            return 1

        # 2. 依赖检查 (.venv / node_modules)
        problems = _dep_problems(self.root)
        if problems:
            for problem in problems:
                print(f"  ✗ {problem}", file=sys.stderr)
            print("  依赖检查未通过, 请先安装。", file=sys.stderr)
            return 1

        # 3. 配置检查 (LLM key 缺失 → 仅提示, 不阻断)
        for hint in _config_hints(self.config):
            print(f"  ⚠ {hint}")

        # 4. 幂等: 前后端均已运行 → 提示不重复起
        backend_up = self._backend_running()
        frontend_up = self._frontend_running()
        if backend_up and frontend_up:
            print(f"  已在运行: http://127.0.0.1:{frontend_port}{FRONTEND_PATH}")
            return 0

        # 5. 端口预检 (仅检查需要启动的一侧; 占用 → 明确提示)
        busy: list[str] = []
        if not backend_up and _port_in_use(backend_port):
            busy.append(f"后端端口 {backend_port}")
        if not frontend_up and _port_in_use(frontend_port):
            busy.append(f"前端端口 {frontend_port}")
        if busy:
            print("  ✗ 端口已被占用: " + " / ".join(busy), file=sys.stderr)
            print(
                "    请先释放端口, 或修改配置 (factory-console/.env 或 "
                "~/.factory/config.json 的 PORT/FRONTEND_PORT)。",
                file=sys.stderr,
            )
            return 1

        # 6. 后端启动 + 健康检查 (失败 → 日志尾部 + 清理)
        if not self._start_backend(backend_port):
            return 1
        if not self._wait_backend(backend_port):
            self._show_log_tail(self.backend_log)
            self._cleanup_pids()
            print("  ✗ 后端启动失败 (健康检查超时, 详见上方日志尾部)", file=sys.stderr)
            return 1

        # 7. 前端启动 + 就绪检查 (失败 → 回滚: 停掉已起后端)
        if not self._start_frontend(frontend_port):
            self.stop()
            return 1
        if not self._wait_frontend(frontend_port):
            self._show_log_tail(self.frontend_log)
            self.stop()
            print("  ✗ 前端启动失败 (详见上方日志尾部)", file=sys.stderr)
            return 1

        # 8. 打开浏览器
        url = f"http://127.0.0.1:{frontend_port}{FRONTEND_PATH}"
        print(f"  ✓ 已就绪: {url}")
        print(f"    后端 API: http://127.0.0.1:{backend_port}{HEALTH_PATH}")
        if not no_browser:
            _open_url(url)
        return 0

    def _start_backend(self, port: int) -> bool:
        """后台启动 uvicorn (bootstrap 经 base64 传子进程); pid 写文件。"""
        if self._backend_running():
            print(f"  后端已在运行 (PID {_read_pid(self.backend_pid)})")
            return True
        self.run_dir.mkdir(parents=True, exist_ok=True)
        python = self.root / ".venv" / "bin" / "python"
        code = (
            "import importlib,uvicorn;"
            "m=importlib.import_module({mod!r});"
            "app=m.create_app(factory_root={root!r});"
            "uvicorn.run(app,host='127.0.0.1',port={port},log_level='info')"
        ).format(mod=BACKEND_MODULE, root=str(self.data_dir), port=port)
        b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
        cmd = [str(python), "-c", f"import base64;exec(base64.b64decode('{b64}').decode('utf-8'))"]
        try:
            log = open(self.backend_log, "ab")
        except OSError as exc:
            print(f"  ✗ 无法写后端日志 {self.backend_log}: {exc}", file=sys.stderr)
            return False
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=str(self.root),
                start_new_session=True,  # 独立进程组 — stop 整组杀, 不误伤
            )
        except OSError as exc:
            log.close()
            print(f"  ✗ 后端启动失败: {exc}", file=sys.stderr)
            return False
        _write_pid(self.backend_pid, proc.pid)
        print(f"  后端启动中 (PID {proc.pid}, http://127.0.0.1:{port})")
        return True

    def _start_frontend(self, port: int) -> bool:
        """后台启动 vite dev (--port --strictPort --host); pid 写文件。"""
        if self._frontend_running():
            print(f"  前端已在运行 (PID {_read_pid(self.frontend_pid)})")
            return True
        frontend = self.root / "factory-console" / "web" / "frontend"
        npm = shutil.which("npm")
        if not npm:
            print("  ✗ 未找到 npm — 请安装 Node.js ≥18", file=sys.stderr)
            return False
        cmd = [
            npm,
            "run",
            "dev",
            "--",
            "--port",
            str(port),
            "--strictPort",
            "--host",
            "127.0.0.1",
        ]
        try:
            log = open(self.frontend_log, "ab")
        except OSError as exc:
            print(f"  ✗ 无法写前端日志 {self.frontend_log}: {exc}", file=sys.stderr)
            return False
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=str(frontend),
                start_new_session=True,
            )
        except OSError as exc:
            log.close()
            print(f"  ✗ 前端启动失败: {exc}", file=sys.stderr)
            return False
        _write_pid(self.frontend_pid, proc.pid)
        print(f"  前端启动中 (PID {proc.pid}, http://127.0.0.1:{port})")
        return True

    # ------------------------------------------------------------- 健康检查

    def _wait_http(self, url: str, timeout: float = HEALTH_TIMEOUT) -> bool:
        """轮询 GET url 直到 200 (幂等可重入; 超时 → False)。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _http_status(url) == 200:
                return True
            time.sleep(HEALTH_INTERVAL)
        return False

    def _wait_backend(self, port: int) -> bool:
        return self._wait_http(f"http://127.0.0.1:{port}{HEALTH_PATH}")

    def _wait_frontend(self, port: int) -> bool:
        return self._wait_http(f"http://127.0.0.1:{port}/", timeout=FRONTEND_TIMEOUT)

    # ------------------------------------------------------------- 进程状态

    def _backend_running(self) -> bool:
        pid = _read_pid(self.backend_pid)
        return pid is not None and _pid_alive(pid)

    def _frontend_running(self) -> bool:
        pid = _read_pid(self.frontend_pid)
        return pid is not None and _pid_alive(pid)

    def _kill_group(self, pid: int) -> None:
        """杀整个进程组 (start_new_session → pgid == pid); 容错静默。"""
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    def _stop_one(self, pid_file: Path, port: int) -> int | None:
        """停单个服务: pid 文件优先; 无 → 按端口 lsof 找。返回被杀 PID。"""
        pid = _read_pid(pid_file)
        if pid is not None:
            if _pid_alive(pid):
                self._kill_group(pid)
                _kill_pid(pid, grace=3.0)
                return pid
            return None  # 陈旧 pid 文件 (进程已死) — 仅清理文件
        for found in _lsof_pids(port):
            _kill_pid(found, grace=3.0)
            return found
        return None

    def _cleanup_pids(self) -> None:
        for path in (self.backend_pid, self.frontend_pid):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    # ------------------------------------------------------------- stop

    def stop(self) -> int:
        print("=== AI Factory 停止 ===")
        stopped: list[str] = []
        for label, pid_file, port in (
            ("后端", self.backend_pid, self.config.get_port()),
            ("前端", self.frontend_pid, self.config.get_frontend_port()),
        ):
            killed = self._stop_one(pid_file, port)
            if killed is not None:
                stopped.append(f"{label} (PID {killed})")
        self._cleanup_pids()  # 统一清理 (循环内删会吞掉后续服务的 pid 文件)
        if stopped:
            print("  已停止: " + ", ".join(stopped))
        else:
            print("  未发现运行中的服务 (无 pid 文件 / 进程已退出)")
        for label, port in (
            ("后端", self.config.get_port()),
            ("前端", self.config.get_frontend_port()),
        ):
            if _port_in_use(port):
                print(
                    f"  ⚠ {label} 端口 {port} 仍被占用 — 存在未托管进程, 请手动检查",
                    file=sys.stderr,
                )
        return 0

    # ------------------------------------------------------------- status

    def status(self) -> int:
        llm = self.config.get_llm()
        print("=== AI Factory 状态 ===")
        print(f"数据目录: {self.data_dir}")
        print(
            f"LLM: provider={llm['provider']} model={llm['model']} "
            f"api_key={'已配置' if llm['api_key'] else '未配置'}"
        )
        for label, pid_file, port in (
            ("后端", self.backend_pid, self.config.get_port()),
            ("前端", self.frontend_pid, self.config.get_frontend_port()),
        ):
            pid = _read_pid(pid_file)
            alive = pid is not None and _pid_alive(pid)
            listening = _port_in_use(port)
            if alive and listening:
                state = f"运行中 (PID {pid})"
            elif alive:
                state = f"进程在但端口未监听 (PID {pid})"
            elif listening:
                state = "未托管进程占用端口"
            else:
                state = "未运行"
            print(f"{label}: {state} — 端口 {port} {'监听中' if listening else '空闲'}")
        return 0

    # ------------------------------------------------------------- 杂项

    def _show_log_tail(self, path: Path, lines: int = 30) -> None:
        """打印日志尾部 (启动失败诊断; 缺失/空 → 静默)。"""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        tail = text.splitlines()[-lines:]
        if not tail:
            return
        print(f"  --- {path.name} 日志尾部 ({len(tail)} 行) ---", file=sys.stderr)
        for line in tail:
            print(f"  | {line}", file=sys.stderr)

    def _stub(self, cmd: str) -> int:
        print(f"`factory {cmd}` 尚未实现 — 架构预留子命令 (计划 S10-007 阶段三实现)。")
        return 1


# ------------------------------------------------------------------ argparse


def build_parser() -> argparse.ArgumentParser:
    """argparse 结构: start/stop/status + 预留 init/config/project/run。"""
    parser = argparse.ArgumentParser(
        prog="factory",
        description="AI Software Factory — 一键启动/停止/状态 (S10-007 阶段二 CLI MVP)",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="命令")
    p_start = sub.add_parser("start", help="启动本地开发环境 (后端 + 前端 + 打开浏览器)")
    p_start.add_argument("--no-browser", action="store_true", help="不自动打开浏览器 (headless/CI)")
    p_start.add_argument("--port", type=int, default=None, help="后端端口 (默认取配置, 8011)")
    p_start.add_argument(
        "--frontend-port", type=int, default=None, help="前端端口 (默认取配置, 5180)"
    )
    sub.add_parser("stop", help="停止前后端服务 (pid 文件优先, 兜底按端口)")
    sub.add_parser("status", help="显示端口/进程/数据目录/LLM 状态")
    for name in STUB_COMMANDS:
        sub.add_parser(name, help=f"[预留] factory {name} — 阶段三实现")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 入口 (bin/factory 经 importlib 调用; sys.argv[1:] 默认)。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    return FactoryCLI(ConfigProvider()).run(args)


if __name__ == "__main__":
    sys.exit(main())
