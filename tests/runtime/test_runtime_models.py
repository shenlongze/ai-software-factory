"""test_runtime_models.py — Runtime 模型校验 (ExecutionRequest/Result/RuntimeInfo + 状态枚举)。"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from runtime.models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    RuntimeInfo,
    RuntimeStatus,
)

from runtime_helpers import make_request, make_result, make_runtime


class TestExecutionStatus:
    def test_values(self):
        """四状态齐全且顺序固定 (PENDING/RUNNING/SUCCESS/FAILED)。"""
        assert [s.value for s in ExecutionStatus] == ["PENDING", "RUNNING", "SUCCESS", "FAILED"]

    def test_is_str_enum(self):
        assert ExecutionStatus.PENDING == "PENDING"
        assert isinstance(ExecutionStatus.PENDING, str)

    def test_parse_lenient(self):
        assert ExecutionStatus.parse("pending") is ExecutionStatus.PENDING
        assert ExecutionStatus.parse(" Success ") is ExecutionStatus.SUCCESS
        assert ExecutionStatus.parse(ExecutionStatus.FAILED) is ExecutionStatus.FAILED

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError):
            ExecutionStatus.parse("DONE")


class TestRuntimeStatus:
    def test_values(self):
        assert [s.value for s in RuntimeStatus] == ["AVAILABLE", "DISABLED"]

    def test_parse_lenient(self):
        assert RuntimeStatus.parse("available") is RuntimeStatus.AVAILABLE
        assert RuntimeStatus.parse("DISABLED") is RuntimeStatus.DISABLED

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError):
            RuntimeStatus.parse("OFFLINE")


class TestExecutionRequest:
    def test_defaults(self):
        """默认: PENDING / input 空 dict / 绑定字段可空 / UTC 时间戳。"""
        req = ExecutionRequest(id="EX-001", task_id="T-1")
        assert req.status is ExecutionStatus.PENDING
        assert req.input == {}
        assert req.workflow_id is None and req.step_id is None
        assert req.agent_id is None and req.runtime_id is None
        assert req.created_at.tzinfo is not None

    def test_full_fields(self):
        req = ExecutionRequest(
            id="EX-001", task_id="T-1", workflow_id="wf", step_id="s1",
            agent_id="A-1", runtime_id="R-1", input={"prompt": "x"},
        )
        assert req.runtime_id == "R-1" and req.agent_id == "A-1"
        assert req.input == {"prompt": "x"}

    def test_status_coerced_from_string(self):
        req = ExecutionRequest(id="EX-001", task_id="T-1", status="running")
        assert req.status is ExecutionStatus.RUNNING

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            ExecutionRequest(id="EX-001", task_id="T-1", status="DONE")

    def test_invalid_id_rejected(self):
        for bad in ("", "../x", "a/b", "."):
            with pytest.raises(ValidationError):
                ExecutionRequest(id=bad, task_id="T-1")

    def test_missing_required_fields_rejected(self):
        with pytest.raises(ValidationError):
            ExecutionRequest(id="EX-001")  # task_id 缺失
        with pytest.raises(ValidationError):
            ExecutionRequest(task_id="T-1")  # id 缺失

    def test_to_dict_json_roundtrip(self):
        """to_dict 输出 JSON 友好 (CLI --json / 持久化共用)。"""
        data = make_request().to_dict()
        assert data["status"] == "PENDING"
        assert json.loads(json.dumps(data)) == data

    def test_model_dump_validate_roundtrip(self):
        req = make_request()
        restored = ExecutionRequest.model_validate(req.model_dump(mode="json"))
        assert restored == req
        assert restored.status is ExecutionStatus.PENDING


class TestExecutionResult:
    def test_defaults(self):
        """默认: SUCCESS / output 空 dict / error None。"""
        res = ExecutionResult(id="EXR-1", request_id="EX-001")
        assert res.status is ExecutionStatus.SUCCESS
        assert res.output == {} and res.error is None
        assert res.created_at.tzinfo is not None

    def test_failed_result(self):
        res = ExecutionResult(id="EXR-1", request_id="EX-001", status="failed", error="boom")
        assert res.status is ExecutionStatus.FAILED
        assert res.error == "boom"

    def test_pending_status_rejected(self):
        """结果只能是终态: PENDING/RUNNING 属于请求中间态 (ADR-0006 决策 2)。"""
        with pytest.raises(ValidationError):
            ExecutionResult(id="EXR-1", request_id="EX-001", status="pending")
        with pytest.raises(ValidationError):
            ExecutionResult(id="EXR-1", request_id="EX-001", status="running")

    def test_invalid_ids_rejected(self):
        with pytest.raises(ValidationError):
            ExecutionResult(id="../x", request_id="EX-001")
        with pytest.raises(ValidationError):
            ExecutionResult(id="EXR-1", request_id="a/b")

    def test_to_dict_roundtrip(self):
        res = make_result()
        restored = ExecutionResult.model_validate(res.model_dump(mode="json"))
        assert restored == res


class TestRuntimeInfo:
    def test_defaults(self):
        """默认: type=agent / description 空 / AVAILABLE / UTC 时间戳。"""
        rt = RuntimeInfo(id="R-001", name="mock")
        assert rt.type == "agent" and rt.description == ""
        assert rt.status is RuntimeStatus.AVAILABLE
        assert rt.created_at.tzinfo is not None

    def test_disabled(self):
        rt = RuntimeInfo(id="R-001", name="mock", status="disabled")
        assert rt.status is RuntimeStatus.DISABLED

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            RuntimeInfo(id="R-001", name="mock", status="bogus")

    def test_invalid_id_rejected(self):
        with pytest.raises(ValidationError):
            RuntimeInfo(id="a/b", name="x")

    def test_to_dict_roundtrip(self):
        rt = make_runtime()
        restored = RuntimeInfo.model_validate(rt.model_dump(mode="json"))
        assert restored == rt
