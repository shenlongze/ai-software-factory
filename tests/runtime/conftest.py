"""tests/runtime/conftest.py — Runtime 测试 fixtures (sys.path 兜底同 workflows 模式)。"""

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

from agents.registry import AgentRegistry
from agents.store import AgentStore
from events.logger import EventLogger
from events.store import EventStore
from runtime.registry import RuntimeRegistry
from runtime.store import RuntimeStore
from tasks.store import TaskStore
from workflows.engine import WorkflowEngine
from workflows.store import WorkflowStore


@pytest.fixture
def runtimes_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "runtimes"


@pytest.fixture
def workflows_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "workflows"


@pytest.fixture
def tasks_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "tasks"


@pytest.fixture
def agents_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "agents"


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
def runtime_store(runtimes_dir: Path) -> RuntimeStore:
    return RuntimeStore(runtimes_dir)


@pytest.fixture
def workflow_store(workflows_dir: Path) -> WorkflowStore:
    return WorkflowStore(workflows_dir)


@pytest.fixture
def task_store(tasks_dir: Path) -> TaskStore:
    return TaskStore(tasks_dir)


@pytest.fixture
def agent_store(agents_dir: Path) -> AgentStore:
    return AgentStore(agents_dir)


@pytest.fixture
def registry(runtime_store: RuntimeStore) -> RuntimeRegistry:
    """无 logger 的纯存储 RuntimeRegistry (事件相关测试另用 event_registry)。"""
    return RuntimeRegistry(runtime_store)


@pytest.fixture
def event_registry(runtime_store: RuntimeStore, logger: EventLogger) -> RuntimeRegistry:
    """带 EventLogger 的 RuntimeRegistry (事件集成断言)。"""
    return RuntimeRegistry(runtime_store, logger=logger)


@pytest.fixture
def engine(runtime_store: RuntimeStore, workflow_store: WorkflowStore, task_store: TaskStore) -> WorkflowEngine:
    """无 logger 的 WorkflowEngine (含 runtime_store, 可测 execute_step)。"""
    return WorkflowEngine(workflow_store, task_store=task_store, runtime_store=runtime_store)


@pytest.fixture
def event_engine(
    runtime_store: RuntimeStore, workflow_store: WorkflowStore,
    task_store: TaskStore, logger: EventLogger,
) -> WorkflowEngine:
    """带 EventLogger 的 WorkflowEngine (execute_step 事件集成断言)。"""
    return WorkflowEngine(workflow_store, task_store=task_store, logger=logger, runtime_store=runtime_store)


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (CLI 测试, 每个测试隔离)。"""
    return tmp_path / "factory"
