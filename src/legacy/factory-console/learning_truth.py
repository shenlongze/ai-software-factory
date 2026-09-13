"""factory-console/learning_truth.py — P2-D Learning Consumption canonical domain。

契约 (docs/audits/2026-09-06-learning-consumption-p2-contract/, 22 份):
- 链: Experience → OBS-* → CAND-* → PROM-* → PROFILE-vN → Router → RD-*
- 每域唯一 writer (Observation/Candidate/Promotion/Profile/RoutingDecision Service)
- 独立 store: <root>/learning/{observations,candidates,promotions,profiles,
  routing_decisions}.json (与 legacy learning_engine_v2/intelligence 隔离)
- 幂等: obs 1 exp→1; cand 稳定派生键; prom 1 cand→1; profile version 递增;
  rd 1 run→1
- 治理: Promotion 默认 Human-in-the-loop (approval 经 governance_service
  subject_type="learning_promotion"); auto 仅低风险阈值内
- Profile = 治理输出 (versioned, 禁直写); Router 消费 {agent_id:
  {success_rate,...}} 兼容 shape (persona_score 映射) — 不改 router 算法
- 单向: Learning 只产 profile 数据, 禁改 prompt/code/tool/router 源码
"""

from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_lock = threading.RLock()

# ------------------------------------------------------------------ helpers


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base(root: Path | str) -> Path:
    return Path(root) / "learning"


def _file(root: Path | str, name: str) -> Path:
    return _base(root) / f"{name}.json"


