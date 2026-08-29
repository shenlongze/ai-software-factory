"""factory-console/production_run.py — S3 ProductionRun / Workflow Orchestration.

AI Factory 2.0 第三个 Production Primitive: 多个 Node 组成真实生产流程。

- Workflow: 定义 (node 列表 + 依赖) — 可复用模板
- ProductionRun: 一次执行事实 (状态机 PENDING→RUNNING→COMPLETED/FAILED/BLOCKED)
- 串行 DAG (第一版): Node A → B → C, B depends_on A
- Artifact binding: Node B 的输入 = Node A 的 Artifact (显式关系, 无 hidden state)
- 每个 Node 走 NodeRun → Artifact → S1 Lifecycle (ProductionRun 不直接改 Workspace)
- 失败语义: A FAILED → B BLOCKED (不执行), ProductionRun FAILED

设计决策 (S3):
- 不复用旧 workflow_runner (它直接写 workspace, 绕 Artifact Lifecycle — Legacy Conflict)
- 不引入并行调度 (串行优先, 真实生产优先)
- 不删除旧代码 (Scope Firewall)
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ------------------------------------------------------------------ 状态

#: ProductionRun 生命周期
PRUN_STATES = ("PENDING", "RUNNING", "COMPLETED", "FAILED", "BLOCKED")

#: 合法转换
PRUN_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "PENDING": ("RUNNING",),
    "RUNNING": ("COMPLETED", "FAILED", "BLOCKED"),
    "COMPLETED": (),
    "FAILED": (),
    "BLOCKED": (),
}


class ProductionRunError(Exception):
    """ProductionRun 非法操作。"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _workflows_dir(root: Path | str) -> Path:
    return Path(root) / "workflows"


def _wf_path(root: Path | str, workflow_id: str) -> Path:
    return _workflows_dir(root) / "definitions" / f"{workflow_id}.json"


def _prun_path(root: Path | str, run_id: str) -> Path:
    return _workflows_dir(root) / "runs" / f"{run_id}.json"


_lock = threading.RLock()


# ------------------------------------------------------------------ Workflow (定义)

