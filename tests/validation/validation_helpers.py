"""tests/validation/validation_helpers.py — Validation 测试辅助 (唯一名, 避免与 events/cli 的 helpers.py 遮蔽)。

注意: 本目录测试文件用唯一 basename (test_validation_*.py / test_cli_validate_report.py),
helper 用唯一模块名 (validation_helpers.py), 避免多测试目录共存时的 import 遮蔽 (ADR-0002 经验)。
"""

from __future__ import annotations

import json
from pathlib import Path

from events.logger import EventLogger
from events.models import EventType
from tasks.models import Task
from tasks.store import TaskStore


def create_task(task_store: TaskStore, task_id: str = "T-001", **kwargs: object) -> Task:
    """写任务文件 (不走事件; 事件由 record_created/record_updated 单独发)。"""
    defaults: dict[str, object] = dict(
        title="实现撤销/重做", project="markpad", workflow="feature-delivery",
    )
    defaults.update(kwargs)
    task = Task(id=task_id, **defaults)
    task_store.create(task)
    return task


def write_raw_task(tasks_dir: Path, task_id: str, content: str) -> Path:
    """直接写任务 JSON 文件 (构造损坏/非法/缺失字段等场景)。"""
    tasks_dir.mkdir(parents=True, exist_ok=True)
    path = tasks_dir / f"{task_id}.json"
    path.write_text(content, encoding="utf-8")
    return path


def record_created(logger: EventLogger, task_id: str = "T-001", status: str = "BACKLOG") -> None:
    """发 task.created 事件 (初始状态记 stage 列, 与 CLI 一致)。"""
    logger.record(
        EventType.TASK_CREATED, source="test", project_id="markpad", task_id=task_id,
        stage=status.lower(), action="create task", result="OK",
    )


def record_updated(logger: EventLogger, task_id: str = "T-001", to: str = "DEVELOPMENT") -> None:
    """发 task.updated 事件 (目标状态记 payload.to, 与 CLI 一致)。"""
    logger.record(
        EventType.TASK_UPDATED, source="test", project_id="markpad", task_id=task_id,
        stage=to.lower(), action="update task status", result="OK",
        payload={"from": "BACKLOG", "to": to},
    )


def read_task_file(tasks_dir: Path, task_id: str) -> dict:
    """读任务 JSON 原始内容 (规则输入构造)。"""
    return json.loads((tasks_dir / f"{task_id}.json").read_text(encoding="utf-8"))
