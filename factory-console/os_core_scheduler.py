"""factory-console/os_core_scheduler.py — OS Core Service: Scheduler (MU-CORE-12).

Scheduler 决定"哪个 TaskNode 现在可以被调度", 并创建 OS Execution (不执行)。

职责边界:
    Scheduler → (readiness) → create OS Execution → [由调用方/Runtime Integration 继续]
    Scheduler 不调用 Provider / Runtime / node_runtime; 不拥有 Execution/TaskNode 真相;
    不实现 Verification; 不新建 execution store。

依赖语义 (业务完成, 非 Execution.succeeded):
    前驱 TaskNode 必须存在 **accepted Outcome** 才算完成; Execution.succeeded + Verification failed
    → Outcome rejected → 后继仍然 blocked。

Idempotency: 同一 TaskNode 同时最多一个 active(queued/running) Execution; 重复调度 = NO-OP。
SSOT: 读取 os_core_{task,task_node,resolution,execution,outcome}; 只通过 os_core_execution 创建 Execution。
"""
from __future__ import annotations

import contextlib
import threading
from pathlib import Path
from typing import Any, Iterator

DECISIONS: tuple[str, ...] = ("ready", "blocked", "completed", "cancelled", "unresolved")
_ACTIVE_STATES = ("queued", "running")
_PROCESS_LOCK = threading.RLock()


@contextlib.contextmanager
def _lock(root: str | Path) -> Iterator[None]:
    """调度互斥 (复用 fcntl 文件锁; 不可用 → 线程锁)。防止并发重复调度。"""
    lock_path = Path(root) / "scheduler" / ".lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _PROCESS_LOCK:
        fh = None
        try:
            try:
                import fcntl

                fh = open(lock_path, "a+")          # noqa: SIM115
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            except Exception:  # noqa: BLE001 — fcntl 不可用 → 仅线程锁
                fh = None
            yield
        finally:
            if fh is not None:
                try:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except Exception:  # noqa: BLE001
                    pass
                fh.close()


# ---------------------------------------------------------------- facts

def _active_execution(root: str | Path, task_node_id: str) -> dict[str, Any] | None:
    from .os_core_execution import list_executions

    for e in list_executions(root, task_node_id=task_node_id):
        if e["status"] in _ACTIVE_STATES:
            return e
    return None


def _accepted_outcome(root: str | Path, task_node_id: str) -> dict[str, Any] | None:
    from .os_core_execution import list_executions
    from .os_core_outcome import list_outcomes

    for e in list_executions(root, task_node_id=task_node_id):
        for o in list_outcomes(root, execution_id=e["execution_id"]):
            if o["status"] == "accepted":
                return o
    return None


# ---------------------------------------------------------------- evaluate

