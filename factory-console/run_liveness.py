"""factory-console/run_liveness.py — Run 存活注册表 + stale 检测 (P0-01)。

解决: Run 线程死亡但 progress.json 永久 RUNNING (僵尸 Run)。

- register_run: 线程启动时注册 (线程对象 + 项目/run id)
- unregister_run: 线程结束时注销
- is_alive: 查询线程是否存活
- reconcile_stale: 扫描 workflow_runs, 把
  (status=running AND 线程不存活 AND updated_at 超阈值) → STALE

状态语义:
  RUNNING    — 线程存活 + 持续心跳 (updated_at 新鲜)
  COMPLETED  — 正常完成事件 (report 落盘)
  FAILED     — 异常退出 (report 落盘 status=failed)
  CANCELLED  — 显式取消 (P0-02 cancel API)
  STALE      — 线程死亡且无完成事件 (僵尸)

失败安全: 注册表缺失/损坏 → 不抛, 保守处理 (不误判活跃 Run)。
边界: 纯标准库 (threading/pathlib/datetime), 零依赖。
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: stale 阈值 (秒) — running 且无心跳超过此时间 → STALE (长任务每 stage 都写 progress)
STALE_AFTER_S = 15 * 60  # 15 分钟无 progress 更新视为僵死 (正常长任务每 stage 都写)

#: 存活线程注册表 {project_id/run_id: (thread, start_ts)}
_ALIVE: dict[str, threading.Thread] = {}
_ALIVE_LOCK = threading.Lock()

#: 取消标志 {project_id/run_id: True} — 线程内检查
_CANCEL: dict[str, bool] = {}
_CANCEL_LOCK = threading.Lock()


def _key(project_id: str, run_id: str) -> str:
    return f"{project_id}/{run_id}"


def request_cancel(project_id: str, run_id: str) -> bool:
    """请求取消 Run (线程内 is_cancelled 检查 → 停止后续 stage)。幂等。"""
    try:
        with _CANCEL_LOCK:
            _CANCEL[_key(project_id, run_id)] = True
        return True
    except Exception:  # noqa: BLE001
        return False


def is_cancelled(project_id: str, run_id: str) -> bool:
    """线程内检查是否被请求取消 (stage 边界调用)。"""
    try:
        with _CANCEL_LOCK:
            return bool(_CANCEL.get(_key(project_id, run_id)))
    except Exception:  # noqa: BLE001
        return False


def clear_cancel(project_id: str, run_id: str) -> None:
    """线程结束时清除取消标志。"""
    try:
        with _CANCEL_LOCK:
            _CANCEL.pop(_key(project_id, run_id), None)
    except Exception:  # noqa: BLE001
        pass


def register_run(project_id: str, run_id: str, thread: threading.Thread) -> None:
    """线程启动时注册 (供 stale 检测判断线程是否存活)。"""
    try:
        with _ALIVE_LOCK:
            _ALIVE[_key(project_id, run_id)] = thread
    except Exception:  # noqa: BLE001
        pass


def unregister_run(project_id: str, run_id: str) -> None:
    """线程正常/异常结束时注销。"""
    try:
        with _ALIVE_LOCK:
            _ALIVE.pop(_key(project_id, run_id), None)
    except Exception:  # noqa: BLE001
        pass


def is_alive(project_id: str, run_id: str) -> bool:
    """线程是否仍存活 (注册表 + is_alive 双确认)。"""
    try:
        with _ALIVE_LOCK:
            th = _ALIVE.get(_key(project_id, run_id))
        return bool(th is not None and th.is_alive())
    except Exception:  # noqa: BLE001
        return True  # 保守: 查询失败当作活跃 (不误判)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_progress(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def mark_stale(path: Path, progress: dict[str, Any]) -> bool:
    """把僵尸 progress 标记 STALE (幂等, 只动 running)。返回是否变更。"""
    if str(progress.get("status") or "").lower() != "running":
        return False
    progress["status"] = "STALE"
    progress.setdefault("errors", []).append(
        f"STALE {_now_iso()}: executor 线程死亡且无完成事件 (reconciliation)"
    )
    progress["updated_at"] = _now_iso()
    _write_json(path, progress)
    return True


def reconcile_stale(runs_dir: Path, *, stale_after_s: int = STALE_AFTER_S) -> dict[str, Any]:
    """扫描全部 workflow_runs: running + 线程不活 + 心跳超时 → STALE。

    幂等; 只动真实僵死 (不误判活跃线程); 返回 {stale: [...], scanned: N}。
    """
    results: dict[str, Any] = {"scanned": 0, "stale": [], "alive": [], "other": 0}
    if not runs_dir.is_dir():
        return results
    now = time.time()
    for proj_dir in sorted(runs_dir.iterdir()):
        if not proj_dir.is_dir():
            continue
        for run_dir in sorted(proj_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            progress_path = run_dir / "progress.json"
            if not progress_path.is_file():
                continue
            results["scanned"] += 1
            project_id = proj_dir.name
            run_id = run_dir.name
            progress = _read_progress(progress_path)
            if progress is None:
                results["other"] += 1
                continue
            status = str(progress.get("status") or "").lower()
            if status != "running":
                results["other"] += 1
                continue
            # 线程存活 → 活跃 (即使心跳旧, 等线程自己完成/失败)
            if is_alive(project_id, run_id):
                results["alive"].append(run_id)
                continue
            # 线程不活 → 看心跳年龄
            updated = str(progress.get("updated_at") or "")
            age_s = 999999.0
            try:
                u = datetime.fromisoformat(updated)
                if u.tzinfo is None:
                    u = u.replace(tzinfo=timezone.utc)
                age_s = now - u.timestamp()
            except Exception:  # noqa: BLE001
                pass
            if age_s >= stale_after_s:
                if mark_stale(progress_path, progress):
                    results["stale"].append(run_id)
            else:
                # 线程死但心跳新 (刚死) → 也标 stale (无完成事件 = 无法继续)
                if mark_stale(progress_path, progress):
                    results["stale"].append(run_id)
    return results


def load_heartbeat(progress: dict[str, Any]) -> float | None:
    """读取 progress 心跳年龄 (秒) — 供 API/UI 展示。"""
    updated = str(progress.get("updated_at") or "")
    if not updated:
        return None
    try:
        u = datetime.fromisoformat(updated)
        if u.tzinfo is None:
            u = u.replace(tzinfo=timezone.utc)
        return max(0.0, time.time() - u.timestamp())
    except Exception:  # noqa: BLE001
        return None
