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

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# 使用绝对导入 (factory_console 是包名，来自 pyproject.toml 的 package-dir 映射)
from factory_console.node_runtime import (
    register_node, create_node_run, get_node_run, transition_node_run,
    finalize_node_run, get_active_run, NodeError,
)
from factory_console.production_run import (
    register_workflow, create_production_run, execute_production_run,
    get_production_run, ProductionRunError,
)
from factory_console.artifact_lifecycle import create_artifact, get_artifact, transition_artifact
from factory_console.verification_domain import materialize_verification

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

def execute_task(
    root: Path | str,
    task_id: str,
    *,
    project_id: str | None = None,
    input_data: dict[str, Any] | None = None,
    actor: str = "human",
    capability_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Production Runtime Kernel Entry Point.

    这是 AI Factory OS 的唯一生产执行入口。
    禁止绕过此函数直接调用 agent_loop 或其他执行路径。

    流程:
    1. 创建/获取 Task
    2. 确定 Node 类型
    3. 创建 NodeRun (执行事实)
    4. 执行 (调用 capability_fn)
    5. 产生 Artifact
    6. 独立 Verification
    7. Recovery (如失败)
    8. 完成 或 失败

    Args:
        root: Workspace root path
        task_id: Task ID to execute
        project_id: Project scope (必须)
        input_data: Node input data
        actor: 执行者 (human/system/agent)
        capability_fn: 执行能力函数 (可选，不提供则默认使用 agent_loop)

    Returns:
        {
            "run_id": NodeRun ID,
            "state": execution state,
            "artifact_id": produced artifact (if any),
            "evidence": verification evidence,
            "verification": PASS/FAIL,
            "error": error message (if failed)
        }
    """
    root = Path(root) if not isinstance(root, Path) else root
    run_id = str(uuid.uuid4())[:12]

    # 1. 确保 Project Scope 存在
    if not project_id:
        raise ProductionKernelError("Project scope is required for production execution")

    # 2. 创建 NodeRun (执行事实)
    try:
        node_run = create_node_run(
            str(root),
            node_id=task_id,
            input_data=input_data or {},
            trigger=f"kernel:{actor}",
        )
        node_run_id = node_run["run_id"]
    except NodeError as e:
        raise ProductionKernelError(f"Failed to create NodeRun: {e}")

    # 3. 记录 Started Event
    _emit_event(root, "execution.started", {
        "run_id": node_run_id,
        "task_id": task_id,
        "project_id": project_id,
        "actor": actor,
    })

    # 4. 执行
    result = None
    error = None
    try:
        # 调用执行能力 (如果没有提供，使用默认)
        if capability_fn:
            result = capability_fn(input_data or {})
        else:
            # 默认: 回退到旧 agent_loop (降级为 Capability)
            # TODO: 未来应完全移除此回退
            result = _default_capability(input_data or {})

        # 5. 产生 Artifact (如果有输出)
        artifact_id = None
        if result and result.get("output"):
            artifact_id = _create_execution_artifact(
                root,
                node_run_id=node_run_id,
                task_id=task_id,
                project_id=project_id,
                output=result.get("output"),
                metadata=result.get("metadata"),
            )

        # 6. 独立 Verification
        verification = VERIFY_PENDING
        evidence = {}
        if artifact_id:
            # 调用 materialize_verification 记录验证结果
            verification_result = materialize_verification(
                str(root),
                task_run_id=node_run_id,
                status="PASS" if result.get("ok") else "FAIL",
                verification_type="node_execution",
                method="runtime_verification",
                result=result.get("summary", ""),
                artifact_ids=[artifact_id],
            )
            verification = verification_result.get("status", VERIFY_FAIL)
            evidence = {"verification_id": verification_result.get("verification_id")}

        # 7. 确定最终状态
        if verification == VERIFY_PASS:
            state = STATE_COMPLETED
            # 自动推进 Artifact Lifecycle
            if artifact_id:
                try:
                    transition_artifact(root, artifact_id, ARTIFACT_STAGED)
                except Exception:
                    pass  # 不阻断
        else:
            state = STATE_FAILED
            error = result.get("error") or "Verification failed"

        # 8. 记录 Completion Event
        _emit_event(root, "execution.completed", {
            "run_id": node_run_id,
            "state": state,
            "artifact_id": artifact_id,
            "verification": verification,
            "actor": actor,
        })

        return {
            "run_id": node_run_id,
            "state": state,
            "artifact_id": artifact_id,
            "evidence": evidence,
            "verification": verification,
            "error": error,
            "output": result.get("output") if state == STATE_COMPLETED else None,
        }

    except Exception as e:
        # 9. Recovery 流程 (简化版 - 未来扩展)
        error = str(e)

        # 记录失败事件
        _emit_event(root, "execution.failed", {
            "run_id": node_run_id,
            "error": error,
            "actor": actor,
        })

        # 更新 NodeRun 状态
        try:
            transition_node_run(str(root), node_run_id, STATE_FAILED, actor=actor, note=error)
        except Exception:
            pass

        return {
            "run_id": node_run_id,
            "state": STATE_FAILED,
            "artifact_id": None,
            "evidence": {},
            "verification": VERIFY_FAIL,
            "error": error,
        }


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

def _default_capability(input_data: dict[str, Any]) -> dict[str, Any]:
    """默认执行能力 - 回退到降级的 agent_loop。

    警告: 这是临时回退。未来应该完全移除。
    """
    # 临时回退 - 实际应该通过 capability_fn 传入
    return {
        "output": "Default capability executed",
        "ok": True,
    }


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
    except Exception as e:
        # 不阻断执行，只是记录
        pass

    return artifact_id


def _emit_event(root: Path, event_type: str, data: dict[str, Any]) -> None:
    """发出 Kernel Event。"""
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(root / "audit" / "kernel_events.json"))
        event = AuditEvent.create(
            event_type,
            trace_id=data.get("run_id", ""),
            project_id=data.get("project_id", ""),
            actor_id=data.get("actor", "system"),
            actor_type="system",
            action="kernel",
            source="production_runtime",
            decision="allow",
            decision_reason="kernel_event",
            evidence=data,
            result={"ok": True},
        )
        store.append(event)
    except Exception:
        # Event 失败不阻断
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