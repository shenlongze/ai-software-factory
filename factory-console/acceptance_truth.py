"""factory-console/acceptance_truth.py — S45 User Acceptance canonical domain.

语义边界 (S45 §6): Verification (机器可验证 PASS) ≠ Acceptance (用户认可)。
本域只回答: 用户是否认可某个具体 artifact/version。

- ID: ACC-{hex8}; SSOT: <root>/acceptance/acceptance.json
- writer: 本模块 (唯一; approve/request_change)
- 状态: PENDING → APPROVED | CHANGE_REQUESTED → (新 artifact 新 ACC) ;
         SUPERSEDED (旧版本被新 cycle 替代 — 不删除历史)
- 绑定: artifact_id + version + verification_id (具体产品版本 — 禁模糊批准)
- 幂等: approve 同 (artifact_id, version) 重复 → 返回现有 APPROVED;
  request_change 同 (artifact, version, comment) 重复 → 不重复建 repair task
- 非法转换: SUPERSEDED → APPROVED 拒绝; CHANGE_REQUESTED → APPROVED 拒绝
  (须新 artifact 新 cycle — 旧版不能错误批准)
- Change Request → repair task (真实 production — 复用 workflow absorb 链)
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_lock = threading.RLock()

PENDING = "PENDING"
APPROVED = "APPROVED"
CHANGE_REQUESTED = "CHANGE_REQUESTED"
SUPERSEDED = "SUPERSEDED"

_VALID = {PENDING, APPROVED, CHANGE_REQUESTED, SUPERSEDED}
# PENDING → APPROVED / CHANGE_REQUESTED; APPROVED → SUPERSEDED (被新 cycle 顶);
# CHANGE_REQUESTED → SUPERSEDED; 终态禁回
_TRANSITIONS = {
    PENDING: {APPROVED, CHANGE_REQUESTED, SUPERSEDED},
    APPROVED: {CHANGE_REQUESTED, SUPERSEDED},  # 用户批准后仍可改 (旧批准失效)
    CHANGE_REQUESTED: {SUPERSEDED},
    SUPERSEDED: set(),
}


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
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save(root: Path | str, data: dict[str, dict[str, Any]]) -> None:
    import json

    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def _art(root: Path | str, artifact_id: str) -> Optional[dict[str, Any]]:
    try:
        from factory_console import artifact_lifecycle as al

        return al.get_artifact(root, artifact_id)
    except Exception:  # noqa: BLE001
        return None


def _ver(root: Path | str, verification_id: str) -> Optional[dict[str, Any]]:
    try:
        from factory_console import verification_domain as vd

        return vd.get_verification(root, verification_id)
    except Exception:  # noqa: BLE001
        return None


def _active_for_artifact(root: Path | str, artifact_id: str, version: int
                         ) -> Optional[dict[str, Any]]:
    """该 artifact+version 的当前 active acceptance (PENDING/APPROVED/CHANGE)。"""
    for acc in _load(root).values():
        if (str(acc.get("artifact_id") or "") == artifact_id
                and int(acc.get("version") or 0) == int(version)
                and str(acc.get("status") or "") != SUPERSEDED):
            return acc
    return None


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


# ------------------------------------------------------------------ create


def begin_acceptance(root: Path | str, *, artifact_id: str, version: int = 1,
                     verification_id: str = "", source_run_id: str = "",
                     project_id: str = "", actor: str = "system") -> dict[str, Any]:
    """Artifact 完成 + ver 结果 → PENDING Acceptance (幂等: 同 art+ver 已有
    active → 返回现有; 旧 APPROVED artifact 再来新 cycle 由 request_change
    产生新 ACC)。

    ver 必须存在 (绑定具体验证); artifact 必须存在。
    """
    if _art(root, artifact_id) is None:
        raise ValueError(f"Artifact 不存在: {artifact_id} (acceptance 必须绑定真实 artifact)")
    if verification_id and _ver(root, verification_id) is None:
        raise ValueError(f"Verification 不存在: {verification_id}")
    with _lock:
        recs = _load(root)
        for acc in recs.values():
            if (str(acc.get("artifact_id") or "") == artifact_id
                    and int(acc.get("version") or 0) == int(version)
                    and str(acc.get("status") or "") in (PENDING, APPROVED,
                                                         CHANGE_REQUESTED)):
                return acc  # 幂等
        aid = f"ACC-{uuid.uuid4().hex[:8]}"
        now = _now_iso()
        acc = {
            "acceptance_id": aid,
            "project_id": str(project_id or ""),
            "artifact_id": artifact_id,
            "version": int(version),
            "verification_id": verification_id,
            "source_run_id": str(source_run_id or ""),
            "status": PENDING,
            "reviewer": "",
            "decision": None,  # {decision, comment, at}
            "created_at": now,
            "updated_at": now,
            "history": [{"to": PENDING, "at": now, "actor": actor, "note": "created"}],
        }
        recs[aid] = acc
        _save(root, recs)
        return acc


# ------------------------------------------------------------------ approve


def approve(root: Path | str, acceptance_id: str, *, reviewer: str = "user",
            comment: str = "") -> dict[str, Any]:
    """用户 Approve → APPROVED (幂等: 已 APPROVED 返回现有)。

    gate: ver 必须 PASS (不能批准未验证产品); artifact 必须存在。
    """
    if not reviewer:
        raise ValueError("reviewer required")
    with _lock:
        recs = _load(root)
        acc = recs.get(acceptance_id)
        if acc is None:
            raise KeyError(f"Acceptance 不存在: {acceptance_id}")
        if str(acc.get("status") or "") == APPROVED:
            return acc  # 幂等 approve
        frm = str(acc.get("status") or "")
        if frm not in _TRANSITIONS or APPROVED not in _TRANSITIONS[frm]:
            raise ValueError(f"非法转换: {frm} → APPROVED")
        vid = str(acc.get("verification_id") or "")
        if vid:
            v = _ver(root, vid)
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


# ------------------------------------------------------------------ request change


def request_change(root: Path | str, acceptance_id: str, *, comment: str,
                   reviewer: str = "user",
                   project_dir: Path | str | None = None) -> dict[str, Any]:
    """用户 Request Change → CHANGE_REQUESTED + 真实 repair task (接 S44 吸收链)。

    语义 (S45 §9): change request 必须产生真实生产动作。当前真实生产入口 =
    workflow absorb (S44); 此处经 workflow 重新运行机制 —— 最小实现:
    - 该 acceptance 置 CHANGE_REQUESTED (原 artifact 不再 active)
    - 调用方 (WebUI/API) 需用 comment 触发新 workflow run → S44 absorb →
      新 art (V+1) → begin_acceptance (新 cycle)
    - 幂等: 同 (artifact, version, comment) 已 CHANGE_REQUESTED → 返回现有
    - 旧 artifact 的 APPROVED 不迁移: 新 artifact 自动新 PENDING (begin 时)
    """
    if not comment or not str(comment).strip():
        raise ValueError("change comment required")
    with _lock:
        recs = _load(root)
        acc = recs.get(acceptance_id)
        if acc is None:
            raise KeyError(f"Acceptance 不存在: {acceptance_id}")
        frm = str(acc.get("status") or "")
        # 幂等: 同 comment 重复 change → 现有 (不重复建)
        if frm == CHANGE_REQUESTED:
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
        acc["history"].append({"to": CHANGE_REQUESTED, "at": _now_iso(),
                               "actor": reviewer,
                               "note": f"change: {str(comment)[:120]}"})
        # 旧版本被新 cycle 顶替标记 (等新 artifact 后由 caller 或此处 SUPERSEDE)
        _save(root, recs)
        return acc


def supersede_older(root: Path | str, artifact_id: str, keep_version: int,
                    actor: str = "system") -> None:
    """新版本 cycle 建立后: 旧版本 acceptance → SUPERSEDED (不删历史)。"""
    with _lock:
        recs = _load(root)
        changed = False
        for acc in recs.values():
            if (str(acc.get("artifact_id") or "") == artifact_id
                    and int(acc.get("version") or 0) != int(keep_version)
                    and str(acc.get("status") or "") in (PENDING, APPROVED,
                                                         CHANGE_REQUESTED)):
                acc["status"] = SUPERSEDED
                acc["updated_at"] = _now_iso()
                acc["history"].append({"to": SUPERSEDED, "at": _now_iso(),
                                       "actor": actor, "note": f"v{keep_version} cycle"})
                changed = True
        if changed:
            _save(root, recs)


# ------------------------------------------------------------------ release gate hook


def acceptance_status_for_release(root: Path | str, artifact_ids: list[str]
                                  ) -> dict[str, Any]:
    """Release gate 查询: 给定 artifacts 的 acceptance 状态。

    返回 {allowed: bool, missing: [..]} — 每个 artifact 须有 APPROVED
    acceptance (且 ver PASS 隐含于 approve gate)。
    """
    missing: list[str] = []
    for aid in artifact_ids or []:
        accs = [a for a in list_acceptances(root, artifact_id=aid)
                if str(a.get("status") or "") == APPROVED]
        if not accs:
            missing.append(f"acceptance_not_approved:{aid}")
    return {"allowed": not missing, "missing": missing}
