"""tests/runtime/runtime_helpers.py — Runtime 测试数据构造 (平铺模块, 唯一名防遮蔽)。

注意: 与其他测试目录的 helpers.py 不同名, 避免多非包目录共存时的模块遮蔽
(backend-developer skill 陷阱记录); 工作流/任务构造自包含, 不跨目录 import。
"""

from __future__ import annotations

from runtime.models import ExecutionRequest, ExecutionResult, RuntimeInfo
from tasks.models import Task
from workflows.models import Workflow, WorkflowStep


def make_runtime(runtime_id: str = "R-001", **overrides) -> RuntimeInfo:
    """默认 Runtime; overrides 覆盖任意字段。"""
    defaults = {
        "id": runtime_id,
        "name": f"runtime {runtime_id}",
        "type": "agent",
        "description": "默认测试 Runtime",
    }
    defaults.update(overrides)
    return RuntimeInfo(**defaults)


def make_request(request_id: str = "EX-001", **overrides) -> ExecutionRequest:
    """默认执行请求; overrides 覆盖任意字段。"""
    defaults = {
        "id": request_id,
        "task_id": "T-001",
        "workflow_id": "wf-test",
        "step_id": "architecture",
        "input": {"prompt": "do the thing"},
    }
    defaults.update(overrides)
    return ExecutionRequest(**defaults)


def make_result(result_id: str = "EXR-001", **overrides) -> ExecutionResult:
    """默认执行结果; overrides 覆盖任意字段。"""
    defaults = {
        "id": result_id,
        "request_id": "EX-001",
        "output": {"summary": "done"},
    }
    defaults.update(overrides)
    return ExecutionResult(**defaults)


def make_workflow(workflow_id: str = "wf-test", *, steps: list[str] | None = None) -> Workflow:
    """构造工作流定义; 缺省两步主干 (s1, s2)。"""
    if steps is None:
        steps = ["s1", "s2"]
    return Workflow(
        id=workflow_id,
        name=f"{workflow_id} 测试",
        description="测试定义",
        steps=[WorkflowStep(id=s, name=s, order=i + 1) for i, s in enumerate(steps)],
    )


def make_task(task_id: str = "T-001", *, workflow: str | None = "wf-test", **overrides) -> Task:
    """构造任务 (直接经 Task 模型, 不走 CLI/事件)。"""
    defaults = {
        "id": task_id,
        "title": f"任务 {task_id}",
        "project": "markpad",
        "type": "feature",
        "workflow": workflow,
    }
    defaults.update(overrides)
    return Task(**defaults)
