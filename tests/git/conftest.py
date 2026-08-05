"""tests/git/conftest.py — Git 集成层测试 fixtures (sys.path 兜底同既有模式)。

复用 tests/cli/cli_helpers (run_cli/open_events/event_types) — 同
tests/dashboard|runtimes/conftest.py 模式; helper 模块用唯一名 git_helpers
(backend-developer skill 陷阱: 多非包目录共存时同名模块互相遮蔽)。
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

from git.client import GitClient
from git.service import GitChangeStore, GitService

from git_helpers import (  # noqa: F401
    commit_all,
    git,
    init_repo,
    make_repo,
    write_file,
)


@pytest.fixture
def repo_path(tmp_path: Path) -> Path:
    """标准 mock 仓库路径 (init + 2 提交, 见 make_repo)。"""
    return make_repo(tmp_path / "repo")


@pytest.fixture
def client(repo_path: Path) -> GitClient:
    """指向 mock 仓库的 GitClient。"""
    return GitClient(repo_path)


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
def changes_dir(tmp_path: Path) -> Path:
    """GitChangeStore 目录 (独立于工厂根, 每测试隔离)。"""
    return tmp_path / "git"


@pytest.fixture
def store(changes_dir: Path) -> GitChangeStore:
    return GitChangeStore(changes_dir)


@pytest.fixture
def service(client: GitClient, store: GitChangeStore) -> GitService:
    """无 logger 的 GitService (事件相关测试另用 event_service)。"""
    return GitService(client, project_id="markpad", changes_store=store)


@pytest.fixture
def event_service(
    client: GitClient, store: GitChangeStore, logger: EventLogger
) -> GitService:
    """带 EventLogger 的 GitService (事件集成断言)。"""
    return GitService(
        client, project_id="markpad", changes_store=store, logger=logger
    )


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (CLI 测试, 每个测试隔离)。"""
    return tmp_path / "factory"
