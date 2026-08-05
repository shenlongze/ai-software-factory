"""tests/workflows/conftest.py — Workflow Engine 测试 fixtures (sys.path 兜底同 agents 模式)。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_CLI_TESTS = _ROOT / "tests" / "cli"
if str(_CLI_TESTS) not in sys.path:  # 复用 cli_helpers (run_cli/open_events/event_types)
    sys.path.insert(0, str(_CLI_TESTS))

import pytest

from events.logger import EventLogger
from events.store import EventStore
from tasks.store import TaskStore
from workflows.engine import WorkflowEngine
from workflows.store import WorkflowStore


@pytest.fixture
def workflows_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "workflows"


@pytest.fixture
def tasks_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "tasks"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "events.db"


@pytest.fixture
def logger(db_path: Path) -> EventLogger:
    """带事件库的 EventLogger (测试事件集成); 退出时关闭连接。"""
    s = EventStore(db_path)
    yield EventLogger(s)
    s.close()


@pytest.fixture
def task_store(tasks_dir: Path) -> TaskStore:
    return TaskStore(tasks_dir)


@pytest.fixture
def workflow_store(workflows_dir: Path) -> WorkflowStore:
    return WorkflowStore(workflows_dir)


@pytest.fixture
def engine(workflow_store: WorkflowStore, task_store: TaskStore) -> WorkflowEngine:
    """无 logger 的纯存储 WorkflowEngine (事件相关测试另用 logger fixture 显式传入)。"""
    return WorkflowEngine(workflow_store, task_store=task_store)


@pytest.fixture
def event_engine(workflow_store: WorkflowStore, task_store: TaskStore, logger: EventLogger) -> WorkflowEngine:
    """带 EventLogger 的 WorkflowEngine (事件集成断言)。"""
    return WorkflowEngine(workflow_store, task_store=task_store, logger=logger)


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (CLI 测试, 每个测试隔离)。"""
    return tmp_path / "factory"
