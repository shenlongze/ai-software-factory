"""factory-console/product_truth.py — P1 Product Truth domain (IDEA-*/DISC-*/REQ-*/PRD-*/PLAN-*)。

契约 (docs/audits/2026-09-05-product-truth-p1-contract/):
- D1: 六层 Product Domain (Idea/Discovery/Requirement/PRD/Plan; Task=P0 canonical)
- D2: IDEA-*/DISC-*/REQ-*/PRD-*/PLAN-*; 旧 PI-*/req_{hex12}/session_id/filename = LEGACY
- D3: 每 Entity 唯一 writer (IdeaService/DiscoveryService/RequirementService/
      PRDService/PlanService — 本模块函数即唯一 writer)
- D4: 独立 lifecycle
- D5-D6: Idea→Discovery 1:N, Discovery→Req 1:N, Req→PRD N:1, PRD→Plan 1:N,
         Plan→Task 1:N (task.plan_id 已由 P0 create_task 支持)
- D7: PRD versioned; Plan immutable snapshot
- D8: PRD-* truth; PRD.md projection
- D9: plans store 唯一 canonical Plan (session_plans.json = orchestration legacy)

存储: <root>/product_truth/{ideas,discoveries,requirements,prds,plans}.json
- 与 legacy 完全隔离: product/ideas.json (PI-*), requirements/requirements.json
  (req_*), session_plans.json — 不读不写不迁移。
- 幂等: create 支持 idempotency_key (同 key → 返回已有); 每 store 原子写 (RLock
  + tmp + os.replace)。
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_lock = threading.RLock()

# ---------------------------------------------------------------------------
# 低层 helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _store_file(root: Path | str, kind: str) -> Path:
    return Path(root) / "product_truth" / f"{kind}.json"


def _load(root: Path | str, kind: str) -> dict[str, dict[str, Any]]:
    p = _store_file(root, kind)
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}  # 失败安全: 单文件损坏不阻断其它
    if not isinstance(raw, dict):
        return {}
    return raw


def _save(root: Path | str, kind: str, recs: dict[str, dict[str, Any]]) -> None:
    p = _store_file(root, kind)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(recs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def _rec_id(rec: dict[str, Any]) -> str:
    return str(rec.get("id") or rec.get(f"{_kind_of(rec)}_id") or "")


def _kind_of(rec: dict[str, Any]) -> str:
    """由 id 前缀推 kind (IDEA-* → ideas …)。"""
    i = str(rec.get("id") or "")
    for prefix, kind in (("IDEA", "ideas"), ("DISC", "discoveries"),
                         ("REQ", "requirements"), ("PRD", "prds"),
                         ("PLAN", "plans")):
        if i.startswith(prefix):
            return kind
    return "ideas"


# ---------------------------------------------------------------------------
# 状态机 (D4 — 最小必要状态, 禁复杂 workflow)
# ---------------------------------------------------------------------------

IDEA_STATES = {"created", "refined", "validated", "approved", "rejected", "archived"}
DISC_STATES = {"pending", "running", "completed"}  # completed = product_defined (契约)
REQ_STATES = {"draft", "validated", "approved", "superseded", "rejected"}
PRD_STATES = {"draft", "approved", "superseded", "archived"}
PLAN_STATES = {"pending", "approved", "executing", "completed", "cancelled"}

# 受控转换表 (allowed: from → to)
_IDEA_T = {("created", "refined"), ("created", "validated"), ("refined", "validated"),
           ("validated", "approved"), ("approved", "archived"),
           ("created", "rejected"), ("validated", "rejected")}
_DISC_T = {("pending", "running"), ("running", "completed"),
           ("pending", "completed")}  # 允许直接完成 (无 running 步骤时)
_REQ_T = {("draft", "validated"), ("validated", "approved"),
          ("approved", "superseded"), ("draft", "rejected"), ("validated", "rejected")}
_PRD_T = {("draft", "approved"), ("approved", "superseded"), ("approved", "archived")}
_PLAN_T = {("pending", "approved"), ("approved", "executing"),
           ("executing", "completed"), ("pending", "cancelled")}


def _transition_allowed(kind: str, frm: str, to: str) -> bool:
    tbl = {"ideas": _IDEA_T, "discoveries": _DISC_T,
           "requirements": _REQ_T, "prds": _PRD_T, "plans": _PLAN_T}.get(kind)
    return bool(tbl and (frm, to) in tbl)


# ---------------------------------------------------------------------------
# 通用 store accessors (每 domain 独立函数, 唯一 writer = 本模块)
# ---------------------------------------------------------------------------


def _base_create(root: Path | str, kind: str, *, prefix: str,
                 init: dict[str, Any], idempotency_key: str = "",
                 actor: str = "") -> dict[str, Any]:
    """锁内: 幂等查 (idempotency_key) → 生成 id → 写入。返回完整 rec。"""
    with _lock:
        recs = _load(root, kind)
        if idempotency_key:
            for r in recs.values():
                if r.get("idempotency_key") == idempotency_key:
                    return r
        rid = _new_id(prefix)
        now = _now_iso()
        rec: dict[str, Any] = {
            "id": rid,
            **init,
            "status": str(init.get("status") or _default_status(kind)),
            "idempotency_key": idempotency_key,
            "actor": actor,
            "created_at": now,
            "updated_at": now,
            "history": [{"to": str(init.get("status") or _default_status(kind)),
                         "at": now, "actor": actor}],
        }
        recs[rid] = rec
        _save(root, kind, recs)
        return rec


def _default_status(kind: str) -> str:
    return {"ideas": "created", "discoveries": "pending", "requirements": "draft",
            "prds": "draft", "plans": "pending"}.get(kind, "created")


def _get(root: Path | str, kind: str, rid: str) -> dict[str, Any] | None:
    return _load(root, kind).get(rid)


def _update_content(root: Path | str, kind: str, rid: str, *,
                    title: str | None = None, description: str | None = None,
                    actor: str = "") -> dict[str, Any]:
    """S47-E4: 通用内容更新 (仅 draft/pending 草稿状态; 已批准语义不可原地改)。
    锁内读-改-写; 返回更新后 rec; 不存在 → KeyError; 非草稿状态 → ValueError。"""
    import copy as _copy

    with _lock:
        data = _load(root, kind)
        rec = data.get(rid)
        if rec is None:
            raise KeyError(f"{kind} {rid} 不存在")
        editable = {"ideas": ("created", "refined"),
                    "discoveries": ("pending", "running"),
                    "requirements": ("draft",),
                    "prds": ("draft",),
                    "plans": ("pending",)}.get(kind, ())
        if str(rec.get("status") or "") not in editable:
            raise ValueError(
                f"{kind} {rid} 状态 {rec.get('status')} 不可原地改 — 已进入审批链, 请走版本化")
        upd = _copy.deepcopy(rec)
        if title is not None:
            upd["title"] = str(title)[:200]
        if description is not None:
            upd["description"] = str(description)[:8000]
        upd["updated_at"] = _now_iso()
        upd.setdefault("history", []).append({"to": str(upd.get("status")),
                                              "at": _now_iso(), "actor": actor or "",
                                              "note": "content-updated"})
        data[rid] = upd
        _save(root, kind, data)
        return upd


def _list(root: Path | str, kind: str,
          **filters: Any) -> list[dict[str, Any]]:
    out = []
    for r in _load(root, kind).values():
        ok = True
        for k, v in filters.items():
            if not v:
                continue
            if isinstance(v, (list, tuple, set)):
                if str(r.get(k, "")) not in {str(x) for x in v}:
                    ok = False
                    break
            elif str(r.get(k, "")) != str(v):
                ok = False
                break
        if ok:
            out.append(r)
    return sorted(out, key=lambda r: str(r.get("created_at") or ""))


def _transition(root: Path | str, kind: str, rid: str, to: str, *,
                actor: str = "", note: str = "") -> dict[str, Any]:
    with _lock:
        recs = _load(root, kind)
        r = recs.get(rid)
        if r is None:
            raise KeyError(f"{kind} 不存在: {rid}")
        frm = str(r.get("status") or "")
        if frm == to:
            return r  # 幂等: 同态转换返回现状
        if not _transition_allowed(kind, frm, to):
            raise ValueError(f"非法 {kind} 转换: {frm} → {to}")
        r["status"] = to
        r["updated_at"] = _now_iso()
        h = list(r.get("history") or [])
        h.append({"to": to, "at": _now_iso(), "actor": actor, "note": note})
        r["history"] = h
        recs[rid] = r
        _save(root, kind, recs)
        return r


# ---------------------------------------------------------------------------
# Domain accessors — Idea (IDEA-*)
# ---------------------------------------------------------------------------


def create_idea(root: Path | str, *, project_id: str = "", title: str,
                description: str = "", source: str = "",
                idempotency_key: str = "", actor: str = "") -> dict[str, Any]:
    """IdeaService.create_idea — 唯一 Idea writer。"""
    if not title:
        raise ValueError("idea title required")
    return _base_create(root, "ideas", prefix="IDEA",
                        init={"project_id": project_id, "title": str(title)[:200],
                              "description": str(description or "")[:2000],
                              "source": str(source or ""),
                              "status": "created", "metadata": {}},
                        idempotency_key=idempotency_key, actor=actor)


def get_idea(root: Path | str, idea_id: str) -> dict[str, Any] | None:
    return _get(root, "ideas", idea_id)


def list_ideas(root: Path | str, **filters: Any) -> list[dict[str, Any]]:
    return _list(root, "ideas", **filters)


def transition_idea(root: Path | str, idea_id: str, to: str, *,
                    actor: str = "") -> dict[str, Any]:
    return _transition(root, "ideas", idea_id, to, actor=actor)


def update_idea(root: Path | str, idea_id: str, *,
                title: str | None = None, description: str | None = None,
                actor: str = "") -> dict[str, Any]:
    """S47-E5: Idea 草稿期内容更新 (created/refined 可改; 已 validated 拒绝)。"""
    return _update_content(root, "ideas", idea_id,
                           title=title, description=description, actor=actor)


def transition_discovery(root: Path | str, discovery_id: str, to: str, *,
                         actor: str = "") -> dict[str, Any]:
    return _transition(root, "discoveries", discovery_id, to, actor=actor)


def update_discovery(root: Path | str, discovery_id: str, *,
                     title: str | None = None, input_ref: str | None = None,
                     actor: str = "") -> dict[str, Any]:
    """S47-E5: Discovery 内容更新 (pending/running 可改)。input_ref 承载正文。"""
    with _lock:
        data = _load(root, "discoveries")
        rec = data.get(discovery_id)
        if rec is None:
            raise KeyError(f"discoveries {discovery_id} 不存在")
        if str(rec.get("status") or "") not in ("pending", "running"):
            raise ValueError(f"discoveries {discovery_id} 状态 {rec.get('status')} 不可原地改")
        import copy as _copy
        upd = _copy.deepcopy(rec)
        if title is not None:
            upd["title"] = str(title)[:200]
        if input_ref is not None:
            upd["input_ref"] = str(input_ref)[:8000]
        upd["updated_at"] = _now_iso()
        upd.setdefault("history", []).append({"to": str(upd.get("status")),
                                              "at": _now_iso(), "actor": actor or "",
                                              "note": "content-updated"})
        data[discovery_id] = upd
        _save(root, "discoveries", data)
        return upd


def transition_prd(root: Path | str, prd_id: str, to: str, *,
                   actor: str = "") -> dict[str, Any]:
    return _transition(root, "prds", prd_id, to, actor=actor)


def transition_plan(root: Path | str, plan_id: str, to: str, *,
                    actor: str = "") -> dict[str, Any]:
    return _transition(root, "plans", plan_id, to, actor=actor)


def update_prd_content(root: Path | str, prd_id: str, body: str, *,
                       actor: str = "") -> dict[str, Any]:
    """S47-E5: PRD 正文写入 (版本化 — draft 阶段追加 version content.body)。
    返回更新后 rec; 不存在 → KeyError; 非 draft → ValueError (已批准走
    supersede + 新 PRD)。"""
    if not body:
        raise ValueError("prd body required")
    with _lock:
        data = _load(root, "prds")
        rec = data.get(prd_id)
        if rec is None:
            raise KeyError(f"prds {prd_id} 不存在")
        if str(rec.get("status") or "") != "draft":
            raise ValueError(f"prds {prd_id} 状态 {rec.get('status')} — 已批准走版本化 (新 PRD)")
        import copy as _copy
        upd = _copy.deepcopy(rec)
        ver = int(upd.get("current_version") or 1) + 1
        upd["current_version"] = ver
        upd.setdefault("versions", []).append({
            "version": ver,
            "content": {"title": str(upd.get("title") or ""),
                        "requirement_ids": list(upd.get("requirement_ids") or []),
                        "body": str(body)[:20000]},
            "created_at": _now_iso(), "actor": actor,
        })
        upd["updated_at"] = _now_iso()
        upd.setdefault("history", []).append({"to": "draft", "at": _now_iso(),
                                              "actor": actor or "", "note": f"v{ver} body"})
        data[prd_id] = upd
        _save(root, "prds", data)
        return upd


# ---------------------------------------------------------------------------
# Discovery (DISC-*)
# ---------------------------------------------------------------------------


def create_discovery(root: Path | str, *, idea_id: str, title: str = "",
                     input_ref: str = "", actor: str = "") -> dict[str, Any]:
    """DiscoveryService.create — 唯一 Discovery writer (复用现有 discovery
    能力边界: 本函数持久化; 现有 complete_discovery 收敛调用)。"""
    if not idea_id:
        raise ValueError("discovery idea_id required")
    return _base_create(root, "discoveries", prefix="DISC",
                        init={"idea_id": idea_id,
                              "title": str(title or "")[:200],
                              "input_ref": str(input_ref or ""),
                              "findings": [], "decision": "",
                              "status": "pending", "metadata": {}},
                        idempotency_key=f"disc:{idea_id}:{title[:60]}",
                        actor=actor)


def get_discovery(root: Path | str, discovery_id: str) -> dict[str, Any] | None:
    return _get(root, "discoveries", discovery_id)


def list_discoveries(root: Path | str, **filters: Any) -> list[dict[str, Any]]:
    return _list(root, "discoveries", **filters)


def complete_discovery(root: Path | str, discovery_id: str, *,
                       findings: list[dict[str, Any]] | None = None,
                       decision: str = "", actor: str = "") -> dict[str, Any]:
    """完成 Discovery (→ completed = product_defined 语义)。写入 findings/decision。"""
    with _lock:
        recs = _load(root, "discoveries")
        r = recs.get(discovery_id)
        if r is None:
            raise KeyError(f"discoveries 不存在: {discovery_id}")
        if str(r.get("status") or "") == "completed":
            return r  # 幂等
        frm = str(r.get("status") or "")
        if not _transition_allowed("discoveries", frm, "completed"):
            raise ValueError(f"非法 discovery 转换: {frm} → completed")
        if findings is not None:
            r["findings"] = list(findings)[:100]
        if decision:
            r["decision"] = str(decision)[:4000]
        r["status"] = "completed"
        r["completed_at"] = _now_iso()
        r["updated_at"] = _now_iso()
        h = list(r.get("history") or [])
        h.append({"to": "completed", "at": _now_iso(), "actor": actor})
        r["history"] = h
        recs[discovery_id] = r
        _save(root, "discoveries", recs)
        return r


# ---------------------------------------------------------------------------
# Requirement (REQ-*)
# ---------------------------------------------------------------------------


def create_requirement(root: Path | str, *, discovery_id: str = "",
                       title: str, description: str = "",
                       priority: str = "P2", source: str = "",
                       idempotency_key: str = "", actor: str = "") -> dict[str, Any]:
    """RequirementService.create — 唯一 Requirement writer (replaces req_* inline)。"""
    if not title:
        raise ValueError("requirement title required")
    return _base_create(root, "requirements", prefix="REQ",
                        init={"discovery_id": discovery_id,
                              "title": str(title)[:200],
                              "description": str(description or "")[:4000],
                              "priority": str(priority or "P2"),
                              "source": str(source or ""),
                              "status": "draft", "metadata": {}},
                        idempotency_key=idempotency_key, actor=actor)


def get_requirement(root: Path | str, req_id: str) -> dict[str, Any] | None:
    return _get(root, "requirements", req_id)


def list_requirements(root: Path | str, **filters: Any) -> list[dict[str, Any]]:
    return _list(root, "requirements", **filters)


def transition_requirement(root: Path | str, req_id: str, to: str, *,
                           actor: str = "") -> dict[str, Any]:
    return _transition(root, "requirements", req_id, to, actor=actor)


def update_requirement(root: Path | str, req_id: str, *,
                       title: str | None = None, description: str | None = None,
                       actor: str = "") -> dict[str, Any]:
    """Requirement 内容更新 (S47-E4): 仅 draft 状态可原地完善内容;
    已 validated/approved 的记录 → 拒绝 (需走版本化, 见 create_prd 禁则)。
    返回更新后 rec; 不存在 → KeyError。"""
    return _update_content(root, "requirements", req_id,
                           title=title, description=description, actor=actor)


# ---------------------------------------------------------------------------
# PRD (PRD-* + version) — D7
# ---------------------------------------------------------------------------


def create_prd(root: Path | str, *, project_id: str = "",
               title: str, requirement_ids: list[str] | None = None,
               actor: str = "") -> dict[str, Any]:
    """PRDService.create — 唯一 PRD writer。生成 draft + 首个 version。"""
    if not title:
        raise ValueError("prd title required")
    rid = _new_id("PRD")
    now = _now_iso()
    rec = {
        "id": rid,
        "project_id": project_id,
        "title": str(title)[:200],
        "requirement_ids": [str(x) for x in (requirement_ids or [])],
        "status": "draft",
        "current_version": 1,
        "versions": [{
            "version": 1,
            "content": {"title": str(title)[:200],
                        "requirement_ids": [str(x) for x in (requirement_ids or [])]},
            "created_at": now, "actor": actor,
        }],
        "actor": actor,
        "created_at": now, "updated_at": now,
        "history": [{"to": "draft", "at": now, "actor": actor}],
    }
    with _lock:
        recs = _load(root, "prds")
        recs[rid] = rec
        _save(root, "prds", recs)
    return rec


def get_prd(root: Path | str, prd_id: str) -> dict[str, Any] | None:
    return _get(root, "prds", prd_id)


def list_prds(root: Path | str, **filters: Any) -> list[dict[str, Any]]:
    return _list(root, "prds", **filters)


def approve_prd(root: Path | str, prd_id: str, *,
                content: dict[str, Any] | None = None,
                actor: str = "") -> dict[str, Any]:
    """批准 PRD → 新 version (D7: Task 经 Plan 锁定 PRD version)。"""
    with _lock:
        recs = _load(root, "prds")
        r = recs.get(prd_id)
        if r is None:
            raise KeyError(f"prds 不存在: {prd_id}")
        if str(r.get("status") or "") == "approved":
            return r  # 幂等
        if not _transition_allowed("prds", str(r.get("status") or ""), "approved"):
            raise ValueError(f"非法 prd 转换: {r.get('status')} → approved")
        ver = int(r.get("current_version") or 0) + 1
        r["current_version"] = ver
        vs = list(r.get("versions") or [])
        vs.append({"version": ver,
                   "content": content if content is not None else
                              (vs[-1].get("content") if vs else {}),
                   "created_at": _now_iso(), "actor": actor})
        r["versions"] = vs
        r["status"] = "approved"
        r["approved_at"] = _now_iso()
        r["updated_at"] = _now_iso()
        h = list(r.get("history") or [])
        h.append({"to": "approved", "at": _now_iso(), "actor": actor,
                  "version": ver})
        r["history"] = h
        recs[prd_id] = r
        _save(root, "prds", recs)
        return r


# ---------------------------------------------------------------------------
# Plan (PLAN-* — immutable snapshot, D9) — D9 canonical store
# ---------------------------------------------------------------------------


def create_plan(root: Path | str, *, project_id: str = "", prd_id: str = "",
                prd_version: int = 0, requirement_id: str = "",
                goal: str, tasks: list[dict[str, Any]] | None = None,
                order: list[str] | None = None,
                acceptance: list[str] | None = None,
                ask_approval: bool = True,
                idempotency_key: str = "", actor: str = "") -> dict[str, Any]:
    """PlanService.create_plan — 唯一 canonical Plan writer (immutable snapshot)。

    修改已批准 Plan = 新 PLAN-* (绝不原地改语义 — 见 update_plan_semantics 禁则)。
    """
    if not goal:
        raise ValueError("plan goal required")
    return _base_create(root, "plans", prefix="PLAN",
                        init={"project_id": project_id, "prd_id": prd_id,
                              "prd_version": int(prd_version or 0),
                              "requirement_id": requirement_id,
                              "requirement_ids": [requirement_id] if requirement_id else [],
                              "goal": str(goal)[:300],
                              "tasks": [dict(t) for t in (tasks or [])][:50],
                              "order": [str(x) for x in (order or [])][:50],
                              "acceptance": [str(x) for x in (acceptance or [])][:20],
                              "ask_approval": bool(ask_approval),
                              "status": "pending", "metadata": {}},
                        idempotency_key=idempotency_key, actor=actor)


def get_plan(root: Path | str, plan_id: str) -> dict[str, Any] | None:
    return _get(root, "plans", plan_id)


def list_plans(root: Path | str, **filters: Any) -> list[dict[str, Any]]:
    return _list(root, "plans", **filters)


def approve_plan(root: Path | str, plan_id: str, *, actor: str = "") -> dict[str, Any]:
    return _transition(root, "plans", plan_id, "approved", actor=actor)


def _reject_mutate_plan(root: Path | str, plan_id: str) -> None:
    """D9/D11 禁则: 已 approved/executing 的 Plan 原地修改 → 拒绝 (须新 PLAN-*)。"""
    r = _get(root, "plans", plan_id)
    if r and str(r.get("status") or "") in ("approved", "executing", "completed"):
        raise ValueError(
            f"Plan {plan_id} 已生效 ({r.get('status')}) — 不可原地修改语义; "
            f"请创建新 PLAN-* (immutable snapshot 契约 D9/D11)")


# ---------------------------------------------------------------------------
# Traceability (D15/D12) — 纯 FK 查询 (forward/reverse)
# ---------------------------------------------------------------------------


def _find(root: Path | str, kind: str, rid: str) -> dict[str, Any] | None:
    return _load(root, kind).get(rid)


def forward_trace(root: Path | str, idea_id: str = "") -> dict[str, Any]:
    """正向: IDEA → DISC[] → REQ[] → PRD[] → PLAN[] → (tasks 引用)。"""
    ideas = list_ideas(root) if not idea_id else \
        [x for x in list_ideas(root) if x.get("id") == idea_id]
    result = {"ideas": [], "discoveries": [], "requirements": [],
              "prds": [], "plans": []}
    for idea in ideas:
        iid = idea.get("id")
        result["ideas"].append(idea)
        discs = [d for d in list_discoveries(root) if d.get("idea_id") == iid]
        for d in discs:
            did = d.get("id")
            result["discoveries"].append(d)
            reqs = [r for r in list_requirements(root)
                    if r.get("discovery_id") == did]
            for rq in reqs:
                result["requirements"].append(rq)
                prds = [p for p in list_prds(root)
                        if rq.get("id") in (p.get("requirement_ids") or [])]
                for p in prds:
                    if p not in result["prds"]:
                        result["prds"].append(p)
                    plans = [pl for pl in list_plans(root)
                             if pl.get("prd_id") == p.get("id")
                             or pl.get("requirement_id") == rq.get("id")]
                    for pl in plans:
                        if pl not in result["plans"]:
                            result["plans"].append(pl)
        # MVP 直连 REQ→PLAN (prd_id 空): plan.requirement_id 属于该 discovery 的 req
        for pl in list_plans(root):
            if pl.get("requirement_id") and \
               any(r.get("id") == pl.get("requirement_id") for r in
                   list_requirements(root)):
                if pl not in result["plans"]:
                    result["plans"].append(pl)
    return result


def reverse_trace(root: Path | str, task_id: str) -> dict[str, Any]:
    """反向: TASK → PLAN → PRD → REQ → DISC → IDEA (纯 canonical FK)。

    task.plan_id 从 backlog task.json 读取 (P0 canonical — 本函数不写,
    只读 P0 store; task 无 plan_id → 仅返回 task 级信息, 不伪造)。
    """
    out: dict[str, Any] = {"task": None, "plan": None, "prd": None,
                           "prd_version": 0, "requirement": None,
                           "discovery": None, "idea": None, "chain": []}
    # 1. Task (P0 canonical backlog)
    task = _find_task(root, task_id)
    if task is None:
        return out
    out["task"] = task
    out["chain"].append(("task", task_id))
    plan_id = str(task.get("plan_id") or "")
    if not plan_id:
        return out  # 无 plan_id → LEGACY/手动任务 (不伪造上游)
    out["chain"].append(("plan", plan_id))
    # 2. Plan
    plan = _find(root, "plans", plan_id)
    if plan is None:
        return out  # plan 不在 canonical store (legacy session plan) — 断链
    out["plan"] = plan
    # 3. PRD (prd_id + prd_version) 或 Requirement (MVP 直连)
    prd_id = str(plan.get("prd_id") or "")
    if prd_id:
        prd = _find(root, "prds", prd_id)
        if prd:
            out["prd"] = prd
            out["prd_version"] = int(plan.get("prd_version") or prd.get("current_version") or 0)
            out["chain"].append(("prd", prd_id, f"v{out['prd_version']}"))
    req_id = str(plan.get("requirement_id") or "")
    if not req_id and prd_id:
        p = out["prd"] or {}
        reqs = p.get("requirement_ids") or []
        req_id = str(reqs[0]) if reqs else ""
    if req_id:
        req = _find(root, "requirements", req_id)
        if req:
            out["requirement"] = req
            out["chain"].append(("requirement", req_id))
            did = str(req.get("discovery_id") or "")
            if did:
                disc = _find(root, "discoveries", did)
                if disc:
                    out["discovery"] = disc
                    out["chain"].append(("discovery", did))
                    iid = str(disc.get("idea_id") or "")
                    if iid:
                        idea = _find(root, "ideas", iid)
                        if idea:
                            out["idea"] = idea
                            out["chain"].append(("idea", iid))
    return out


def _find_task(root: Path | str, task_id: str) -> dict[str, Any] | None:
    """P0 canonical Task 只读查找 (backlog task.json — 不写不迁移)。"""
    base = Path(root) / "workspace" / "projects"
    if base.is_dir():
        for proj in base.iterdir():
            p = proj / "management" / "backlog" / "task.json"
            if p.is_file():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                tasks = data if isinstance(data, list) else data.get("tasks", [])
                if isinstance(tasks, dict):
                    tasks = list(tasks.values())
                for t in tasks:
                    if str(t.get("id") or "") == task_id:
                        return t
    return None


# ---------------------------------------------------------------------------
# 查询: Product chain 反查 task (供 CLI/API — 只读)
# ---------------------------------------------------------------------------


def task_chain(root: Path | str, task_id: str) -> list[str]:
    """返回 [TASK-*, PLAN-*, PRD-*, REQ-*, DISC-*, IDEA-*] 已解析段 (供显示)。"""
    tr = reverse_trace(root, task_id)
    return [f"{k}:{v.get('id', '')}" for k, v in tr.items()
            if v is not None and k != "chain"]
