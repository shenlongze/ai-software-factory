"""tests/change/conftest.py — Change Intelligence 层测试 fixtures。

复用 tests/git/git_helpers (make_repo/commit_all/write_file — 真实 git subprocess
mock 仓库) 与 tests/cli/cli_helpers (run_cli/open_events/event_types); 本目录
helper 模块用唯一名 change_helpers (backend-developer skill 陷阱: 多非包目录
共存时同名模块互相遮蔽)。

fixtures:
- repo: 标准 2 提交 mock 仓库 (feat: init / feat: second, 无任务 ID)
- task_repo: 含 MP-BUG-001 / MP-FEATURE-002 提交的仓库 (commit parser/L4 用)
- client: 指向 repo 的 GitClient
- task_store / db_path / logger / change_dir / store
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
_GIT_TESTS = _ROOT / "tests" / "git"
if str(_GIT_TESTS) not in sys.path:  # 复用 git_helpers (make_repo/commit_all/write_file)
    sys.path.insert(0, str(_GIT_TESTS))

import pytest

from events.logger import EventLogger
from events.store import EventStore

from git.client import GitClient
from git.service import GitChangeStore

from change.service import ChangeService, ChangeStore

from git_helpers import (  # noqa: F401
    commit_all,
    git,
    init_repo,
    make_repo,
    write_file,
)


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


@pytest.fixture
def client(repo_path: Path) -> GitClient:
    """指向 mock 仓库的 GitClient (无任务提交)。"""
    return GitClient(repo_path)


@pytest.fixture
def task_client(task_repo: Path) -> GitClient:
    """指向含任务提交仓库的 GitClient。"""
    return GitClient(task_repo)


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
def change_dir(tmp_path: Path) -> Path:
    """ChangeStore 目录 (独立于工厂根, 每测试隔离)。"""
    return tmp_path / "change"


@pytest.fixture
def store(change_dir: Path) -> ChangeStore:
    return ChangeStore(change_dir)


@pytest.fixture
def task_store(tmp_path: Path):
    """TaskStore (L4 任务标题装载; 唯一 basename 规则: 不直接 import 具体类)。"""
    from tasks.store import TaskStore

    return TaskStore(tmp_path / "tasks")


@pytest.fixture
def service(client: GitClient, task_store, logger: EventLogger, change_dir: Path) -> ChangeService:
    """全装配 ChangeService (client + task_store + logger + 显式 store 路径)。"""
    return ChangeService(
        client=client,
        task_store=task_store,
        logger=logger,
        change_store=ChangeStore(change_dir),
        git_changes_store=GitChangeStore(change_dir.parent / "git"),
        project_id="markpad",
    )


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (CLI 测试, 每个测试隔离)。"""
    return tmp_path / "factory"


@pytest.fixture
def task_cli_root(tmp_path: Path):
    """工厂根同时是含任务提交的 git 仓库 (change 命令默认 repo=工厂根)。"""
    root = tmp_path / "factory"
    init_repo(root)
    write_file(root, "app/auth.py", "def login(): ...\n")
    commit_all(root, "MP-BUG-001: fix login crash")
    return root


# ------------------------------------------------------------------ Dashboard 聚合 fixtures
# (Change View 渲染/聚合测试复用 — 与 tests/dashboard/conftest.py 同构,
# 不跨目录依赖 conftest, 保持 tests/change 自洽。)

@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    return tmp_path / "factory"


@pytest.fixture
def event_store(logger: EventLogger):
    return logger.store


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
