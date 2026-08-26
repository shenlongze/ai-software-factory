"""factory-console/monitor.py — 统一监控运维 (D 系列, Founder 2026-08-26)。

单一采集器 → 统一 snapshot → 多处消费 (会话 system_status / 概览健康条 /
运维页 / CLI factory monitor)。全部真实数据, 失败安全。

- collect_system: 前端/后端端口探测 + 版本 + 模型 + 数据目录
- collect_project: 质量分 + 任务统计 + 产出物版本 + 文档数 + 最近活动
- save_snapshot / read_snapshots: monitor/snapshots.json (历史趋势)
"""

from __future__ import annotations

import json
import socket
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FRONTEND_PORT = 5180
BACKEND_PORT = 8011
SNAPSHOT_FILE = "monitor/snapshots.json"
MAX_SNAPSHOTS = 200

_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def port_up(host: str, port: int, timeout: float = 0.5) -> bool:
    """端口探测 (真实运行状态)。"""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except Exception:  # noqa: BLE001 — 探测失败 → 未运行 (诚实)
        return False


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def collect_system(
    root: Path | str, version: str, *, model_line: str = ""
) -> dict[str, Any]:
    """系统级监控: 前端/后端端口 + 版本 + 模型 + 数据目录。"""
    root = Path(root)
    return {
        "version": version,
        "frontend": {"port": FRONTEND_PORT, "up": port_up("127.0.0.1", FRONTEND_PORT)},
        "backend": {"port": BACKEND_PORT, "up": port_up("127.0.0.1", BACKEND_PORT)},
        "model": model_line or "",
        "data_dir": str(root),
        "collected_at": _now_iso(),
    }


def _task_stats(tasks: dict[str, Any]) -> dict[str, int]:
    stats: dict[str, int] = {}
    for t in tasks.values():
        if not isinstance(t, dict):
            continue
        st = str(t.get("status") or "todo")
        stats[st] = stats.get(st, 0) + 1
    return stats


def collect_project(
    root: Path | str,
    project_id: str,
    *,
    name: str | None = None,
    lifecycle: str | None = None,
    runtimes: int = 0,
    failed: int = 0,
) -> dict[str, Any] | None:
    """项目级监控 (文件信源, 失败安全): 质量分/任务/产出物/文档/最近活动。

    兼容两处项目目录: root/projects/<id> 与 root/workspace/projects/<id>。
    """
    root = Path(root)
    pid = Path(str(project_id)).name
    pdirs = [
        p for p in (root / "projects" / pid, root / "workspace" / "projects" / pid)
        if p.is_dir()
    ]
    if not pdirs:
        return None
    main = pdirs[0]
    # 质量分 (quality.json)
    q = None
    for pdir in pdirs:
        d = _read_json(pdir / "quality.json")
        if isinstance(d, dict) and isinstance(d.get("score"), (int, float)):
            q = d["score"]
            break
    # 任务统计 (management/backlog/task.json)
    tasks = {}
    for pdir in pdirs:
        data = _read_json(pdir / "management" / "backlog" / "task.json")
        if isinstance(data, dict) and isinstance(data.get("tasks"), dict):
            tasks = data["tasks"]
            break
    # 产出物契约版本 (artifacts.manifest.json)
    artifacts_version = 0
    for pdir in pdirs:
        md = _read_json(pdir / "artifacts.manifest.json")
        if isinstance(md, dict):
            artifacts_version = int(md.get("version", 0) or 0)
            break
    # 生命周期兜底 (product.json / project.json status)
    if not lifecycle:
        info = _read_json(main / "product.json") or {}
        lifecycle = str(info.get("status") or "")
        if not lifecycle:
            meta = _read_json(main / "project.json") or {}
            lifecycle = str(meta.get("status") or "")
    # 文档数 (board 扫描, 失败安全)
    docs = 0
    try:
        from .session.board import list_project_docs

        docs = sum(1 for d in list_project_docs(root, project_id) if d.get("exists"))
    except Exception:  # noqa: BLE001
        docs = 0
    # 最近活动 (项目目录最新文件 mtime)
    last_activity = None
    try:
        mtimes = [
            f.stat().st_mtime
            for pdir in pdirs
            for f in pdir.rglob("*")
            if f.is_file() and ".git" not in f.parts
        ]
        if mtimes:
            from datetime import datetime as _dt

            last_activity = _dt.fromtimestamp(max(mtimes)).astimezone(timezone.utc).isoformat(timespec="seconds")
    except Exception:  # noqa: BLE001
        last_activity = None
    return {
        "project_id": project_id,
        "name": name or project_id,
        "lifecycle": lifecycle or "",
        "runtimes": runtimes,
        "failed": failed,
        "quality": q,
        "tasks": _task_stats(tasks),
        "artifacts_version": artifacts_version,
        "docs": docs,
        "last_activity": last_activity,
        "collected_at": _now_iso(),
    }


