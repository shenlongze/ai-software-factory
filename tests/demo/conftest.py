"""tests/demo/conftest.py — Phase 13A demo 测试 fixture (sys.path 兜底同 cli/project 模式)。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_TESTS_CLI = _ROOT / "tests" / "cli"
if str(_TESTS_CLI) not in sys.path:
    sys.path.insert(0, str(_TESTS_CLI))  # 复用 cli_helpers.run_cli

import pytest


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (每个测试隔离; demo 内部临时根与 CLI root 无关)。"""
    return tmp_path / "factory"


@pytest.fixture
def repo_root() -> Path:
    """仓库根 (scripts/examples 断言)。"""
    return _ROOT
