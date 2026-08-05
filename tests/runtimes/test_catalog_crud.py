"""tests/runtimes/test_catalog_crud.py — RuntimeCatalog CRUD (register/get/list/remove)。

覆盖: 注册/重复冲突/读取/过滤/删除/内建定义只读边界/持久化生效。默认定义
(hermes/echo/mock) 为内建基线 — 合并视图见 test_catalog_definitions.py。
"""

from __future__ import annotations

import pytest

from runtimes.catalog import (
    RuntimeCatalog,
    RuntimeCatalogError,
    RuntimeDefinitionExistsError,
    RuntimeDefinitionNotFoundError,
)
from runtimes.models import CatalogStatus

from catalog_helpers import make_definition


class TestRegister:
    def test_register_ok(self, catalog):
        d, ev = catalog.register(make_definition())
        assert ev is None  # 无 logger → 纯存储, 不发事件
        assert catalog.get("custom-rt").id == "custom-rt"

    def test_register_duplicate_raises(self, catalog):
        catalog.register(make_definition())
        with pytest.raises(RuntimeDefinitionExistsError, match="already exists"):
            catalog.register(make_definition())

    def test_register_persists_across_instances(self, catalog_store):
        """注册经 store 落盘 — 新 catalog 实例读同一目录可见 (独立进程语义)。"""
        RuntimeCatalog(catalog_store).register(make_definition("rt-a"))
        fresh = RuntimeCatalog(catalog_store)
        assert fresh.get("rt-a") is not None

    def test_register_default_id_rejected(self, catalog):
        """内建默认定义 id 保留 (hermes/echo/mock 只读基线, ADR-0014 决策 4)。"""
        with pytest.raises(RuntimeDefinitionExistsError, match="hermes"):
            catalog.register(make_definition("hermes"))


class TestGet:
    def test_get_missing_returns_none(self, catalog):
        assert catalog.get("nope") is None

    def test_get_returns_registered(self, catalog):
        catalog.register(make_definition("rt-a", capabilities=["x"]))
        assert catalog.get("rt-a").capabilities == ["x"]

    def test_get_returns_default_without_register(self, catalog):
        """默认定义无需注册即可读取 (内建基线, 空 store 也可见)。"""
        d = catalog.get("hermes")
        assert d is not None and d.type == "agent"


class TestList:
    def test_list_includes_defaults_and_registered(self, catalog):
        catalog.register(make_definition("custom-rt"))
        ids = [d.id for d in catalog.list()]
        assert "hermes" in ids and "echo" in ids and "mock" in ids
        assert "custom-rt" in ids
        assert ids == sorted(ids)

    def test_list_filter_by_type(self, catalog):
        catalog.register(make_definition("custom-rt", type="agent"))
        mock_ids = [d.id for d in catalog.list(type="mock")]
        assert mock_ids == ["echo", "mock"]
        assert "custom-rt" not in mock_ids

    def test_list_filter_by_status(self, catalog):
        catalog.register(make_definition("old-rt", status=CatalogStatus.DEPRECATED))
        active = catalog.list(status=CatalogStatus.ACTIVE)
        assert all(d.status is CatalogStatus.ACTIVE for d in active)
        deprecated = catalog.list(status="DEPRECATED")
        assert [d.id for d in deprecated] == ["old-rt"]

    def test_list_invalid_status_raises(self, catalog):
        with pytest.raises(ValueError, match="invalid catalog status"):
            catalog.list(status="bogus")

    def test_count_includes_defaults(self, catalog):
        assert catalog.count() == 3
        catalog.register(make_definition("custom-rt"))
        assert catalog.count() == 4

    def test_ids_sorted(self, catalog):
        catalog.register(make_definition("rt-b"))
        catalog.register(make_definition("rt-a"))
        assert catalog.ids() == ["echo", "hermes", "mock", "rt-a", "rt-b"]


class TestRemove:
    def test_remove_registered(self, catalog):
        catalog.register(make_definition("custom-rt"))
        removed, ev = catalog.remove("custom-rt")
        assert removed.id == "custom-rt"
        assert ev is None
        assert catalog.get("custom-rt") is None
        assert catalog.count() == 3  # 回到纯默认基线

    def test_remove_missing_raises(self, catalog):
        with pytest.raises(RuntimeDefinitionNotFoundError, match="not found"):
            catalog.remove("nope")

    def test_remove_builtin_rejected(self, catalog):
        """内建默认定义不可移除 (只读基线, ADR-0014 决策 4)。"""
        with pytest.raises(RuntimeCatalogError, match="cannot remove builtin"):
            catalog.remove("hermes")

    def test_remove_then_register_same_id_ok(self, catalog):
        """删除已持久化定义后, 同 id 可重新注册 (默认 id 除外)。"""
        catalog.register(make_definition("custom-rt"))
        catalog.remove("custom-rt")
        catalog.register(make_definition("custom-rt", version="2.0.0"))
        assert catalog.get("custom-rt").version == "2.0.0"


class TestLayering:
    def test_catalog_does_not_touch_registry_store(self, catalog_store, runtimes_dir):
        """Catalog 写路径只写 catalog.json — 不产生/不修改 runtimes.json。"""
        catalog = RuntimeCatalog(catalog_store)
        catalog.register(make_definition("custom-rt"))
        assert not (runtimes_dir / "runtimes.json").exists()

    def test_catalog_does_not_execute(self, catalog):
        """Catalog 只描述能力 — 无 execute 方法 (三层分离, ADR-0014 决策 2)。"""
        assert not hasattr(catalog, "execute")
