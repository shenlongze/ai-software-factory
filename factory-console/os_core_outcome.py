"""factory-console/os_core_outcome.py — OS Core: Outcome (MU-CORE-10).

Outcome = 该次工作最终业务结果 (绑定 Execution, 引用 Verification/Evidence)。

语义: Execution succeeded ≠ Outcome accepted (Verification failed → Outcome rejected 合法)。
SSOT: <root>/outcome/outcomes.json (OUT-*)。
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OUTCOME_STATUSES: tuple[str, ...] = ("accepted", "rejected")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: str | Path) -> Path:
    return Path(root) / "outcome" / "outcomes.json"


def _load(root: str | Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = data.get("outcomes") if isinstance(data, dict) else None
    return items if isinstance(items, dict) else {}


def _save(root: str | Path, data: dict[str, dict[str, Any]]) -> None:
    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"outcomes": data}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def create_outcome(root: str | Path, *, execution_id: str, status: str,
                   verification_refs: list[str] | None = None,
                   evidence_refs: list[str] | None = None,
                   result_refs: list[str] | None = None) -> dict[str, Any]:
    """创建 Outcome: 必须绑定 Execution 且至少引用一个 Verification 或 Evidence。"""
    from .os_core_evidence import get_evidence
    from .os_core_execution import get_execution
    from .os_core_verification import get_verification

    if status not in OUTCOME_STATUSES:
        raise ValueError(f"未知 status: {status} (可选: {OUTCOME_STATUSES})")
    if get_execution(root, execution_id) is None:
        raise ValueError(f"Execution 不存在: {execution_id}")
    vrefs = [str(v) for v in (verification_refs or [])]
    erefs = [str(e) for e in (evidence_refs or [])]
    if not vrefs and not erefs:
        raise ValueError("Outcome 必须引用至少一个 Verification 或 Evidence")
    for vid in vrefs:
        ver = get_verification(root, vid)
        if ver is None:
            raise ValueError(f"Verification 不存在: {vid}")
        if ver["execution_id"] != str(execution_id):
            raise ValueError(f"Verification {vid} 不属于该 Execution")
    for eid in erefs:
        ev = get_evidence(root, eid)
        if ev is None:
            raise ValueError(f"Evidence 不存在: {eid}")
        if ev["execution_id"] != str(execution_id):
            raise ValueError(f"Evidence {eid} 不属于该 Execution")
    data = _load(root)
    oid = f"OUT-{uuid.uuid4().hex[:10]}"
    rec = {"outcome_id": oid, "execution_id": str(execution_id), "status": status,
           "verification_refs": vrefs, "evidence_refs": erefs,
           "result_refs": [str(r) for r in (result_refs or [])],
           "created_at": _now_iso()}
    data[oid] = rec
    _save(root, data)
    return rec


def get_outcome(root: str | Path, outcome_id: str) -> dict[str, Any] | None:
    return _load(root).get(str(outcome_id))


def list_outcomes(root: str | Path, *, execution_id: str = "") -> list[dict[str, Any]]:
    recs = list(_load(root).values())
    if execution_id:
        recs = [r for r in recs if r["execution_id"] == str(execution_id)]
    return sorted(recs, key=lambda r: (r.get("created_at", ""), r["outcome_id"]))


__all__ = ["OUTCOME_STATUSES", "create_outcome", "get_outcome", "list_outcomes"]
