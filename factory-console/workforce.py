"""factory-console/workforce.py — S16 Multi-Agent Professional Workforce。

把多个专业 Agent 组织成可执行、可验证、可追溯的 Workforce。

- ROLE_CAPABILITIES: 每角色能力声明 (非 prompt)
- ROLE_PERMISSIONS: 每角色权限边界
- enforce_permission(role, action): 权限检查
- select_agent(root, role): 从 AgentRegistry 选择 AgentEntity
- create_task: TaskRecord 持久化
- workforce_lineage(run_id): 全链 (agent/decision/artifact/verification/handoff)
- run_workforce: 编排 (复用 run_professional_workflow)

原则:
- Orchestrator 只调度不执行 (Agent 独立 Loop)
- 无 Central Mega-Agent (真多 AgentEntity)
- 权限: PM 不能改代码, Dev 不能 override QA, 无 self-approve
- Handoff 只传 Artifact refs
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ------------------------------------------------------------------ Role Capability / Permission (冻结)

#: 每角色能力声明
ROLE_CAPABILITIES: dict[str, list[str]] = {
    "product_manager": ["discover_product", "create_prd", "product_decision"],
    "market_analyst": ["market_research", "competitive_analysis"],
    "ux_designer": ["design_ux", "create_design_artifact"],
    "software_architect": ["design_architecture", "technical_decision"],
    "software_developer": ["implement", "repair"],
    "qa_engineer": ["verify", "test", "quality_decision"],
    "release_engineer": ["release_prepare", "release_verify"],
}

#: 每角色权限边界 (action → 允许的 role)
PERMISSION_MATRIX: dict[str, list[str]] = {
    "create_prd": ["product_manager"],
    "market_analysis": ["market_analyst"],
    "design_ux": ["ux_designer"],
    "architecture_decision": ["software_architect"],
    "implement_code": ["software_developer"],
    "repair_code": ["software_developer"],
    "verify_code": ["qa_engineer"],
    "approve_quality": ["qa_engineer"],
    "release": ["release_engineer"],
}

#: 禁止: 任何 Agent 不能 override QA / 自批准
FORBIDDEN_ACTIONS: dict[str, list[str]] = {
    "software_developer": ["override_qa", "self_approve", "release"],
    "product_manager": ["implement_code", "release"],
    "software_architect": ["release"],
}

#: 专业 workflow 顺序 (S16 扩展: 含 Market/UX, 可选)
WORKFORCE_WORKFLOWS: dict[str, list[str]] = {
    "software-product-production": [
        "product_manager", "software_architect", "software_developer", "qa_engineer"],
    "software-product-full": [
        "market_analyst", "product_manager", "ux_designer",
        "software_architect", "software_developer", "qa_engineer", "release_engineer"],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def enforce_permission(role: str, action: str) -> None:
    """权限检查: action 不在 role 允许列表 → 拒绝。"""
    allowed = PERMISSION_MATRIX.get(action, [])
    if allowed and role not in allowed:
        raise PermissionError(f"角色 {role} 无权执行 {action} (允许: {allowed})")
    forbidden = FORBIDDEN_ACTIONS.get(role, [])
    if action in forbidden:
        raise PermissionError(f"角色 {role} 被禁止执行 {action}")


def capabilities(role: str) -> list[str]:
    return list(ROLE_CAPABILITIES.get(role, []))


def _tasks_file(root: Path | str) -> Path:
    return Path(root) / "workforce" / "tasks.json"


def _load_tasks(root: Path | str) -> list[dict[str, Any]]:
    try:
        d = json.loads(_tasks_file(root).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save_tasks(root: Path | str, data: list[dict[str, Any]]) -> None:
    p = _tasks_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


# ------------------------------------------------------------------ Agent Selection

def select_agent(root: Path | str, role: str) -> dict[str, Any] | None:
    """从 AgentRegistry 选择匹配 role 的 AgentEntity。"""
    from .session.agent_registry import AgentRegistry

    reg = AgentRegistry(agents_file=Path(root) / "agents" / "factory_agents.json")
    for a in reg.list():
        if a.role == role:
            return a.to_dict() if hasattr(a, "to_dict") else {"id": a.id, "role": a.role}
    return None


def list_agents(root: Path | str) -> list[dict[str, Any]]:
    from .session.agent_registry import AgentRegistry

    reg = AgentRegistry(agents_file=Path(root) / "agents" / "factory_agents.json")
    out = []
    for a in reg.list():
        d = a.to_dict() if hasattr(a, "to_dict") else {"id": a.id, "role": a.role}
        d["capabilities"] = capabilities(getattr(a, "role", ""))
        out.append(d)
    return out


# ------------------------------------------------------------------ Task Record

def create_task(root: Path | str, *, role: str, objective: str,
                input_artifacts: list[str] | None = None,
                production_run_id: str = "") -> dict[str, Any]:
    """创建 Workforce TaskRecord (正式任务事实)。"""
    task = {
        "task_id": f"task-{uuid.uuid4().hex[:10]}",
        "role": role,
        "agent_id": "",
        "objective": objective,
        "input_artifacts": list(input_artifacts or []),
        "acceptance_criteria": [],
        "dependencies": [],
        "status": "PENDING",
        "production_run_id": production_run_id,
        "output_artifacts": [],
        "verification": {},
        "handoff_id": "",
        "created_at": _now_iso(),
    }
    data = _load_tasks(root)
    data.append(task)
    _save_tasks(root, data)
    return task


def get_tasks(root: Path | str, *, production_run_id: str | None = None) -> list[dict[str, Any]]:
    data = _load_tasks(root)
    if production_run_id:
        data = [t for t in data if t.get("production_run_id") == production_run_id]
    return data


# ------------------------------------------------------------------ Workforce Lineage

def workforce_lineage(root: Path | str, production_run_id: str) -> dict[str, Any]:
    """Multi-Agent 全链 Lineage: task → agent → decision → artifact → verification → handoff。"""
    from .production_run import get_production_run
    from .node_runtime import get_node_run
    from .artifact_lifecycle import get_artifact
    from .production_guidance import production_lineage

    run = get_production_run(root, production_run_id)
    nodes = []
    if run:
        for nr in run.get("node_runs", []):
            nrec = get_node_run(root, nr.get("run_id")) if nr.get("run_id") else None
            nodes.append({
                "node_id": nr.get("node_id"),
                "run_id": nr.get("run_id"),
                "state": nr.get("state"),
                "artifact_id": nr.get("artifact_id"),
                "verification": (nrec.get("verification") if nrec else None),
                "attempts": len(nrec.get("attempts", [])) if nrec else 0,
            })
    lineage = production_lineage(root, production_run_id)
    return {
        "production_run_id": production_run_id,
        "workflow_id": run.get("workflow_id") if run else None,
        "state": run.get("state") if run else None,
        "nodes": nodes,
        "experiences": lineage.get("experiences", []),
        "decisions": lineage.get("decisions", []),
        "tasks": get_tasks(root, production_run_id=production_run_id),
        "artifacts": run.get("artifacts", []) if run else [],
    }


# ------------------------------------------------------------------ Workforce Run (编排)

def run_workforce(
    root: Path | str,
    *,
    idea: str,
    workflow: str = "software-product-production",
    executor_factory=None,
    experience_guidance: bool = True,
    max_repair: int = 1,
    record_usage: bool = True,
) -> dict[str, Any]:
    """编排 Multi-Agent Workforce (复用 Professional Workflow, 只调度不执行)。"""
    if workflow not in WORKFORCE_WORKFLOWS:
        raise ValueError(f"未知 workflow: {workflow} (可用: {list(WORKFORCE_WORKFLOWS)})")
    from .professional_workflow import run_professional_workflow

    # 权限预检: 角色存在且可选到 Agent
    missing = [r for r in WORKFORCE_WORKFLOWS[workflow] if select_agent(root, r) is None]
    if missing:
        raise ValueError(f"缺少 Agent 角色: {missing}")

    result = run_professional_workflow(
        root, idea=idea, executor_factory=executor_factory,
        max_repair=max_repair, experience_guidance=experience_guidance,
        record_usage=record_usage,
    )
    # 为每个角色创建 TaskRecord (只记录, 不重复执行)
    roles = WORKFORCE_WORKFLOWS[workflow]
    for i, role in enumerate(roles):
        ar = result.get("runs", {}).get(role)
        prun_id = ar.get("production_run_id") if ar else ""
        task = create_task(root, role=role, objective=f"{role}: {idea[:80]}",
                           production_run_id=prun_id)
        if ar:
            task["status"] = ar["state"]
            task["agent_id"] = ar.get("agent_id", "")
            task["output_artifacts"] = ar.get("output_artifacts", [])
            task["verification"] = {"state": ar["state"]}
        # 更新 task (含 handoff)
        data = _load_tasks(root)
        for t in data:
            if t["task_id"] == task["task_id"]:
                t.update(task)
        _save_tasks(root, data)
    return result
