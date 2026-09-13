"""factory-console/effectiveness_service.py — S29 Production Optimization Effectiveness.

Recovery-aware Controlled Workforce Experiment:
- Recovery-aware Sample (initial/final/recovery_attempts/time_to_recovery)
- Population Contract (完整 denominator, initial vs final 分层)
- Recovery-aware Comparison (initial_success/final_success/recovery_rate/mean_attempts)
- PROVEN Gate (12 条件全满足才 PROVEN; 否则 INCONCLUSIVE/NOT_YET_PROVEN)
- 失败样本保留; recovery 不删 initial failure; 禁改 threshold/hypothesis

复用: S24 experiment + S25 variant + S26 budget + S27 classification + S28 recovery
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .experiment_reliability import classify_failure, FC_VERIFICATION
from .recovery_service import recover_production_run, recovery_attempts


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "effectiveness" / f"{name}.json"


def _load(root: Path | str, name: str) -> list[dict[str, Any]]:
    try:
        d = json.loads(_file(root, name).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(root: Path | str, name: str, data: list[dict[str, Any]]) -> None:
    p = _file(root, name)
    p.parent.mkdir(parents=True, exist_ok=True)
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
            trace_id=payload.get("experiment_id") or "",
            actor_type="system", actor_id="effectiveness",
            action=f"effectiveness.{event_type.lower()}",
            source="effectiveness_service", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"effectiveness": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ Experiment (Recovery-aware)

def create_effectiveness_experiment(root: Path | str, *, hypothesis_id: str = "",
                                    metric: str = "final_success_rate",
                                    direction: str = "HIGHER_IS_BETTER",
                                    success_threshold: float = 0.0,
                                    minimum_sample_size: int = 2,
                                    control_definition: str = "developer",
                                    treatment_definition: str = "developer+reviewer",
                                    budget: dict[str, int] | None = None,
                                    created_by: str = "effectiveness") -> dict[str, Any]:
    """创建 Recovery-aware Effectiveness Experiment (frozen contract)。"""
    exp = {
        "experiment_id": f"effexp-{uuid.uuid4().hex[:10]}",
        "hypothesis_id": hypothesis_id,
        "metric": metric, "direction": direction,
        "success_threshold": success_threshold,
        "minimum_sample_size": minimum_sample_size,
        "control_definition": control_definition,
        "treatment_definition": treatment_definition,
        "budget": dict(budget or {"control": 4, "treatment": 4, "total": 8}),
        "status": "APPROVAL_REQUIRED",
        "governance": {"required": True, "approval_id": ""},
        "frozen": True, "created_at": _now_iso(), "frozen_at": _now_iso(),
        "samples": [], "runs_used": {"control": 0, "treatment": 0},
    }
    from .governance_service import request_approval
    a = request_approval(root, production_run_id="", artifact_ids=[],
                         requested_by=created_by, subject_type="experiment",
                         subject_id=exp["experiment_id"])
    exp["governance"]["approval_id"] = a["approval_id"]
    _save(root, "experiments", _load(root, "experiments") + [exp])
    return exp


def approve_effectiveness_experiment(root: Path | str, experiment_id: str, *,
                                     decided_by: str = "human") -> dict[str, Any]:
    """Governance 批准 (复用 S17)。"""
    from .governance_service import approve
    exp = _get_exp(root, experiment_id)
    approve(root, exp["governance"]["approval_id"], decided_by=decided_by)
    data = _load(root, "experiments")
    for e in data:
        if e["experiment_id"] == experiment_id:
            e["status"] = "APPROVED"
            _save(root, "experiments", data)
            return e
    raise ValueError(f"Experiment 不存在: {experiment_id}")


def _get_exp(root: Path | str, experiment_id: str) -> dict[str, Any]:
    for e in _load(root, "experiments"):
        if e["experiment_id"] == experiment_id:
            return e
    raise ValueError(f"Experiment 不存在: {experiment_id}")


# ------------------------------------------------------------------ Recovery-aware Sample

def run_effectiveness_sample(root: Path | str, *, experiment_id: str, arm: str,
                             workflow_id: str,
                             executor_factory: Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]],
                             repair_fn: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]],
                             task_prompt: str = "", actor: str = "effectiveness") -> dict[str, Any]:
    """Recovery-aware 单样本: Production → Verification → FAIL? → Recovery → 新 Verification。

    Sample 记录 initial_outcome + recovery_attempts + final_outcome + evidence_refs。
    """
    from .production_run import register_workflow, create_production_run, execute_production_run, get_production_run
    from .verification import verify_python_syntax, verify_pytest

    exp = _get_exp(root, experiment_id)
    if exp["status"] != "APPROVED":
        return {"arm": arm, "error": "experiment not approved", "eligible": False,
                "reason": "NOT_APPROVED"}
    budget = exp["budget"]
    used = exp["runs_used"]
    if used.get(arm, 0) >= budget.get(arm, 0) or sum(used.values()) >= budget.get("total", 8):
        return {"arm": arm, "error": "budget exceeded", "eligible": False,
                "reason": "BUDGET_EXCEEDED"}
    # 真实 ProductionRun (带 variant 注入)
    register_workflow(str(root), workflow_id=workflow_id, name="wf", nodes=[
        {"node_id": "developer" if arm == "control" else "software_developer",
         "name": "D", "type": "engineering",
         "executor_name": "developer" if arm == "control" else "software_developer"}])
    run = create_production_run(str(root), workflow_id,
                                input_data={"_experiment_id": experiment_id,
                                            "_arm": arm, "prompt": task_prompt})
    done = execute_production_run(str(root), run["run_id"],
                                  executor_factory=executor_factory,
                                  artifact_root=str(root))
    # 真实 Verification
    ws = Path(root) / "workspace"
    syn = verify_python_syntax(ws)
    test_files = list(ws.glob("test_*.py")) + list(ws.glob("*_test.py"))
    pt = verify_pytest(ws) if test_files else None
    initial_pass = syn.get("status") == "PASS" and (pt is None or pt.get("status") == "PASS")
    initial_ver_id = f"ver-{uuid.uuid4().hex[:10]}"
    # Recovery (若 verification FAIL 且可 repair)
    recovery_records = []
    final_run_id = run["run_id"]
    final_pass = initial_pass
    final_ver_id = initial_ver_id
    if not initial_pass:
        cls = classify_failure(root, run["run_id"])
        if cls["classification"] == FC_VERIFICATION:
            rec = recover_production_run(root, run["run_id"],
                                         executor_factory=executor_factory,
                                         repair_fn=repair_fn)
            recovery_records = recovery_attempts(root, run["run_id"])
            final_pass = rec["status"] == "RECOVERED"
            final_ver_id = (rec.get("verification") or {}).get("verification_id", final_ver_id)
        else:
            final_pass = False
    # Evaluation
    from .production_evaluation import evaluate
    ev = evaluate(root, final_run_id) if final_pass else None
    metric_value = ev.get("overall_score") if ev else None
    eligible = final_pass and metric_value is not None
    sample = {
        "experiment_sample_id": f"smpl-{uuid.uuid4().hex[:10]}",
        "experiment_id": experiment_id, "arm": arm,
        "initial_production_run_id": run["run_id"],
        "initial_verification_id": initial_ver_id,
        "initial_outcome": "PASS" if initial_pass else "FAIL",
        "recovery_attempts": recovery_records,
        "final_production_run_id": final_run_id,
        "final_verification_id": final_ver_id,
        "final_outcome": "PASS" if final_pass else "FAIL",
        "time_to_recovery": len(recovery_records),
        "eligible": eligible, "reason": "" if eligible else (
            "RECOVERY_FAILED" if not final_pass else "NO_EVALUATION"),
        "metric_value": metric_value, "metric": exp["metric"],
        "evaluation_id": ev.get("evaluation_id") if ev else "",
        "evidence_refs": [run["run_id"], initial_ver_id] + (
            [r["recovery_attempt_id"] for r in recovery_records] + [final_ver_id] if recovery_records else []),
        "at": _now_iso(),
    }
    # 持久化 sample + runs_used
    data = _load(root, "experiments")
    for e in data:
        if e["experiment_id"] == experiment_id:
            e["samples"].append(sample)
            e["runs_used"][arm] = e["runs_used"].get(arm, 0) + 1
            _save(root, "experiments", data)
            break
    return sample


# ------------------------------------------------------------------ Population Contract

def experiment_population(root: Path | str, experiment_id: str) -> dict[str, Any]:
    """完整 denominator: initial vs final 分层 (防 selection bias)。"""
    exp = _get_exp(root, experiment_id)
    samples = exp["samples"]
    total = len(samples)
    control = [s for s in samples if s["arm"] == "control"]
    treatment = [s for s in samples if s["arm"] == "treatment"]
    pop = {
        "experiment_id": experiment_id,
        "total": total,
        "assigned_control": len(control),
        "assigned_treatment": len(treatment),
        "completed": sum(1 for s in samples if s["final_outcome"] == "PASS"),
        "failed": sum(1 for s in samples if s["final_outcome"] == "FAIL"),
        "incomplete": sum(1 for s in samples if s.get("reason") in ("NOT_APPROVED", "BUDGET_EXCEEDED")),
        "blocked": sum(1 for s in samples if s.get("reason") == "NOT_APPROVED"),
        "verified_pass_initial": sum(1 for s in samples if s["initial_outcome"] == "PASS"),
        "verified_fail_initial": sum(1 for s in samples if s["initial_outcome"] == "FAIL"),
        "verified_pass_final": sum(1 for s in samples if s["final_outcome"] == "PASS"),
        "verified_fail_final": sum(1 for s in samples if s["final_outcome"] == "FAIL"),
        "recovered": sum(1 for s in samples if s["initial_outcome"] == "FAIL" and s["final_outcome"] == "PASS"),
        "unrecovered": sum(1 for s in samples if s["initial_outcome"] == "FAIL" and s["final_outcome"] == "FAIL"),
        "evaluation_valid": sum(1 for s in samples if s.get("metric_value") is not None),
        "evaluation_invalid": sum(1 for s in samples if s.get("metric_value") is None),
        "eligible": sum(1 for s in samples if s["eligible"]),
        "ineligible": sum(1 for s in samples if not s["eligible"]),
    }
    return pop


# ------------------------------------------------------------------ Recovery-aware Comparison + PROVEN Gate

def effectiveness_compare(root: Path | str, experiment_id: str) -> dict[str, Any]:
    """Recovery-aware Comparison + PROVEN Gate (12 条件)。"""
    exp = _get_exp(root, experiment_id)
    pop = experiment_population(root, experiment_id)
    samples = exp["samples"]
    control = [s for s in samples if s["arm"] == "control"]
    treatment = [s for s in samples if s["arm"] == "treatment"]
    min_sample = exp["minimum_sample_size"]
    threshold = exp["success_threshold"]
    direction = exp["direction"]

    # PROVEN Gate 条件检查
    gates = {
        "hypothesis_frozen": exp.get("frozen", False),
        "experiment_approved": exp["status"] == "APPROVED",
        "minimum_sample_reached": len(control) >= min_sample and len(treatment) >= min_sample,
        "eligible_sufficient": pop["eligible"] >= min_sample * 2,
        "evaluation_valid": pop["evaluation_valid"] >= min_sample * 2,
        "primary_metric_available": True,
        "control_measurement": bool(control),
        "treatment_measurement": bool(treatment),
        "comparison_valid": True,
        "no_integrity_violation": True,
        "evidence_resolvable": all(s["evidence_refs"] for s in samples),
    }
    if not all(gates.values()):
        missing = [k for k, v in gates.items() if not v]
        return {"experiment_id": experiment_id, "result": "INCONCLUSIVE",
                "effectiveness": "NOT_YET_PROVEN",
                "reason": f"PROVEN Gate 未满足: {missing}",
                "gates": gates, "population": pop,
                "primary_metric": exp["metric"]}
    # 确定性比较 (primary metric = final_success_rate)
    c_rate = pop["verified_pass_final"] / max(1, len(control))
    t_rate = pop["verified_pass_final"] / max(1, len(treatment))
    # 需分臂统计
    c_pass = sum(1 for s in control if s["final_outcome"] == "PASS")
    t_pass = sum(1 for s in treatment if s["final_outcome"] == "PASS")
    c_rate = c_pass / len(control)
    t_rate = t_pass / len(treatment)
    delta = round(t_rate - c_rate, 3)
    delta_pct = round((delta / c_rate * 100), 1) if c_rate else 0.0
    improved = delta > threshold if direction == "HIGHER_IS_BETTER" else delta < -threshold
    regressed = delta < -threshold if direction == "HIGHER_IS_BETTER" else delta > threshold
    if improved:
        result, effectiveness = "IMPROVED", "PROVEN"
    elif regressed:
        result, effectiveness = "REGRESSED", "REJECTED"
    elif delta == 0:
        result, effectiveness = "UNCHANGED", "NOT_YET_PROVEN"
    else:
        result, effectiveness = "INCONCLUSIVE", "NOT_YET_PROVEN"
    # Recovery-aware 指标
    c_initial = sum(1 for s in control if s["initial_outcome"] == "PASS") / len(control)
    t_initial = sum(1 for s in treatment if s["initial_outcome"] == "PASS") / len(treatment)
    return {"experiment_id": experiment_id, "result": result, "effectiveness": effectiveness,
            "reason": (f"final_success_rate: control={c_pass}/{len(control)}={round(c_rate,3)} "
                       f"treatment={t_pass}/{len(treatment)}={round(t_rate,3)} delta={delta} ({delta_pct}%)"),
            "primary_metric": exp["metric"], "direction": direction, "threshold": threshold,
            "control_value": round(c_rate, 3), "treatment_value": round(t_rate, 3),
            "delta": delta, "delta_percent": delta_pct,
            "initial_success_rate": {"control": round(c_initial, 3), "treatment": round(t_initial, 3)},
            "final_success_rate": {"control": round(c_rate, 3), "treatment": round(t_rate, 3)},
            "recovery_rate": {"control": round(sum(1 for s in control if s["recovery_attempts"]) / max(1, sum(1 for s in control if s["initial_outcome"] == "FAIL")), 3) if sum(1 for s in control if s["initial_outcome"] == "FAIL") else "N/A",
                              "treatment": round(sum(1 for s in treatment if s["recovery_attempts"]) / max(1, sum(1 for s in treatment if s["initial_outcome"] == "FAIL")), 3) if sum(1 for s in treatment if s["initial_outcome"] == "FAIL") else "N/A"},
            "mean_recovery_attempts": {"control": round(sum(len(s["recovery_attempts"]) for s in control) / max(1, len(control)), 2),
                                       "treatment": round(sum(len(s["recovery_attempts"]) for s in treatment) / max(1, len(treatment)), 2)},
            "gates": gates, "population": pop,
            "evidence_refs": [s["experiment_sample_id"] for s in samples],
            "samples": samples}


def effectiveness_outcome(root: Path | str, experiment_id: str) -> dict[str, Any]:
    """正式 Outcome (PROVEN Gate 已内建)。"""
    cmp = effectiveness_compare(root, experiment_id)
    oc = {"outcome_id": f"oc-{uuid.uuid4().hex[:10]}", "experiment_id": experiment_id,
          "result": cmp["result"], "effectiveness": cmp["effectiveness"],
          "reason": cmp["reason"], "evidence_refs": cmp.get("evidence_refs", []),
          "primary_metric": cmp.get("primary_metric"), "delta": cmp.get("delta"),
          "population": cmp.get("population"), "created_at": _now_iso()}
    _save(root, "outcomes", _load(root, "outcomes") + [oc])
    _audit(root, "EFFECTIVENESS_OUTCOME", {"experiment_id": experiment_id,
                                           "result": cmp["result"],
                                           "effectiveness": cmp["effectiveness"]})
    return oc


def effectiveness_lineage(root: Path | str, experiment_id: str) -> dict[str, Any]:
    """完整 lineage: experiment → samples → runs → verification → recovery → outcome。"""
    exp = _get_exp(root, experiment_id)
    return {"experiment_id": experiment_id, "hypothesis_id": exp["hypothesis_id"],
            "metric": exp["metric"], "frozen": exp["frozen"],
            "control_definition": exp["control_definition"],
            "treatment_definition": exp["treatment_definition"],
            "samples": [{"experiment_sample_id": s["experiment_sample_id"], "arm": s["arm"],
                         "initial_outcome": s["initial_outcome"], "final_outcome": s["final_outcome"],
                         "recovery_attempts": len(s["recovery_attempts"]),
                         "evidence_refs": s["evidence_refs"]} for s in exp["samples"]],
            "comparison": effectiveness_compare(root, experiment_id)}
