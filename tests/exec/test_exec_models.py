"""tests/exec/test_exec_models.py — 执行领域模型 (Pydantic v2 陷阱覆盖)。

覆盖: ExecutionRequest/Artifact/ExecutionResult/SandboxSession/ApprovalRecord
字段默认值/None 归一/枚举强制/to_dict JSON 友好/extra=forbid。
"""

from __future__ import annotations

from exec.models import (
    AgentInstance,
    ApprovalDecision,
    ApprovalRecord,
    Artifact,
    ArtifactType,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    SandboxSession,
    new_id,
    utcnow,
)


class TestIdsAndTime:
    def test_new_id_prefix_format(self):
        rid = new_id("EXR")
        assert rid.startswith("EXR-")
        assert len(rid) == len("EXR-") + 8

    def test_utcnow_aware(self):
        assert utcnow().tzinfo is not None


class TestExecutionRequest:
    def test_defaults(self):
        r = ExecutionRequest(id="EXR-1", objective="fix bug")
        assert r.task_id == ""
        assert r.requirement == ""
        assert r.input == {}
        assert r.output_refs == []
        assert r.created_at.tzinfo is not None

    def test_input_none_normalized(self):
        r = ExecutionRequest(id="EXR-1", objective="o", input=None, output_refs=None)
        assert r.input == {}
        assert r.output_refs == []

    def test_str_fields_none_normalized(self):
        r = ExecutionRequest(id="EXR-1", objective="o", task_id=None, requirement=None)
        assert r.task_id == ""
        assert r.requirement == ""

    def test_extra_forbidden(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ExecutionRequest(id="EXR-1", objective="o", bogus=1)

    def test_to_dict_json(self):
        r = ExecutionRequest(id="EXR-1", objective="o", input={"project_dir": "/p"})
        d = r.to_dict()
        assert d["id"] == "EXR-1"
        assert d["objective"] == "o"
        assert d["input"] == {"project_dir": "/p"}
        assert isinstance(d["created_at"], str)  # datetime → ISO 字符串


class TestArtifact:
    def test_defaults(self):
        a = Artifact(id="ART-1", type=ArtifactType.PATCH)
        assert a.task_id == ""
        assert a.employee_id == ""
        assert a.agent_id == ""
        assert a.event_refs == []
        assert a.path == ""

    def test_type_string_coerced(self):
        a = Artifact(id="ART-1", type="test_result")
        assert a.type is ArtifactType.TEST_RESULT

    def test_type_invalid_raises(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Artifact(id="ART-1", type="bogus")

    def test_event_refs_none_normalized(self):
        a = Artifact(id="ART-1", type=ArtifactType.PATCH, event_refs=None)
        assert a.event_refs == []

    def test_to_dict_enum_value(self):
        a = Artifact(id="ART-1", type=ArtifactType.REPORT)
        assert a.to_dict()["type"] == "report"


class TestExecutionResult:
    def test_defaults(self):
        r = ExecutionResult(id="EXS-1", request_id="EXR-1")
        assert r.status is ExecutionStatus.SUCCESS
        assert r.artifacts == []
        assert r.usage == {}
        assert r.report == ""
        assert r.error == ""
        assert r.duration == 0.0

    def test_status_string_coerced(self):
        r = ExecutionResult(id="EXS-1", request_id="EXR-1", status="failed")
        assert r.status is ExecutionStatus.FAILED

    def test_artifacts_dict_coerced(self):
        r = ExecutionResult(
            id="EXS-1", request_id="EXR-1",
            artifacts=[{"id": "ART-9", "type": "patch"}],
        )
        assert isinstance(r.artifacts[0], Artifact)
        assert r.artifacts[0].type is ArtifactType.PATCH

    def test_is_success_property(self):
        ok = ExecutionResult(id="EXS-1", request_id="EXR-1")
        bad = ExecutionResult(id="EXS-2", request_id="EXR-1", status=ExecutionStatus.FAILED)
        assert ok.is_success is True
        assert bad.is_success is False

    def test_to_dict_includes_artifacts(self):
        r = ExecutionResult(
            id="EXS-1", request_id="EXR-1",
            artifacts=[Artifact(id="ART-1", type=ArtifactType.PATCH)],
        )
        d = r.to_dict()
        assert d["artifacts"][0]["id"] == "ART-1"
        assert d["status"] == "success"


class TestSandboxSession:
    def test_defaults(self):
        s = SandboxSession(id="SBX-1", workspace_copy_path="/tmp/x")
        assert s.request_id == ""
        assert s.baseline_commit is None
        assert s.change_summary == ""
        assert s.patch_path == ""

    def test_change_summary_none_normalized(self):
        s = SandboxSession(id="SBX-1", workspace_copy_path="/tmp/x", change_summary=None)
        assert s.change_summary == ""


class TestApprovalRecord:
    def test_defaults(self):
        a = ApprovalRecord(id="APR-1", request_id="EXR-1")
        assert a.decision is ApprovalDecision.PENDING
        assert a.decided_by == ""
        assert a.comment == ""
        assert a.applied is False
        assert a.applied_at is None
        assert a.decided_at is None

    def test_decision_string_coerced(self):
        a = ApprovalRecord(id="APR-1", request_id="EXR-1", decision="approved")
        assert a.decision is ApprovalDecision.APPROVED

    def test_is_approved_property(self):
        p = ApprovalRecord(id="APR-1", request_id="EXR-1")
        ok = ApprovalRecord(id="APR-2", request_id="EXR-1", decision=ApprovalDecision.APPROVED)
        assert p.is_approved is False
        assert ok.is_approved is True

    def test_to_dict_decision_value(self):
        a = ApprovalRecord(id="APR-1", request_id="EXR-1", decision=ApprovalDecision.REJECTED)
        assert a.to_dict()["decision"] == "rejected"


class TestAgentInstance:
    def test_defaults(self):
        a = AgentInstance(id="agent-1")
        assert a.name == "Developer Agent"
        assert a.agent_type == "developer"
        assert a.to_dict()["id"] == "agent-1"
