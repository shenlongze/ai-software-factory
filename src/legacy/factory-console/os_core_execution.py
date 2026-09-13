"""factory-console/os_core_execution.py — OS Core: Execution (MU-CORE-09).

Execution = TaskNode 的一次实际执行事实 (一个 TaskNode 可有多次 Execution)。

语义: TaskNode ≠ Execution ≠ NodeRun。Execution 只保存引用与执行事实,
不复制 Capability/Workforce/Agent Profile 定义。
因果引用: Execution.resolution_id -> Resolution -> Capability/PR/Workforce/Identity。

SSOT: <root>/execution/executions.json (EX-*, single writer + 原子写)。
范围外: 真实 executor 调用 / Plugin Closure / Verification / Evidence / Outcome (后续 MU)。
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXECUTION_STATES: tuple[str, ...] = ("queued", "running", "succeeded", "failed", "cancelled")
EXECUTION_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "queued": ("running", "cancelled"),
    "running": ("succeeded", "failed", "cancelled"),
    "succeeded": (),
    "failed": (),
    "cancelled": (),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: str | Path) -> Path:
    return Path(root) / "execution" / "executions.json"


def _load(root: str | Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = data.get("executions") if isinstance(data, dict) else None
    return items if isinstance(items, dict) else {}


def _save(root: str | Path, data: dict[str, dict[str, Any]]) -> None:
    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"executions": data}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def create_execution(root: str | Path, *, task_node_id: str, resolution_id: str = "",
                     actor_identity_id: str = "", workforce_id: str = "",
                     input_refs: list[str] | None = None,
                     execution_id: str | None = None) -> dict[str, Any]:
    """创建一次 Execution (queued)。校验上下游引用与因果一致性。"""
    from .os_core_identity import get_identity
    from .os_core_resolution import get_resolution
    from .os_core_task_node import get_task_node
    from .os_core_workforce import get_workforce

    if get_task_node(root, task_node_id) is None:
        raise ValueError(f"TaskNode 不存在: {task_node_id}")
    resolution_id = str(resolution_id or "")
    resolution = None
    if resolution_id:
        resolution = get_resolution(root, resolution_id)
        if resolution is None:
            raise ValueError(f"Resolution 不存在: {resolution_id}")
    actor_identity_id = str(actor_identity_id or "")
    if actor_identity_id and get_identity(root, actor_identity_id) is None:
        raise ValueError(f"Identity 不存在: {actor_identity_id}")
    workforce_id = str(workforce_id or "")
    if workforce_id and get_workforce(root, workforce_id) is None:
        raise ValueError(f"Workforce 不存在: {workforce_id}")
    # 因果一致性: 若指定 resolution, 则 company 上下文必须一致 (T3/T26)
    if resolution is not None:
        from .os_core_task import resolve_task
        from .os_core_task_node import get_task_node as _get_node

        _node = _get_node(root, task_node_id)
        _chain = resolve_task(root, _node["task_id"])
        _node_company = str(_chain["project"].get("company_id") or "")
        _res_company = str((resolution.get("request") or {}).get("company_id") or "")
        if _node_company != _res_company:
            raise ValueError(
                f"Resolution {resolution_id} 属于 company {_res_company!r}, "
                f"TaskNode 属于 {_node_company!r} — 跨 company 拒绝")
    # 因果一致性: 若指定 resolution, 则 actor/workforce 必须来自该 resolution 的 match
    if resolution is not None:
        m_wf = {m["workforce_id"] for m in resolution.get("matches", []) if m.get("workforce_id")}
        m_id = {m["identity_id"] for m in resolution.get("matches", []) if m.get("identity_id")}
        if workforce_id and m_wf and workforce_id not in m_wf:
            raise ValueError(f"Workforce {workforce_id} 不在 Resolution {resolution_id} 的 match 中")
        if actor_identity_id and m_id and actor_identity_id not in m_id:
            raise ValueError(f"Identity {actor_identity_id} 不在 Resolution {resolution_id} 的 match 中")
    data = _load(root)
    eid = execution_id or f"EX-{uuid.uuid4().hex[:10]}"
    if eid in data:
        raise ValueError(f"Execution 已存在: {eid}")
    now = _now_iso()
    rec = {"execution_id": eid, "task_node_id": str(task_node_id),
           "resolution_id": resolution_id, "status": "queued",
           "actor_identity_id": actor_identity_id, "workforce_id": workforce_id,
           "runtime_ref": "", "node_run_id": "", "provider": "",
           "plugin_id": "", "implementation_ref": "",
           "termination_reason": "", "duration_ms": None, "pid": None,
           "exit_code": None, "signal": None, "timeout_seconds": None,
           "usage_refs": [],
           "started_at": "", "completed_at": "",
           "input_refs": [str(x) for x in (input_refs or [])],
           "output_refs": [], "error": "",
           "verification_refs": [], "evidence_refs": [],
           "created_at": now, "updated_at": now}
    data[eid] = rec
    _save(root, data)
    return rec


def get_execution(root: str | Path, execution_id: str) -> dict[str, Any] | None:
    return _load(root).get(str(execution_id))


def list_executions(root: str | Path, *, task_node_id: str = "",
                    status: str = "") -> list[dict[str, Any]]:
    recs = list(_load(root).values())
    if task_node_id:
        recs = [r for r in recs if r["task_node_id"] == str(task_node_id)]
    if status:
        recs = [r for r in recs if r["status"] == str(status)]
    return sorted(recs, key=lambda r: (r.get("created_at", ""), r["execution_id"]))


def set_execution_status(root: str | Path, execution_id: str, target: str, *,
                         error: str = "", output_refs: list[str] | None = None,
                         runtime_ref: str = "", node_run_id: str = "",
                         provider: str = "", plugin_id: str = "",
                         implementation_ref: str = "", termination_reason: str = "",
                         duration_ms: int | None = None, pid: int | None = None,
                         exit_code: int | None = None, signal: int | None = None,
                         timeout_seconds: int | None = None,
                         usage_refs: list[str] | None = None) -> dict[str, Any]:
    """Execution 生命周期 (queued→running→succeeded/failed/cancelled)。"""
    if target not in EXECUTION_STATES:
        raise ValueError(f"未知状态: {target}")
    data = _load(root)
    rec = data.get(str(execution_id))
    if rec is None:
        raise ValueError(f"Execution 不存在: {execution_id}")
    current = rec["status"]
    if target == current:
        return rec
    if target not in EXECUTION_TRANSITIONS.get(current, ()):
        raise ValueError(f"非法状态迁移: {current} → {target}")
    rec["status"] = target
    if target == "running" and not rec["started_at"]:
        rec["started_at"] = _now_iso()
    if target in ("succeeded", "failed", "cancelled"):
        rec["completed_at"] = _now_iso()
    if error:
        rec["error"] = error
    if output_refs is not None:
        rec["output_refs"] = [str(x) for x in output_refs]
    if runtime_ref:
        rec["runtime_ref"] = str(runtime_ref)
    if node_run_id:
        rec["node_run_id"] = str(node_run_id)
    if provider:
        rec["provider"] = str(provider)
    if plugin_id:
        rec["plugin_id"] = str(plugin_id)
    if implementation_ref:
        rec["implementation_ref"] = str(implementation_ref)
    for _k, _v in (("termination_reason", termination_reason), ("duration_ms", duration_ms),
                   ("pid", pid), ("exit_code", exit_code), ("signal", signal),
                   ("timeout_seconds", timeout_seconds)):
        if _v not in ("", None):
            rec[_k] = _v
    if usage_refs is not None:
        rec["usage_refs"] = [str(u) for u in usage_refs]
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


def cancel_execution(root: str | Path, execution_id: str, *,
                     reason: str = "user_cancelled") -> dict[str, Any]:
    """取消 Execution (terminal 不可变: 已终态 → NO-OP)。

    queued → cancelled; running → 先经 Runtime 真实终止进程, 再 cancelled。
    """
    from .os_core_runtime import mark_cancelling, terminate_running_process

    rec = get_execution(root, execution_id)
    if rec is None:
        raise ValueError(f"Execution 不存在: {execution_id}")
    if rec["status"] in ("succeeded", "failed", "cancelled"):
        return {**rec, "already_terminal": True, "terminated": False}
    if rec["status"] == "running":
        mark_cancelling(execution_id)
        term = terminate_running_process(root, execution_id)
        duration_ms = None
        if rec.get("started_at"):
            try:
                from datetime import datetime, timezone

                t0 = datetime.fromisoformat(str(rec["started_at"]))
                duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
            except Exception:  # noqa: BLE001 — 时间解析失败 → 不伪造
                duration_ms = None
        rec = set_execution_status(root, execution_id, "cancelled",
                                   error=str(reason), termination_reason=str(reason),
                                   pid=term.get("pid"), exit_code=term.get("exit_code"),
                                   signal=term.get("signal"), duration_ms=duration_ms)
        return {**rec, "already_terminal": False, "terminated": bool(term.get("terminated"))}
    rec = set_execution_status(root, execution_id, "cancelled", error=str(reason),
                               termination_reason=str(reason))
    return {**rec, "already_terminal": False, "terminated": False}

__all__ = ["EXECUTION_STATES", "EXECUTION_TRANSITIONS", "create_execution", "get_execution",
           "list_executions", "set_execution_status"]
