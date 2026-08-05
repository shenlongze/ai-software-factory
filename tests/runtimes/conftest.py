"""tests/runtimes/conftest.py — Runtime Catalog 测试 fixtures (sys.path 兜底同既有模式)。

复用 tests/cli/cli_helpers (run_cli/open_events/event_types) — 同
tests/dashboard|recovery/conftest.py 模式; helper 模块用唯一名 catalog_helpers
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
from runtimes.catalog import RuntimeCatalog
from runtimes.store import CatalogStore

from catalog_helpers import make_definition  # noqa: F401


@pytest.fixture
def runtimes_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "runtimes"


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (CLI 测试, 每个测试隔离)。"""
    return tmp_path / "factory"


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
def catalog_store(runtimes_dir: Path) -> CatalogStore:
    return CatalogStore(runtimes_dir)


@pytest.fixture
def catalog(catalog_store: CatalogStore) -> RuntimeCatalog:
    """无 logger 的纯存储 RuntimeCatalog (事件相关测试另用 event_catalog)。"""
    return RuntimeCatalog(catalog_store)


@pytest.fixture
def event_catalog(catalog_store: CatalogStore, logger: EventLogger) -> RuntimeCatalog:
    """带 EventLogger 的 RuntimeCatalog (事件集成断言)。"""
    return RuntimeCatalog(catalog_store, logger=logger)


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (CLI 测试, 每个测试隔离)。"""
    return tmp_path / "factory"
