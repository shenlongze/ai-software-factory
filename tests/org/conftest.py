"""tests/org/conftest.py — Organization Extension 测试 fixtures (Phase 16A, ADR-0036)。

fixtures:
- org_dir: 独立 Org 数据空间 (<root>/org — 与 tasks/agents/product/intelligence 分离)
- org_store: OrgStore (六子库门面)
- db_path / logger / event_store: 事件集成断言 (org.* 14 事件)
- cli_root: 独立工厂根 (CLI 测试: main(["--root", ...]) 数据根 + 事件库 R/factory.db)

sys.path: 挂 factory-core (Core 包) + factory-org (org 包父目录 — 以 `org` 导入)。
本目录自洽 (不跨目录依赖 helper): org_helpers 为唯一名; 测试文件 basename
一律 test_org_* 前缀 (backend-developer skill 陷阱: 多非包目录共存时同名
模块互相遮蔽)。损坏文件测试的 mkdir 局部化在测试类 autouse fixture
(见 test_org_store_atomic.py), 不放在共享目录 fixture — 避免破坏
"目录由首次原子写创建" 逆断言。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_FACTORY_ORG = _ROOT / "factory-org"
if str(_FACTORY_ORG) not in sys.path:  # org 包父目录 (factory-org/org/)
    sys.path.insert(0, str(_FACTORY_ORG))

import pytest

from events.logger import EventLogger
from events.store import EventStore

from org.store import OrgStore


@pytest.fixture
def org_dir(tmp_path: Path) -> Path:
    """Org 数据空间 (<root>/org — 独立目录, 与 tasks/agents 分离)。"""
    return tmp_path / "factory" / "org"


@pytest.fixture
def org_store(org_dir: Path) -> OrgStore:
    return OrgStore(org_dir)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "events.db"


@pytest.fixture
def logger(db_path: Path) -> EventLogger:
    """带事件库的 EventLogger (org.* 事件集成断言); 退出时关闭连接。"""
    s = EventStore(db_path)
    yield EventLogger(s)
    s.close()


@pytest.fixture
def event_store(logger: EventLogger) -> EventStore:
    return logger.store


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根 (CLI 测试: 数据空间 R/org/, 事件库 R/factory.db)。"""
    return tmp_path / "factory"
