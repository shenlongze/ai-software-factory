"""tests/agents/conftest.py — Agent/Skill 注册表测试 fixtures (sys.path 兜底同 events 模式)。"""

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

from agents.registry import AgentRegistry, SkillRegistry
from agents.store import AgentStore, SkillStore
from events.logger import EventLogger
from events.store import EventStore


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (CLI 测试, 每个测试隔离)。"""
    return tmp_path / "factory"


@pytest.fixture
def agents_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "agents"


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "skills"


@pytest.fixture
def agent_store(agents_dir: Path) -> AgentStore:
    return AgentStore(agents_dir)


@pytest.fixture
def skill_store(skills_dir: Path) -> SkillStore:
    return SkillStore(skills_dir)


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
def agent_registry(agent_store: AgentStore) -> AgentRegistry:
    """无 logger 的纯存储 AgentRegistry (事件相关测试另用 logger fixture)。"""
    return AgentRegistry(agent_store)


@pytest.fixture
def skill_registry(skill_store: SkillStore) -> SkillRegistry:
    return SkillRegistry(skill_store)
