"""factory-console/learning_engine_v2.py — S37 Evidence-driven Workforce Learning.

Production Evidence → LearningObservation → LearningHypothesis → LearningCandidate
→ Evidence Evaluation → VALIDATED/REJECTED/CONFLICT → [STOP]

- Observation 来源必须是 Production Evidence (禁 Conversation/LLM imagination)
- LearningLifecycle: OBSERVED→HYPOTHESIS→CANDIDATE→EVALUATING→VALIDATED/REJECTED/SUPERSEDED
- Confidence: observed/inferred/validated (小样本自然降权)
- Negative Learning: what fails / why / under which scope
- Learning Conflict: evidence/scope/freshness/confidence (非 last-write-wins)
- Learning Plugin (type=learning): discovery plugin 化, Core 零修改替换
- Learning Cost: estimated (不伪装 billing)
- 绝不自动修改 Production (Promotion = S38)

复用: S14/S15 Experience + S36 ContextFeedback + S33 Performance + S31 Plugin Kernel
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

#: Lifecycle
LEARN_STATES = ("OBSERVED", "HYPOTHESIS", "CANDIDATE", "EVALUATING",
                "VALIDATED", "REJECTED", "SUPERSEDED")
LEARN_TRANSITIONS = {
    "OBSERVED": ("HYPOTHESIS", "REJECTED"),
    "HYPOTHESIS": ("CANDIDATE", "REJECTED"),
    "CANDIDATE": ("EVALUATING", "REJECTED", "SUPERSEDED"),
    "EVALUATING": ("VALIDATED", "REJECTED", "SUPERSEDED"),
    "VALIDATED": ("SUPERSEDED",),
    "REJECTED": (),
    "SUPERSEDED": (),
}

#: Candidate 类型
CANDIDATE_TYPES = ("STRATEGY", "PATTERN", "LESSON", "PROCEDURE",
                   "CONSTRAINT", "SUCCESS_PATTERN", "FAILURE_PATTERN")

#: Confidence 类型
CONFIDENCE_TYPES = ("observed", "inferred", "validated", "unknown")

#: Learning Plugins (discovery, Core 不 import 具体实现)
LEARNING_PLUGINS: dict[str, Callable[[list[dict[str, Any]]], list[dict[str, Any]]]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "learning" / f"{name}.json"


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
            trace_id=payload.get("candidate_id") or payload.get("observation_id") or "",
            actor_type="system", actor_id="learning",
            action=f"learning.{event_type.lower()}",
            source="learning_engine_v2", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"learning": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ LearningObservation

def create_observation(root: Path | str, *, source_type: str, source_id: str,
                       pattern_key: str, outcome: str = "UNKNOWN",
                       scope: str = "node", detail: str = "") -> dict[str, Any]:
    """Observation 来源必须是 Production Evidence (source_type 白名单)。"""
    if source_type not in ("production_run", "node_run", "verification", "recovery",
                           "evaluation", "context_feedback", "experience", "performance"):
        raise ValueError(f"非法 observation 来源: {source_type} (禁 Conversation/LLM imagination)")
    if outcome not in ("SUCCESS", "FAILURE", "UNKNOWN"):
        raise ValueError(f"非法 outcome: {outcome}")
    obs = {"observation_id": f"obs-{uuid.uuid4().hex[:10]}",
           "source_type": source_type, "source_id": source_id,
           "pattern_key": pattern_key, "outcome": outcome,
           "scope": scope, "detail": detail, "created_at": _now_iso(),
           "evidence_refs": [f"{source_type}:{source_id}"]}
    _save(root, "observations", _load(root, "observations") + [obs])
    _audit(root, "LEARNING_OBSERVED", {"observation_id": obs["observation_id"],
                                       "pattern_key": pattern_key, "outcome": outcome})
    return obs


def observations(root: Path | str, *, pattern_key: str = "") -> list[dict[str, Any]]:
    data = _load(root, "observations")
    if pattern_key:
        data = [o for o in data if o["pattern_key"] == pattern_key]
    return data


# ------------------------------------------------------------------ LearningHypothesis

def create_hypothesis(root: Path | str, *, statement: str, observation_ids: list[str],
                      scope: str = "node") -> dict[str, Any]:
    hyp = {"hypothesis_id": f"hyp-{uuid.uuid4().hex[:10]}",
           "statement": statement, "observation_ids": observation_ids,
           "status": "HYPOTHESIS", "scope": scope, "created_at": _now_iso()}
    _save(root, "hypotheses", _load(root, "hypotheses") + [hyp])
    return hyp


def hypotheses(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "hypotheses")


# ------------------------------------------------------------------ LearningCandidate

def create_candidate(root: Path | str, *, hypothesis_id: str, candidate_type: str,
                     content: str, scope: str = "node") -> dict[str, Any]:
    if candidate_type not in CANDIDATE_TYPES:
        raise ValueError(f"非法 candidate 类型: {candidate_type}")
    cand = {"candidate_id": f"lrn-{uuid.uuid4().hex[:10]}",
            "hypothesis_id": hypothesis_id, "type": candidate_type,
            "content": content, "scope": scope, "lifecycle": "CANDIDATE",
            "created_at": _now_iso(), "lifecycle_history": [
                {"from": "OBSERVED", "to": "CANDIDATE", "at": _now_iso(), "actor": "learning"}],
            "aggregate": {"sample_count": 0, "success_count": 0, "failure_count": 0,
                          "verification_count": 0, "recovery_count": 0, "confidence": "unknown"},
            "evidence_refs": []}
    _save(root, "candidates", _load(root, "candidates") + [cand])
    return cand


def _candidate(root: Path | str, candidate_id: str) -> dict[str, Any]:
    for c in _load(root, "candidates"):
        if c["candidate_id"] == candidate_id:
            return c
    raise ValueError(f"Candidate 不存在: {candidate_id}")


def transition(root: Path | str, candidate_id: str, *, target: str,
               actor: str = "learning") -> dict[str, Any]:
    """Lifecycle 迁移 (非法拒绝; history append-only)。"""
    data = _load(root, "candidates")
    for c in data:
        if c["candidate_id"] == candidate_id:
            current = c["lifecycle"]
            if target not in LEARN_TRANSITIONS.get(current, ()) and target != current:
                raise ValueError(f"非法状态迁移: {current} → {target}")
            c["lifecycle"] = target
            c["lifecycle_history"] = c.get("lifecycle_history", []) + [
                {"from": current, "to": target, "at": _now_iso(), "actor": actor}]
            _save(root, "candidates", data)
            _audit(root, "LEARNING_TRANSITION", {"candidate_id": candidate_id,
                                                 "from": current, "to": target})
            return c
    raise ValueError(f"Candidate 不存在: {candidate_id}")


# ------------------------------------------------------------------ Evidence Evaluation

def evaluate_candidate(root: Path | str, candidate_id: str, *, evidence_count: int = 0,
                       success_count: int = 0, failure_count: int = 0,
                       min_samples: int = 3) -> dict[str, Any]:
    """Evidence Evaluation: 聚合 + 置信度 (小样本自然降权) → VALIDATED/REJECTED。

    - evidence_count < min_samples → EVALUATING (数据不足, 不伪装)
    - failure_count > success_count → REJECTED (Negative Learning)
    - 否则 → VALIDATED
    """
    cand = _candidate(root, candidate_id)
    # 幂等: 已 EVALUATING 不重复迁移; VALIDATED/REJECTED/SUPERSEDED 拒绝重评
    if cand["lifecycle"] in ("VALIDATED", "REJECTED", "SUPERSEDED"):
        raise ValueError(f"Candidate 已终态: {cand['lifecycle']} (禁止重评)")
    if cand["lifecycle"] != "EVALUATING":
        transition(root, candidate_id, target="EVALUATING")
    agg = cand.get("aggregate", {})
    agg["sample_count"] = evidence_count
    agg["success_count"] = success_count
    agg["failure_count"] = failure_count
    agg["verification_count"] = success_count + failure_count
    if evidence_count < min_samples:
        agg["confidence"] = "unknown"
        transition(root, candidate_id, target="EVALUATING")
        result = "EVALUATING"
    else:
        # 小样本降权: confidence = validated 仅当 success 占优
        success_rate = success_count / evidence_count
        if failure_count > success_count or success_rate < 0.5:
            agg["confidence"] = "observed" if evidence_count < 10 else "inferred"
            transition(root, candidate_id, target="REJECTED")
            result = "REJECTED"
        else:
            agg["confidence"] = "validated"
            transition(root, candidate_id, target="VALIDATED")
            result = "VALIDATED"
    _save_candidate_agg(root, candidate_id, agg)
    _audit(root, "LEARNING_EVALUATED", {"candidate_id": candidate_id, "result": result,
                                        "sample_count": evidence_count,
                                        "success": success_count, "failure": failure_count})
    return {"candidate_id": candidate_id, "result": result,
            "aggregate": agg, "explain": f"{evidence_count} 样本, {success_count} 成功/{failure_count} 失败 → {result}"}


def _save_candidate_agg(root: Path | str, candidate_id: str, agg: dict[str, Any]) -> None:
    data = _load(root, "candidates")
    for c in data:
        if c["candidate_id"] == candidate_id:
            c["aggregate"] = agg
            c["evidence_refs"] = [f"eval:{candidate_id}"]
            _save(root, "candidates", data)
            return


# ------------------------------------------------------------------ Conflict

def detect_conflicts(root: Path | str) -> list[dict[str, Any]]:
    """同 scope + 同 pattern_key 的 VALIDATED vs REJECTED/矛盾 → CONFLICT。"""
    cands = _load(root, "candidates")
    by_pattern: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for c in cands:
        key = (c.get("scope", ""), c.get("pattern_key", c["content"][:20]))
        by_pattern.setdefault(key, []).append(c)
    conflicts = []
    for (scope, pattern), members in by_pattern.items():
        if len(members) < 2:
            continue
        outcomes = {m["lifecycle"] for m in members}
        if "VALIDATED" in outcomes and "REJECTED" in outcomes:
            conflicts.append({"conflict_id": f"lc-{uuid.uuid4().hex[:8]}",
                              "pattern_key": pattern, "scope": scope,
                              "candidate_ids": [m["candidate_id"] for m in members],
                              "status": "CONFLICT",
                              "explain": f"同 pattern {pattern} 出现 VALIDATED 与 REJECTED 矛盾",
                              "created_at": _now_iso()})
    _save(root, "conflicts", conflicts)
    return conflicts


def learning_conflicts(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "conflicts")


# ------------------------------------------------------------------ Learning Plugin

def register_learning_plugin(plugin_id: str,
                             fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]) -> None:
    LEARNING_PLUGINS[plugin_id] = fn


def _get_learning_plugin(root: Path | str):
    from .plugin_kernel import get_plugin
    for pid in LEARNING_PLUGINS:
        p = get_plugin(root, pid)
        if p is not None and p["status"] == "ENABLED":
            return LEARNING_PLUGINS[pid]
    return None


# ------------------------------------------------------------------ 默认 discovery (deterministic)

def default_discovery(root: Path | str) -> list[dict[str, Any]]:
    """从 Observations 聚合 → 自动生成 Candidates (deterministic, 非 LLM)。"""
    obs = _load(root, "observations")
    by_pattern: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for o in obs:
        key = (o["scope"], o["pattern_key"])
        by_pattern.setdefault(key, []).append(o)
    created = []
    for (scope, pattern), members in by_pattern.items():
        if len(members) < 2:
            continue
        success = sum(1 for o in members if o["outcome"] == "SUCCESS")
        failure = sum(1 for o in members if o["outcome"] == "FAILURE")
        cand_type = "SUCCESS_PATTERN" if success > failure else "FAILURE_PATTERN"
        content = (f"pattern={pattern}: {success} 成功 / {failure} 失败 (scope={scope})"
                   if failure else f"pattern={pattern}: {success} 成功 (scope={scope})")
        cand = create_candidate(root, hypothesis_id="auto", candidate_type=cand_type,
                                content=content, scope=scope)
        cand["pattern_key"] = pattern
        cand["aggregate"] = {"sample_count": len(members), "success_count": success,
                             "failure_count": failure, "verification_count": len(members),
                             "recovery_count": 0,
                             "confidence": "inferred" if len(members) >= 3 else "observed"}
        _save(root, "candidates",
              [c if c["candidate_id"] != cand["candidate_id"] else cand
               for c in _load(root, "candidates")])
        created.append(cand)
    return created


# ------------------------------------------------------------------ CLI 辅助

def run_learning(root: Path | str, *, min_samples: int = 3,
                 plugin_id: str = "") -> dict[str, Any]:
    """运行 Learning: discovery (Plugin 可替换) → evaluate → conflicts。"""
    started = time.time()
    plugin = _get_learning_plugin(root)
    if plugin is not None:
        created = plugin(_load(root, "observations"))
    else:
        created = default_discovery(root)
    results = []
    for c in created:
        agg = c.get("aggregate", {})
        r = evaluate_candidate(root, c["candidate_id"],
                               evidence_count=agg.get("sample_count", 0),
                               success_count=agg.get("success_count", 0),
                               failure_count=agg.get("failure_count", 0),
                               min_samples=min_samples)
        results.append(r)
    conflicts = detect_conflicts(root)
    return {"created": [c["candidate_id"] for c in created],
            "results": results, "conflicts": [c["conflict_id"] for c in conflicts],
            "input_tokens": 0, "output_tokens": 0,
            "estimated_cost": 0.0, "cost_type": "estimated",
            "evidence_count": len(_load(root, "observations")),
            "processing_time": round(time.time() - started, 3)}


# ------------------------------------------------------------------ Quality

def learning_quality(root: Path | str) -> dict[str, Any]:
    cands = _load(root, "candidates")
    if not cands:
        return {"learning_candidates": 0, "validated_candidates": 0,
                "rejected_candidates": 0, "conflicted_candidates": 0,
                "unknown_candidates": 0, "evidence_per_candidate": 0}
    return {
        "learning_candidates": len(cands),
        "validated_candidates": sum(1 for c in cands if c["lifecycle"] == "VALIDATED"),
        "rejected_candidates": sum(1 for c in cands if c["lifecycle"] == "REJECTED"),
        "conflicted_candidates": len(learning_conflicts(root)),
        "unknown_candidates": sum(1 for c in cands if c.get("aggregate", {}).get("confidence") == "unknown"),
        "evidence_per_candidate": round(
            sum(c.get("aggregate", {}).get("sample_count", 0) for c in cands) / len(cands), 2),
    }


def candidates(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "candidates")
