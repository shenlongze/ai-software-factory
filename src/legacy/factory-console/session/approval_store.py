"""factory-console/session/approval_store.py — bash 写操作批准门 (S8-4, v1.1.247).

Hermes "⚠ Approval" 机制: bash_exec 遇到写/敏感命令 → 不直接执行,
登记为 pending 批准请求 → WebUI/会话显示 → 用户批准 → 执行 → 结果回写。

结构 (<data_dir>/session_approvals/<session_id>.json):
{
  "pending": [{"id","command","created_at"}],
  "history": [{"id","command","status":"approved|rejected","result","created_at","resolved_at"}]
}
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_STATUS = ("pending", "approved", "rejected")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(data_dir: str | Path, session_id: str) -> Path:
    return Path(data_dir) / "session_approvals" / f"{session_id}.json"


def _load(path: Path) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def list_approvals(data_dir: str | Path | None, session_id: str) -> dict[str, Any]:
    if not data_dir or not session_id:
        return {"pending": [], "history": [], "count": 0}
    d = _load(_path(data_dir, session_id))
    return {"pending": d.get("pending") or [], "history": d.get("history") or [],
            "count": len(d.get("pending") or [])}


def request_approval(data_dir: str | Path | None, session_id: str, command: str) -> dict[str, Any]:
    """登记待批准命令 → {id, command, status:pending}。"""
    if not data_dir or not session_id:
        return {}
    p = _path(data_dir, session_id)
    d = _load(p)
    aid = "APR-" + uuid.uuid4().hex[:8]
    item = {"id": aid, "command": str(command or "")[:2000], "created_at": _now_iso()}
    d.setdefault("pending", []).append(item)
    _save(p, d)
    return {**item, "status": "pending"}


def get_pending(data_dir: str | Path | None, session_id: str, approval_id: str) -> dict[str, Any] | None:
    if not data_dir or not session_id:
        return None
    d = _load(_path(data_dir, session_id))
    for it in d.get("pending") or []:
        if it.get("id") == approval_id:
            return it
    return None


def resolve(data_dir: str | Path | None, session_id: str, approval_id: str,
            status: str, result: str = "") -> dict[str, Any] | None:
    """批准/拒绝 → 从 pending 移到 history。返回被处理的条目。"""
    if status not in ("approved", "rejected"):
        return None
    if not data_dir or not session_id:
        return None
    p = _path(data_dir, session_id)
    d = _load(p)
    pending = d.get("pending") or []
    item = next((it for it in pending if it.get("id") == approval_id), None)
    if item is None:
        return None
    d["pending"] = [it for it in pending if it.get("id") != approval_id]
    rec = {**item, "status": status, "result": str(result or "")[:3000],
           "resolved_at": _now_iso()}
    d.setdefault("history", []).append(rec)
    _save(p, d)
    return rec


__all__ = ["list_approvals", "request_approval", "get_pending", "resolve"]
