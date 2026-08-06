"""test_provider_config_8b1.py — runtime_preferences.provider 解析 (Phase 8B-1, ADR-0023)。

Phase 8B-1 增强 (providers/config.py): parse_runtime_preferences(preferences,
task_type) → {"runtime", "provider"} 成为单一解析事实源 (preferred_provider
委托它, DRY); runtime_default_provider 读取 Runtime 目录定义声明的默认
provider (metadata.default_provider 推荐形态 / 顶层 provider 旧形态兼容)。
"""

from __future__ import annotations

from providers.config import (
    parse_runtime_preferences,
    preferred_provider,
    runtime_default_provider,
)


class TestParseRuntimePreferences:
    def test_none_returns_both_none(self):
        assert parse_runtime_preferences(None, "feature") == {
            "runtime": None, "provider": None,
        }

    def test_empty_dict(self):
        assert parse_runtime_preferences({}, "feature") == {
            "runtime": None, "provider": None,
        }

    def test_missing_task_type_entry(self):
        assert parse_runtime_preferences(
            {"development": {"provider": "openai"}}, "feature",
        ) == {"runtime": None, "provider": None}

    def test_entry_not_dict(self):
        assert parse_runtime_preferences(
            {"feature": "openai"}, "feature",
        ) == {"runtime": None, "provider": None}

    def test_missing_keys(self):
        assert parse_runtime_preferences({"feature": {}}, "feature") == {
            "runtime": None, "provider": None,
        }

    def test_runtime_and_provider(self):
        assert parse_runtime_preferences(
            {"feature": {"runtime": "hermes", "provider": "openai"}}, "feature",
        ) == {"runtime": "hermes", "provider": "openai"}

    def test_provider_only(self):
        assert parse_runtime_preferences(
            {"feature": {"provider": "ollama"}}, "feature",
        ) == {"runtime": None, "provider": "ollama"}

    def test_whitespace_values_are_none(self):
        assert parse_runtime_preferences(
            {"feature": {"runtime": "  ", "provider": ""}}, "feature",
        ) == {"runtime": None, "provider": None}

    def test_values_stripped(self):
        assert parse_runtime_preferences(
            {"feature": {"runtime": " hermes ", "provider": " openai "}}, "feature",
        ) == {"runtime": "hermes", "provider": "openai"}

    def test_task_types_do_not_leak(self):
        parsed = parse_runtime_preferences(
            {"development": {"provider": "openai"},
             "local": {"provider": "ollama"}},
            "local",
        )
        assert parsed == {"runtime": None, "provider": "ollama"}

    def test_keys_always_present(self):
        for prefs in (None, {}, {"feature": {"runtime": "x"}}, {"feature": {"provider": "y"}}):
            result = parse_runtime_preferences(prefs, "feature")
            assert set(result) == {"runtime", "provider"}


class TestPreferredProvider:
    def test_delegates_to_parse(self):
        """preferred_provider 委托 parse_runtime_preferences (单一解析事实源)。"""
        assert preferred_provider(
            {"feature": {"provider": "openai"}}, "feature",
        ) == "openai"

    def test_none_prefs(self):
        assert preferred_provider(None, "feature") is None

    def test_missing_key(self):
        assert preferred_provider({"feature": {"runtime": "hermes"}}, "feature") is None


class TestRuntimeDefaultProvider:
    def test_none_definition(self):
        assert runtime_default_provider(None) is None

    def test_metadata_default_provider(self):
        definition = _FakeDefinition(metadata={"default_provider": "openai"})
        assert runtime_default_provider(definition) == "openai"

    def test_legacy_top_level_provider(self):
        definition = _FakeDefinition(provider="claude")
        assert runtime_default_provider(definition) == "claude"

    def test_metadata_wins_over_legacy(self):
        definition = _FakeDefinition(
            metadata={"default_provider": "openai"}, provider="claude",
        )
        assert runtime_default_provider(definition) == "openai"

    def test_no_declaration(self):
        assert runtime_default_provider(_FakeDefinition()) is None

    def test_whitespace_declaration_is_none(self):
        assert runtime_default_provider(
            _FakeDefinition(metadata={"default_provider": "  "}),
        ) is None

    def test_non_dict_metadata_ignored(self):
        assert runtime_default_provider(_FakeDefinition(metadata="nope")) is None

    def test_arbitrary_object_safe(self):
        """对任意对象宽容读取 (getattr + dict 检查), 不抛异常。"""
        assert runtime_default_provider(object()) is None
        assert runtime_default_provider("plain-string") is None


class _FakeDefinition:
    """Runtime 目录定义的替身: 仅承载 metadata / provider 读取路径。"""

    def __init__(self, metadata=None, provider=None):
        self.metadata = metadata
        self.provider = provider