#: 质量分告警阈值 (低于 → warning)
QUALITY_ALERT_THRESHOLD = 0.3


def check_alerts(system: dict[str, Any] | None, projects: list[dict[str, Any]]) -> list[dict[str, str]]:
    """阈值告警: 端口未运行 (critical) / 失败运行 (warning) / 质量偏低 (warning)。"""
    alerts: list[dict[str, str]] = []
    if system is not None:
        if not system.get("frontend", {}).get("up", False):
            alerts.append({"level": "critical", "scope": "system", "message": "Web 前端 (5180) 未运行"})
        if not system.get("backend", {}).get("up", False):
            alerts.append({"level": "critical", "scope": "system", "message": "后端 API (8011) 未运行"})
    for p in projects:
        name = str(p.get("name") or p.get("project_id") or "项目")
        if int(p.get("failed", 0) or 0) > 0:
            alerts.append({
                "level": "warning", "scope": "project",
                "project_id": str(p.get("project_id") or ""),
                "message": f"{name} 有 {p.get('failed')} 个失败运行实例",
            })
        q = p.get("quality")
        if isinstance(q, (int, float)) and q < QUALITY_ALERT_THRESHOLD:
            alerts.append({
                "level": "warning", "scope": "project",
                "project_id": str(p.get("project_id") or ""),
                "message": f"{name} 质量分偏低 ({q:.2f})",
            })
    return alerts


def save_snapshot(root: Path | str, payload: dict[str, Any]) -> bool:
    """快照落盘 (append, 保留最近 MAX_SNAPSHOTS; 失败安全)。"""
    root = Path(root)
    with _lock:
        try:
            f = root / SNAPSHOT_FILE
            f.parent.mkdir(parents=True, exist_ok=True)
            snaps = _snapshots_all(root)
            snaps.append({"at": _now_iso(), **payload})
            if len(snaps) > MAX_SNAPSHOTS:
                snaps = snaps[-MAX_SNAPSHOTS:]
            f.write_text(json.dumps(snaps, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except OSError:
            return False


def _snapshots_all(root: Path) -> list[dict[str, Any]]:
    try:
        data = _read_json(Path(root) / SNAPSHOT_FILE)
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def snapshot_count(root: Path | str) -> int:
    return len(_snapshots_all(root))


def read_snapshots(root: Path | str, limit: int = 10, offset: int = 0) -> list[dict[str, Any]]:
    """快照分页: 最新在前 (offset=0 → 最近 limit 条)。"""
    snaps = _snapshots_all(root)
    total = len(snaps)
    end = total - offset
    start = max(0, end - limit)
    return list(reversed(snaps[start:end])) if end > start else []


__all__ = ["collect_system", "collect_project", "save_snapshot", "read_snapshots", "snapshot_count", "port_up", "check_alerts", "QUALITY_ALERT_THRESHOLD", "FRONTEND_PORT", "BACKEND_PORT"]
