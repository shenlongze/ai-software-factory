"""tests/assignment/test_agent_matcher.py — AgentMatcher (role/skill/AVAILABLE/排序/无候选)。"""

from __future__ import annotations

from agents.models import AgentStatus
from agents.registry import AgentRegistry
from assignment.matcher import AgentMatcher

from assignment_helpers import make_agent, make_step


def _register(registry: AgentRegistry, *agents) -> None:
    for a in agents:
        registry.register(a)


class TestFiltering:
    def test_role_must_match(self, matcher: AgentMatcher, agent_registry: AgentRegistry):
        _register(
            agent_registry,
            make_agent("A-001", role="backend-developer"),
            make_agent("A-002", role="test-engineer"),
        )
        step = make_step(required_role="backend-developer")
        agents = [a.id for a, _ in matcher.candidates(step)]
        assert agents == ["A-001"]

    def test_skill_must_be_included(self, matcher: AgentMatcher, agent_registry: AgentRegistry):
        _register(
            agent_registry,
            make_agent("A-001", skills=["development"]),
            make_agent("A-002", skills=["testing"]),
        )
        step = make_step(required_skill="development")
        agents = [a.id for a, _ in matcher.candidates(step)]
        assert agents == ["A-001"]

    def test_status_must_be_available(self, matcher: AgentMatcher, agent_registry: AgentRegistry):
        _register(
            agent_registry,
            make_agent("A-001", status=AgentStatus.AVAILABLE),
            make_agent("A-002", status=AgentStatus.WORKING),
            make_agent("A-003", status=AgentStatus.OFFLINE),
        )
        step = make_step()
        agents = [a.id for a, _ in matcher.candidates(step)]
        assert agents == ["A-001"]

    def test_single_required_skill_qualifies(self, matcher: AgentMatcher, agent_registry: AgentRegistry):
        _register(
            agent_registry,
            make_agent("A-001", skills=["development", "flutter"]),
            make_agent("A-002", skills=["development"]),
        )
        step = make_step(required_skill="development")
        assert {a.id for a, _ in matcher.candidates(step)} == {"A-001", "A-002"}

    def test_no_candidates_returns_empty(self, matcher: AgentMatcher, agent_registry: AgentRegistry):
        _register(agent_registry, make_agent("A-001", role="test-engineer", skills=["testing"]))
        step = make_step(required_role="backend-developer", required_skill="development")
        assert matcher.candidates(step) == []

    def test_empty_registry_returns_empty(self, matcher: AgentMatcher):
        step = make_step()
        assert matcher.candidates(step) == []


class TestRanking:
    def test_ranking_by_skill_match_count(self, matcher: AgentMatcher, agent_registry: AgentRegistry):
        """多必需技能时按命中数降序: 覆盖 2 个的排在覆盖 1 个的前面 (skill 匹配数量优先)。

        WorkflowStep.required_skill 为单值 (str), 多技能匹配走 match_criteria 直连。
        """
        _register(
            agent_registry,
            make_agent("A-001", skills=["flutter"]),                      # 命中 1
            make_agent("A-002", skills=["flutter", "backend"]),           # 命中 2
            make_agent("A-003", skills=["flutter", "backend", "testing"]),  # 命中 2
        )
        ranked = matcher.match_criteria(
            required_role="backend-developer", required_skill=["flutter", "backend"],
        )
        assert [a.id for a, _ in ranked] == ["A-002", "A-003", "A-001"]
        assert [n for _, n in ranked] == [2, 2, 1]

    def test_tie_break_by_agent_id(self, matcher: AgentMatcher, agent_registry: AgentRegistry):
        """同分 (单必需技能) 时按 agent id 升序 — 确定性。"""
        _register(
            agent_registry,
            make_agent("B-001", skills=["development"]),
            make_agent("A-001", skills=["development"]),
            make_agent("C-001", skills=["development"]),
        )
        step = make_step(required_skill="development")
        assert [a.id for a, _ in matcher.candidates(step)] == ["A-001", "B-001", "C-001"]

    def test_matched_count_reported(self, matcher: AgentMatcher, agent_registry: AgentRegistry):
        _register(agent_registry, make_agent("A-001", skills=["flutter", "backend"]))
        ranked = matcher.match_criteria(required_skill=["flutter", "backend"])
        assert ranked == [(agent_registry.get("A-001"), 2)]


class TestStepRequirements:
    def test_step_with_no_requirements_matches_all_available(self, matcher: AgentMatcher, agent_registry: AgentRegistry):
        _register(
            agent_registry,
            make_agent("A-001", role="backend-developer"),
            make_agent("A-002", role="test-engineer", status=AgentStatus.WORKING),
            make_agent("A-003", role="ops-engineer"),
        )
        step = make_step(required_skill=None, required_role=None)
        assert [a.id for a, _ in matcher.candidates(step)] == ["A-001", "A-003"]

    def test_step_requires_role_only(self, matcher: AgentMatcher, agent_registry: AgentRegistry):
        _register(
            agent_registry,
            make_agent("A-001", role="backend-developer", skills=["anything"]),
            make_agent("A-002", role="backend-developer", skills=["development"]),
            make_agent("A-003", role="test-engineer"),
        )
        step = make_step(required_skill=None, required_role="backend-developer")
        assert [a.id for a, _ in matcher.candidates(step)] == ["A-001", "A-002"]

    def test_step_requires_skill_only(self, matcher: AgentMatcher, agent_registry: AgentRegistry):
        _register(
            agent_registry,
            make_agent("A-001", role="backend-developer", skills=["development"]),
            make_agent("A-002", role="test-engineer", skills=["development"]),
            make_agent("A-003", role="backend-developer", skills=["testing"]),
        )
        step = make_step(required_role=None, required_skill="development")
        assert [a.id for a, _ in matcher.candidates(step)] == ["A-001", "A-002"]


class TestBest:
    def test_best_returns_top_candidate(self, matcher: AgentMatcher, agent_registry: AgentRegistry):
        """单必需技能全部合格同分 → 取 id 序首位 (确定性)。"""
        _register(
            agent_registry,
            make_agent("B-001", skills=["development"]),
            make_agent("A-001", skills=["development"]),
        )
        step = make_step(required_skill="development")
        assert matcher.best(step) == agent_registry.get("A-001")

    def test_best_returns_role_qualified_only(self, matcher: AgentMatcher, agent_registry: AgentRegistry):
        _register(
            agent_registry,
            make_agent("A-001", role="backend-developer"),
            make_agent("A-002", role="test-engineer"),
        )
        step = make_step(required_role="backend-developer")
        assert matcher.best(step) == agent_registry.get("A-001")

    def test_best_none_when_no_candidates(self, matcher: AgentMatcher):
        assert matcher.best(make_step()) is None
