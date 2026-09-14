"""metrics — Factory Metrics Intelligence Layer (Phase 5B, 只读)。

对外出口 (phase5b-status.md + ADR-0015): FactoryMetrics / MetricsCollector /
各域计算纯函数 / format_metrics 报告 / MetricsStore 可选快照。
只读铁律: 本模块不写任何状态 (不修改 Task/Agent/Workflow/Execution/Event),
事件审计 (metrics.viewed) 由 CLI 命令层 (cmd_metrics) 经 EventLogger 发出。
"""

from .calculators import (
    calculate_agent_metrics,
    calculate_execution_metrics,
    calculate_failure_metrics,
    calculate_failure_reason_count,
    calculate_first_attempt_success_rate,
    calculate_task_metrics,
    calculate_validation_metrics,
    calculate_workflow_metrics,
)
from .collectors import MetricsCollector
from .models import (
    AgentMetric,
    ExecutionMetrics,
    FactoryMetrics,
    FailureMetrics,
    TaskMetrics,
    ValidationMetrics,
    WorkflowMetrics,
)
from .reports import format_metrics
from .store import CorruptMetricsStoreError, MetricsStore, MetricsStoreError

__all__ = [
    "FactoryMetrics",
    "MetricsCollector",
    "TaskMetrics",
    "ExecutionMetrics",
    "AgentMetric",
    "WorkflowMetrics",
    "ValidationMetrics",
    "FailureMetrics",
    "calculate_task_metrics",
    "calculate_execution_metrics",
    "calculate_first_attempt_success_rate",
    "calculate_agent_metrics",
    "calculate_workflow_metrics",
    "calculate_validation_metrics",
    "calculate_failure_reason_count",
    "calculate_failure_metrics",
    "format_metrics",
    "MetricsStore",
    "MetricsStoreError",
    "CorruptMetricsStoreError",
]
