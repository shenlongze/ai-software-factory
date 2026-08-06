"""test_provider_models.py — Provider 领域模型 (ProviderDefinition/Request/Response/Status)。

覆盖: 枚举宽容 parse / id 即存储键校验 (空值/路径分隔符拒绝) / name/type/version
非空 / capabilities/models 列表规范化 (去空白/去空串/保序去重) / 默认定义基线
(hermes 内建, 只描述不执行) / Request 统一 I/O 契约 / Response ok 语义 (error
互斥, 不抛异常哲学) / to_dict JSON 友好 (CLI --json 与持久化共用)。

设计依据: providers/models.py (Phase 8A, ADR-0022), 参照 runtimes/models.py 风格。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from providers.definitions import (
    DEFAULT_PROVIDER_DEFINITIONS,
    DEFAULT_PROVIDER_IDS,
    default_provider_definition,
    default_provider_definitions,
)
from providers.models import (
    ProviderDefinition,
    ProviderRequest,
    ProviderResponse,
    ProviderStatus,
)

from providers_helpers import make_definition


class TestProviderStatus:
    def test_enum_values(self):
        assert ProviderStatus.ACTIVE.value == "ACTIVE"
        assert ProviderStatus.DISABLED.value == "DISABLED"

    def test_parse_case_insensitive(self):
        assert ProviderStatus.parse("active") is ProviderStatus.ACTIVE
        assert ProviderStatus.parse("Disabled") is ProviderStatus.DISABLED

    def test_parse_enum_passthrough(self):
        assert ProviderStatus.parse(ProviderStatus.ACTIVE) is ProviderStatus.ACTIVE

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError, match="invalid provider status"):
            ProviderStatus.parse("bogus")

    def test_parse_invalid_lists_valid(self):
        with pytest.raises(ValueError) as exc:
            ProviderStatus.parse("nope")
        assert "ACTIVE" in str(exc.value) and "DISABLED" in str(exc.value)


class TestProviderDefinition:
    def test_minimal_definition(self):
        d = ProviderDefinition(id="p1", name="P1")
        assert d.type == "cloud"
        assert d.status is ProviderStatus.ACTIVE
        assert d.capabilities == [] and d.models == []
        assert d.version == "1.0.0"

    def test_id_is_storage_key_rejects_empty(self):
        with pytest.raises(ValidationError):
            ProviderDefinition(id="", name="x")

    def test_id_is_storage_key_rejects_path_separators(self):
        for bad in ("a/b", "a\\b", "..", "."):
            with pytest.raises(ValidationError):
                ProviderDefinition(id=bad, name="x")

    def test_id_strips_whitespace(self):
        assert ProviderDefinition(id="  p1  ", name="x").id == "p1"

    def test_name_must_be_nonempty(self):
        with pytest.raises(ValidationError):
            ProviderDefinition(id="p1", name="   ")

    def test_type_must_be_nonempty(self):
        with pytest.raises(ValidationError):
            ProviderDefinition(id="p1", name="x", type=" ")

    def test_version_must_be_nonempty(self):
        with pytest.raises(ValidationError):
            ProviderDefinition(id="p1", name="x", version="")

    def test_status_coerced_from_string(self):
        d = ProviderDefinition(id="p1", name="x", status="disabled")
        assert d.status is ProviderStatus.DISABLED

    def test_status_invalid_raises(self):
        with pytest.raises(ValidationError):
            ProviderDefinition(id="p1", name="x", status="weird")

    def test_capabilities_normalized(self):
        d = ProviderDefinition(
            id="p1", name="x",
            capabilities=[" chat ", "", "chat", "code", "  "],
        )
        assert d.capabilities == ["chat", "code"]  # 去空白/去空串/保序去重

    def test_models_normalized(self):
        d = ProviderDefinition(
            id="p1", name="x", models=["gpt-4o", "gpt-4o", " claude "],
        )
        assert d.models == ["gpt-4o", "claude"]

    def test_capabilities_none_becomes_empty(self):
        assert ProviderDefinition(id="p1", name="x", capabilities=None).capabilities == []

    def test_config_schema_and_metadata_default_empty(self):
        d = ProviderDefinition(id="p1", name="x")
        assert d.config_schema == {} and d.metadata == {}

    def test_to_dict_json_friendly(self):
        d = make_definition("openai", status="disabled")
        data = d.to_dict()
        assert data["id"] == "openai"
        assert data["status"] == "DISABLED"  # 枚举 → 字符串
        assert isinstance(data["created_at"], str)  # datetime → ISO 字符串
        assert data["capabilities"] == ["chat", "generation"]

    def test_to_dict_roundtrip(self):
        d = make_definition("claude", models=["claude-sonnet"])
        assert ProviderDefinition.model_validate(d.to_dict()) == d


class TestDefaultDefinitions:
    def test_default_baseline_hermes(self):
        """默认定义基线: hermes (Phase 8a 基础, 内建只读)。"""
        assert DEFAULT_PROVIDER_IDS == ("hermes",)
        d = DEFAULT_PROVIDER_DEFINITIONS[0]
        assert d.id == "hermes"
        assert d.name == "Hermes Agent"
        assert d.type == "agent"

    def test_hermes_capabilities(self):
        d = DEFAULT_PROVIDER_DEFINITIONS[0]
        assert "chat" in d.capabilities and "code" in d.capabilities
        assert "tool-use" in d.capabilities

    def test_hermes_config_schema_describes_env(self):
        d = DEFAULT_PROVIDER_DEFINITIONS[0]
        assert d.config_schema["command"]["env"] == "FACTORY_PROVIDER_HERMES_CMD"
        assert d.config_schema["timeout_s"]["default"] == 300

    def test_default_provider_definition_lookup(self):
        d = default_provider_definition("hermes")
        assert d is not None and d.id == "hermes"

    def test_default_provider_definition_miss(self):
        assert default_provider_definition("ghost") is None

    def test_default_provider_definitions_deep_copy(self):
        """深拷贝: 调用方修改不影响模块常量 (definitions.py 契约)。"""
        copies = default_provider_definitions()
        copies[0].models.append("mutated")
        assert DEFAULT_PROVIDER_DEFINITIONS[0].models == ["hermes-default"]


class TestProviderRequest:
    def test_minimal_request(self):
        r = ProviderRequest(provider_id="hermes")
        assert r.prompt is None and r.messages is None
        assert r.metadata == {}

    def test_full_request(self):
        r = ProviderRequest(
            provider_id="hermes", prompt="hello", system="be nice",
            model="m1", temperature=0.7, metadata={"task_id": "T-1"},
        )
        assert r.model == "m1" and r.temperature == 0.7
        assert r.metadata["task_id"] == "T-1"

    def test_request_to_dict(self):
        r = ProviderRequest(provider_id="hermes", prompt="hi")
        assert r.to_dict()["prompt"] == "hi"
        assert r.to_dict()["provider_id"] == "hermes"


class TestProviderResponse:
    def test_ok_when_no_error(self):
        r = ProviderResponse(provider_id="hermes", content="OK")
        assert r.ok is True and r.error is None

    def test_not_ok_when_error(self):
        r = ProviderResponse(provider_id="hermes", error="boom")
        assert r.ok is False
        assert r.content == ""  # 失败不携带正文

    def test_error_and_content_mutually_exclusive_by_ok(self):
        """ok 属性 = error is None (稳定响应哲学, 不抛异常)。"""
        assert ProviderResponse(provider_id="x", error="e").ok is False
        assert ProviderResponse(provider_id="x", content="c").ok is True

    def test_usage_default_empty(self):
        r = ProviderResponse(provider_id="hermes", content="OK")
        assert r.usage == {} and r.metadata == {}

    def test_response_to_dict(self):
        r = ProviderResponse(provider_id="hermes", content="OK", model="hermes-default")
        data = r.to_dict()
        assert data["content"] == "OK" and data["model"] == "hermes-default"
        # ok 为 property (error is None 判定), 不进入 model_dump 字段序列化
        assert "ok" not in data
