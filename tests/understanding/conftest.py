"""tests/understanding/conftest.py — Project Understanding Layer 测试 fixtures (Phase 7, ADR-0021)。

复用 tests/cli/cli_helpers (run_cli/open_events/event_types); helper 模块用唯一名
understanding_helpers (backend-developer skill 陷阱: 多非包目录共存时同名模块互相遮蔽)。

fixtures:
- logger / event_store: 事件集成断言 (UnderstandingService 分析事件)
- task_store / agent_registry / workflow_store / runtime_store / checkpoint_store:
  Dashboard Understanding View 聚合测试 (与 tests/dashboard/conftest.py 同构,
  本目录自洽 — conftest 按目录层级发现, 不跨目录依赖)
- cli_root: 独立工厂根 (CLI 测试)
"""

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


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "events.db"


@pytest.fixture
def logger(db_path: Path) -> EventLogger:
    """带事件库的 EventLogger (事件集成断言); 退出时关闭连接。"""
    s = EventStore(db_path)
    yield EventLogger(s)
    s.close()


@pytest.fixture
def event_store(logger: EventLogger):
    return logger.store


@pytest.fixture
def task_store(tmp_path: Path):
    from tasks.store import TaskStore

    return TaskStore(tmp_path / "tasks")


@pytest.fixture
def agent_registry(tmp_path: Path):
    from agents.registry import AgentRegistry
    from agents.store import AgentStore

    return AgentRegistry(AgentStore(tmp_path / "agents"))


@pytest.fixture
def workflow_store(tmp_path: Path):
    from workflows.store import WorkflowStore

    return WorkflowStore(tmp_path / "workflows")


@pytest.fixture
def runtime_store(tmp_path: Path):
    from runtime.store import RuntimeStore

    return RuntimeStore(tmp_path / "runtimes")


@pytest.fixture
def checkpoint_store(tmp_path: Path):
    from recovery.checkpoint import CheckpointStore

    return CheckpointStore(tmp_path / "checkpoints")


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (CLI 测试, 每个测试隔离)。"""
    return tmp_path / "factory"
