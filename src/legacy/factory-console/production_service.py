"""factory-console/production_service.py — S6 ProductionRun Service.

CLI 与 API 共享的统一 ProductionRun 入口 (S6 架构: 禁止两套 orchestration)。

- create(root, workflow_id, input) → run_id
- start(root, run_id, executor_factory) → 执行 (真实外部 executor)
- status(root, run_id) → 完整状态 (node_runs/artifacts/verification/failure)
- history(root, run_id) → append-only 历史
- 全部通过 production_run 持久化事实读取 (单一事实源)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .production_run import (
    get_workflow, create_production_run, execute_production_run,
    get_production_run, list_production_runs, ProductionRunError,
)
from .node_runtime import get_node_run


class ProductionServiceError(Exception):
    """Production Service 错误。"""


def create(root: Path | str, workflow_id: str, *,
           input_data: dict[str, Any] | None = None, trigger: str = "cli") -> dict[str, Any]:
    """创建 ProductionRun (PENDING)。校验 workflow 存在。"""
    wf = get_workflow(root, workflow_id)
    if wf is None:
        raise ProductionServiceError(f"Workflow 不存在: {workflow_id}")
    try:
        run = create_production_run(root, workflow_id, input_data=input_data, trigger=trigger)
    except ProductionRunError as exc:
        raise ProductionServiceError(str(exc)) from exc
    return run


def start(root: Path | str, run_id: str, *,
          executor_factory: Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]],
          artifact_root: Path | str | None = None) -> dict[str, Any]:
    """启动 ProductionRun (RUNNING→COMPLETED/FAILED/BLOCKED)。"""
    try:
        return execute_production_run(root, run_id, executor_factory=executor_factory,
                                      artifact_root=artifact_root)
    except ProductionRunError as exc:
        raise ProductionServiceError(str(exc)) from exc


def status(root: Path | str, run_id: str) -> dict[str, Any]:
    """完整状态视图 (含 node_runs 详情 + recovery 分析 + timeline)。"""
    run = get_production_run(root, run_id)
    if run is None:
        raise ProductionServiceError(f"ProductionRun 不存在: {run_id}")
    # 补充每个 node_run 的 attempts/verification (从 node_runtime 读事实)
    node_details = []
    for nr in run.get("node_runs", []):
        det = dict(nr)
        if nr.get("run_id"):
            nr_rec = get_node_run(root, nr["run_id"])
            if nr_rec:
                det["attempts"] = len(nr_rec.get("attempts", []))
                det["verification"] = nr_rec.get("verification")
                det["failure_reason"] = nr_rec.get("failure_reason")
                det["timeline"] = [
                    {"state": h.get("to"), "at": h.get("at"), "note": h.get("note")}
                    for h in nr_rec.get("history", [])
                ]
        node_details.append(det)
    out = dict(run)
    out["node_runs"] = node_details
    # S8: recovery 分析视图 (只读)
    try:
        out["recovery"] = analyze(root, run_id)
    except Exception:  # noqa: BLE001
        out["recovery"] = {"recoverable": False, "reason": "分析失败"}
    return out


def history(root: Path | str, run_id: str) -> dict[str, Any]:
    """append-only 执行历史。"""
    run = get_production_run(root, run_id)
    if run is None:
        raise ProductionServiceError(f"ProductionRun 不存在: {run_id}")
    return {"run_id": run_id, "state": run.get("state"), "history": run.get("history", [])}


def list_runs(root: Path | str) -> list[dict[str, Any]]:
    return list_production_runs(root)


# ------------------------------------------------------------------ S8: Recovery Control + Observability

def analyze(root: Path | str, run_id: str) -> dict[str, Any]:
    """只读 Recovery 分析 (side-effect free): 是否可恢复 + 每 Node 动作。"""
    from .recovery import analyze as _rec_analyze, RecoveryError

    try:
        analysis = _rec_analyze(root, run_id)
    except RecoveryError as exc:
        raise ProductionServiceError(str(exc)) from exc
    # 可恢复性分类
    run = get_production_run(root, run_id)
    state = run.get("state") if run else "UNKNOWN"
    actions = {p["node_id"]: p["action"] for p in analysis["plan"]}
    has_resume = any(p["action"] == "RESUME" for p in analysis["plan"])
    if state == "COMPLETED":
        rec_state = "already_completed"
    elif state in ("FAILED", "BLOCKED", "RUNNING") and has_resume:
        rec_state = "recoverable"
    elif not analysis["plan"]:
        rec_state = "corrupt_state"
    else:
        rec_state = "not_recoverable"
    return {
        "run_id": run_id,
        "state": state,
        "recoverable_state": rec_state,
        "recoverable": rec_state == "recoverable",
        "reason": ("有可恢复 Node" if rec_state == "recoverable"
                   else "无可恢复 Node" if rec_state == "not_recoverable"
                   else "已全部完成" if rec_state == "already_completed"
                   else "状态异常/损坏"),
        "plan": analysis["plan"],
        "recommended_action": "recover" if rec_state == "recoverable" else "none",
    }


def recover(root: Path | str, run_id: str, *,
            executor_factory: Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]],
            artifact_root: Path | str | None = None) -> dict[str, Any]:
    """执行 Recovery (command): analyze → resume → 最终状态。"""
    from .recovery import resume as _rec_resume, RecoveryError

    analysis = analyze(root, run_id)
    prev_state = analysis["state"]
    if analysis["recoverable_state"] == "already_completed":
        return {"run_id": run_id, "previous_state": prev_state, "final_state": prev_state,
                "recovery_actions": [], "node_results": [],
                "message": "already completed, no-op"}
    if not analysis["recoverable"]:
        return {"run_id": run_id, "previous_state": prev_state, "final_state": prev_state,
                "recovery_actions": [], "node_results": [],
                "message": f"not recoverable: {analysis['reason']}"}
    try:
        done = _rec_resume(root, run_id, executor_factory=executor_factory,
                           artifact_root=artifact_root)
    except RecoveryError as exc:
        raise ProductionServiceError(str(exc)) from exc
    node_results = []
    for nr in done.get("node_runs", []):
        node_results.append({"node_id": nr.get("node_id"), "state": nr.get("state"),
                             "artifact_id": nr.get("artifact_id")})
    return {
        "run_id": run_id,
        "previous_state": prev_state,
        "final_state": done.get("state"),
        "recovery_actions": [{"node_id": p["node_id"], "action": p["action"]}
                             for p in analysis["plan"] if p["action"] != "SKIP"],
        "node_results": node_results,
        "failure": done.get("failure"),
        "message": f"recovered: {prev_state} → {done.get('state')}",
    }
