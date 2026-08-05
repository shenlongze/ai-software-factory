"""tests/assignment/conftest.py — Agent Assignment 测试 fixtures (sys.path 兜底同 agents 模式)。"""

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
from assignment.allocator import AgentAllocator
from assignment.matcher import AgentMatcher
from assignment.store import AssignmentStore
from events.logger import EventLogger
from events.store import EventStore
from runtime.store import RuntimeStore


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (CLI 测试, 每个测试隔离)。"""
    return tmp_path / "factory"


@pytest.fixture
def assignments_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "assignments"


@pytest.fixture
def agents_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "agents"


@pytest.fixture
def runtimes_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "runtimes"


@pytest.fixture
def assignment_store(assignments_dir: Path) -> AssignmentStore:
    return AssignmentStore(assignments_dir)


@pytest.fixture
def agent_store(agents_dir: Path) -> AgentStore:
    return AgentStore(agents_dir)


@pytest.fixture
def agent_registry(agent_store: AgentStore) -> AgentRegistry:
    """无 logger 的纯存储 AgentRegistry (事件相关测试另用 logger fixture)。"""
    return AgentRegistry(agent_store)


@pytest.fixture
def runtime_store(runtimes_dir: Path) -> RuntimeStore:
    return RuntimeStore(runtimes_dir)


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
def matcher(agent_registry: AgentRegistry) -> AgentMatcher:
    return AgentMatcher(agent_registry)


@pytest.fixture
def allocator(assignment_store: AssignmentStore, agent_registry: AgentRegistry) -> AgentAllocator:
    """无 logger/runtime_store 的纯存储 Allocator (事件/执行集成测试另用专属 fixture)。"""
    return AgentAllocator(assignment_store, agent_registry)


@pytest.fixture
def event_allocator(
    assignment_store: AssignmentStore, agent_registry: AgentRegistry, logger: EventLogger,
) -> AgentAllocator:
    """带 EventLogger 的 Allocator (事件集成断言)。"""
    return AgentAllocator(assignment_store, agent_registry, logger=logger)


@pytest.fixture
def exec_allocator(
    assignment_store: AssignmentStore,
    agent_registry: AgentRegistry,
    runtime_store: RuntimeStore,
    logger: EventLogger,
) -> AgentAllocator:
    """带 EventLogger + RuntimeStore 的 Allocator (Execution 集成断言)。"""
    return AgentAllocator(
        assignment_store, agent_registry, logger=logger, runtime_store=runtime_store,
    )
