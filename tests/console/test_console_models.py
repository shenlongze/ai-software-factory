"""tests/console/test_console_models.py — 9 响应模型 + ConsoleDashboard 七域 (Phase 11A, ADR-0034)。

覆盖 (factory-console/models.py):
- 各响应模型默认值/归一化 (tech_stack/capability/evidence/options/factors 等
  容器字段 None/字符串 → 列表/dict, pydantic mode="before" validator)
- 数值约束 (confidence/score/risk 0-1, 计数 ge=0)
- ConsoleDashboard 七域 SECTIONS 键序 + 派生属性 (active_projects /
  pending_approvals / running_agents / cost_summary / experience_summary /
  activity_summary)
- to_dict() = model_dump(mode="json") (CLI --json/测试断言共用)

basename 全仓库唯一 (test_console_* 前缀)。
"""

from __future__ import annotations

import importlib

import pytest
from pydantic import ValidationError

_MODELS = importlib.import_module("factory-console.models")

ProjectSummary = _MODELS.ProjectSummary
LifecycleSummary = _MODELS.LifecycleSummary
ApprovalSummary = _MODELS.ApprovalSummary
DecisionSummary = _MODELS.DecisionSummary
RecommendationSummary = _MODELS.RecommendationSummary
ExperienceSummary = _MODELS.ExperienceSummary
ProviderSummary = _MODELS.ProviderSummary
CostSummary = _MODELS.CostSummary
ExperienceSummaryModel = _MODELS.ExperienceSummaryModel
AgentSummary = _MODELS.AgentSummary
EventSummary = _MODELS.EventSummary
ConsoleDashboard = _MODELS.ConsoleDashboard


# ------------------------------------------------------------------ ProjectSummary


class TestProjectSummary:
    def test_defaults(self):
        p = ProjectSummary(id="demo")
        assert p.name == ""
        assert p.status == "active"
        assert p.tech_stack == []
        assert p.tasks == {}
        assert p.pending_approvals == 0
        assert p.lifecycle_stage is None
        assert p.last_activity is None

    def test_tech_stack_none_to_empty(self):
        assert ProjectSummary(id="demo", tech_stack=None).tech_stack == []

    def test_tech_stack_csv_string_coerced(self):
        p = ProjectSummary(id="demo", tech_stack="python, flask,,go")
        assert p.tech_stack == ["python", "flask", "go"]

    def test_tasks_none_and_int_coercion(self):
        assert ProjectSummary(id="demo", tasks=None).tasks == {}
        p = ProjectSummary(id="demo", tasks={"BACKLOG": 3, "RUNNING": "1"})
        assert p.tasks == {"BACKLOG": 3, "RUNNING": 1}

    def test_pending_approvals_negative_rejected(self):
        with pytest.raises(ValidationError):
            ProjectSummary(id="demo", pending_approvals=-1)

    def test_to_dict_json(self):
        d = ProjectSummary(id="demo", name="Demo", tech_stack=["python"]).to_dict()
        assert d["id"] == "demo"
        assert d["tech_stack"] == ["python"]
        assert d["tasks"] == {}


# ------------------------------------------------------------------ LifecycleSummary


class TestLifecycleSummary:
    def test_defaults(self):
        s = LifecycleSummary(project_id="demo")
        assert s.lifecycle_id is None
        assert s.template_name == ""
        assert s.status == ""
        assert s.current_stage is None
        assert s.completed_stages == []
        assert s.next_actions == []
        assert s.pending_approval is None

    def test_str_lists_coerced(self):
        s = LifecycleSummary(project_id="demo", completed_stages=None, next_actions="a,b")
        assert s.completed_stages == []
        assert s.next_actions == ["a", "b"]

    def test_to_dict(self):
        s = LifecycleSummary(project_id="demo", status="running", completed_stages=["research"])
        d = s.to_dict()
        assert d["project_id"] == "demo"
        assert d["completed_stages"] == ["research"]


# ------------------------------------------------------------------ ApprovalSummary


class TestApprovalSummary:
    def test_defaults(self):
        a = ApprovalSummary(id="req-1", artifact_id="art-1")
        assert a.gate == ""
        assert a.status == "pending"
        assert a.confidence == 0.0
        assert a.risk is None
        assert a.evidence == []
        assert a.by == "human"

    def test_evidence_coerced(self):
        assert ApprovalSummary(id="r", artifact_id="a", evidence=None).evidence == []
        a = ApprovalSummary(id="r", artifact_id="a", evidence="e1,e2")
        assert a.evidence == ["e1", "e2"]

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            ApprovalSummary(id="r", artifact_id="a", confidence=1.5)
        with pytest.raises(ValidationError):
            ApprovalSummary(id="r", artifact_id="a", confidence=-0.1)

    def test_to_dict(self):
        a = ApprovalSummary(id="r", artifact_id="a", gate="prd", status="pending",
                            confidence=0.8, risk="medium", idea_id="idea-1",
                            artifact_version=2)
        d = a.to_dict()
        assert d["gate"] == "prd"
        assert d["artifact_version"] == 2
        assert d["idea_id"] == "idea-1"


