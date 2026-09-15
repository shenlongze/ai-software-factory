"""验收域 · 用户认可用例（S45 canonical 语义，搬迁自 factory_console.acceptance_truth）。

语义边界（S45 §6）：Verification（机器可验证 PASS）≠ Acceptance（用户认可）。
本域只回答：用户是否认可某个具体 artifact/version。

- ID: ACC-{hex8}；SSOT: <root>/acceptance/acceptance.json
- writer: 本模块（唯一；approve / request_change）
- 状态: PENDING → APPROVED | CHANGE_REQUESTED → SUPERSEDED（不删历史）
- 绑定: artifact_id + version + verification_id（禁模糊批准）
- 幂等: approve 同 (artifact_id, version) 重复 → 返回现有；
        request_change 同 (artifact, version, comment) 重复 → 不重复建
- 非法转换: SUPERSEDED → APPROVED 拒绝；CHANGE_REQUESTED → APPROVED 拒绝

跨域读取（artifact / verification / release / exec 反查）**不在本域 import 实现** ——
按 SSoT R3/R5「服务域不许跨域直连，跨域走契约」，改由 `bind_lookups()` 注入，
装配是 bootstrap 的职责。未注入 → **拒绝动作（fail-closed）**，绝不静默降级成
"没校验就算通过"（那等于放行未验证产品）。
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_lock = threading.RLock()

PENDING = "PENDING"
APPROVED = "APPROVED"
CHANGE_REQUESTED = "CHANGE_REQUESTED"
SUPERSEDED = "SUPERSEDED"

_VALID = {PENDING, APPROVED, CHANGE_REQUESTED, SUPERSEDED}
_TRANSITIONS = {
    PENDING: {APPROVED, CHANGE_REQUESTED, SUPERSEDED},
    APPROVED: {CHANGE_REQUESTED, SUPERSEDED},   # 批准后仍可改（旧批准失效）
    CHANGE_REQUESTED: {SUPERSEDED},
    SUPERSEDED: set(),
}

#: 跨域查询钩子（由 bootstrap 注入；不注入 = 该校验跳过）
Lookup = Callable[[Path | str, str], Optional[dict[str, Any]]]
_hooks: dict[str, Callable[..., Any]] = {}


class _NoLookup:
    """哨兵：校验器未注入（≠ 查不到）。如实区分「没校验」与「校验失败」。"""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - 仅调试
        return "<no-lookup>"


NO_LOOKUP = _NoLookup()


def bind_lookups(*, artifact: Lookup | None = None, verification: Lookup | None = None,
                 release_creator: Callable[..., dict[str, Any]] | None = None,
                 release_gate: Callable[..., dict[str, Any]] | None = None,
                 exec_exs_lookup: Lookup | None = None) -> None:
    """注入跨域查询/动作（bootstrap 装配时调用；传 None 的项保持不变）。"""
    for key, fn in (("artifact", artifact), ("verification", verification),
                    ("release_creator", release_creator), ("release_gate", release_gate),
                    ("exec_exs_lookup", exec_exs_lookup)):
        if fn is not None:
            _hooks[key] = fn


def _query(kind: str, root: Path | str, key: str) -> Any:
    fn = _hooks.get(kind)
    return NO_LOOKUP if fn is None else fn(root, key)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file(root: Path | str) -> Path:
    return Path(root) / "acceptance" / "acceptance.json"


def _load(root: Path | str) -> dict[str, dict[str, Any]]:
    p = _file(root)
    try:
        import json

        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items() if isinstance(v, dict)}
    except Exception:  # noqa: BLE001 — 缺失/损坏 → 空（诚实空态）
        pass
    return {}


def _save(root: Path | str, data: dict[str, dict[str, Any]]) -> None:
    import json

    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")          # 原子写：临时名后 replace
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def _active_for_artifact(root: Path | str, artifact_id: str, version: int
                         ) -> Optional[dict[str, Any]]:
    """该 artifact+version 的当前 active acceptance（非 SUPERSEDED）。"""
    for acc in _load(root).values():
        if (str(acc.get("artifact_id") or "") == artifact_id
                and int(acc.get("version") or 0) == int(version)
                and str(acc.get("status") or "") != SUPERSEDED):
            return acc
    return None


# ------------------------------------------------------------------ 读

def get_acceptance(root: Path | str, acceptance_id: str) -> Optional[dict[str, Any]]:
    return _load(root).get(acceptance_id)


def list_acceptances(root: Path | str, *, artifact_id: str = "",
                     status: str = "") -> list[dict[str, Any]]:
    recs = _load(root)
    return sorted(
        (r for r in recs.values()
         if (not artifact_id or str(r.get("artifact_id") or "") == artifact_id)
         and (not status or str(r.get("status") or "") == status)),
        key=lambda r: str(r.get("created_at") or ""))


# ------------------------------------------------------------------ 创建

def begin_acceptance(root: Path | str, *, artifact_id: str, version: int = 1,
                     verification_id: str = "", source_run_id: str = "",
                     project_id: str = "", actor: str = "system") -> dict[str, Any]:
    """Artifact 完成 + ver 结果 → PENDING Acceptance（幂等：同 art+ver 已有 active → 返回现有）。"""
    art = _query("artifact", root, artifact_id)
    if art is NO_LOOKUP:
        raise ValueError("artifact 校验未接线（bootstrap 未注入 lookup）— 拒绝建验收 (fail-closed)")
    if art is None:
        raise ValueError(f"Artifact 不存在: {artifact_id} (acceptance 必须绑定真实 artifact)")
    if verification_id:
        v = _query("verification", root, verification_id)
        if v is NO_LOOKUP:
            raise ValueError("verification 校验未接线 — 拒绝建验收 (fail-closed)")
        if v is None:
            raise ValueError(f"Verification 不存在: {verification_id}")
    with _lock:
        acc = _active_for_artifact(root, artifact_id, version)
        if acc is not None:
            return acc                                     # 幂等
        recs = _load(root)
        aid = f"ACC-{uuid.uuid4().hex[:8]}"
        now = _now_iso()
        rec = {
            "acceptance_id": aid,
            "project_id": str(project_id or ""),
            "artifact_id": artifact_id,
            "version": int(version),
            "verification_id": verification_id,
            "source_run_id": str(source_run_id or ""),
            "status": PENDING,
            "reviewer": "",
            "decision": None,
            "created_at": now,
            "updated_at": now,
            "history": [{"to": PENDING, "at": now, "actor": actor, "note": "created"}],
        }
        recs[aid] = rec
        _save(root, recs)
        return rec


# ------------------------------------------------------------------ 用户决策

def approve(root: Path | str, acceptance_id: str, *, reviewer: str = "user",
            comment: str = "") -> dict[str, Any]:
    """用户 Approve → APPROVED（幂等）。gate: ver 必须 PASS。"""
    if not reviewer:
        raise ValueError("reviewer required")
    with _lock:
        recs = _load(root)
        acc = recs.get(acceptance_id)
        if acc is None:
            raise KeyError(f"Acceptance 不存在: {acceptance_id}")
        if str(acc.get("status") or "") == APPROVED:
            return acc                                     # 幂等 approve
        frm = str(acc.get("status") or "")
        if frm not in _TRANSITIONS or APPROVED not in _TRANSITIONS[frm]:
            raise ValueError(f"非法转换: {frm} → APPROVED")
        vid = str(acc.get("verification_id") or "")
        if vid:
            v = _query("verification", root, vid)
            if v is NO_LOOKUP:
                raise ValueError(
                    f"ver {vid} 校验未接线 — 拒绝批准未验证产品 (fail-closed)")
            if v is None or str(v.get("status") or "") != "PASS":
                raise ValueError(
                    f"Acceptance {acceptance_id} 的 ver {vid} 非 PASS — 不能批准未验证产品")
        acc["status"] = APPROVED
        acc["reviewer"] = reviewer
        acc["decision"] = {"decision": APPROVED, "comment": str(comment or "")[:500],
                           "at": _now_iso()}
        acc["updated_at"] = _now_iso()
        acc["history"].append({"to": APPROVED, "at": _now_iso(), "actor": reviewer,
                               "note": str(comment or "")[:200]})
        _save(root, recs)
        return acc


def request_change(root: Path | str, acceptance_id: str, *, comment: str,
                   reviewer: str = "user") -> dict[str, Any]:
    """用户 Request Change → CHANGE_REQUESTED（真实生产动作由调用方经 workflow 触发）。"""
    if not comment or not str(comment).strip():
        raise ValueError("change comment required")
    with _lock:
        recs = _load(root)
        acc = recs.get(acceptance_id)
        if acc is None:
            raise KeyError(f"Acceptance 不存在: {acceptance_id}")
        frm = str(acc.get("status") or "")
        if frm == CHANGE_REQUESTED:                        # 幂等：同 comment 不重复建
            d = acc.get("decision") or {}
            if str(d.get("comment") or "") == str(comment).strip():
                return acc
        if frm not in _TRANSITIONS or CHANGE_REQUESTED not in _TRANSITIONS[frm]:
            raise ValueError(f"非法转换: {frm} → CHANGE_REQUESTED")
        acc["status"] = CHANGE_REQUESTED
        acc["reviewer"] = reviewer
        acc["decision"] = {"decision": CHANGE_REQUESTED,
                           "comment": str(comment).strip()[:500], "at": _now_iso()}
        acc["updated_at"] = _now_iso()
        acc["history"].append({"to": CHANGE_REQUESTED, "at": _now_iso(), "actor": reviewer,
                               "note": f"change: {str(comment)[:120]}"})
        _save(root, recs)
        return acc


def supersede_older(root: Path | str, artifact_id: str, keep_version: int,
                    actor: str = "system") -> None:
    """新版本 cycle 建立后：旧版本 acceptance → SUPERSEDED（不删历史）。"""
    with _lock:
        recs = _load(root)
        changed = False
        for acc in recs.values():
            if (str(acc.get("artifact_id") or "") == artifact_id
                    and int(acc.get("version") or 0) != int(keep_version)
                    and str(acc.get("status") or "") in (PENDING, APPROVED, CHANGE_REQUESTED)):
                acc["status"] = SUPERSEDED
                acc["updated_at"] = _now_iso()
                acc["history"].append({"to": SUPERSEDED, "at": _now_iso(),
                                       "actor": actor, "note": f"v{keep_version} cycle"})
                changed = True
        if changed:
            _save(root, recs)


# ------------------------------------------------------------------ 交付门（跨域经钩子）

def acceptance_status_for_release(root: Path | str, artifact_ids: list[str]
                                  ) -> dict[str, Any]:
    """Release gate 查询：每个 artifact 须有 APPROVED acceptance。

    返回 {allowed: bool, missing: [...]}。
    """
    missing: list[str] = []
    for aid in artifact_ids or []:
        ok = [a for a in list_acceptances(root, artifact_id=aid)
              if str(a.get("status") or "") == APPROVED]
        if not ok:
            missing.append(f"acceptance_not_approved:{aid}")
    return {"allowed": not missing, "missing": missing}


def create_release_for_acceptance(root: Path | str, acceptance_id: str) -> dict[str, Any]:
    """由已 APPROVED 的验收创建 canonical Release 并过 gate（原 42 行端点逻辑）。

    跨域动作经钩子（release_creator / release_gate / exec_exs_lookup）——
    未注入 → 报"未接线"，**不假装成功**。
    """
    acc = get_acceptance(root, acceptance_id)
    if acc is None:
        raise KeyError(f"Acceptance 不存在: {acceptance_id}")
    if str(acc.get("status") or "") != APPROVED:
        raise ValueError("仅 APPROVED 验收可创建 Release")
    run_id = str(acc.get("source_run_id") or "")
    if not run_id:
        raise ValueError("Acceptance 缺 source_run 绑定 (无法建 canonical Release)")

    # 从 run 反查 canonical EXS（release gate 要求 exs provenance）
    exs_id = ""
    exs = _query("exec_exs_lookup", root, run_id)
    if exs is not NO_LOOKUP and exs:
        exs_id = str(exs.get("result_id") or "") if isinstance(exs, dict) else str(exs)

    creator, gate = _hooks.get("release_creator"), _hooks.get("release_gate")
    if creator is None or gate is None:
        raise RuntimeError("release 跨域动作未接线（bind_lookups 未注入 release_creator/release_gate）")
    rel = creator(root, run_id, exs_id)
    rel_id = str(rel.get("release_id") or "")
    g = gate(root, rel_id, True)
    return {"release": g, "gate": g.get("gate") or {}, "release_id": rel_id}
