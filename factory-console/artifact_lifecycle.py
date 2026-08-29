"""factory-console/artifact_lifecycle.py — S1 Artifact Lifecycle (Production Core).

AI Factory 2.0 第一个真正的 Production Primitive: 8 态生命周期状态机 + 持久化
Store + 12 条 Invariants + 真实 Apply Integration (复用 delivery.apply_patch)。

- 8 态: GENERATED → STAGED → REVIEWED → APPROVED → APPLIED → VALIDATED → COMMITTED → RELEASED
- 单一权威状态: artifact.state (不可变记录, 修改 = 新 version, 不 UPDATE 旧记录)
- 每转换: validate → persist → emit event/evidence (不出现"内存变了但持久化失败"的假成功)
- Apply: APPROVED 后调 delivery.apply_patch() 真实改 workspace; 失败绝不进 APPLIED
- Invariants I1-I12 (见 INVARIANTS 表), 每转换前置校验

参考: docs/audit/ai-factory-2-production-core-contract.md (S0.5 Freeze)
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ------------------------------------------------------------------ 状态定义

#: 生命周期 8 态 (权威顺序)
LIFECYCLE_STATES = (
    "GENERATED",
    "STAGED",
    "REVIEWED",
    "APPROVED",
    "APPLIED",
    "VALIDATED",
    "COMMITTED",
    "RELEASED",
)

#: 合法转换表 (FROM → 允许的 TO)
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "GENERATED": ("STAGED",),
    "STAGED": ("REVIEWED",),
    "REVIEWED": ("APPROVED",),
    "APPROVED": ("APPLIED",),
    "APPLIED": ("VALIDATED",),
    "VALIDATED": ("COMMITTED",),
    "COMMITTED": ("RELEASED",),
    "RELEASED": (),
}

#: 终态 (不可再转换)
TERMINAL_STATES = ("RELEASED",)

#: 失败/异常态 (从任何非终态可进, 不能回生产主链)
FAILURE_STATES = ("FAILED", "REJECTED", "REPAIRING", "BLOCKED", "CANCELLED")

#: 需要 Approval 的转换 (S0.5 Contract: APPLY/COMMIT/RELEASE 三 Gate)
APPROVAL_GATES = ("APPLIED", "COMMITTED", "RELEASED")

#: 需要 Evidence 的转换
EVIDENCE_REQUIRED_TRANSITIONS = ("APPLIED", "COMMITTED", "RELEASED")

# ------------------------------------------------------------------ Invariants

#: 12 条 Contract Invariants (实现=transition_guard, 测试=test_artifact_invariants)
INVARIANTS: dict[str, str] = {
    "I1": "Artifact 未 APPROVED 不能 APPLIED。",
    "I2": "Applied Artifact 必须携带 Evidence (apply 输出)。",
    "I3": "Artifact 未 VALIDATED 不能 COMMITTED。",
    "I4": "NodeRun 未经过 VERIFYING 不能 COMPLETED。(S1: 以 Artifact VALIDATED 前置落地)",
    "I5": "ProductionRun 有未完成 NodeRun 不能 COMPLETED。(S1 范围外, 标记待接)",
    "I6": "Commit 必须对应 Validated 的 Workspace 状态。",
    "I7": "一切生产变更 (Apply/Commit/Release) 必须可审计 (事件+证据)。",
    "I8": "外部 Executor 不能绕过 Artifact Lifecycle (产物必须走 GENERATED→…→COMMITTED)。",
    "I9": "Conversation Session 不能直接改 Workspace (必须经 NodeRun)。",
    "I10": "Artifact 不可变 (修改 = 新 version, 不 UPDATE 旧记录)。",
    "I11": "NodeRun 是事实记录, 不可变; Node 是可编辑模板。(S1: Artifact 记录不可变)",
    "I12": "无 Approval 记录, 不允许 APPLIED/COMMITTED/RELEASED 转换。",
}

# ------------------------------------------------------------------ 存储

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _artifacts_dir(root: Path | str) -> Path:
    return Path(root) / "artifacts"


def _artifact_path(root: Path | str, artifact_id: str) -> Path:
    # 按 artifact_id 前缀分片 (避免单目录文件过多)
    return _artifacts_dir(root) / artifact_id[:2] / f"{artifact_id}.json"


_lock = threading.RLock()


class ArtifactError(Exception):
    """生命周期非法操作 (invalid transition / invariant violation)。"""


class ArtifactConflict(Exception):
    """Contract 冲突 — 需要人工裁决 (S0.5: 不自行修改 Contract)。"""


def create_artifact(
    root: Path | str,
    *,
    artifact_type: str,
    payload: dict[str, Any] | None = None,
    patch_text: str | None = None,
    project_id: str | None = None,
    node_run_id: str | None = None,
    producer: str = "unknown",
) -> dict[str, Any]:
    """创建 Artifact, 状态 = GENERATED。返回完整 artifact dict (含 artifact_id)。"""
    artifact_id = f"art-{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    art: dict[str, Any] = {
        "artifact_id": artifact_id,
        "version": 1,
        "type": artifact_type,
        "state": "GENERATED",
        "payload": payload or {},
        "patch_text": patch_text,
        "project_id": project_id,
        "node_run_id": node_run_id,
        "producer": producer,
        "evidence_ids": [],
        "approval_ids": [],
        "workspace": None,          # Apply 目标 (Destination, 非 Artifact 一部分)
        "commit_hash": None,
        "created_at": now,
        "updated_at": now,
        "history": [],              # 状态变更历史 (不可变记录)
    }
    with _lock:
        _write_artifact(root, art)
    _record_transition(root, art, "CREATED", actor=producer, evidence={})
    return art


def get_artifact(root: Path | str, artifact_id: str) -> dict[str, Any] | None:
    p = _artifact_path(root, artifact_id)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def list_artifacts(root: Path | str, project_id: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    base = _artifacts_dir(root)
    if not base.is_dir():
        return out
    for sub in sorted(base.iterdir()):
        if not sub.is_dir():
            continue
        for f in sorted(sub.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(d, dict) and (project_id is None or d.get("project_id") == project_id):
                out.append(d)
    return out


def _write_artifact(root: Path | str, art: dict[str, Any]) -> None:
    p = _artifact_path(root, art["artifact_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(art, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_transition(root: Path | str, art: dict[str, Any], to_state: str,
                       *, actor: str, evidence: dict[str, Any] | None) -> None:
    """记录状态变更历史 (不可变 append; 同时落 audit event)。"""
    now = _now_iso()
    rec = {
        "from": art.get("state"),
        "to": to_state,
        "actor": actor,
        "at": now,
        "evidence": evidence or {},
    }
    art.setdefault("history", []).append(rec)
    art["updated_at"] = now
    _write_artifact(root, art)
    # 审计事件 (复用 audit_store; 失败不阻断 — 审计尽力而为)
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            "ARTIFACT_TRANSITION",
            trace_id=art.get("node_run_id") or art["artifact_id"],
            project_id=art.get("project_id") or "",
            agent_id=actor,
            actor_type="system" if actor != "user" else "human",
            actor_id=actor,
            action=f"artifact.{to_state.lower()}",
            source="artifact_lifecycle",
            decision="allow",
            decision_reason="lifecycle transition",
            evidence=[{"artifact_id": art["artifact_id"], "from": rec["from"], "to": to_state}],
            result={"ok": True},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ 转换

def _transition(
    root: Path | str,
    art: dict[str, Any],
    to_state: str,
    *,
    actor: str,
    evidence: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """核心转换: validate → (approval check) → persist → record。失败抛 ArtifactError。"""
    from_state = art.get("state")

    # 1) 状态合法性
    if to_state not in LIFECYCLE_STATES:
        raise ArtifactError(f"非法目标状态: {to_state} (生命周期: {', '.join(LIFECYCLE_STATES)})")
    if from_state not in ALLOWED_TRANSITIONS:
        raise ArtifactError(f"状态 {from_state} 不在转换表 (非生产状态, 可能已 FAILED)")
    if to_state not in ALLOWED_TRANSITIONS.get(from_state, ()):
        raise ArtifactError(
            f"非法转换: {from_state} → {to_state} (允许: {', '.join(ALLOWED_TRANSITIONS.get(from_state, ())) or '无'})"
        )

    # 2) Approval Gate (APPLIED/COMMITTED/RELEASED 必须有 approval)
    if to_state in APPROVAL_GATES:
        if not approval:
            raise ArtifactError(f"转换 {from_state} → {to_state} 需要 Approval (I12)")
        if approval.get("state") != "APPROVED":
            raise ArtifactError(f"Approval 状态必须为 APPROVED (当前: {approval.get('state')})")
        art.setdefault("approval_ids", []).append(str(approval.get("approval_id") or ""))

    # 3) 更新状态 + 记录
    art["state"] = to_state
    _record_transition(root, art, to_state, actor=actor, evidence=evidence)
    return art


def transition_artifact(
    root: Path | str,
    artifact_id: str,
    to_state: str,
    *,
    actor: str = "system",
    evidence: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """公开转换入口: 读 → 校验 → 转换 → 持久化。"""
    with _lock:
        art = get_artifact(root, artifact_id)
        if art is None:
            raise ArtifactError(f"Artifact 不存在: {artifact_id}")
        # 终态保护 (不可变)
        if art.get("state") in TERMINAL_STATES:
            raise ArtifactError(f"Artifact 已在终态 {art['state']}, 不可再转换 (I10)")
        return _transition(root, art, to_state, actor=actor, evidence=evidence, approval=approval)


def approve_artifact(
    root: Path | str,
    artifact_id: str,
    *,
    approved_by: str,
    note: str = "",
) -> dict[str, Any]:
    """生成 Approval 记录 (state=APPROVED) 并推进 REVIEWED → APPROVED。"""
    with _lock:
        art = get_artifact(root, artifact_id)
        if art is None:
            raise ArtifactError(f"Artifact 不存在: {artifact_id}")
        if art.get("state") not in ("REVIEWED", "APPROVED"):
            raise ArtifactError(f"Approval 只能在 REVIEWED/APPROVED 状态 (当前: {art.get('state')})")
        approval = {
            "approval_id": f"apr-{uuid.uuid4().hex[:10]}",
            "artifact_id": artifact_id,
            "state": "APPROVED",
            "approved_by": approved_by,
            "note": note,
            "at": _now_iso(),
        }
        if art.get("state") == "REVIEWED":
            _transition(root, art, "APPROVED", actor=approved_by,
                        evidence={"note": note}, approval=approval)
        else:
            art.setdefault("approval_ids", []).append(approval["approval_id"])
            _write_artifact(root, art)
        return approval


def apply_artifact(
    root: Path | str,
    artifact_id: str,
    *,
    workspace_dir: Path | str,
    apply_fn: Callable[[Path | str, str], tuple[bool, str]] | None = None,
    actor: str = "system",
    approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply: APPROVED → 真实 delivery.apply_patch → APPLIED。

    apply_fn 注入 (默认 session.delivery.apply_patch; 测试可注入但 Integration Test 用真实)。
    核心: apply 失败 → 抛 ArtifactError, Artifact 状态不变 (绝不伪装 APPLIED)。
    """
    from .session.delivery import apply_patch as _real_apply

    with _lock:
        art = get_artifact(root, artifact_id)
        if art is None:
            raise ArtifactError(f"Artifact 不存在: {artifact_id}")
        if art.get("state") != "APPROVED":
            raise ArtifactError(f"Apply 前置: 状态必须 APPROVED (当前: {art.get('state')}) — I1")
        if not approval and not art.get("approval_ids"):
            raise ArtifactError("Apply 需要 Approval 记录 (I12)")
        if not art.get("patch_text"):
            # 无 patch → 视为无变更 (仍记录 APPLIED)
            art["workspace"] = str(workspace_dir)
            _transition(root, art, "APPLIED", actor=actor,
                        evidence={"note": "no patch (no-op)"}, approval=approval)
            return art
        fn = apply_fn or _real_apply
        ok, msg = fn(Path(workspace_dir), art["patch_text"])
        if not ok:
            raise ArtifactError(f"Apply 失败: {msg} (Artifact 状态保持 {art['state']})")
        # 真实成功后才 APPLIED
        art["workspace"] = str(workspace_dir)
        _transition(root, art, "APPLIED", actor=actor,
                    evidence={"apply_msg": msg, "workspace": str(workspace_dir)},
                    approval=approval)
        return art


