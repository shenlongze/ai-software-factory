"""factory-console/promotion_service.py — S38 Learning Evaluation & Governed Promotion.

LearningCandidate (S37 VALIDATED) → PromotionCandidate
→ Evaluation (baseline vs candidate, evidence-based, cost-aware)
→ Experiment (budget/sample/sandbox; max_runs/max_cost)
→ Comparison (IMPROVED/REGRESSED/INCONCLUSIVE/CONFLICT)
→ Governance (AUTO_APPROVE/REVIEW_REQUIRED/HUMAN_APPROVAL_REQUIRED/REJECT; 风险分类)
→ Canary (scope/runs/cost; regression → 复用 S21 rollback)
→ PromotionDecision + PromotionSnapshot (immutable)

Lifecycle: CANDIDATE→EVALUATING→EVALUATED→GOVERNED→CANARY→PROMOTED; 失败→REJECTED/INCONCLUSIVE/ROLLED_BACK
Plugin: Evaluator/Experimenter/Promotion Policy (Core 零修改替换)
复用: S21 rollback + S17 governance + S29 effectiveness + S33 performance + S37 learning

绝不: LLM→Production / Learning→Production / Evaluation PASS→无限自动
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

#: Promotion Lifecycle
PROM_STATES = ("CANDIDATE", "EVALUATING", "EVALUATED", "GOVERNED", "CANARY",
               "PROMOTED", "REJECTED", "INCONCLUSIVE", "ROLLED_BACK")
PROM_TRANSITIONS = {
    "CANDIDATE": ("EVALUATING", "REJECTED"),
    "EVALUATING": ("EVALUATED", "REJECTED", "INCONCLUSIVE"),
    "EVALUATED": ("GOVERNED", "REJECTED", "INCONCLUSIVE"),
    "GOVERNED": ("CANARY", "PROMOTED", "REJECTED"),
    "CANARY": ("PROMOTED", "REJECTED", "ROLLED_BACK"),
    "PROMOTED": (),
    "REJECTED": (),
    "INCONCLUSIVE": (),
    "ROLLED_BACK": (),
}

#: Risk
RISKS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

#: Governance Modes
GOV_MODES = ("AUTO_APPROVE", "REVIEW_REQUIRED", "HUMAN_APPROVAL_REQUIRED", "REJECT")

#: Promotion Plugins (strategy, Core 不 import 具体实现)
EVALUATOR_PLUGINS: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {}
POLICY_PLUGINS: dict[str, Callable[[dict[str, Any]], str]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "promotion" / f"{name}.json"


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
            trace_id=payload.get("candidate_id") or payload.get("experiment_id") or "",
            actor_type="system", actor_id="promotion",
            action=f"promotion.{event_type.lower()}",
            source="promotion_service", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"promotion": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


def _find(root: Path | str, name: str, key: str, value: str) -> dict[str, Any]:
    for item in _load(root, name):
        if item.get(key) == value:
            return item
    raise ValueError(f"{name} 中无 {key}={value}")


def _update(root: Path | str, name: str, item: dict[str, Any]) -> None:
    data = _load(root, name)
    for i, x in enumerate(data):
        if x.get("candidate_id") == item.get("candidate_id") or \
           x.get("experiment_id") == item.get("experiment_id") or \
           x.get("evaluation_run_id") == item.get("evaluation_run_id") or \
           x.get("canary_id") == item.get("canary_id") or \
           x.get("promotion_candidate_id") == item.get("promotion_candidate_id"):
            data[i] = item
            _save(root, name, data)
            return
    _save(root, name, data + [item])


# ------------------------------------------------------------------ PromotionCandidate

def create_promotion_candidate(root: Path | str, *, learning_candidate_id: str,
                               target: str = "memory", baseline_ref: str = "",
                               candidate_ref: str = "", scope: str = "node",
                               risk: str = "MEDIUM") -> dict[str, Any]:
    """从 S37 LearningCandidate 创建 PromotionCandidate (统一 Contract)。"""
    if risk not in RISKS:
        raise ValueError(f"非法 risk: {risk}")
    # 验证 S37 candidate 存在 (Evidence-driven 输入)
    from .learning_engine_v2 import candidates as learn_cands
    lc = [c for c in learn_cands(root) if c["candidate_id"] == learning_candidate_id]
    if not lc:
        raise ValueError(f"LearningCandidate 不存在: {learning_candidate_id}")
    cand = {"promotion_candidate_id": f"prom-{uuid.uuid4().hex[:10]}",
            "learning_candidate_id": learning_candidate_id,
            "target": target, "baseline_ref": baseline_ref, "candidate_ref": candidate_ref,
            "scope": scope, "risk": risk, "lifecycle": "CANDIDATE",
            "created_at": _now_iso(),
            "lifecycle_history": [{"from": "S37", "to": "CANDIDATE", "at": _now_iso(), "actor": "learning"}]}
    _save(root, "candidates", _load(root, "candidates") + [cand])
    _audit(root, "PROMOTION_CANDIDATE", {"candidate_id": cand["promotion_candidate_id"],
                                         "learning_candidate_id": learning_candidate_id,
                                         "risk": risk})
    return cand


def promotion_candidates(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "candidates")


def _transition(root: Path | str, candidate_id: str, *, target: str,
                actor: str = "promotion") -> dict[str, Any]:
    data = _load(root, "candidates")
    for c in data:
        if c["promotion_candidate_id"] == candidate_id:
            current = c["lifecycle"]
            if target not in PROM_TRANSITIONS.get(current, ()) and target != current:
                raise ValueError(f"非法状态迁移: {current} → {target}")
            c["lifecycle"] = target
            c["lifecycle_history"] = c.get("lifecycle_history", []) + [
                {"from": current, "to": target, "at": _now_iso(), "actor": actor}]
            _save(root, "candidates", data)
            _audit(root, "PROMOTION_TRANSITION", {"candidate_id": candidate_id,
                                                  "from": current, "to": target})
            return c
    raise ValueError(f"PromotionCandidate 不存在: {candidate_id}")


# ------------------------------------------------------------------ Evaluation

def evaluate_candidate(root: Path | str, candidate_id: str, *,
                       baseline_metrics: dict[str, Any],
                       candidate_metrics: dict[str, Any],
                       sample_count: int = 0, min_samples: int = 5,
                       evaluator_plugin: str = "") -> dict[str, Any]:
    """Evaluation: baseline vs candidate (evidence-based; 小样本 → INCONCLUSIVE)。"""
    _transition(root, candidate_id, target="EVALUATING")
    # Evaluator Plugin hook (可替换, Core 零修改)
    if evaluator_plugin and evaluator_plugin in EVALUATOR_PLUGINS:
        result = EVALUATOR_PLUGINS[evaluator_plugin](baseline_metrics, candidate_metrics)
    else:
        result = _default_evaluate(baseline_metrics, candidate_metrics, sample_count, min_samples)
    run = {"evaluation_run_id": f"eval-{uuid.uuid4().hex[:10]}",
           "candidate_id": candidate_id, "baseline_metrics": baseline_metrics,
           "candidate_metrics": candidate_metrics, "sample_count": sample_count,
           "result": result["status"], "deltas": result["deltas"],
           "confidence": result["confidence"], "cost_type": "estimated",
           "created_at": _now_iso()}
    _save(root, "evaluations", _load(root, "evaluations") + [run])
    if result["status"] == "INCONCLUSIVE":
        _transition(root, candidate_id, target="INCONCLUSIVE")
    else:
        _transition(root, candidate_id, target="EVALUATED")
    return run


def _default_evaluate(baseline: dict[str, Any], candidate: dict[str, Any],
                      sample_count: int, min_samples: int) -> dict[str, Any]:
    """确定性比较: delta_success/verification/recovery/quality/cost → IMPROVED/REGRESSED/INCONCLUSIVE。"""
    if sample_count < min_samples:
        return {"status": "INCONCLUSIVE",
                "deltas": {}, "confidence": "unknown",
                "explain": f"样本不足 ({sample_count} < {min_samples}), 不伪装"}
    b_s = baseline.get("success", 0); c_s = candidate.get("success", 0)
    b_v = baseline.get("verification", 0); c_v = candidate.get("verification", 0)
    b_q = baseline.get("quality", 0); c_q = candidate.get("quality", 0)
    b_c = baseline.get("cost", 0.01); c_c = candidate.get("cost", 0.01)
    deltas = {"delta_success": round(c_s - b_s, 3),
              "delta_verification": round(c_v - b_v, 3),
              "delta_quality": round(c_q - b_q, 3),
              "delta_cost": round(c_c - b_c, 6)}
    # Cost-aware: quality/cost 比值
    b_ratio = (b_q + 0.001) / b_c if b_c else 0
    c_ratio = (c_q + 0.001) / c_c if c_c else 0
    deltas["delta_value_per_cost"] = round(c_ratio - b_ratio, 3)
    composite_c = c_s + c_v + c_q
    composite_b = b_s + b_v + b_q
    if composite_c > composite_b and c_s >= b_s:
        status = "IMPROVED"
    elif composite_c < composite_b:
        status = "REGRESSED"
    else:
        status = "INCONCLUSIVE"
    return {"status": status, "deltas": deltas, "confidence": "validated"}


# ------------------------------------------------------------------ Experiment

def create_experiment(root: Path | str, *, candidate_id: str,
                      max_runs: int = 10, max_cost: float = 0.5,
                      max_duration_sec: int = 3600) -> dict[str, Any]:
    """Experiment Contract (budget/sample/sandbox; 超限 STOP)。"""
    exp = {"experiment_id": f"exp-{uuid.uuid4().hex[:10]}",
           "candidate_id": candidate_id, "max_runs": max_runs,
           "max_cost": max_cost, "max_duration_sec": max_duration_sec,
           "runs_used": 0, "cost_used": 0.0, "started_at": _now_iso(),
           "status": "RUNNING"}
    _save(root, "experiments", _load(root, "experiments") + [exp])
    return exp


def experiment_record_run(root: Path | str, experiment_id: str, *,
                          cost: float = 0.0, result: str = "") -> dict[str, Any]:
    """Experiment 记录 run (budget 检查: 超 max_runs/max_cost → STOP)。"""
    exp = _find(root, "experiments", "experiment_id", experiment_id)
    exp["runs_used"] += 1
    exp["cost_used"] = round(exp.get("cost_used", 0) + cost, 6)
    exp["runs"] = exp.get("runs", []) + [{"result": result, "cost": cost,
                                          "at": _now_iso()}]
    if exp["runs_used"] >= exp["max_runs"] or exp["cost_used"] >= exp["max_cost"]:
        exp["status"] = "STOPPED"
        exp["stop_reason"] = "budget_exhausted"
    _update(root, "experiments", exp)
    return exp


def experiments(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "experiments")


# ------------------------------------------------------------------ Governance + Risk

def classify_risk(root: Path | str, *, blast_radius: str = "node",
                  permission_scope: str = "read",
                  production_impact: bool = False,
                  capability_change: bool = False) -> str:
    """Risk 分类 (blast_radius/permission/production_impact/capability_change)。"""
    if production_impact and capability_change:
        return "CRITICAL"
    if blast_radius in ("workforce", "organization") or capability_change:
        return "HIGH"
    if blast_radius == "project" or permission_scope == "write":
        return "MEDIUM"
    return "LOW"


def governance_mode(risk: str, *, evidence_sufficient: bool = True) -> str:
    """Governance Mode: LOW+evidence → AUTO; MEDIUM → REVIEW; HIGH/CRITICAL → HUMAN。"""
    if risk in ("HIGH", "CRITICAL"):
        return "HUMAN_APPROVAL_REQUIRED"
    if risk == "MEDIUM":
        return "REVIEW_REQUIRED"
    if not evidence_sufficient:
        return "REVIEW_REQUIRED"
    return "AUTO_APPROVE"


def decide_promotion(root: Path | str, candidate_id: str, *,
                     decision: str = "APPROVE", actor: str = "human",
                     note: str = "") -> dict[str, Any]:
    """Governance Decision: APPROVE/REJECT (High-risk 必须 Human Gate)。"""
    cand = _find(root, "candidates", "promotion_candidate_id", candidate_id)
    risk = cand["risk"]
    if risk in ("HIGH", "CRITICAL") and actor != "human":
        raise PermissionError(f"高风险 ({risk}) Promotion 必须 Human Gate: {candidate_id}")
    if decision == "REJECT":
        _transition(root, candidate_id, target="REJECTED", actor=actor)
        return {"candidate_id": candidate_id, "decision": "REJECTED", "actor": actor}
    if cand["lifecycle"] != "EVALUATED":
        raise ValueError(f"未 EVALUATED 不可 Governance: {cand['lifecycle']}")
    _transition(root, candidate_id, target="GOVERNED", actor=actor)
    return {"candidate_id": candidate_id, "decision": "GOVERNED",
            "mode": governance_mode(risk), "actor": actor, "note": note}


# ------------------------------------------------------------------ Canary

def create_canary(root: Path | str, *, candidate_id: str,
                  scope: str = "node", max_runs: int = 3,
                  max_cost: float = 0.1, max_duration_sec: int = 600) -> dict[str, Any]:
    """Canary (受 scope/runs/cost/duration 限制; regression → rollback)。"""
    _transition(root, candidate_id, target="CANARY")
    can = {"canary_id": f"canary-{uuid.uuid4().hex[:10]}",
           "candidate_id": candidate_id, "scope": scope,
           "max_runs": max_runs, "max_cost": max_cost,
           "max_duration_sec": max_duration_sec, "runs": [],
           "runs_used": 0, "cost_used": 0.0, "status": "RUNNING",
           "created_at": _now_iso()}
    _save(root, "canaries", _load(root, "canaries") + [can])
    return can


def canary_record_run(root: Path | str, canary_id: str, *, result: str,
                      cost: float = 0.0, verification: str = "PASS") -> dict[str, Any]:
    """Canary run 记录 (真实 Evidence; 超限 STOP; 失败累积 → 判定)。"""
    can = _find(root, "canaries", "canary_id", canary_id)
    can["runs"] = can.get("runs", []) + [{"result": result, "cost": cost,
                                          "verification": verification, "at": _now_iso()}]
    can["runs_used"] += 1
    can["cost_used"] = round(can.get("cost_used", 0) + cost, 6)
    if can["runs_used"] >= can["max_runs"] or can["cost_used"] >= can["max_cost"]:
        can["status"] = "STOPPED"
    _update(root, "canaries", can)
    return can


def canary_compare(root: Path | str, canary_id: str, *,
                   baseline_success: float = 0.8) -> dict[str, Any]:
    """Canary vs Baseline: PASS (Canary >= Baseline) / FAIL (Regression → rollback)。"""
    can = _find(root, "canaries", "canary_id", canary_id)
    runs = can.get("runs", [])
    if not runs:
        return {"canary_id": canary_id, "status": "INCONCLUSIVE",
                "explain": "Canary 无 runs"}
    success = sum(1 for r in runs if r.get("verification") == "PASS") / len(runs)
    can_success = round(success, 3)
    if can_success >= baseline_success:
        result = "PASS"
    else:
        result = "FAIL"
    return {"canary_id": canary_id, "status": result,
            "canary_success": can_success, "baseline_success": baseline_success,
            "runs": len(runs), "explain": f"canary {can_success} vs baseline {baseline_success}"}


def promote(root: Path | str, candidate_id: str, *, canary_id: str = "",
            actor: str = "system") -> dict[str, Any]:
    """Promotion (仅 GOVERNED 或 CANARY PASS 后; 生成 immutable Snapshot)。"""
    cand = _find(root, "candidates", "promotion_candidate_id", candidate_id)
    if cand["lifecycle"] not in ("GOVERNED", "CANARY"):
        raise ValueError(f"不可 Promotion: {cand['lifecycle']} (须 GOVERNED/CANARY)")
    if cand["lifecycle"] == "CANARY":
        # Canary PASS 必需
        can = _find(root, "canaries", "canary_id", canary_id)
        cmp = canary_compare(root, canary_id)
        if cmp["status"] != "PASS":
            raise ValueError(f"Canary 未 PASS: {cmp['status']}")
    _transition(root, candidate_id, target="PROMOTED", actor=actor)
    # PromotionSnapshot (immutable)
    snap = {"snapshot_id": f"psnap-{uuid.uuid4().hex[:10]}",
            "candidate_id": candidate_id, "learning_candidate_id": cand["learning_candidate_id"],
            "target": cand["target"], "baseline_ref": cand["baseline_ref"],
            "candidate_ref": cand["candidate_ref"], "scope": cand["scope"],
            "risk": cand["risk"], "canary_id": canary_id,
            "actor": actor, "timestamp": _now_iso(),
            "lifecycle_history": cand["lifecycle_history"],
            "note": f"Promoted by {actor} via S38 Governed Promotion"}
    _save(root, "snapshots", _load(root, "snapshots") + [snap])
    _audit(root, "PROMOTION_PROMOTED", {"candidate_id": candidate_id,
                                        "snapshot_id": snap["snapshot_id"],
                                        "actor": actor})
    return snap


def promotion_snapshots(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "snapshots")


def promotion_history(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "candidates")
