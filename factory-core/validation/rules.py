"""validation/rules.py — 三层验证规则 (纯函数, 不发事件)。

设计依据 (phase3a-status.md + 父任务):
- L1 Factory Validation: ① Task 是否存在 ② Task 数据合法 ③ Task 状态合法 ④ Task 文件完整
- L2 Workflow Validation: 事件历史是否满足流程要求 (状态一致性; 无 workflow 定义 → SKIP)
- L3 Artifact Validation: Hook 占位 → SKIP (预留 Flutter/Java/Python 验证器接口)

铁律: 规则只做判定, 事件由 ValidationEngine 统一经 EventLogger 发布 (不绕过)。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from events.models import Event, EventType
from tasks.models import Task, TaskStatus

from .models import ValidationResult, ValidationStatus

# 规则 → 人类可读名 (checks 载荷 / 报告展示)
RULE_NAMES: dict[str, str] = {
    "task_exists": "任务存在",
    "task_data": "任务数据合法",
    "task_status": "任务状态合法",
    "task_files": "任务文件完整",
    "workflow": "流程事件历史",
    "expect_status": "期望状态",
    "artifact": "Artifact 验证 Hook",
}

# L1 文件完整性必填键 (任务文件 JSON 顶层)
_REQUIRED_KEYS = ("id", "title", "project", "status")

# L2 状态历史来源事件 (事件词汇: task.created 记录初始状态, task.updated 记录流转)
_STATUS_EVENT_TYPES = (EventType.TASK_CREATED, EventType.TASK_UPDATED)


def _res(
    task_id: str, level: str, rule: str, status: ValidationStatus, message: str,
) -> ValidationResult:
    return ValidationResult(
        id=f"{level}.{rule}", task_id=task_id, level=level,
        rule=rule, status=status, message=message,
    )


# ------------------------------------------------------------------ L1 Factory

def rule_task_exists(task_id: str, path: Path) -> ValidationResult:
    """① Task 是否存在: 任务 JSON 文件存在。"""
    if path.exists():
        return _res(task_id, "L1", "task_exists", ValidationStatus.PASS, "任务文件存在")
    return _res(task_id, "L1", "task_exists", ValidationStatus.FAIL, f"task not found: {task_id}")


def rule_task_data(task_id: str, data: Any, error: str | None = None) -> ValidationResult:
    """② Task 数据合法: JSON 可解析 + 通过 Task 模型校验。

    data 为已解析 JSON dict; None 表示文件缺失 (SKIP) 或损坏 (error 非空 → FAIL)。
    """
    if data is None:
        if error:
            return _res(task_id, "L1", "task_data", ValidationStatus.FAIL, f"任务数据不合法: {error}")
        return _res(task_id, "L1", "task_data", ValidationStatus.SKIP, "任务文件缺失, 跳过数据校验")
    try:
        Task.model_validate(data)
    except ValidationError as exc:
        return _res(task_id, "L1", "task_data", ValidationStatus.FAIL, f"任务数据不合法: {exc}")
    return _res(task_id, "L1", "task_data", ValidationStatus.PASS, "任务数据合法")


def rule_task_status(task_id: str, data: Any) -> ValidationResult:
    """③ Task 状态合法: status 是五状态生命周期之一 (TaskStatus.parse)。"""
    if data is None:
        return _res(task_id, "L1", "task_status", ValidationStatus.SKIP, "任务数据不可用, 跳过状态校验")
    raw = data.get("status")
    try:
        status = TaskStatus.parse(raw)
    except ValueError as exc:
        return _res(task_id, "L1", "task_status", ValidationStatus.FAIL, str(exc))
    return _res(task_id, "L1", "task_status", ValidationStatus.PASS, f"状态 {status.value} 合法")


def rule_task_files(task_id: str, data: Any) -> ValidationResult:
    """④ Task 文件完整: 必填键存在且非空 (id/title/project/status)。"""
    if data is None:
        return _res(task_id, "L1", "task_files", ValidationStatus.SKIP, "任务数据不可用, 跳过文件完整性校验")
    missing = [k for k in _REQUIRED_KEYS if not data.get(k)]
    if missing:
        return _res(task_id, "L1", "task_files", ValidationStatus.FAIL, f"任务文件不完整, 缺少字段: {missing}")
    return _res(task_id, "L1", "task_files", ValidationStatus.PASS, "任务文件完整")


# ------------------------------------------------------------------ L2 Workflow

def rule_workflow(task_id: str, task: Task | None, events: list[Event]) -> ValidationResult:
    """L2 流程校验: 事件历史须支撑当前任务状态。

    - 无 workflow 定义 → SKIP (父任务约定)
    - 状态事件历史与当前状态一致 → PASS
    - 不一致 (如状态 DEVELOPMENT 但无对应 task.updated 事件) → FAIL
    """
    if task is None:
        return _res(task_id, "L2", "workflow", ValidationStatus.SKIP, "无任务数据, 跳过流程校验")
    if not (task.workflow or "").strip():
        return _res(task_id, "L2", "workflow", ValidationStatus.SKIP, "无 workflow 定义")
    status_events = [e for e in events if e.type in _STATUS_EVENT_TYPES]
    if not status_events:
        return _res(task_id, "L2", "workflow", ValidationStatus.FAIL, "事件历史中无状态记录")
    last = status_events[-1]
    if last.type is EventType.TASK_UPDATED:
        recorded = last.payload.get("to")
    else:  # task.created: 初始状态记在 stage 列 (如 backlog)
        recorded = (last.stage or "").upper() or None
    if not recorded:
        return _res(task_id, "L2", "workflow", ValidationStatus.FAIL, "事件历史无法确定任务状态")
    try:
        recorded = TaskStatus.parse(recorded).value
    except ValueError as exc:
        return _res(task_id, "L2", "workflow", ValidationStatus.FAIL, str(exc))
    if recorded != task.status.value:
        return _res(
            task_id, "L2", "workflow", ValidationStatus.FAIL,
            f"事件历史与任务状态不一致: 历史 {recorded}, 当前 {task.status.value}",
        )
    return _res(task_id, "L2", "workflow", ValidationStatus.PASS, "事件历史与任务状态一致")


def rule_expect_status(
    task_id: str, task: Task | None, expect: TaskStatus | None,
) -> ValidationResult:
    """期望状态门 (Phase 2 CLI --expect-status 契约): 实际状态须等于期望状态。"""
    if expect is None:
        return _res(task_id, "L2", "expect_status", ValidationStatus.SKIP, "未指定期望状态")
    if task is None:
        return _res(task_id, "L2", "expect_status", ValidationStatus.SKIP, "任务不存在, 跳过期望状态校验")
    if task.status is expect:
        return _res(task_id, "L2", "expect_status", ValidationStatus.PASS,
                    f"状态 {expect.value} 符合期望")
    return _res(task_id, "L2", "expect_status", ValidationStatus.FAIL,
                f"期望状态 {expect.value}, 实际 {task.status.value}")


# ------------------------------------------------------------------ L3 Artifact Hook

def rule_artifact(task_id: str) -> ValidationResult:
    """L3 Artifact 验证: Hook 占位 → SKIP (预留 Flutter/Java/Python 验证器接口)。"""
    return _res(task_id, "L3", "artifact", ValidationStatus.SKIP,
                "Artifact 验证 Hook 未实现 (预留 Flutter/Java/Python 验证器)")


# ------------------------------------------------------------------ 加载辅助

def load_task_file(task_id: str, tasks_dir: Path) -> tuple[Any, Task | None, str | None]:
    """读取任务原始 JSON + 构建 Task 模型。

    返回 (data, task, error):
    - data: 已解析 JSON dict; 文件缺失或 JSON 无法解析时为 None
      (模型校验失败时保留原始数据, 供细粒度规则 task_status/task_files 继续诊断)
    - task: Task 模型; 不可用时为 None
    - error: 数据错误信息 (仅损坏/非法时非 None)
    """
    path = tasks_dir / f"{task_id}.json"
    if not path.exists():
        return None, None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, None, str(exc)
    try:
        task = Task.model_validate(data)
        return data, task, None
    except ValidationError as exc:
        return data, None, str(exc)
