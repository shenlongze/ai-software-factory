"""tests/validation/conftest.py — Validation Engine 测试根目录 fixture (sys.path 兜底同 events/cli 模式)。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

import pytest

from events.logger import EventLogger
from events.store import EventStore
from tasks.store import TaskStore
from validation.engine import ValidationEngine


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (每个测试隔离)。"""
    return tmp_path / "factory"


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """CLI 测试独立根目录。"""
    return tmp_path / "factory"


@pytest.fixture
def event_store(factory_root: Path) -> EventStore:
    """临时事件库 (引擎测试直接断言事件)。"""
    factory_root.mkdir(parents=True, exist_ok=True)
    store = EventStore(factory_root / "factory.db")
    yield store
    store.close()


@pytest.fixture
def logger(event_store: EventStore) -> EventLogger:
    return EventLogger(event_store)


@pytest.fixture
def task_store(factory_root: Path) -> TaskStore:
    return TaskStore(factory_root / "tasks")


@pytest.fixture
def engine(task_store: TaskStore, logger: EventLogger) -> ValidationEngine:
    return ValidationEngine(task_store=task_store, logger=logger, source="test")
