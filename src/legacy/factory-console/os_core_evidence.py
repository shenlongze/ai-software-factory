"""factory-console/os_core_evidence.py — OS Core: Evidence (MU-CORE-10).

Evidence = 可定位、可追溯、可解析的事实引用 (绑定 Execution)。

规则: 必须有可解析的 locator (file:<path> / output:<execution_id>);
LLM 文本自身不是 Evidence (locator 不可解析 → 拒绝)。
SSOT: <root>/evidence/evidences.json (EV-*)。
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVIDENCE_TYPES: tuple[str, ...] = ("command_output", "file", "artifact", "test_result",
                                   "runtime_result", "log")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: str | Path) -> Path:
    return Path(root) / "evidence" / "evidences.json"


def _load(root: str | Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = data.get("evidences") if isinstance(data, dict) else None
    return items if isinstance(items, dict) else {}


def _save(root: str | Path, data: dict[str, dict[str, Any]]) -> None:
    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"evidences": data}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def resolve_locator(root: str | Path, locator: str) -> str:
    """解析 locator; 不可解析 -> ValueError (LLM 文本不自动成为 Evidence)。"""
    loc = str(locator or "")
    if loc.startswith("file:"):
        target = Path(loc[len("file:"):])
        path = target if target.is_absolute() else Path(root) / target
        if not path.is_file():
            raise ValueError(f"evidence file 不存在: {path}")
        return str(path)
    if loc.startswith("output:"):
        eid = loc[len("output:"):] or ""
        path = Path(root) / "execution" / "outputs" / f"{eid}.json"
        if not path.is_file():
            raise ValueError(f"evidence output 不存在: {eid}")
        return str(path)
    raise ValueError(f"不可解析的 locator (需 file: 或 output:): {loc!r}")


def create_evidence(root: str | Path, *, execution_id: str, type: str, source: str,
                    locator: str, summary: str = "",
                    verification_id: str = "") -> dict[str, Any]:
    from .os_core_execution import get_execution
    from .os_core_verification import get_verification

    if type not in EVIDENCE_TYPES:
        raise ValueError(f"未知 evidence type: {type} (可选: {EVIDENCE_TYPES})")
    if get_execution(root, execution_id) is None:
        raise ValueError(f"Execution 不存在: {execution_id}")
    verification_id = str(verification_id or "")
    if verification_id:
        ver = get_verification(root, verification_id)
        if ver is None:
            raise ValueError(f"Verification 不存在: {verification_id}")
        if ver["execution_id"] != str(execution_id):
            raise ValueError("Verification 不属于该 Execution")
    resolve_locator(root, locator)          # 不可解析 → 拒绝
    data = _load(root)
    eid = f"EV-{uuid.uuid4().hex[:10]}"
    rec = {"evidence_id": eid, "execution_id": str(execution_id),
           "verification_id": verification_id, "type": type, "source": source,
           "locator": locator, "summary": summary, "created_at": _now_iso()}
    data[eid] = rec
    _save(root, data)
    return rec


def get_evidence(root: str | Path, evidence_id: str) -> dict[str, Any] | None:
    return _load(root).get(str(evidence_id))


def resolve_evidence(root: str | Path, evidence_id: str) -> dict[str, Any]:
    """解析 Evidence -> 真实来源路径 (证据可定位)。"""
    rec = get_evidence(root, evidence_id)
    if rec is None:
        raise ValueError(f"Evidence 不存在: {evidence_id}")
    return {**rec, "resolved_path": resolve_locator(root, rec["locator"])}


def list_evidences(root: str | Path, *, execution_id: str = "",
                   verification_id: str = "") -> list[dict[str, Any]]:
    recs = list(_load(root).values())
    if execution_id:
        recs = [r for r in recs if r["execution_id"] == str(execution_id)]
    if verification_id:
        recs = [r for r in recs if r["verification_id"] == str(verification_id)]
    return sorted(recs, key=lambda r: (r.get("created_at", ""), r["evidence_id"]))


__all__ = ["EVIDENCE_TYPES", "create_evidence", "get_evidence", "list_evidences",
           "resolve_evidence", "resolve_locator"]
