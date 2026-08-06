"""test_provider_selector.py — ProviderSelector 四层优先级选择 (Phase 8B-1, ADR-0023)。

选择链: explicit (CLI --provider) > project (runtime_preferences.<task_type>.provider)
> agent (角色级偏好同构) > runtime (Runtime 目录定义默认) > default (Registry 默认)。

层级语义 (providers/selector.py docstring):
- explicit 层: 用户意图 — 未注册/禁用 → ProviderNotFoundError (不静默降级)。
- 配置层 (project/agent/runtime/default): 条目缺失、空 id、未注册或 DISABLED
  → 该层缺失, 降级下一层。
- 注册表装配 (ProviderSelector(registry)) 时对配置层做存在性/状态校验;
  不装配时只做 id 链决策 (provider 定义由调用方自行解析)。
"""

from __future__ import annotations

import pytest

from providers.models import ProviderStatus
from providers.registry import ProviderNotFoundError
from providers.selector import SELECTION_SOURCES, ProviderSelection, ProviderSelector

from providers_helpers import make_definition


class TestSelectorNoRegistry:
    """不装配注册表: 纯 id 链决策 (无存储单测, provider 定义不校验)。"""

    def test_all_missing_returns_none(self):
        assert ProviderSelector().resolve(task_type="feature") is None

    def test_all_layers_none_returns_none(self):
        sel = ProviderSelector().resolve(
            task_type="feature", explicit=None, project_prefs=None,
            agent_prefs=None, runtime_default=None, registry_default=None,
        )
        assert sel is None

    def test_empty_prefs_returns_none(self):
        assert ProviderSelector().resolve(
            task_type="feature", project_prefs={}, agent_prefs={},
        ) is None

    def test_explicit_hit(self):
        sel = ProviderSelector().resolve(task_type="feature", explicit="openai")
        assert sel is not None
        assert sel.provider_id == "openai"
        assert sel.source == "explicit"

    def test_explicit_whitespace_falls_through(self):
        sel = ProviderSelector().resolve(task_type="feature", explicit="   ")
        assert sel is None

    def test_project_hit(self):
        sel = ProviderSelector().resolve(
            task_type="feature",
            project_prefs={"feature": {"provider": "openai"}},
        )
        assert sel is not None
        assert sel.provider_id == "openai"
        assert sel.source == "project"

    def test_agent_hit(self):
        sel = ProviderSelector().resolve(
            task_type="feature",
            agent_prefs={"feature": {"provider": "claude"}},
        )
        assert sel is not None
        assert sel.provider_id == "claude"
        assert sel.source == "agent"

    def test_runtime_default_hit(self):
        sel = ProviderSelector().resolve(task_type="feature", runtime_default="deepseek")
        assert sel is not None
        assert sel.provider_id == "deepseek"
        assert sel.source == "runtime"

    def test_registry_default_hit(self):
        sel = ProviderSelector().resolve(task_type="feature", registry_default="hermes")
        assert sel is not None
        assert sel.provider_id == "hermes"
        assert sel.source == "default"

    def test_explicit_beats_project(self):
        sel = ProviderSelector().resolve(
            task_type="feature", explicit="openai",
            project_prefs={"feature": {"provider": "claude"}},
        )
        assert sel.provider_id == "openai"
        assert sel.source == "explicit"

    def test_project_beats_agent(self):
        sel = ProviderSelector().resolve(
            task_type="feature",
            project_prefs={"feature": {"provider": "openai"}},
            agent_prefs={"feature": {"provider": "claude"}},
        )
        assert sel.provider_id == "openai"
        assert sel.source == "project"

    def test_agent_beats_runtime(self):
        sel = ProviderSelector().resolve(
            task_type="feature",
            agent_prefs={"feature": {"provider": "claude"}},
            runtime_default="deepseek",
        )
        assert sel.provider_id == "claude"
        assert sel.source == "agent"

    def test_runtime_beats_default(self):
        sel = ProviderSelector().resolve(
            task_type="feature", runtime_default="deepseek", registry_default="hermes",
        )
        assert sel.provider_id == "deepseek"
        assert sel.source == "runtime"

    def test_project_missing_falls_to_default(self):
        sel = ProviderSelector().resolve(
            task_type="feature",
            project_prefs={"feature": {"provider": ""}},
            registry_default="hermes",
        )
        assert sel.provider_id == "hermes"
        assert sel.source == "default"

    def test_project_other_task_type_ignored(self):
        sel = ProviderSelector().resolve(
            task_type="feature",
            project_prefs={"development": {"provider": "openai"}},
            registry_default="hermes",
        )
        assert sel.provider_id == "hermes"
        assert sel.source == "default"

    def test_prefs_entry_not_dict_falls_through(self):
        sel = ProviderSelector().resolve(
            task_type="feature", project_prefs={"feature": "openai"},
            registry_default="hermes",
        )
        assert sel.provider_id == "hermes"

    def test_prefs_value_whitespace_falls_through(self):
        sel = ProviderSelector().resolve(
            task_type="feature", project_prefs={"feature": {"provider": "  "}},
            registry_default="hermes",
        )
        assert sel.provider_id == "hermes"

    def test_definition_not_resolved_without_registry(self):
        """不装配注册表: provider 定义不校验 (None), 只产出 id 链。"""
        sel = ProviderSelector().resolve(task_type="feature", explicit="openai")
        assert sel.provider is None
        assert sel.provider_id == "openai"

    def test_selection_to_dict(self):
        sel = ProviderSelector().resolve(task_type="feature", explicit="openai")
        assert sel.to_dict() == {"provider_id": "openai", "source": "explicit"}

    def test_selection_sources_constant(self):
        assert SELECTION_SOURCES == ("explicit", "project", "agent", "runtime", "default")


