"""factory-console/production_runtime.py — AI Factory OS Production Runtime Kernel

KERNEL INVERSION: 这是 AI Factory OS 的唯一生产执行 Kernel。

设计原则:
- 唯一生产执行入口: 所有生产任务必须经过此 Runtime
- NodeRun 作为执行事实: 每次执行都有 NodeRun + Execution 记录
- Artifact Lifecycle 强制: 所有生产输出必须进入 Artifact Lifecycle
- Verification 独立: Agent Result 不是 Verified Result
- Recovery 内置: 失败自动进入 Recovery 流程
- Event 驱动: 所有动作产生 Event

禁止:
- agent_loop.py 直接执行生产任务 (已降级为 Agent Capability)
- conv_state.json 作为 Production State
- 前端 useState 作为业务状态来源
- LLM 猜测 active_work/next_action (已禁用)
"""

import os
import uuid
from pathlib import Path
from typing import Any, Callable

# 使用绝对导入 (factory_console 是包名，来自 pyproject.toml 的 package-dir 映射)
from factory_console.node_runtime import (
    create_node_run, get_node_run, transition_node_run,
    execute_node_run, NodeError,
)
from factory_console.artifact_lifecycle import create_artifact, get_artifact

# =============================================================================
# Kernel Constants
# =============================================================================

KERNEL_VERSION = "2.0.0-kernel-inversion"
KERNEL_NAME = "AI Factory OS Production Runtime"

# Execution States
STATE_PENDING = "PENDING"
STATE_RUNNING = "RUNNING"
STATE_WAITING = "WAITING"
STATE_COMPLETED = "COMPLETED"
STATE_FAILED = "FAILED"
STATE_RECOVERING = "RECOVERING"
STATE_BLOCKED = "BLOCKED"

# Artifact Lifecycle States (from artifact_lifecycle)
ARTIFACT_GENERATED = "GENERATED"
ARTIFACT_STAGED = "STAGED"
ARTIFACT_REVIEWED = "REVIEWED"
ARTIFACT_APPROVED = "APPROVED"
ARTIFACT_COMMITTED = "COMMITTED"
ARTIFACT_RELEASED = "RELEASED"

# Verification Result
VERIFY_PASS = "PASS"
VERIFY_FAIL = "FAIL"
VERIFY_PENDING = "PENDING"


# =============================================================================
# Kernel Entry Point
# =============================================================================

def _list_files_relative(directory: str | Path) -> list[str]:
    """目录内相对文件列表 (真实 executor 产物检查用; 只读)。"""
    base = Path(directory)
    if not base.exists():
        return []
    out: list[str] = []
    for fp in sorted(base.rglob("*")):
        if fp.is_file():
            out.append(str(fp.relative_to(base)))
    return out


