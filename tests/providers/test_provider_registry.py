"""test_provider_registry.py — ProviderRegistry: 能力目录 + 默认选择。

覆盖: 合并视图 (默认定义基线 hermes + 已持久化定义, 持久化按 id 覆盖) /
register 冲突 (含默认定义 id 保留 → ProviderExistsError) / remove (未命中
ProviderNotFoundError; 内建默认定义不可移除 → ProviderRegistryError) / 读接口
(get/list 过滤/count/ids/find_by_capability 大小写不敏感) / default/set_default
(持久化默认 id; 默认引用已移除 → 自动失效返回 None 不抛错) / resolve 优先级
(显式 id → 默认 → None; 显式未注册抛 ProviderNotFoundError) / 事件经 events.py
辅助 (logger 可缺省 → 无事件)。

设计依据: providers/registry.py (Phase 8A, ADR-0022)。
"""

from __future__ import annotations

import pytest

from providers.definitions import DEFAULT_PROVIDER_DEFINITIONS
from providers.models import ProviderStatus
from providers.registry import (
    ProviderExistsError,
    ProviderNotFoundError,
    ProviderRegistry,
    ProviderRegistryError,
)

from providers_helpers import make_definition


class TestMergedView:
    def test_empty_store_has_baseline_hermes(self, registry):
        """空库 (未注册任何定义) → 合并视图 = 默认定义基线。"""
        assert registry.count() == 1
        assert registry.ids() == ["hermes"]
        assert registry.get("hermes") is not None

    def test_merged_includes_registered(self, registry):
        registry.register(make_definition("openai"))
        assert registry.count() == 2
        assert registry.ids() == ["hermes", "openai"]

    def test_registered_overrides_default_same_id_forbidden(self, registry):
        """默认 id 不可覆盖注册: hermes 已存在 → ProviderExistsError (内建只读)。"""
        with pytest.raises(ProviderExistsError):
            registry.register(make_definition("hermes"))

    def test_registered_overrides_persisted_same_id(self, registry):
        """持久化定义按 id 覆盖 (合并视图规则; 先 remove 后 register 即可覆盖)。"""
        registry.register(make_definition("openai", version="1.0.0"))
        registry.remove("openai")
        registry.register(make_definition("openai", version="2.0.0"))
        assert registry.get("openai").version == "2.0.0"

    def test_default_definition_readonly_in_merge(self, registry):
        """默认定义常驻合并视图, 永不自动写入 catalog.json (边界: 读路径合并)。"""
        registry.get("hermes")
        assert registry.store.definition_ids() == []  # 持久化层零写入


class TestRegister:
    def test_register_ok(self, registry):
        d, ev = registry.register(make_definition("openai"))
        assert d.id == "openai"
        assert ev is None  # 无 logger → 无事件 (logger 可缺省)

    def test_register_persists(self, registry):
        registry.register(make_definition("openai"))
        assert registry.store.definition_ids() == ["openai"]

    def test_register_duplicate_raises(self, registry):
        registry.register(make_definition("openai"))
        with pytest.raises(ProviderExistsError):
            registry.register(make_definition("openai"))

    def test_register_event(self, event_registry, event_store):
        """带 logger → register 发 provider.registered (存储先落地、事件后发)。"""
        event_registry.register(make_definition("openai"))
        events = event_store.query()
        assert len(events) == 1
        assert events[0].type.value == "provider.registered"
        assert events[0].payload["provider_id"] == "openai"
        assert events[0].payload["status"] == "ACTIVE"


class TestRemove:
    def test_remove_ok(self, registry):
        registry.register(make_definition("openai"))
        d, ev = registry.remove("openai")
        assert d.id == "openai"
        assert registry.get("openai") is None
        assert registry.count() == 1  # 只剩 hermes 基线

    def test_remove_not_found_raises(self, registry):
        with pytest.raises(ProviderNotFoundError):
            registry.remove("ghost")

    def test_remove_builtin_forbidden(self, registry):
        """内建默认定义 (hermes) 不可移除 → ProviderRegistryError。"""
        with pytest.raises(ProviderRegistryError, match="builtin"):
            registry.remove("hermes")

    def test_remove_builtin_keeps_default(self, registry):
        with pytest.raises(ProviderRegistryError):
            registry.remove("hermes")
        assert registry.get("hermes") is not None

    def test_remove_emits_event(self, event_registry, event_store):
        event_registry.register(make_definition("openai"))
        event_registry.remove("openai")
        types = [e.type.value for e in event_store.query()]
        assert types == ["provider.registered", "provider.removed"]