# ------------------------------------------------------------------ DecisionSummary


class TestDecisionSummary:
    def test_defaults(self):
        d = DecisionSummary(id="dec-1")
        assert d.decision_type == "general"
        assert d.status == "open"
        assert d.options == []
        assert d.recommendation is None
        assert d.score == 0.0
        assert d.confidence == 0.5
        assert d.risk_level == "low"
        assert d.requires_approval is False

    def test_options_none_to_empty(self):
        assert DecisionSummary(id="d", options=None).options == []

    def test_options_factors_coerced(self):
        d = DecisionSummary(id="d", options=[{"id": "a", "score": 0.9,
                                              "factors": {"capability": 0.9, "cost": "0.8"}}])
        assert d.options[0]["factors"] == {"capability": 0.9, "cost": 0.8}

    def test_str_lists_coerced(self):
        d = DecisionSummary(id="d", reasoning=None, evidence="evt:1,evt:2")
        assert d.reasoning == []
        assert d.evidence == ["evt:1", "evt:2"]

    def test_score_bounds(self):
        with pytest.raises(ValidationError):
            DecisionSummary(id="d", score=1.1)

    def test_to_dict(self):
        d = DecisionSummary(id="dec-1", recommendation="a", score=0.9,
                            requires_approval=True, approval_request_id="req-9")
        dd = d.to_dict()
        assert dd["recommendation"] == "a"
        assert dd["requires_approval"] is True
        assert dd["approval_request_id"] == "req-9"


# ------------------------------------------------------------------ RecommendationSummary


class TestRecommendationSummary:
    def test_requires_score(self):
        with pytest.raises(ValidationError):
            RecommendationSummary(id="rec-1")

    def test_factors_none_to_empty(self):
        r = RecommendationSummary(id="rec-1", score=0.9, factors=None)
        assert r.factors == {}

    def test_factors_non_numeric_skipped(self):
        r = RecommendationSummary(id="rec-1", score=0.9,
                                  factors={"capability": 0.7, "note": "x"})
        assert r.factors == {"capability": 0.7}

    def test_explanation_evidence_coerced(self):
        r = RecommendationSummary(id="rec-1", score=0.9, explanation=None,
                                  evidence="evt:1")
        assert r.explanation == []
        assert r.evidence == ["evt:1"]

    def test_to_dict(self):
        r = RecommendationSummary(id="rec-1", target_type="provider", score=0.92)
        d = r.to_dict()
        assert d["target_type"] == "provider"
        assert d["confidence"] == 0.5


# ------------------------------------------------------------------ ExperienceSummary


class TestExperienceSummary:
    def test_defaults(self):
        e = ExperienceSummary(id="exp-1", score=0.9)
        assert e.domain == ""
        assert e.result == "success"
        assert e.freshness == 1.0
        assert e.capability == []

    def test_capability_coerced(self):
        e = ExperienceSummary(id="exp-1", score=0.9, capability=None)
        assert e.capability == []
        assert ExperienceSummary(id="exp-1", score=0.9, capability="a,b").capability == ["a", "b"]

    def test_score_bounds(self):
        with pytest.raises(ValidationError):
            ExperienceSummary(id="exp-1", score=1.01)

    def test_to_dict(self):
        e = ExperienceSummary(id="exp-1", domain="provider", score=0.95,
                              subject="provider:hermes", result="success")
        d = e.to_dict()
        assert d["subject"] == "provider:hermes"
        assert d["result"] == "success"


# ------------------------------------------------------------------ ProviderSummary


class TestProviderSummary:
    def test_defaults(self):
        p = ProviderSummary(id="hermes")
        assert p.status == "ACTIVE"
        assert p.type == "cloud"
        assert p.cost is None
        assert p.performance is None
        assert p.experience is None
        assert p.usage_calls == 0

    def test_str_lists_coerced(self):
        p = ProviderSummary(id="hermes", capabilities=None, models="m1,m2")
        assert p.capabilities == []
        assert p.models == ["m1", "m2"]

    def test_score_fields_bounds(self):
        with pytest.raises(ValidationError):
            ProviderSummary(id="hermes", cost=1.5)
        with pytest.raises(ValidationError):
            ProviderSummary(id="hermes", usage_calls=-1)

    def test_to_dict(self):
        p = ProviderSummary(id="hermes", cost=0.8, usage_calls=5)
        d = p.to_dict()
        assert d["cost"] == 0.8
        assert d["usage_calls"] == 5


# ------------------------------------------------------------------ CostSummary / ExperienceSummaryModel


