"""factory-console/production_run.py — S3 ProductionRun / Workflow Orchestration.

AI Factory 2.0 第三个 Production Primitive: 多个 Node 组成真实生产流程。

- Workflow: 定义 (node 列表 + 依赖) — 可复用模板
- ProductionRun: 一次执行事实 (状态机 PENDING→RUNNING→COMPLETED/FAILED/BLOCKED)
- 串行 DAG (第一版): Node A → B → C, B depends_on A
- Artifact binding: Node B 的输入 = Node A 的 Artifact (显式关系, 无 hidden state)
- 每个 Node 走 NodeRun → Artifact → S1 Lifecycle (ProductionRun 不直接改 Workspace)
- 失败语义: A FAILED → B BLOCKED (不执行), ProductionRun FAILED

设计决策 (S3):
- 不复用旧 workflow_runner (它直接写 workspace, 绕 Artifact Lifecycle — Legacy Conflict)
- 不引入并行调度 (串行优先, 真实生产优先)
- 不删除旧代码 (Scope Firewall)
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ------------------------------------------------------------------ 状态

#: ProductionRun 生命周期
PRUN_STATES = ("PENDING", "RUNNING", "COMPLETED", "FAILED", "BLOCKED")

#: 合法转换
PRUN_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "PENDING": ("RUNNING",),
    "RUNNING": ("COMPLETED", "FAILED", "BLOCKED"),
    "COMPLETED": (),
    "FAILED": (),
    "BLOCKED": (),
}


class ProductionRunError(Exception):
    """ProductionRun 非法操作。"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _workflows_dir(root: Path | str) -> Path:
    return Path(root) / "workflows"


def _wf_path(root: Path | str, workflow_id: str) -> Path:
    return _workflows_dir(root) / "definitions" / f"{workflow_id}.json"


def _prun_path(root: Path | str, run_id: str) -> Path:
    return _workflows_dir(root) / "runs" / f"{run_id}.json"


_lock = threading.RLock()


# ------------------------------------------------------------------ Workflow (定义)

