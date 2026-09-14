"""orchestration — Execution Orchestration Flow (Phase 4C-2)。

把既有模块 (WorkflowEngine / AgentMatcher / AgentAllocator / ExecutionService /
RuntimeAdapter) 组装成自动生产流水线: Workflow → Matcher → Allocator → Execution →
Runner → Result → 推进; 失败 → Workflow FAILED (无半完成状态)。

对外出口: OrchestrationEngine / execute_workflow / OrchestrationOutcome /
StepOutcome / 编排错误类。
"""

from .engine import (
    OrchestrationEngine,
    OrchestrationError,
    OrchestrationOutcome,
    OrchestrationStateError,
    StepExecutionError,
    StepOutcome,
)
from .pipeline import execute_workflow

__all__ = [
    "OrchestrationEngine",
    "OrchestrationOutcome",
    "StepOutcome",
    "OrchestrationError",
    "OrchestrationStateError",
    "StepExecutionError",
    "execute_workflow",
]
