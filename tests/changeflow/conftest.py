"""tests/changeflow/conftest.py — Change Driven Workflow Layer 测试 fixtures (Phase 6E, ADR-0020)。

复用 tests/git/git_helpers (make_repo/commit_all/write_file — 真实 git subprocess
mock 仓库) 与 tests/cli/cli_helpers (run_cli/open_events/event_types); 本目录
helper 模块用唯一名 changeflow_helpers (backend-developer skill 陷阱: 多非包目录
共存时同名模块互相遮蔽 — 与 change_helpers/workflow_helpers 同款规则)。

fixtures:
- changeflow_dir / trigger_registry: 触发器注册表 (每测试隔离)
- task_store / workflow_store / runtime_store / runtime_registry / workflow_engine
- db_path / logger / event_store
- repo_path / task_repo: git mock 仓库 (真实 subprocess)
- engine: 全装配 ChangeWorkflowEngine (change_service=None — 规则输入缺省 SKIP;
  需要 change 证据的测试局部注入 stub/真实 ChangeService)
- cli_root: 独立工厂根 (CLI 测试)
- cli_task_root: 工厂根同时是含任务提交的 git 仓库 (evaluate 链路)
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
_GIT_TESTS = _ROOT / "tests" / "git"
if str(_GIT_TESTS) not in sys.path:  # 复用 git_helpers (make_repo/commit_all/write_file)
    sys.path.insert(0, str(_GIT_TESTS))

import pytest

from events.logger import EventLogger
from events.store import EventStore
from runtime.registry import RuntimeRegistry
from runtime.store import RuntimeStore
from tasks.store import TaskStore
from workflows.engine import WorkflowEngine
from workflows.store import WorkflowStore

from changeflow.engine import ChangeWorkflowEngine
from changeflow.triggers import ChangeTriggerRegistry

from git_helpers import (  # noqa: F401
    commit_all,
    init_repo,
    make_repo,
    write_file,
)


# ------------------------------------------------------------------ 目录/存储 fixtures

@pytest.fixture
def changeflow_dir(tmp_path: Path) -> Path:
    """ChangeTriggerRegistry 目录 (独立于工厂根, 每测试隔离)。"""
    return tmp_path / "changeflow"


@pytest.fixture
def trigger_registry(changeflow_dir: Path) -> ChangeTriggerRegistry:
    return ChangeTriggerRegistry(changeflow_dir)


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
def task_store(tmp_path: Path) -> TaskStore:
    return TaskStore(tmp_path / "tasks")


@pytest.fixture
def workflow_store(tmp_path: Path) -> WorkflowStore:
    return WorkflowStore(tmp_path / "workflows")


@pytest.fixture
def runtime_store(tmp_path: Path) -> RuntimeStore:
    return RuntimeStore(tmp_path / "runtimes")


@pytest.fixture
def runtime_registry(runtime_store: RuntimeStore) -> RuntimeRegistry:
    return RuntimeRegistry(runtime_store)


@pytest.fixture
def workflow_engine(
    workflow_store: WorkflowStore, task_store: TaskStore, logger: EventLogger,
) -> WorkflowEngine:
    return WorkflowEngine(workflow_store, task_store=task_store, logger=logger)


# ------------------------------------------------------------------ git mock 仓库

@pytest.fixture
def repo_path(tmp_path: Path) -> Path:
    """标准 mock 仓库 (init + 2 提交, 无任务 ID — 见 make_repo)。"""
    return make_repo(tmp_path / "repo")


@pytest.fixture
def task_repo(tmp_path: Path) -> Path:
    """含任务提交的仓库: MP-BUG-001 (login) / MP-FEATURE-002 (settings)。"""
    repo = init_repo(tmp_path / "task-repo")
    write_file(repo, "app/auth.py", "def login(): ...\n")
    commit_all(repo, "MP-BUG-001: fix login crash")
    write_file(repo, "app/settings.py", "THEME = 'dark'\n")
    commit_all(repo, "MP-FEATURE-002: add settings page")
    return repo


# ------------------------------------------------------------------ 引擎 (change_service 缺省 None)

@pytest.fixture
def engine(
    trigger_registry: ChangeTriggerRegistry,
    task_store: TaskStore,
    workflow_engine: WorkflowEngine,
    workflow_store: WorkflowStore,
    runtime_registry: RuntimeRegistry,
    logger: EventLogger,
) -> ChangeWorkflowEngine:
    """全装配引擎 (change_service=None — 规则输入缺省 SKIP; 触发可用)。"""
    return ChangeWorkflowEngine(
        triggers=trigger_registry,
        task_store=task_store,
        workflow_engine=workflow_engine,
        workflow_store=workflow_store,
        runtime_registry=runtime_registry,
        logger=logger,
    )


# ------------------------------------------------------------------ CLI 工厂根

@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (CLI 测试, 每个测试隔离)。"""
    return tmp_path / "factory"


@pytest.fixture
def cli_task_root(tmp_path: Path) -> Path:
    """工厂根同时是含任务提交的 git 仓库 (change/evaluate 命令默认 repo=工厂根)。"""
    root = tmp_path / "factory"
    init_repo(root)
    write_file(root, "app/auth.py", "def login(): ...\n")
    commit_all(root, "MP-BUG-001: fix login crash")
    return root
