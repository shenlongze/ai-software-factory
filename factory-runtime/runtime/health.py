"""runtime/health.py — 健康检查 (Service Health / Command Health 区分)。

架构裁决 B (Core Command Model, 用户已确认):
- ServiceHealth: 长期组件 (managed service)。当前唯一 = Console
  (uvicorn 常驻 + GET /api/dashboard → 200)。未来: Agent Worker / Scheduler。
- CommandHealth: 短生命周期命令。当前唯一 = Core (factory CLI 命令执行;
  health = 命令可用性检查, 如 `factory --help` rc 0)。Core 退出是预期,
  非 crash — watchdog 不 watch Core (见 runtime/watchdog.py)。

设计依据: phase15-runtime-design.md §1.3/§1.2 + docs/architecture/
runtime-service-model.md (Service vs Command Model)。

- check_console: 只读 GET, 任何异常/非 200 → False (失败安全)。
- check_process: Popen 轮询 → (alive, exitcode)。
- service_health: 组装 ServiceHealth (进程存活 [+ HTTP probe])。
- command_health: 执行短命令 → CommandHealth (rc == 0 = available)。
- wait_healthy: 轮询 fn() 直到 True; 超时抛 RuntimeError (健康检查通过
  才报 READY, 超时 = 启动失败)。
"""

from __future__ import annotations

import subprocess
import time
import urllib.request
from dataclasses import asdict, dataclass, field

from .errors import RuntimeError


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class ServiceHealth:
    """长期组件 (managed service) 健康快照。

    - console: 常驻进程存活 = healthy (启动期以 HTTP /api/dashboard 为证)
    - 未来 Agent Worker / Scheduler: 进程存活 + 各自探针 (端口/心跳)
    """

    name: str
    alive: bool
    detail: str = ""
    checked_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CommandHealth:
    """短生命周期命令健康快照 (命令可用性, 非进程存活)。

    - core: `factory --help` rc 0 = available; 命令退出/失败 ≠ runtime 崩溃
    """

    name: str
    available: bool
    returncode: int | None = None
    detail: str = ""
    checked_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


def check_console(base_url: str, timeout: float = 2.0) -> bool:
    """GET {base_url}/api/dashboard → 200 即健康; 异常/非 200 → False。"""
    url = base_url.rstrip("/") + "/api/dashboard"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def check_process(proc) -> tuple[bool, int | None]:
    """子进程存活 + 退出码: 存活 → (True, None); 已退出 → (False, code)。"""
    if proc is None:
        return False, None
    code = proc.poll()
    if code is None:
        return True, None
    return False, code


def service_health(
    name: str,
    proc,
    base_url: str | None = None,
    timeout: float = 2.0,
) -> ServiceHealth:
    """组装 ServiceHealth: 进程存活; base_url 给定时叠加 HTTP 探针。"""
    alive, _code = check_process(proc)
    detail = ""
    if base_url is not None:
        http_ok = check_console(base_url, timeout=timeout)
        detail = f"http={http_ok}"
        alive = alive and http_ok
    return ServiceHealth(name=name, alive=alive, detail=detail)


def command_health(
    name: str,
    argv: list[str],
    timeout: float = 10.0,
    cwd: str | None = None,
) -> CommandHealth:
    """执行短命令并判定可用性 (rc == 0 = available)。

    失败安全: 找不到命令/超时/OSError → available False (绝不抛)。
    """
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        return CommandHealth(
            name=name,
            available=False,
            returncode=None,
            detail=f"command not found: {exc}",
        )
    except subprocess.TimeoutExpired:
        return CommandHealth(
            name=name,
            available=False,
            returncode=None,
            detail=f"timed out after {timeout:.1f}s",
        )
    except OSError as exc:
        return CommandHealth(
            name=name,
            available=False,
            returncode=None,
            detail=str(exc),
        )
    return CommandHealth(
        name=name,
        available=result.returncode == 0,
        returncode=result.returncode,
    )


def wait_healthy(fn, timeout: float, interval: float = 0.5) -> bool:
    """轮询 fn() 直到返回 True; 超时抛 RuntimeError。"""
    deadline = time.monotonic() + timeout
    while True:
        if fn():
            return True
        if time.monotonic() >= deadline:
            raise RuntimeError(f"health check timed out after {timeout:.1f}s")
        time.sleep(interval)
