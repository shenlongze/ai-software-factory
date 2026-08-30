"""factory-console/production_intelligence.py — S23 Production Intelligence & RCA.

从真实 Production Facts (Incident/HealthCheck/Release/Verification/Experience) 提取 Signals、
时间相关性、Root Cause Candidates (deterministic evidence weighting + 反证)、
Recommendations (经 Governance 决策 → 现有 Production Core)。

原则:
- Intelligence 只 READ/ANALYZE/RECOMMEND, 不 MUTATE (不直接 rollback/修改 artifact)
- Correlation ≠ Causation (只报告 temporal correlation)
- Evidence-first: 任何 claim 必须 evidence_refs 可追溯
- Hallucination Protection: 不存在的 evidence_ref → reject
- Re-analysis → 新 analysis_id (不覆盖旧)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .health_service import list_incidents, list_health_checks, get_incident
from .release_service import list_releases, get_release
from .ops_projection import release_health_history

#: Analysis 状态
ST_REQUESTED = "REQUESTED"
ST_COLLECTING = "COLLECTING"
ST_ANALYZING = "ANALYZING"
ST_COMPLETED = "COMPLETED"
ST_FAILED = "FAILED"

#: Analysis 类型
AN_INCIDENT = "INCIDENT_ANALYSIS"
AN_RELEASE = "RELEASE_HEALTH_ANALYSIS"
AN_RUN = "PRODUCTION_RUN_ANALYSIS"
AN_RCA = "ROOT_CAUSE_ANALYSIS"

#: RootCauseCandidate 状态
RC_SUPPORTED = "SUPPORTED"
RC_POSSIBLE = "POSSIBLE"
RC_WEAK = "WEAK"
RC_REJECTED = "REJECTED"
RC_INCONCLUSIVE = "INCONCLUSIVE"

#: 确定性 evidence weighting (verification > health > correlation > pattern > experience)
WEIGHTS = {
    "verification": 1.0,
    "health": 0.8,
    "correlation": 0.6,
    "historical_pattern": 0.4,
    "experience": 0.3,
}
CONTRADICTION_PENALTY = 0.5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _analyses_file(root: Path | str) -> Path:
    return Path(root) / "ops" / "intelligence" / "analyses.json"


def _recommendations_file(root: Path | str) -> Path:
    return Path(root) / "ops" / "intelligence" / "recommendations.json"


def _load(root: Path | str, p: Path) -> list[dict[str, Any]]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(root: Path | str, p: Path, data: list[dict[str, Any]]) -> None:
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
            trace_id=payload.get("analysis_id") or payload.get("incident_id") or "",
            actor_type="system", actor_id="intelligence",
            action=f"intelligence.{event_type.lower()}",
            source="production_intelligence", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"intelligence": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ Evidence 校验

def _resolve_evidence(root: Path | str, ref: str) -> dict[str, Any] | None:
    """校验 evidence_ref 是否存在 (Hallucination Protection)。"""
    if ref.startswith("inc-"):
        return get_incident(root, ref)
    if ref.startswith("hchk-"):
        for c in list_health_checks(root):
            if c["health_check_id"] == ref:
                return c
        return None
    if ref.startswith("rel-"):
        return get_release(root, ref)
    return None


def _validate_evidence_refs(root: Path | str, refs: list[str]) -> tuple[list[str], list[str]]:
    """返回 (valid_refs, invalid_refs)。不存在的 ref → invalid (hallucination)。"""
    valid, invalid = [], []
    for ref in refs:
        if _resolve_evidence(root, ref) is not None:
            valid.append(ref)
        else:
            invalid.append(ref)
    return valid, invalid


# ------------------------------------------------------------------ Signal Extraction

def _extract_signals(root: Path | str, incident: dict[str, Any],
                     checks: list[dict[str, Any]], releases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从真实 facts 提取 signals (带 source_ref)。"""
    signals: list[dict[str, Any]] = []
    for c in checks:
        if c.get("release_id") == incident.get("release_id"):
            failed = [x["check_type"] for x in c.get("checks", []) if x["status"] == "FAILED"]
            signals.append({"signal_id": f"sig-{uuid.uuid4().hex[:8]}",
                            "signal_type": "health_check_failed",
                            "source_ref": c["health_check_id"],
                            "timestamp": c.get("completed_at", ""),
                            "value": c.get("result", ""), "detail": failed})
    for rel in releases:
        if rel["release_id"] == incident.get("release_id"):
            signals.append({"signal_id": f"sig-{uuid.uuid4().hex[:8]}",
                            "signal_type": "release_state",
                            "source_ref": rel["release_id"],
                            "timestamp": rel.get("created_at", ""),
                            "value": rel.get("state", "")})
    # incident 自身
    signals.append({"signal_id": f"sig-{uuid.uuid4().hex[:8]}",
                    "signal_type": "incident_created",
                    "source_ref": incident["incident_id"],
                    "timestamp": incident.get("created_at", ""),
                    "value": incident.get("health_result", ""),
                    "detail": incident.get("failed_checks", [])})
    return signals


