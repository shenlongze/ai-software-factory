"""tests/intelligence/test_intelligence_store.py — 三 Store 写读往返 (Phase 10A-1)。

覆盖: DecisionStore / RecommendationStore / ExperienceStore 的 save/get/list/
count/过滤 + 独立数据空间 (三文件互不干扰) + 逐字段 round-trip (created_at
陷阱: 逐字段比较 + 时间戳相等, 不构造同参新对象)。
"""

from __future__ import annotations

import json
from pathlib import Path

from intelligence.models import Decision, ExperienceDomain, Recommendation
from intelligence.store import DecisionStore, ExperienceStore, RecommendationStore

from intelligence_helpers import (
    TS_OLD,
    assert_decision_equal,
    assert_experience_equal,
    assert_recommendation_equal,
    make_decision,
    make_experience,
    make_recommendation,
)


# ------------------------------------------------------------------ DecisionStore


class TestDecisionStore:
    def test_save_get_roundtrip(self, decision_store):
        d = make_decision()
        decision_store.save(d)
        got = decision_store.get("dec-1")
        assert got is not None
        assert_decision_equal(got, d)

    def test_save_upserts_same_id(self, decision_store):
        decision_store.save(make_decision(decision_id="dec-1", description="v1"))
        decision_store.save(make_decision(decision_id="dec-1", description="v2"))
        assert decision_store.count() == 1
        assert decision_store.get("dec-1").description == "v2"

    def test_list_all_sorted_by_id(self, decision_store):
        decision_store.save(make_decision(decision_id="b"))
        decision_store.save(make_decision(decision_id="a"))
        decision_store.save(make_decision(decision_id="c"))
        assert [d.id for d in decision_store.list_all()] == ["a", "b", "c"]

    def test_list_by_subject(self, decision_store):
        decision_store.save(make_decision(decision_id="d1", subject_id="task-1"))
        decision_store.save(make_decision(decision_id="d2", subject_id="task-2"))
        decision_store.save(make_decision(decision_id="d3", subject_id="task-1"))
        got = decision_store.list_by_subject("task-1")
        assert [d.id for d in got] == ["d1", "d3"]

    def test_get_missing_returns_none(self, decision_store):
        assert decision_store.get("nope") is None

    def test_count(self, decision_store):
        assert decision_store.count() == 0
        decision_store.save(make_decision(decision_id="d1"))
        decision_store.save(make_decision(decision_id="d2"))
        assert decision_store.count() == 2

    def test_empty_dir_is_empty_store(self, decision_store):
        assert decision_store.list_all() == []
        assert decision_store.count() == 0

    def test_evidence_and_options_preserved(self, decision_store):
        d = make_decision(
            options=[{"id": "a", "title": "A"}, {"id": "b"}],
            evidence=[{"source_type": "human_input", "source_id": "h-1", "confidence": 0.8}],
        )
        decision_store.save(d)
        got = decision_store.get(d.id)
        assert got.options == d.options
        assert [e.lineage_ref() for e in got.evidence] == ["human_input:h-1"]
        assert got.evidence[0].confidence == 0.8

    def test_non_ascii_roundtrip(self, decision_store):
        d = make_decision(description="选择 Provider 供应商 — 中文描述 ✓")
        decision_store.save(d)
        assert decision_store.get(d.id).description == "选择 Provider 供应商 — 中文描述 ✓"


# ------------------------------------------------------------------ RecommendationStore


class TestRecommendationStore:
    def test_save_get_roundtrip(self, recommendation_store):
        r = make_recommendation()
        recommendation_store.save(r)
        got = recommendation_store.get("rec-1")
        assert got is not None
        assert_recommendation_equal(got, r)

    def test_list_all_sorted(self, recommendation_store):
        recommendation_store.save(make_recommendation(rec_id="r2"))
        recommendation_store.save(make_recommendation(rec_id="r1"))
        assert [r.id for r in recommendation_store.list_all()] == ["r1", "r2"]

    def test_list_by_target(self, recommendation_store):
        recommendation_store.save(make_recommendation(rec_id="r1", target_type="provider", target_id="hermes"))
        recommendation_store.save(make_recommendation(rec_id="r2", target_type="provider", target_id="claude"))
        recommendation_store.save(make_recommendation(rec_id="r3", target_type="agent", target_id="agent-1"))
        got = recommendation_store.list_by_target("provider", "hermes")
        assert [r.id for r in got] == ["r1"]

    def test_reasoning_explanation_preserved(self, recommendation_store):
        r = make_recommendation(reasoning=["原因一: 能力匹配", "原因二: 零成本"])
        recommendation_store.save(r)
        got = recommendation_store.get(r.id)
        assert got.reasoning == ["原因一: 能力匹配", "原因二: 零成本"]

    def test_upsert(self, recommendation_store):
        recommendation_store.save(make_recommendation(rec_id="r1", score=0.5))
        recommendation_store.save(make_recommendation(rec_id="r1", score=0.99))
        assert recommendation_store.count() == 1
        assert recommendation_store.get("r1").score == 0.99

    def test_count_and_missing(self, recommendation_store):
        assert recommendation_store.count() == 0
        assert recommendation_store.get("x") is None


# ------------------------------------------------------------------ ExperienceStore


