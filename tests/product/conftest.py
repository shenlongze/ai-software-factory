"""tests/product/conftest.py — Product Intelligence Layer 测试 fixtures (Phase 9A, ADR-0026)。

复用 tests/cli/cli_helpers (run_cli/open_events/event_types); helper 模块用唯一名
product_helpers (backend-developer skill 陷阱: 多非包目录共存时同名模块互相遮蔽;
本目录测试文件 basename 一律 test_product_* 前缀, 全仓库唯一)。

fixtures:
- product_dir: 独立 Product 数据空间 (<root>/product, 与 tasks/agents/providers 分离)
- store: ProductStore (纯持久化)
- logger / event_store: 事件集成断言 (idea.*/approval.*/product.* 生命周期)
- service / event_service: 无事件 / 带 EventLogger 的 ProductService
- task_store / agent_registry / workflow_store / runtime_store / checkpoint_store:
  Dashboard Product View 聚合测试 (与 tests/dashboard/conftest.py 同构,
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

from agents.registry import AgentRegistry
from agents.store import AgentStore
from dashboard.collector import DashboardCollector
from events.logger import EventLogger
from events.store import EventStore
from recovery.checkpoint import CheckpointStore
from runtime.store import RuntimeStore
from tasks.store import TaskStore
from workflows.store import WorkflowStore

from product.service import ProductService
from product.store import ProductStore


@pytest.fixture
def product_dir(tmp_path: Path) -> Path:
    """Product 数据空间 (<root>/product — 独立目录, 与 tasks/agents 分离)。"""
    return tmp_path / "factory" / "product"


@pytest.fixture
def store(product_dir: Path) -> ProductStore:
    return ProductStore(product_dir)


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
def service(store: ProductStore) -> ProductService:
    """无 logger 的纯存储 ProductService (事件相关测试另用 event_service)。"""
    return ProductService(store)


@pytest.fixture
def event_service(store: ProductStore, logger: EventLogger) -> ProductService:
    """带 EventLogger 的 ProductService (写路径事件集成断言)。"""
    return ProductService(store, logger=logger)


# ------------------------------------------------------------------ Dashboard Product View 聚合测试 (本目录自洽)

@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
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
def checkpoints_dir(factory_root: Path) -> Path:
    return factory_root / "checkpoints"


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
def checkpoint_store(checkpoints_dir: Path) -> CheckpointStore:
    return CheckpointStore(checkpoints_dir)


@pytest.fixture
def collector(
    task_store: TaskStore,
    agent_registry: AgentRegistry,
    workflow_store: WorkflowStore,
    runtime_store: RuntimeStore,
    event_store: EventStore,
    checkpoint_store: CheckpointStore,
) -> DashboardCollector:
    """默认装配的 DashboardCollector (全 store, 只读; 与 tests/dashboard 同构 —
    Phase 9d Lifecycle View 渲染器测试需要)。"""
    return DashboardCollector(
        task_store=task_store,
        agent_registry=agent_registry,
        workflow_store=workflow_store,
        runtime_store=runtime_store,
        event_store=event_store,
        checkpoint_store=checkpoint_store,
    )


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (CLI 测试, 每个测试隔离)。"""
    return tmp_path / "factory"
