"""tests/tasks/helpers.py — Task 构造 helper (测试共享)。"""

from __future__ import annotations

from tasks.models import Task


def make_task(task_id: str = "T-001", **overrides) -> Task:
    """默认任务; overrides 覆盖任意字段。"""
    defaults = {
        "id": task_id,
        "title": f"task {task_id}",
        "project": "default",
        "type": "feature",
    }
    defaults.update(overrides)
    return Task(**defaults)
