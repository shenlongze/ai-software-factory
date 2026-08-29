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
    """完整状态视图 (含 node_runs 详情)。"""
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
        node_details.append(det)
    out = dict(run)
    out["node_runs"] = node_details
    return out


def history(root: Path | str, run_id: str) -> dict[str, Any]:
    """append-only 执行历史。"""
    run = get_production_run(root, run_id)
    if run is None:
        raise ProductionServiceError(f"ProductionRun 不存在: {run_id}")
    return {"run_id": run_id, "state": run.get("state"), "history": run.get("history", [])}


def list_runs(root: Path | str) -> list[dict[str, Any]]:
    return list_production_runs(root)
