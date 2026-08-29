"""factory-console/agent_kernel.py — S9 Agent Kernel (AI Workforce Kernel).

Agent = 专业员工定义 (复用 session/agent_entity.AgentEntity + AgentRegistry)
AgentRun = 一次工作事实 (agent_run_id/agent_id/production_run_id/state/refs/history)
Handoff = Artifact-centric 传递 (from_agent_run/to_agent/input_artifacts)

核心原则 (S9):
- Agent 只通过 Production Kernel 执行 (AgentRun 包 ProductionRun → NodeRun → Executor)
- Agent 不直接 subprocess / 不直接改 Workspace (I8/I9)
- Handoff 只通过 Artifact references (无 global/session hidden state)
- AgentRun 崩溃 → 复用 S7 Recovery (不建第二套)
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

#: AgentRun 生命周期 (复用 NodeRun 状态语义)
AGENTRUN_STATES = ("PENDING", "RUNNING", "VERIFYING", "COMPLETED", "FAILED", "BLOCKED")

AGENTRUN_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "PENDING": ("RUNNING",),
    "RUNNING": ("VERIFYING", "FAILED"),
    "VERIFYING": ("COMPLETED", "FAILED"),
    "COMPLETED": (),
    "FAILED": (),
    "BLOCKED": (),
}


class AgentKernelError(Exception):
    """Agent Kernel 错误。"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _runs_dir(root: Path | str) -> Path:
    return Path(root) / "agents" / "runs"


def _run_path(root: Path | str, run_id: str) -> Path:
    return _runs_dir(root) / f"{run_id}.json"


_lock = threading.RLock()


# ------------------------------------------------------------------ AgentRun

def _registry(root: Path | str):
    from .session.agent_registry import AgentRegistry

    return AgentRegistry(agents_file=Path(root) / "agents" / "factory_agents.json")


def create_agent_run(
    root: Path | str,
    agent_id: str,
    *,
    production_run_id: str | None = None,
    input_artifacts: list[str] | None = None,
    context_refs: dict[str, Any] | None = None,
    trigger: str = "cli",
) -> dict[str, Any]:
    """创建 AgentRun (PENDING)。Agent 定义必须存在 (Registry)。"""
    reg = _registry(root)
    agent = reg.get(agent_id)
    if agent is None:
        raise AgentKernelError(f"Agent 不存在: {agent_id} (请先注册 Agent)")
    run_id = f"agr-{uuid.uuid4().hex[:12]}"
    run: dict[str, Any] = {
        "agent_run_id": run_id,
        "agent_id": agent_id,
        "role": getattr(agent, "role", "") or agent_id,
        "production_run_id": production_run_id,
        "state": "PENDING",
        "status": "PENDING",
        "input_artifacts": input_artifacts or [],
        "output_artifacts": [],
        "context_refs": context_refs or {},
        "trigger": trigger,
        "failure": None,
        "created_at": _now_iso(),
        "started_at": None,
        "completed_at": None,
        "history": [],
    }
    with _lock:
        _write(root, run)
    _record(root, run, "PENDING", actor="system", note="created")
    return run


