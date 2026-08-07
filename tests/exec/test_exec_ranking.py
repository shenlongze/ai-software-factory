"""tests/exec/test_exec_ranking.py — Context Ranking Engine 单元测试 (Sprint 4 T4.1)。

覆盖 (全部纯函数/模型校验, 零 LLM 零网络):
- ContextCandidate 模型: 构造/校验/边界 (评分 clamp / 成本非负 / 类型归一 /
  extra=forbid / factor_scores clamp / char_cost 级别成本)
- Task Analyzer: 类型检测 (bug_fix/feature/greenfield) / 关键词 / 符号候选 / 验收
- Feature Extractor: 6 因素评分纯函数 (边界/权重语义)
- RankingEngine: 加权评分 / 全零→0 / 全满分→1.0 / 权重上限保护 / reason 可复算
- TopKSelector: 排序/核心相关分级/预算截断
- Budget Controller: 任务类型预算 / 降级链各层 / context_overflow

按子任务分节 (每节一个 commit 阶段)。
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from exec.ranking import (
    CANDIDATE_TYPES,
    DEFAULT_TASK_BUDGET,
    HARD_CAP_CHARS,
    LEVEL_DROP,
    LEVEL_FULL,
    LEVEL_ONE_LINE,
    LEVEL_SUMMARY,
    LEVEL_SYMBOL,
    RANKING_WEIGHTS,
    TASK_TYPE_BUDGETS,
    TASK_TYPES,
    ContextCandidate,
)

# ================================================================ §1 ContextCandidate 模型


class TestContextCandidateModel:
    """模型构造/校验/审计 (设计 §2: reason 可复算, 内容延迟加载)。"""

    def test_minimal_construction_defaults(self) -> None:
        c = ContextCandidate(id="code:app/main.py")
        assert c.type == "code"
        assert c.source == ""
        assert c.content_ref == ""
        assert c.token_cost == 0
        assert c.relevance_score == 0.0
        assert c.confidence == 0.0
        assert c.factor_scores == {}
        assert c.reason == ""

    def test_full_construction(self) -> None:
        c = ContextCandidate(
            id="code:app/main.py",
            type="code",
            source="app/main.py",
            content_ref="app/main.py:1-120",
            token_cost=300,
            relevance_score=0.75,
            reason="keyword_match 1.0×0.35=0.350",
            confidence=0.83,
            factor_scores={"keyword_match": 1.0, "symbol_relation": 0.7},
        )
        assert c.id == "code:app/main.py"
        assert c.type == "code"
        assert c.content_ref == "app/main.py:1-120"
        assert c.token_cost == 300
        assert c.relevance_score == 0.75
        assert c.confidence == 0.83
        assert c.factor_scores["keyword_match"] == 1.0

    def test_score_clamped_to_unit_interval(self) -> None:
        c = ContextCandidate(id="x", relevance_score=1.5, confidence=-0.2)
        assert c.relevance_score == 1.0
        assert c.confidence == 0.0

    def test_token_cost_non_negative(self) -> None:
        c = ContextCandidate(id="x", token_cost=-50)
        assert c.token_cost == 0

    def test_type_normalized_to_known(self) -> None:
        assert ContextCandidate(id="x", type="bogus").type == "code"
        assert ContextCandidate(id="x", type=None).type == "code"
        assert ContextCandidate(id="x", type="experience").type == "experience"

    def test_factor_scores_clamped(self) -> None:
        c = ContextCandidate(
            id="x", factor_scores={"keyword_match": 2.0, "test_relation": -1.0}
        )
        assert c.factor_scores["keyword_match"] == 1.0
        assert c.factor_scores["test_relation"] == 0.0

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            ContextCandidate(id="x", unknown_field=1)  # type: ignore[call-arg]

    def test_missing_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ContextCandidate()  # type: ignore[call-arg]

    def test_to_dict_json_friendly(self) -> None:
        c = ContextCandidate(id="x", type="test", source="t.py", token_cost=10)
        d = c.to_dict()
        assert set(d) == {
            "id", "type", "source", "content_ref", "token_cost",
            "relevance_score", "reason", "confidence", "factor_scores",
        }
        assert d["token_cost"] == 10

    def test_char_cost_levels(self) -> None:
        """级别成本确定性 (full=token×4 / symbol=×0.8 下限 40 / summary / one_line / drop)。"""
        c = ContextCandidate(id="x", token_cost=100)
        assert c.char_cost(LEVEL_FULL) == 400
        assert c.char_cost(LEVEL_SYMBOL) == 80
        assert c.char_cost(LEVEL_SUMMARY) == 20
        assert c.char_cost(LEVEL_ONE_LINE) == 60
        assert c.char_cost(LEVEL_DROP) == 0

    def test_char_cost_symbol_floor(self) -> None:
        c = ContextCandidate(id="x", token_cost=10)
        assert c.char_cost(LEVEL_SYMBOL) == 40  # 下限保护

    def test_char_cost_unknown_level_zero(self) -> None:
        assert ContextCandidate(id="x").char_cost("bogus") == 0

    def test_audit_reason_recomputable(self) -> None:
        """reason 可复算: factor_scores × 权重 = 分数 (审计保证)。"""
        c = ContextCandidate(
            id="x",
            relevance_score=0.715,
            reason=(
                "keyword_match=0.350(0.35×1.000); symbol_relation=0.175(0.25×0.700); "
                "dependency_distance=0.150(0.15×1.000); test_relation=0.000(0.10×0.000); "
                "history_success=0.040(0.08×0.500); experience_match=0.000(0.07×0.000) "
                "→ score=0.715"
            ),
            factor_scores={
                "keyword_match": 1.0, "symbol_relation": 0.7, "dependency_distance": 1.0,
                "test_relation": 0.0, "history_success": 0.5, "experience_match": 0.0,
            },
        )
        recomputed = sum(
            RANKING_WEIGHTS[k] * v for k, v in c.factor_scores.items()
        )
        assert abs(recomputed - c.relevance_score) < 1e-6


class TestRankingConstants:
    """常量契约 (设计 §4/§5)。"""

    def test_weights_sum_to_one(self) -> None:
        assert abs(sum(RANKING_WEIGHTS.values()) - 1.0) < 1e-9

    def test_six_factors(self) -> None:
        assert set(RANKING_WEIGHTS) == {
            "keyword_match", "symbol_relation", "dependency_distance",
            "test_relation", "history_success", "experience_match",
        }

    def test_weights_order(self) -> None:
        assert RANKING_WEIGHTS["keyword_match"] > RANKING_WEIGHTS["symbol_relation"]
        assert RANKING_WEIGHTS["symbol_relation"] > RANKING_WEIGHTS["dependency_distance"]
        assert RANKING_WEIGHTS["dependency_distance"] > RANKING_WEIGHTS["test_relation"]
        assert RANKING_WEIGHTS["test_relation"] > RANKING_WEIGHTS["history_success"]
        assert RANKING_WEIGHTS["history_success"] > RANKING_WEIGHTS["experience_match"]

    def test_candidate_types(self) -> None:
        assert CANDIDATE_TYPES == ("code", "test", "history", "experience", "architecture")

    def test_task_types_and_budgets(self) -> None:
        assert TASK_TYPES == ("bug_fix", "feature", "greenfield")
        assert TASK_TYPE_BUDGETS["bug_fix"] == 20_000
        assert TASK_TYPE_BUDGETS["feature"] == 25_000
        assert TASK_TYPE_BUDGETS["greenfield"] == 15_000

    def test_default_budget_and_hard_cap(self) -> None:
        assert DEFAULT_TASK_BUDGET == 25_000
        assert HARD_CAP_CHARS == 30_000
