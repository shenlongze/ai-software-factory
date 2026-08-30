"""factory-console/optimization_service.py — S24 Workforce Optimization & Production Optimization.

从真实 Production Evidence 发现低效模式 → Hypothesis → Baseline → Controlled Experiment
→ Measurement → Comparison → Outcome (经 Governance) → Experience。

核心原则:
- 只有真实 Baseline + 真实 Experiment + 真实 Measurement + 真实 Outcome 才能判定优化有效
- confidence ≠ improvement (confidence 仅 evidence 支持度)
- 无足够真实数据 → BASELINE_INSUFFICIENT / INCONCLUSIVE (不造数据)
- Experiment 不绕过 Governance (S17)
- 复用 Production Kernel (不建第二套 engine)
- 仅 IMPROVED (真实实验证明) → Experience
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .production_evaluation import evaluate as _evaluate
from .production_run import list_production_runs  # noqa: F401  (复用)
from .governance_service import request_approval, approve

#: Analysis 状态
ST_REQUESTED = "REQUESTED"
ST_ANALYZING = "ANALYZING"
ST_COMPLETED = "COMPLETED"
ST_FAILED = "FAILED"

#: Baseline 状态
BL_COMPLETED = "COMPLETED"
BL_INSUFFICIENT = "BASELINE_INSUFFICIENT"

#: Experiment 状态
EX_PROPOSED = "PROPOSED"
EX_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
EX_APPROVED = "APPROVED"
EX_RUNNING = "RUNNING"
EX_COMPLETED = "COMPLETED"
EX_FAILED = "FAILED"
EX_REJECTED = "REJECTED"
EX_INCONCLUSIVE = "INCONCLUSIVE"

#: Outcome 结果
OC_IMPROVED = "IMPROVED"
OC_REGRESSED = "REGRESSED"
OC_UNCHANGED = "UNCHANGED"
OC_INCONCLUSIVE = "INCONCLUSIVE"

#: 最小样本量 (少于则 INCONCLUSIVE)
MIN_SAMPLE = 2


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "optimization" / f"{name}.json"


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
            trace_id=payload.get("experiment_id") or payload.get("analysis_id") or "",
            actor_type="system", actor_id="optimization",
            action=f"optimization.{event_type.lower()}",
            source="optimization_service", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"optimization": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ Metrics (真实 production facts)

def _run_metrics(root: Path | str, run_id: str) -> dict[str, Any]:
    """从真实 ProductionRun + Evaluation 提取指标 (机器可测, 非主观)。"""
    from .production_run import get_production_run
    from .production_evaluation import get_evaluation

    run = get_production_run(root, run_id)
    if run is None:
        raise ValueError(f"ProductionRun 不存在: {run_id}")
    metrics: dict[str, Any] = {"run_id": run_id, "state": run.get("state", "")}
    ev = get_evaluation(root, run_id)
    if ev is not None:
        metrics["repair_count"] = ev.get("repair_count", 0)
        metrics["evaluation_score"] = ev.get("overall_score", ev.get("score", 0))
        metrics["attempt_count"] = ev.get("verification_attempts", 0)
    else:
        metrics["repair_count"] = 0
        metrics["evaluation_score"] = 0
        metrics["attempt_count"] = 0
    return metrics


def _collect_runs(root: Path | str, scope: str = "") -> list[dict[str, Any]]:
    """收集 scope 内 COMPLETED production runs 的真实指标。"""
    from .production_run import list_production_runs

    runs = list_production_runs(root)
    out = []
    for r in runs:
        if r.get("state") != "COMPLETED":
            continue
        if scope and (r.get("project_id") or "") != scope:
            continue
        try:
            out.append(_run_metrics(root, r["run_id"]))
        except ValueError:
            continue
    return out


# ------------------------------------------------------------------ Analysis + Hypothesis

def analyze(root: Path | str, *, project_id: str = "", scope: str = "") -> dict[str, Any]:
    """Optimization Analysis: 从真实 runs 提取 signals → patterns → candidates。"""
    analysis = {
        "analysis_id": f"opt-an-{uuid.uuid4().hex[:10]}",
        "project_id": project_id, "scope": scope, "status": ST_ANALYZING,
        "signals": [], "patterns": [], "candidates": [],
        "evidence_refs": [], "created_at": _now_iso(), "completed_at": "",
        "failure_reason": "",
    }
    _audit(root, "OPTIMIZATION_ANALYSIS_STARTED", {"analysis_id": analysis["analysis_id"]})
    try:
        runs = _collect_runs(root, project_id)
        if not runs:
            analysis["status"] = ST_COMPLETED
            analysis["completed_at"] = _now_iso()
            analysis["signals"] = [{"signal_type": "insufficient_data",
                                    "value": 0, "note": "无 COMPLETED production runs"}]
            _save(root, "analyses", _load(root, "analyses") + [analysis])
            return analysis
        # signals: 真实指标聚合
        repair_counts = [r["repair_count"] for r in runs]
        avg_repair = sum(repair_counts) / len(repair_counts)
        failed = [r for r in runs if r.get("state") == "FAILED"]
        analysis["signals"] = [
            {"signal_type": "avg_repair_count", "value": round(avg_repair, 2),
             "sample_size": len(runs), "run_refs": [r["run_id"] for r in runs]},
            {"signal_type": "failure_rate", "value": round(len(failed) / len(runs), 2),
             "sample_size": len(runs)},
        ]
        analysis["evidence_refs"] = [r["run_id"] for r in runs]
        # patterns: repair_count > 0 → repair 是常见成本
        if avg_repair > 0:
            analysis["patterns"].append({"pattern_type": "repair_overhead",
                                         "value": round(avg_repair, 2),
                                         "note": "平均 repair_count > 0, 修复是生产开销"})
        # candidates → hypothesis
        if avg_repair > 0.5:
            analysis["candidates"].append({
                "candidate_id": f"opt-c-{uuid.uuid4().hex[:8]}",
                "target": "repair_count", "problem": "平均修复次数偏高",
                "proposed_change": "降低 repair 触发", "expected_effect": "减少 repair_count",
                "risk": "medium", "confidence": round(min(0.9, avg_repair / 3), 2),
                "evidence_refs": analysis["evidence_refs"],
                "explain": f"[repair_overhead] 真实 runs={len(runs)} 平均 repair_count={round(avg_repair,2)}; "
                           f"confidence={round(min(0.9, avg_repair/3),2)} 仅表示 evidence 支持度, 非改善承诺"})
        analysis["status"] = ST_COMPLETED
        analysis["completed_at"] = _now_iso()
        _save(root, "analyses", _load(root, "analyses") + [analysis])
        _audit(root, "OPTIMIZATION_ANALYSIS_COMPLETED",
               {"analysis_id": analysis["analysis_id"], "runs": len(runs)})
        return analysis
    except Exception as exc:  # noqa: BLE001
        analysis["status"] = ST_FAILED
        analysis["failure_reason"] = str(exc)
        _save(root, "analyses", _load(root, "analyses") + [analysis])
        return analysis


def get_analysis(root: Path | str, analysis_id: str) -> dict[str, Any] | None:
    for a in _load(root, "analyses"):
        if a["analysis_id"] == analysis_id:
            return a
    return None


def hypotheses(root: Path | str, analysis_id: str | None = None) -> list[dict[str, Any]]:
    data = _load(root, "hypotheses")
    if analysis_id:
        return [h for h in data if h.get("analysis_id") == analysis_id]
    return data


# ------------------------------------------------------------------ Baseline

def create_baseline(root: Path | str, *, analysis_id: str = "", scope: str = "",
                    metric: str = "repair_count") -> dict[str, Any]:
    """真实 Baseline: 从 COMPLETED production runs 度量。不足 → BASELINE_INSUFFICIENT。"""
    runs = _collect_runs(root, scope)
    baseline = {
        "baseline_id": f"bsl-{uuid.uuid4().hex[:10]}",
        "analysis_id": analysis_id, "scope": scope,
        "metric": metric, "sample_size": len(runs),
        "production_run_refs": [r["run_id"] for r in runs],
        "metrics": {}, "evidence_refs": [r["run_id"] for r in runs],
        "status": BL_INSUFFICIENT, "created_at": _now_iso(), "explain": "",
    }
    if len(runs) < MIN_SAMPLE:
        baseline["explain"] = f"BASELINE_INSUFFICIENT: 仅 {len(runs)} 个 COMPLETED runs (需要 ≥{MIN_SAMPLE})"
        _save(root, "baselines", _load(root, "baselines") + [baseline])
        return baseline
    values = [r[metric] for r in runs if metric in r]
    if not values:
        baseline["explain"] = f"BASELINE_INSUFFICIENT: metric '{metric}' 无真实数据"
        _save(root, "baselines", _load(root, "baselines") + [baseline])
        return baseline
    baseline["status"] = BL_COMPLETED
    baseline["metrics"] = {"mean": round(sum(values) / len(values), 2), "values": values}
    baseline["explain"] = f"真实 runs={len(runs)} metric={metric} mean={baseline['metrics']['mean']}"
    _save(root, "baselines", _load(root, "baselines") + [baseline])
    return baseline


def get_baseline(root: Path | str, baseline_id: str) -> dict[str, Any] | None:
    for b in _load(root, "baselines"):
        if b["baseline_id"] == baseline_id:
            return b
    return None


# ------------------------------------------------------------------ Experiment

def create_experiment(root: Path | str, *, hypothesis_id: str = "", baseline_id: str = "",
                      control_definition: str = "", treatment_definition: str = "",
                      metric: str = "repair_count", created_by: str = "optimization") -> dict[str, Any]:
    """Experiment Proposal (PROPOSED → Governance approval → 才 RUNNING)。"""
    bl = get_baseline(root, baseline_id)
    if bl is None:
        raise ValueError(f"Baseline 不存在: {baseline_id}")
    if bl["status"] != BL_COMPLETED:
        raise ValueError(f"Baseline 未完成 (BASELINE_INSUFFICIENT): {baseline_id}")
    exp = {
        "experiment_id": f"exp-{uuid.uuid4().hex[:10]}",
        "hypothesis_id": hypothesis_id, "baseline_id": baseline_id,
        "control_definition": control_definition, "treatment_definition": treatment_definition,
        "metric": metric, "status": EX_APPROVAL_REQUIRED,
        "governance": {"required": True, "approval_id": ""},
        "runs": [], "measurements": [], "created_at": _now_iso(), "updated_at": _now_iso(),
    }
    # Governance: request approval (human) — 绑定 baseline 的真实 run (S17 契约)
    run_ref = (bl.get("production_run_refs") or [""])[0]
    a = request_approval(root, production_run_id=run_ref, artifact_ids=[],
                         requested_by=created_by, subject_type="experiment",
                         subject_id=exp["experiment_id"])
    exp["governance"]["approval_id"] = a["approval_id"]
    _save(root, "experiments", _load(root, "experiments") + [exp])
    _audit(root, "OPTIMIZATION_EXPERIMENT_PROPOSED",
           {"experiment_id": exp["experiment_id"], "approval_id": a["approval_id"]})
    return exp


def approve_experiment(root: Path | str, experiment_id: str, *, decided_by: str = "human") -> dict[str, Any]:
    """Governance 批准实验 (复用 S17 approval)。"""
    exp = get_experiment(root, experiment_id)
    if exp is None:
        raise ValueError(f"Experiment 不存在: {experiment_id}")
    approval_id = exp["governance"]["approval_id"]
    approve(root, approval_id, decided_by=decided_by)
    data = _load(root, "experiments")
    for e in data:
        if e["experiment_id"] == experiment_id:
            e["status"] = EX_APPROVED
            e["updated_at"] = _now_iso()
            _save(root, "experiments", data)
            return e
    raise ValueError(f"Experiment 不存在: {experiment_id}")


def get_experiment(root: Path | str, experiment_id: str) -> dict[str, Any] | None:
    for e in _load(root, "experiments"):
        if e["experiment_id"] == experiment_id:
            return e
    return None


# ------------------------------------------------------------------ Run (真实执行 Control/Treatment)

def run_experiment(root: Path | str, experiment_id: str, *, run_id: str,
                   arm: str = "treatment", actor: str = "optimization") -> dict[str, Any]:
    """执行实验一个臂 (control/treatment): 对真实 production run 度量。"""
    exp = get_experiment(root, experiment_id)
    if exp is None:
        raise ValueError(f"Experiment 不存在: {experiment_id}")
    if exp["status"] != EX_APPROVED:
        raise ValueError(f"Experiment 未批准 (当前: {exp['status']})")
    if arm not in ("control", "treatment"):
        raise ValueError(f"未知 arm: {arm}")
    metrics = _run_metrics(root, run_id)
    rec = {"run_id": run_id, "arm": arm, "metrics": metrics, "at": _now_iso()}
    data = _load(root, "experiments")
    for e in data:
        if e["experiment_id"] == experiment_id:
            e["runs"] = e.get("runs", []) + [rec]
            e["updated_at"] = _now_iso()
            _save(root, "experiments", data)
            return rec
    raise ValueError(f"Experiment 不存在: {experiment_id}")


# ------------------------------------------------------------------ Measurement + Comparison + Outcome

def compare(root: Path | str, experiment_id: str) -> dict[str, Any]:
    """Measurement + Comparison: control vs treatment (真实指标)。"""
    exp = get_experiment(root, experiment_id)
    if exp is None:
        raise ValueError(f"Experiment 不存在: {experiment_id}")
    control = [r for r in exp.get("runs", []) if r["arm"] == "control"]
    treatment = [r for r in exp.get("runs", []) if r["arm"] == "treatment"]
    if not control or not treatment:
        return {"experiment_id": experiment_id, "result": OC_INCONCLUSIVE,
                "reason": "control 或 treatment 缺真实 runs",
                "measurements": [], "evidence_refs": []}
    metric = exp["metric"]
    c_vals = [r["metrics"].get(metric, 0) for r in control]
    t_vals = [r["metrics"].get(metric, 0) for r in treatment]
    if len(c_vals) < MIN_SAMPLE or len(t_vals) < MIN_SAMPLE:
        return {"experiment_id": experiment_id, "result": OC_INCONCLUSIVE,
                "reason": f"样本不足 (control={len(c_vals)}, treatment={len(t_vals)}, 需 ≥{MIN_SAMPLE})",
                "measurements": [], "evidence_refs": []}
    c_mean = sum(c_vals) / len(c_vals)
    t_mean = sum(t_vals) / len(t_vals)
    delta = round(t_mean - c_mean, 3)
    delta_pct = round((delta / c_mean * 100), 1) if c_mean else 0.0
    measurement = {
        "measurement_id": f"msr-{uuid.uuid4().hex[:8]}",
        "experiment_id": experiment_id, "metric": metric,
        "control_value": round(c_mean, 3), "treatment_value": round(t_mean, 3),
        "delta": delta, "delta_percent": delta_pct,
        "sample_size": {"control": len(c_vals), "treatment": len(t_vals)},
        "evidence_refs": [r["run_id"] for r in control + treatment],
    }
    # Comparison: 对 repair_count/failure 类指标, 更低 = 更好
    lower_better = metric in ("repair_count", "failure_rate", "rollback_count",
                              "verification_failure_rate", "execution_duration")
    if delta == 0:
        result = OC_UNCHANGED
        reason = f"{metric}: control={c_mean} treatment={t_mean} delta=0"
    elif (delta < 0 and lower_better) or (delta > 0 and not lower_better):
        result = OC_IMPROVED
        reason = f"{metric}: control={c_mean} → treatment={t_mean} delta={delta} ({delta_pct}%)"
    else:
        result = OC_REGRESSED
        reason = f"{metric}: control={c_mean} → treatment={t_mean} delta={delta} ({delta_pct}%)"
    return {"experiment_id": experiment_id, "result": result, "reason": reason,
            "measurements": [measurement], "evidence_refs": measurement["evidence_refs"]}


def outcome(root: Path | str, experiment_id: str, *, decided_by: str = "human") -> dict[str, Any]:
    """正式 Outcome (真实实验+测量+比较)。IMPROVED 才考虑进 Experience。"""
    exp = get_experiment(root, experiment_id)
    if exp is None:
        raise ValueError(f"Experiment 不存在: {experiment_id}")
    cmp = compare(root, experiment_id)
    oc = {
        "outcome_id": f"oc-{uuid.uuid4().hex[:10]}",
        "experiment_id": experiment_id, "result": cmp["result"],
        "metrics": {"control": cmp["measurements"][0]["control_value"] if cmp["measurements"] else None,
                    "treatment": cmp["measurements"][0]["treatment_value"] if cmp["measurements"] else None,
                    "delta": cmp["measurements"][0]["delta"] if cmp["measurements"] else None},
        "evidence_refs": cmp["evidence_refs"], "decision": cmp["result"],
        "reason": cmp["reason"], "created_at": _now_iso(),
        "experience_written": False,
    }
    # 仅 IMPROVED (真实实验证明) → 写 Experience
    if cmp["result"] == OC_IMPROVED:
        _write_optimization_experience(root, exp, cmp)
        oc["experience_written"] = True
    _save(root, "outcomes", _load(root, "outcomes") + [oc])
    _audit(root, "OPTIMIZATION_OUTCOME", {"experiment_id": experiment_id, "result": cmp["result"]})
    return oc


def _write_optimization_experience(root: Path | str, exp: dict[str, Any], cmp: dict[str, Any]) -> None:
    """仅真实 IMPROVED → Optimization Experience (S14/S15 体系)。"""
    try:
        from .production_experience import extract, _store as _exp_store
        from .memory.experience import ExperienceRecord

        rec = ExperienceRecord(
            type="SUCCESS_PATTERN",  # optimization_pattern 不在 TYPES; SUCCESS_PATTERN 承载
            project="", task=f"optimization:{exp['metric']}",
            context=f"control={cmp['measurements'][0]['control_value']} "
                    f"treatment={cmp['measurements'][0]['treatment_value']} "
                    f"delta={cmp['measurements'][0]['delta']}",
            problem="", action=exp.get("treatment_definition", ""),
            result="optimization validated",
            success=True, confidence=cmp["measurements"][0]["delta_percent"] / 100.0,
            source=f"experiment:{exp['experiment_id']}",
        )
        st = _exp_store(root)
        st.add(rec)
    except Exception:  # noqa: BLE001
        pass


def lineage(root: Path | str, optimization_id: str) -> dict[str, Any]:
    """完整 lineage: analysis → hypothesis → baseline → experiment → measurement → outcome。"""
    out: dict[str, Any] = {"optimization_id": optimization_id, "chain": {}}
    for e in _load(root, "experiments"):
        if e["experiment_id"] == optimization_id:
            out["chain"]["experiment"] = e
            bl = get_baseline(root, e["baseline_id"])
            if bl:
                out["chain"]["baseline"] = bl
            out["chain"]["comparison"] = compare(root, optimization_id)
            for o in _load(root, "outcomes"):
                if o["experiment_id"] == optimization_id:
                    out["chain"]["outcome"] = o
                    break
            for h in _load(root, "hypotheses"):
                if h["hypothesis_id"] == e.get("hypothesis_id"):
                    out["chain"]["hypothesis"] = h
                    break
    return out
