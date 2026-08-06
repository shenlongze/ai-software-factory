"""tests/intelligence/conftest.py — Intelligence Layer 测试 fixtures (Phase 10A-1, ADR-0030)。

fixtures:
- intelligence_dir: 独立 Intelligence 数据空间 (<root>/intelligence — 与 tasks/
  agents/providers/product 分离, 删除不影响 Factory)
- decision_store / recommendation_store / experience_store: 三 Store (纯持久化)
- db_path / logger / event_store: 事件集成断言 (intelligence.* 4 事件)

本目录自洽 (不跨目录依赖 helper): intelligence_helpers 为唯一名 (backend-developer
skill 陷阱: 多非包目录共存时同名模块互相遮蔽; 测试文件 basename 一律
test_intelligence_* 前缀, 全仓库唯一)。损坏文件测试的 mkdir 局部化在测试类
autouse fixture (见 test_intelligence_store_atomic.py), 不放在共享目录 fixture —
避免破坏"目录由首次原子写创建"逆断言。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

import pytest

from events.logger import EventLogger
from events.store import EventStore

from intelligence.store import DecisionStore, ExperienceStore, RecommendationStore


@pytest.fixture
def intelligence_dir(tmp_path: Path) -> Path:
    """Intelligence 数据空间 (<root>/intelligence — 独立目录, 与 tasks/agents 分离)。"""
    return tmp_path / "factory" / "intelligence"


@pytest.fixture
def decision_store(intelligence_dir: Path) -> DecisionStore:
    return DecisionStore(intelligence_dir)


@pytest.fixture
def recommendation_store(intelligence_dir: Path) -> RecommendationStore:
    return RecommendationStore(intelligence_dir)


@pytest.fixture
def experience_store(intelligence_dir: Path) -> ExperienceStore:
    return ExperienceStore(intelligence_dir)


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
