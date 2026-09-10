"""factory-console/os_core_verification.py — OS Core: Verification (MU-CORE-10).

Verification = 针对**一次真实 Execution** 判断结果是否满足要求 (不针对 TaskNode, 不自动由 succeeded 推导)。

SSOT: <root>/verification/verifications.json (V-*)。
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERIFICATION_STATUSES: tuple[str, ...] = ("passed", "failed")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: str | Path) -> Path:
    return Path(root) / "verification" / "verifications.json"


def _load(root: str | Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = data.get("verifications") if isinstance(data, dict) else None
    return items if isinstance(items, dict) else {}


def _save(root: str | Path, data: dict[str, dict[str, Any]]) -> None:
    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"verifications": data}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def create_verification(root: str | Path, *, execution_id: str, status: str,
                        checks: list[dict[str, Any]] | None = None,
                        evidence_refs: list[str] | None = None) -> dict[str, Any]:
    """创建 Verification: 必须绑定真实 Execution (execution_id 必填且存在)。"""
    from .os_core_execution import get_execution

    if status not in VERIFICATION_STATUSES:
        raise ValueError(f"未知 status: {status} (可选: {VERIFICATION_STATUSES})")
    if get_execution(root, execution_id) is None:
        raise ValueError(f"Execution 不存在: {execution_id}")
    data = _load(root)
    vid = f"V-{uuid.uuid4().hex[:10]}"
    rec = {"verification_id": vid, "execution_id": str(execution_id), "status": status,
           "passed": status == "passed", "checks": list(checks or []),
           "evidence_refs": [str(e) for e in (evidence_refs or [])],
           "created_at": _now_iso(), "verified_at": _now_iso()}
    data[vid] = rec
    _save(root, data)
    return rec


def get_verification(root: str | Path, verification_id: str) -> dict[str, Any] | None:
    return _load(root).get(str(verification_id))


def list_verifications(root: str | Path, *, execution_id: str = "",
                       status: str = "") -> list[dict[str, Any]]:
    recs = list(_load(root).values())
    if execution_id:
        recs = [r for r in recs if r["execution_id"] == str(execution_id)]
    if status:
        recs = [r for r in recs if r["status"] == str(status)]
    return sorted(recs, key=lambda r: (r.get("created_at", ""), r["verification_id"]))


__all__ = ["VERIFICATION_STATUSES", "create_verification", "get_verification",
           "list_verifications"]
