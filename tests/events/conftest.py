"""tests/events/conftest.py — 临时事件库 fixture。

pytest 配置已含 pythonpath=["factory-core"] (pyproject.toml), 此处 sys.path 兜底,
保证不依赖 editable install 也能导入 events 包。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

import pytest

from events.store import EventStore


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "events.db"


@pytest.fixture
def store(db_path: Path) -> EventStore:
    s = EventStore(db_path)
    yield s
    s.close()
