"""factory-console/ops_scheduler.py — S22 Continuous Production Operations Scheduler.

Schedule Contract + 持久化 + 执行循环 + 幂等/并发/missed schedule。

职责边界:
- Scheduler 只负责 When/What (发现到期任务 → 调 health_service)
- 不判断健康 / 不决定 rollback / 不修改 release (HealthMonitor/Policy/Rollback 各司其职)
- 持久化配置 (重启恢复) + dedup (并发/重复触发安全) + bounded catch-up
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .integrity_lock import file_lock

#: bounded catch-up 上限 (missed schedule 最多补 N 次)
MAX_CATCH_UP = 3
#: dedup 时间窗口 (秒) — 同一 schedule 同窗口只执行一次
DEDUP_WINDOW_SECONDS = 300


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _schedules_file(root: Path | str) -> Path:
    return Path(root) / "ops" / "schedules.json"


def _schedules_lock(root: Path | str) -> Path:
    return Path(root) / "ops" / "schedules.lock"


def _load(root: Path | str) -> list[dict[str, Any]]:
    try:
        d = json.loads(_schedules_file(root).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(root: Path | str, data: list[dict[str, Any]]) -> None:
    p = _schedules_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def create_schedule(root: Path | str, *, project_id: str = "", release_id: str = "",
                    interval_seconds: int = 300, check_type: str = "health",
                    created_by: str = "ops") -> dict[str, Any]:
    """创建 Schedule (持久化)。release_id 可选: 空 = 对 project 最新 RELEASED release。"""
    if interval_seconds < 10:
        raise ValueError("interval_seconds 最小 10s")
    with file_lock(_schedules_lock(root)):
        data = _load(root)
        sched = {
            "schedule_id": f"sch-{uuid.uuid4().hex[:10]}",
            "project_id": project_id,
            "release_id": release_id,
            "check_type": check_type,
            "interval_seconds": interval_seconds,
            "enabled": True,
            "next_run_at": _now_iso(),
            "last_run_at": "",
            "last_result": "",
            "skipped_count": 0,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "created_by": created_by,
            "history": [{"at": _now_iso(), "note": "created"}],
        }
        data.append(sched)
        _save(root, data)
    return sched


def list_schedules(root: Path | str, *, enabled: bool | None = None) -> list[dict[str, Any]]:
    data = _load(root)
    if enabled is not None:
        return [s for s in data if s.get("enabled") is enabled]
    return data


def get_schedule(root: Path | str, schedule_id: str) -> dict[str, Any] | None:
    for s in _load(root):
        if s["schedule_id"] == schedule_id:
            return s
    return None


def _update(root: Path | str, schedule_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    with file_lock(_schedules_lock(root)):
        data = _load(root)
        for s in data:
            if s["schedule_id"] == schedule_id:
                s.update(patch)
                s["updated_at"] = _now_iso()
                s["history"].append({"at": _now_iso(), "note": f"updated: {','.join(patch.keys())}"})
                _save(root, data)
                return s
        raise ValueError(f"Schedule 不存在: {schedule_id}")


def enable_schedule(root: Path | str, schedule_id: str) -> dict[str, Any]:
    return _update(root, schedule_id, {"enabled": True})


def disable_schedule(root: Path | str, schedule_id: str) -> dict[str, Any]:
    return _update(root, schedule_id, {"enabled": False})


def delete_schedule(root: Path | str, schedule_id: str) -> None:
    with file_lock(_schedules_lock(root)):
        data = [s for s in _load(root) if s["schedule_id"] != schedule_id]
        _save(root, data)


# ------------------------------------------------------------------ 执行循环

def _resolve_target(root: Path | str, sched: dict[str, Any]) -> str | None:
    """resolve release_id (schedule 未指定 → project 最新 RELEASED release)。"""
    if sched.get("release_id"):
        return sched["release_id"]
    from .release_service import list_releases
    rels = list_releases(root)
    released = [r for r in rels if r["state"] == "RELEASED"]
    if not released:
        return None
    released.sort(key=lambda r: r.get("created_at", ""))
    return released[-1]["release_id"]


def run_due_schedules(root: Path | str, *, now: datetime | None = None) -> dict[str, Any]:
    """执行所有到期 schedule (幂等 + dedup + bounded catch-up)。

    Returns: {executed: [...], skipped_duplicates: [...], missed: [...]}
    """
    from .health_service import health_check

    now = now or datetime.now(timezone.utc)
    now_ts = now.timestamp()
    result: dict[str, Any] = {"executed": [], "skipped_duplicates": [], "missed": []}
    for sched in list_schedules(root, enabled=True):
        sid = sched["schedule_id"]
        try:
            next_run = datetime.fromisoformat(sched.get("next_run_at", "").replace("Z", "+00:00"))
        except (ValueError, TypeError):
            next_run = now
        if next_run.timestamp() > now_ts:
            continue  # 未到期
        # missed detection: next_run 远早于 now (超过 1 个 interval)
        missed_count = 0
        if next_run.timestamp() < now_ts - sched.get("interval_seconds", 300):
            missed_count = min(MAX_CATCH_UP, int((now_ts - next_run.timestamp()) // sched.get("interval_seconds", 300)))
        # dedup: 同 schedule 同窗口只执行一次 (用 lock + last_run_at 窗口判断)
        dedup_key = f"{sid}:{int(now_ts // DEDUP_WINDOW_SECONDS)}"
        with file_lock(_schedules_lock(root)):
            current = get_schedule(root, sid)
            if current is None:
                continue
            # last_run_at 在本窗口内 → 已执行 (duplicate worker)
            if current.get("last_run_at"):
                try:
                    last_ts = datetime.fromisoformat(str(current["last_run_at"]).replace("Z", "+00:00")).timestamp()
                    if last_ts >= now_ts - DEDUP_WINDOW_SECONDS and current.get("last_result"):
                        result["skipped_duplicates"].append(sid)
                        continue
                except (ValueError, TypeError):
                    pass
            # 标记执行中 (防并发双跑)
            _update(root, sid, {"last_run_at": _now_iso()})
        # 执行 (锁外跑, 避免长持锁)
        target = _resolve_target(root, sched)
        if target is None:
            _update(root, sid, {"last_result": "NO_TARGET", "next_run_at": (
                now + timedelta(seconds=sched.get("interval_seconds", 300))).isoformat(timespec="seconds")})
            continue
        try:
            hc = health_check(root, target)
            result["executed"].append({"schedule_id": sid, "release_id": target,
                                       "health_check_id": hc["health_check_id"], "result": hc["result"]})
            _update(root, sid, {"last_result": hc["result"],
                                "next_run_at": (now + timedelta(seconds=sched.get("interval_seconds", 300))).isoformat(timespec="seconds")})
            if missed_count:
                _update(root, sid, {"skipped_count": sched.get("skipped_count", 0) + missed_count})
                result["missed"].append({"schedule_id": sid, "missed": missed_count})
        except Exception as exc:  # noqa: BLE001
            result["executed"].append({"schedule_id": sid, "error": str(exc)})
            _update(root, sid, {"last_result": f"ERROR:{exc}",
                                "next_run_at": (now + timedelta(seconds=sched.get("interval_seconds", 300))).isoformat(timespec="seconds")})
    return result


# ------------------------------------------------------------------ 后台循环 (可选, 非唯一状态)

class OpsSchedulerLoop:
    """后台循环线程: 周期调用 run_due_schedules (进程内, 配置持久化)。"""

    def __init__(self, root: Path | str, tick_seconds: int = 30):
        self.root = root
        self.tick = tick_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="ops-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        import time
        while not self._stop.is_set():
            try:
                run_due_schedules(self.root)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(self.tick)
