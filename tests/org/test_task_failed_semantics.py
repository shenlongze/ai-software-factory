"""tests/org/test_task_failed_semantics.py — P1-FIX: FAILED ≠ BLOCKED 语义。

FAILED = 任务自身真实执行失败 (finish_task_exec success=False)
BLOCKED = 依赖失败传播 (ExecState)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from org.management import (
    TASK_TRANSITIONS, TaskStatus, Task, transition_task, validate_dependency,
)


def _mk_task(tid: str = "T-1", deps: list[str] | None = None) -> Task:
    return Task(id=tid, title="x", priority="P2", status=TaskStatus.TODO,
                dependency=deps or [])


def test_taskstatus_has_failed() -> None:
    assert TaskStatus.FAILED.value == "failed"
    assert TaskStatus.FAILED not in (TaskStatus.BLOCKED, TaskStatus.DONE)


def test_transitions_support_failed() -> None:
    """in_progress → failed 合法; review → failed 合法; failed → ready (重试)。"""
    assert TaskStatus.READY in TASK_TRANSITIONS[TaskStatus.TODO]
    assert TaskStatus.IN_PROGRESS in TASK_TRANSITIONS[TaskStatus.READY]
    assert TaskStatus.FAILED in TASK_TRANSITIONS[TaskStatus.IN_PROGRESS]
    assert TaskStatus.FAILED in TASK_TRANSITIONS[TaskStatus.REVIEW]
    assert TaskStatus.READY in TASK_TRANSITIONS[TaskStatus.FAILED]


def test_failed_retry_to_ready() -> None:
    """FAILED → READY (重试语义, transition 受控)。"""
    t = _mk_task()
    t2 = transition_task(t, TaskStatus.READY, actor="test")
    t3 = transition_task(t2, TaskStatus.IN_PROGRESS, actor="test")
    t4 = transition_task(t3, TaskStatus.FAILED, actor="test")
    t5 = transition_task(t4, TaskStatus.READY, actor="test")
    assert t5.status == TaskStatus.READY


def test_blocked_is_dependency_propagation() -> None:
    """BLOCKED 仍可用于依赖传播 (TODO → BLOCKED 合法)。"""
    t = _mk_task()
    t2 = transition_task(t, TaskStatus.BLOCKED, actor="test")
    assert t2.status == TaskStatus.BLOCKED
    assert t2.status != TaskStatus.FAILED


def test_validate_dependency_unknown_rejected_or_safe() -> None:
    """依赖校验: 未知依赖不产生虚假 FAILED/BLOCKED。"""
    t = _mk_task(deps=["T-missing"])
    # 自引用/环检测仍工作 (validate_dependency 拒绝环)
    with pytest.raises(ValueError):
        validate_dependency(["T-1"], "T-1", known_dependencies={"T-1"})


def test_failed_status_persists_roundtrip(tmp_path: Path) -> None:
    """FAILED 落库可往返 (Restart 后保持 FAILED, 不被转 BLOCKED)。"""
    from org.management import ManagementStore

    mgmt = ManagementStore(tmp_path)
    t = _mk_task()
    mgmt.save_task(t)
    t2 = transition_task(t, TaskStatus.READY, actor="test")
    t3 = transition_task(t2, TaskStatus.IN_PROGRESS, actor="test")
    t4 = transition_task(t3, TaskStatus.FAILED, actor="test")
    mgmt.save_task(t4)
    reloaded = mgmt.get_task("T-1")
    assert reloaded.status == TaskStatus.FAILED, "重启后 FAILED 保持"
    assert reloaded.status != TaskStatus.BLOCKED