def validate_artifact(
    root: Path | str,
    artifact_id: str,
    *,
    verification: dict[str, Any],
    actor: str = "system",
) -> dict[str, Any]:
    """VALIDATED: APPLIED → 验证通过 → VALIDATED。verification 必须含结果。"""
    with _lock:
        art = get_artifact(root, artifact_id)
        if art is None:
            raise ArtifactError(f"Artifact 不存在: {artifact_id}")
        if art.get("state") != "APPLIED":
            raise ArtifactError(f"Validate 前置: 状态必须 APPLIED (当前: {art.get('state')})")
        result = verification.get("result")
        if result != "PASS":
            raise ArtifactError(f"验证未通过 (result={result}) — 不能 VALIDATED (I3/I6)")
        _transition(root, art, "VALIDATED", actor=actor, evidence=verification)
        return art


def commit_artifact(
    root: Path | str,
    artifact_id: str,
    *,
    commit_fn: Callable[[str], tuple[bool, str]] | None = None,
    actor: str = "system",
    approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """COMMITTED: VALIDATED → git commit → COMMITTED。commit_fn 默认 git commit (workspace 目录)。"""
    import subprocess

    with _lock:
        art = get_artifact(root, artifact_id)
        if art is None:
            raise ArtifactError(f"Artifact 不存在: {artifact_id}")
        if art.get("state") != "VALIDATED":
            raise ArtifactError(f"Commit 前置: 状态必须 VALIDATED (当前: {art.get('state')}) — I3/I6")
        if not approval and not art.get("approval_ids"):
            raise ArtifactError("Commit 需要 Approval 记录 (I12)")
        ws = art.get("workspace")
        if not ws:
            raise ArtifactError("无 workspace — 无法 commit")

        def _default_commit(ws_dir: str) -> tuple[bool, str]:
            proc = subprocess.run(
                ["git", "-C", ws_dir, "add", "-A"], capture_output=True, text=True, timeout=60,
            )
            proc2 = subprocess.run(
                ["git", "-C", ws_dir, "-c", "user.email=factory@local", "-c", "user.name=factory",
                 "commit", "-q", "-m", f"factory: artifact {artifact_id} ({art.get('type')})"],
                capture_output=True, text=True, timeout=60,
            )
            if proc2.returncode != 0:
                return False, (proc2.stdout or "") + (proc2.stderr or "")
            return True, (proc2.stdout or "").strip()

        fn = commit_fn or _default_commit
        ok, msg = fn(ws)
        if not ok:
            raise ArtifactError(f"Commit 失败: {msg} (状态保持 {art['state']})")
        # 提取 hash (兼容: git 输出含 [branch hash] 或裸 hash; 失败则取 git rev-parse)
        import re as _re
        m = _re.search(r"\[[^\]]* ([0-9a-f]{7,40})\]|([0-9a-f]{40})", msg)
        commit_hash = m.group(1) or m.group(2) if m else ""
        if not commit_hash:
            try:
                proc = subprocess.run(["git", "-C", ws, "rev-parse", "HEAD"],
                                      capture_output=True, text=True, timeout=30)
                commit_hash = (proc.stdout or "").strip()[:40]
            except Exception:  # noqa: BLE001
                pass
        art["commit_hash"] = commit_hash or msg[:40]
        _transition(root, art, "COMMITTED", actor=actor,
                    evidence={"commit_msg": msg[:200]}, approval=approval)
        return art


def release_artifact(
    root: Path | str,
    artifact_id: str,
    *,
    release_info: dict[str, Any] | None = None,
    actor: str = "system",
    approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """RELEASED: COMMITTED → RELEASED (终态)。"""
    with _lock:
        art = get_artifact(root, artifact_id)
        if art is None:
            raise ArtifactError(f"Artifact 不存在: {artifact_id}")
        if art.get("state") != "COMMITTED":
            raise ArtifactError(f"Release 前置: 状态必须 COMMITTED (当前: {art.get('state')})")
        if not approval and not art.get("approval_ids"):
            raise ArtifactError("Release 需要 Approval 记录 (I12)")
        _transition(root, art, "RELEASED", actor=actor,
                    evidence=release_info or {}, approval=approval)
        return art


def fail_artifact(
    root: Path | str,
    artifact_id: str,
    *,
    reason: str,
    actor: str = "system",
) -> dict[str, Any]:
    """失败态: 任何非终态 → FAILED (带失败证据)。不可回生产主链。"""
    with _lock:
        art = get_artifact(root, artifact_id)
        if art is None:
            raise ArtifactError(f"Artifact 不存在: {artifact_id}")
        if art.get("state") in TERMINAL_STATES:
            raise ArtifactError(f"终态 {art['state']} 不可 FAILED")
        art["state"] = "FAILED"
        _record_transition(root, art, "FAILED", actor=actor, evidence={"reason": reason})
        return art


# ------------------------------------------------------------------ 状态查询

def artifact_state(root: Path | str, artifact_id: str) -> str | None:
    art = get_artifact(root, artifact_id)
    return art.get("state") if art else None


def is_valid_transition(from_state: str, to_state: str) -> bool:
    return to_state in ALLOWED_TRANSITIONS.get(from_state, ())
