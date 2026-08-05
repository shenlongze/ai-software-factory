"""tests/tasks/conftest.py — TaskStore 临时目录 fixture。

与 tests/events/conftest.py 同款 sys.path 兜底 (pytest pythonpath 之外的双保险)。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

import pytest

from tasks.store import TaskStore


@pytest.fixture
def tasks_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "tasks"


@pytest.fixture
def store(tasks_dir: Path) -> TaskStore:
    return TaskStore(tasks_dir)
