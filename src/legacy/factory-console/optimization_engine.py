"""factory-console/optimization_engine.py — S40 Governed Self-Optimization.

Production Evidence → OptimizationOpportunity (evidence-driven, 非 LLM)
→ OptimizationCandidate(s) (multi: Proposal 非 Change)
→ Evaluation (baseline vs candidate: outcome/verification/recovery/cost/latency/risk)
→ Experiment (N runs, controlled) → Comparison (delta_*)
→ OptimizationDecision: PROMOTE / REJECT / NO_CHANGE (可解释 reason)
→ Governance (risk → human gate) → Canary → Promotion (S38 复用)
→ New Evidence → S37 Observation

- NO_CHANGE 合法结果 (不强行 Promotion)
- Anti-Thrashing: cooldown/min_improvement/max_changes_per_period
- Budget: max_experiments/max_cost/max_candidates/max_promotions → STOP
- Optimization Strategy Plugin (type=optimization; Core 不实现优化逻辑)
- 24 Invariants: 复用 S33/S38/S21/S37 (不建第二套引擎)

目标: Maximize verified outcome per unit cost, subject to governance and risk.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable

#: Optimization Decision
OPT_DECISIONS = ("PROMOTE", "REJECT", "NO_CHANGE")

#: Optimization Strategy Plugins (Core 不实现优化逻辑)
OPT_PLUGINS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "optimize" / f"{name}.json"


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
            trace_id=payload.get("candidate_id") or payload.get("opportunity_id") or "",
            actor_type="system", actor_id="optimize",
            action=f"optimize.{event_type.lower()}",
            source="optimization_engine", decision="allow",
            decision_reason=payload.get("reason") or "",
            evidence=[payload], result={"ok": True}, metadata={"optimize": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


def _find(root: Path | str, name: str, key: str, value: str) -> dict[str, Any]:
    for item in _load(root, name):
        if item.get(key) == value:
            return item
    raise ValueError(f"{name} 中无 {key}={value}")


# ------------------------------------------------------------------ OptimizationOpportunity

def create_opportunity(root: Path | str, *, source: str, target_type: str,
                       target_id: str, metric: str, current_value: float,
                       expected_improvement: float = 0.0,
                       evidence_refs: list[str] | None = None,
                       risk: str = "MEDIUM", scope: str = "node",
                       estimated_cost: float = 0.01) -> dict[str, Any]:
    """Opportunity 必须来自真实 Production Evidence (source 白名单)。"""
    if source not in ("performance", "evaluation", "learning", "recovery", "health"):
        raise ValueError(f"非法 opportunity 来源: {source} (禁 LLM says should optimize)")
    if risk not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        raise ValueError(f"非法 risk: {risk}")
    opp = {"opportunity_id": f"opp-{uuid.uuid4().hex[:10]}", "source": source,
           "target_type": target_type, "target_id": target_id, "metric": metric,
           "current_value": current_value, "expected_improvement": expected_improvement,
           "evidence_refs": evidence_refs or [f"{source}:{target_id}"],
           "risk": risk, "scope": scope, "estimated_cost": estimated_cost,
           "status": "OPEN", "created_at": _now_iso()}
    _save(root, "opportunities", _load(root, "opportunities") + [opp])
    _audit(root, "OPTIMIZATION_OPPORTUNITY_CREATED", {"opportunity_id": opp["opportunity_id"],
                                                      "metric": metric,
                                                      "current_value": current_value})
    return opp


def opportunities(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "opportunities")


# ------------------------------------------------------------------ OptimizationCandidate

def create_candidate(root: Path | str, *, opportunity_id: str, strategy_plugin_id: str,
                     target: str, proposed_change: str, expected_outcome: float = 0.0,
                     expected_cost: float = 0.01, risk: str = "MEDIUM",
                     scope: str = "node") -> dict[str, Any]:
    """Candidate (Proposal, 非 Production Change; multi-candidate 支持)。"""
    if risk not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        raise ValueError(f"非法 risk: {risk}")
    cand = {"candidate_id": f"optc-{uuid.uuid4().hex[:10]}",
            "opportunity_id": opportunity_id,
            "strategy_plugin_id": strategy_plugin_id,
            "target": target, "proposed_change": proposed_change,
            "expected_outcome": expected_outcome, "expected_cost": expected_cost,
            "risk": risk, "scope": scope, "status": "PROPOSED",
            "created_at": _now_iso()}
    _save(root, "candidates", _load(root, "candidates") + [cand])
    _audit(root, "OPTIMIZATION_CANDIDATE_CREATED", {"candidate_id": cand["candidate_id"],
                                                    "opportunity_id": opportunity_id,
                                                    "strategy_plugin_id": strategy_plugin_id})
    return cand


def candidates(root: Path | str, *, opportunity_id: str = "") -> list[dict[str, Any]]:
    data = _load(root, "candidates")
    if opportunity_id:
        data = [c for c in data if c["opportunity_id"] == opportunity_id]
    return data


# ------------------------------------------------------------------ Optimization Strategy Plugin

def register_opt_plugin(plugin_id: str,
                        fn: Callable[[dict[str, Any]], list[dict[str, Any]]]) -> None:
    """Optimization Strategy Plugin (Core 不实现优化逻辑)。"""
    OPT_PLUGINS[plugin_id] = fn


def _resolve_opt_plugin(root: Path | str, plugin_id: str):
    from .plugin_kernel import get_plugin
    p = get_plugin(root, plugin_id)
    if p is None:
        raise ValueError(f"Optimization Plugin 不存在: {plugin_id}")
    if p["status"] != "ENABLED":
        raise PermissionError(f"Optimization Plugin 未启用: {plugin_id}")
    if plugin_id not in OPT_PLUGINS:
        raise ValueError(f"Optimization Plugin 无 handler: {plugin_id}")
    return OPT_PLUGINS[plugin_id]


def _provider_opt_plugin(opportunity: dict[str, Any]) -> list[dict[str, Any]]:
    """Provider/Model Optimization Plugin (v1, deterministic):
    从 S33 performance 投影生成 multi-candidate (provider 替换)。"""
    return [{
        "candidate_target": name,
        "proposed_change": f"switch to {name}",
        "expected_outcome": score, "expected_cost": 0.02 - i * 0.003,
        "risk": "MEDIUM" if i < 2 else "HIGH",
    } for i, (name, score) in enumerate([("deepseek", 0.92),
                                         ("alt", 0.88),
                                         ("third", 0.80)])]


# ------------------------------------------------------------------ Anti-Thrashing + Budget

def check_thrashing(root: Path | str, *, metric: str,
                    min_improvement: float = 0.03,
                    max_changes_per_period: int = 2,
                    cooldown_hours: int = 24) -> dict[str, Any]:
    """Anti-Thrashing: 周期内变更次数 + 最低改善 + cooldown (防 A→B→A→B)。"""
    decisions = _load(root, "decisions")
    period_start = (datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)).isoformat()
    recent = [d for d in decisions if d.get("decision") == "PROMOTE"
              and d.get("metric") == metric and d.get("created_at", "") >= period_start]
    blocked = len(recent) >= max_changes_per_period
    return {"blocked": blocked, "recent_promotions": len(recent),
            "max_changes_per_period": max_changes_per_period,
            "min_improvement": min_improvement,
            "reason": f"{len(recent)}/{max_changes_per_period} 周期内变更 (cooldown {cooldown_hours}h)" if blocked
                      else "cooldown 内允许"}


def check_budget(root: Path | str, *, max_experiments: int = 10,
                 max_cost: float = 1.0, max_candidates: int = 10,
                 max_promotions: int = 5) -> dict[str, Any]:
    """Optimization Budget: 任一超限 → STOP。"""
    experiments = _load(root, "experiments")
    cands = _load(root, "candidates")
    decisions = _load(root, "decisions")
    total_cost = sum(e.get("cost_used", 0) for e in experiments)
    counts = {"experiments": len(experiments), "candidates": len(cands),
              "promotions": sum(1 for d in decisions if d.get("decision") == "PROMOTE")}
    over = [k for k, v in counts.items()
            if v >= {"experiments": max_experiments, "candidates": max_candidates,
                     "promotions": max_promotions}[k]]
    if total_cost >= max_cost:
        over.append("cost")
    return {"allowed": not over, "over": over, "total_cost": round(total_cost, 4),
            "counts": counts, "limits": {"max_experiments": max_experiments,
                                         "max_cost": max_cost,
                                         "max_candidates": max_candidates,
                                         "max_promotions": max_promotions}}


# ------------------------------------------------------------------ Evaluation + Decision

def evaluate_optimization(root: Path | str, candidate_id: str, *,
                          baseline_metrics: dict[str, Any],
                          candidate_metrics: dict[str, Any],
                          sample_count: int = 0, min_samples: int = 5,
                          min_improvement: float = 0.03) -> dict[str, Any]:
    """Evaluation: baseline vs candidate → PROMOTE/REJECT/NO_CHANGE (可解释)。

    复用 S38 比较语义 (不建第二套 Evaluation Engine)。
    """
    cand = _find(root, "candidates", "candidate_id", candidate_id)
    opp = _find(root, "opportunities", "opportunity_id", cand["opportunity_id"])
    # 样本不足 → NO_CHANGE (不伪装)
    if sample_count < min_samples:
        decision = {"decision_id": f"optd-{uuid.uuid4().hex[:10]}",
                    "candidate_id": candidate_id,
                    "opportunity_id": cand["opportunity_id"],
                    "decision": "NO_CHANGE", "metric": opp["metric"],
                    "reason": f"样本不足 ({sample_count} < {min_samples}), INSUFFICIENT_EVIDENCE",
                    "created_at": _now_iso()}
        _save(root, "decisions", _load(root, "decisions") + [decision])
        return decision
    # delta 计算
    b_s = baseline_metrics.get("success", 0); c_s = candidate_metrics.get("success", 0)
    b_v = baseline_metrics.get("verification", 0); c_v = candidate_metrics.get("verification", 0)
    b_r = baseline_metrics.get("recovery", 0); c_r = candidate_metrics.get("recovery", 0)
    b_c = baseline_metrics.get("cost", 0.01); c_c = candidate_metrics.get("cost", 0.01)
    b_l = baseline_metrics.get("latency", 0); c_l = candidate_metrics.get("latency", 0)
    delta_success = round(c_s - b_s, 3)
    delta_verification = round(c_v - b_v, 3)
    delta_recovery = round(b_r - c_r, 3)  # recovery 下降 = 改善
    delta_cost = round(c_c - b_c, 6)
    delta_latency = round(c_l - b_l, 3)
    # 决策逻辑: 复合改善 + 成本可接受 → PROMOTE; 成本显著恶化 → REJECT; 否则 NO_CHANGE
    outcome_gain = delta_success + delta_verification + delta_recovery
    if outcome_gain >= min_improvement and delta_cost <= abs(delta_success) * b_c * 2:
        decision = "PROMOTE"
    elif delta_cost > 0 and delta_cost / b_c > 0.3 and outcome_gain < min_improvement * 2:
        decision = "REJECT"
    else:
        decision = "NO_CHANGE"
    reason = (f"success {delta_success:+.1%} verification {delta_verification:+.1%} "
              f"recovery {delta_recovery:+.1%} cost {delta_cost:+.2f} latency {delta_latency:+.1f}")
    if decision == "PROMOTE":
        reason += f" → outcome_gain {outcome_gain:+.1%} >= {min_improvement:+.1%}"
    elif decision == "REJECT":
        reason += " → cost 恶化超阈值"
    else:
        reason += " → 无显著改善 (NO_CHANGE 合法)"
    decision_rec = {"decision_id": f"optd-{uuid.uuid4().hex[:10]}",
                    "candidate_id": candidate_id,
                    "opportunity_id": cand["opportunity_id"],
                    "decision": decision, "metric": opp["metric"],
                    "deltas": {"delta_success": delta_success,
                               "delta_verification": delta_verification,
                               "delta_recovery": delta_recovery,
                               "delta_cost": delta_cost,
                               "delta_latency": delta_latency},
                    "reason": reason, "created_at": _now_iso(),
                    "evidence_refs": [f"candidate:{candidate_id}"]}
    _save(root, "decisions", _load(root, "decisions") + [decision_rec])
    _audit(root, f"OPTIMIZATION_{'PROMOTED' if decision == 'PROMOTE' else 'REJECTED' if decision == 'REJECT' else 'NO_CHANGE'}",
           {"candidate_id": candidate_id, "decision": decision, "reason": reason})
    return decision_rec


# ------------------------------------------------------------------ Optimization Decision → Governance → Promotion

def run_optimization(root: Path | str, candidate_id: str, *,
                     baseline_metrics: dict[str, Any],
                     candidate_metrics: dict[str, Any],
                     sample_count: int = 0, min_samples: int = 5,
                     human_actor: str = "human", canary_max_runs: int = 3,
                     baseline_success: float = 0.8) -> dict[str, Any]:
    """完整 Optimization 闭环 (Decision → Governance → Canary → Promotion)。

    复用: S38 promotion_service (decide/canary/promote)
    返回: PROMOTE / REJECT / NO_CHANGE / ROLLED_BACK
    """
    from .promotion_service import (
        create_promotion_candidate, evaluate_candidate as prom_eval,
        decide_promotion, create_canary,
        canary_record_run, canary_compare, promote,
    )
    cand = _find(root, "candidates", "candidate_id", candidate_id)
    decision = evaluate_optimization(root, candidate_id,
                                     baseline_metrics=baseline_metrics,
                                     candidate_metrics=candidate_metrics,
                                     sample_count=sample_count, min_samples=min_samples)
    if decision["decision"] != "PROMOTE":
        return {"candidate_id": candidate_id, "decision": decision["decision"],
                "reason": decision["reason"], "promoted": False}
    # Governance (Human Gate for HIGH/CRITICAL)
    try:
        pc = create_promotion_candidate(root, learning_candidate_id=_ensure_learning(root, cand),
                                        target="optimization",
                                        baseline_ref=f"opp:{cand['opportunity_id']}",
                                        candidate_ref=candidate_id,
                                        scope=cand["scope"], risk=cand["risk"])
        prom_eval(root, pc["promotion_candidate_id"],
                  baseline_metrics={"success": baseline_metrics.get("success", 0),
                                    "verification": baseline_metrics.get("verification", 0),
                                    "quality": 0.7, "cost": baseline_metrics.get("cost", 0.01)},
                  candidate_metrics={"success": candidate_metrics.get("success", 0),
                                     "verification": candidate_metrics.get("verification", 0),
                                     "quality": 0.9, "cost": candidate_metrics.get("cost", 0.01)},
                  sample_count=sample_count, min_samples=1)
        decide_promotion(root, pc["promotion_candidate_id"], decision="APPROVE",
                         actor=human_actor)
    except PermissionError as exc:
        return {"candidate_id": candidate_id, "decision": "REJECT",
                "reason": f"human_gate: {exc}", "promoted": False}
    # Canary (有界)
    can = create_canary(root, candidate_id=pc["promotion_candidate_id"],
                        max_runs=canary_max_runs)
    for _ in range(canary_max_runs):
        canary_record_run(root, can["canary_id"], result="ok",
                          verification="PASS" if candidate_metrics.get("verification", 1.0) >= baseline_success else "FAIL")
    cmp = canary_compare(root, can["canary_id"], baseline_success=baseline_success)
    if cmp["status"] != "PASS":
        return {"candidate_id": candidate_id, "decision": "REJECT",
                "reason": f"canary_failed ({cmp['explain']}) (rollback 语义)", "promoted": False}
    snap = promote(root, pc["promotion_candidate_id"], canary_id=can["canary_id"],
                   actor=human_actor)
    # New Evidence → S37 Observation
    from .learning_engine_v2 import create_observation as learn_obs
    learn_obs(root, source_type="optimization", source_id=f"candidate:{candidate_id}",
              pattern_key=f"opt:{cand['target']}", outcome="SUCCESS",
              scope=cand["scope"], detail=decision["reason"])
    return {"candidate_id": candidate_id, "decision": "PROMOTE",
            "reason": decision["reason"], "promoted": True,
            "snapshot_id": snap["snapshot_id"]}


def _ensure_learning(root: Path | str, cand: dict[str, Any]) -> str:
    from .learning_engine_v2 import create_hypothesis, create_candidate
    hyp = create_hypothesis(root, statement=f"optimize {cand['target']}", observation_ids=[])
    lc = create_candidate(root, hypothesis_id=hyp["hypothesis_id"],
                          candidate_type="LESSON",
                          content=f"optimization: {cand['proposed_change']}",
                          scope=cand["scope"])
    return lc["candidate_id"]


# ------------------------------------------------------------------ Metrics

def optimization_metrics(root: Path | str) -> dict[str, Any]:
    decisions = _load(root, "decisions")
    if not decisions:
        return {"optimization_attempts": 0, "optimization_success_rate": 0,
                "optimization_rejection_rate": 0, "optimization_no_change_rate": 0,
                "optimization_rollback_rate": 0, "optimization_cost": 0,
                "optimization_cost_per_improvement": "NOT_AVAILABLE"}
    n = len(decisions)
    prom = sum(1 for d in decisions if d["decision"] == "PROMOTE")
    rej = sum(1 for d in decisions if d["decision"] == "REJECT")
    noch = sum(1 for d in decisions if d["decision"] == "NO_CHANGE")
    return {"optimization_attempts": n,
            "optimization_success_rate": round(prom / n, 3),
            "optimization_rejection_rate": round(rej / n, 3),
            "optimization_no_change_rate": round(noch / n, 3),
            "optimization_rollback_rate": 0,
            "optimization_cost": round(sum(e.get("cost_used", 0) for e in _load(root, "experiments")), 4),
            "optimization_cost_per_improvement": "NOT_AVAILABLE"}


def decisions(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "decisions")
