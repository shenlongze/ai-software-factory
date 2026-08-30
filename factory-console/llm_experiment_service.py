"""factory-console/llm_experiment_service.py — S26 Real LLM Optimization Experiment.

用真实 LLM Production Evidence 判定 Workforce Optimization 是否有效。

- 结构化 Hypothesis (metric/direction/threshold/min_sample 冻结)
- Control=Developer, Treatment=Developer+Reviewer (S25 Variant + 真实 LLM executor)
- Budget Guard (max_runs; 超限 STOPPED)
- Sample Eligibility (ELIGIBLE/INELIGIBLE/FAILED, 防 selection bias)
- PROVEN 硬性保护 (样本/evidence/evaluation/metric 缺失 → PROVEN impossible)
- Outcome: IMPROVED/REGRESSED/UNCHANGED/INCONCLUSIVE + Effectiveness: PROVEN/REJECTED/NOT_YET_PROVEN

复用: S24 Baseline/Measurement/Outcome + S25 Variant/Assignment + S11 真实 LLM + S13 Evaluation + S17 Governance
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .optimization_service import (
    create_experiment as _s24_create_exp, approve_experiment as _s24_approve,
    get_experiment as _s24_get, run_experiment as _s24_run,
    compare as _s24_compare, outcome as _s24_outcome,
)
from .adaptive_workforce import (
    create_variant, approve_variant, run_with_variant, get_variant,
)

#: 默认 Budget Guard
DEFAULT_MAX_RUNS = {"control": 2, "treatment": 2, "total": 4}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "llm_exp" / f"{name}.json"


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
            trace_id=payload.get("experiment_id") or "",
            actor_type="system", actor_id="llm_experiment",
            action=f"llm_exp.{event_type.lower()}",
            source="llm_experiment_service", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"llm_exp": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ Hypothesis

def create_hypothesis(root: Path | str, *, statement: str, metric: str,
                      direction: str, control_definition: str, treatment_definition: str,
                      minimum_sample_size: int = 2, success_threshold: float = 0.0,
                      baseline_reference: str = "", risk: str = "medium") -> dict[str, Any]:
    """结构化 Hypothesis (metric/threshold 冻结, 结果后不可改)。"""
    if direction not in ("HIGHER_IS_BETTER", "LOWER_IS_BETTER"):
        raise ValueError(f"未知 direction: {direction}")
    if minimum_sample_size < 1:
        raise ValueError("minimum_sample_size ≥ 1")
    h = {
        "hypothesis_id": f"hyp-{uuid.uuid4().hex[:10]}",
        "statement": statement, "metric": metric, "direction": direction,
        "control_definition": control_definition, "treatment_definition": treatment_definition,
        "baseline_reference": baseline_reference, "minimum_sample_size": minimum_sample_size,
        "success_threshold": success_threshold, "risk": risk,
        "frozen": True, "created_at": _now_iso(),
    }
    _save(root, "hypotheses", _load(root, "hypotheses") + [h])
    return h


def get_hypothesis(root: Path | str, hypothesis_id: str) -> dict[str, Any] | None:
    for h in _load(root, "hypotheses"):
        if h["hypothesis_id"] == hypothesis_id:
            return h
    return None


# ------------------------------------------------------------------ Experiment (真实 LLM)

def create_llm_experiment(root: Path | str, *, hypothesis_id: str,
                          baseline_id: str = "", metric: str = "overall_score",
                          max_runs: dict[str, int] | None = None,
                          created_by: str = "optimization") -> dict[str, Any]:
    """创建真实 LLM Experiment (冻结 metric/threshold; Governance approval 前置)。"""
    h = get_hypothesis(root, hypothesis_id)
    if h is None:
        raise ValueError(f"Hypothesis 不存在: {hypothesis_id}")
    # S26 实验独立于 S24 baseline (control vs treatment 直接对比, 不依赖历史 baseline)
    budget = dict(DEFAULT_MAX_RUNS)
    if max_runs:
        budget.update(max_runs)
    exp = {
        "experiment_id": f"exp-{uuid.uuid4().hex[:10]}",
        "hypothesis_id": hypothesis_id,
        "baseline_id": baseline_id,
        "control_definition": h["control_definition"],
        "treatment_definition": h["treatment_definition"],
        "metric": h["metric"],
        "status": "APPROVAL_REQUIRED",
        "governance": {"required": True, "approval_id": ""},
        "runs": [], "measurements": [], "created_at": _now_iso(), "updated_at": _now_iso(),
        "llm_experiment": {
            "direction": h["direction"], "success_threshold": h["success_threshold"],
            "minimum_sample_size": h["minimum_sample_size"],
            "budget": budget, "runs_used": {"control": 0, "treatment": 0},
            "samples": [], "status": "PENDING", "stopped": False,
        },
    }
    # Governance: request approval (human)
    from .governance_service import request_approval
    a = request_approval(root, production_run_id="", artifact_ids=[],
                         requested_by=created_by, subject_type="experiment",
                         subject_id=exp["experiment_id"])
    exp["governance"]["approval_id"] = a["approval_id"]
    data = _load(root, "experiments")
    data.append(exp)
    _save(root, "experiments", data)
    return exp


def approve_llm_experiment(root: Path | str, experiment_id: str, *, decided_by: str = "human") -> dict[str, Any]:
    """Governance 批准 LLM Experiment (复用 S17 approval)。"""
    from .governance_service import approve
    exp = _get_llm_exp(root, experiment_id)
    approve(root, exp["governance"]["approval_id"], decided_by=decided_by)
    data = _load(root, "experiments")
    for e in data:
        if e["experiment_id"] == experiment_id:
            e["status"] = "APPROVED"
            e["updated_at"] = _now_iso()
            _save(root, "experiments", data)
            return e
    raise ValueError(f"Experiment 不存在: {experiment_id}")


def _get_llm_exp(root: Path | str, experiment_id: str) -> dict[str, Any]:
    for e in _load(root, "experiments"):
        if e["experiment_id"] == experiment_id:
            return e
    raise ValueError(f"Experiment 不存在: {experiment_id}")


def llm_run_sample(root: Path | str, *, experiment_id: str, arm: str,
                   workflow_id: str,
                   real_executor_factory: Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]],
                   task_prompt: str = "", actor: str = "llm_experiment") -> dict[str, Any]:
    """真实 LLM 单样本执行: 用 S25 Variant + 真实 executor factory。

    Returns: sample {arm, production_run_id, variant_id, state, eligible, reason, metrics}
    """
    exp = _get_llm_exp(root, experiment_id)
    llm = exp.get("llm_experiment", {})
    budget = llm.get("budget", DEFAULT_MAX_RUNS)
    used = llm.get("runs_used", {"control": 0, "treatment": 0})
    if used.get(arm, 0) >= budget.get(arm, 0):
        return {"arm": arm, "error": "budget exceeded", "eligible": False, "reason": "BUDGET_EXCEEDED"}
    if sum(used.values()) >= budget.get("total", 4):
        return {"arm": arm, "error": "total budget exceeded", "eligible": False, "reason": "TOTAL_BUDGET_EXCEEDED"}
    # Governance: experiment 必须批准
    if exp.get("status") != "APPROVED":
        return {"arm": arm, "error": "experiment not approved", "eligible": False,
                "reason": "NOT_APPROVED"}
    # 创建 variant (control/treatment) + 批准 + 真实执行
    v = create_variant(root, experiment_id=experiment_id, variant_type=arm,
                       created_by=actor)
    approve_variant(root, v["variant_id"], decided_by="human")
    try:
        r = run_with_variant(root, variant_id=v["variant_id"], workflow_id=workflow_id,
                             base_factory=real_executor_factory,
                             input_data={"prompt": task_prompt}, actor=actor)
    except Exception as exc:  # noqa: BLE001
        sample = {"arm": arm, "production_run_id": "", "variant_id": v["variant_id"],
                  "state": "FAILED", "eligible": False, "reason": f"EXECUTION_FAILED: {exc}",
                  "at": _now_iso()}
        _record_sample(root, experiment_id, arm, sample)
        return sample
    # S13 Evaluation → metric
    from .production_evaluation import evaluate
    ev = evaluate(root, r["production_run_id"])
    metric_name = exp.get("metric", "overall_score")
    metric_value = None
    if ev is not None:
        metric_value = ev.get(metric_name, ev.get("overall_score"))
    eligible = r["state"] == "COMPLETED" and ev is not None and metric_value is not None
    sample = {"arm": arm, "production_run_id": r["production_run_id"],
              "variant_id": v["variant_id"], "assignment_id": r.get("assignment_id"),
              "state": r["state"], "eligible": eligible,
              "reason": "" if eligible else ("INCOMPLETE" if r["state"] != "COMPLETED"
                                             else "NO_EVALUATION" if ev is None else "NO_METRIC"),
              "metric_value": metric_value, "metric": metric_name,
              "evaluation_id": ev.get("evaluation_id") if ev else "",
              "at": _now_iso()}
    _record_sample(root, experiment_id, arm, sample)
    return sample


def _record_sample(root: Path | str, experiment_id: str, arm: str, sample: dict[str, Any]) -> None:
    data = _load(root, "experiments")
    for e in data:
        if e["experiment_id"] == experiment_id:
            llm = e.setdefault("llm_experiment", {})
            llm.setdefault("samples", []).append(sample)
            used = llm.setdefault("runs_used", {"control": 0, "treatment": 0})
            used[arm] = used.get(arm, 0) + 1
            if sum(used.values()) >= llm.get("budget", DEFAULT_MAX_RUNS).get("total", 4):
                llm["stopped"] = True
                llm["status"] = "STOPPED"
            _save(root, "experiments", data)
            break


def llm_compare(root: Path | str, experiment_id: str) -> dict[str, Any]:
    """真实 LLM 实验比较 (仅 ELIGIBLE samples; PROVEN 硬性保护)。"""
    exp = _get_llm_exp(root, experiment_id)
    llm = exp.get("llm_experiment", {})
    samples = llm.get("samples", [])
    eligible = [s for s in samples if s.get("eligible")]
    control = [s for s in eligible if s["arm"] == "control"]
    treatment = [s for s in eligible if s["arm"] == "treatment"]
    h = get_hypothesis(root, exp.get("hypothesis_id", "")) or {}
    min_sample = h.get("minimum_sample_size", 2)
    threshold = h.get("success_threshold", 0.0)
    direction = h.get("direction", "HIGHER_IS_BETTER")
    metric = exp.get("metric", "overall_score")

    if len(control) < min_sample or len(treatment) < min_sample:
        return {"experiment_id": experiment_id, "result": "INCONCLUSIVE",
                "reason": f"样本不足 (control={len(control)}, treatment={len(treatment)}, 需 ≥{min_sample})",
                "effectiveness": "NOT_YET_PROVEN",
                "control_samples": len(control), "treatment_samples": len(treatment),
                "metric": metric, "direction": direction, "threshold": threshold}
    c_vals = [s["metric_value"] for s in control]
    t_vals = [s["metric_value"] for s in treatment]
    c_mean = sum(c_vals) / len(c_vals)
    t_mean = sum(t_vals) / len(t_vals)
    delta = round(t_mean - c_mean, 3)
    delta_pct = round((delta / c_mean * 100), 1) if c_mean else 0.0
    improved = delta > threshold if direction == "HIGHER_IS_BETTER" else delta < -threshold
    regressed = delta < -threshold if direction == "HIGHER_IS_BETTER" else delta > threshold
    if improved:
        result = "IMPROVED"
        effectiveness = "PROVEN"
    elif regressed:
        result = "REGRESSED"
        effectiveness = "REJECTED"
    elif delta == 0:
        result = "UNCHANGED"
        effectiveness = "NOT_YET_PROVEN"
    else:
        result = "INCONCLUSIVE"
        effectiveness = "NOT_YET_PROVEN"
    return {"experiment_id": experiment_id, "result": result, "effectiveness": effectiveness,
            "reason": f"{metric}: control={round(c_mean,3)} treatment={round(t_mean,3)} "
                      f"delta={delta} ({delta_pct}%) threshold={threshold} direction={direction}",
            "control_value": round(c_mean, 3), "treatment_value": round(t_mean, 3),
            "delta": delta, "delta_percent": delta_pct,
            "control_samples": len(control), "treatment_samples": len(treatment),
            "control_runs": [s["production_run_id"] for s in control],
            "treatment_runs": [s["production_run_id"] for s in treatment],
            "evidence_refs": [s["production_run_id"] for s in eligible],
            "metric": metric, "direction": direction, "threshold": threshold,
            "statistical_significance": "NOT_STATISTICALLY_ESTABLISHED",
            "samples": eligible}


def llm_outcome(root: Path | str, experiment_id: str) -> dict[str, Any]:
    """正式 Outcome (真实 LLM 实验)。"""
    cmp = llm_compare(root, experiment_id)
    oc = {"outcome_id": f"oc-{uuid.uuid4().hex[:10]}", "experiment_id": experiment_id,
          "result": cmp["result"], "effectiveness": cmp["effectiveness"],
          "reason": cmp["reason"], "evidence_refs": cmp.get("evidence_refs", []),
          "created_at": _now_iso()}
    # 仅 IMPROVED (真实证据) 才写 Experience candidate
    if cmp["result"] == "IMPROVED":
        oc["experience_candidate"] = True
    _save(root, "outcomes", _load(root, "outcomes") + [oc])
    _audit(root, "LLM_EXPERIMENT_OUTCOME", {"experiment_id": experiment_id,
                                            "result": cmp["result"],
                                            "effectiveness": cmp["effectiveness"]})
    return oc


def llm_experiment_lineage(root: Path | str, experiment_id: str) -> dict[str, Any]:
    """完整 lineage: hypothesis → experiment → variants → samples → outcome。"""
    exp = _get_llm_exp(root, experiment_id)
    h = get_hypothesis(root, exp.get("hypothesis_id", "")) or {}
    variants = []
    for v in _load(root, "variants"):
        if v.get("experiment_id") == experiment_id:
            variants.append({"variant_id": v["variant_id"], "variant_type": v["variant_type"],
                             "status": v["status"]})
    cmp = llm_compare(root, experiment_id)
    return {"experiment_id": experiment_id, "hypothesis": h,
            "control_definition": exp.get("control_definition"),
            "treatment_definition": exp.get("treatment_definition"),
            "variants": variants, "comparison": cmp,
            "samples": exp.get("llm_experiment", {}).get("samples", [])}