def register_workflow(
    root: Path | str,
    *,
    workflow_id: str,
    name: str,
    project_id: str | None = None,
    nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """注册 Workflow 定义 (可复用模板)。

    nodes: [{node_id, depends_on: [node_id...], executor_name, input_binding: {...}}]
    input_binding: {field: "artifact:<node_id>"} — Node 输入字段来自某 Node 的 Artifact。
    """
    wf: dict[str, Any] = {
        "workflow_id": workflow_id,
        "name": name,
        "project_id": project_id,
        "nodes": nodes or [],
        "created_at": _now_iso(),
    }
    # 校验依赖存在
    ids = {n["node_id"] for n in (nodes or [])}
    for n in (nodes or []):
        for dep in n.get("depends_on", []):
            if dep not in ids:
                raise ProductionRunError(f"Workflow {workflow_id}: 依赖 {dep} 不在节点列表")
    with _lock:
        p = _wf_path(root, workflow_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    return wf


def get_workflow(root: Path | str, workflow_id: str) -> dict[str, Any] | None:
    p = _wf_path(root, workflow_id)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ ProductionRun (执行事实)

def create_production_run(
    root: Path | str,
    workflow_id: str,
    *,
    input_data: dict[str, Any] | None = None,
    trigger: str = "user",
) -> dict[str, Any]:
    """实例化 ProductionRun: PENDING。"""
    wf = get_workflow(root, workflow_id)
    if wf is None:
        raise ProductionRunError(f"Workflow 不存在: {workflow_id}")
    run_id = f"prun-{uuid.uuid4().hex[:12]}"
    run: dict[str, Any] = {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "project_id": wf.get("project_id"),
        "state": "PENDING",
        "status": "PENDING",   # 兼容视图 (单一权威 = state)
        "input": input_data or {},
        "trigger": trigger,
        "node_runs": [],       # [{node_id, run_id, state, artifact_id}]
        "artifacts": [],       # [artifact_id...] (引用, 不复制内容)
        "failure": None,
        "started_at": None,
        "completed_at": None,
        "created_at": _now_iso(),
        "history": [],
    }
    with _lock:
        _write(root, run)
    _record(root, run, "PENDING", actor="system", note="created")
    return run


def get_production_run(root: Path | str, run_id: str) -> dict[str, Any] | None:
    p = _prun_path(root, run_id)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def list_production_runs(root: Path | str) -> list[dict[str, Any]]:
    base = _workflows_dir(root) / "runs"
    if not base.is_dir():
        return []
    out = []
    for f in sorted(base.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                out.append(d)
        except (OSError, ValueError):
            continue
    return out


def _write(root: Path | str, run: dict[str, Any]) -> None:
    p = _prun_path(root, run["run_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")


def _record(root: Path | str, run: dict[str, Any], to_state: str, *, actor: str, note: str) -> None:
    run["history"].append({"from": run.get("state"), "to": to_state, "actor": actor,
                           "at": _now_iso(), "note": note})
    run["state"] = to_state
    run["status"] = to_state
    _write(root, run)
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            f"PRODUCTION_RUN_{to_state}",
            trace_id=run["run_id"],
            project_id=run.get("project_id") or "",
            agent_id=actor,
            actor_type="system",
            actor_id=actor,
            action=f"production_run.{to_state.lower()}",
            source="production_run",
            decision="allow",
            decision_reason="production run transition",
            evidence=[{"run_id": run["run_id"], "workflow_id": run["workflow_id"], "note": note}],
            result={"ok": True},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ 执行 (串行)

def execute_production_run(
    root: Path | str,
    run_id: str,
    *,
    executor_factory: Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]],
    artifact_root: Path | str | None = None,
    actor: str = "system",
) -> dict[str, Any]:
    """执行 ProductionRun: 串行依赖解析 → 每 Node create NodeRun + execute。

    executor_factory(node_id) → executor_fn (Node 的执行器, 统一契约).
    每个 Node 产出 Artifact → binding 到下游 Node 输入。
    """
    from .node_runtime import (
        register_node, create_node_run, execute_node_run, get_node_run, NodeError,
    )

    with _lock:
        run = get_production_run(root, run_id)
        if run is None:
            raise ProductionRunError(f"ProductionRun 不存在: {run_id}")
        if run.get("state") != "PENDING":
            raise ProductionRunError(f"非 PENDING (当前: {run.get('state')})")
        wf = get_workflow(root, run["workflow_id"])
        _record(root, run, "RUNNING", actor=actor, note="started")
        run["started_at"] = _now_iso()
        _write(root, run)

    nodes = wf["nodes"]
    # 拓扑: 串行, 按依赖解析 (依赖先执行)
    executed: dict[str, dict[str, Any]] = {}  # node_id -> {run_id, artifact_id, state}
    artifacts: dict[str, str] = {}            # node_id -> artifact_id
    ar = Path(artifact_root or root)

    for node_spec in nodes:
        node_id = node_spec["node_id"]
        deps = node_spec.get("depends_on", [])
        # 依赖检查
        dep_failed = None
        for dep in deps:
            dep_rec = executed.get(dep)
            if dep_rec is None:
                dep_failed = f"依赖 {dep} 未执行 (节点顺序错误)"
                break
            if dep_rec["state"] != "COMPLETED":
                dep_failed = f"依赖 {dep} 未成功 (state={dep_rec['state']})"
                break
        if dep_failed:
            with _lock:
                run = get_production_run(root, run_id)
                run["node_runs"].append({"node_id": node_id, "run_id": None,
                                         "state": "BLOCKED", "artifact_id": None,
                                         "reason": dep_failed})
                run["failure"] = f"Node {node_id} BLOCKED: {dep_failed}"
                _write(root, run)
            # BLOCKED → 整个 ProductionRun BLOCKED
            with _lock:
                run = get_production_run(root, run_id)
                _record(root, run, "BLOCKED", actor=actor, note=dep_failed)
            return run

        # 构建 Node 输入: 显式 binding (input_binding: {field: "artifact:<node_id>"})
        node_input = dict(run.get("input") or {})
        binding = node_spec.get("input_binding") or {}
        for field, src in binding.items():
            if isinstance(src, str) and src.startswith("artifact:"):
                src_node = src.split(":", 1)[1]
                if src_node not in artifacts:
                    with _lock:
                        run = get_production_run(root, run_id)
                        run["failure"] = f"Node {node_id}: binding {field} 引用 {src_node} 无 artifact"
                        _record(root, run, "FAILED", actor=actor, note="binding missing")
                    return run
                node_input[field] = artifacts[src_node]
            else:
                node_input[field] = src

        # 注册 Node 定义 (若不存在)
        try:
            register_node(ar, node_id=node_id, name=node_spec.get("name", node_id),
                          node_type=node_spec.get("type", "engineering"))
        except Exception:  # noqa: BLE001 — 已存在则复用
            pass

        # 创建 NodeRun
        try:
            nr = create_node_run(ar, node_id, input_data=node_input, trigger="production")
        except NodeError as exc:
            with _lock:
                run = get_production_run(root, run_id)
                run["failure"] = f"Node {node_id}: {exc}"
                _record(root, run, "FAILED", actor=actor, note=str(exc)[:120])
            return run

        # 执行
        executor_fn = executor_factory(node_id)
        done = execute_node_run(ar, nr["run_id"], executor_fn=executor_fn,
                                executor_name=node_spec.get("executor_name", "node-exec"),
                                artifact_root=str(ar))

        with _lock:
            run = get_production_run(root, run_id)
            run["node_runs"].append({
                "node_id": node_id, "run_id": nr["run_id"],
                "state": done["state"], "artifact_id": done.get("artifact_id"),
            })
            if done.get("artifact_id"):
                artifacts[node_id] = done["artifact_id"]
                run["artifacts"].append(done["artifact_id"])
            _write(root, run)

        executed[node_id] = {"run_id": nr["run_id"], "artifact_id": done.get("artifact_id"),
                             "state": done["state"]}

        if done["state"] != "COMPLETED":
            with _lock:
                run = get_production_run(root, run_id)
                run["failure"] = f"Node {node_id} {done['state']}: {done.get('failure_reason') or ''}"
                _record(root, run, "FAILED", actor=actor, note=f"node {node_id} {done['state']}")
            return run

    # 全部成功
    with _lock:
        run = get_production_run(root, run_id)
        run["completed_at"] = _now_iso()
        _record(root, run, "COMPLETED", actor=actor, note="all nodes completed")
    return run
