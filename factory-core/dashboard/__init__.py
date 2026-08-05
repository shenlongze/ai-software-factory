"""dashboard — 只读 Dashboard (CLI 可视化控制台, Rich 非 Web)。

对外出口 (phase4c4-status.md): FactorySnapshot / DashboardCollector /
DashboardRenderer / 各视图构建函数。只读铁律: 本模块不写任何状态
(不修改 Task/Agent/Workflow/Execution/Event), 事件审计 (dashboard.viewed)
由 CLI 命令层经 EventLogger 发出。
"""

from .collector import DashboardCollector
from .models import (
    AgentSnapshot,
    CheckpointSnapshot,
    ExecutionSnapshot,
    FactorySnapshot,
    MetricsSnapshot,
    TaskSnapshot,
    ValidationSummary,
    WorkflowSnapshot,
)
from .renderer import DashboardRenderer, VIEWS

__all__ = [
    "DashboardCollector",
    "DashboardRenderer",
    "FactorySnapshot",
    "TaskSnapshot",
    "AgentSnapshot",
    "WorkflowSnapshot",
    "ExecutionSnapshot",
    "CheckpointSnapshot",
    "MetricsSnapshot",
    "ValidationSummary",
    "VIEWS",
]
