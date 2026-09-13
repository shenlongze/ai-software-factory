"""orchestration/pipeline.py — execute_workflow(task_id): 完整链路组合根。

设计依据:
- phase4c2-status.md: Pipeline: execute_workflow(task_id) 完整链路 — Step PENDING →
  Agent Assigned → Execution Created → Execution Running → SUCCESS → Step Completed;
  失败 (Execution FAILED / 无匹配 Agent / 无 Runtime / Step FAILED) → Workflow FAILED
  (不能半完成状态)。
- 模块调用规则 (phase4c2-status §2): 只组装不重写 — 本模块装配全部既有模块
  (WorkflowEngine / AgentRegistry / AgentAllocator / AgentMatcher / ExecutionService /
  RuntimeRegistry + 内置 Adapter 映射) 成 OrchestrationEngine 并执行, 不复制任何逻辑。
- 与 CLI 共用同一装配点 (commands.py 的 --auto 路径直接调本函数), 测试亦同 —
  单点组合根, KISS/DRY。
"""

from __future__ import annotations

from typing import Mapping

from agents.registry import AgentRegistry
from agents.store import AgentStore
from assignment.allocator import AgentAllocator
from assignment.matcher import AgentMatcher
from assignment.store import AssignmentStore
from events.logger import EventLogger
from execution.service import ExecutionService
from runtime.adapter import RuntimeAdapter
from runtime.adapters import BUILTIN_ADAPTERS
from runtime.registry import RuntimeRegistry
from runtime.store import RuntimeStore
from tasks.store import TaskStore
from workflows.engine import WorkflowEngine
from workflows.store import WorkflowStore

from .engine import OrchestrationEngine, OrchestrationOutcome


def execute_workflow(
    task_id: str,
    *,
    workflow_store: WorkflowStore,
    task_store: TaskStore,
    agent_store: AgentStore,
    assignment_store: AssignmentStore,
    runtime_store: RuntimeStore,
    logger: EventLogger | None = None,
    adapters: Mapping[str, RuntimeAdapter] | None = None,
) -> OrchestrationOutcome:
    """完整链路入口: 装配全部既有模块 → OrchestrationEngine.execute_workflow(task_id)。

    - adapters 缺省使用内置映射 (BUILTIN_ADAPTERS: echo mock + hermes-runtime);
      runtime 身份 (RuntimeInfo) 仍须已注册 (registry 是派发解析的唯一事实源,
      ADR-0007 决策 3)。
    - 失败 (执行期) → Workflow FAILED; 前置错误 → outcome.status=FAILED 不改状态。
    """
    agent_registry = AgentRegistry(agent_store, logger=logger)
    wf_engine = WorkflowEngine(
        workflow_store,
        task_store=task_store,
        logger=logger,
        runtime_store=runtime_store,
        agent_registry=agent_registry,
    )
    allocator = AgentAllocator(
        assignment_store, agent_registry, logger=logger, runtime_store=runtime_store,
    )
    service = ExecutionService(
        runtime_store,
        RuntimeRegistry(runtime_store, logger=logger),
        adapters=adapters if adapters is not None else BUILTIN_ADAPTERS,
        logger=logger,
        # 注意: 不绑定 workflow_engine — 步骤推进由 OrchestrationEngine 统一驱动
        # (避免 Runner 联动与编排推进重复 complete_step, ADR-0010 决策 3)。
    )
    engine = OrchestrationEngine(
        workflow_engine=wf_engine,
        allocator=allocator,
        matcher=AgentMatcher(agent_registry),
        execution_service=service,
        logger=logger,
    )
    return engine.execute_workflow(task_id)
