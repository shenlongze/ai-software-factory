"""test_validation_models.py — ValidationStatus / ValidationResult 模型测试。

覆盖: 状态枚举 / 结果创建 / 默认值 / 序列化往返 / 非法输入拒绝。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from validation.models import ValidationResult, ValidationStatus


class TestValidationStatus:
    def test_four_status_values(self):
        """PASS/FAIL/SKIP/ERROR 四态 (phase3a-status.md)。"""
        assert [s.value for s in ValidationStatus] == ["PASS", "FAIL", "SKIP", "ERROR"]

    def test_is_str_enum(self):
        """str 枚举: 可直接进事件 result 语义列。"""
        assert ValidationStatus.PASS == "PASS"
        assert isinstance(ValidationStatus.PASS, str)


class TestValidationResult:
    @staticmethod
    def _result(**overrides: object) -> ValidationResult:
        base: dict[str, object] = dict(
            id="L1.task_exists", task_id="T-001", level="L1",
            rule="task_exists", status=ValidationStatus.PASS,
        )
        base.update(overrides)
        return ValidationResult(**base)

    def test_create_with_defaults(self):
        """默认值: message 空串, created_at 自动生成 (带时区)。"""
        r = self._result()
        assert r.id == "L1.task_exists"
        assert r.task_id == "T-001"
        assert r.level == "L1" and r.rule == "task_exists"
        assert r.status is ValidationStatus.PASS
        assert r.message == ""
        assert r.created_at.tzinfo is not None

    def test_status_coerce_from_string(self):
        """status 传字符串自动转枚举。"""
        r = self._result(status="FAIL")
        assert r.status is ValidationStatus.FAIL

    def test_required_fields_missing_rejected(self):
        """缺必填 id/task_id 拒绝。"""
        with pytest.raises(ValidationError):
            ValidationResult(level="L1", rule="x", status=ValidationStatus.PASS)

    def test_invalid_status_rejected(self):
        """非法 status 字符串拒绝。"""
        with pytest.raises(ValidationError):
            self._result(status="BOGUS")

    def test_custom_message_and_created_at(self):
        """显式 message / created_at 生效。"""
        ts = datetime(2026, 8, 5, 10, 0, 0, tzinfo=timezone.utc)
        r = self._result(status=ValidationStatus.SKIP, message="hook 未实现", created_at=ts)
        assert r.message == "hook 未实现"
        assert r.created_at == ts

    def test_to_dict_json_roundtrip(self):
        """to_dict → JSON → model_validate 往返一致 (序列化契约)。"""
        r = self._result(id="L2.workflow", level="L2", rule="workflow",
                         status=ValidationStatus.FAIL, message="不一致")
        d = r.to_dict()
        assert d["status"] == "FAIL"
        assert d["id"] == "L2.workflow"
        assert "created_at" in d
        restored = ValidationResult.model_validate(json.loads(json.dumps(d)))
        assert restored == r
        assert restored.status is ValidationStatus.FAIL

    def test_to_dict_json_safe(self):
        """to_dict 输出可被 json.dumps (事件 payload 兼容)。"""
        json.dumps(self._result(status=ValidationStatus.ERROR, message="boom").to_dict())
