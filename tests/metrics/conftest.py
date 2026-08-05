"""tests/metrics/conftest.py — Metrics 测试 fixtures (sys.path 兜底同既有模式)。

复用 tests/cli/cli_helpers (run_cli/open_events/event_types) 与
tests/dashboard/dashboard_helpers (make_* 数据构造), 同 tests/dashboard/conftest.py 模式。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_CLI_TESTS = _ROOT / "tests" / "cli"
if str(_CLI_TESTS) not in sys.path:
    sys.path.insert(0, str(_CLI_TESTS))
_DASHBOARD_TESTS = _ROOT / "tests" / "dashboard"
if str(_DASHBOARD_TESTS) not in sys.path:  # 复用 dashboard_helpers (make_*)
    sys.path.insert(0, str(_DASHBOARD_TESTS))

import pytest

from agents.registry import AgentRegistry
from agents.store import AgentStore
from events.logger import EventLogger
from events.store import EventStore
from metrics.collectors import MetricsCollector
from runtime.store import RuntimeStore
from tasks.store import TaskStore
from workflows.store import WorkflowStore


# ------------------------------------------------------------------ 目录/存储 fixtures

@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (每个测试隔离)。"""
    return tmp_path / "factory"


@pytest.fixture
def tasks_dir(factory_root: Path) -> Path:
    return factory_root / "tasks"


@pytest.fixture
def agents_dir(factory_root: Path) -> Path:
    return factory_root / "agents"


@pytest.fixture
def workflows_dir(factory_root: Path) -> Path:
    return factory_root / "workflows"


@pytest.fixture
def runtimes_dir(factory_root: Path) -> Path:
    return factory_root / "runtimes"


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
def event_store(logger: EventLogger) -> EventStore:
    return logger.store


@pytest.fixture
def task_store(tasks_dir: Path) -> TaskStore:
    return TaskStore(tasks_dir)


@pytest.fixture
def agent_store(agents_dir: Path) -> AgentStore:
    return AgentStore(agents_dir)


@pytest.fixture
def agent_registry(agent_store: AgentStore) -> AgentRegistry:
    return AgentRegistry(agent_store)


@pytest.fixture
def workflow_store(workflows_dir: Path) -> WorkflowStore:
    return WorkflowStore(workflows_dir)


@pytest.fixture
def runtime_store(runtimes_dir: Path) -> RuntimeStore:
    return RuntimeStore(runtimes_dir)


@pytest.fixture
def collector(
    task_store: TaskStore,
    agent_registry: AgentRegistry,
    workflow_store: WorkflowStore,
    runtime_store: RuntimeStore,
    event_store: EventStore,
) -> MetricsCollector:
    """默认装配的 MetricsCollector (全 store, 只读)。"""
    return MetricsCollector(
        event_store=event_store,
        task_store=task_store,
        agent_registry=agent_registry,
        workflow_store=workflow_store,
        runtime_store=runtime_store,
    )


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (CLI 测试, 每个测试隔离)。"""
    return tmp_path / "factory"