# ------------------------------------------------------------------ Temporal Correlation

def _temporal_correlation(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """事件时间序 → correlation evidence (观察, 非因果)。

    排序: 先时间, 同秒按事件语义 (release → health → incident)。
    """
    order = {"release_state": 0, "health_check_failed": 1, "health_check_passed": 1,
             "incident_created": 2, "verification_failed": 1}
    ts = [(s.get("timestamp", ""), order.get(s["signal_type"], 9), s["signal_type"], s["source_ref"])
          for s in signals]
    ts.sort(key=lambda x: (x[0], x[1]))
    correlations = []
    for i in range(len(ts) - 1):
        correlations.append({"from": ts[i][2], "from_ref": ts[i][3],
                             "to": ts[i + 1][2], "to_ref": ts[i + 1][3],
                             "relation": "temporal_order",
                             "note": "observed temporal order (correlation ≠ causation)"})
    return correlations


# ------------------------------------------------------------------ Root Cause Candidates

def _build_candidates(root: Path | str, incident: dict[str, Any], signals: list[dict[str, Any]],
                      correlations: list[dict[str, Any]], releases: list[dict[str, Any]],
                      checks: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """确定性 Root Cause Candidates (evidence weighting + 反证)。"""
    rel_id = incident.get("release_id", "")
    rel = get_release(root, rel_id)
    candidates: list[dict[str, Any]] = []
    # Candidate 1: Release regression
    supporting = []
    refs = []
    for corr in correlations:
        if corr["from"] == "release_state" and corr["to"] == "health_check_failed":
            supporting.append({"signal": "release_preceded_failure",
                               "evidence_type": "correlation", "weight": WEIGHTS["correlation"],
                               "ref": corr["from_ref"]})
            refs.append(corr["from_ref"])
    for s in signals:
        if s["signal_type"] == "health_check_failed":
            supporting.append({"signal": "health_check_failed",
                               "evidence_type": "health", "weight": WEIGHTS["health"],
                               "ref": s["source_ref"]})
            refs.append(s["source_ref"])
    if rel is not None:
        attempts = rel.get("verification_attempts", [])
        if any(a.get("result") == "FAIL" for a in attempts):
            supporting.append({"signal": "verification_failed",
                               "evidence_type": "verification", "weight": WEIGHTS["verification"],
                               "ref": rel["release_id"]})
    # 反证: 后续健康恢复 (真实反证信号) 而非状态字段
    contradicting = []
    later_checks = [c for c in (checks or []) if c.get("release_id") == rel_id
                    and c.get("completed_at", "") > incident.get("created_at", "")
                    and c.get("result") in ("HEALTHY",)]
    if later_checks:
        contradicting.append({"signal": "health_recovered_after_incident",
                              "note": "incident 后健康恢复 (弱反证)"})
    score = _confidence(supporting, contradicting)
    candidates.append({"candidate_id": f"rc-{uuid.uuid4().hex[:8]}", "category": "release_regression",
                       "description": "Release 后出现健康退化",
                       "confidence": score, "evidence_refs": _dedup(refs),
                       "supporting_signals": supporting, "contradicting_signals": contradicting,
                       "status": _status(score),
                       "explain": _explain_candidate("release_regression", score, supporting, contradicting)})
    # Candidate 2: Configuration mismatch (incident 有配置类 signal)
    cfg_signals = [s for s in signals if "config" in str(s.get("detail", "")).lower()]
    refs2 = [s["source_ref"] for s in cfg_signals]
    supporting2 = [{"signal": "config_signal", "evidence_type": "correlation",
                    "weight": WEIGHTS["correlation"], "ref": s["source_ref"]} for s in cfg_signals]
    score2 = _confidence(supporting2, [])
    candidates.append({"candidate_id": f"rc-{uuid.uuid4().hex[:8]}", "category": "configuration_mismatch",
                       "description": "配置不匹配 (证据不足时低置信度)",
                       "confidence": score2, "evidence_refs": refs2,
                       "supporting_signals": supporting2, "contradicting_signals": [],
                       "status": _status(score2),
                       "explain": _explain_candidate("configuration_mismatch", score2, supporting2, [])})
    # 证据不足 → INCONCLUSIVE
    if not candidates or all(c["status"] == RC_WEAK for c in candidates):
        candidates.append({"candidate_id": f"rc-{uuid.uuid4().hex[:8]}", "category": "inconclusive",
                           "description": "证据不足, 无法确定根因", "confidence": 0.0,
                           "evidence_refs": [], "supporting_signals": [],
                           "contradicting_signals": [], "status": RC_INCONCLUSIVE,
                           "explain": "[inconclusive] 支持证据: 无; 证据不足, 无法确定根因 (正式结论)"})
    return candidates


def _dedup(items: list[str]) -> list[str]:
    seen = set()
    return [x for x in items if not (x in seen or seen.add(x))]


def _explain_candidate(category: str, score: float, supporting: list[dict[str, Any]],
                       contradicting: list[dict[str, Any]]) -> str:
    """确定性解释: 基于真实 supporting/contradicting signals + 权重 (非 LLM)。"""
    parts = []
    if supporting:
        sig_desc = ", ".join(f"{s.get('signal', s.get('evidence_type', ''))}({s.get('evidence_type', '')}×{s.get('weight', 0)})"
                             for s in supporting)
        parts.append(f"支持证据: {sig_desc}")
    else:
        parts.append("支持证据: 无")
    if contradicting:
        parts.append(f"反证: {', '.join(s.get('signal', '') for s in contradicting)}")
    parts.append(f"置信度 {score} = 加权支持/2 - 反证惩罚(0.5×{len(contradicting)})")
    return f"[{category}] " + "; ".join(parts)


def _confidence(supporting: list[dict[str, Any]], contradicting: list[dict[str, Any]]) -> float:
    """确定性 confidence: 加权支持 - 反证惩罚 (可解释)。"""
    if not supporting:
        return 0.0
    support = sum(s.get("weight", WEIGHTS["correlation"]) for s in supporting)
    penalty = CONTRADICTION_PENALTY * len(contradicting)
    return round(max(0.0, min(1.0, support / 2.0 - penalty)), 2)


def _status(score: float) -> str:
    if score >= 0.7:
        return RC_SUPPORTED
    if score >= 0.4:
        return RC_POSSIBLE
    if score >= 0.1:
        return RC_WEAK
    return RC_REJECTED


# ------------------------------------------------------------------ Historical Pattern

def _historical_patterns(root: Path | str, incident: dict[str, Any]) -> list[dict[str, Any]]:
    """历史相似 incidents (同 failed_checks 或同 release)。"""
    all_inc = list_incidents(root)
    patterns = []
    for other in all_inc:
        if other["incident_id"] == incident["incident_id"]:
            continue
        overlap = set(other.get("failed_checks", [])) & set(incident.get("failed_checks", []))
        if overlap:
            patterns.append({"pattern_id": f"pat-{uuid.uuid4().hex[:8]}",
                             "incident_id": other["incident_id"],
                             "overlap_checks": sorted(overlap),
                             "similarity": round(len(overlap) / max(1, len(set(other.get("failed_checks", [])) | set(incident.get("failed_checks", [])))), 2),
                             "evidence_type": "historical_pattern", "weight": WEIGHTS["historical_pattern"]})
    return patterns


# ------------------------------------------------------------------ Recommendations

def _build_recommendations(root: Path | str, analysis_id: str, candidates: list[dict[str, Any]],
                           incident: dict[str, Any]) -> list[dict[str, Any]]:
    """从 Root Cause Candidates 生成 Recommendations (不直接执行)。"""
    recs = []
    top = max(candidates, key=lambda c: c["confidence"]) if candidates else None
    if top is None or top["status"] == RC_INCONCLUSIVE:
        return []
    if top["category"] == "release_regression" and top["confidence"] >= 0.5:
        recs.append({"recommendation_id": f"rec-{uuid.uuid4().hex[:10]}",
                     "analysis_id": analysis_id, "type": "ROLLBACK_RELEASE",
                     "description": f"回滚 Release {incident.get('release_id')} (高置信度 release regression)",
                     "reason": f"基于 {top['status']} 候选: {top.get('explain', '')}",
                     "priority": "high", "confidence": top["confidence"],
                     "risk": "HIGH", "requires_approval": True,
                     "evidence_refs": top["evidence_refs"],
                     "status": "PENDING", "decision": "", "outcome": ""})
    recs.append({"recommendation_id": f"rec-{uuid.uuid4().hex[:10]}",
                 "analysis_id": analysis_id, "type": "INVESTIGATE_CONFIGURATION",
                 "description": "调查配置状态 (低置信度候选)", "priority": "low",
                 "reason": "配置类信号证据不足, 仅建议调查 (风险 LOW)",
                 "confidence": next((c["confidence"] for c in candidates if c["category"] == "configuration_mismatch"), 0.1),
                 "risk": "LOW", "requires_approval": False,
                 "evidence_refs": [], "status": "PENDING", "decision": "", "outcome": ""})
    return recs


# ------------------------------------------------------------------ 主分析入口

def analyze_incident(root: Path | str, incident_id: str, *, analyzer: str = "intelligence") -> dict[str, Any]:
    """对 Incident 执行 RCA (确定性 baseline, 无 LLM 依赖)。"""
    incident = get_incident(root, incident_id)
    if incident is None:
        raise ValueError(f"Incident 不存在: {incident_id}")
    analysis = {
        "analysis_id": f"an-{uuid.uuid4().hex[:10]}",
        "incident_id": incident_id,
        "release_id": incident.get("release_id", ""),
        "project_id": incident.get("run_id", ""),
        "analysis_type": AN_INCIDENT,
        "status": ST_ANALYZING,
        "created_at": _now_iso(),
        "completed_at": "",
        "signals": [], "correlations": [], "root_cause_candidates": [],
        "recommendations": [], "evidence_refs": [], "failure_reason": "",
        "patterns": [],
    }
    _audit(root, "INTELLIGENCE_ANALYSIS_STARTED", {"analysis_id": analysis["analysis_id"],
                                                  "incident_id": incident_id})
    try:
        checks = list_health_checks(root, release_id=incident.get("release_id", ""))
        releases = list_releases(root)
        analysis["signals"] = _extract_signals(root, incident, checks, releases)
        analysis["correlations"] = _temporal_correlation(analysis["signals"])
        analysis["patterns"] = _historical_patterns(root, incident)
        analysis["root_cause_candidates"] = _build_candidates(
            root, incident, analysis["signals"], analysis["correlations"], releases, checks)
        analysis["recommendations"] = _build_recommendations(
            root, analysis["analysis_id"], analysis["root_cause_candidates"], incident)
        # evidence_refs 汇总 + 校验 (hallucination protection)
        all_refs = [r for c in analysis["root_cause_candidates"] for r in c["evidence_refs"]]
        valid, invalid = _validate_evidence_refs(root, all_refs)
        analysis["evidence_refs"] = valid
        if invalid:
            analysis["note"] = f"rejected invalid evidence_refs: {invalid}"
        analysis["status"] = ST_COMPLETED
        analysis["completed_at"] = _now_iso()
        # 持久化 (append-only; re-analysis 新 id)
        data = _load(root, _analyses_file(root))
        data.append(analysis)
        _save(root, _analyses_file(root), data)
        # recommendations 独立持久化
        rec_data = _load(root, _recommendations_file(root))
        rec_data.extend(analysis["recommendations"])
        _save(root, _recommendations_file(root), rec_data)
        _audit(root, "INTELLIGENCE_ANALYSIS_COMPLETED",
               {"analysis_id": analysis["analysis_id"], "incident_id": incident_id,
                "candidates": len(analysis["root_cause_candidates"]),
                "recommendations": len(analysis["recommendations"])})
        return analysis
    except Exception as exc:  # noqa: BLE001
        analysis["status"] = ST_FAILED
        analysis["failure_reason"] = str(exc)
        data = _load(root, _analyses_file(root))
        data.append(analysis)
        _save(root, _analyses_file(root), data)
        _audit(root, "INTELLIGENCE_ANALYSIS_FAILED", {"analysis_id": analysis["analysis_id"],
                                                     "incident_id": incident_id, "error": str(exc)})
        return analysis


def get_analysis(root: Path | str, analysis_id: str) -> dict[str, Any] | None:
    for a in _load(root, _analyses_file(root)):
        if a["analysis_id"] == analysis_id:
            return a
    return None


def list_analyses(root: Path | str, *, incident_id: str | None = None) -> list[dict[str, Any]]:
    data = _load(root, _analyses_file(root))
    if incident_id:
        return [a for a in data if a.get("incident_id") == incident_id]
    return data


def analysis_evidence(root: Path | str, analysis_id: str) -> list[dict[str, Any]]:
    """返回 analysis 引用 evidence 的解析结果 (可追溯)。"""
    a = get_analysis(root, analysis_id)
    if a is None:
        raise ValueError(f"Analysis 不存在: {analysis_id}")
    out = []
    for ref in a.get("evidence_refs", []):
        resolved = _resolve_evidence(root, ref)
        if resolved is not None:
            out.append({"ref": ref, "resolved": True, "kind": ref.split("-")[0], "data": resolved})
        else:
            out.append({"ref": ref, "resolved": False, "kind": "missing"})
    return out


def list_recommendations(root: Path | str, *, analysis_id: str | None = None) -> list[dict[str, Any]]:
    data = _load(root, _recommendations_file(root))
    if analysis_id:
        return [r for r in data if r.get("analysis_id") == analysis_id]
    return data


def decide_recommendation(root: Path | str, recommendation_id: str, *,
                          decision: str, decided_by: str = "human") -> dict[str, Any]:
    """Recommendation 决策 (APPROVED/REJECTED) — 不直接执行 Action。

    APPROVED 后由 Governance → 现有 Production Core (rollback_service) 执行。
    """
    if decision not in ("APPROVED", "REJECTED"):
        raise ValueError(f"未知 decision: {decision}")
    data = _load(root, _recommendations_file(root))
    for r in data:
        if r["recommendation_id"] == recommendation_id:
            if r["status"] != "PENDING":
                raise ValueError(f"Recommendation 已决 (当前: {r['status']})")
            r["status"] = decision
            r["decision"] = decision
            r["decided_by"] = decided_by
            r["decided_at"] = _now_iso()
            _save(root, _recommendations_file(root), data)
            _audit(root, "INTELLIGENCE_RECOMMENDATION_DECIDED",
                   {"recommendation_id": recommendation_id, "decision": decision})
            return r
    raise ValueError(f"Recommendation 不存在: {recommendation_id}")


def record_outcome(root: Path | str, recommendation_id: str, *, outcome: str,
                   verification_result: str = "") -> dict[str, Any]:
    """回写 Recommendation Outcome (真实验证结果)。"""
    data = _load(root, _recommendations_file(root))
    for r in data:
        if r["recommendation_id"] == recommendation_id:
            r["outcome"] = outcome
            r["verification_result"] = verification_result
            _save(root, _recommendations_file(root), data)
            return r
    raise ValueError(f"Recommendation 不存在: {recommendation_id}")


def intelligence_metrics(root: Path | str) -> dict[str, Any]:
    """Intelligence 质量指标 (真实数据, 不伪造)。"""
    analyses = _load(root, _analyses_file(root))
    recs = _load(root, _recommendations_file(root))
    incs = list_incidents(root)
    completed = [a for a in analyses if a["status"] == ST_COMPLETED]
    inconclusive = sum(1 for a in completed
                       if any(c["status"] == RC_INCONCLUSIVE for c in a.get("root_cause_candidates", [])))
    return {
        "incident_count": len(incs),
        "analyzed_incident_count": len(completed),
        "root_cause_candidate_count": sum(len(a.get("root_cause_candidates", [])) for a in completed),
        "inconclusive_rate": round(inconclusive / max(1, len(completed)), 2),
        "recommendation_count": len(recs),
        "recommendation_accept_rate": round(sum(1 for r in recs if r.get("decision") == "APPROVED") / max(1, len(recs)), 2),
        "recommendation_reject_rate": round(sum(1 for r in recs if r.get("decision") == "REJECTED") / max(1, len(recs)), 2),
    }