def build_real_executor(
    root: str | Path,
    *,
    executor_name: str = "",
    timeout: int | None = None,
    workspace_dir: str | Path | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]] | None:
    """接线现有 external executor (codex/claude/hermes adapter) → Node executor_fn 契约。

    R0 P0: 复用 external_executor (现有 Runtime 的接线层), 不新建执行器/Agent 平台。
    返回 None = 本机无可用 executor (调用方必须诚实 FAILED, 禁止占位假成功)。
    """
    from factory_console.external_executor.executor import discover_binary
    from factory_console.external_executor.executor import run as ext_run
    from factory_console.external_executor.registry import ExternalExecutorRegistry

    reg = ExternalExecutorRegistry(str(root))
    candidates: list[str] = []
    if executor_name:
        # 显式指定 → 严格匹配 (未知 executor 不静默回退到其它 CLI)
        candidates.append(executor_name)
    else:
        env_name = os.environ.get("FACTORY_EXECUTOR", "").strip()
        if env_name:
            candidates.append(env_name)
        candidates += ["codex", "claude", "hermes"]
    adapter = None
    chosen = ""
    for name in candidates:
        if not name:
            continue
        a = reg.get(name)
        if a is not None and discover_binary(a):
            adapter, chosen = a, name
            break
    if adapter is None:
        return None
    if timeout is None:
        try:
            timeout = int(os.environ.get("FACTORY_EXECUTOR_TIMEOUT") or 0) or None
        except ValueError:
            timeout = None

    def _executor_fn(input_data: dict[str, Any]) -> dict[str, Any]:
        data = dict(input_data or {})
        task = data.get("task") or {}
        title = str(task.get("title") or task.get("id") or "任务")
        goal = str(data.get("goal") or task.get("goal")
                   or task.get("title") or "")[:400]
        pdir = str(data.get("project_dir") or workspace_dir or "").strip()
        if not pdir:
            return {
                "ok": False,
                "error": f"executor {chosen}: 未提供 project_dir",
                "artifact_type": "report",
                "verification": {"result": "FAIL", "error": "no project_dir",
                                 "source": "resolve"},
            }
        Path(pdir).mkdir(parents=True, exist_ok=True)
        prompt = (
            f"你是 AI Factory OS 的生产执行器。请在目录 {pdir} 中完成任务。\n"
            f"任务: {title}\n目标: {goal}\n"
            "要求: 创建最小可运行实现; 文件必须真实写入该目录; "
            "不要展开成大型工程; 完成后用一两句话报告创建/修改了哪些文件。"
        )
        before = set(_list_files_relative(pdir))
        try:
            r = ext_run(adapter, prompt, pdir, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 — 子进程异常 → 诚实 FAILED
            return {
                "ok": False,
                "error": f"executor {chosen} 调用异常: {exc}",
                "artifact_type": "report",
                "verification": {"result": "FAIL",
                                 "error": str(exc)[:200], "source": "exception"},
            }
        after = _list_files_relative(pdir)
        new_files = [f for f in after if f not in before]
        ok = bool(r.get("exit_code") == 0 and new_files)
        error = ""
        if r.get("exit_code") != 0:
            error = str(r.get("error") or f"executor exit={r.get('exit_code')}")
        elif not new_files:
            error = f"executor {chosen}: exit 0 但未产生新文件"
        return {
            "ok": ok,
            "output": str(r.get("output") or "")[:20000],
            "error": error,
            "artifact_type": str(data.get("artifact_type") or "code_change"),
            "verification": {
                "result": "PASS" if ok else "FAIL",
                "source": f"executor={chosen} exit={r.get('exit_code')} "
                          f"new_files={len(new_files)}",
                "error": error,
                "command": str(r.get("command") or "")[:300],
                "new_files": new_files[:100],
            },
        }

    return _executor_fn


def execute_task(
    root: Path | str,
    task_id: str,
    *,
    project_id: str | None = None,
    input_data: dict[str, Any] | None = None,
    actor: str = "human",
    capability_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    executor_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    executor_name: str = "",
) -> dict[str, Any]:
    """Production Runtime Kernel Entry Point (R0 P0: 真实执行内核)。

    委托 node_runtime.execute_node_run 执行完整 NodeRun 生命周期
    (RUNNING → Artifact → VERIFYING → COMPLETED/FAILED, 全部持久化 +
    ver-*/EVD-* 证据)。禁止占位假成功:
    - capability_fn 提供 (测试/宿主注入) → 包装为 executor_fn 契约
    - executor_fn 提供 (真实 executor, 见 build_real_executor) → 直接使用
    - 两者均无 → 诚实 FAILED (不返回 ok=True 掩盖未执行)

    返回: {run_id, state, artifact_id, evidence, verification, error, output}
    """
    root = Path(root) if not isinstance(root, Path) else root
    data = dict(input_data or {})
    project_id = str(project_id or data.get("project_id") or "")
    if not project_id:
        raise ProductionKernelError("Project scope is required for production execution")

    # 1. NodeRun (执行事实; PENDING 持久化)
    try:
        node_run = create_node_run(
            str(root), node_id=task_id,
            input_data=data, trigger=f"kernel:{actor}")
        node_run_id = node_run["run_id"]
    except NodeError as exc:
        raise ProductionKernelError(f"Failed to create NodeRun: {exc}")

    # 2. 解析执行能力
    executor_label = executor_name or "node-executor"
    if executor_fn is None and capability_fn is not None:
        cap = capability_fn

        def _executor_fn(inp: dict[str, Any]) -> dict[str, Any]:
            r = cap(inp) or {}
            ok = bool(r.get("ok"))
            return {
                "ok": ok,
                "output": r.get("output") or {},
                "error": r.get("error") or "",
                "artifact_type": str(r.get("artifact_type")
                                     or inp.get("artifact_type") or "code_change"),
                "verification": r.get("verification") or {
                    "result": "PASS" if ok else "FAIL",
                    "source": "capability_fn",
                    "error": "" if ok else (r.get("error")
                                            or "capability returned ok=False"),
                },
            }

        executor_label = executor_name or "capability"
    elif executor_fn is None:
        _executor_fn = None
    else:
        _executor_fn = executor_fn

    if _executor_fn is None:
        reason = ("未配置执行能力 (capability_fn/executor_fn 均未提供) — "
                  "禁止占位假成功")
        # 事件由 transition_node_run → node_runtime._record 唯一发射 (S1: 事件单点)
        try:
            transition_node_run(str(root), node_run_id, STATE_FAILED,
                                actor=actor, note=reason[:120])
        except NodeError:
            pass
        return {"run_id": node_run_id, "state": STATE_FAILED,
                "artifact_id": None, "evidence": {}, "verification": VERIFY_FAIL,
                "error": reason, "output": None}

    # 3. started event (补充语义: node_runtime 发射 RUNNING, STARTED 为 kernel 视图)
    _emit_event(root, "NODE_RUN_STARTED", {
        "run_id": node_run_id, "task_id": task_id,
        "project_id": project_id, "actor": actor,
        "executor": executor_label,
    })

    # 4. 完整 NodeRun 生命周期 (node_runtime.execute_node_run — 唯一正确 kernel)
    try:
        done = execute_node_run(
            str(root), node_run_id,
            executor_fn=_executor_fn,
            executor_name=executor_label,
            agent=data.get("agent"),
            model=data.get("model"),
            artifact_root=str(root),
            max_attempts=int(data.get("max_attempts") or 1),
        )
    except Exception as exc:  # noqa: BLE001 — 内核异常 → 诚实 FAILED (不吞)
        reason = f"execute_node_run exception: {exc}"
        try:
            transition_node_run(str(root), node_run_id, STATE_FAILED,
                                actor=actor, note=reason[:120])
        except NodeError:
            pass
        return {"run_id": node_run_id, "state": STATE_FAILED,
                "artifact_id": None, "evidence": {}, "verification": VERIFY_FAIL,
                "error": reason, "output": None}

    state = done.get("state") or STATE_FAILED
    artifact_id = done.get("artifact_id")
    failure_reason = done.get("failure_reason") or done.get("error")
    verification_ref = done.get("verification")
    verification_status = (VERIFY_PASS if state == STATE_COMPLETED
                           else VERIFY_FAIL)
    evidence = {"node_run_id": node_run_id}
    if isinstance(verification_ref, dict):
        if verification_ref.get("verification_id"):
            evidence["verification_id"] = verification_ref["verification_id"]
        if verification_ref.get("status"):
            verification_status = verification_ref["status"]

    # 5. completion/failure event — 已由 execute_node_run → node_runtime._record
    #    唯一发射 (NODE_RUN_COMPLETED/FAILED; S1: 事件单点)。此处不重复。

    # 6. output (COMPLETED + artifact payload)
    output = None
    if state == STATE_COMPLETED and artifact_id:
        try:
            art = get_artifact(root, artifact_id)
            payload = (art or {}).get("payload")
            if isinstance(payload, dict):
                output = payload.get("output", payload)
            else:
                output = payload
        except Exception:  # noqa: BLE001 — output 读取失败不影响状态事实
            output = None

    return {"run_id": node_run_id, "state": state,
            "artifact_id": artifact_id, "evidence": evidence,
            "verification": verification_status,
            "error": failure_reason, "output": output}


def resume_task(
    root: Path | str,
    run_id: str,
    *,
    resume_data: dict[str, Any] | None = None,
    actor: str = "human",
) -> dict[str, Any]:
    """恢复已存在的 NodeRun。

    用于 WAITING_FOR_USER 后的人类决策恢复。

    Args:
        root: Workspace root
        run_id: NodeRun ID to resume
        resume_data: Resume 时提供的数据
        actor: 执行者

    Returns:
        执行结果 (同 execute_task)
    """
    root = Path(root) if not isinstance(root, Path) else root

    # 获取现有 NodeRun
    node_run = get_node_run(str(root), run_id)
    if not node_run:
        raise ProductionKernelError(f"NodeRun not found: {run_id}")

    # 只有 WAITING 状态才能恢复
    if node_run.get("state") != STATE_WAITING:
        raise ProductionKernelError(f"NodeRun not in WAITING state: {node_run.get('state')}")

    # 记录恢复事件
    _emit_event(root, "execution.resumed", {
        "run_id": run_id,
        "actor": actor,
        "resume_data": resume_data,
    })

    # 转换状态回 RUNNING
    transition_node_run(str(root), run_id, STATE_RUNNING, actor=actor, note="resumed")

    # 继续执行 (需要 capability 能力，这里简化处理)
    return {
        "run_id": run_id,
        "state": STATE_RUNNING,
        "message": "Resumed - continue execution",
    }


def get_execution_status(
    root: Path | str,
    run_id: str,
) -> dict[str, Any]:
    """获取执行状态。

    Args:
        root: Workspace root
        run_id: NodeRun ID

    Returns:
        NodeRun 状态和上下文
    """
    node_run = get_node_run(str(root), run_id)
    if not node_run:
        raise ProductionKernelError(f"NodeRun not found: {run_id}")

    return {
        "run_id": run_id,
        "state": node_run.get("state"),
        "node_id": node_run.get("node_id"),
        "project_id": node_run.get("project_id"),
        "attempts": node_run.get("attempts", []),
        "created_at": node_run.get("created_at"),
        "updated_at": node_run.get("updated_at"),
    }


# =============================================================================
# Private Helpers
# =============================================================================

def _create_execution_artifact(
    root: Path,
    *,
    node_run_id: str,
    task_id: str,
    project_id: str,
    output: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    """创建执行产生的 Artifact。"""
    artifact_id = str(uuid.uuid4())[:12]

    try:
        create_artifact(
            str(root),
            artifact_type="execution_output",
            project_id=project_id,
            payload={
                "node_run_id": node_run_id,
                "task_id": task_id,
                "source": "production_runtime",
                "output": output,
                **(metadata or {}),
            },
            node_run_id=node_run_id,
            producer="production_runtime",
        )
    except Exception:
        # 不阻断执行，只是记录
        pass

    return artifact_id


def _emit_event(root: Path, event_type: str, data: dict[str, Any]) -> None:
    """Kernel Event → 现有 AuditStore (R0 P0: 注册事件类型 + 标准 audit 文件)。

    事件类型必须 ∈ EVENT_TYPES (审计契约); 失败安全 (审计故障不中断业务),
    但不静默吞掉"类型非法" — 类型非法直接不写 (调用方负责用注册类型)。
    """
    try:
        from .audit.audit_event import EVENT_TYPES, AuditEvent
        from .audit.audit_store import AuditStore

        if str(event_type) not in EVENT_TYPES:
            return
        store = AuditStore(workspace=str(root))
        event = AuditEvent.create(
            str(event_type),
            trace_id=str(data.get("run_id", "")),
            project_id=str(data.get("project_id", "")),
            actor_id=str(data.get("actor", "system")),
            actor_type="system",
            action="kernel",
            source="production_runtime",
            decision="allow",
            decision_reason="kernel_event",
            evidence=data,
            result={"ok": True},
        )
        store.append(event)
    except Exception:  # noqa: BLE001 — 审计故障不中断业务 (AuditEmitter 同纪律)
        pass


class ProductionKernelError(Exception):
    """Production Runtime Kernel 错误。"""
    pass


# =============================================================================
# Kernel Info
# =============================================================================

def kernel_info() -> dict[str, Any]:
    """获取 Kernel 信息。"""
    return {
        "name": KERNEL_NAME,
        "version": KERNEL_VERSION,
        "states": [
            STATE_PENDING,
            STATE_RUNNING,
            STATE_WAITING,
            STATE_COMPLETED,
            STATE_FAILED,
            STATE_RECOVERING,
            STATE_BLOCKED,
        ],
        "artifact_lifecycle": [
            ARTIFACT_GENERATED,
            ARTIFACT_STAGED,
            ARTIFACT_REVIEWED,
            ARTIFACT_APPROVED,
            ARTIFACT_COMMITTED,
            ARTIFACT_RELEASED,
        ],
    }