def _load(root: Path | str, name: str) -> dict[str, dict[str, Any]]:
    p = _file(root, name)
    try:
        import json

        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items() if isinstance(v, dict)}
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save(root: Path | str, name: str, data: dict[str, dict[str, Any]]) -> None:
    import json

    p = _file(root, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def _import_console(mod: str):
    try:
        return __import__(f"factory_console.{mod}", fromlist=["*"])
    except ImportError:
        import importlib

        return importlib.import_module(mod)


def _exp_store(root: Path | str):
    m = _import_console("memory.experience_store")
    return m.ExperienceStore.from_workspace(Path(root))


def _get_exp(root: Path | str, exp_id: str) -> Optional[dict[str, Any]]:
    try:
        for r in _exp_store(root).records():
            d = r.to_dict() if hasattr(r, "to_dict") else r
            if str(d.get("id") or "") == exp_id:
                return d
    except Exception:  # noqa: BLE001
        pass
    return None


# ===================================================================
# OBSERVATION (OBS-*) — 从 canonical Experience 派生
# ===================================================================

OBS_STATUSES = ("CREATED", "PROCESSED", "REJECTED")


def derive_observation(root: Path | str, experience_id: str, *,
                       capability: str = "", agent: str = "",
                       quality: float = 0.5) -> dict[str, Any]:
    """canonical exp → OBS (唯一派生入口; 1 exp → 1 obs 幂等)。

    experience_id 必须存在 (canonical); 无 exp → ValueError。
    signal = SUCCESS/FAILURE (来自 exp.success — 不伪装)。
    """
    exp = _get_exp(root, experience_id)
    if exp is None:
        raise ValueError(f"Experience 不存在: {experience_id} (obs 必须来自 canonical exp)")
    if not (exp.get("task_run_id") or exp.get("exs_id") or exp.get("release_id")):
        raise ValueError(
            f"Experience {experience_id} 无 canonical anchor (legacy M3) — "
            f"不可作 P2-D 输入 (禁无 provenance 学习)")
    with _lock:
        recs = _load(root, "observations")
        for r in recs.values():
            if str(r.get("source_experience_id") or "") == experience_id:
                return r  # 幂等: 1 exp → 1 obs
        oid = f"OBS-{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        cap = str(capability or "")
        if not cap:
            cap = f"task:{str(exp.get('task') or 'general')[:40]}"
        obs = {
            "observation_id": oid,
            "source_experience_id": experience_id,
            "task_run_id": str(exp.get("task_run_id") or ""),
            "exs_id": str(exp.get("exs_id") or ""),
            "release_id": str(exp.get("release_id") or ""),
            "agent_id": str(agent or exp.get("agent") or ""),
            "capability": cap,
            "signal": "SUCCESS" if exp.get("success") else "FAILURE",
            "quality": float(quality or 0.5),
            "confidence": float(exp.get("confidence") or 0.5),
            "evidence_refs": [str(exp.get("source_id") or experience_id)],
            "status": "CREATED",
            "created_at": now,
        }
        recs[oid] = obs
        _save(root, "observations", recs)
        return obs


def list_observations(root: Path | str, *, agent: str = "",
                      capability: str = "", signal: str = "") -> list[dict[str, Any]]:
    recs = _load(root, "observations")
    out = []
    for r in recs.values():
        if agent and str(r.get("agent_id") or "") != agent:
            continue
        if capability and capability not in str(r.get("capability") or ""):
            continue
        if signal and str(r.get("signal") or "") != signal:
            continue
        out.append(r)
    return sorted(out, key=lambda r: str(r.get("created_at") or ""))


# ===================================================================
# CANDIDATE (CAND-*) — Learning 建议 (非生效)
# ===================================================================

CAND_STATUSES = ("PROPOSED", "APPROVED", "REJECTED", "EXPIRED")


def propose_candidate(root: Path | str, *, agent_id: str, capability: str,
                      proposed_delta: float, rationale: str = "",
                      min_obs: int = 3) -> dict[str, Any]:
    """Observations → Candidate (学习建议; 非生效)。

    幂等键: (agent_id, capability) 的 PROPOSED/APPROVED candidate 已存在 →
    返回现有 (不重复建议)。evidence = 该 agent+capability 的 CREATED obs。
    evidence_count < min_obs → 仍可 PROPOSED (标低证据), 但 promotion gate 拦。
    """
    obs = list_observations(root, agent=agent_id, capability=capability,
                            signal="SUCCESS")
    if not obs:
        # 允许 FAILURE-only? candidate 需正信号; 无 → 仍可建但 evidence 0
        obs_all = list_observations(root, agent=agent_id, capability=capability)
        if not obs_all:
            raise ValueError(
                f"无 observations for agent={agent_id} capability={capability} — "
                f"candidate 必须来自 obs (禁凭空建议)")
    with _lock:
        recs = _load(root, "candidates")
        for r in recs.values():
            if (str(r.get("agent_id") or "") == agent_id
                    and str(r.get("capability") or "") == capability
                    and str(r.get("status") or "") in ("PROPOSED", "APPROVED")):
                return r  # 幂等
        cid = f"CAND-{uuid.uuid4().hex[:12]}"
        cand = {
            "candidate_id": cid,
            "observation_ids": [o["observation_id"] for o in obs],
            "agent_id": agent_id,
            "capability": capability,
            "proposed_delta": float(proposed_delta or 0.0),
            "proposed_success_rate": None,  # promotion 时按 obs 统计填
            "rationale": str(rationale or "")[:500],
            "evidence_count": len(obs),
            "confidence": min(0.95, 0.4 + 0.1 * len(obs)),
            "status": "PROPOSED",
            "created_at": _now_iso(),
        }
        recs[cid] = cand
        _save(root, "candidates", recs)
        return cand


def _candidate_success_rate(root: Path | str, cand: dict[str, Any]) -> float:
    """从 candidate 的 obs 统计 success_rate (真实 evidence 依据)。"""
    succ = 0
    total = 0
    for oid in cand.get("observation_ids") or []:
        obs = _load(root, "observations").get(str(oid))
        if obs:
            total += 1
            if str(obs.get("signal") or "") == "SUCCESS":
                succ += 1
    return (succ / total) if total else 0.0


def list_candidates(root: Path | str, *, agent: str = "", status: str = "") -> list[dict[str, Any]]:
    recs = _load(root, "candidates")
    return sorted(
        (r for r in recs.values()
         if (not agent or str(r.get("agent_id") or "") == agent)
         and (not status or str(r.get("status") or "") == status)),
        key=lambda r: str(r.get("created_at") or ""))


def get_candidate(root: Path | str, cid: str) -> Optional[dict[str, Any]]:
    return _load(root, "candidates").get(cid)


# ===================================================================
# PROMOTION (PROM-*) — 治理事实 (Human-in-the-loop 默认)
# ===================================================================

PROM_STATUSES = ("PROPOSED", "APPROVED", "APPLIED", "REJECTED", "REVOKED", "FAILED")


def propose_promotion(root: Path | str, candidate_id: str, *,
                      policy: str = "human_review",
                      min_obs_gate: int = 3,
                      min_quality_gate: float = 0.6) -> dict[str, Any]:
    """Candidate → Promotion PROPOSED (治理提案; 1 cand → 1 prom 幂等)。

    policy 决定审批路径: human_review (默认 — governance approval 必需) /
    auto_low_risk (evidence_count ≥ auto 阈值且 delta 在界内 — 契约 D9 边界)。
    """
    cand = get_candidate(root, candidate_id)
    if cand is None:
        raise ValueError(f"Candidate 不存在: {candidate_id}")
    with _lock:
        recs = _load(root, "promotions")
        for r in recs.values():
            if str(r.get("candidate_id") or "") == candidate_id:
                return r  # 幂等: 1 cand → 1 prom
        pid = f"PROM-{uuid.uuid4().hex[:8]}"
        rate = _candidate_success_rate(root, cand)
        auto_allowed = (
            policy == "auto_low_risk"
            and int(cand.get("evidence_count") or 0) >= 10
            and rate >= 0.8
        )
        prom = {
            "promotion_id": pid,
            "candidate_id": candidate_id,
            "agent_id": str(cand.get("agent_id") or ""),
            "capability": str(cand.get("capability") or ""),
            "policy": policy,
            "auto_allowed": bool(auto_allowed),
            "approval": None,  # {approval_id, decision, decided_by, at}
            "evidence_count": int(cand.get("evidence_count") or 0),
            "proposed_success_rate": round(rate, 4),
            "min_obs_gate": min_obs_gate,
            "min_quality_gate": float(min_quality_gate),
            "status": "PROPOSED",
            "profile_version": None,  # APPLIED 后填
            "created_at": _now_iso(),
            "history": [{"to": "PROPOSED", "at": _now_iso(), "actor": "learning"}],
        }
        recs[pid] = prom
        _save(root, "promotions", recs)
        return prom


def approve_promotion(root: Path | str, promotion_id: str, *,
                      decided_by: str = "admin", reason: str = "") -> dict[str, Any]:
    """治理审批 → APPROVED (human 或 auto_allowed)。"""
    with _lock:
        recs = _load(root, "promotions")
        prom = recs.get(promotion_id)
        if prom is None:
            raise KeyError(f"Promotion 不存在: {promotion_id}")
        if str(prom.get("status") or "") not in ("PROPOSED",):
            raise ValueError(f"Promotion {promotion_id} 已决 (当前 {prom.get('status')})")
        cand = get_candidate(root, str(prom.get("candidate_id") or ""))
        ec = int(cand.get("evidence_count") or 0) if cand else 0
        if ec < int(prom.get("min_obs_gate") or 3):
            raise ValueError(
                f"Promotion {promotion_id} evidence 不足: {ec} < min {prom.get('min_obs_gate')} — REJECT")
        if bool(prom.get("auto_allowed")):
            prom["approval"] = {"approval_id": "auto", "decision": "AUTO_APPROVED",
                                "decided_by": "learning-policy", "at": _now_iso()}
        else:
            # human 审批: 复用 governance_service (subject_type=learning_promotion)
            gov = _import_console("governance_service")
            ar = gov.request_approval(
                Path(root), production_run_id="", artifact_ids=[],
                requested_by="learning", policy_id="learning_promotion",
                subject_type="learning_promotion", subject_id=promotion_id)
            gov.decide_approval(Path(root), ar["approval_id"], decision="APPROVED",
                                decided_by=decided_by, reason=reason)
            prom["approval"] = {"approval_id": ar["approval_id"], "decision": "APPROVED",
                                "decided_by": decided_by, "at": _now_iso(),
                                "reason": str(reason or "")[:300]}
        prom["status"] = "APPROVED"
        prom["history"].append({"to": "APPROVED", "at": _now_iso(),
                                "actor": decided_by, "note": reason})
        _save(root, "promotions", recs)
        return prom


def reject_promotion(root: Path | str, promotion_id: str, *,
                     decided_by: str = "admin", reason: str = "") -> dict[str, Any]:
    with _lock:
        recs = _load(root, "promotions")
        prom = recs.get(promotion_id)
        if prom is None:
            raise KeyError(f"Promotion 不存在: {promotion_id}")
        if str(prom.get("status") or "") not in ("PROPOSED", "APPROVED"):
            raise ValueError(f"Promotion {promotion_id} 不可拒 (当前 {prom.get('status')})")
        prom["status"] = "REJECTED"
        prom["approval"] = {"decision": "REJECTED", "decided_by": decided_by,
                            "at": _now_iso(), "reason": str(reason or "")[:300]}
        prom["history"].append({"to": "REJECTED", "at": _now_iso(),
                                "actor": decided_by, "note": reason})
        _save(root, "promotions", recs)
        return prom


def list_promotions(root: Path | str, *, status: str = "") -> list[dict[str, Any]]:
    recs = _load(root, "promotions")
    return sorted(
        (r for r in recs.values()
         if not status or str(r.get("status") or "") == status),
        key=lambda r: str(r.get("created_at") or ""))


def get_promotion(root: Path | str, pid: str) -> Optional[dict[str, Any]]:
    return _load(root, "promotions").get(pid)


# ===================================================================
# PROFILE (PROFILE-vN) — 治理输出 (versioned, 只经 promotion 生)
# ===================================================================

def _profiles_file_data(root: Path | str) -> dict[str, Any]:
    """profiles store: {agent_id: {current_version, profiles: {v: {...}}}}。"""
    return _load(root, "profiles")


def _persist_profiles(root: Path | str, data: dict[str, Any]) -> None:
    _save(root, "profiles", data)


def apply_promotion(root: Path | str, promotion_id: str) -> dict[str, Any]:
    """APPROVED Promotion → Profile 新版本 (1 prom → 1 version; 幂等)。

    PROFILE-{agent_id}:v{N} 追加 (immutable 历史); 旧版 SUPERSEDED 语义保留。
    """
    with _lock:
        recs = _load(root, "promotions")
        prom = recs.get(promotion_id)
        if prom is None:
            raise KeyError(f"Promotion 不存在: {promotion_id}")
        if str(prom.get("status") or "") == "APPLIED":
            cur = _current_profile(root, str(prom.get("agent_id") or ""))
            if cur is None:  # pragma: no cover — 状态不一致兜底
                raise ValueError(f"Promotion {promotion_id} APPLIED 但无 profile")
            return cur  # 幂等
        if str(prom.get("status") or "") != "APPROVED":
            raise ValueError(f"Promotion {promotion_id} 未 APPROVED (当前 {prom.get('status')}) — 禁 APPLY")
        aid = str(prom.get("agent_id") or "")
        cap = str(prom.get("capability") or "")
        rate = float(prom.get("proposed_success_rate") or 0.0)
        # 目标 success_rate: 从当前 active cap score 提升 (capability 加权平均)
        data = _profiles_file_data(root)
        agent_rec = data.get(aid)
        if agent_rec is None:
            agent_rec = {"current_version": 0, "profiles": {}}
            data[aid] = agent_rec
        ver = int(agent_rec.get("current_version") or 0) + 1
        prev = agent_rec.get("profiles", {}).get(str(agent_rec.get("current_version") or 0)) or {}
        prev_caps = dict(prev.get("capabilities") or {})
        # 新 cap score = rate (由真实 obs evidence 支撑); 其余能力沿用 (衰减不覆盖)
        new_caps = dict(prev_caps)
        new_caps[cap] = max(0.0, min(1.0, rate))
        # 聚合 success_rate: capability score 均值 (router persona_score 来源)
        agg = (sum(new_caps.values()) / len(new_caps)) if new_caps else 0.0
        profile = {
            "profile_id": f"PROFILE-{aid}-v{ver}",
            "agent_id": aid,
            "version": ver,
            "promotion_id": promotion_id,
            "candidate_id": str(prom.get("candidate_id") or ""),
            "capabilities": new_caps,
            "success_rate": round(agg, 4),  # router persona_score 消费字段
            "confidence": min(0.95, 0.4 + 0.05 * int(prom.get("evidence_count") or 0)),
            "evidence_count": int(prom.get("evidence_count") or 0),
            "status": "ACTIVE",
            "created_at": _now_iso(),
        }
        agent_rec["profiles"][str(ver)] = profile
        agent_rec["current_version"] = ver
        _persist_profiles(root, data)
        prom["status"] = "APPLIED"
        prom["profile_version"] = ver
        prom["history"].append({"to": "APPLIED", "at": _now_iso(),
                                "actor": "learning", "note": f"PROFILE-{aid}-v{ver}"})
        _save(root, "promotions", recs)
        return profile


def _current_profile(root: Path | str, agent_id: str) -> Optional[dict[str, Any]]:
    data = _profiles_file_data(root)
    agent_rec = data.get(agent_id)
    if not agent_rec:
        return None
    ver = int(agent_rec.get("current_version") or 0)
    return (agent_rec.get("profiles") or {}).get(str(ver))


def get_profile(root: Path | str, agent_id: str,
                version: Optional[int] = None) -> Optional[dict[str, Any]]:
    data = _profiles_file_data(root)
    agent_rec = data.get(agent_id)
    if not agent_rec:
        return None
    if version is None:
        return _current_profile(root, agent_id)
    return (agent_rec.get("profiles") or {}).get(str(int(version)))


def rollback_profile(root: Path | str, agent_id: str, to_version: int, *,
                     actor: str = "admin", reason: str = "") -> dict[str, Any]:
    """Profile rollback: 切 current_version 到历史版本 (immutable, 审计)。"""
    with _lock:
        data = _profiles_file_data(root)
        agent_rec = data.get(agent_id)
        if not agent_rec:
            raise KeyError(f"无 profile for {agent_id}")
        profiles = agent_rec.get("profiles") or {}
        target = profiles.get(str(int(to_version)))
        if target is None:
            raise ValueError(f"Profile v{to_version} 不存在 for {agent_id}")
        agent_rec["current_version"] = int(to_version)
        agent_rec["rollback"] = {"to_version": int(to_version), "actor": actor,
                                 "reason": str(reason or "")[:300], "at": _now_iso()}
        _persist_profiles(root, data)
        return target


def list_profiles(root: Path | str, *, agent_id: str = "") -> list[dict[str, Any]]:
    data = _profiles_file_data(root)
    out = []
    for aid, agent_rec in data.items():
        if agent_id and aid != agent_id:
            continue
        cur = int(agent_rec.get("current_version") or 0)
        for ver, p in (agent_rec.get("profiles") or {}).items():
            p = dict(p)
            p["is_current"] = int(ver) == cur
            out.append(p)
    return sorted(out, key=lambda p: (str(p.get("agent_id")), int(p.get("version") or 0)))


def router_profiles(root: Path | str) -> dict[str, dict[str, Any]]:
    """Router 消费 shape: {agent_id: {success_rate, ...}} (persona_score 映射)。
    失败安全: 空 {} → router 中性 (不 fake)。"""
    data = _profiles_file_data(root)
    out: dict[str, dict[str, Any]] = {}
    for aid, agent_rec in data.items():
        cur = _current_profile(root, aid)
        if cur:
            out[aid] = {"success_rate": float(cur.get("success_rate") or 0.0),
                        "profile_id": str(cur.get("profile_id") or ""),
                        "version": int(cur.get("version") or 0)}
    return out


# ===================================================================
# ROUTING DECISION (RD-*) — 可审计决策事实
# ===================================================================

RD_STATUSES = ("CREATED", "CONSUMED")


def record_routing_decision(root: Path | str, *, task_run_id: str,
                            task_id: str = "", objective: str = "",
                            selected_resource: str = "", resource_type: str = "agent",
                            profile_id: str = "", profile_version: Optional[int] = None,
                            persona_score: Optional[float] = None,
                            alternatives: Optional[list[dict[str, Any]]] = None,
                            reason: str = "", fallback: bool = False,
                            actor: str = "") -> dict[str, Any]:
    """RoutingDecision (1 run → 1 RD 幂等)。"""
    if not task_run_id:
        raise ValueError("RD 需要 task_run_id")
    with _lock:
        recs = _load(root, "routing_decisions")
        for r in recs.values():
            if str(r.get("task_run_id") or "") == task_run_id:
                return r  # 幂等
        rid = f"RD-{uuid.uuid4().hex[:8]}"
        rd = {
            "decision_id": rid,
            "task_run_id": task_run_id,
            "task_id": str(task_id or ""),
            "objective": str(objective or "")[:200],
            "selected_resource": str(selected_resource or ""),
            "resource_type": str(resource_type or "agent"),
            "profile_id": str(profile_id or ""),
            "profile_version": profile_version,
            "persona_score": persona_score,
            "alternatives": alternatives or [],
            "reason": str(reason or "")[:500],
            "fallback": bool(fallback),
            "status": "CREATED",
            "actor": str(actor or ""),
            "created_at": _now_iso(),
        }
        recs[rid] = rd
        _save(root, "routing_decisions", recs)
        return rd


def list_routing_decisions(root: Path | str, *, task_run_id: str = "") -> list[dict[str, Any]]:
    recs = _load(root, "routing_decisions")
    return sorted(
        (r for r in recs.values()
         if not task_run_id or str(r.get("task_run_id") or "") == task_run_id),
        key=lambda r: str(r.get("created_at") or ""))


def trace_decision(root: Path | str, decision_id: str) -> dict[str, Any]:
    """RD → profile → PROM → CAND → OBS → exp (纯 FK)。"""
    out: dict[str, Any] = {"decision": None, "profile": None, "promotion": None,
                           "candidate": None, "observations": [],
                           "experience_ids": [], "chain": []}
    rd = _load(root, "routing_decisions").get(decision_id)
    if rd is None:
        return out
    out["decision"] = rd
    out["chain"].append(("routing_decision", decision_id))
    pid = str(rd.get("profile_id") or "")
    if pid:
        m = re.match(r"^PROFILE-(.+)-v(\d+)$", pid)
        if m:
            prof = get_profile(root, m.group(1), version=int(m.group(2)))
            out["profile"] = prof
            out["chain"].append(("profile", pid))
            prom = get_promotion(root, str((prof or {}).get("promotion_id") or ""))
            if prom:
                out["promotion"] = prom
                out["chain"].append(("promotion", prom["promotion_id"]))
                cand = get_candidate(root, str(prom.get("candidate_id") or ""))
                if cand:
                    out["candidate"] = cand
                    out["chain"].append(("candidate", cand["candidate_id"]))
                    obs_all = _load(root, "observations")
                    for oid in cand.get("observation_ids") or []:
                        obs = obs_all.get(str(oid))
                        if obs:
                            out["observations"].append(obs)
                            eid = str(obs.get("source_experience_id") or "")
                            if eid and eid not in out["experience_ids"]:
                                out["experience_ids"].append(eid)
    return out
