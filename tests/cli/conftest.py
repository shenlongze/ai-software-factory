"""tests/cli/conftest.py — CLI 测试根目录 fixture (sys.path 兜底同 events 模式)。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

import pytest


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (每个测试隔离)。"""
    return tmp_path / "factory"
