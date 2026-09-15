"""work · 调度计划（S22 —— 搬迁自 factory_console.ops_scheduler）。

职责边界（与老区一致，不变）:
    调度器只负责 **When / What** —— 发现到期任务并交给下游。
    不判断健康 / 不决定 rollback / 不修改 release（HealthMonitor / Policy / Rollback 各司其职）。

数据: `<root>/ops/schedules.json`（列表；原子写 os.replace，避免半写文件）。

搬迁说明（刀2 第三域 · work）:
  · 只搬 HTTP 面用到的 6 个函数: create / list / get / enable / disable / delete。
  · 老区的 `run_due_schedules` + `OpsSchedulerLoop` **未搬** —— 实测全仓无任何消费者
    （grep 为空），且它们要 release_service + health_service 两个**别的域**；
    按"判退即不搬"处理，不做无消费者的搬运。
  · 文件锁（老区 integrity_lock）**去掉** —— 新地基约定见 `services/work/store.py`:
    「单进程本地使用, 不做文件锁 (KISS); 并发写入由上层(单 CLI 进程)保证」。
    去掉不改变单进程行为; 跨进程并发本就不是当前形态。
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["create_schedule", "list_schedules", "get_schedule",
           "enable_schedule", "disable_schedule", "delete_schedule"]

#: 最小调度间隔（秒）—— 与老区一致
MIN_INTERVAL_SECONDS = 10


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _schedules_file(root: Path | str) -> Path:
    return Path(root) / "ops" / "schedules.json"


def _load(root: Path | str) -> list[dict[str, Any]]:
    try:
        d = json.loads(_schedules_file(root).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(root: Path | str, data: list[dict[str, Any]]) -> None:
    p = _schedules_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def create_schedule(root: Path | str, *, project_id: str = "", release_id: str = "",
                    interval_seconds: int = 300, check_type: str = "health",
                    created_by: str = "ops") -> dict[str, Any]:
    """创建 Schedule（持久化）。release_id 可选: 空 = 对 project 最新 RELEASED release。"""
    if interval_seconds < MIN_INTERVAL_SECONDS:
        raise ValueError(f"interval_seconds 最小 {MIN_INTERVAL_SECONDS}s")
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
    """列表（可按启用状态过滤）。"""
    data = _load(root)
    if enabled is not None:
        return [s for s in data if s.get("enabled") is enabled]
    return data


def get_schedule(root: Path | str, schedule_id: str) -> dict[str, Any] | None:
    """单个 Schedule；不存在 → None。"""
    for s in _load(root):
        if s.get("schedule_id") == schedule_id:
            return s
    return None


def _update(root: Path | str, schedule_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    data = _load(root)
    for s in data:
        if s.get("schedule_id") == schedule_id:
            s.update(patch)
            s["updated_at"] = _now_iso()
            s.setdefault("history", []).append(
                {"at": _now_iso(), "note": f"updated: {','.join(patch.keys())}"})
            _save(root, data)
            return s
    raise ValueError(f"Schedule 不存在: {schedule_id}")


def enable_schedule(root: Path | str, schedule_id: str) -> dict[str, Any]:
    """启用（不存在 → ValueError）。"""
    return _update(root, schedule_id, {"enabled": True})


def disable_schedule(root: Path | str, schedule_id: str) -> dict[str, Any]:
    """停用（不存在 → ValueError）。"""
    return _update(root, schedule_id, {"enabled": False})


def delete_schedule(root: Path | str, schedule_id: str) -> None:
    """删除（幂等: 不存在也视为成功，与老区一致）。"""
    _save(root, [s for s in _load(root) if s.get("schedule_id") != schedule_id])
