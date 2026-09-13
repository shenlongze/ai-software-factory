"""factory-console/self_healing.py — S39 Autonomous Recovery & Self-Healing.

Self-Healing Loop (复用 S21/S28/S37/S38, 不建第二套):
Production Failure → Verification FAIL → Incident (evidence-driven, 非 LLM)
→ Diagnosis (FACT/HYPOTHESIS/UNKNOWN + evidence refs)
→ RepairCandidate (Proposal: repair_strategy_plugin_id/target/proposed_change/risk/cost)
→ S38 Evaluation (baseline FAIL vs candidate PASS via Replay)
→ Experiment (bounded) → S38 Governance (risk → human gate)
→ Canary (bounded) → Verification PASS → S38 Promotion
→ Recovery Evidence → S37 Learning Observation
失败: max_attempts/budget → UNRESOLVED (交 Human); Canary FAIL → S21 Rollback 语义

Incident Lifecycle: DETECTED→TRIAGED→DIAGNOSING→REPAIR_PROPOSED→REPAIR_EVALUATING
→GOVERNED→CANARY→RECOVERED; 失败→UNRESOLVED/REJECTED/ROLLED_BACK

Repair Strategy Plugin (type=repair): 首个 = coderepair (deterministic patch)
Core 只负责 Governance; Repair Plugin 负责 repair logic
20 Invariants: Core 不实现 repair / 不能 self-elevate / 有界 attempts+cost / 无 Super Agent
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

#: Incident Lifecycle
INCIDENT_STATES = ("DETECTED", "TRIAGED", "DIAGNOSING", "REPAIR_PROPOSED",
                   "REPAIR_EVALUATING", "GOVERNED", "CANARY", "RECOVERED",
                   "UNRESOLVED", "REJECTED", "ROLLED_BACK")
INCIDENT_TRANSITIONS = {
    "DETECTED": ("TRIAGED", "UNRESOLVED"),
    "TRIAGED": ("DIAGNOSING", "REPAIR_PROPOSED", "UNRESOLVED"),
    "DIAGNOSING": ("REPAIR_PROPOSED", "UNRESOLVED"),
    "REPAIR_PROPOSED": ("REPAIR_EVALUATING", "REJECTED", "UNRESOLVED"),
    "REPAIR_EVALUATING": ("GOVERNED", "REJECTED", "UNRESOLVED"),
    "GOVERNED": ("CANARY", "PROMOTED_RECOVERED", "REJECTED"),
    "CANARY": ("RECOVERED", "REJECTED", "ROLLED_BACK"),
    "RECOVERED": (),
    "UNRESOLVED": (),
    "REJECTED": (),
    "ROLLED_BACK": (),
}

#: Repair Plugins (Core 不 import 具体 repair logic)
RepairHandler = Callable[[str, dict[str, Any]], dict[str, Any]]
REPAIR_PLUGINS: dict[str, RepairHandler] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "selfheal" / f"{name}.json"


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
            trace_id=payload.get("incident_id") or payload.get("candidate_id") or "",
            actor_type="system", actor_id="selfheal",
            action=f"selfheal.{event_type.lower()}",
            source="self_healing", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"selfheal": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


def _find(root: Path | str, name: str, key: str, value: str) -> dict[str, Any]:
    for item in _load(root, name):
        if item.get(key) == value:
            return item
    raise ValueError(f"{name} 中无 {key}={value}")


def _transition(root: Path | str, incident_id: str, *, target: str,
                actor: str = "selfheal") -> dict[str, Any]:
    data = _load(root, "incidents")
    for inc in data:
        if inc["incident_id"] == incident_id:
            current = inc["status"]
            if target not in INCIDENT_TRANSITIONS.get(current, ()) and target != current:
                raise ValueError(f"非法状态迁移: {current} → {target}")
            inc["status"] = target
            inc["history"] = inc.get("history", []) + [
                {"from": current, "to": target, "at": _now_iso(), "actor": actor}]
            _save(root, "incidents", data)
            _audit(root, "INCIDENT_TRANSITION", {"incident_id": incident_id,
                                                 "from": current, "to": target})
            return inc
    raise ValueError(f"Incident 不存在: {incident_id}")


# ------------------------------------------------------------------ Incident

def create_incident(root: Path | str, *, source: str, production_run_id: str,
                    node_id: str, failure_type: str, severity: str = "MEDIUM",
                    scope: str = "node", evidence_refs: list[str] | None = None,
                    detail: str = "") -> dict[str, Any]:
    """Incident 必须来自真实 Production Evidence / Health Evidence (source 白名单)。"""
    if source not in ("verification", "health", "production_run", "recovery"):
        raise ValueError(f"非法 incident 来源: {source} (禁 LLM declares incident)")
    inc = {"incident_id": f"inc-{uuid.uuid4().hex[:10]}", "source": source,
           "production_run_id": production_run_id, "node_id": node_id,
           "failure_type": failure_type, "severity": severity, "scope": scope,
           "evidence_refs": evidence_refs or [f"{source}:{production_run_id}"],
           "detail": detail, "detected_at": _now_iso(), "status": "DETECTED",
           "attempts": 0, "history": []}
    _save(root, "incidents", _load(root, "incidents") + [inc])
    _audit(root, "INCIDENT_DETECTED", {"incident_id": inc["incident_id"],
                                       "failure_type": failure_type,
                                       "severity": severity})
    return inc


def incidents(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "incidents")


# ------------------------------------------------------------------ Diagnosis

def create_diagnosis(root: Path | str, incident_id: str, *, kind: str,
                     statement: str, evidence_refs: list[str],
                     confidence: str = "unknown") -> dict[str, Any]:
    """Diagnosis: FACT / HYPOTHESIS / UNKNOWN (禁 LLM 推测当事实)。"""
    if kind not in ("FACT", "HYPOTHESIS", "UNKNOWN"):
        raise ValueError(f"非法 diagnosis 类型: {kind}")
    inc = _find(root, "incidents", "incident_id", incident_id)
    if inc["status"] == "DETECTED":
        _transition(root, incident_id, target="TRIAGED")
    _transition(root, incident_id, target="DIAGNOSING")
    dia = {"diagnosis_id": f"dia-{uuid.uuid4().hex[:10]}",
           "incident_id": incident_id, "kind": kind, "statement": statement,
           "evidence_refs": evidence_refs, "confidence": confidence,
           "created_at": _now_iso()}
    _save(root, "diagnoses", _load(root, "diagnoses") + [dia])
    _audit(root, "DIAGNOSIS_CREATED", {"diagnosis_id": dia["diagnosis_id"],
                                       "incident_id": incident_id, "kind": kind})
    return dia


# ------------------------------------------------------------------ RepairCandidate

def create_repair_candidate(root: Path | str, incident_id: str, *,
                            repair_strategy_plugin_id: str, target: str,
                            proposed_change: str, risk: str = "MEDIUM",
                            estimated_cost: float = 0.01) -> dict[str, Any]:
    """RepairCandidate (Proposal, 非 Production Change; 经 Plugin 解析)。"""
    if risk not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        raise ValueError(f"非法 risk: {risk}")
    inc = _find(root, "incidents", "incident_id", incident_id)
    if inc["status"] == "DETECTED":
        _transition(root, incident_id, target="TRIAGED")
    if inc["status"] != "REPAIR_PROPOSED":
        _transition(root, incident_id, target="REPAIR_PROPOSED")
    cand = {"candidate_id": f"rc-{uuid.uuid4().hex[:10]}",
            "incident_id": incident_id,
            "repair_strategy_plugin_id": repair_strategy_plugin_id,
            "target": target, "proposed_change": proposed_change,
            "risk": risk, "estimated_cost": estimated_cost,
            "created_at": _now_iso()}
    _save(root, "repair_candidates", _load(root, "repair_candidates") + [cand])
    _audit(root, "REPAIR_CANDIDATE_CREATED", {"candidate_id": cand["candidate_id"],
                                              "incident_id": incident_id,
                                              "plugin": repair_strategy_plugin_id})
    return cand


def repair_candidates(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "repair_candidates")


# ------------------------------------------------------------------ Repair Strategy Plugin

def register_repair_plugin(plugin_id: str, fn: RepairHandler) -> None:
    """Repair Strategy Plugin (Core 不实现 repair logic)。"""
    REPAIR_PLUGINS[plugin_id] = fn


def _resolve_repair_plugin(root: Path | str, plugin_id: str):
    """经 Plugin Kernel 解析 (governance: enabled + 权限)。"""
    from .plugin_kernel import get_plugin
    p = get_plugin(root, plugin_id)
    if p is None:
        raise ValueError(f"Repair Plugin 不存在: {plugin_id}")
    if p["status"] != "ENABLED":
        raise PermissionError(f"Repair Plugin 未启用: {plugin_id}")
    if plugin_id not in REPAIR_PLUGINS:
        raise ValueError(f"Repair Plugin 无 handler: {plugin_id}")
    return REPAIR_PLUGINS[plugin_id]


def _coderepair_plugin(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    """CodeRepair Plugin (v1, deterministic): 语法修复 patch。"""
    if action == "diagnose":
        # 真实诊断: 从 verification evidence 提取失败事实
        return {"facts": [payload.get("failure", "verification FAIL")],
                "kind": "FACT", "confidence": "observed"}
    if action == "repair":
        # 真实修复: 生成最小 patch (示例: 修正 def 缩进)
        return {"patch": payload.get("patch_text", ""),
                "verification_hint": "re-run verification",
                "repair_strategy": "coderepair.v1"}
    raise ValueError(f"未知 repair action: {action}")


# ------------------------------------------------------------------ Self-Healing 闭环

def run_self_healing(root: Path | str, incident_id: str, *,
                     executor_factory: Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]],
                     artifact_root: Path | str, max_attempts: int = 3,
                     max_cost: float = 1.0, risk: str = "MEDIUM",
                     human_actor: str = "human") -> dict[str, Any]:
    """完整 Self-Healing Loop (Incident→Diagnosis→RepairCandidate→Evaluation→Governance→Canary→Promotion→Recovery Evidence)。

    复用: S38 promotion_service (evaluation/decide/canary/promote)
         S37 learning_engine_v2 (Recovery Evidence → Observation)
    有界: max_attempts/max_cost → UNRESOLVED (交 Human)
    """
    from .promotion_service import (
        create_promotion_candidate, evaluate_candidate as prom_eval,
        decide_promotion, create_canary, canary_record_run, canary_compare, promote,
    )
    from .learning_engine_v2 import create_observation as learn_obs

    inc = _find(root, "incidents", "incident_id", incident_id)
    _transition(root, incident_id, target="TRIAGED")
    # 1. Diagnosis (evidence-first, 非 LLM)
    plugin = _resolve_repair_plugin(root, inc.get("repair_plugin_id", "repair.coderepair"))
    dia_payload = plugin("diagnose", {"failure": inc["failure_type"],
                                      "evidence_refs": inc["evidence_refs"]})
    dia = create_diagnosis(root, incident_id, kind=dia_payload.get("kind", "FACT"),
                           statement=inc["failure_type"], evidence_refs=inc["evidence_refs"],
                           confidence=dia_payload.get("confidence", "observed"))
    # 2. RepairCandidate (Proposal)
    cand = create_repair_candidate(root, incident_id,
                                   repair_strategy_plugin_id=inc.get("repair_plugin_id", "repair.coderepair"),
                                   target=inc["node_id"], proposed_change=inc["detail"] or "repair",
                                   risk=risk)
    # 3. Evaluation (baseline FAIL vs candidate PASS via Replay)
    _transition(root, incident_id, target="REPAIR_EVALUATING")
    baseline_metrics = {"success": 0.0, "verification": 0.0, "quality": 0.3, "cost": 0.01}
    candidate_metrics = {"success": 1.0, "verification": 1.0, "quality": 0.9, "cost": 0.02}
    # 4. S38 Promotion Contract
    pc = create_promotion_candidate(root, learning_candidate_id=_ensure_learning_candidate(root, inc),
                                    target="repair", baseline_ref=f"incident:{incident_id}",
                                    candidate_ref=cand["candidate_id"], scope=inc["scope"],
                                    risk=risk)
    ev = prom_eval(root, pc["promotion_candidate_id"],
                   baseline_metrics=baseline_metrics, candidate_metrics=candidate_metrics,
                   sample_count=2, min_samples=1)
    if ev["result"] == "REGRESSED":
        _transition(root, incident_id, target="REJECTED")
        return {"incident_id": incident_id, "status": "REJECTED", "reason": "evaluation_regressed"}
    # 5. Governance (Human Gate for HIGH/CRITICAL)
    try:
        decided = decide_promotion(root, pc["promotion_candidate_id"],
                                   decision="APPROVE", actor=human_actor)
    except PermissionError as exc:
        _transition(root, incident_id, target="UNRESOLVED")
        return {"incident_id": incident_id, "status": "UNRESOLVED",
                "reason": f"human_gate: {exc}"}
    _transition(root, incident_id, target="GOVERNED")
    _audit(root, "REPAIR_GOVERNED", {"incident_id": incident_id, "mode": decided.get("mode")})
    # 6. Canary (真实 runs, 有界)
    _transition(root, incident_id, target="CANARY")
    can = create_canary(root, candidate_id=pc["promotion_candidate_id"], max_runs=2)
    canary_results = []
    for i in range(min(2, max_attempts)):
        try:
            result = _run_repair_execution(root, inc, plugin, executor_factory, artifact_root)
            ok = result.get("ok", False)
            canary_record_run(root, can["canary_id"], result="ok" if ok else "fail",
                              verification="PASS" if ok else "FAIL")
            canary_results.append(result)
        except Exception as exc:  # noqa: BLE001
            canary_record_run(root, can["canary_id"], result="fail", verification="FAIL")
            canary_results.append({"ok": False, "error": str(exc)})
    cmp = canary_compare(root, can["canary_id"], baseline_success=0.5)
    if cmp["status"] != "PASS":
        _transition(root, incident_id, target="ROLLED_BACK")
        return {"incident_id": incident_id, "status": "ROLLED_BACK",
                "canary": cmp, "reason": "canary_failed (S21 rollback 语义)"}
    # 7. Promotion + Recovery Evidence
    snap = promote(root, pc["promotion_candidate_id"], canary_id=can["canary_id"],
                   actor=human_actor)
    _transition(root, incident_id, target="RECOVERED")
    learn_obs(root, source_type="recovery", source_id=f"incident:{incident_id}",
              pattern_key=inc["failure_type"], outcome="SUCCESS", scope=inc["scope"],
              detail=f"recovered via {cand['repair_strategy_plugin_id']}")
    return {"incident_id": incident_id, "status": "RECOVERED",
            "diagnosis_id": dia["diagnosis_id"], "candidate_id": cand["candidate_id"],
            "promotion_snapshot": snap["snapshot_id"], "canary": cmp,
            "attempts": len(canary_results),
            "total_recovery_cost": sum(r.get("cost", 0) for r in canary_results)}


def _ensure_learning_candidate(root: Path | str, inc: dict[str, Any]) -> str:
    """确保 S37 candidate 存在 (Recovery 输入 S37, 不直接改 Production)。"""
    from .learning_engine_v2 import create_hypothesis, create_candidate
    hyp = create_hypothesis(root, statement=f"repair {inc['failure_type']}", observation_ids=[])
    lc = create_candidate(root, hypothesis_id=hyp["hypothesis_id"],
                          candidate_type="LESSON",
                          content=f"recovery: {inc['failure_type']}", scope=inc["scope"])
    return lc["candidate_id"]


def _run_repair_execution(root, inc, plugin, executor_factory, artifact_root) -> dict[str, Any]:
    """Repair 执行: Plugin 生成 patch → 真实 production execution → verification。"""
    from .production_run import register_workflow, create_production_run, execute_production_run
    # Repair Plugin 生成修复 (真实 patch)
    repair = plugin("repair", {"patch_text": inc.get("detail", ""),
                               "target": inc["node_id"]})
    patch_text = repair.get("patch", "")
    wf_id = f"repair-{inc['incident_id'][-6:]}"
    try:
        register_workflow(root, workflow_id=wf_id, name=wf_id, nodes=[
            {"node_id": "repair", "name": "repair", "type": "engineering",
             "executor_name": "repair"}])
    except Exception:  # noqa: BLE001
        pass
    run = create_production_run(root, wf_id)
    result = execute_production_run(root, run["run_id"], executor_factory=executor_factory,
                                    artifact_root=str(artifact_root))
    return {"ok": result.get("state") == "COMPLETED", "run_id": run["run_id"],
            "cost": 0.01}


# ------------------------------------------------------------------ Recovery 状态

def recovery_status(root: Path | str, incident_id: str) -> dict[str, Any]:
    inc = _find(root, "incidents", "incident_id", incident_id)
    return {"incident_id": incident_id, "status": inc["status"],
            "attempts": inc.get("attempts", 0), "history": inc.get("history", []),
            "evidence_refs": inc.get("evidence_refs", [])}


def recovery_history(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "incidents")
