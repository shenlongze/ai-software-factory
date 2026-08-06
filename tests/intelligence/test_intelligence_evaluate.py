"""tests/intelligence/test_intelligence_evaluate.py — TaskEvaluator 任务评估器
(Phase 10A-4, ADR-0033): TaskRequirement → 历史经验分组聚合 → 推荐执行资源。

覆盖 (任务要求 ≥100 中的任务评估部分):
- Cold start (无记录 → 空推荐 + 低置信度 + 风险提示; 不惩罚主体)
- 推荐分组 (agent/provider/skill 按 subject_type; 有效分 ≥ 0.5 中性门槛)
- 排序 (有效分降序) + 每类封顶 5 个
- 非执行域 (workflow/project/decision) 不参与推荐
- 正负聚合 (成功提高/失败降低; 失败主导 → 低于门槛不推荐 + 风险)
- 置信度规则 (分数差距/类型覆盖/候选深度) + 低置信度风险
- 过滤 (task_type + capability) / 增强字段 (quality/cost/duration)
- 事件 (intelligence.task.evaluated + 载荷; logger=None 静默)
- Failure cases (缺 task_type → ValidationError)

basename 全仓库唯一 (test_intelligence_* 前缀)。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from intelligence.evaluate import (
    EVALUATION_SUBJECT_TYPES,
    TaskEvaluator,
)
from intelligence.experience import RECOMMEND_THRESHOLD
from intelligence.models import (
    TaskEvaluation,
    TaskRequirement,
)

from intelligence_helpers import (
    event_types_of,
    make_experience,
    payload_of,
    TS_LATE,
    TS_OLD,
)


def _evaluator(store=None, logger=None, *, now=None, half_life_days=30.0):
    # now 缺省注入固定时钟 TS_LATE — 记录 created_at=TS_LATE 时 freshness=1.0,
    # 避免真实 UTC (2026-08+) 相对 TS_LATE 产生 5+ 半衰期衰减 (测试确定性)
    if now is None:
        now = lambda: TS_LATE
    return TaskEvaluator(store, logger, now=now, half_life_days=half_life_days)


def _req(task_type="development", capabilities=("code",)):
    return TaskRequirement(
        task_type=task_type,
        required_capabilities=list(capabilities),
    )


def _agent_ok(score=0.9, **kw):
    base = dict(
        exp_id="exp-agent", domain="agent", subject_id="coder-1", subject_type="agent",
        task_type="development", capability=["code"],
        score=score, confidence=1.0, created_at=TS_LATE,
    )
    base.update(kw)
    return make_experience(**base)


def _provider_ok(score=0.8, **kw):
    base = dict(
        exp_id="exp-provider", domain="provider", subject_id="hermes", subject_type="provider",
        task_type="development", capability=["code"],
        score=score, confidence=1.0, created_at=TS_LATE,
    )
    base.update(kw)
    return make_experience(**base)


def _skill_ok(score=0.85, **kw):
    base = dict(
        exp_id="exp-skill", domain="skill", subject_id="python", subject_type="skill",
        task_type="development", capability=["code"],
        score=score, confidence=1.0, created_at=TS_LATE,
    )
    base.update(kw)
    return make_experience(**base)


def _agent_fail(**kw):
    base = dict(
        exp_id="exp-agent-fail", domain="agent", subject_id="buggy", subject_type="agent",
        task_type="development", capability=["code"],
        result="failure", score=0.3, confidence=0.8, created_at=TS_LATE,
    )
    base.update(kw)
    return make_experience(**base)


# ------------------------------------------------------- Cold start


class TestColdStart:
    def test_empty_evaluation(self, experience_store):
        ev = _evaluator(experience_store).evaluate(_req())
        assert isinstance(ev, TaskEvaluation)
        assert ev.task_type == "development"
        assert ev.required_capabilities == ["code"]
        assert ev.recommended_agents == []
        assert ev.recommended_providers == []
        assert ev.recommended_skills == []
        assert ev.recommended_count() == 0

    def test_cold_start_confidence_zero(self, experience_store):
        ev = _evaluator(experience_store).evaluate(_req())
        assert ev.confidence == 0.0

    def test_cold_start_risk(self, experience_store):
        ev = _evaluator(experience_store).evaluate(_req())
        assert any("冷启动" in r for r in ev.risks)
        assert any("人工确认" in r for r in ev.risks)

    def test_cold_start_reasoning(self, experience_store):
        ev = _evaluator(experience_store).evaluate(_req())
        assert any("无匹配历史经验" in r for r in ev.reasoning)

    def test_no_store_cold_start(self):
        ev = _evaluator(None).evaluate(_req())
        assert ev.recommended_count() == 0
        assert ev.confidence == 0.0

    def test_cold_start_not_an_error(self, experience_store):
        # 无经验不惩罚: 空推荐是正常结果, 不是失败
        ev = _evaluator(experience_store).evaluate(_req())
        assert ev.confidence < 0.5  # 低置信度 → 需人工确认


# ------------------------------------------------------- 推荐分组与排序


class TestRecommendation:
    def test_recommends_agent(self, experience_store):
        experience_store.save(_agent_ok())
        ev = _evaluator(experience_store).evaluate(_req())
        assert [e["id"] for e in ev.recommended_agents] == ["coder-1"]
        assert ev.recommended_agents[0]["score"] > RECOMMEND_THRESHOLD

    def test_recommends_provider(self, experience_store):
        experience_store.save(_provider_ok())
        ev = _evaluator(experience_store).evaluate(_req())
        assert [e["id"] for e in ev.recommended_providers] == ["hermes"]

    def test_recommends_skill(self, experience_store):
        experience_store.save(_skill_ok())
        ev = _evaluator(experience_store).evaluate(_req())
        assert [e["id"] for e in ev.recommended_skills] == ["python"]

    def test_all_three_types(self, experience_store):
        experience_store.save(_agent_ok())
        experience_store.save(_provider_ok())
        experience_store.save(_skill_ok())
        ev = _evaluator(experience_store).evaluate(_req())
        assert ev.recommended_count() == 3
        assert ev.recommended_agents[0]["subject_type"] == "agent"
        assert ev.recommended_providers[0]["subject_type"] == "provider"
        assert ev.recommended_skills[0]["subject_type"] == "skill"

    def test_ranks_descending_within_type(self, experience_store):
        experience_store.save(_agent_ok(score=0.9, exp_id="e1"))
        experience_store.save(_agent_ok(score=0.7, subject_id="coder-2", exp_id="e2"))
        experience_store.save(_agent_ok(score=0.8, subject_id="coder-3", exp_id="e3"))
        ev = _evaluator(experience_store).evaluate(_req())
        ids = [e["id"] for e in ev.recommended_agents]
        assert ids == ["coder-1", "coder-3", "coder-2"]
        scores = [e["score"] for e in ev.recommended_agents]
        assert scores == sorted(scores, reverse=True)

    def test_groups_multiple_records_same_subject(self, experience_store):
        experience_store.save(_agent_ok(score=0.9, exp_id="e1"))
        experience_store.save(_agent_ok(score=0.7, exp_id="e2"))
        ev = _evaluator(experience_store).evaluate(_req())
        assert len(ev.recommended_agents) == 1  # 同主体合并为一组
        assert ev.recommended_agents[0]["records"] == 2
        assert ev.recommended_agents[0]["score"] == pytest.approx(0.8)

    def test_entry_shape(self, experience_store):
        experience_store.save(_agent_ok())
        ev = _evaluator(experience_store).evaluate(_req())
        entry = ev.recommended_agents[0]
        assert set(entry) == {"id", "subject_type", "score", "records", "success_rate", "reasoning"}
        assert entry["success_rate"] == 1.0
        assert entry["reasoning"]

    def test_max_five_per_type(self, experience_store):
        for i in range(7):
            experience_store.save(
                _agent_ok(score=0.9, subject_id=f"coder-{i}", exp_id=f"e{i}")
            )
        ev = _evaluator(experience_store).evaluate(_req())
        assert len(ev.recommended_agents) == 5  # 每类封顶 5 个

    def test_non_execution_domains_excluded(self, experience_store):
        """workflow/project/decision 域记录不参与执行资源推荐 (非执行候选)。"""
        experience_store.save(_agent_ok())
        for domain, sid in (("workflow", "wf-1"), ("project", "proj-1"), ("decision", "dec-1")):
            experience_store.save(
                make_experience(
                    domain=domain, subject_id=sid, subject_type=domain,
                    task_type="development", capability=["code"],
                    score=0.9, confidence=1.0, created_at=TS_LATE,
                )
            )
        ev = _evaluator(experience_store).evaluate(_req())
        assert ev.recommended_count() == 1  # 只有 agent 被推荐
        assert [e["id"] for e in ev.recommended_agents] == ["coder-1"]


# ------------------------------------------------------- 门槛与正负聚合


class TestThresholdAndFeedback:
    def test_below_neutral_threshold_not_recommended(self, experience_store):
        experience_store.save(_agent_fail())
        ev = _evaluator(experience_store).evaluate(_req())
        assert ev.recommended_agents == []  # 全失败 → 有效分 0.0 < 0.5

    def test_failure_dominant_risk(self, experience_store):
        experience_store.save(_agent_ok(score=0.5, exp_id="e1"))
        experience_store.save(_agent_fail(exp_id="e2"))
        ev = _evaluator(experience_store).evaluate(_req())
        assert any("负经验主导" in r for r in ev.risks)
        assert "agent:buggy" in ev.risks[0]

    def test_below_threshold_risk(self, experience_store):
        experience_store.save(_agent_fail())
        ev = _evaluator(experience_store).evaluate(_req())
        assert any("低于中性门槛" in r for r in ev.risks)
        assert any("agent:buggy" in r for r in ev.risks)

    def test_mixed_success_failure_score(self, experience_store):
        experience_store.save(_agent_ok(score=0.9, exp_id="e1"))
        experience_store.save(_agent_fail(score=0.5, subject_id="coder-1", exp_id="e2"))
        ev = _evaluator(experience_store).evaluate(_req())
        # 同主体分组: (0.9 - 0.5) / 2 = 0.2 < 0.5 → 不推荐
        assert ev.recommended_agents == []

    def test_success_overcomes_single_failure(self, experience_store):
        experience_store.save(_agent_ok(score=0.9, exp_id="e1"))
        experience_store.save(_agent_ok(score=0.9, exp_id="e2"))
        # confidence=1.0: 失败记录有效分 = 0.3×1.0×freshness(1.0) = 0.3
        # (_agent_fail 缺省 confidence=0.8 会得到 0.24 → 0.52, 偏离边界语义)
        experience_store.save(
            _agent_fail(score=0.3, subject_id="coder-1", exp_id="e3", confidence=1.0)
        )
        ev = _evaluator(experience_store).evaluate(_req())
        # 同主体分组: (0.9 + 0.9 - 0.3) / 3 = 0.5 ≥ 0.5 → 刚好过门槛
        assert len(ev.recommended_agents) == 1
        assert ev.recommended_agents[0]["score"] == pytest.approx(0.5)

    def test_freshness_decay_lowers_score(self, experience_store):
        experience_store.save(_agent_ok(score=0.9, created_at=TS_OLD))
        ev = _evaluator(experience_store, now=lambda: TS_LATE).evaluate(_req())
        # 60 天 → 2 个半衰期 → freshness 0.25 → effective 0.225 < 0.5
        assert ev.recommended_agents == []
        assert any("低于中性门槛" in r for r in ev.risks)

    def test_recent_experience_recommended(self, experience_store):
        experience_store.save(_agent_ok(score=0.9, created_at=TS_LATE))
        ev = _evaluator(experience_store, now=lambda: TS_LATE).evaluate(_req())
        assert [e["id"] for e in ev.recommended_agents] == ["coder-1"]

    def test_success_rate_in_entry(self, experience_store):
        experience_store.save(_agent_ok(score=0.9, exp_id="e1"))
        experience_store.save(_agent_fail(subject_id="coder-1", exp_id="e2"))
        ev = _evaluator(experience_store).evaluate(_req())
        # 同主体: 成功 1 / 失败 1 → 成功率 0.5; 有效分 (0.9-0.3)/2=0.3 < 0.5 → 不推荐
        assert ev.recommended_agents == []


# ------------------------------------------------------- 过滤


class TestFiltering:
    def test_filters_by_task_type(self, experience_store):
        experience_store.save(_agent_ok())
        experience_store.save(
            _agent_ok(task_type="testing", subject_id="tester-1", exp_id="e2")
        )
        ev = _evaluator(experience_store).evaluate(_req(task_type="development"))
        assert [e["id"] for e in ev.recommended_agents] == ["coder-1"]

    def test_filters_by_capability(self, experience_store):
        experience_store.save(_agent_ok())
        experience_store.save(
            _agent_ok(capability=["design"], subject_id="designer-1", exp_id="e2")
        )
        ev = _evaluator(experience_store).evaluate(_req(capabilities=("code",)))
        assert [e["id"] for e in ev.recommended_agents] == ["coder-1"]

    def test_no_capability_required_matches_all(self, experience_store):
        experience_store.save(_agent_ok())
        experience_store.save(_provider_ok())
        ev = _evaluator(experience_store).evaluate(_req(capabilities=()))
        assert ev.recommended_count() == 2

    def test_reasoning_mentions_record_count(self, experience_store):
        experience_store.save(_agent_ok())
        experience_store.save(_provider_ok())
        ev = _evaluator(experience_store).evaluate(_req())
        text = "\n".join(ev.reasoning)
        assert "基于 2 条历史经验评估" in text
        assert "task_type='development'" in text


# ------------------------------------------------------- 置信度


class TestConfidence:
    def test_single_entry_confidence_spread(self, experience_store):
        experience_store.save(_agent_ok())
        ev = _evaluator(experience_store).evaluate(_req())
        # spread = top = 0.9; coverage = 1/3; depth = 1/5
        # 0.5×0.9 + 0.3×0.333 + 0.2×0.2 = 0.45 + 0.1 + 0.04 = 0.59
        assert ev.confidence == pytest.approx(0.59)

    def test_three_types_confidence(self, experience_store):
        experience_store.save(_agent_ok())
        experience_store.save(_provider_ok())
        experience_store.save(_skill_ok())
        ev = _evaluator(experience_store).evaluate(_req())
        # spread = 0.9-0.85=0.05; coverage = 3/3 = 1; depth = 3/5 = 0.6
        # 0.5×0.05 + 0.3×1 + 0.2×0.6 = 0.025 + 0.3 + 0.12 = 0.445
        assert ev.confidence == pytest.approx(0.445)

    def test_low_confidence_risk(self, experience_store):
        # 低分单主体: spread=0.55 → confidence 0.415 < 0.5 → 低置信度风险
        experience_store.save(_agent_ok(score=0.55))
        ev = _evaluator(experience_store).evaluate(_req())
        assert ev.confidence < 0.5
        assert any("置信度低" in r for r in ev.risks)

    def test_high_confidence_no_risk(self, experience_store):
        for i in range(5):
            experience_store.save(
                _agent_ok(score=0.9, subject_id=f"c-{i}", exp_id=f"e{i}")
            )
        for i in range(3):
            experience_store.save(
                _provider_ok(score=0.9, subject_id=f"p-{i}", exp_id=f"pe{i}")
            )
        experience_store.save(_skill_ok())
        ev = _evaluator(experience_store).evaluate(_req())
        assert ev.confidence >= 0.5
        assert not any("置信度低" in r for r in ev.risks)


# ------------------------------------------------------- 事件


class TestEvaluateEvents:
    def test_evaluate_fires_task_evaluated(self, logger):
        ev = _evaluator(None, logger).evaluate(_req())
        types = event_types_of(logger.store)
        assert types == ["intelligence.task.evaluated"]

    def test_task_evaluated_payload(self, experience_store, logger):
        # 成功 agent + 失败 provider → 有低于门槛风险 → risk_count ≥ 1
        experience_store.save(_agent_ok())
        experience_store.save(_provider_ok(score=0.2, result="failure"))
        _evaluator(experience_store, logger).evaluate(_req())
        payload = payload_of(logger.store, "intelligence.task.evaluated")
        assert payload["task_type"] == "development"
        assert payload["required_capabilities"] == ["code"]
        assert payload["recommended_agent_count"] == 1
        assert payload["recommended_provider_count"] == 0
        assert payload["recommended_skill_count"] == 0
        assert payload["confidence"] == pytest.approx(0.73)
        assert payload["risk_count"] >= 1

    def test_evaluate_silent_without_logger(self, experience_store):
        ev = _evaluator(experience_store, None).evaluate(_req())
        assert ev.recommended_count() == 0  # 无 logger 不崩

    def test_evaluate_after_records_chain(self, experience_store, logger):
        """闭环: record_experience (feedback.learned) → evaluate (task.evaluated)。"""
        from intelligence.experience import ExperienceAnalyzer

        an = ExperienceAnalyzer(experience_store, logger)
        an.record_experience(subject_type="agent", subject_id="coder-1",
                             task_type="development", capability=["code"],
                             score=0.9, confidence=1.0)
        _evaluator(experience_store, logger).evaluate(_req())
        types = event_types_of(logger.store)
        assert types.index("intelligence.feedback.learned") < types.index(
            "intelligence.task.evaluated"
        )


# ------------------------------------------------------- Failure cases / 模型


class TestTaskRequirementModel:
    def test_requirement_defaults(self):
        r = TaskRequirement(task_type="development")
        assert r.required_capabilities == []
        assert r.quality_target is None
        assert r.budget is None
        assert r.constraints == []

    def test_requirement_none_lists_coerced(self):
        r = TaskRequirement(task_type="development", required_capabilities=None,
                            constraints=None)  # type: ignore[arg-type]
        assert r.required_capabilities == []
        assert r.constraints == []

    def test_requirement_missing_task_type_rejected(self):
        with pytest.raises(ValidationError):
            TaskRequirement()  # type: ignore[call-arg]

    def test_evaluation_to_dict_json_serializable(self, experience_store):
        import json

        experience_store.save(_agent_ok())
        ev = _evaluator(experience_store).evaluate(_req())
        data = ev.to_dict()
        assert json.loads(json.dumps(data)) == data
        assert data["task_type"] == "development"
        assert data["recommended_agents"][0]["id"] == "coder-1"

    def test_injected_analyzer_shared_clock(self, experience_store):
        from intelligence.experience import ExperienceAnalyzer

        analyzer = ExperienceAnalyzer(experience_store, now=lambda: TS_LATE)
        experience_store.save(_agent_ok(created_at=TS_LATE))
        ev = TaskEvaluator(experience_store, analyzer=analyzer).evaluate(_req())
        assert [e["id"] for e in ev.recommended_agents] == ["coder-1"]

    def test_evaluation_subject_types_constant(self):
        assert EVALUATION_SUBJECT_TYPES == ("agent", "provider", "skill")