class TestCostSummary:
    def test_defaults_zero(self):
        c = CostSummary()
        assert c.total_cost == 0.0
        assert c.calls == 0
        assert c.success_rate == 0.0
        assert c.avg_cost == 0.0
        assert c.total_tokens == 0
        assert c.by_provider == {}

    def test_by_provider_none_to_empty(self):
        assert CostSummary(by_provider=None).by_provider == {}

    def test_bounds(self):
        with pytest.raises(ValidationError):
            CostSummary(success_rate=1.1)
        with pytest.raises(ValidationError):
            CostSummary(total_cost=-0.1)

    def test_to_dict(self):
        c = CostSummary(total_cost=0.03, calls=3).to_dict()
        assert c["total_cost"] == 0.03
        assert c["calls"] == 3


class TestExperienceSummaryModel:
    def test_defaults_zero(self):
        e = ExperienceSummaryModel()
        assert e.total == 0
        assert e.by_domain == {}
        assert e.success_rate == 0.0
        assert e.avg_score == 0.0
        assert e.avg_confidence == 0.0

    def test_by_domain_none_to_empty(self):
        assert ExperienceSummaryModel(by_domain=None).by_domain == {}

    def test_to_dict(self):
        e = ExperienceSummaryModel(total=2, by_domain={"provider": 2}).to_dict()
        assert e["total"] == 2
        assert e["by_domain"] == {"provider": 2}


# ------------------------------------------------------------------ AgentSummary / EventSummary


class TestAgentSummary:
    def test_defaults(self):
        a = AgentSummary(id="agent-1")
        assert a.status == "AVAILABLE"
        assert a.skills == []
        assert a.current_task is None

    def test_skills_coerced(self):
        assert AgentSummary(id="a", skills=None).skills == []
        assert AgentSummary(id="a", skills="python,go").skills == ["python", "go"]

    def test_to_dict(self):
        a = AgentSummary(id="agent-1", status="WORKING", current_task="task-1")
        d = a.to_dict()
        assert d["status"] == "WORKING"
        assert d["current_task"] == "task-1"


class TestEventSummary:
    def test_defaults(self):
        e = EventSummary()
        assert e.seq == 0
        assert e.type == ""
        assert e.project_id is None
        assert e.action is None
        assert e.result is None

    def test_to_dict(self):
        e = EventSummary(seq=3, type="console.viewed", source="cli").to_dict()
        assert e["seq"] == 3
        assert e["type"] == "console.viewed"
        assert e["source"] == "cli"


# ------------------------------------------------------------------ ConsoleDashboard


class TestConsoleDashboard:
    def test_sections_order(self):
        assert ConsoleDashboard.SECTIONS == (
            "projects", "approvals", "agents", "decisions", "cost", "experience", "activity",
        )

    def test_empty_dashboard_defaults(self):
        d = ConsoleDashboard()
        assert d.projects == []
        assert d.approvals == []
        assert d.agents == []
        assert d.decisions == []
        assert isinstance(d.cost, CostSummary)
        assert isinstance(d.experience, ExperienceSummaryModel)
        assert d.activity == []

    def test_cost_none_coerced(self):
        d = ConsoleDashboard(cost=None)
        assert isinstance(d.cost, CostSummary)
        assert d.cost.calls == 0

    def test_experience_none_coerced(self):
        d = ConsoleDashboard(experience=None)
        assert isinstance(d.experience, ExperienceSummaryModel)
        assert d.experience.total == 0

    def test_active_projects_property(self):
        d = ConsoleDashboard(projects=[
            ProjectSummary(id="a", status="active"),
            ProjectSummary(id="b", status="archived"),
        ])
        assert [p.id for p in d.active_projects] == ["a"]

    def test_pending_approvals_property(self):
        d = ConsoleDashboard(approvals=[
            ApprovalSummary(id="r1", artifact_id="a1", status="pending"),
            ApprovalSummary(id="r2", artifact_id="a2", status="approved"),
        ])
        assert [a.id for a in d.pending_approvals] == ["r1"]

    def test_running_agents_property(self):
        d = ConsoleDashboard(agents=[
            AgentSummary(id="a1", status="WORKING"),
            AgentSummary(id="a2", status="AVAILABLE"),
        ])
        assert [a.id for a in d.running_agents] == ["a1"]

    def test_cost_and_experience_properties(self):
        d = ConsoleDashboard(cost=CostSummary(calls=2), experience=ExperienceSummaryModel(total=3))
        assert d.cost_summary.calls == 2
        assert d.experience_summary.total == 3
        assert d.activity_summary == []

    def test_to_dict(self):
        d = ConsoleDashboard(projects=[ProjectSummary(id="a")])
        dd = d.to_dict()
        assert set(dd) == set(ConsoleDashboard.SECTIONS)
        assert dd["projects"][0]["id"] == "a"
