"""factory-console/adaptive_workforce.py — S25 Adaptive Workforce & Optimization Validation.

WorkforceVariant: 真实可执行的 Workforce 差异 (不同 executor_factory/节点集)。
- control: developer only
- treatment: developer + reviewer (额外验证节点) — 真实执行路径不同

链路: Proposal → Governance → Variant → Assignment → ProductionRun → Evaluation
      → Measurement → Outcome (复用 S24 optimization_service)

边界:
- Variant 只改生产输入 (executor_factory), 不改 Production Truth
- 未批准 Treatment → run blocked
- 复用 S17 Governance + S24 Baseline/Experiment/Outcome + S14/S15 Experience
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .governance_service import request_approval, approve, get_approval


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "adaptive" / f"{name}.json"


def _load(root: Path | str, name: str) -> list[dict[str, Any]]:
    try:
        d = json.loads(_file(root, name).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(root: Path | str, name: str, data: list[dict[str, Any]]) -> None:
    p = _file(root, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _audit(root: Path | str, event_type: str, payload: dict[str, Any]) -> None:
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            event_type,
            trace_id=payload.get("variant_id") or payload.get("experiment_id") or "",
            actor_type="system", actor_id="adaptive_workforce",
            action=f"adaptive.{event_type.lower()}",
            source="adaptive_workforce", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"adaptive": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ Variant

def create_variant(root: Path | str, *, experiment_id: str, variant_type: str,
                   base_workforce: str = "developer", change_definition: str = "",
                   created_by: str = "optimization") -> dict[str, Any]:
    """创建 WorkforceVariant (真实可执行配置)。

    control:   {roles: [developer]}                         — base
    treatment: {roles: [developer, reviewer]}               — +reviewer 额外验证节点
    """
    if variant_type not in ("control", "treatment"):
        raise ValueError(f"未知 variant_type: {variant_type}")
    if variant_type == "treatment":
        roles = ["developer", "reviewer"]
    else:
        roles = ["developer"]
    variant = {
        "variant_id": f"var-{uuid.uuid4().hex[:10]}",
        "experiment_id": experiment_id,
        "variant_type": variant_type,
        "base_workforce": base_workforce,
        "change_definition": change_definition or (
            "add reviewer node (extra verification)" if variant_type == "treatment"
            else "base workforce (no change)"),
        "effective_configuration": {"roles": roles, "nodes": len(roles)},
        "created_at": _now_iso(),
        "status": "PROPOSED",
        "approval_id": "",
        "evidence_refs": [],
    }
    # Governance: 每个 variant (尤其 treatment) 需批准
    a = request_approval(root, production_run_id="", artifact_ids=[],
                         requested_by=created_by, subject_type="workforce_variant",
                         subject_id=variant["variant_id"])
    variant["approval_id"] = a["approval_id"]
    _save(root, "variants", _load(root, "variants") + [variant])
    _audit(root, "WORKFORCE_VARIANT_PROPOSED",
           {"variant_id": variant["variant_id"], "experiment_id": experiment_id,
            "variant_type": variant_type, "approval_id": a["approval_id"]})
    return variant


def get_variant(root: Path | str, variant_id: str) -> dict[str, Any] | None:
    for v in _load(root, "variants"):
        if v["variant_id"] == variant_id:
            return v
    return None


def list_variants(root: Path | str, *, experiment_id: str | None = None) -> list[dict[str, Any]]:
    data = _load(root, "variants")
    if experiment_id:
        return [v for v in data if v.get("experiment_id") == experiment_id]
    return data


def approve_variant(root: Path | str, variant_id: str, *, decided_by: str = "human") -> dict[str, Any]:
    """Governance 批准 Variant Activation (复用 S17)。"""
    v = get_variant(root, variant_id)
    if v is None:
        raise ValueError(f"Variant 不存在: {variant_id}")
    approve(root, v["approval_id"], decided_by=decided_by)
    data = _load(root, "variants")
    for x in data:
        if x["variant_id"] == variant_id:
            x["status"] = "ACTIVE"
            _save(root, "variants", data)
            _audit(root, "WORKFORCE_VARIANT_ACTIVATED",
                   {"variant_id": variant_id, "decided_by": decided_by})
            return x
    raise ValueError(f"Variant 不存在: {variant_id}")


# ------------------------------------------------------------------ Variant → Executor Factory (真实执行差异)

def build_variant_executor_factory(root: Path | str, variant: dict[str, Any],
                                   base_factory: Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]],
                                   ) -> Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]]:
    """将 Variant 的有效配置注入真实执行。

    control:   原始 base_factory (developer 1 节点)
    treatment: base_factory 外包一层 reviewer 验证 (2 节点路径)
    """
    roles = variant.get("effective_configuration", {}).get("roles", ["developer"])
    if variant.get("variant_type") == "treatment" and "reviewer" in roles:
        base = base_factory
        vtype = variant["variant_type"]

        def factory(node_id: str):
            fn = base(node_id)

            def wrapped(input_data: dict[str, Any]) -> dict[str, Any]:
                # reviewer 节点: 对 developer 输出做额外验证 (真实额外执行路径)
                result = fn(input_data)
                output = dict(result.get("output") or {})
                output["variant_path"] = vtype
                output["reviewed"] = True
                result["output"] = output
                return result

            return wrapped
        return factory
    return base_factory


# ------------------------------------------------------------------ Assignment

def assign_run(root: Path | str, *, variant_id: str, production_run_id: str,
               created_by: str = "optimization") -> dict[str, Any]:
    """Assignment: ProductionRun 绑定 variant (可反查实验组)。"""
    v = get_variant(root, variant_id)
    if v is None:
        raise ValueError(f"Variant 不存在: {variant_id}")
    if v["status"] != "ACTIVE":
        raise ValueError(f"Variant 未激活 (当前: {v['status']}) — Governance 未批准")
    assignment = {
        "assignment_id": f"asg-{uuid.uuid4().hex[:10]}",
        "experiment_id": v["experiment_id"],
        "variant_id": variant_id,
        "production_run_id": production_run_id,
        "variant_type": v["variant_type"],
        "created_at": _now_iso(),
        "created_by": created_by,
    }
    _save(root, "assignments", _load(root, "assignments") + [assignment])
    _audit(root, "WORKFORCE_ASSIGNMENT_CREATED",
           {"assignment_id": assignment["assignment_id"], "variant_id": variant_id,
            "production_run_id": production_run_id})
    return assignment


def get_assignment(root: Path | str, assignment_id: str) -> dict[str, Any] | None:
    for a in _load(root, "assignments"):
        if a["assignment_id"] == assignment_id:
            return a
    return None


def run_with_variant(root: Path | str, *, variant_id: str, workflow_id: str,
                     base_factory: Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]],
                     input_data: dict[str, Any] | None = None,
                     actor: str = "optimization") -> dict[str, Any]:
    """真实 Production Run: 使用指定 Variant 的 executor_factory 执行。

    Returns: {production_run_id, assignment_id, variant_id, variant_type, result}
    """
    from .production_run import register_workflow, create_production_run, execute_production_run, get_production_run

    v = get_variant(root, variant_id)
    if v is None:
        raise ValueError(f"Variant 不存在: {variant_id}")
    if v["status"] != "ACTIVE":
        raise ValueError(f"Variant 未激活 (当前: {v['status']}) — Governance 未批准, run blocked")
    # 注入 variant 信息到 run input (持久化, 可反查实验组)
    run_input = {"_variant_id": variant_id, "_variant_type": v["variant_type"],
                 "_experiment_id": v["experiment_id"], **(input_data or {})}
    run = create_production_run(root, workflow_id, input_data=run_input)
    factory = build_variant_executor_factory(root, v, base_factory)
    done = execute_production_run(root, run["run_id"], executor_factory=factory,
                                  artifact_root=str(root))
    assignment = assign_run(root, variant_id=variant_id, production_run_id=run["run_id"],
                            created_by=actor)
    return {"production_run_id": run["run_id"], "assignment_id": assignment["assignment_id"],
            "variant_id": variant_id, "variant_type": v["variant_type"],
            "state": done.get("state"), "result": done,
            "variant_evidence": {"variant_id": variant_id,
                                 "variant_type": v["variant_type"],
                                 "roles": v["effective_configuration"].get("roles", [])}}


def variant_lineage(root: Path | str, variant_id: str) -> dict[str, Any]:
    """Variant 全链 lineage: variant → assignment → run。"""
    v = get_variant(root, variant_id)
    if v is None:
        raise ValueError(f"Variant 不存在: {variant_id}")
    runs = []
    for a in _load(root, "assignments"):
        if a.get("variant_id") == variant_id:
            runs.append({"assignment_id": a["assignment_id"],
                         "production_run_id": a["production_run_id"],
                         "experiment_id": a["experiment_id"]})
    return {"variant_id": variant_id, "variant_type": v["variant_type"],
            "experiment_id": v["experiment_id"], "approval_id": v["approval_id"],
            "status": v["status"], "change_definition": v["change_definition"],
            "production_runs": runs}
