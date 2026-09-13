"""runtime/watchdog.py — managed service 退出检测 + 自动重启 (独立模块)。

架构裁决 B (Core Command Model):
- watchdog 只 watch **managed services** (当前 Console; manager.managed_services
  注册点, 未来 Agent Worker/Scheduler 在此扩展 — watchdog 本体零改动)。
- Core 是命令执行器 (短生命周期): 退出是**预期**, 不重启, 不报警为 crash。

设计依据: phase15-runtime-design.md §1.6/§3 (崩溃恢复, 修正后: 仅 managed
service 崩溃 → 重启 ≤3 次 → 事件记录; 超限置 failed) + docs/architecture/
runtime-service-model.md。

与 manager 解耦: Watchdog 只依赖 manager 的稳定协作 API
(managed_services/status/service_proc/restart_process/mark_failed) —
不触碰 manager 内部字段。后台守护线程, stop() 事件退出并 join。
"""

from __future__ import annotations

import logging
import threading
import time

from .health import check_process
from .logging import log_event


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Watchdog:
    """managed service 存活轮询 → 非预期退出自动重启 (≤ max_restarts, 超限 failed)。"""

    def __init__(
        self,
        manager,
        max_restarts: int = 3,
        poll_interval: float = 1.0,
        logger: logging.Logger | None = None,
    ) -> None:
        self.manager = manager
        self.max_restarts = int(max_restarts)
        self.poll_interval = float(poll_interval)
        self.logger = logger
        #: 累计重启次数 / 事件记录 [(name, exit_code, at)]
        self.restart_count = 0
        self.restarts: list[dict] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """启动守护线程 (幂等)。"""
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="factory-runtime-watchdog",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """停止轮询并 join (幂等)。"""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    # ------------------------------------------------------------- 内部

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._check_once()
            except Exception:
                # watchdog 自身绝不崩溃 (失败安全: 下轮再试)
                pass
            self._stop_event.wait(self.poll_interval)

    def _check_once(self) -> None:
        status = self.manager.status()["status"]
        if status not in ("starting", "ready"):
            return
        # 只 watch managed services (当前 Console); Core 命令退出是预期, 不 watch
        for name in self.manager.managed_services:
            proc = self.manager.service_proc(name)
            if proc is None:
                continue
            alive, code = check_process(proc)
            if not alive:
                self._on_exit(name, code)

    def _on_exit(self, name: str, exit_code: int | None) -> None:
        with self._lock:
            if self._stop_event.is_set():
                return
            if self.manager.status()["status"] not in ("starting", "ready"):
                return  # 停止流程中不重启
            self.restart_count += 1
            self.restarts.append({"name": name, "exit_code": exit_code, "at": _now_iso()})
            if self.restart_count > self.max_restarts:
                if self.logger is not None:
                    log_event(
                        self.logger,
                        "watchdog limit reached",
                        f"{name} exited code={exit_code} (restarts={self.restart_count})",
                    )
                self.manager.mark_failed(
                    f"watchdog restart limit exceeded ({self.max_restarts})"
                )
                self._stop_event.set()
                return
            if self.logger is not None:
                log_event(
                    self.logger,
                    "restart",
                    f"{name} exited code={exit_code}, restart #{self.restart_count}",
                )
            try:
                self.manager.restart_process(name)
            except Exception as exc:  # 重启失败 → failed (响亮, 不静默)
                if self.logger is not None:
                    log_event(self.logger, "restart failed", f"{name}: {exc}")
                self.manager.mark_failed(f"restart failed: {exc}")
                self._stop_event.set()
