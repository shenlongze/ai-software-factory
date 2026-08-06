"""tests/console/conftest.py — Human Console Layer 测试 fixtures (Phase 11A, ADR-0034)。

fixtures:
- console_mod: importlib 加载的 factory-console 模块 (包名含连字符, 唯一导入方式)
- factory_root: 独立工厂根 (tmp_path/factory — 与用户 ~/.factory 隔离)
- event_logger / event_store: 事件集成断言 (console.* 3 事件)
- stores: decision/recommendation/experience/product/usage/agent/workspace 装配点

本目录自洽 (不跨目录依赖 helper): console_helpers 为唯一名; 测试文件
basename 一律 test_console_* 前缀 (全仓库唯一, 后端开发陷阱: 多非包目录
共存时同名模块互相遮蔽)。sys.path 同时挂仓库根 (factory-console 包父目录)
与 factory-core (Core 包), 同 tests/intelligence/conftest.py 模式。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 的父目录 (含连字符包名, importlib 导入)
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

import pytest

from events.logger import EventLogger
from events.store import EventStore


@pytest.fixture(scope="session")
def console_mod():
    """factory-console 包 (importlib — 目录名含连字符, 无法用 import 语句)。"""
    return importlib.import_module("factory-console")


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """独立工厂根 (数据空间: tasks/agents/skills/workflows/events/product/
    intelligence/providers/projects — 与用户 ~/.factory 完全隔离)。"""
    root = tmp_path / "factory"
    root.mkdir()
    return root


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "events.db"


@pytest.fixture
def event_logger(db_path: Path) -> EventLogger:
    """带事件库的 EventLogger (console.* 事件集成断言); 退出时关闭连接。"""
    store = EventStore(db_path)
    yield EventLogger(store)
    store.close()


@pytest.fixture
def event_store(event_logger: EventLogger) -> EventStore:
    return event_logger.store