def evaluate_node(root: str | Path, task_node_id: str) -> dict[str, Any]:
    """判定 TaskNode 是否可调度 (deterministic, 可解释; 不产生副作用)。"""
    from .os_core_task import get_task
    from .os_core_task_node import get_task_node, resolve_task_node

    out: dict[str, Any] = {"task_node_id": str(task_node_id), "decision": "blocked",
                           "reasons": [], "resolution_id": "", "workforce_id": "",
                           "identity_id": "", "company_id": ""}
    node = get_task_node(root, task_node_id)
    if node is None:
        return {**out, "reasons": ["TaskNode 不存在"]}
    task = get_task(root, node["task_id"])
    if task is None:
        return {**out, "reasons": [f"Task 不存在: {node['task_id']}"]}
    try:
        chain = resolve_task_node(root, task_node_id)       # TaskNode→Task→Work→Project
    except ValueError as exc:
        return {**out, "reasons": [f"上游链不完整: {exc}"]}
    out["company_id"] = str(chain["project"].get("company_id") or "")

    if node["status"] == "cancelled" or task["status"] == "cancelled":
        return {**out, "decision": "cancelled", "reasons": ["TaskNode/Task 已取消"]}
    if node["status"] == "completed":
        return {**out, "decision": "completed", "reasons": ["TaskNode 已完成"]}
    if task["status"] == "completed":
        return {**out, "decision": "completed", "reasons": ["Task 已完成"]}
    if _accepted_outcome(root, task_node_id) is not None:
        return {**out, "decision": "completed", "reasons": ["已存在 accepted Outcome (不重复调度)"]}
    if node["status"] == "running":
        return {**out, "decision": "blocked", "reasons": ["TaskNode 正在运行"]}
    if _active_execution(root, task_node_id) is not None:
        active = _active_execution(root, task_node_id)
        return {**out, "decision": "blocked",
                "reasons": [f"已有 active Execution: {active['execution_id']}"]}

    # 依赖: 前驱必须有 accepted Outcome (业务完成, 非 Execution.succeeded)
    from .os_core_task_node import list_task_nodes

    node_map = {n["task_node_id"]: n for n in list_task_nodes(root, task_id=node["task_id"])}
    blocked: list[str] = []
    for dep in node.get("depends_on", []):
        dep_node = node_map.get(dep)
        if dep_node is None:
            blocked.append(f"前驱缺失: {dep}")
            continue
        if _accepted_outcome(root, dep) is None:
            blocked.append(f"前驱 {dep} 未 accepted (Execution 成功不等于业务完成)")
    if blocked:
        return {**out, "decision": "blocked", "reasons": blocked}

    if not node.get("required_capability_refs"):
        return {**out, "decision": "unresolved", "reasons": ["无 required_capability_refs"]}
    from .os_core_resolution import find_resolution_for_task_node, resolve_task_node

    resolution = (find_resolution_for_task_node(root, task_node_id)
                  or resolve_task_node(root, task_node_id))
    if resolution["status"] != "resolved" or not resolution.get("matches"):
        return {**out, "decision": "unresolved",
                "reasons": [f"Resolution 未解析: {resolution.get('reason') or resolution['status']}",
                            *[f"unresolved: {c}" for c in resolution.get("unresolved_capabilities", [])]]}
    match = resolution["matches"][0]
    if not match.get("workforce_id") or not match.get("identity_id"):
        return {**out, "decision": "unresolved",
                "reasons": ["Resolution 缺少 workforce/identity"]}
    return {**out, "decision": "ready",
            "reasons": ["dependencies satisfied", "capability available",
                        "resolution resolved", "no active execution"],
            "resolution_id": resolution["resolution_id"],
            "workforce_id": match["workforce_id"], "identity_id": match["identity_id"]}


# ---------------------------------------------------------------- schedule

def schedule_node(root: str | Path, task_node_id: str) -> dict[str, Any]:
    """evaluate + (ready 时) 创建 OS Execution; 重复调度 = NO-OP。"""
    with _lock(root):
        ev = evaluate_node(root, task_node_id)
        if ev["decision"] != "ready":
            return {**ev, "scheduled": False, "execution_id": ""}
        from .os_core_execution import create_execution

        ex = create_execution(root, task_node_id=task_node_id,
                              resolution_id=ev["resolution_id"],
                              actor_identity_id=ev["identity_id"],
                              workforce_id=ev["workforce_id"])
        return {**ev, "scheduled": True, "execution_id": ex["execution_id"], "execution": ex}


def schedule_ready(root: str | Path, *, task_id: str = "") -> dict[str, Any]:
    """批量: 评估(并调度) Task 下所有 TaskNode; 返回 decisions + scheduled。"""
    from .os_core_task_node import list_task_nodes

    decisions, scheduled = [], []
    for node in list_task_nodes(root, task_id=task_id):
        r = schedule_node(root, node["task_node_id"])
        decisions.append({k: r[k] for k in ("task_node_id", "decision", "reasons")})
        if r.get("scheduled"):
            scheduled.append(r["execution_id"])
    return {"decisions": decisions, "scheduled": scheduled}


__all__ = ["DECISIONS", "evaluate_node", "schedule_node", "schedule_ready"]
