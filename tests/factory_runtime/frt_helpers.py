"""tests/factory_runtime/frt_helpers.py — 唯一名 helper (防跨目录遮蔽)。

- wait_until: 轮询断言 (watchdog/子进程时序测试用, 确定性优于固定 sleep)
- pid_alive: pid 存活探测
"""

from __future__ import annotations

import os
import time


def wait_until(fn, timeout: float = 10.0, interval: float = 0.1) -> bool:
    """轮询 fn() 直到返回真值; 超时返回 False (内部异常忽略)。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def pid_alive(pid: int | None) -> bool:
    """pid 存活探测 (不存在/僵尸 → False)。"""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
