"""tests/intelligence/test_intelligence_models.py — Intelligence 模型校验 (Phase 10A-1)。

覆盖: Decision / Recommendation / ExperienceRecord / Evidence 的字段/校验/
默认值/枚举/序列化 (决策模型 vs 审批模型语义分离; 五域 + freshness; 六来源)。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from intelligence.models import (
    Decision,
    DecisionStatus,
    Evidence,
    EvidenceSource,
    ExperienceDomain,
    ExperienceRecord,
    ExperienceResult,
    Recommendation,
    decay_freshness,
)

from intelligence_helpers import (
    TS_OLD,
    make_decision,
    make_evidence,
    make_experience,
    make_recommendation,
)


# ------------------------------------------------------------------ Decision


class TestDecisionDefaults:
    def test_default_id_and_created_at(self):
        d = Decision(subject_id="task-1")
        assert d.id
        assert len(d.id) == 32  # uuid4 hex
        # created_at 为统一 UTC 存储格式 (26 字符, 可解析)
        dt = datetime.strptime(d.created_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
        assert dt.tzinfo is not None

    def test_default_status_is_open(self):
        d = Decision(subject_id="task-1")
        assert d.status == DecisionStatus.OPEN

    def test_default_options_and_evidence_empty(self):
        d = Decision(subject_id="task-1")
        assert d.options == []
        assert d.evidence == []

    def test_default_recommendation_none(self):
        d = Decision(subject_id="task-1")
        assert d.recommendation is None

    def test_default_confidence_and_risk(self):
        d = Decision(subject_id="task-1")
        assert d.confidence == 0.5
        assert d.risk == 0.0

    def test_default_approval_request_id_none(self):
        # Decision ≠ Approval: 不强制绑定审批; approval_request_id 为可选预留
        d = Decision(subject_id="task-1")
        assert d.approval_request_id is None

    def test_decision_type_and_description_roundtrip(self):
        d = Decision(subject_id="task-1", decision_type="task_plan", description="plan")
        assert d.decision_type == "task_plan"
        assert d.description == "plan"


class TestDecisionValidation:
    @pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0, -1.0])
    def test_confidence_out_of_range_rejected(self, bad):
        with pytest.raises(ValidationError):
            Decision(subject_id="t", confidence=bad)

    @pytest.mark.parametrize("ok", [0.0, 0.5, 1.0])
    def test_confidence_boundaries_accepted(self, ok):
        assert Decision(subject_id="t", confidence=ok).confidence == ok

    @pytest.mark.parametrize("bad", [-0.01, 1.01])
    def test_risk_out_of_range_rejected(self, bad):
        with pytest.raises(ValidationError):
            Decision(subject_id="t", risk=bad)

    def test_status_coerced_from_string(self):
        d = Decision(subject_id="t", status="recommended")
        assert d.status == DecisionStatus.RECOMMENDED
        assert d.status.value == "recommended"

    def test_status_invalid_string_rejected(self):
        with pytest.raises(ValidationError):
            Decision(subject_id="t", status="in_progress")

    def test_evidence_coerced_from_dicts(self):
        d = Decision(
            subject_id="t",
            evidence=[{"source_type": "event", "source_id": "evt-1"}],
        )
        assert len(d.evidence) == 1
        assert isinstance(d.evidence[0], Evidence)
        assert d.evidence[0].source_id == "evt-1"

    def test_evidence_none_becomes_empty(self):
        d = Decision(subject_id="t", evidence=None)
        assert d.evidence == []

    def test_options_accept_dicts(self):
        d = Decision(subject_id="t", options=[{"id": "a"}, {"id": "b", "extra": 1}])
        assert d.options == [{"id": "a"}, {"id": "b", "extra": 1}]

    def test_subject_id_required(self):
        with pytest.raises(ValidationError):
            Decision()  # type: ignore[call-arg]


class TestDecisionLifecycle:
    def test_with_status_returns_new_instance(self):
        d = make_decision()
        updated = d.with_status(DecisionStatus.ACCEPTED)
        assert updated.status == DecisionStatus.ACCEPTED
        assert d.status == DecisionStatus.OPEN  # 原对象不变 (不可变流转语义)

    def test_with_status_accepts_string(self):
        d = make_decision()
        assert d.with_status("accepted").status == DecisionStatus.ACCEPTED

    def test_to_dict_json_serializable(self):
        d = make_decision()
        data = d.to_dict()
        assert json.loads(json.dumps(data)) == data
        assert data["subject_id"] == "task-1"
        assert data["status"] == "open"
        assert data["evidence"][0]["source_type"] == "event"

    def test_decision_is_not_approval(self):
        # Decision 状态机独立于 Approval: 无 pending/approved 审批语义
        d = make_decision()
        assert d.status.value not in {"pending", "approved"}
        assert set(DecisionStatus.__members__) == {"OPEN", "RECOMMENDED", "ACCEPTED", "REJECTED"}


# ------------------------------------------------------------------ Recommendation


class TestRecommendationModel:
    def test_defaults(self):
        r = Recommendation(target_type="provider", target_id="hermes", score=0.9)
        assert r.reasoning == []
        assert r.evidence == []
        assert r.confidence == 0.5
        assert r.risk == 0.0
        assert r.id

    def test_reasoning_supports_explanation(self):
        r = make_recommendation(reasoning=["capability match", "lowest cost", "success 92%"])
        assert len(r.reasoning) == 3
        assert r.reasoning[0] == "capability match"

    def test_score_range_validation(self):
        with pytest.raises(ValidationError):
            Recommendation(target_type="p", target_id="x", score=1.5)
        with pytest.raises(ValidationError):
            Recommendation(target_type="p", target_id="x", score=-0.1)
        assert Recommendation(target_type="p", target_id="x", score=1.0).score == 1.0

    def test_confidence_risk_range_validation(self):
        with pytest.raises(ValidationError):
            Recommendation(target_type="p", target_id="x", score=0.5, confidence=1.1)
        with pytest.raises(ValidationError):
            Recommendation(target_type="p", target_id="x", score=0.5, risk=-0.5)

    def test_evidence_coerced_from_dicts(self):
        r = Recommendation(
            target_type="p",
            target_id="x",
            score=0.5,
            evidence=[{"source_type": "artifact", "source_id": "art-1"}],
        )
        assert r.evidence[0].lineage_ref() == "artifact:art-1"

    def test_target_fields(self):
        r = make_recommendation(target_type="agent", target_id="agent-1")
        assert r.target_type == "agent"
        assert r.target_id == "agent-1"

    def test_to_dict_roundtrip(self):
        r = make_recommendation()
        data = r.to_dict()
        assert json.loads(json.dumps(data)) == data
        assert data["reasoning"] == ["capability match", "low cost"]

    def test_recommendation_carries_no_execution_instruction(self):
        # 只推荐不执行: 模型无任何执行指令字段 (边界铁律)
        r = make_recommendation()
        assert "execute" not in r.to_dict()
        assert r.to_dict().get("action") is None


# ------------------------------------------------------------------ ExperienceRecord


class TestExperienceRecordModel:
    def test_domain_five_values(self):
        assert [e.value for e in ExperienceDomain] == [
            "provider",
            "agent",
            "workflow",
            "project",
            "decision",
        ]

    @pytest.mark.parametrize(
        "domain", ["provider", "agent", "workflow", "project", "decision"]
    )
    def test_domain_accepted(self, domain):
        assert make_experience(domain=domain).domain == ExperienceDomain(domain)

    def test_domain_invalid_rejected(self):
        with pytest.raises(ValidationError):
            make_experience(domain="skill")

    def test_result_success_failure(self):
        assert make_experience(result="failure").result == ExperienceResult.FAILURE
        assert make_experience().result == ExperienceResult.SUCCESS
        with pytest.raises(ValidationError):
            make_experience(result="partial")

    def test_score_confidence_freshness_range(self):
        with pytest.raises(ValidationError):
            make_experience(score=1.1)
        with pytest.raises(ValidationError):
            make_experience(confidence=-0.1)
        with pytest.raises(ValidationError):
            make_experience(freshness=1.5)

    def test_usage_defaults(self):
        e = make_experience()
        assert e.usage_count == 0
        assert e.last_used is None
        assert e.freshness == 1.0

    def test_subject_id_required(self):
        with pytest.raises(ValidationError):
            ExperienceRecord(domain="provider", score=0.5)  # type: ignore[call-arg]

    def test_failure_result_is_negative_evidence(self):
        # 反事实记录: 失败样本同样落库 (防自我循环偏差)
        e = make_experience(result="failure", score=0.2)
        assert e.result == ExperienceResult.FAILURE
        assert e.score == 0.2

    def test_to_dict_json_serializable(self):
        e = make_experience()
        data = e.to_dict()
        assert json.loads(json.dumps(data)) == data
        assert data["domain"] == "provider"
        assert data["result"] == "success"


# ------------------------------------------------------------------ Evidence


class TestEvidenceModel:
    def test_six_source_types(self):
        assert [s.value for s in EvidenceSource] == [
            "artifact",
            "event",
            "experience",
            "external_data",
            "human_input",
            "provider_output",
        ]

    @pytest.mark.parametrize(
        "source_type",
        ["artifact", "event", "experience", "external_data", "human_input", "provider_output"],
    )
    def test_all_source_types_accepted(self, source_type):
        e = make_evidence(source_type=source_type)
        assert e.source_type == EvidenceSource(source_type)

    def test_source_type_invalid_rejected(self):
        with pytest.raises(ValidationError):
            make_evidence(source_type="llm_guess")

    def test_confidence_range(self):
        assert make_evidence(confidence=0.0).confidence == 0.0
        assert make_evidence(confidence=1.0).confidence == 1.0
        with pytest.raises(ValidationError):
            make_evidence(confidence=1.01)

    def test_defaults(self):
        e = Evidence(source_type="event", source_id="evt-1")
        assert e.description == ""
        assert e.confidence == 1.0
        assert e.timestamp  # 自动 UTC 时间戳

    def test_lineage_ref(self):
        e = make_evidence(source_type="event", source_id="evt-abc")
        assert e.lineage_ref() == "event:evt-abc"

    def test_to_dict_roundtrip(self):
        e = make_evidence()
        data = e.to_dict()
        assert json.loads(json.dumps(data)) == data
        assert data["source_type"] == "event"


# ------------------------------------------------------------------ decay_freshness


class TestDecayFreshness:
    def test_age_zero_is_fresh(self):
        assert decay_freshness(0.0, 86400.0 * 30) == 1.0

    def test_one_half_life_half(self):
        assert decay_freshness(86400.0 * 30, 86400.0 * 30) == 0.5

    def test_two_half_lives_quarter(self):
        assert decay_freshness(86400.0 * 60, 86400.0 * 30) == 0.25

    def test_never_negative(self):
        assert decay_freshness(86400.0 * 3650, 86400.0 * 30) > 0.0

    def test_half_life_zero_rejected(self):
        with pytest.raises(ValueError):
            decay_freshness(1.0, 0.0)

    def test_negative_age_rejected(self):
        with pytest.raises(ValueError):
            decay_freshness(-1.0, 86400.0)
