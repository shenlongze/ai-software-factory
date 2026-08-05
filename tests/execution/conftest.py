"""tests/execution/conftest.py — Execution 派发层测试 fixtures (sys.path 兜底同 runtime 模式)。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_RUNTIME_TESTS = _ROOT / "tests" / "runtime"
if str(_RUNTIME_TESTS) not in sys.path:  # 复用 runtime_helpers (make_request/make_runtime/...)
    sys.path.insert(0, str(_RUNTIME_TESTS))
_CLI_TESTS = _ROOT / "tests" / "cli"
if str(_CLI_TESTS) not in sys.path:  # 复用 cli_helpers (run_cli/open_events/event_types)
    sys.path.insert(0, str(_CLI_TESTS))

import pytest

from events.logger import EventLogger
from events.store import EventStore
from execution.dispatcher import ExecutionDispatcher
from execution.runner import ExecutionRunner
from execution.service import ExecutionService
from runtime.adapters import BUILTIN_ADAPTERS
from runtime.models import RuntimeInfo
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
    """带事件库的 EventLogger (事件集成断言); 退出时关闭连接。"""
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
def registry(runtime_store: RuntimeStore) -> RuntimeRegistry:
    """无 logger 的 RuntimeRegistry (身份注册 + 派发解析)。"""
    return RuntimeRegistry(runtime_store)


@pytest.fixture
def event_registry(runtime_store: RuntimeStore, logger: EventLogger) -> RuntimeRegistry:
    return RuntimeRegistry(runtime_store, logger=logger)


def register_echo(registry: RuntimeRegistry) -> RuntimeInfo:
    """注册内置 echo runtime 身份 (id="echo", type="mock", AVAILABLE)。"""
    return registry.register(
        RuntimeInfo(id="echo", name="echo", type="mock", description="内置 mock runtime")
    )[0]


@pytest.fixture
def echo_dispatcher(registry: RuntimeRegistry) -> ExecutionDispatcher:
    """带内置 Adapter 映射的 Dispatcher (身份未注册时 resolve 失败 — 测试显式控制)。"""
    return ExecutionDispatcher(registry, adapters=BUILTIN_ADAPTERS)


@pytest.fixture
def runner(runtime_store: RuntimeStore, echo_dispatcher: ExecutionDispatcher) -> ExecutionRunner:
    """无 logger / 无联动引擎的 ExecutionRunner。"""
    return ExecutionRunner(runtime_store, echo_dispatcher)


@pytest.fixture
def event_runner(
    runtime_store: RuntimeStore, echo_dispatcher: ExecutionDispatcher, logger: EventLogger,
) -> ExecutionRunner:
    return ExecutionRunner(runtime_store, echo_dispatcher, logger=logger)


@pytest.fixture
def wf_engine(
    runtime_store: RuntimeStore, workflow_store: WorkflowStore, task_store: TaskStore,
) -> WorkflowEngine:
    """含 runtime_store 的 WorkflowEngine (execute_step 造请求 + 联动 complete/fail)。"""
    return WorkflowEngine(workflow_store, task_store=task_store, runtime_store=runtime_store)


@pytest.fixture
def event_wf_engine(
    runtime_store: RuntimeStore, workflow_store: WorkflowStore,
    task_store: TaskStore, logger: EventLogger,
) -> WorkflowEngine:
    return WorkflowEngine(
        workflow_store, task_store=task_store, logger=logger, runtime_store=runtime_store,
    )


@pytest.fixture
def service(
    runtime_store: RuntimeStore, registry: RuntimeRegistry,
    workflow_store: WorkflowStore, task_store: TaskStore,
) -> ExecutionService:
    """组合根: 内置 Adapter + 无 logger + Workflow 联动引擎。"""
    return ExecutionService(
        runtime_store, registry, adapters=BUILTIN_ADAPTERS,
        workflow_engine=WorkflowEngine(workflow_store, task_store=task_store),
    )


@pytest.fixture
def event_service(
    runtime_store: RuntimeStore, registry: RuntimeRegistry,
    workflow_store: WorkflowStore, task_store: TaskStore, logger: EventLogger,
) -> ExecutionService:
    """带 EventLogger 与联动引擎的 ExecutionService (事件序断言)。"""
    return ExecutionService(
        runtime_store, registry, adapters=BUILTIN_ADAPTERS, logger=logger,
        workflow_engine=WorkflowEngine(workflow_store, task_store=task_store, logger=logger),
    )


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (CLI 测试, 每个测试隔离)。"""
    return tmp_path / "factory"
