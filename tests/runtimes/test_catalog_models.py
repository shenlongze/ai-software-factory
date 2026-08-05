"""tests/runtimes/test_catalog_models.py — RuntimeDefinition 模型 (创建/校验/序列化)。

覆盖: 字段默认值 / id 校验 / 列表规范化 (去空白去重) / 状态宽容解析 / to_dict JSON 友好。
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from runtimes.models import CatalogStatus, RuntimeDefinition

from catalog_helpers import make_definition


class TestModelDefaults:
    def test_minimal_creation(self):
        d = RuntimeDefinition(id="rt-1", name="RT 1")
        assert d.type == "agent"
        assert d.description == ""
        assert d.capabilities == []
        assert d.supported_tasks == []
        assert d.version == "1.0.0"
        assert d.status is CatalogStatus.ACTIVE
        assert d.metadata == {}
        assert d.created_at.tzinfo is not None  # UTC 带时区

    def test_full_creation(self):
        d = RuntimeDefinition(
            id="rt-1", name="RT 1", type="mock",
            description="desc", capabilities=["a", "b"],
            supported_tasks=["t1"], version="2.1.0",
            status="DEPRECATED", metadata={"k": "v"},
        )
        assert d.status is CatalogStatus.DEPRECATED
        assert d.metadata == {"k": "v"}

    def test_status_case_insensitive_parse(self):
        assert RuntimeDefinition(id="a", name="A", status="deprecated").status is CatalogStatus.DEPRECATED
        assert RuntimeDefinition(id="a", name="A", status="Active").status is CatalogStatus.ACTIVE


class TestIdValidation:
    @pytest.mark.parametrize("bad", ["", " ", ".", "..", "a/b", "a\\b"])
    def test_invalid_id_rejected(self, bad):
        with pytest.raises(ValidationError):
            RuntimeDefinition(id=bad, name="RT")

    def test_id_stripped(self):
        assert RuntimeDefinition(id="  rt-1  ", name="RT").id == "rt-1"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            RuntimeDefinition(id="rt-1", name="   ")


class TestListNormalization:
    def test_capabilities_strip_and_dedupe(self):
        d = RuntimeDefinition(
            id="rt-1", name="RT",
            capabilities=[" code-gen ", "tool-use", "code-gen", "", " "],
        )
        assert d.capabilities == ["code-gen", "tool-use"]

    def test_supported_tasks_normalized(self):
        d = RuntimeDefinition(id="rt-1", name="RT", supported_tasks=[" a ", "a", "b"])
        assert d.supported_tasks == ["a", "b"]

    def test_none_lists_default_empty(self):
        d = RuntimeDefinition(id="rt-1", name="RT", capabilities=None, supported_tasks=None)
        assert d.capabilities == [] and d.supported_tasks == []


class TestSerialization:
    def test_to_dict_json_roundtrip(self):
        d = make_definition(version="1.2.3", metadata={"vendor": "x"})
        data = d.to_dict()
        assert data["id"] == "custom-rt"
        assert data["status"] == "ACTIVE"
        assert data["metadata"] == {"vendor": "x"}
        restored = RuntimeDefinition.model_validate(data)
        assert restored.id == d.id
        assert restored.version == d.version
        assert restored.status is CatalogStatus.ACTIVE

    def test_to_dict_json_dumpable(self):
        """--json 出口: 必须可 json.dumps (无 datetime/枚举残留)。"""
        payload = json.dumps(make_definition().to_dict(), ensure_ascii=False)
        assert '"custom-rt"' in payload

    def test_model_copy_deep(self):
        d = make_definition()
        copy = d.model_copy(deep=True)
        copy.capabilities.append("extra")
        assert d.capabilities != copy.capabilities  # 深拷贝互不影响
