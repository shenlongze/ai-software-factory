"""changeflow — Change Driven Workflow Layer (Phase 6E, ADR-0020)。

Git Change 成为 Workflow 驱动事件: ChangeTrigger (声明式规则) + 4 规则引擎
(Validation L4 / Commit linked / Required files / Runtime pref) +
ChangeWorkflowEngine (评估通过 → 触发并执行下一 workflow)。

复用不复制: 规则输入来自 change 层 (ChangeService), 触发执行复用
workflows (WorkflowEngine/WorkflowStore) 与 orchestration (pipeline),
本模块不修改任何既有模块。
"""

from .engine import ChangeFlowError, ChangeWorkflowEngine
from .events import (
    record_change_trigger_created,
    record_change_trigger_evaluated,
    record_change_trigger_viewed,
    record_change_workflow_completed,
    record_change_workflow_started,
)
from .models import ChangeEvaluation, ChangeTrigger, RuleResult
from .rules import RuleContext, evaluate_rules, overall_status
from .triggers import (
    ChangeTriggerExistsError,
    ChangeTriggerNotFoundError,
    ChangeTriggerRegistry,
)

__all__ = [
    "ChangeEvaluation",
    "ChangeFlowError",
    "ChangeTrigger",
    "ChangeTriggerExistsError",
    "ChangeTriggerNotFoundError",
    "ChangeTriggerRegistry",
    "ChangeWorkflowEngine",
    "RuleContext",
    "RuleResult",
    "evaluate_rules",
    "overall_status",
    "record_change_trigger_created",
    "record_change_trigger_evaluated",
    "record_change_trigger_viewed",
    "record_change_workflow_completed",
    "record_change_workflow_started",
]
