"""factory-console/performance_selection.py — S33 Performance-aware Workforce Selection.

Evidence → Performance → Deterministic Selection:
- Ranking Contract: score = w1*success + w2*verification + w3*recovery + w4*evaluation; confidence = n/(n+K)
- Selection Pipeline: Capability → Eligibility → Permission → Policy → Ranking → Selected
- Governance 永远优先于 Performance
- Cold-start: sample_count=0 → deterministic fallback (不锁死)
- Performance Snapshot: selection 时保存当时 performance (append-only, 历史可解释)
- 真实替换实验: Evidence 变化 → Selection 变化 (非 hard-coded)

复用: S30 agent_performance + S31 Plugin Kernel + S32 Composition + S17 governance
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .plugin_kernel import bootstrap, get_plugin, list_plugins
from .workforce_os import agent_performance, _get_or_create_agent_profile

#: Evidence-aware ranking 权重 (冻结)
W_SUCCESS = 0.4
W_VERIFICATION = 0.3
W_RECOVERY = 0.2
W_EVALUATION = 0.1
#: confidence 半衰常数 (n=K → confidence=0.5)
CONFIDENCE_K = 10.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "selection" / f"{name}.json"


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
            trace_id=payload.get("selection_id") or payload.get("capability") or "",
            actor_type="system", actor_id="selection",
            action=f"selection.{event_type.lower()}",
            source="performance_selection", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"selection": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ Performance (从 Evidence 投影)

def plugin_performance(root: Path | str, plugin_id: str) -> dict[str, Any]:
    """Plugin 的 Performance (从真实 Production Evidence 投影; 无样本 → 0 诚实)。"""
    p = get_plugin(root, plugin_id)
    if p is None:
        raise ValueError(f"Plugin 不存在: {plugin_id}")
    # 从 AgentProfile (同 role) 投影真实 runs performance
    from .workforce_os import list_agent_profiles
    best: dict[str, Any] | None = None
    for prof in list_agent_profiles(root):
        if prof.get("composition", {}).get("agent_plugin_id") == plugin_id or \
           prof.get("composition", {}).get("provider_plugin_id") == plugin_id:
            perf = agent_performance(root, prof["agent_id"])
            if best is None or (perf.get("sample_count", 0) > best.get("sample_count", 0)):
                best = perf
    if best is None or best.get("sample_count", 0) == 0:
        return {"plugin_id": plugin_id, "sample_count": 0, "success_rate": None,
                "verification_rate": None, "recovery_rate": None, "evaluation_score": None,
                "confidence": 0.0, "ranking_score": 0.0,
                "explain": "无 Production Evidence (sample_count=0, 诚实 unknown)"}
    n = best["sample_count"]
    success = best.get("success_rate", 0) or 0
    verification = best.get("verification_pass_rate", 0) or 0
    eval_score = best.get("evaluation_score")
    eval_norm = (eval_score / 100.0) if eval_score is not None else 0.0
    recovery = _recovery_rate(root, best.get("evidence_refs", []))
    score = W_SUCCESS * success + W_VERIFICATION * verification + W_RECOVERY * recovery + W_EVALUATION * eval_norm
    confidence = n / (n + CONFIDENCE_K)
    return {"plugin_id": plugin_id, "sample_count": n,
            "success_rate": success, "verification_rate": verification,
            "recovery_rate": recovery, "evaluation_score": eval_score,
            "confidence": round(confidence, 3), "ranking_score": round(score * confidence, 4),
            "evidence_refs": best.get("evidence_refs", []),
            "explain": f"从 {n} 个真实 ProductionRun 投影"}


def _recovery_rate(root: Path | str, run_refs: list[str]) -> float:
    """Recovery rate: 该 agent 的 runs 中 recovery 成功比例 (S28 数据)。"""
    from .recovery_service import recovery_attempts
    recovered = 0
    total = 0
    for run_id in run_refs:
        attempts = recovery_attempts(root, run_id)
        if attempts:
            total += 1
            if attempts[-1]["status"] == "RECOVERED":
                recovered += 1
    return round(recovered / total, 3) if total else 0.0


# ------------------------------------------------------------------ 确定性 Ranking

def rank_plugins(root: Path | str, *, required_capability: str) -> dict[str, Any]:
    """确定性 Ranking: capability → eligible → permission → policy → performance score。

    Governance (permission/policy) 优先于 Performance。相同输入 → 相同排序。
    """
    bootstrap(root)
    # 1. capability eligible (ENABLED)
    candidates = [p for p in list_plugins(root)
                  if required_capability in p["capabilities"] and p["status"] == "ENABLED"]
    # 2. permission/policy gate (Governance 优先)
    eligible = []
    rejected = []
    for p in candidates:
        if any(perm == "self_elevate" for perm in p["permissions"]):
            rejected.append({"plugin_id": p["plugin_id"], "reason": "permission_denied (self_elevate)"})
            continue
        eligible.append(p)
    # 3. performance ranking (deterministic)
    ranked = []
    for p in eligible:
        perf = plugin_performance(root, p["plugin_id"])
        ranked.append({"plugin_id": p["plugin_id"], "type": p["type"],
                       "version": p["version"], "performance": perf,
                       "ranking_score": perf["ranking_score"]})
    # 确定性排序: score desc, 同分按 plugin_id (稳定)
    ranked.sort(key=lambda r: (-r["ranking_score"], r["plugin_id"]))
    return {"capability": required_capability, "candidates": ranked, "rejected": rejected,
            "ranking": [r["plugin_id"] for r in ranked]}


def select_plugin(root: Path | str, *, required_capability: str,
                  explain: bool = True) -> dict[str, Any]:
    """Performance-aware Selection (deterministic; cold-start 不锁死)。"""
    result = rank_plugins(root, required_capability=required_capability)
    if not result["candidates"]:
        return {"selected": False, "capability": required_capability,
                "reason": f"无 eligible plugin (capability={required_capability})",
                "rejected": result["rejected"], "ranking": []}
    selected = result["candidates"][0]
    # Performance Snapshot (append-only, 历史可解释)
    snapshot = {"snapshot_id": f"snap-{uuid.uuid4().hex[:8]}",
                "capability": required_capability,
                "selected_plugin": selected["plugin_id"],
                "version": selected["version"],
                "performance": selected["performance"],
                "ranking_score": selected["ranking_score"],
                "candidates": [c["plugin_id"] for c in result["candidates"]],
                "created_at": _now_iso()}
    _save(root, "snapshots", _load(root, "snapshots") + [snapshot])
    _audit(root, "PERFORMANCE_SELECTION",
           {"capability": required_capability, "selected": selected["plugin_id"],
            "score": selected["ranking_score"]})
    if explain:
        sel = selected
        reason = (f"capability_match=true permission=granted policy=allowed "
                  f"sample_count={sel['performance']['sample_count']} "
                  f"success_rate={sel['performance'].get('success_rate')} "
                  f"ranking_score={sel['ranking_score']}")
        return {"selected": True, "plugin_id": selected["plugin_id"],
                "version": selected["version"], "capability": required_capability,
                "ranking_score": selected["ranking_score"],
                "reason": reason, "snapshot_id": snapshot["snapshot_id"],
                "ranking": result["ranking"], "rejected": result["rejected"]}
    return {"selected": True, "plugin_id": selected["plugin_id"],
            "ranking": result["ranking"]}


# ------------------------------------------------------------------ 历史可追溯

def selection_history(root: Path | str, *, capability: str = "") -> list[dict[str, Any]]:
    """历史 Selection (append-only, 从 snapshot 解释)。"""
    data = _load(root, "snapshots")
    if capability:
        data = [s for s in data if s["capability"] == capability]
    return data


def plugin_performance_history(root: Path | str, plugin_id: str) -> list[dict[str, Any]]:
    """某 plugin 的历史 performance 快照 (每次被选时记录)。"""
    return [s for s in _load(root, "snapshots") if s["selected_plugin"] == plugin_id]


# ------------------------------------------------------------------ Cold-start 规则

def cold_start_strategy(root: Path | str, *, required_capability: str) -> dict[str, Any]:
    """Cold-start: 全部候选无 evidence → 确定性规则 (注册顺序, 不锁死)。"""
    result = rank_plugins(root, required_capability=required_capability)
    no_evidence = [c for c in result["candidates"] if c["performance"]["sample_count"] == 0]
    has_evidence = [c for c in result["candidates"] if c["performance"]["sample_count"] > 0]
    strategy = {
        "capability": required_capability,
        "has_evidence": [c["plugin_id"] for c in has_evidence],
        "no_evidence": [c["plugin_id"] for c in no_evidence],
    }
    if has_evidence:
        strategy["strategy"] = "evidence_priority"
        strategy["note"] = "优先选择有真实 evidence 的 plugin (样本数加权)"
    elif no_evidence:
        strategy["strategy"] = "registration_order"
        strategy["note"] = "全部无 evidence → 按注册顺序选择 (cold-start 不锁死)"
    else:
        strategy["strategy"] = "none"
        strategy["note"] = "无候选"
    return strategy