class TestSelectorWithRegistry:
    """装配注册表: 配置层做存在性/状态校验 (未注册/禁用 → 降级); explicit 层抛错。"""

    @pytest.fixture
    def registry(self, store):
        from providers.registry import ProviderRegistry

        reg = ProviderRegistry(store)
        reg.register(make_definition("openai"))
        reg.register(make_definition("claude"))
        reg.register(make_definition("deepseek"))
        return reg

    def test_explicit_registered_returns_definition(self, registry):
        sel = ProviderSelector(registry).resolve(task_type="feature", explicit="openai")
        assert sel.provider_id == "openai"
        assert sel.provider is not None
        assert sel.provider.id == "openai"
        assert sel.source == "explicit"

    def test_explicit_unregistered_raises(self, registry):
        with pytest.raises(ProviderNotFoundError) as exc:
            ProviderSelector(registry).resolve(task_type="feature", explicit="ghost")
        assert "ghost" in str(exc.value)

    def test_explicit_disabled_raises(self, registry):
        registry.register(make_definition("off", status=ProviderStatus.DISABLED))
        with pytest.raises(ProviderNotFoundError) as exc:
            ProviderSelector(registry).resolve(task_type="feature", explicit="off")
        assert "off" in str(exc.value)

    def test_project_registered(self, registry):
        sel = ProviderSelector(registry).resolve(
            task_type="feature",
            project_prefs={"feature": {"provider": "claude"}},
        )
        assert sel.provider_id == "claude"
        assert sel.provider is not None and sel.provider.id == "claude"
        assert sel.source == "project"

    def test_project_unregistered_falls_through(self, registry):
        sel = ProviderSelector(registry).resolve(
            task_type="feature",
            project_prefs={"feature": {"provider": "ghost"}},
            registry_default="hermes",
        )
        assert sel.provider_id == "hermes"
        assert sel.source == "default"

    def test_project_disabled_falls_through(self, registry):
        registry.register(make_definition("off", status=ProviderStatus.DISABLED))
        sel = ProviderSelector(registry).resolve(
            task_type="feature",
            project_prefs={"feature": {"provider": "off"}},
            runtime_default="deepseek",
        )
        assert sel.provider_id == "deepseek"
        assert sel.source == "runtime"

    def test_runtime_default_unregistered_falls_through(self, registry):
        sel = ProviderSelector(registry).resolve(
            task_type="feature", runtime_default="ghost",
        )
        assert sel is None

    def test_default_layer_uses_registry_default(self, registry):
        sel = ProviderSelector(registry).resolve(
            task_type="feature", registry_default="openai",
        )
        assert sel.provider_id == "openai"
        assert sel.provider is not None
        assert sel.source == "default"

    def test_agent_layer_registered(self, registry):
        sel = ProviderSelector(registry).resolve(
            task_type="feature", agent_prefs={"feature": {"provider": "deepseek"}},
        )
        assert sel.provider_id == "deepseek"
        assert sel.source == "agent"

    def test_registry_property(self, registry):
        selector = ProviderSelector(registry)
        assert selector.registry is registry