def get_agent_run(root: Path | str, run_id: str) -> dict[str, Any] | None:
    p = _run_path(root, run_id)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def list_agent_runs(root: Path | str, agent_id: str | None = None) -> list[dict[str, Any]]:
    base = _runs_dir(root)
    if not base.is_dir():
        return []
    out = []
    for f in sorted(base.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(d, dict) and (agent_id is None or d.get("agent_id") == agent_id):
                out.append(d)
        except (OSError, ValueError):
            continue
    return out


def _write(root: Path | str, run: dict[str, Any]) -> None:
    import os
    import tempfile

    p = _run_path(root, run["agent_run_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(run, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


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
            f"AGENT_RUN_{to_state}", trace_id=run["agent_run_id"],
            project_id=run.get("production_run_id") or "", agent_id=run["agent_id"],
            actor_type="system", actor_id=actor,
            action=f"agent_run.{to_state.lower()}", source="agent_kernel",
            decision="allow", decision_reason="agent run transition",
            evidence=[{"agent_run_id": run["agent_run_id"], "agent_id": run["agent_id"],
                       "production_run_id": run.get("production_run_id"), "note": note}],
            result={"ok": True},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ Agent Loop (经 Production Kernel)

def run_agent(
    root: Path | str,
    run_id: str,
    *,
    workflow_id: str,
    executor_factory: Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]],
    workflow_input: dict[str, Any] | None = None,
    actor: str = "system",
) -> dict[str, Any]:
    """执行 AgentRun: 创建 ProductionRun 底座 → execute → 关联 output artifacts。

    Agent 不直接执行 — 通过 Production Kernel (ProductionRun → NodeRun → Executor)。
    """
    from .production_run import (
        register_workflow, create_production_run, execute_production_run,
    )
    from .production_service import status as _prun_status

    with _lock:
        run = get_agent_run(root, run_id)
        if run is None:
            raise AgentKernelError(f"AgentRun 不存在: {run_id}")
        if run.get("state") != "PENDING":
            raise AgentKernelError(f"AgentRun 非 PENDING (当前: {run.get('state')})")
        _record(root, run, "RUNNING", actor=actor, note="agent loop started")
        run["started_at"] = _now_iso()
        _write(root, run)

    try:
        # 确保 workflow 存在 (复用, 不存在则注册 — Agent 的 workflow 是其专业流程)
        from .production_run import get_workflow

        if get_workflow(root, workflow_id) is None:
            register_workflow(root, workflow_id=workflow_id,
                              name=f"agent:{run['agent_id']}",
                              project_id=workflow_input.get("project_id") if workflow_input else None,
                              nodes=[{"node_id": "work", "name": "work", "type": "work",
                                      "executor_name": "work"}])

        prun = create_production_run(root, workflow_id,
                                     input_data=workflow_input or {}, trigger="agent")
        with _lock:
            run = get_agent_run(root, run_id)
            run["production_run_id"] = prun["run_id"]
            _write(root, run)

        done = execute_production_run(root, prun["run_id"],
                                      executor_factory=executor_factory,
                                      artifact_root=str(root))
        # 关联 output artifacts
        with _lock:
            run = get_agent_run(root, run_id)
            run["output_artifacts"] = done.get("artifacts", [])
            if done["state"] == "COMPLETED":
                run["completed_at"] = _now_iso()
                _record(root, run, "COMPLETED", actor=actor, note="production completed")
            else:
                run["failure"] = done.get("failure") or done.get("state")
                _record(root, run, "FAILED", actor=actor, note=run["failure"][:120] if run["failure"] else "failed")
            _write(root, run)
        return get_agent_run(root, run_id)
    except Exception as exc:  # noqa: BLE001
        with _lock:
            run = get_agent_run(root, run_id)
            run["failure"] = str(exc)
            _record(root, run, "FAILED", actor=actor, note=str(exc)[:120])
        return run


# ------------------------------------------------------------------ Handoff (Artifact-centric)

def create_handoff(
    root: Path | str,
    *,
    from_agent_run_id: str,
    to_agent_id: str,
    input_artifacts: list[str],
    context_refs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """创建 Handoff: from AgentRun → to Agent, 只传 Artifact references。

    校验: from run 存在且 COMPLETED (有输出); to agent 存在; artifacts 存在。
    """
    from .session.agent_registry import AgentRegistry

    reg = AgentRegistry(agents_file=Path(root) / "agents" / "factory_agents.json")
    from_run = get_agent_run(root, from_agent_run_id)
    if from_run is None:
        raise AgentKernelError(f"来源 AgentRun 不存在: {from_agent_run_id}")
    if from_run.get("state") != "COMPLETED":
        raise AgentKernelError(f"来源 AgentRun 未完成 (state={from_run.get('state')})")
    reg = AgentRegistry(agents_file=Path(root) / "agents" / "factory_agents.json")
    if reg.get(to_agent_id) is None:
        raise AgentKernelError(f"接收 Agent 不存在: {to_agent_id}")
    # 校验 artifacts 存在
    from .artifact_lifecycle import get_artifact

    for aid in input_artifacts:
        if get_artifact(root, aid) is None:
            raise AgentKernelError(f"Artifact 不存在: {aid}")

    handoff_id = f"hnd-{uuid.uuid4().hex[:12]}"
    h: dict[str, Any] = {
        "handoff_id": handoff_id,
        "from_agent_run_id": from_agent_run_id,
        "from_agent_id": from_run.get("agent_id"),
        "to_agent_id": to_agent_id,
        "production_run_id": from_run.get("production_run_id"),
        "input_artifacts": input_artifacts,
        "context_refs": context_refs or {},
        "status": "CREATED",
        "created_at": _now_iso(),
        "accepted_at": None,
    }
    with _lock:
        p = Path(root) / "agents" / "handoffs" / f"{handoff_id}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            "HANDOFF_CREATED", trace_id=handoff_id, project_id=h["production_run_id"] or "",
            agent_id=h["to_agent_id"], actor_type="system", actor_id=h["from_agent_id"],
            action="handoff.created", source="agent_kernel", decision="allow",
            decision_reason="agent handoff",
            evidence=[{"handoff_id": handoff_id, "from": h["from_agent_id"],
                       "to": h["to_agent_id"], "artifacts": input_artifacts}],
            result={"ok": True},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass
    return h


def get_handoff(root: Path | str, handoff_id: str) -> dict[str, Any] | None:
    p = Path(root) / "agents" / "handoffs" / f"{handoff_id}.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def list_handoffs(root: Path | str) -> list[dict[str, Any]]:
    base = Path(root) / "agents" / "handoffs"
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