def register_workflow(
    root: Path | str,
    *,
    workflow_id: str,
    name: str,
    project_id: str | None = None,
    nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """注册 Workflow 定义 (可复用模板)。

    nodes: [{node_id, depends_on: [node_id...], executor_name, input_binding: {...}}]
    input_binding: {field: "artifact:<node_id>"} — Node 输入字段来自某 Node 的 Artifact。
    """
    wf: dict[str, Any] = {
        "workflow_id": workflow_id,
        "name": name,
        "project_id": project_id,
        "nodes": nodes or [],
        "created_at": _now_iso(),
    }
    # 校验依赖存在
    ids = {n["node_id"] for n in (nodes or [])}
    for n in (nodes or []):
        for dep in n.get("depends_on", []):
            if dep not in ids:
                raise ProductionRunError(f"Workflow {workflow_id}: 依赖 {dep} 不在节点列表")
    with _lock:
        p = _wf_path(root, workflow_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    return wf


def get_workflow(root: Path | str, workflow_id: str) -> dict[str, Any] | None:
    p = _wf_path(root, workflow_id)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ ProductionRun (执行事实)

def create_production_run(
    root: Path | str,
    workflow_id: str,
    *,
    input_data: dict[str, Any] | None = None,
    trigger: str = "user",
) -> dict[str, Any]:
    """实例化 ProductionRun: PENDING。"""
    wf = get_workflow(root, workflow_id)
    if wf is None:
        raise ProductionRunError(f"Workflow 不存在: {workflow_id}")
    run_id = f"prun-{uuid.uuid4().hex[:12]}"
    run: dict[str, Any] = {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "project_id": wf.get("project_id"),
        "state": "PENDING",
        "status": "PENDING",   # 兼容视图 (单一权威 = state)
        "input": input_data or {},
        "trigger": trigger,
        "node_runs": [],       # [{node_id, run_id, state, artifact_id}]
        "artifacts": [],       # [artifact_id...] (引用, 不复制内容)
        "failure": None,
        "started_at": None,
        "completed_at": None,
        "created_at": _now_iso(),
        "history": [],
    }
    with _lock:
        _write(root, run)
    _record(root, run, "PENDING", actor="system", note="created")
    return run


def get_production_run(root: Path | str, run_id: str) -> dict[str, Any] | None:
    p = _prun_path(root, run_id)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def list_production_runs(root: Path | str) -> list[dict[str, Any]]:
    base = _workflows_dir(root) / "runs"
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


def _write(root: Path | str, run: dict[str, Any]) -> None:
    p = _prun_path(root, run["run_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    # S7: atomic write (temp + rename) — 防崩溃半写 corrupt JSON
    import os
    import tempfile

    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(run, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _record(root: Path | str, run: dict[str, Any], to_state: str, *, actor: str, note: str) -> None:
    run["history"].append({"from": run.get("state"), "to": to_state, "actor": actor,
                           "at": _now_iso(), "note": note})
    run["state"] = to_state
    run["status"] = to_state
    _write(root, run)
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            f"PRODUCTION_RUN_{to_state}",
            trace_id=run["run_id"],
            project_id=run.get("project_id") or "",
            agent_id=actor,
            actor_type="system",
            actor_id=actor,
            action=f"production_run.{to_state.lower()}",
            source="production_run",
            decision="allow",
            decision_reason="production run transition",
            evidence=[{"run_id": run["run_id"], "workflow_id": run["workflow_id"], "note": note}],
            result={"ok": True},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ 执行 (串行)

# ------------------------------------------------------------------ 真实 Executor 接线 (S4)

#: 模块加载时锁定 build_registry 原始引用 (防测试 patch 污染全局 registry)
from .external_executor import registry as _ext_registry  # noqa: E402

_BUILD_REGISTRY = _ext_registry.build_registry

def _extract_code(output: str) -> str:
    """从 executor 输出提取代码 (markdown 围栏 → 裸代码; 非围栏 → 原样)。"""
    import re

    text = str(output or "")
    blocks = re.findall(r"```(?:python|py|text|bash|sh)?\s*\n(.*?)```", text, re.S)
    if blocks:
        # 多个块 → 拼接 (保持顺序)
        return "\n".join(b.strip("\n") for b in blocks) + "\n"
    return text.strip("\n") + "\n"


def _to_patch(executor_name: str, output: str, input_data: dict[str, Any]) -> str:
    """把 executor 输出转成合法 git patch。

    - 输出本身是 patch (含 diff --git) → 原样返回
    - 否则: 提取代码 → 写入 input 指定的目标文件 (target_file) →
      用 git diff 生成 patch (临时 git 仓库)。
    返回 patch 文本 (空 = 无变更)。
    """
    import re
    import subprocess as _sp

    text = str(output or "")
    if "diff --git" in text:
        return text
    target = str(input_data.get("target_file") or "generated.py")
    code = _extract_code(text)
    if not code.strip():
        return ""
    # 临时目录: 空 git 仓库 + 目标文件 → git add → git diff 生成 patch
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        f = repo / target
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(code, encoding="utf-8")
        for c in (["init", "-q"], ["add", "-A"]):
            _sp.run(["git", "-C", str(repo), *c], capture_output=True, text=True, timeout=30)
        # 从空基线 diff → 新文件 patch
        proc = _sp.run(["git", "-C", str(repo), "diff", "--cached", "--no-color", "--", target],
                       capture_output=True, text=True, timeout=30)
        patch = proc.stdout or ""
        # git diff --cached 对未提交新文件输出 index 0000000..; 需要 --no-index 或先 commit
        if not patch:
            _sp.run(["git", "-C", str(repo), "-c", "user.email=f@l", "-c", "user.name=f",
                     "commit", "-q", "-m", "base"], capture_output=True, text=True, timeout=30)
            _sp.run(["git", "-C", str(repo), "rm", "-q", "--cached", target], capture_output=True, text=True, timeout=30)
            proc2 = _sp.run(["git", "-C", str(repo), "diff", "--no-color", "--", target],
                            capture_output=True, text=True, timeout=30)
            patch = proc2.stdout or ""
        return patch


def build_executor_factory(
    root: Path | str,
    *,
    prompt_builder: Callable[[str, dict[str, Any]], str] | None = None,
    timeout: int | None = None,
) -> Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]]:
    """把 executor_name 路由到真实外部 executor (S4)。

    executor_name → registry adapter (codex/claude/hermes) → adapt_external_executor.
    prompt_builder(executor_name, node_input) → prompt 文本 (默认用 input 的 prompt 字段).
    返回 executor_factory(node_id) → executor_fn(input) 与 S3 execute_production_run 兼容。
    """
    from .external_executor.executor import run as ext_run

    reg = _BUILD_REGISTRY(str(root))

    def _build(executor_name: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
        try:
            adapter = reg.get(executor_name) if hasattr(reg, "get") else None
        except Exception:  # noqa: BLE001 — registry 被测试 patch 或损坏 → 不可用
            adapter = None
        if adapter is None:
            def _missing(input_data):
                return {"ok": False, "error": f"未知 executor: {executor_name}",
                        "artifact_type": "report",
                        "verification": {"result": "FAIL", "error": "unknown executor"}}
            return _missing

        def _fn(input_data: dict[str, Any]) -> dict[str, Any]:
            prompt = ""
            if prompt_builder:
                prompt = prompt_builder(executor_name, input_data)
            else:
                prompt = str(input_data.get("prompt") or "")
            if not prompt:
                return {"ok": False, "error": f"executor {executor_name}: 无 prompt",
                        "artifact_type": "report",
                        "verification": {"result": "FAIL", "error": "no prompt"}}
            project_dir = str(input_data.get("project_dir") or "")
            agent = str(input_data.get("agent") or "")
            r = ext_run(adapter, prompt, project_dir, agent=agent, timeout=timeout)
            ok = r.get("exit_code") == 0
            output = r.get("output") or ""
            # S4: 真实执行可靠性 — exit_code=0 但无输出 → 重试一次 (外部 CLI 偶发空)
            if ok and not output.strip():
                r = ext_run(adapter, prompt, project_dir, agent=agent, timeout=timeout)
                ok = r.get("exit_code") == 0
                output = r.get("output") or ""
                if ok and not output.strip():
                    ok = False
                    r["error"] = (r.get("error") or "") + f" | executor {executor_name} 返回空输出"
            # S4: 真实 executor 输出可能是自由代码 (非 git patch) — 转成合法 patch
            patch_text = _to_patch(executor_name, output, input_data)
            return {
                "ok": ok,
                "output": output,
                "patch_text": patch_text,
                "error": r.get("error") or "",
                "artifact_type": input_data.get("artifact_type", "code_change"),
                "verification": {"result": "PASS" if ok else "FAIL",
                                 "source": f"executor {executor_name} exit_code={r.get('exit_code')}",
                                 "command": r.get("command") or ""},
            }
        return _fn

    def _factory(node_id: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
        return _build(node_id)

    return _factory


def execute_production_run(
    root: Path | str,
    run_id: str,
    *,
    executor_factory: Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]],
    artifact_root: Path | str | None = None,
    actor: str = "system",
    resume: bool = False,
) -> dict[str, Any]:
    """执行 ProductionRun: 串行依赖解析 → 每 Node create NodeRun + execute。

    executor_factory(node_id) → executor_fn (Node 的执行器, 统一契约).
    每个 Node 产出 Artifact → binding 到下游 Node 输入。
    """
    from .node_runtime import (
        register_node, create_node_run, execute_node_run, get_node_run, NodeError,
    )

    with _lock:
        run = get_production_run(root, run_id)
        if run is None:
            raise ProductionRunError(f"ProductionRun 不存在: {run_id}")
        if run.get("state") != "PENDING" and not resume:
            raise ProductionRunError(f"非 PENDING (当前: {run.get('state')})")
        if run.get("state") != "PENDING" and resume:
            # S7: resume 重置为 PENDING (终态由 recovery.resume 提前拦截)
            run["state"] = "PENDING"
            run["status"] = "PENDING"
            run["history"].append({"from": run.get("state"), "to": "PENDING",
                                   "actor": actor, "at": _now_iso(), "note": "resume reset"})
        wf = get_workflow(root, run["workflow_id"])
        _record(root, run, "RUNNING", actor=actor, note="started")
        run["started_at"] = _now_iso()
        _write(root, run)

    nodes = wf["nodes"]
    # 拓扑: 串行, 按依赖解析 (依赖先执行)
    executed: dict[str, dict[str, Any]] = {}  # node_id -> {run_id, artifact_id, state}
    artifacts: dict[str, str] = {}            # node_id -> artifact_id
    ar = Path(artifact_root or root)

    # resume 模式: 预载已完成的 NodeRun (跳过, 禁止重复执行 — S7)
    if resume:
        for nr in run.get("node_runs", []):
            nid = nr.get("node_id")
            if nr.get("state") == "COMPLETED":
                executed[nid] = {"run_id": nr.get("run_id"), "artifact_id": nr.get("artifact_id"),
                                 "state": "COMPLETED"}
                if nr.get("artifact_id"):
                    artifacts[nid] = nr["artifact_id"]

    for node_spec in nodes:
        node_id = node_spec["node_id"]
        deps = node_spec.get("depends_on", [])
        # 已完成 → 跳过 (不重建 NodeRun)
        if node_id in executed and executed[node_id]["state"] == "COMPLETED":
            continue
        # 依赖检查
        dep_failed = None
        for dep in deps:
            dep_rec = executed.get(dep)
            if dep_rec is None:
                dep_failed = f"依赖 {dep} 未执行 (节点顺序错误)"
                break
            if dep_rec["state"] != "COMPLETED":
                dep_failed = f"依赖 {dep} 未成功 (state={dep_rec['state']})"
                break
        if dep_failed:
            with _lock:
                run = get_production_run(root, run_id)
                run["node_runs"].append({"node_id": node_id, "run_id": None,
                                         "state": "BLOCKED", "artifact_id": None,
                                         "reason": dep_failed})
                run["failure"] = f"Node {node_id} BLOCKED: {dep_failed}"
                _write(root, run)
            # BLOCKED → 整个 ProductionRun BLOCKED
            with _lock:
                run = get_production_run(root, run_id)
                _record(root, run, "BLOCKED", actor=actor, note=dep_failed)
            return run

        # 构建 Node 输入: 显式 binding (input_binding: {field: "artifact:<node_id>"})
        node_input = dict(run.get("input") or {})
        binding = node_spec.get("input_binding") or {}
        for field, src in binding.items():
            if isinstance(src, str) and src.startswith("artifact:"):
                src_node = src.split(":", 1)[1]
                if src_node not in artifacts:
                    with _lock:
                        run = get_production_run(root, run_id)
                        run["failure"] = f"Node {node_id}: binding {field} 引用 {src_node} 无 artifact"
                        _record(root, run, "FAILED", actor=actor, note="binding missing")
                    return run
                node_input[field] = artifacts[src_node]
            else:
                node_input[field] = src

        # 注册 Node 定义 (若不存在)
        try:
            register_node(ar, node_id=node_id, name=node_spec.get("name", node_id),
                          node_type=node_spec.get("type", "engineering"))
        except Exception:  # noqa: BLE001 — 已存在则复用
            pass

        # 创建 NodeRun
        try:
            nr = create_node_run(ar, node_id, input_data=node_input, trigger="production")
        except NodeError as exc:
            with _lock:
                run = get_production_run(root, run_id)
                run["failure"] = f"Node {node_id}: {exc}"
                _record(root, run, "FAILED", actor=actor, note=str(exc)[:120])
            return run

        # 执行
        executor_fn = executor_factory(node_id)
        done = execute_node_run(ar, nr["run_id"], executor_fn=executor_fn,
                                executor_name=node_spec.get("executor_name", "node-exec"),
                                artifact_root=str(ar))

        with _lock:
            run = get_production_run(root, run_id)
            # S7: resume 时替换该 node 的旧记录 (旧 RUNNING 无完成证据, 重跑)
            run["node_runs"] = [n for n in run.get("node_runs", []) if n.get("node_id") != node_id]
            run["node_runs"].append({
                "node_id": node_id, "run_id": nr["run_id"],
                "state": done["state"], "artifact_id": done.get("artifact_id"),
            })
            if done.get("artifact_id"):
                artifacts[node_id] = done["artifact_id"]
                run["artifacts"].append(done["artifact_id"])
            _write(root, run)

        executed[node_id] = {"run_id": nr["run_id"], "artifact_id": done.get("artifact_id"),
                             "state": done["state"]}

        if done["state"] != "COMPLETED":
            with _lock:
                run = get_production_run(root, run_id)
                run["failure"] = f"Node {node_id} {done['state']}: {done.get('failure_reason') or ''}"
                _record(root, run, "FAILED", actor=actor, note=f"node {node_id} {done['state']}")
            return run

    # 全部成功
    with _lock:
        run = get_production_run(root, run_id)
        run["completed_at"] = _now_iso()
        _record(root, run, "COMPLETED", actor=actor, note="all nodes completed")
    return run
