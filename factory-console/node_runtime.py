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

#: NodeRun 生命周期 (S2 最小: 无 Repair)
NODERUN_STATES = ("PENDING", "RUNNING", "VERIFYING", "COMPLETED", "FAILED")

#: 合法转换
NODERUN_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "PENDING": ("RUNNING",),
    "RUNNING": ("VERIFYING", "FAILED"),
    "VERIFYING": ("COMPLETED", "FAILED"),
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
) -> dict[str, Any]:
    """实例化 NodeRun: PENDING。NodeRun 是事实记录 (不可变: state 转换 append 而非覆写)。"""
    node = get_node(root, node_id)
    if node is None:
        raise NodeError(f"Node 不存在: {node_id} (请先 register_node)")
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    run: dict[str, Any] = {
        "run_id": run_id,
        "node_id": node_id,
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
        if v_result not in VERIFY_RESULTS:
            v_result = "INCONCLUSIVE"

        # 记录 attempt
        with _lock:
            run = get_node_run(root, run_id)
            run["verification"] = verification
            run["attempts"].append({
                "attempt": attempts_used,
                "state": "VERIFIED",
                "artifact_id": artifact["artifact_id"],
                "verification": {"status": v_result, **verification},
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
