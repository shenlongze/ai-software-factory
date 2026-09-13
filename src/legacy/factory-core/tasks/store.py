"""tasks/store.py — TaskStore: JSON 文件持久化 (单任务单文件, 标准库零依赖)。

设计依据:
- phase2-status.md: Task Store (JSON/YAML 文件持久化), 不引入数据库
- 选型: `<root>/tasks/<id>.json` 单任务单文件 — 简单可靠, 无并发合并问题,
  与 cli-design init 目录骨架 (tasks/) 一致, 便于人工审计与 git 差异对比。

约定:
- 原子写: 临时文件 + os.replace, 避免半写文件。
- 单进程本地使用, 不做文件锁 (KISS); 并发写入由上层 (单 CLI 进程) 保证。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError

from .models import Task, TaskStatus


class TaskStoreError(Exception):
    """TaskStore 基础异常。"""


class TaskExistsError(TaskStoreError):
    """任务已存在 (create 时 id 冲突)。"""


class TaskNotFoundError(TaskStoreError):
    """任务不存在。"""


class TaskStore:
    """JSON 文件任务库。一个任务一个 `<id>.json` 文件。"""

    def __init__(self, tasks_dir: str | Path):
        self._dir = Path(tasks_dir)

    @property
    def dir(self) -> Path:
        return self._dir

    # ------------------------------------------------------------------ 写入

    def create(self, task: Task) -> Task:
        """写入新任务; id 已存在则抛 TaskExistsError。"""
        if self.get(task.id) is not None:
            raise TaskExistsError(f"task already exists: {task.id}")
        self._write(task)
        return task

    def update_status(self, task_id: str, status: TaskStatus | str) -> Task:
        """更新任务状态并刷新 updated_at; 不存在抛 TaskNotFoundError。"""
        task = self.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"task not found: {task_id}")
        task.status = status if isinstance(status, TaskStatus) else TaskStatus.parse(status)
        task.updated_at = datetime.now(timezone.utc)
        self._write(task)
        return task

    def _write(self, task: Task) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._dir / f".{task.id}.{os.getpid()}.tmp"
        tmp.write_text(
            json.dumps(task.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self._path(task.id))

    # ------------------------------------------------------------------ 读取

    def get(self, task_id: str) -> Task | None:
        """按 id 取任务; 不存在返回 None。"""
        path = self._path(task_id)
        if not path.exists():
            return None
        return self._load(path)

    def list(
        self,
        *,
        status: TaskStatus | str | None = None,
        project: str | None = None,
    ) -> list[Task]:
        """全部任务 (按 id 排序), 可选按状态/项目过滤。"""
        want_status = TaskStatus.parse(status) if isinstance(status, str) else status
        tasks: list[Task] = []
        if not self._dir.exists():
            return tasks
        for path in sorted(self._dir.glob("*.json")):
            if path.name.startswith("."):
                continue
            task = self._load(path)
            if want_status is not None and task.status is not want_status:
                continue
            if project is not None and task.project != project:
                continue
            tasks.append(task)
        return tasks

    def count(self) -> int:
        return len(self.list())

    def _load(self, path: Path) -> Task:
        try:
            return Task.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise TaskStoreError(f"corrupt task file: {path}: {exc}") from exc

    def _path(self, task_id: str) -> Path:
        return self._dir / f"{task_id}.json"

    # ------------------------------------------------------------------ 便捷

    def ids(self) -> list[str]:
        """现有任务 id 列表 (CLI 自动编号用)。"""
        return [t.id for t in self.list()]

    def next_id(self, prefix: str = "T-") -> str:
        """自动编号: 取现有最大数字后缀 +1 (如 T-001 → T-002)。"""
        max_n = 0
        for task_id in self.ids():
            rest = task_id[len(prefix):] if task_id.startswith(prefix) else ""
            if rest.isdigit():
                max_n = max(max_n, int(rest))
        return f"{prefix}{max_n + 1:03d}"
