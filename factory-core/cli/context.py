"""cli/context.py — 工厂上下文: 根目录布局 + EventStore/EventLogger/TaskStore 装配。

布局 (ADR-0002 + ADR-0004):
```
<root>/                 (默认 ~/.factory, --root 覆盖)
├── factory.db          SQLite EventStore (events 表, WAL)
├── tasks/              TaskStore JSON 文件
├── agents/             AgentStore JSON (agents.json)  [Phase 3B]
├── skills/             SkillStore JSON (skills.json)  [Phase 3B]
├── workflows/          Phase 3 占位
└── events/             Phase 3 占位 (事件导出等)
```

所有命令先 ensure_dirs() (幂等), 保证 init 之前也能安全运行; init 负责显式发 system.init。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from agents.store import AgentStore, SkillStore
from events.logger import EventLogger
from events.store import EventStore
from tasks.store import TaskStore

DEFAULT_ROOT = Path.home() / ".factory"

# 目录骨架 (phase2-status 指令清单 + phase3b-status: skills/), 优先于 cli-design 的 projects/roles/skills/workflows
_SUBDIRS = ("tasks", "agents", "skills", "workflows", "events")


class FactoryContext:
    """一个工厂根目录下的全部存储装配点。"""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root is not None else DEFAULT_ROOT

    # ------------------------------------------------------------------ 路径

    @property
    def tasks_dir(self) -> Path:
        return self.root / "tasks"

    @property
    def agents_dir(self) -> Path:
        return self.root / "agents"

    @property
    def skills_dir(self) -> Path:
        return self.root / "skills"

    @property
    def workflows_dir(self) -> Path:
        return self.root / "workflows"

    @property
    def events_dir(self) -> Path:
        return self.root / "events"

    @property
    def db_path(self) -> Path:
        return self.root / "factory.db"

    def subdirs(self) -> list[Path]:
        return [getattr(self, f"{name}_dir") for name in _SUBDIRS]

    # ------------------------------------------------------------------ 生命周期

    def ensure_dirs(self) -> None:
        """幂等创建根目录与骨架目录 (SQLite 与 TaskStore 的前置)。"""
        self.root.mkdir(parents=True, exist_ok=True)
        for d in self.subdirs():
            d.mkdir(parents=True, exist_ok=True)

    def open_store(self) -> EventStore:
        """打开事件库 (须先 ensure_dirs, 调用方负责 close)。"""
        return EventStore(self.db_path)

    @contextmanager
    def logger_scope(self) -> Iterator[EventLogger]:
        """打开 EventStore + EventLogger 的作用域; 退出时关闭连接 (WAL 回收)。"""
        store = self.open_store()
        try:
            yield EventLogger(store)
        finally:
            store.close()

    def open_task_store(self) -> TaskStore:
        return TaskStore(self.tasks_dir)

    def open_agent_store(self) -> AgentStore:
        """Agent 注册表存储 (JSON: <root>/agents/agents.json)。"""
        return AgentStore(self.agents_dir)

    def open_skill_store(self) -> SkillStore:
        """Skill 注册表存储 (JSON: <root>/skills/skills.json)。"""
        return SkillStore(self.skills_dir)