class TestRead:
    def test_get_miss_returns_none(self, registry):
        assert registry.get("ghost") is None

    def test_list_sorted_by_id(self, registry):
        registry.register(make_definition("zebra"))
        registry.register(make_definition("alpha"))
        assert [d.id for d in registry.list()] == ["alpha", "hermes", "zebra"]

    def test_list_filter_by_type(self, registry):
        registry.register(make_definition("openai", type="cloud"))
        registry.register(make_definition("local-llm", type="local"))
        ids = [d.id for d in registry.list(type="local")]
        assert ids == ["local-llm"]

    def test_list_filter_by_status(self, registry):
        registry.register(make_definition("openai"))
        registry.register(make_definition("off", status="disabled"))
        assert [d.id for d in registry.list(status=ProviderStatus.DISABLED)] == ["off"]
        assert [d.id for d in registry.list(status="disabled")] == ["off"]  # 字符串宽容

    def test_find_by_capability_exact_ci(self, registry):
        """大小写不敏感精确匹配 (合并视图: 默认 hermes 基线含 'chat' 也命中)。"""
        registry.register(make_definition("openai", capabilities=["Chat", "Code"]))
        registry.register(make_definition("claude", capabilities=["chat", "vision"]))
        assert [d.id for d in registry.find_by_capability("chat")] == ["claude", "hermes", "openai"]
        assert [d.id for d in registry.find_by_capability("CHAT")] == ["claude", "hermes", "openai"]

    def test_find_by_capability_no_substring(self, registry):
        """大小写不敏感精确匹配, 不含子串 (capability='chat' 不命中 'chatty' 的
        openai; 默认 hermes 基线精确 'chat' 仍命中)。"""
        registry.register(make_definition("openai", capabilities=["chatty"]))
        assert [d.id for d in registry.find_by_capability("chat")] == ["hermes"]

    def test_find_by_capability_empty(self, registry):
        assert registry.find_by_capability("") == []
        assert registry.find_by_capability("   ") == []

    def test_find_by_capability_miss(self, registry):
        registry.register(make_definition("openai", capabilities=["chat"]))
        assert registry.find_by_capability("vision") == []


class TestDefault:
    def test_default_none_when_unset(self, registry):
        assert registry.default() is None

    def test_set_default_ok(self, registry):
        registry.register(make_definition("openai"))
        d, ev = registry.set_default("openai")
        assert d.id == "openai"
        assert ev is None  # 无 logger → 无事件

    def test_set_default_persists(self, registry):
        registry.register(make_definition("openai"))
        registry.set_default("openai")
        assert registry.store.get_default() == "openai"
        assert registry.default().id == "openai"

    def test_set_default_switch(self, registry):
        registry.register(make_definition("openai"))
        registry.register(make_definition("claude"))
        registry.set_default("openai")
        registry.set_default("claude")
        assert registry.default().id == "claude"

    def test_set_default_not_found_raises(self, registry):
        with pytest.raises(ProviderNotFoundError):
            registry.set_default("ghost")

    def test_set_default_emits_selected_event(self, event_registry, event_store):
        event_registry.register(make_definition("openai"))
        event_registry.set_default("openai")
        ev = event_store.query()[-1]
        assert ev.type.value == "provider.selected"
        assert ev.payload["provider_id"] == "openai"
        assert ev.payload["default"] is True
        assert ev.stage == "default"

    def test_default_auto_invalidates_when_removed(self, registry):
        """默认引用已移除 → default() 返回 None (自动失效, 不抛错)。"""
        registry.register(make_definition("openai"))
        registry.set_default("openai")
        registry.remove("openai")
        assert registry.store.get_default() == "openai"  # 引用残留
        assert registry.default() is None  # 解析失效


class TestResolve:
    def test_resolve_explicit(self, registry):
        registry.register(make_definition("openai"))
        assert registry.resolve("openai") == "openai"

    def test_resolve_explicit_not_found_raises(self, registry):
        with pytest.raises(ProviderNotFoundError):
            registry.resolve("ghost")

    def test_resolve_default(self, registry):
        registry.register(make_definition("openai"))
        registry.set_default("openai")
        assert registry.resolve() == "openai"

    def test_resolve_none_when_no_default(self, registry):
        """未设置默认 → None (调用方自行兜底, 同 resolve_runtime_id 语义)。"""
        assert registry.resolve() is None

    def test_resolve_explicit_beats_default(self, registry):
        registry.register(make_definition("openai"))
        registry.register(make_definition("claude"))
        registry.set_default("openai")
        assert registry.resolve("claude") == "claude"
