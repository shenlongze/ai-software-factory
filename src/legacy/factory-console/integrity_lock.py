"""factory-console/integrity_lock.py — S20.5 跨进程文件锁。

release/rollback/governance 的 read-modify-write 竞态保护。

- FileLock: fcntl.flock (macOS/Linux) 跨进程互斥
- 进程内 threading.RLock + 线程本地持有计数: 同一线程重入安全 (跳过重复 flock)
- 所有 mutation 操作 (approve/release execute/rollback execute/state transition)
  必须包在 FileLock scope 内
- 与现有 atomic write (tmp+fsync+os.replace) 组合 = 完整并发安全

原则:
- 不引入新依赖 (fcntl 标准库)
- 不改变 Service Contract
- 锁文件存于各实体目录 (.lock 后缀)
"""
from __future__ import annotations

import contextlib
import os
import threading
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # Windows 兜底 (项目实际 macOS/Linux)
    fcntl = None  # type: ignore[assignment]

#: 进程内重入锁 (key=lock 文件绝对路径)
_LOCAL_LOCKS: dict[str, threading.RLock] = {}
_LOCAL_LOCK_GUARD = threading.Lock()
#: 线程本地: 当前线程已持有的锁 (path → 持有计数)
_TLS = threading.local()


def _local_lock(path: Path) -> threading.RLock:
    key = str(path)
    with _LOCAL_LOCK_GUARD:
        return _LOCAL_LOCKS.setdefault(key, threading.RLock())


@contextlib.contextmanager
def file_lock(lock_path: Path | str, *, timeout: float = 30.0) -> Iterator[None]:
    """跨进程互斥锁 (fcntl.flock 阻塞 + timeout 兜底; 同线程重入安全)。"""
    p = Path(lock_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    local = _local_lock(p)
    held = getattr(_TLS, "held_locks", None)
    if held is None:
        held = _TLS.held_locks = {}
    if str(p) in held:
        # 同线程已持锁 (重入) → 直接进入, 不重复 flock
        held[str(p)] += 1
        try:
            yield
        finally:
            held[str(p)] -= 1
        return
    with local:  # 进程内不同线程互斥 (等待)
        fd = os.open(str(p), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            if fcntl is not None:
                import time

                deadline = time.monotonic() + timeout
                while True:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError(f"等待锁超时: {p} ({timeout}s)")
                        time.sleep(0.05)
            held[str(p)] = 1
            yield
        finally:
            held.pop(str(p), None)
            if fcntl is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            os.close(fd)
