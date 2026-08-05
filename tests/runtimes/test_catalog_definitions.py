"""tests/runtimes/test_catalog_definitions.py — 默认定义 (hermes/echo/mock, 只描述不执行)。

覆盖: 三个默认定义存在且描述正确 / 只描述不执行 / 默认与已注册定义合并视图 /
默认定义不自动落盘 (catalog.json 保持空) / 深拷贝安全。
"""

from __future__ import annotations

import pytest

from runtimes.definitions import (
    DEFAULT_DEFINITION_IDS,
    DEFAULT_DEFINITIONS,
    default_definition,
    default_definitions,
)

from catalog_helpers import make_definition


class TestDefaultDefinitions:
    def test_three_defaults_present(self):
        assert DEFAULT_DEFINITION_IDS == ("hermes", "echo", "mock")
        assert len(DEFAULT_DEFINITIONS) == 3

    def test_hermes_definition(self):
        d = default_definition("hermes")
        assert d is not None
        assert d.type == "agent"
        assert d.capabilities == ["code-generation", "tool-use", "reasoning"]
        assert "feature-implementation" in d.supported_tasks
        assert d.version == "1.0.0"

    def test_echo_definition(self):
        d = default_definition("echo")
        assert d is not None
        assert d.type == "mock"
        assert "echo" in d.capabilities
        assert "smoke-test" in d.supported_tasks

    def test_mock_definition(self):
        d = default_definition("mock")
        assert d is not None
        assert d.type == "mock"
        assert "simulation" in d.capabilities
        assert d.status.value == "ACTIVE"

    def test_unknown_default_returns_none(self):
        assert default_definition("nope") is None

    def test_definitions_describe_only_no_execution(self):
        """只描述不执行: 默认定义不含任何可执行引用 (无 adapter/命令字段)。"""
        for d in DEFAULT_DEFINITIONS:
            assert not hasattr(d, "execute")
            assert d.metadata.get("builtin") is True


class TestMergeView:
    def test_catalog_lists_defaults_on_empty_store(self, catalog):
        ids = catalog.ids()
        assert ids == ["echo", "hermes", "mock"]

    def test_defaults_not_auto_persisted(self, catalog_store, catalog):
        """读路径合并 — 只 list 不注册, catalog.json 不产生文件 (零写)。"""
        catalog.list()
        catalog.get("hermes")
        assert not catalog_store.path.exists()

    def test_registered_definition_joins_defaults(self, catalog):
        catalog.register(make_definition("custom-rt"))
        assert catalog.count() == 4
        assert catalog.get("custom-rt") is not None

    def test_defaults_visible_in_capability_search(self, catalog):
        hits = catalog.find_by_capability("code-generation")
        assert [d.id for d in hits] == ["hermes"]


class TestCopySafety:
    def test_default_definitions_returns_copies(self):
        a = default_definitions()
        a[0].capabilities.append("mutated")
        assert "mutated" not in DEFAULT_DEFINITIONS[0].capabilities

    def test_default_definition_returns_copy(self):
        d = default_definition("hermes")
        d.capabilities.append("mutated")
        assert "mutated" not in default_definition("hermes").capabilities
