"""runtime/health.py — 健康检查 (Console HTTP / Core 进程)。

设计依据: phase15-runtime-design.md §1.3 (Console 健康: GET /api/dashboard
→ 200) / §1.2 (Core 健康: 子进程存活 + 退出码)。

- check_console: 只读 GET, 任何异常/非 200 → False (失败安全)。
- check_core: Popen 轮询 → (alive, exitcode)。
- wait_healthy: 轮询 fn() 直到 True; 超时抛 RuntimeError (设计: 健康检查
  通过才报 READY, 超时 = 启动失败)。
"""

from __future__ import annotations

import time
import urllib.request

from .errors import RuntimeError


def check_console(base_url: str, timeout: float = 2.0) -> bool:
    """GET {base_url}/api/dashboard → 200 即健康; 异常/非 200 → False。"""
    url = base_url.rstrip("/") + "/api/dashboard"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def check_core(proc) -> tuple[bool, int | None]:
    """子进程存活 + 退出码: 存活 → (True, None); 已退出 → (False, code)。"""
    if proc is None:
        return False, None
    code = proc.poll()
    if code is None:
        return True, None
    return False, code


def wait_healthy(fn, timeout: float, interval: float = 0.5) -> bool:
    """轮询 fn() 直到返回 True; 超时抛 RuntimeError。"""
    deadline = time.monotonic() + timeout
    while True:
        if fn():
            return True
        if time.monotonic() >= deadline:
            raise RuntimeError(f"health check timed out after {timeout:.1f}s")
        time.sleep(interval)
