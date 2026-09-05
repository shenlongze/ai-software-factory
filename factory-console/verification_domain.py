"""factory-console/verification_domain.py — P0-F3 Verification SSOT (ver-*)。

设计 (方案 1 — 语义 A 升级为 SSOT):
- Verification 是独立、持久、可追踪的质量事实对象 (ver-*)。
- 唯一 canonical: 本模块 VerificationStore (<root>/verifications/verifications.json)。
- NodeRun.verification 从内嵌 dict 升级为 ver-* 物化 + 引用 (run 保留精简快照,
  canonical 指向 ver-* id; 不再产生第二事实源)。
- 状态: PASS / FAIL / UNKNOWN (+ INCONCLUSIVE/BLOCKED 兼容 execution metadata)。
  禁止把 "无验证" 当 PASS; EXS SUCCESS + Verification FAIL/UNKNOWN 是合法终态。
- 真实执行路径复用: verification.py (S5 subprocess) / external executor auto_verify /
  调用方传入的 verify metadata → 统一经 materialize_verification() 落盘。
- 幂等: 同 (task_run_id, attempt, verification_type) 已存在 → 返回现有 ver-* (不重复)。

F3 范围: 不做 Artifact/Evidence SSOT (F4), 不改 EXS/Task/TaskRun model 语义。
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: 状态 (canonical; F3 §4 — UNKNOWN 是真实语义, 非 PASS 的别名)
VERIFY_STATUS = ("PASS", "FAIL", "UNKNOWN", "INCONCLUSIVE", "BLOCKED")
#: 合法终态 (materialize 后可进入)
VERIFY_TERMINAL = ("PASS", "FAIL", "UNKNOWN", "INCONCLUSIVE", "BLOCKED")

_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _verifications_file(root: Path | str) -> Path:
    return Path(root) / "verifications" / "verifications.json"


def _load_all(root: Path | str) -> dict[str, dict[str, Any]]:
    p = _verifications_file(root)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # 损坏响亮失败 (store 铁律)
        raise ValueError(f"corrupt verifications store: {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"corrupt verifications store: {p}: not object")
    sec = raw.get("verifications")
    if not isinstance(sec, dict):
        return {}
    return {k: v for k, v in sec.items() if isinstance(v, dict)}


def _write_all(root: Path | str, records: dict[str, dict[str, Any]]) -> None:
    p = _verifications_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(
        json.dumps({"verifications": dict(sorted(records.items()))},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, p)


def get_verification(root: Path | str, verification_id: str) -> dict[str, Any] | None:
    """按 ver-* id 读取 (不存在 → None)。"""
    return _load_all(root).get(verification_id)


def list_verifications(root: Path | str,
                       task_run_id: str = "",
                       exs_id: str = "") -> list[dict[str, Any]]:
    """全部 (可按 task_run_id / exs_id 过滤, 审计友好排序)。"""
    recs = _load_all(root)
    out = []
    for v in recs.values():
        if task_run_id and v.get("task_run_id") != task_run_id:
            continue
        if exs_id and v.get("exs_id") != exs_id:
            continue
        out.append(v)
    return sorted(out, key=lambda v: str(v.get("created_at") or ""))


def count(root: Path | str) -> int:
    return len(_load_all(root))


def materialize_verification(
    root: Path | str,
    *,
    task_run_id: str = "",
    exs_id: str = "",
    status: str,
    verification_type: str = "task_run_execution",
    method: str = "",
    result: str = "",
    evidence_ref: list[str] | None = None,
    attempt: int = 0,
    detail: dict[str, Any] | None = None,
    actor: str = "verification",
    note: str = "",
) -> dict[str, Any]:
    """P0-F3 唯一写入口: verify metadata → ver-* SSOT 物化 (幂等)。

    status 规范化: 接受 PASS/FAIL/UNKNOWN/INCONCLUSIVE/BLOCKED;
    小写 pass/fail/unknown → 大写 (兼容 gateway auto_verify / EXS.verify 词汇)。
    幂等: 同 (task_run_id, attempt, verification_type, status 同源 method) 已存在
    → 返回现有 (不重复创建多个 canonical)。
    禁止: 无验证输入默认 PASS; status 非法 → ValueError (响亮, 不静默)。
    """
    norm = str(status or "").strip().upper()
    if norm in ("PASS", "FAIL", "UNKNOWN", "INCONCLUSIVE", "BLOCKED"):
        pass
    elif norm in ("", "NONE", "NULL"):
        raise ValueError("verification status required (禁止把无验证当 PASS)")
    else:
        raise ValueError(f"illegal verification status: {status!r}")

    with _lock:
        recs = _load_all(root)
        # 幂等: 同源同 attempt 同 type → 返回已有 (不双写)
        if task_run_id:
            for v in recs.values():
                if (v.get("task_run_id") == task_run_id
                        and v.get("attempt") == attempt
                        and v.get("verification_type") == verification_type):
                    return v
        vid = f"ver-{uuid.uuid4().hex[:10]}"
        now = _now_iso()
        rec: dict[str, Any] = {
            "verification_id": vid,
            "task_run_id": str(task_run_id or ""),
            "exs_id": str(exs_id or ""),
            "status": norm,
            "verification_type": str(verification_type or "task_run_execution"),
            "method": str(method or ""),
            "result": str(result or "")[:500],
            "evidence_ref": [str(x) for x in (evidence_ref or [])],
            "attempt": int(attempt or 0),
            "detail": detail or {},
            "actor": str(actor or "verification"),
            "note": str(note or "")[:300],
            "created_at": now,
            "completed_at": now if norm in VERIFY_TERMINAL else None,
        }
        recs[vid] = rec
        _write_all(root, recs)
        return rec


def emit_audit(root: Path | str, rec: dict[str, Any], event: str) -> None:
    """Verification audit observation (非 SSOT; 失败安全)。"""
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            event,
            trace_id=str(rec.get("verification_id") or ""),
            project_id="",
            agent_id=str(rec.get("actor") or "verification"),
            actor_type="system",
            actor_id=str(rec.get("actor") or "verification"),
            action=f"verification.{event.lower().replace('verification_', '')}",
            source="verification_domain",
            decision="allow",
            decision_reason=f"verification {rec.get('status')}",
            evidence=[{"verification_id": rec.get("verification_id"),
                       "task_run_id": rec.get("task_run_id"),
                       "exs_id": rec.get("exs_id"),
                       "status": rec.get("status")}],
            result={"ok": True, "status": rec.get("status")},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001 — 审计尽力而为
        pass
