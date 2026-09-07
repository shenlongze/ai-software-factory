"""factory-console/node_runtime.py — S2 Node Runtime (Production Primitive #2).

AI Factory 2.0 第二个 Production Primitive: Node 定义 + NodeRun 执行事实。

- Node: 可复用生产模板 (node_id/input_contract/output_contract/execution_policy)
- NodeRun: Node 的一次不可变执行事实 (状态机 PENDING→RUNNING→VERIFYING→COMPLETED/FAILED)
- Executor Contract: 复用 external_executor (execute/collect), 不新建体系
- Artifact: NodeRun 产出 → 交给 S1 Artifact Lifecycle (NodeRun 不直接改 Workspace)
- Verification: PASS/FAIL/INCONCLUSIVE/BLOCKED (S0.5 四态, 不发明第五种)

架构 Invariants (S2):
- Node 只依赖 Executor Contract, 不依赖 Claude/Codex/Hermes 具体实现
- NodeRun 不允许直接修改 Workspace (必须走 Artifact Lifecycle)
- Conversation Session 不能直接修改 Workspace (经 Node)
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ------------------------------------------------------------------ 状态

#: NodeRun 生命周期 (含 E1 WAITING_FOR_USER / REPAIRING)
NODERUN_STATES = ("PENDING", "RUNNING", "VERIFYING", "REPAIRING",
                  "WAITING_FOR_USER", "COMPLETED", "FAILED")

#: 合法转换
NODERUN_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "PENDING": ("RUNNING", "FAILED"),
    "RUNNING": ("VERIFYING", "FAILED", "WAITING_FOR_USER", "REPAIRING"),
    "VERIFYING": ("COMPLETED", "FAILED", "RUNNING"),  # INCONCLUSIVE → 续跑
    "REPAIRING": ("RUNNING", "FAILED"),
    "WAITING_FOR_USER": ("RUNNING", "FAILED"),  # 人类决策/输入到达 → resume
    "COMPLETED": (),
    "FAILED": (),
}

#: Verification 四态 (S0.5 Contract)
VERIFY_RESULTS = ("PASS", "FAIL", "INCONCLUSIVE", "BLOCKED")


class NodeError(Exception):
    """Node/NodeRun 非法操作。"""


# ------------------------------------------------------------------ 存储

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _nodes_dir(root: Path | str) -> Path:
    return Path(root) / "nodes"


def _node_def_path(root: Path | str, node_id: str) -> Path:
    return _nodes_dir(root) / "definitions" / f"{node_id}.json"


def _run_path(root: Path | str, run_id: str) -> Path:
    return _nodes_dir(root) / "runs" / f"{run_id}.json"


_lock = threading.RLock()


# ------------------------------------------------------------------ Node (定义/模板)

def register_node(
    root: Path | str,
    *,
    node_id: str,
    name: str,
    node_type: str,
    input_contract: dict[str, Any] | None = None,
    output_contract: dict[str, Any] | None = None,
    execution_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """注册/更新 Node 定义 (可复用模板, 持久化)。"""
    node: dict[str, Any] = {
        "node_id": node_id,
        "name": name,
        "type": node_type,
        "input_contract": input_contract or {},
        "output_contract": output_contract or {},
        "execution_policy": execution_policy or {},
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    with _lock:
        p = _node_def_path(root, node_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(node, ensure_ascii=False, indent=2), encoding="utf-8")
    return node


def get_node(root: Path | str, node_id: str) -> dict[str, Any] | None:
    p = _node_def_path(root, node_id)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def list_nodes(root: Path | str) -> list[dict[str, Any]]:
    base = _nodes_dir(root) / "definitions"
    if not base.is_dir():
        return []
    out = []
    for f in sorted(base.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                out.append(d)
        except (OSError, ValueError):
            continue
    return out


# ------------------------------------------------------------------ NodeRun (执行事实)

def create_node_run(
    root: Path | str,
    node_id: str,
    *,
    input_data: dict[str, Any] | None = None,
    trigger: str = "user",
    task_id: str = "",  # P0-F1: TaskRun 锚定 backlog Task (TASK-*); 空 = 未锚 (冒烟/独立)
    project_id: str = "",  # Node Loop 泛化: 产品节点锚定项目 (active_run 过滤)
) -> dict[str, Any]:
    """实例化 NodeRun: PENDING。NodeRun 是事实记录 (不可变: state 转换 append 而非覆写)。

    task_id: 本 TaskRun 对应的 canonical backlog Task (TASK-*)。默认空 — 兼容
    既有 S2/S3 workflow 调用 (不锚 backlog 的独立执行); F0 契约: TaskRun.task_id → Task。
    """
    node = get_node(root, node_id)
    if node is None:
        raise NodeError(f"Node 不存在: {node_id} (请先 register_node)")
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    run: dict[str, Any] = {
        "run_id": run_id,
        "node_id": node_id,
        "task_id": str(task_id or ""),  # P0-F1: TaskRun → Task 锚 (显式持久化, 非派生)
        "project_id": str(project_id or ""),  # Node Loop 泛化
        "state": "PENDING",
        "input": input_data or {},
        "trigger": trigger,
        "executor": None,
        "agent": None,
        "model": None,
        "artifact_id": None,
        "verification": None,
        "failure_reason": None,
        "started_at": None,
        "completed_at": None,
        "created_at": _now_iso(),
        "history": [],   # 状态变更事实 (append-only)
        "decisions": [],  # E1: Human Decision 事实
        "checkpoint": None,  # E2: 进度事实 (resume)
    }
    with _lock:
        _write_run(root, run)
    _record(root, run, "PENDING", actor="system", note="created")
    return run


def get_node_run(root: Path | str, run_id: str) -> dict[str, Any] | None:
    p = _run_path(root, run_id)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def list_node_runs(root: Path | str, node_id: str | None = None) -> list[dict[str, Any]]:
    base = _nodes_dir(root) / "runs"
    if not base.is_dir():
        return []
    out = []
    for f in sorted(base.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(d, dict) and (node_id is None or d.get("node_id") == node_id):
                out.append(d)
        except (OSError, ValueError):
            continue
    return out


def _write_run(root: Path | str, run: dict[str, Any]) -> None:
    p = _run_path(root, run["run_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")


def _record(root: Path | str, run: dict[str, Any], to_state: str, *, actor: str, note: str) -> None:
    """状态变更事实 (append-only history + audit event)。"""
    run["history"].append({
        "from": run.get("state"),
        "to": to_state,
        "actor": actor,
        "at": _now_iso(),
        "note": note,
    })
    run["state"] = to_state
    _write_run(root, run)
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            f"NODE_RUN_{to_state}",
            trace_id=run["run_id"],
            project_id="",
            agent_id=actor,
            actor_type="system",
            actor_id=actor,
            action=f"noderun.{to_state.lower()}",
            source="node_runtime",
            decision="allow",
            decision_reason="node run transition",
            evidence=[{"run_id": run["run_id"], "node_id": run["node_id"], "note": note}],
            result={"ok": True},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001 — 审计尽力而为
        pass


def transition_node_run(
    root: Path | str,
    run_id: str,
    to_state: str,
    *,
    actor: str = "system",
    note: str = "",
) -> dict[str, Any]:
    """状态转换: 校验合法 → 记录。非法跳转抛 NodeError。"""
    with _lock:
        run = get_node_run(root, run_id)
        if run is None:
            raise NodeError(f"NodeRun 不存在: {run_id}")
        frm = run.get("state")
        if to_state not in NODERUN_TRANSITIONS.get(frm, ()):
            raise NodeError(f"非法 NodeRun 转换: {frm} → {to_state}")
        _record(root, run, to_state, actor=actor, note=note)
        return run


def _absorb_execution_artifact(
    root: Path | str,
    run_id: str,
    *,
    exs_id: str,
    output: str = "",
    artifact_root: Path | str,
    actor: str = "execution",
) -> dict[str, Any] | None:
    """P0-F4 (I8): 执行成功 → 收纳产物为 canonical art-* (生产 contract 内)。

    产物形态: EXS 执行输出 (output 文本) → artifact type="report" (execution
    output snapshot; 真实产物内容, 非伪造)。挂 node_run_id + exs_id。
    幂等: create_artifact 的 exs_id 幂等键保证同 EXS+type → 同 art-*。
    失败安全: 收纳失败 → 返回 None (不阻断 run 终态); 绝不事后补登记。
    """
    try:
        try:
            from .artifact_lifecycle import create_artifact  # 包内
        except ImportError:  # 兼容直接 import (sys.path 模式)
            from artifact_lifecycle import create_artifact  # type: ignore

        if not exs_id:
            return None  # 无 EXS → 无 I8 收纳 (workflow 域走 execute_node_run 路径)
        return create_artifact(
            artifact_root,
            artifact_type="report",
            payload={"source": "external_execution", "run_id": run_id,
                     "exs_id": exs_id, "output_tail": str(output or "")[-2000:]},
            project_id=None,
            node_run_id=run_id,
            exs_id=exs_id,
            producer=str(actor or "execution"),
        )
    except Exception:  # noqa: BLE001 — 失败安全: 收纳失败不阻断 run 终态
        return None


def _materialize_verify(
    root: Path | str,
    run_id: str,
    verify_meta: dict[str, Any],
    *,
    ok: bool,
    actor: str = "verification",
    exs_id: str = "",
    attempt: int = 0,
    artifact_ids: list[str] | None = None,  # P0-F4: 被本验证检查的 canonical art-*
) -> dict[str, Any]:
    """P0-F3: verify metadata → ver-* SSOT 物化 (方案 1 — run 存引用, canonical 在 store)。

    输入 verify_meta: gateway/executor 返回的 {method, result: pass|fail|unknown|PASS|FAIL, ...}。
    映射:
      result in (pass, PASS)       → status PASS
      result in (fail, FAIL)       → status FAIL
      result in (unknown, ...)     → status UNKNOWN (诚实 — 无验证 ≠ PASS)
      ok=True + 无 verify_meta     → UNKNOWN (不可把缺省当 PASS)
      ok=False                     → FAIL (执行失败 = 验证失败语义, 与 run 终态一致)
    返回 run.verification 引用 dict {verification_id, status, method} (精简快照 +
    canonical id — 完整事实在 verifications store; 禁止第二事实源)。
    """
    try:
        try:
            from .verification_domain import materialize_verification  # 包内
        except ImportError:  # 兼容直接 import (sys.path 模式)
            from verification_domain import materialize_verification  # type: ignore

        raw_result = str((verify_meta or {}).get("result")
                         or (verify_meta or {}).get("status") or "").strip().lower()
        method = str((verify_meta or {}).get("method") or "")
        if not ok:
            status = "FAIL"
        elif raw_result in ("pass",):
            status = "PASS"
        elif raw_result in ("fail",):
            status = "FAIL"
        elif raw_result in ("unknown", "inconclusive", "blocked", "none"):
            status = "UNKNOWN"
        else:
            status = "UNKNOWN"  # 缺省/无验证 → UNKNOWN (禁止默认 PASS)
        rec = materialize_verification(
            root,
            task_run_id=run_id,
            exs_id=exs_id,
            status=status,
            verification_type="task_run_execution",
            method=method,
            result=str((verify_meta or {}).get("reason") or ""),
            detail={"source_meta": {k: v for k, v in (verify_meta or {}).items()
                                    if k in ("score", "reason", "source")}},
            attempt=attempt,
            actor=actor,
            note="materialized from execution verify metadata",
            artifact_ids=artifact_ids or [],
        )
        return {"verification_id": str(rec.get("verification_id") or ""),
                "status": str(rec.get("status") or ""),
                "method": method}
    except Exception:  # noqa: BLE001 — 物化失败 → 失败安全返回空引用 (不阻断 run 终态)
        return {"verification_id": "", "status": "UNKNOWN" if ok else "FAIL", "method": ""}


def _attach_verify_evidence(
    root: Path | str,
    verification_id: str,
    *,
    verify_meta: dict[str, Any],
    actor: str = "verification",
) -> dict[str, Any] | None:
    """P0-F4: 真实 verifier 输出 → EVD-* Evidence (支撑 Verification 结论)。

    仅当 verify_meta 含真实证据 (method + 输出/错误/reason) 时物化 —
    禁止 "verification passed" 无内容伪造 EVD。失败安全 (不阻断)。
    """
    try:
        try:
            from .evidence_domain import materialize_evidence  # 包内
        except ImportError:  # 兼容直接 import (sys.path 模式)
            from evidence_domain import materialize_evidence  # type: ignore

        if not verification_id:
            return None
        method = str((verify_meta or {}).get("method") or "").strip()
        # 真实证据候选: verifier 输出字段 (stdout/stderr/error/reason/detail)
        ev_content = str(
            (verify_meta or {}).get("stdout")
            or (verify_meta or {}).get("stderr")
            or (verify_meta or {}).get("error")
            or (verify_meta or {}).get("reason")
            or ""
        ).strip()
        if not method and not ev_content:
            return None  # 无真实 verifier 证据 → 不伪造 EVD
        return materialize_evidence(
            root,
            verification_id=verification_id,
            evidence_type="verifier_output",
            source_ref=method or "external-verifier",
            content=ev_content[:20000],
            metadata={"verifier_meta": {k: v for k, v in (verify_meta or {}).items()
                                        if k in ("score", "tests", "exit_code", "source")}},
            actor=actor,
        )
    except Exception:  # noqa: BLE001 — 失败安全
        return None


def finalize_node_run(
    root: Path | str,
    run_id: str,
    *,
    success: bool,
    verification: dict[str, Any] | None = None,
    failure_reason: str = "",
    note: str = "",
    actor: str = "execution",
    exs_id: str = "",        # P0-F4: canonical EXS-* (I8 收纳产物 + ver 关联)
    output: str = "",        # P0-F4: 执行输出 (收纳为 report artifact 候选)
    artifact_root: Path | str | None = None,  # P0-F4: 产物收纳目标 (缺省 root)
) -> dict[str, Any]:
    """P0-F2: 外部执行完成后推进 NodeRun (TaskRun) 到终态 — 幂等, 零二次执行。

    与 execute_node_run 的区别: execute_node_run 是完整执行循环 (会调用 executor_fn
    触发真实执行); 本函数只做**已发生执行的结果吸收** (EXS 已由 gateway/外部执行器
    产生), 绝不调用 executor_fn — 满足 P0-F1 STOP 条件 (NodeRun 不得触发第二次执行)。

    合法转换 (NODERUN_TRANSITIONS):
      PENDING → RUNNING → VERIFYING → COMPLETED (success)
      PENDING → RUNNING → FAILED                (failure; RUNNING→FAILED 合法)
      已在 COMPLETED/FAILED (终态) → 幂等返回现状, 不重复转换。
    verification: 外部执行的 verify 元数据 (gateway verify dict) — 记录为 run 字段,
      不构成 F3 Verification SSOT (仅 metadata)。
    """
    with _lock:
        run = get_node_run(root, run_id)
        if run is None:
            raise NodeError(f"NodeRun 不存在: {run_id}")
        cur = run.get("state")
        # 幂等: 终态已定 → 返回现状 (重复 writeback 不逆转/不重复转换)
        if cur in ("COMPLETED", "FAILED"):
            return run
        if cur == "PENDING":
            _record(root, run, "RUNNING", actor=actor, note="external execution finished, absorbing result")
        if success:
            # PENDING→RUNNING→VERIFYING→COMPLETED (无 repair 最小路径)
            if run.get("state") == "RUNNING":
                _record(root, run, "VERIFYING", actor=actor,
                        note=note or "absorbing external result (success)")
            # P0-F4 (I8): 执行成功 → 收纳产物为 canonical art-* (生产 contract 内,
            # 非事后补登记; 幂等: 同 EXS+type → 同 art-*)
            _art = _absorb_execution_artifact(
                root, run_id, exs_id=exs_id, output=output,
                artifact_root=artifact_root or root, actor=actor)
            # P0-F3: verify metadata → ver-* SSOT 物化 (唯一 canonical); run 存引用
            run["verification"] = _materialize_verify(
                root, run_id, verification or {},
                ok=True, actor=actor, exs_id=exs_id,
                artifact_ids=[_art["artifact_id"]] if _art else [],
            )
            # P0-F4: 真实 verifier 输出 → EVD-* (支撑 ver 结论; 无内容不伪造)
            _attach_verify_evidence(
                root, str(run["verification"].get("verification_id") or ""),
                verify_meta=verification or {}, actor=actor)
            run["artifact_id"] = _art["artifact_id"] if _art else run.get("artifact_id")
            run["completed_at"] = _now_iso()
            _record(root, run, "COMPLETED", actor=actor, note=note or "external execution success")
        else:
            run["verification"] = _materialize_verify(
                root, run_id, verification or {},
                ok=False, actor=actor, exs_id=exs_id)
            _attach_verify_evidence(
                root, str(run["verification"].get("verification_id") or ""),
                verify_meta=verification or {}, actor=actor)
            run["failure_reason"] = str(failure_reason or "")[:300]
            # 当前态必为 RUNNING (PENDING 已在上面推为 RUNNING); RUNNING→FAILED 合法
            _record(root, run, "FAILED", actor=actor, note=note or "external execution failure")
        return run


# ------------------------------------------------------------------ 执行

def execute_node_run(
    root: Path | str,
    run_id: str,
    *,
    executor_fn: Callable[[dict[str, Any]], dict[str, Any]],
    executor_name: str,
    agent: str | None = None,
    model: str | None = None,
    artifact_root: Path | str | None = None,
    max_attempts: int = 1,
    repair_fn: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """执行 NodeRun: PENDING→RUNNING→(Artifact)→VERIFYING→COMPLETED/FAILED (S5 Repair Loop)。

    executor_fn: 统一契约 execute(input) → {ok, output/patch_text, error, artifact_type, verification}
    repair_fn: 统一契约 repair(failed_artifact, verification, diagnosis_ctx) → 新执行结果
      (与 executor_fn 同形状; 缺省 → 无 repair, max_attempts=1 即 S2 行为)
    max_attempts: 最大尝试次数 (含首次); verification FAIL → 若 attempts < max → REPAIRING → 重试
    Artifact 不可变: 每次尝试产出新 Artifact (A→FAIL, B→PASS), 历史保留在 run.attempts
    """
    with _lock:
        run = get_node_run(root, run_id)
        if run is None:
            raise NodeError(f"NodeRun 不存在: {run_id}")
        if run.get("state") != "PENDING":
            raise NodeError(f"NodeRun 非 PENDING (当前: {run.get('state')})")

        _record(root, run, "RUNNING", actor=executor_name, note="started")
        run["executor"] = executor_name
        run["agent"] = agent
        run["model"] = model
        run["started_at"] = _now_iso()
        run.setdefault("attempts", [])
        _write_run(root, run)

    ar = Path(artifact_root or root)
    attempts_used = 0
    current_input = dict(run.get("input") or {})

    while True:
        attempts_used += 1
        # 执行 (锁外 — 真实 subprocess 可能长)
        try:
            result = executor_fn(current_input)
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "error": f"executor exception: {exc}", "artifact_type": "report"}

        if not result.get("ok"):
            # 执行失败: 若允许 retry 且 attempts 未满 → 重试 (transient); 否则 FAILED
            if attempts_used < max_attempts:
                with _lock:
                    run = get_node_run(root, run_id)
                    run["attempts"].append({"attempt": attempts_used, "state": "RETRY",
                                            "reason": str(result.get("error") or "")[:200]})
                    _record(root, run, "REPAIRING", actor="system", note=f"retry {attempts_used}")
                continue
            with _lock:
                run = get_node_run(root, run_id)
                run["failure_reason"] = str(result.get("error") or "executor returned not ok")[:300]
                _record(root, run, "FAILED", actor="system", note=run["failure_reason"][:120])
            return run

        # 产出 Artifact (S1 Lifecycle, GENERATED; 每次尝试新 Artifact — 不可变 I10)
        try:
            from .artifact_lifecycle import create_artifact

            artifact = create_artifact(
                ar,
                artifact_type=result.get("artifact_type", "code_change"),
                payload=result.get("output") or {},
                patch_text=result.get("patch_text"),
                project_id=run.get("input", {}).get("project_id"),
                node_run_id=run_id,
                producer=executor_name,
            )
        except Exception as exc:  # noqa: BLE001
            with _lock:
                run = get_node_run(root, run_id)
                run["failure_reason"] = f"artifact creation failed: {exc}"
                _record(root, run, "FAILED", actor="system", note="artifact failed")
            return run

        with _lock:
            run = get_node_run(root, run_id)
            run["artifact_id"] = artifact["artifact_id"]
            _record(root, run, "VERIFYING", actor="system", note=f"artifact produced (attempt {attempts_used})")

        # Verification
        verification = result.get("verification") or {"result": "PASS", "source": "default"}
        v_result = verification.get("result")
        if v_result is None:
            v_result = verification.get("status")  # S11: pytest 结果用 status 字段
        if v_result not in VERIFY_RESULTS:
            v_result = "INCONCLUSIVE"

        # 记录 attempt (P0-F3: verification → ver-* SSOT 物化; run 存引用)
        v_ref = _materialize_verify(
            root, run_id, verification,
            ok=(v_result == "PASS"),
            actor=str(executor_name or "node-exec"),
            exs_id="",
            attempt=attempts_used,
            artifact_ids=[artifact["artifact_id"]],  # P0-F4 (D3): ver ↔ art
        )
        # P0-F4: 真实 verifier 输出 → EVD-* (有内容才物化, 不伪造)
        _attach_verify_evidence(
            root, str(v_ref.get("verification_id") or ""),
            verify_meta=verification, actor=str(executor_name or "node-exec"))
        with _lock:
            run = get_node_run(root, run_id)
            run["verification"] = v_ref
            run["attempts"].append({
                "attempt": attempts_used,
                "state": "VERIFIED",
                "artifact_id": artifact["artifact_id"],
                "verification": {"status": v_result, **verification,
                                 "verification_id": v_ref.get("verification_id")},
            })
            _write_run(root, run)

        if v_result == "PASS":
            with _lock:
                run = get_node_run(root, run_id)
                run["completed_at"] = _now_iso()
                _record(root, run, "COMPLETED", actor="system", note="verification PASS")
            return run

        # FAIL → Repair (若允许且未到上限)
        if attempts_used >= max_attempts or repair_fn is None:
            with _lock:
                run = get_node_run(root, run_id)
                run["failure_reason"] = (
                    f"verification {v_result} (attempt {attempts_used}/{max_attempts}): "
                    f"{str(verification.get('error') or verification.get('stderr') or '')[:200]}")
                _record(root, run, "FAILED", actor="system", note=f"verification {v_result}")
            return run

        # Repair: 基于失败 Artifact + Verification evidence → 新执行结果
        with _lock:
            run = get_node_run(root, run_id)
            _record(root, run, "REPAIRING", actor="system", note=f"repair attempt {attempts_used}")
        try:
            repaired = repair_fn(artifact, verification, run.get("input") or {})
            current_input = dict(run.get("input") or {})
            # Repair 结果作为下一轮执行输入 (显式传递, 无 hidden state)
            if repaired.get("input"):
                current_input.update(repaired["input"])
            executor_fn = lambda _inp, _r=repaired: _r  # noqa: E731 — repair 结果即执行结果
        except Exception as exc:  # noqa: BLE001
            with _lock:
                run = get_node_run(root, run_id)
                run["failure_reason"] = f"repair exception: {exc}"
                _record(root, run, "FAILED", actor="system", note="repair failed")
            return run
        # 继续循环 (attempts_used 已 +1, 下一轮 verify repaired 结果)


# ------------------------------------------------------------------ 兼容真实 Executor

def adapt_external_executor(adapter: Any, prompt_builder: Callable[[dict[str, Any]], str]):
    """把 external_executor.run 适配成 Node executor_fn 契约。

    返回 fn(input) → {ok, output, patch_text, error, artifact_type}
    """
    from .external_executor.executor import run as ext_run

    def _fn(input_data: dict[str, Any]) -> dict[str, Any]:
        prompt = prompt_builder(input_data)
        project_dir = str(input_data.get("project_dir") or "")
        agent = str(input_data.get("agent") or "")
        r = ext_run(adapter, prompt, project_dir, agent=agent)
        ok = r.get("exit_code") == 0
        return {
            "ok": ok,
            "output": r.get("output") or "",
            "patch_text": r.get("output") or "",
            "error": r.get("error") or "",
            "artifact_type": input_data.get("artifact_type", "code_change"),
            "verification": {"result": "PASS" if ok else "FAIL",
                             "source": f"executor exit_code={r.get('exit_code')}"},
        }

    return _fn


# ------------------------------------------------------------------ E1: Human Decision / WAITING_FOR_USER (Node Loop 泛化)

def request_decision(root: Path | str, run_id: str, *, question: str,
                     options: list[str] | None = None, finding_refs: list[str] | None = None,
                     actor: str = "system") -> dict[str, Any]:
    """NodeRun → WAITING_FOR_USER + 决策请求 (事实化 Ask User)。

    Decision 是 NodeRun 事实 (run['decisions'] append + audit), 非聊天文本。
    LLM 不能自行 RESOLVED (需 human actor) — 防伪确认。
    """
    with _lock:
        run = get_node_run(root, run_id)
        if run is None:
            raise NodeError(f"NodeRun 不存在: {run_id}")
        if run.get("state") not in ("RUNNING", "PENDING", "VERIFYING"):
            raise NodeError(f"状态 {run.get('state')} 不能请求决策")
        decision = {
            "decision_id": f"dec-{uuid.uuid4().hex[:10]}",
            "question": question,
            "options": list(options or []),
            "finding_refs": list(finding_refs or []),
            "status": "PENDING",
            "chosen": None,
            "requested_by": actor,
            "requested_at": _now_iso(),
            "decided_at": None,
            "decided_by": None,
        }
        run.setdefault("decisions", []).append(decision)
        _record(root, run, "WAITING_FOR_USER", actor=actor,
                note=f"decision requested: {decision['decision_id']}")
        return decision


def record_decision(root: Path | str, run_id: str, decision_id: str, *,
                    chosen: str, actor: str = "human") -> dict[str, Any]:
    """人类决策写入 NodeRun 事实。actor != human → 拒绝 (防 LLM 伪确认)。

    记录后状态 WAITING_FOR_USER → RUNNING (可 resume)。
    """
    if str(actor or "") != "human":
        raise NodeError("decision 必须由 human 确认 (LLM 不能自标 confirmed)")
    with _lock:
        run = get_node_run(root, run_id)
        if run is None:
            raise NodeError(f"NodeRun 不存在: {run_id}")
        decs = run.get("decisions") or []
        dec = next((d for d in decs if d.get("decision_id") == decision_id), None)
        if dec is None:
            raise NodeError(f"decision 不存在: {decision_id}")
        if dec.get("status") == "RESOLVED":
            return dec  # 幂等
        dec["status"] = "RESOLVED"
        dec["chosen"] = chosen
        dec["decided_at"] = _now_iso()
        dec["decided_by"] = actor
        if run.get("state") == "WAITING_FOR_USER":
            _record(root, run, "RUNNING", actor=actor,
                    note=f"decision resolved: {decision_id} → {chosen}")
        else:
            _write_run(root, run)
        return dec


# ------------------------------------------------------------------ E2: Checkpoint / Resume

def update_checkpoint(root: Path | str, run_id: str, *, patch: dict[str, Any]) -> dict[str, Any]:
    """NodeRun 进度事实 (迭代/已完成维度/findings 引用/open/next_work)。

    checkpoint 属于 NodeRun (非 conv_state) — '继续' = 读此续跑。
    """
    with _lock:
        run = get_node_run(root, run_id)
        if run is None:
            raise NodeError(f"NodeRun 不存在: {run_id}")
        cp = dict(run.get("checkpoint") or {})
        for k, v in (patch or {}).items():
            cp[k] = v
        cp["updated_at"] = _now_iso()
        run["checkpoint"] = cp
        _write_run(root, run)
        return run


def bump_iteration(root: Path | str, run_id: str) -> int:
    """迭代计数 +1 (真实新工作才调)。"""
    with _lock:
        run = get_node_run(root, run_id)
        if run is None:
            raise NodeError(f"NodeRun 不存在: {run_id}")
        cp = dict(run.get("checkpoint") or {})
        cp["iteration"] = int(cp.get("iteration") or 0) + 1
        cp["updated_at"] = _now_iso()
        run["checkpoint"] = cp
        _write_run(root, run)
        return int(cp["iteration"])


def get_active_run(root: Path | str, node_id: str,
                   project_id: str = "") -> dict[str, Any] | None:
    """项目当前活动 NodeRun (RUNNING/WAITING_FOR_USER/PENDING — 未终态)。"""
    best = None
    for r in list_node_runs(root, node_id):
        if r.get("state") in ("RUNNING", "WAITING_FOR_USER", "PENDING", "VERIFYING", "REPAIRING"):
            if project_id and r.get("project_id") != project_id:
                continue
            if best is None or str(r.get("created_at") or "") > str(best.get("created_at") or ""):
                best = r
    return best
