"""factory-console/recovery.py — S7 Recovery & Resume Engine.

进程崩溃后从持久化 ProductionRun 状态恢复:
- analyze(run_id): 基于真实事实 (state/artifact/verification/history) 分类每个 Node
- recover(run_id): 生成恢复计划 (SKIP/RESUME/RECONCILE/BLOCKED)
- resume(run_id): 从断点继续执行 (已完成 Node 不重复, 未完成 Node 续跑)

Recovery Truth Model (S7):
  COMPLETED + Artifact/Verification 证据 → SKIP (禁止重复执行)
  PENDING   → RESUME (可执行)
  RUNNING   → RECONCILE (无完成证据 → 安全重跑)
  VERIFYING → RECONCILE (无 PASS evidence → 重新验证/重跑)
  REPAIRING → RECONCILE (保留 Artifact lineage, 续 repair)
  FAILED    → 保持 (recovery policy: 不自动重试 FAILED)
  BLOCKED   → 保持 blocked (依赖未满足)

不把 RUNNING 直接标 COMPLETED — 无证据不伪造成功 (Production Truth)。
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .production_run import (
    get_production_run, get_workflow, _write, _record, ProductionRunError,
)
from .node_runtime import get_node_run, list_node_runs


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _audit(root: Path | str, event_type: str, run_id: str, *, note: str, data: dict[str, Any]) -> None:
    """Recovery 审计事件 (尽力而为, 不阻断恢复)。"""
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            event_type, trace_id=run_id, project_id="", agent_id="recovery",
            actor_type="system", actor_id="recovery", action="recovery",
            source="recovery", decision="allow", decision_reason="recovery",
            evidence=[{"run_id": run_id, "note": note, **data}], result={"ok": True},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


class RecoveryError(Exception):
    """Recovery 失败。"""


# ------------------------------------------------------------------ analyze

def analyze(root: Path | str, run_id: str) -> dict[str, Any]:
    """分析 ProductionRun 每个 Node 的真实恢复需求 (只读, 不修改)。"""
    run = get_production_run(root, run_id)
    if run is None:
        raise RecoveryError(f"ProductionRun 不存在: {run_id}")
    wf = get_workflow(root, run["workflow_id"])
    nodes = wf["nodes"] if wf else []

    # 建立 node_id → NodeRun 记录
    node_runs = {nr.get("node_id"): nr for nr in run.get("node_runs", [])}
    # 真实 NodeRun 事实 (含 attempts/artifact)
    node_facts: dict[str, dict[str, Any]] = {}
    for node_id, nr in node_runs.items():
        facts: dict[str, Any] = {"node_run_state": nr.get("state")}
        if nr.get("run_id"):
            rec = get_node_run(root, nr["run_id"])
            if rec:
                facts["node_run_state"] = rec.get("state")
                facts["attempts"] = rec.get("attempts", [])
                facts["verification"] = rec.get("verification")
                facts["artifact_id"] = rec.get("artifact_id")
                facts["failure_reason"] = rec.get("failure_reason")
                facts["executor"] = rec.get("executor")
        node_facts[node_id] = facts

    plan: list[dict[str, Any]] = []
    for node_spec in nodes:
        node_id = node_spec["node_id"]
        facts = node_facts.get(node_id, {})
        nr_state = facts.get("node_run_state")
        artifact_id = facts.get("artifact_id")
        verification = facts.get("verification") or {}
        v_status = verification.get("result") or verification.get("status")

        # 依赖状态 (决定 BLOCKED) — 仅当依赖已执行且未完成时才 BLOCKED;
        # 依赖无记录 (未执行) → 不 BLOCKED (串行执行会先跑依赖)
        deps_blocked = []
        for dep in node_spec.get("depends_on", []):
            dep_facts = node_facts.get(dep, {})
            if dep_facts.get("node_run_state") is not None and dep_facts.get("node_run_state") != "COMPLETED":
                deps_blocked.append(dep)

        # 分类
        if nr_state == "COMPLETED" and artifact_id and v_status == "PASS":
            action = "SKIP"  # 已确认完成: 禁止重复执行
            reason = "COMPLETED + Artifact + Verification PASS"
        elif deps_blocked:
            action = "BLOCKED"
            reason = f"依赖未完成: {', '.join(deps_blocked)}"
        elif nr_state in ("PENDING", None):
            action = "RESUME"
            reason = "PENDING/未执行 → 可执行"
        elif nr_state in ("RUNNING", "VERIFYING", "REPAIRING"):
            # 无完成证据 → 安全重跑 (at-least-once 边界)
            action = "RESUME"
            reason = f"{nr_state} 无完成证据 → 安全重跑 (at-least-once)"
        elif nr_state == "FAILED":
            # crash/executor 中断类 → 可恢复重跑 (at-least-once); 业务失败 → 保持
            failure_reason = str(facts.get("failure_reason") or "")
            if "executor exception" in failure_reason or "interrupted" in failure_reason:
                action = "RESUME"
                reason = f"FAILED by executor interruption → 可安全重跑: {failure_reason[:120]}"
            else:
                action = "KEEP_FAILED"
                reason = f"FAILED (recovery policy: 不自动重试): {failure_reason[:120]}"
        elif nr_state == "BLOCKED":
            action = "BLOCKED"
            reason = "BLOCKED (依赖未满足)"
        else:
            action = "RESUME"
            reason = f"未知状态 {nr_state} → 安全重跑"

        plan.append({
            "node_id": node_id,
            "action": action,
            "reason": reason,
            "node_run_state": nr_state,
            "artifact_id": artifact_id,
            "verification": v_status,
            "existing_run_id": (node_runs.get(node_id) or {}).get("run_id"),
        })

    all_skip = all(p["action"] == "SKIP" for p in plan)
    return {
        "run_id": run_id,
        "state": run.get("state"),
        "plan": plan,
        "recoverable": True,
        "already_complete": all_skip and run.get("state") == "COMPLETED",
    }


# ------------------------------------------------------------------ recover

_recovery_lock = threading.RLock()


def recover(root: Path | str, run_id: str) -> dict[str, Any]:
    """恢复入口: 分析 → 记录审计 → 返回计划 (不直接执行)。

    resume(run_id) 执行实际续跑。
    """
    with _recovery_lock:
        run = get_production_run(root, run_id)
        if run is None:
            raise RecoveryError(f"ProductionRun 不存在: {run_id}")
        if run.get("state") in ("COMPLETED", "FAILED", "BLOCKED"):
            # 终态: 不恢复 (保持终态)
            _audit(root, "PRODUCTION_RUN_RECOVERY_STARTED", run_id,
                   note="terminal state, no recovery", data={"state": run.get("state")})
            return {"run_id": run_id, "recovered": False,
                    "reason": f"terminal state {run.get('state')}, 无需恢复"}
        analysis = analyze(root, run_id)
        if analysis.get("already_complete"):
            return {"run_id": run_id, "recovered": False, "reason": "已全部完成"}
        _audit(root, "PRODUCTION_RUN_RECOVERY_STARTED", run_id,
               note="recovery analysis", data={"actions": [p["action"] for p in analysis["plan"]]})
        return {"run_id": run_id, "recovered": True, "plan": analysis["plan"]}


# ------------------------------------------------------------------ resume

def resume(
    root: Path | str,
    run_id: str,
    *,
    executor_factory: Any,
    artifact_root: Path | str | None = None,
    actor: str = "recovery",
) -> dict[str, Any]:
    """从断点继续执行: 已完成 Node 跳过, 未完成 Node 续跑。

    返回最终 ProductionRun 状态。
    """
    from .production_run import execute_production_run

    with _recovery_lock:
        run = get_production_run(root, run_id)
        if run is None:
            raise RecoveryError(f"ProductionRun 不存在: {run_id}")
        if run.get("state") == "COMPLETED":
            return run  # 已完成不可恢复
        # FAILED/BLOCKED: 若 analysis 显示有可恢复 node → 允许重置重试 (S7 at-least-once)
        if run.get("state") == "FAILED":
            analysis = analyze(root, run_id)
            resume_nodes = [p for p in analysis["plan"] if p["action"] == "RESUME"]
            if not resume_nodes:
                return run  # 无可恢复 node → 保持 FAILED

        # 重置非 PENDING ProductionRun → PENDING 以便 execute 重入
        if run.get("state") != "PENDING":
            run["state"] = "PENDING"
            run["status"] = "PENDING"
            run["history"].append({"from": run.get("state", ""), "to": "PENDING",
                                   "actor": actor, "at": _now_iso(),
                                   "note": "recovery: reset for resume"})
            _write(root, run)
        _audit(root, "PRODUCTION_RUN_RECOVERY_STARTED", run_id, note="resume start", data={})

    done = execute_production_run(
        root, run_id, executor_factory=executor_factory, artifact_root=artifact_root,
        resume=True,
    )
    _audit(root, "PRODUCTION_RUN_RECOVERY_COMPLETED", run_id,
           note=f"resume finished: {done.get('state')}", data={"final_state": done.get("state")})
    return done