class TestExperienceStore:
    def test_save_get_roundtrip(self, experience_store):
        e = make_experience()
        experience_store.save(e)
        got = experience_store.get("exp-1")
        assert got is not None
        assert_experience_equal(got, e)

    def test_list_by_domain(self, experience_store):
        experience_store.save(make_experience(exp_id="e1", domain="provider", subject_id="hermes"))
        experience_store.save(make_experience(exp_id="e2", domain="agent", subject_id="agent-1"))
        experience_store.save(make_experience(exp_id="e3", domain="provider", subject_id="claude"))
        got = experience_store.list_by_domain("provider")
        assert [e.id for e in got] == ["e1", "e3"]
        assert [e.subject_id for e in got] == ["hermes", "claude"]

    def test_list_by_domain_accepts_enum(self, experience_store):
        experience_store.save(make_experience(exp_id="e1", domain="workflow"))
        got = experience_store.list_by_domain(ExperienceDomain.WORKFLOW)
        assert [e.id for e in got] == ["e1"]

    def test_find_by_subject(self, experience_store):
        experience_store.save(make_experience(exp_id="e1", domain="provider", subject_id="hermes"))
        experience_store.save(make_experience(exp_id="e2", domain="provider", subject_id="hermes"))
        experience_store.save(make_experience(exp_id="e3", domain="agent", subject_id="hermes"))
        assert len(experience_store.find("hermes")) == 3
        assert [e.id for e in experience_store.find("hermes", domain="provider")] == ["e1", "e2"]
        assert experience_store.find("unknown") == []

    def test_usage_fields_preserved(self, experience_store):
        e = make_experience(usage_count=7, last_used=TS_OLD, freshness=0.5)
        experience_store.save(e)
        got = experience_store.get(e.id)
        assert got.usage_count == 7
        assert got.last_used == TS_OLD
        assert got.freshness == 0.5

    def test_failure_samples_stored(self, experience_store):
        experience_store.save(make_experience(exp_id="fail-1", result="failure", score=0.1))
        got = experience_store.get("fail-1")
        assert got.result.value == "failure"
        assert got.score == 0.1

    def test_upsert(self, experience_store):
        experience_store.save(make_experience(exp_id="e1", score=0.3))
        experience_store.save(make_experience(exp_id="e1", score=0.9))
        assert experience_store.count() == 1
        assert experience_store.get("e1").score == 0.9


# ------------------------------------------------------------------ 独立数据空间


class TestIndependentDataSpace:
    def test_three_stores_share_dir_but_separate_files(
        self,
        intelligence_dir: Path,
        decision_store,
        recommendation_store,
        experience_store,
    ):
        decision_store.save(make_decision())
        recommendation_store.save(make_recommendation())
        experience_store.save(make_experience())
        files = sorted(p.name for p in intelligence_dir.iterdir())
        assert files == ["decisions.json", "experiences.json", "recommendations.json"]
        # 每文件单节结构
        raw = json.loads((intelligence_dir / "decisions.json").read_text(encoding="utf-8"))
        assert set(raw.keys()) == {"decisions"}
        assert "dec-1" in raw["decisions"]

    def test_stores_do_not_see_each_others_records(
        self, decision_store, recommendation_store, experience_store
    ):
        decision_store.save(make_decision())
        assert recommendation_store.count() == 0
        assert experience_store.count() == 0
        recommendation_store.save(make_recommendation())
        assert decision_store.count() == 1
        assert experience_store.count() == 0

    def test_independent_directory_layout(self, tmp_path: Path):
        """数据空间只落在 <root>/intelligence/ 下, 不在工厂根散落文件。"""
        root = tmp_path / "factory"
        DecisionStore(root / "intelligence").save(make_decision(decision_id="d1"))
        RecommendationStore(root / "intelligence").save(make_recommendation(rec_id="r1"))
        ExperienceStore(root / "intelligence").save(make_experience(exp_id="e1"))
        assert sorted(p.name for p in root.iterdir()) == ["intelligence"]
        assert sorted(p.name for p in (root / "intelligence").iterdir()) == [
            "decisions.json",
            "experiences.json",
            "recommendations.json",
        ]

    def test_saved_json_is_hand_editable_shape(self, intelligence_dir: Path, decision_store):
        """落盘 JSON 形状稳定 (节内 id → 记录 dict, 便于人工审计/修复)。"""
        decision_store.save(make_decision())
        raw = json.loads((intelligence_dir / "decisions.json").read_text(encoding="utf-8"))
        record = raw["decisions"]["dec-1"]
        assert record["decision_type"] == "provider_selection"
        assert record["subject_id"] == "task-1"
        assert isinstance(record["evidence"], list)

    def test_models_roundtrip_through_json(self, decision_store, recommendation_store, experience_store):
        """三模型经 store 落盘读回后仍可 model_dump (类型完整)。"""
        d = make_decision()
        r = make_recommendation()
        e = make_experience()
        decision_store.save(d)
        recommendation_store.save(r)
        experience_store.save(e)
        assert isinstance(decision_store.get(d.id), Decision)
        assert isinstance(recommendation_store.get(r.id), Recommendation)
        got_e = experience_store.get(e.id)
        assert got_e.domain == ExperienceDomain.PROVIDER
        assert got_e.to_dict()["usage_count"] == 0
