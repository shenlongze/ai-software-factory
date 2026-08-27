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
import os
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


# ------------------------------------------------------------------ env 泄漏防护

#: load_llm_key (workflow_runner) 会把解析到的 LLM key 注入**进程环境**
#: (deepseek/openai → OPENAI_API_KEY, anthropic → ANTHROPIC_API_KEY)。
#: 这是应用代码直接写 os.environ 的副作用 — monkeypatch 无法 undo。
#: 部分 console 测试 (doctor/init 等) 会触发注入且不清理 → OPENAI_API_KEY
#: 泄漏给后续 tests/llm 路由测试 → 误判 openai 可用 → 偶发失败 (全量跑
#: 必现, 单跑恒过)。本 autouse fixture 在每次 console 测试后快照还原。
_LLM_ENV_KEYS = (
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
)


@pytest.fixture(autouse=True)
def _restore_llm_env_after_test():
    """console 测试后还原 LLM 环境变量 (load_llm_key 进程内注入的副作用)。

    与 monkeypatch 恢复顺序无关: 本 fixture 还原到测试前快照, monkeypatch
    还原到原始值 — 两者在无测试内修改时都等于快照; 有测试内修改时, 先跑的
    还原者确定最终值, 后跑者会覆盖到同一目标 (原始值 == 快照, 前提是测试
    前进程 env 未被污染 — 本 fixture 保证上一测试后已还原)。
    """
    snapshot = {k: os.environ.get(k) for k in _LLM_ENV_KEYS}
    yield
    for key, val in snapshot.items():
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val
