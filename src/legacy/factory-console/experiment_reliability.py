"""factory-console/experiment_reliability.py — S27 Production Experiment Reliability.

可靠地区分 Agent/Production/Verification/Evaluation/Infrastructure 失败,
判断 Production Run 是否有资格成为 Optimization Experiment 有效样本。

- Production Outcome Contract (COMPLETED/INCOMPLETE/FAILED/BLOCKED/CANCELLED 投影)
- Failure Classification (deterministic, evidence_refs, UNKNOWN 不猜测)
- Sample Eligibility (ELIGIBLE/INELIGIBLE + reason/classification/evidence_refs)
- Selection Bias 保护 (完整 denominator)
- Evaluation Quality Contract (EVALUATION_INVALID)
- Experiment Reliability 聚合

原则:
- Classification 是 Projection, 非新事实源 (facts 来自 ProductionRun/Verification/Evaluation)
- 失败样本保留在 denominator (不静默删除)
- 证据不足 → UNKNOWN (不猜测)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .production_run import get_production_run
from .production_evaluation import get_evaluation

#: Production Outcome
OC_COMPLETED = "COMPLETED"
OC_INCOMPLETE = "INCOMPLETE"
OC_FAILED = "FAILED"
OC_BLOCKED = "BLOCKED"
OC_CANCELLED = "CANCELLED"

#: Failure Classification
FC_AGENT = "AGENT_FAILURE"
FC_PRODUCTION = "PRODUCTION_FAILURE"
FC_VERIFICATION = "VERIFICATION_FAILURE"
FC_EVALUATION = "EVALUATION_FAILURE"
FC_EXPERIMENT = "EXPERIMENT_FAILURE"
FC_INFRA = "INFRASTRUCTURE_FAILURE"
FC_BUDGET = "BUDGET_EXCEEDED"
FC_TIMEOUT = "TIMEOUT"
FC_GOV = "GOVERNANCE_BLOCKED"
FC_UNKNOWN = "UNKNOWN"

#: Eligibility
EL_ELIGIBLE = "ELIGIBLE"
EL_INELIGIBLE = "INELIGIBLE"

#: 内置 pytest 失败关键词 (真实代码 evidence: professional_workflow.py:503)
VERIFICATION_FAIL_KEYWORDS = ("内置 pytest 失败", "verification failed", "pytest")
AGENT_FAIL_KEYWORDS = ("未知角色", "executor error", "LLM 空输出")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "reliability" / f"{name}.json"


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
            trace_id=payload.get("sample_id") or payload.get("experiment_id") or "",
            actor_type="system", actor_id="reliability",
            action=f"reliability.{event_type.lower()}",
            source="experiment_reliability", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"reliability": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ Production Outcome

def production_outcome(root: Path | str, production_run_id: str) -> dict[str, Any]:
    """Production Outcome 投影 (facts → outcome)。"""
    run = get_production_run(root, production_run_id)
    if run is None:
        return {"outcome": OC_UNKNOWN if False else "UNKNOWN_RUN",
                "production_run_id": production_run_id, "evidence_refs": [],
                "explain": "ProductionRun 不存在"}
    state = run.get("state", "")
    if state == "COMPLETED":
        outcome = OC_COMPLETED
    elif state == "BLOCKED":
        outcome = OC_BLOCKED
    elif state == "FAILED":
        outcome = OC_FAILED
    elif state in ("PENDING", "RUNNING"):
        outcome = OC_INCOMPLETE
    else:
        outcome = OC_CANCELLED
    return {"outcome": outcome, "production_run_id": production_run_id,
            "state": state, "evidence_refs": [production_run_id],
            "explain": f"ProductionRun state={state} → outcome={outcome}"}


# ------------------------------------------------------------------ Failure Classification

def classify_failure(root: Path | str, production_run_id: str) -> dict[str, Any]:
    """确定性 Failure Classification (evidence_refs + explain; UNKNOWN 不猜测)。"""
    run = get_production_run(root, production_run_id)
    if run is None:
        return {"classification": FC_UNKNOWN, "confidence": 0.0,
                "evidence_refs": [], "explain": "ProductionRun 不存在"}
    state = run.get("state", "")
    failure = str(run.get("failure") or "")
    refs = [production_run_id]

    if state == "BLOCKED":
        return {"classification": FC_GOV, "confidence": 1.0, "evidence_refs": refs,
                "explain": f"ProductionRun BLOCKED (Governance/Policy): {failure[:100]}"}
    if state != "FAILED":
        # 未失败 → 无分类 (可能是 COMPLETED/INCOMPLETE)
        return {"classification": "NO_FAILURE", "confidence": 1.0,
                "evidence_refs": refs, "explain": f"ProductionRun state={state} 无失败"}
    # FAILED → 从真实 failure 文本分类
    if any(k in failure for k in VERIFICATION_FAIL_KEYWORDS):
        return {"classification": FC_VERIFICATION, "confidence": 1.0, "evidence_refs": refs,
                "explain": f"Production 完成但 verification 失败: {failure[:150]}"}
    if any(k in failure for k in AGENT_FAIL_KEYWORDS):
        return {"classification": FC_AGENT, "confidence": 1.0, "evidence_refs": refs,
                "explain": f"Agent 执行失败: {failure[:150]}"}
    if "timeout" in failure.lower() or "timed out" in failure.lower():
        return {"classification": FC_TIMEOUT, "confidence": 1.0, "evidence_refs": refs,
                "explain": f"执行超时: {failure[:150]}"}
    if "budget" in failure.lower():
        return {"classification": FC_BUDGET, "confidence": 1.0, "evidence_refs": refs,
                "explain": f"预算超限: {failure[:150]}"}
    # 证据不足 → UNKNOWN (不猜测)
    return {"classification": FC_UNKNOWN, "confidence": 0.2, "evidence_refs": refs,
            "explain": f"失败原因无法从 evidence 确定: {failure[:150]} (不猜测)"}


# ------------------------------------------------------------------ Evaluation Quality

def evaluation_quality(root: Path | str, production_run_id: str) -> dict[str, Any]:
    """Evaluation Quality Contract: 判断 Evaluation 是否可作为 measurement 输入。"""
    ev = get_evaluation(root, production_run_id)
    if ev is None:
        return {"valid": False, "reason": "EVALUATION_INVALID",
                "evidence_refs": [], "explain": "Evaluation 不存在"}
    metric = ev.get("overall_score")
    if metric is None:
        return {"valid": False, "reason": "EVALUATION_INVALID",
                "evidence_refs": [ev.get("evaluation_id", "")],
                "explain": "Evaluation 存在但无 overall_score metric"}
    return {"valid": True, "reason": "", "metric_value": metric,
            "evidence_refs": [ev.get("evaluation_id", "")],
            "evaluation_id": ev.get("evaluation_id", ""),
            "explain": f"Evaluation 有效: overall_score={metric}"}


# ------------------------------------------------------------------ Sample Eligibility

def sample_eligibility(root: Path | str, production_run_id: str, *,
                       experiment_id: str = "", variant_id: str = "") -> dict[str, Any]:
    """Sample Eligibility (ELIGIBLE/INELIGIBLE + reason/classification/evidence_refs)。"""
    outcome = production_outcome(root, production_run_id)
    cls = classify_failure(root, production_run_id)
    eq = evaluation_quality(root, production_run_id)
    refs = [production_run_id] + [r for r in eq.get("evidence_refs", []) if r]

    if outcome["outcome"] != OC_COMPLETED:
        return {"eligibility": EL_INELIGIBLE,
                "reason": f"Production 未完成 (outcome={outcome['outcome']})",
                "failure_class": cls["classification"],
                "evidence_refs": refs,
                "explain": f"{outcome['explain']}; {cls['explain']}",
                "production_run_id": production_run_id}
    if cls["classification"] == FC_VERIFICATION:
        return {"eligibility": EL_INELIGIBLE, "reason": "Verification failed",
                "failure_class": FC_VERIFICATION, "evidence_refs": refs,
                "explain": cls["explain"], "production_run_id": production_run_id}
    if not eq["valid"]:
        return {"eligibility": EL_INELIGIBLE, "reason": "Evaluation invalid",
                "failure_class": FC_EVALUATION, "evidence_refs": refs,
                "explain": eq["explain"], "production_run_id": production_run_id}
    return {"eligibility": EL_ELIGIBLE, "reason": "",
            "failure_class": "NONE", "evidence_refs": refs,
            "metric_value": eq.get("metric_value"),
            "explain": "Production COMPLETED + Verification PASS + Evaluation 有效",
            "production_run_id": production_run_id,
            "experiment_id": experiment_id, "variant_id": variant_id}


# ------------------------------------------------------------------ Experiment Reliability

def experiment_reliability(root: Path | str, experiment_id: str,
                           samples: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Reliability 聚合 (完整 denominator, 防 selection bias)。"""
    from .llm_experiment_service import _get_llm_exp

    try:
        exp = _get_llm_exp(root, experiment_id)
    except Exception:  # noqa: BLE001
        exp = None
    if samples is None:
        samples = (exp or {}).get("llm_experiment", {}).get("samples", [])
    classifications: dict[str, int] = {}
    eligible = 0
    detailed = []
    for s in samples:
        run_id = s.get("production_run_id", "")
        if not run_id:
            if s.get("reason") in ("BUDGET_EXCEEDED", "TOTAL_BUDGET_EXCEEDED"):
                classification = FC_BUDGET
            elif s.get("reason") == "NOT_APPROVED":
                classification = FC_GOV
            else:
                classification = FC_UNKNOWN
            elig = EL_INELIGIBLE
            reason = s.get("reason", "no run")
        else:
            cls = classify_failure(root, run_id)
            classification = cls["classification"]
            elig_rec = sample_eligibility(root, run_id,
                                          experiment_id=experiment_id,
                                          variant_id=s.get("variant_id", ""))
            elig = elig_rec["eligibility"]
            reason = elig_rec["reason"]
        classifications[classification] = classifications.get(classification, 0) + 1
        if elig == EL_ELIGIBLE:
            eligible += 1
        detailed.append({"sample_id": f"smpl-{uuid.uuid4().hex[:8]}",
                         "arm": s.get("arm", ""), "production_run_id": run_id,
                         "eligibility": elig, "reason": reason,
                         "failure_class": classification,
                         "evidence_refs": [run_id] if run_id else []})
    total = len(samples)
    return {
        "experiment_id": experiment_id,
        "total_samples": total,
        "eligible_samples": eligible,
        "ineligible_samples": total - eligible,
        "failed_samples": sum(1 for s in samples if s.get("state") == "FAILED"),
        "incomplete_samples": sum(1 for s in samples if not s.get("eligible") and s.get("state") != "FAILED"),
        "blocked_samples": sum(1 for s in samples if s.get("reason") in ("NOT_APPROVED", "GOVERNANCE_BLOCKED")),
        "failure_classification_distribution": classifications,
        "samples": detailed,
        "explain": (f"Total={total}, Eligible={eligible}, Ineligible={total - eligible}; "
                    f"distribution={classifications}"),
    }


def inspect_sample(root: Path | str, sample_id: str) -> dict[str, Any]:
    """Sample 详情 (lineage: run → outcome → classification → eligibility → evaluation)。"""
    for exp_name in ("experiments",):
        for e in _load(root, exp_name):
            for s in e.get("llm_experiment", {}).get("samples", []):
                sid = f"smpl-{s.get('production_run_id', '')[:8]}" or ""
    # 直接按 production_run_id 查
    for e in _load(root, "experiments"):
        for s in e.get("llm_experiment", {}).get("samples", []):
            if s.get("production_run_id", "")[:8] == sample_id[:8] or s.get("production_run_id") == sample_id:
                run_id = s["production_run_id"]
                return {"sample": s,
                        "outcome": production_outcome(root, run_id),
                        "classification": classify_failure(root, run_id),
                        "eligibility": sample_eligibility(root, run_id,
                                                          experiment_id=e.get("experiment_id", ""),
                                                          variant_id=s.get("variant_id", "")),
                        "evaluation_quality": evaluation_quality(root, run_id)}
    raise ValueError(f"Sample 不存在: {sample_id}")
