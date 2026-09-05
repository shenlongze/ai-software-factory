"""factory-console/release_truth.py — P2-A Release Truth (RELEASE-*)。

契约 (docs/audits/2026-09-06-release-truth-p2-contract/):
- Canonical Release = RELEASE-{hex8}; rel-* (M3) = LEGACY 隔离
- SSOT: <root>/releases/release_truth.json (独立于 M3 release_service 的
  releases.json — rel-* 同文件会 id 混列 + M3 create KeyError, 故独立文件)
- Writer: ReleaseService (本模块函数唯一)
- Lifecycle: CREATED → CANDIDATE → GATED → RELEASED → SUPERSEDED
                       ↘ REJECTED (可重试) / REVOKED (撤回)
- Gate 消费 canonical P0 facts: art-* (artifact_ids), ver-* (verification_ids
  MUST PASS), EVD-* (evidence_ids, completeness), run/EXS provenance
- Release 不自己验证 (不跑 pytest), 不产 Artifact, 不写 ver/EVD
- P0/P1 consume-only (FK 全来自已有 store; zero reverse-write)
- Git tag = metadata (external ref), 非 Release Truth
- 幂等: create(idempotency_key) → 同 key 已有返回; 同 task_run+exs 非 terminal → 返回

依赖读取 (consume):
  node_runtime.get_node_run / verification_domain.list_verifications /
  evidence_domain.list_evidence / artifact_lifecycle.list_artifacts /
  product_truth.reverse_trace (TASK 反查 Product Truth)
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_lock = threading.RLock()

# Lifecycle (契约 03)
ST_CREATED = "CREATED"
ST_CANDIDATE = "CANDIDATE"
ST_GATED = "GATED"
ST_RELEASED = "RELEASED"
ST_SUPERSEDED = "SUPERSEDED"
ST_REJECTED = "REJECTED"
ST_REVOKED = "REVOKED"
TERMINAL = (ST_RELEASED, ST_SUPERSEDED, ST_REJECTED, ST_REVOKED)

_TRANSITIONS = {
    ST_CREATED: {ST_CANDIDATE, ST_REJECTED, ST_SUPERSEDED, ST_REVOKED},
    ST_CANDIDATE: {ST_GATED, ST_REJECTED, ST_SUPERSEDED, ST_REVOKED},
    ST_GATED: {ST_RELEASED, ST_REJECTED, ST_CANDIDATE, ST_SUPERSEDED, ST_REVOKED},
    ST_RELEASED: {ST_SUPERSEDED, ST_REVOKED},
    ST_SUPERSEDED: set(),
    ST_REJECTED: {ST_CANDIDATE, ST_SUPERSEDED, ST_REVOKED},  # gate 修复后重试 / 作废 / 撤回
    ST_REVOKED: set(),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _store_file(root: Path | str) -> Path:
    return Path(root) / "releases" / "release_truth.json"


def _load(root: Path | str) -> dict[str, dict[str, Any]]:
    p = _store_file(root)
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, dict)}


def _save(root: Path | str, recs: dict[str, dict[str, Any]]) -> None:
    p = _store_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(recs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)


# ---------------------------------------------------------------------------
# 读取 helpers (consume P0 canonical — 包内/顶层双模式)
# ---------------------------------------------------------------------------


def _import(mod: str):
    try:
        return __import__(f"factory_console.{mod}", fromlist=["*"])
    except ImportError:
        import importlib

        return importlib.import_module(mod)


def _get_run(root: Path | str, run_id: str) -> dict[str, Any] | None:
    try:
        nr = _import("node_runtime")
        return nr.get_node_run(root, run_id)
    except Exception:  # noqa: BLE001
        return None


def _verifications_for_run(root: Path | str, run_id: str) -> list[dict[str, Any]]:
    try:
        vd = _import("verification_domain")
        return vd.list_verifications(root, task_run_id=run_id)
    except Exception:  # noqa: BLE001
        return []


def _evidence_for_ver(root: Path | str, ver_id: str) -> list[dict[str, Any]]:
    try:
        ed = _import("evidence_domain")
        return ed.list_evidence(root, verification_id=ver_id)
    except Exception:  # noqa: BLE001
        return []


def _artifacts_for(root: Path | str, *, run_id: str = "", exs_id: str = "") -> list[dict[str, Any]]:
    try:
        al = _import("artifact_lifecycle")
        arts = al.list_artifacts(root)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for a in arts:
        if run_id and a.get("node_run_id") == run_id:
            out.append(a)
        elif exs_id and a.get("exs_id") == exs_id:
            out.append(a)
    return out


def _task_of_run(root: Path | str, run_id: str) -> str:
    run = _get_run(root, run_id)
    if run:
        return str(run.get("task_id") or "")
    return ""


# ---------------------------------------------------------------------------
# ReleaseService
# ---------------------------------------------------------------------------


def create_release(root: Path | str, *, task_run_id: str, exs_id: str = "",
                   reason: str = "", actor: str = "release_engineer",
                   idempotency_key: str = "") -> dict[str, Any]:
    """创建 Release (唯一 writer)。自动从 P0 canonical 收集 FK。

    幂等: idempotency_key 或 同 (task_run_id, exs_id) 非 terminal → 返回现有。
    初始状态 CREATED; 自动收集的产物/验证/证据存 candidate 段。
    """
    if not task_run_id:
        raise ValueError("release task_run_id required")
    task_id = _task_of_run(root, task_run_id)
    arts = _artifacts_for(root, run_id=task_run_id, exs_id=exs_id)
    vers = _verifications_for_run(root, task_run_id)
    evd = []
    for v in vers:
        for e in _evidence_for_ver(root, str(v.get("verification_id") or "")):
            if e not in evd:
                evd.append(e)
    with _lock:
        recs = _load(root)
        # 幂等
        for r in recs.values():
            if idempotency_key and r.get("idempotency_key") == idempotency_key:
                return r
            if (r.get("task_run_id") == task_run_id
                    and r.get("exs_id") == exs_id
                    and r.get("status") not in TERMINAL):
                return r
        rid = f"RELEASE-{uuid.uuid4().hex[:8]}"
        now = _now_iso()
        rec = {
            "release_id": rid,
            "status": ST_CANDIDATE,  # 契约 03: CREATED 后即 CANDIDATE (可评估)
            "task_id": task_id,
            "task_run_id": task_run_id,
            "exs_id": exs_id,
            "artifact_ids": [str(a.get("artifact_id") or "") for a in arts if a.get("artifact_id")],
            "verification_ids": [str(v.get("verification_id") or "") for v in vers
                                 if v.get("verification_id")],
            "evidence_ids": [str(e.get("evidence_id") or "") for e in evd if e.get("evidence_id")],
            "reason": str(reason or "")[:500],
            "metadata": {},           # git_commit/tag 等 external ref 只入此
            "actor": actor,
            "idempotency_key": idempotency_key,
            "gate": None,             # gate 评估结果快照
            "created_at": now,
            "updated_at": now,
            "history": [{"to": ST_CANDIDATE, "at": now, "actor": actor, "note": "created as candidate"}],
        }
        recs[rid] = rec
        _save(root, recs)
        return rec


def get_release(root: Path | str, release_id: str) -> dict[str, Any] | None:
    return _load(root).get(release_id)


def list_releases(root: Path | str, *, status: str = "",
                  task_id: str = "") -> list[dict[str, Any]]:
    out = []
    for r in _load(root).values():
        if status and r.get("status") != status:
            continue
        if task_id and r.get("task_id") != task_id:
            continue
        out.append(r)
    return sorted(out, key=lambda r: str(r.get("created_at") or ""))


def _transition(root: Path | str, rid: str, to: str, *, actor: str,
                note: str = "") -> dict[str, Any]:
    with _lock:
        recs = _load(root)
        r = recs.get(rid)
        if r is None:
            raise KeyError(f"Release 不存在: {rid}")
        frm = str(r.get("status") or "")
        if frm == to:
            return r  # 幂等同态
        allowed = _TRANSITIONS.get(frm, set())
        if to not in allowed:
            raise ValueError(f"非法 Release 转换: {frm} → {to}")
        r["status"] = to
        r["updated_at"] = _now_iso()
        h = list(r.get("history") or [])
        h.append({"to": to, "at": _now_iso(), "actor": actor, "note": note})
        r["history"] = h
        recs[rid] = r
        _save(root, recs)
        return r


def _ver_status(root: Path | str, ver_id: str) -> str:
    try:
        vd = _import("verification_domain")
        v = vd.get_verification(root, ver_id)
        return str(v.get("status") or "") if v else ""
    except Exception:  # noqa: BLE001
        return ""


def _has_evidence(root: Path | str, ver_id: str) -> bool:
    return bool(_evidence_for_ver(root, ver_id))


def gate_release(root: Path | str, release_id: str, *,
                 require_approval: bool = False,
                 actor: str = "release_engineer") -> dict[str, Any]:
    """Release Gate (契约 04): 消费 canonical art-*/ver-*/EVD-*。

    MUST: artifact ≥1 / verification ≥1 且全 PASS / evidence completeness /
          run+exs provenance / (approval 若 require_approval — execute 时查)
    全过 → GATED; 否则 → REJECTED (诚实, 可修复后 CANDIDATE 重试)。
    """
    r = get_release(root, release_id)
    if r is None:
        raise KeyError(f"Release 不存在: {release_id}")
    missing: list[str] = []
    # 1. Artifact 存在 (canonical art-*)
    arts = [a for a in (r.get("artifact_ids") or [])]
    if not arts:
        missing.append("artifact")
    # 2. Verification canonical ver-* 存在且全 PASS (release policy: MUST)
    vers = [v for v in (r.get("verification_ids") or [])]
    if not vers:
        missing.append("verification")
    ver_fail = [v for v in vers if _ver_status(root, v) != "PASS"]
    if ver_fail:
        missing.append(f"verification_not_pass:{','.join(ver_fail)}")
    # 3. Evidence completeness (每 ver PASS 有 ≥1 EVD-*)
    if vers:
        no_ev = [v for v in vers if not _has_evidence(root, v)]
        if no_ev:
            missing.append(f"evidence_missing:{','.join(no_ev)}")
    # 4. run/exs provenance
    if not r.get("task_run_id"):
        missing.append("task_run")
    if not r.get("exs_id"):
        missing.append("exs")
    allowed = len(missing) == 0
    r["gate"] = {"allowed": allowed, "missing": missing,
                 "checked_at": _now_iso(), "actor": actor}
    with _lock:
        recs = _load(root)
        r = recs.get(release_id)
        if r is None:
            raise KeyError(f"Release 不存在: {release_id}")
        r["gate"] = {"allowed": allowed, "missing": missing,
                     "checked_at": _now_iso(), "actor": actor}
        r["updated_at"] = _now_iso()
        recs[release_id] = r
        _save(root, recs)
    if allowed:
        return _transition(root, release_id, ST_GATED, actor=actor,
                           note="gate passed (canonical ver-*/EVD-*)")
    return _transition(root, release_id, ST_REJECTED, actor=actor,
                       note=f"gate blocked: {', '.join(missing)}")


def _approval_ok(root: Path | str, release_id: str) -> bool:
    """查 governance approval (subject_type=release, subject_id=RELEASE-*) 已批准。

    governance 记录: decision 字段 (PENDING/APPROVED/REJECTED) — APPROVED 即放行。
    """
    try:
        from factory_console.governance_service import list_approvals
        for ar in list_approvals(root):
            if (str(ar.get("subject_type") or "") == "release"
                    and str(ar.get("subject_id") or "") == release_id
                    and str(ar.get("decision") or "") == "APPROVED"):
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


def execute_release(root: Path | str, release_id: str, *,
                    require_approval: bool = True,
                    actor: str = "release_engineer") -> dict[str, Any]:
    """RELEASED (人工 approval 后)。Gate 未过/无 approval → 拒绝 (FAIL→BLOCK)。"""
    r = get_release(root, release_id)
    if r is None:
        raise KeyError(f"Release 不存在: {release_id}")
    if r.get("status") == ST_RELEASED:
        return r  # 幂等
    if require_approval and not _approval_ok(root, release_id):
        raise ValueError(
            f"Release {release_id} 无已批准的 governance approval "
            f"(subject_type=release) — FAIL→BLOCK")
    # gate 重新评估 (确保消费最新 ver/EVD)
    g = gate_release(root, release_id, actor=actor)
    if g.get("status") != ST_GATED:
        raise ValueError(
            f"Release {release_id} gate 未通过: {g.get('gate', {}).get('missing')}")
    return _transition(root, release_id, ST_RELEASED, actor=actor,
                       note="released (canonical gate passed + approval)")


def supersede_release(root: Path | str, release_id: str, *,
                      by_release_id: str = "", actor: str = "release_engineer") -> dict[str, Any]:
    r = _transition(root, release_id, ST_SUPERSEDED, actor=actor,
                    note=f"superseded by {by_release_id}" if by_release_id else "superseded")
    return r


def revoke_release(root: Path | str, release_id: str, *,
                   actor: str = "release_engineer", reason: str = "") -> dict[str, Any]:
    return _transition(root, release_id, ST_REVOKED, actor=actor,
                       note=reason or "revoked")


# ---------------------------------------------------------------------------
# Traceability (契约 05) — 纯 FK, 复用 P1 reverse_trace
# ---------------------------------------------------------------------------


def trace_release(root: Path | str, release_id: str) -> dict[str, Any]:
    """反向: RELEASE → ver/EVD/art → EXS → run → TASK → PLAN → PRD → REQ → DISC → IDEA。"""
    r = get_release(root, release_id)
    out: dict[str, Any] = {"release": None, "chain": []}
    if r is None:
        return out
    out["release"] = r
    out["chain"].append(("release", release_id))
    # P0 段 (release 字段直连)
    if r.get("exs_id"):
        out["chain"].append(("exs", r["exs_id"]))
    if r.get("task_run_id"):
        out["chain"].append(("task_run", r["task_run_id"]))
    for aid in (r.get("artifact_ids") or []):
        out["chain"].append(("artifact", aid))
    for vid in (r.get("verification_ids") or []):
        out["chain"].append(("verification", vid))
    for eid in (r.get("evidence_ids") or []):
        out["chain"].append(("evidence", eid))
    # Task → Product Truth (复用 P1)
    task_id = str(r.get("task_id") or "")
    if task_id:
        try:
            pt = _import("product_truth")
            tr = pt.reverse_trace(root, task_id)
            out["task"] = tr.get("task")
            out["plan"] = tr.get("plan")
            out["prd"] = tr.get("prd")
            out["prd_version"] = tr.get("prd_version")
            out["requirement"] = tr.get("requirement")
            out["discovery"] = tr.get("discovery")
            out["idea"] = tr.get("idea")
            # 附加 tr 链 (plan→prd→req→disc→idea)
            for k, v in tr.get("chain", []):
                if k != "task" and (k, v) not in out["chain"]:
                    out["chain"].append((k, v))
        except Exception:  # noqa: BLE001 — task 反查失败不阻断 release trace
            pass
    return out
