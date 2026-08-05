"""tests/agents/test_skill_models.py — Skill 模型 (创建/序列化/版本/能力列表)。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agents.models import Skill


def test_skill_defaults():
    s = Skill(id="flutter", name="flutter")
    assert s.category == "general"
    assert s.version == "1.0.0"
    assert s.capabilities == []
    assert s.description == ""


def test_skill_full_fields():
    s = Skill(
        id="flutter", name="Flutter", category="frontend", description="UI 开发",
        capabilities=["widget", "dart"], version="2.0.0",
    )
    assert s.category == "frontend"
    assert s.version == "2.0.0"
    assert s.capabilities == ["widget", "dart"]


def test_skill_to_dict_json_serializable():
    s = Skill(id="flutter", name="Flutter", capabilities=["widget"])
    d = s.to_dict()
    assert d["id"] == "flutter"
    assert d["version"] == "1.0.0"
    assert isinstance(d["created_at"], str)
    assert isinstance(d["updated_at"], str)


def test_skill_roundtrip_from_dict():
    s = Skill(id="backend", name="Backend", version="1.2.0")
    assert Skill.model_validate(s.to_dict()) == s


def test_skill_version_custom_string():
    s = Skill(id="s", name="n", version="0.9.1-alpha")
    assert s.version == "0.9.1-alpha"


def test_skill_id_rejects_path_separators():
    for bad in ("a/b", "..", ".", "a\\b", ""):
        with pytest.raises(ValidationError):
            Skill(id=bad, name="n")


def test_skill_capabilities_dedup_keep_order():
    s = Skill(id="s", name="n", capabilities=["a", "a", "b", ""])
    assert s.capabilities == ["a", "b"]


def test_skill_name_required():
    with pytest.raises(ValidationError):
        Skill(id="s")  # name 必填


def test_skill_timestamps_utc_aware():
    s = Skill(id="s", name="n")
    assert s.created_at.tzinfo is not None
    assert s.updated_at.tzinfo is not None
