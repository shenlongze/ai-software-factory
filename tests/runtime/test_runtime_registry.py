"""test_runtime_registry.py — RuntimeRegistry: register/get/list/remove + 状态过滤 + 派发辅助。"""

from __future__ import annotations

import pytest

from runtime.models import RuntimeStatus
from runtime.registry import RuntimeExistsError, RuntimeNotFoundError, RuntimeRegistry

from runtime_helpers import make_runtime


class TestRegister:
    def test_register_returns_tuple(self, registry):
        rt = make_runtime()
        out = registry.register(rt)
        assert isinstance(out, tuple) and out[0] is rt

    def test_register_no_logger_event_none(self, registry):
        rt, ev = registry.register(make_runtime())
        assert rt.id == "R-001"
        assert ev is None  # 无 logger → 纯存储操作

    def test_register_persists(self, registry):
        rt = make_runtime()
        registry.register(rt)
        got = registry.get("R-001")
        assert got is not None
        assert got.id == rt.id and got.name == rt.name and got.type == rt.type
        assert got.status is rt.status
        assert got.created_at == rt.created_at

    def test_register_duplicate_raises(self, registry):
        registry.register(make_runtime("R-001"))
        with pytest.raises(RuntimeExistsError):
            registry.register(make_runtime("R-001"))

    def test_register_status_preserved(self, registry):
        registry.register(make_runtime("R-001", status=RuntimeStatus.DISABLED))
        assert registry.get("R-001").status is RuntimeStatus.DISABLED


class TestGet:
    def test_get_missing_none(self, registry):
        assert registry.get("R-999") is None

    def test_get_after_reload(self, registry, runtime_store):
        """注册后经新 Registry 实例 (同 store) 可读 → 持久化闭环。"""
        registry.register(make_runtime("R-001"))
        fresh = RuntimeRegistry(runtime_store)
        assert fresh.get("R-001").name == "runtime R-001"


class TestList:
    def test_list_empty(self, registry):
        assert registry.list() == []

    def test_list_sorted_by_id(self, registry):
        registry.register(make_runtime("R-002"))
        registry.register(make_runtime("R-001"))
        assert [r.id for r in registry.list()] == ["R-001", "R-002"]

    def test_list_filter_status(self, registry):
        registry.register(make_runtime("R-001"))
        registry.register(make_runtime("R-002", status=RuntimeStatus.DISABLED))
        assert [r.id for r in registry.list(status=RuntimeStatus.AVAILABLE)] == ["R-001"]
        assert [r.id for r in registry.list(status=RuntimeStatus.DISABLED)] == ["R-002"]

    def test_list_filter_status_str(self, registry):
        registry.register(make_runtime("R-001"))
        assert [r.id for r in registry.list(status="available")] == ["R-001"]

    def test_list_invalid_status_raises(self, registry):
        with pytest.raises(ValueError):
            registry.list(status="bogus")


class TestRemove:
    def test_remove_returns_removed(self, registry):
        rt, _ = registry.register(make_runtime("R-001"))
        removed, _ = registry.remove("R-001")
        assert removed == rt

    def test_remove_deletes(self, registry):
        registry.register(make_runtime("R-001"))
        registry.remove("R-001")
        assert registry.get("R-001") is None
        assert registry.list() == []

    def test_remove_missing_raises(self, registry):
        with pytest.raises(RuntimeNotFoundError):
            registry.remove("R-999")


class TestCountIdsNext:
    def test_count(self, registry):
        registry.register(make_runtime("R-001"))
        registry.register(make_runtime("R-002"))
        assert registry.count() == 2

    def test_ids_sorted(self, registry):
        registry.register(make_runtime("R-002"))
        registry.register(make_runtime("R-001"))
        assert registry.ids() == ["R-001", "R-002"]

    def test_next_id(self, registry):
        assert registry.next_id() == "R-001"
        registry.register(make_runtime("R-001"))
        assert registry.next_id() == "R-002"
        registry.register(make_runtime("R-009"))
        assert registry.next_id() == "R-010"


class TestResolveRuntimeId:
    """派发辅助 (ADR-0006 决策 6): 显式 id → 首个 AVAILABLE → None。"""

    def test_explicit_registered(self, registry):
        registry.register(make_runtime("R-001"))
        assert registry.resolve_runtime_id("R-001") == "R-001"

    def test_explicit_unknown_raises(self, registry):
        with pytest.raises(RuntimeNotFoundError):
            registry.resolve_runtime_id("R-999")

    def test_explicit_disabled_still_resolves(self, registry):
        """显式指定 DISABLED runtime 也允许 (调用方明确选择)。"""
        registry.register(make_runtime("R-001", status=RuntimeStatus.DISABLED))
        assert registry.resolve_runtime_id("R-001") == "R-001"

    def test_auto_picks_first_available(self, registry):
        registry.register(make_runtime("R-001"))
        registry.register(make_runtime("R-002", status=RuntimeStatus.DISABLED))
        assert registry.resolve_runtime_id() == "R-001"

    def test_auto_skips_disabled(self, registry):
        registry.register(make_runtime("R-001", status=RuntimeStatus.DISABLED))
        registry.register(make_runtime("R-002"))
        assert registry.resolve_runtime_id() == "R-002"

    def test_none_when_no_available(self, registry):
        registry.register(make_runtime("R-001", status=RuntimeStatus.DISABLED))
        assert registry.resolve_runtime_id() is None

    def test_none_when_empty(self, registry):
        assert registry.resolve_runtime_id() is None
