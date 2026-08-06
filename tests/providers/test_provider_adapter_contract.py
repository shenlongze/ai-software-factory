"""test_provider_adapter_contract.py — ProviderAdapter 抽象契约 (统一智能出口协议)。

覆盖: 抽象接口不可实例化 (generate/chat/stream 必须实现) / PROVIDER_ID 与
PROVIDER_TYPE 类常量约定 / 内置实现映射 BUILTIN_PROVIDER_ADAPTERS (hermes
真实 Agent, id 与默认定义一致) / 与 events/registry/store 解耦 (零依赖,
ADR-0006 解耦铁律) / 命名空间独立于 runtime/adapters (Hermes 双角色并存,
phase8-plan §Q4)。

设计依据: providers/provider.py + providers/adapters/__init__.py (Phase 8A)。
"""

from __future__ import annotations

import inspect

import pytest

from providers.adapters import BUILTIN_PROVIDER_ADAPTERS, HermesProviderAdapter
from providers.definitions import DEFAULT_PROVIDER_DEFINITIONS
from providers.models import ProviderRequest, ProviderResponse
from providers.provider import ProviderAdapter


class TestAbstractContract:
    def test_abstract_cannot_instantiate(self):
        """契约: 抽象接口不可直接实例化 (generate/chat/stream 未实现)。"""
        with pytest.raises(TypeError):
            ProviderAdapter()

    def test_abstract_methods_declared(self):
        for name in ("generate", "chat", "stream"):
            assert name in ProviderAdapter.__abstractmethods__

    def test_class_constants_defaults(self):
        """类常量约定: PROVIDER_ID/PROVIDER_TYPE 由子类覆盖。"""
        assert ProviderAdapter.PROVIDER_ID == ""
        assert ProviderAdapter.PROVIDER_TYPE == "cloud"

    def test_hermes_is_concrete(self):
        """hermes 为具体实现 (覆盖全部抽象方法, 可实例化)。"""
        adapter = HermesProviderAdapter()
        assert isinstance(adapter, ProviderAdapter)
        assert not inspect.isabstract(adapter)

    def test_hermes_identity_matches_definition(self):
        """身份一致性: adapter id 与默认定义 id 对齐 (目录↔实现解耦但键一致)。"""
        assert HermesProviderAdapter.PROVIDER_ID == "hermes"
        assert HermesProviderAdapter.PROVIDER_TYPE == "agent"
        assert DEFAULT_PROVIDER_DEFINITIONS[0].id == "hermes"
        assert DEFAULT_PROVIDER_DEFINITIONS[0].type == "agent"


class TestBuiltinMap:
    def test_hermes_registered(self):
        assert "hermes" in BUILTIN_PROVIDER_ADAPTERS
        assert isinstance(BUILTIN_PROVIDER_ADAPTERS["hermes"], HermesProviderAdapter)

    def test_builtin_keys_match_definition_ids(self):
        """内置实现 id 集 = 默认定义 id 集 (目录与实现同步, Phase 8a 范围)。"""
        builtin = set(BUILTIN_PROVIDER_ADAPTERS)
        defaults = {d.id for d in DEFAULT_PROVIDER_DEFINITIONS}
        assert builtin == defaults

    def test_namespace_independent_from_runtime(self):
        """命名空间独立: provider hermes ≠ runtime hermes-runtime (双角色并存)。"""
        from runtime.adapters import BUILTIN_ADAPTERS

        assert "hermes-runtime" in BUILTIN_ADAPTERS
        assert "hermes" not in BUILTIN_ADAPTERS
        assert "hermes-runtime" not in BUILTIN_PROVIDER_ADAPTERS

    def test_adapter_decoupled_from_events_and_registry(self):
        """解耦铁律 (ADR-0006): hermes adapter 模块零依赖 events/registry/store。"""
        mod = inspect.getmodule(HermesProviderAdapter)
        assert mod is not None
        src = inspect.getsource(mod)
        assert "EventLogger" not in src
        assert "from events" not in src
        assert "import events" not in src
        assert "from .registry" not in src
        assert "from .store" not in src
        assert "from providers.models" in src
        assert "from providers.provider" in src
