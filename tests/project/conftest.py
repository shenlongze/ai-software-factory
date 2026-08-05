"""tests/project/conftest.py — Phase 5A 测试 fixture (sys.path 兜底同 cli/events 模式)。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_TESTS_CLI = _ROOT / "tests" / "cli"
if str(_TESTS_CLI) not in sys.path:
    sys.path.insert(0, str(_TESTS_CLI))  # 复用 cli_helpers.run_cli / open_events / event_types

import pytest

_MARKPAD_FILES = ("project.yaml", "agents.yaml", "skills.yaml", "workflows.yaml")


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (每个测试隔离)。"""
    return tmp_path / "factory"


@pytest.fixture
def examples_dir(tmp_path: Path) -> Path:
    """临时 examples 目录 (复制真实 markpad 配置, 不依赖仓库内目录的稳定性)。"""
    src = _ROOT / "examples" / "markpad"
    dst = tmp_path / "examples" / "markpad"
    dst.mkdir(parents=True, exist_ok=True)
    for name in _MARKPAD_FILES:
        (dst / name).write_text((src / name).read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path / "examples"
