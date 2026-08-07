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
    FeatureContext,
    TaskProfile,
    analyze_task,
    detect_task_type,
    extract_acceptance,
    extract_candidate_features,
    extract_symbol_candidates,
    score_dependency_distance,
    score_experience_match,
    score_history_success,
    score_keyword_match,
    score_symbol_relation,
    score_test_relation,
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


# ================================================================ §2 Task Analyzer

class _DuckTask:
    """duck-typed 任务 (对齐 ExecutionRequest: objective/requirement/task_id/id)。"""

    def __init__(
        self,
        objective: str,
        requirement: str = "",
        task_id: str = "T-RANK-1",
        id: str = "REQ-RANK-1",
    ) -> None:
        self.objective = objective
        self.requirement = requirement
        self.task_id = task_id
        self.id = id


class TestTaskTypeDetection:
    """规则检测 (bug_fix > greenfield > feature; 零 LLM)。"""

    def test_bug_fix_chinese(self) -> None:
        assert detect_task_type("修复文件列表加载报错") == "bug_fix"

    def test_bug_fix_english(self) -> None:
        assert detect_task_type("Fix the crash when saving") == "bug_fix"
        assert detect_task_type("handle exception in parser") == "bug_fix"

    def test_greenfield_chinese(self) -> None:
        assert detect_task_type("新建一个设置页面") == "greenfield"
        assert detect_task_type("从零搭建项目脚手架") == "greenfield"

    def test_greenfield_english(self) -> None:
        assert detect_task_type("Create a new module") == "greenfield"

    def test_feature_default(self) -> None:
        assert detect_task_type("增加导出功能") == "feature"
        assert detect_task_type("Add pagination to the list") == "feature"

    def test_bug_fix_priority_over_greenfield(self) -> None:
        """「新建…修复报错」语义是修 bug → bug_fix 优先 (预算最小)。"""
        assert detect_task_type("新建页面后修复崩溃问题") == "bug_fix"

    def test_requirement_joined_into_detection(self) -> None:
        assert detect_task_type("优化列表", "滚动时出现异常") == "bug_fix"

    def test_unknown_type_normalized(self) -> None:
        p = TaskProfile(objective="x", task_type="bogus")
        assert p.task_type == "feature"


class TestTaskProfile:
    """TaskProfile 模型 + analyze_task (结构化解析)。"""

    def test_analyze_task_full(self) -> None:
        task = _DuckTask(
            "修复 replaceCurrent 只替换当前匹配的问题",
            "验收: 1. 光标处替换生效; 2. 其他匹配不受影响",
            task_id="T-BUG-9",
        )
        p = analyze_task(task)
        assert p.task_type == "bug_fix"
        assert p.task_id == "T-BUG-9"
        assert "replace" in p.keywords and "current" in p.keywords
        assert "replaceCurrent" in p.symbol_candidates
        assert len(p.acceptance) >= 1

    def test_analyze_task_id_fallback(self) -> None:
        class _NoTaskId:
            objective = "add feature"
            requirement = ""
            id = "REQ-X"

        p = analyze_task(_NoTaskId())
        assert p.task_id == "REQ-X"

    def test_analyze_task_missing_fields(self) -> None:
        p = analyze_task(object())  # 无任何字段 → 空 objective
        assert p.objective == ""
        assert p.keywords == []
        assert p.symbol_candidates == []
        assert p.task_type == "feature"

    def test_explicit_task_type_overrides(self) -> None:
        task = _DuckTask("修复崩溃问题")
        p = analyze_task(task, task_type="feature")
        assert p.task_type == "feature"  # 显式覆盖规则检测

    def test_symbol_candidates_extraction(self) -> None:
        syms = extract_symbol_candidates(
            "fix _cloneBlock crash and replaceCurrent flow"
        )
        assert "_cloneBlock" in syms or "cloneblock" in syms
        assert "replaceCurrent" in syms

    def test_symbol_candidates_dedup_order(self) -> None:
        syms = extract_symbol_candidates("doThing then doThing again")
        assert syms.count("doThing") == 1
        assert syms[0] == "doThing"

    def test_symbol_candidates_empty(self) -> None:
        assert extract_symbol_candidates("修复列表显示问题") == []

    def test_acceptance_extraction_numbered(self) -> None:
        a = extract_acceptance("实现搜索", "1. 输入关键词即时过滤\n2. 结果高亮")
        assert len(a) == 2
        assert a[0] == "输入关键词即时过滤"

    def test_acceptance_extraction_markers(self) -> None:
        a = extract_acceptance("新增设置页", "验收: 设置项应能保存并重启后保留")
        assert any("保存并重启后保留" in e for e in a)

    def test_acceptance_extraction_cleanup_anchored(self) -> None:
        """编号清理只剥行首 (不误删句中 '1.')。"""
        a = extract_acceptance("x", "step 1. keep the number in sentence")
        assert not a  # 无验收标记无列表样式 → 不提取

    def test_acceptance_cap_at_eight(self) -> None:
        req = "\n".join(f"{i}. item {i}" for i in range(1, 12))
        a = extract_acceptance("x", req)
        assert len(a) == 8

    def test_profile_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            TaskProfile(objective="x", bogus=1)  # type: ignore[call-arg]

    def test_profile_to_dict(self) -> None:
        p = TaskProfile(objective="x", task_type="bug_fix")
        d = p.to_dict()
        assert d["task_type"] == "bug_fix"
        assert d["acceptance"] == []


# ================================================================ §3 Feature Extractor

class TestKeywordMatchFactor:
    """因素 1 — 关键词命中 (精确 1.0 / 前缀 0.8 / 包含 0.6 / 无 0)。"""

    def test_exact_match(self) -> None:
        assert score_keyword_match(["replace"], ["replace"]) == 1.0

    def test_prefix_match(self) -> None:
        assert score_keyword_match(["replace"], ["replace_current"]) == 0.8

    def test_contains_match(self) -> None:
        assert score_keyword_match(["replace"], ["my_replacer"]) == 0.6

    def test_no_match(self) -> None:
        assert score_keyword_match(["zzz"], ["app/main.py"]) == 0.0

    def test_empty_keywords_or_names(self) -> None:
        assert score_keyword_match([], ["a.py"]) == 0.0
        assert score_keyword_match(["a"], []) == 0.0

    def test_best_of_multiple(self) -> None:
        """多关键词×多名字取最高分 (前缀 0.8 > 包含 0.6)。"""
        assert score_keyword_match(["fix", "save"], ["save_flow", "main.py"]) == 0.8

    def test_path_and_symbol_names(self) -> None:
        names = ["app/main.py", "replace_current", "run"]
        assert score_keyword_match(["replace"], names) == 0.8
        assert score_keyword_match(["main"], names) == 0.6  # 路径段包含命中

    def test_case_insensitive(self) -> None:
        assert score_keyword_match(["Replace"], ["REPLACE"]) == 1.0


class TestSymbolRelationFactor:
    """因素 2 — 候选与任务符号关系 (定义 1.0 / 调用 0.7 / 被调 0.5 / 无关 0)。"""

    def test_defines_symbol(self) -> None:
        assert score_symbol_relation({"run"}, set(), set(), {"run"}) == 1.0

    def test_calls_symbol(self) -> None:
        assert score_symbol_relation(set(), {"helper"}, set(), {"helper"}) == 0.7

    def test_called_by_symbol_caller(self) -> None:
        assert score_symbol_relation(set(), set(), {"run"}, {"run"}) == 0.5

    def test_unrelated(self) -> None:
        assert score_symbol_relation({"run"}, set(), set(), {"other"}) == 0.0

    def test_definition_priority_over_calls(self) -> None:
        """同一符号既定义又调用 → 定义优先 (1.0)。"""
        assert score_symbol_relation({"run"}, {"run"}, set(), {"run"}) == 1.0

    def test_case_insensitive(self) -> None:
        assert score_symbol_relation({"Run"}, set(), set(), {"run"}) == 1.0

    def test_empty_symbols(self) -> None:
        assert score_symbol_relation({"run"}, set(), set(), set()) == 0.0


class TestDependencyDistanceFactor:
    """因素 3 — 依赖距离 (直接 1.0 / 间接 0.5 / 无关 0.1)。"""

    def test_target_itself(self) -> None:
        assert score_dependency_distance(0) == 1.0

    def test_direct_dependency(self) -> None:
        assert score_dependency_distance(1) == 1.0

    def test_indirect(self) -> None:
        assert score_dependency_distance(2) == 0.5

    def test_unrelated(self) -> None:
        assert score_dependency_distance(None) == 0.1


class TestTestRelationFactor:
    """因素 4 — 测试关系 (目标 1.0 / 相关 0.6 / 无 0)。"""

    def test_target_test(self) -> None:
        assert score_test_relation(True, False) == 1.0

    def test_related_test(self) -> None:
        assert score_test_relation(False, True) == 0.6

    def test_no_relation(self) -> None:
        assert score_test_relation(False, False) == 0.0

    def test_target_over_related(self) -> None:
        assert score_test_relation(True, True) == 1.0


class TestHistorySuccessFactor:
    """因素 5 — 历史成功率 (冷启动 None → 0.5 中性)。"""

    def test_cold_start_neutral(self) -> None:
        assert score_history_success(None) == 0.5

    def test_high_rate(self) -> None:
        assert score_history_success(0.9) == 0.9

    def test_low_rate(self) -> None:
        assert score_history_success(0.2) == 0.2

    def test_rate_clamped(self) -> None:
        assert score_history_success(1.5) == 1.0
        assert score_history_success(-0.5) == 0.0


class TestExperienceMatchFactor:
    """因素 6 — 历史失败模式匹配 (symbol miss 提权 +0.2; 首轮 0)。"""

    def test_symbol_miss_history_boost(self) -> None:
        assert score_experience_match(True) == 0.2

    def test_no_history(self) -> None:
        assert score_experience_match(False) == 0.0


class TestFeatureContextExtraction:
    """FeatureContext + extract_candidate_features (6 维装配)。"""

    def _code_candidate(self, rel: str = "app/main.py") -> ContextCandidate:
        return ContextCandidate(id=f"code:{rel}", type="code", source=rel, token_cost=50)

    def test_code_candidate_all_six_factors(self) -> None:
        profile = TaskProfile(objective="fix replace crash", task_type="bug_fix")
        ctx = FeatureContext(
            keywords=["replacecurrent"],
            symbol_candidates=["replacecurrent"],
            core_files={"app/main.py"},
            defined_symbols={"app/main.py": {"replacecurrent"}},
            history_rates={"app/main.py": 0.8},
            symbol_miss_files={"app/main.py"},
        )
        f = extract_candidate_features(self._code_candidate(), profile, ctx)
        assert set(f) == {
            "keyword_match", "symbol_relation", "dependency_distance",
            "test_relation", "history_success", "experience_match",
        }
        assert f["keyword_match"] == 1.0          # 符号名精确命中
        assert f["symbol_relation"] == 1.0        # 定义任务符号
        assert f["dependency_distance"] == 1.0    # 核心目标
        assert f["test_relation"] == 0.0
        assert f["history_success"] == 0.8
        assert f["experience_match"] == 0.2       # symbol miss 提权

    def test_related_code_file_factors(self) -> None:
        profile = TaskProfile(objective="fix replace crash")
        ctx = FeatureContext(
            keywords=["replace"],
            symbol_candidates=["replacecurrent"],
            core_files={"app/main.py"},
            depends_on_core={"util/helper.py"},
            defined_symbols={"util/helper.py": {"helper"}},
            caller_symbols={"util/helper.py": {"replacecurrent"}},
        )
        f = extract_candidate_features(self._code_candidate("util/helper.py"), profile, ctx)
        assert f["dependency_distance"] == 1.0    # 直接依赖
        assert f["symbol_relation"] == 0.5        # 被任务符号调用方调用
        assert f["history_success"] == 0.5        # 冷启动中性

    def test_indirect_file_factor(self) -> None:
        profile = TaskProfile(objective="add feature xyz")
        ctx = FeatureContext(
            core_files={"app/main.py"}, indirect={"deep/other.py"}
        )
        f = extract_candidate_features(self._code_candidate("deep/other.py"), profile, ctx)
        assert f["dependency_distance"] == 0.5

    def test_test_candidate_factors(self) -> None:
        profile = TaskProfile(objective="fix replace crash")
        c = ContextCandidate(id="test:tests/test_main.py", type="test",
                             source="tests/test_main.py")
        ctx = FeatureContext(
            keywords=["replace"],
            core_files={"app/main.py"},
            target_tests={"tests/test_main.py"},
            history_rates={"tests/test_main.py": 0.6},
        )
        f = extract_candidate_features(c, profile, ctx)
        assert f["test_relation"] == 1.0          # 目标测试
        assert f["dependency_distance"] == 0.1    # 无关基线
        assert f["symbol_relation"] == 0.0
        assert f["history_success"] == 0.6

    def test_related_test_candidate_factor(self) -> None:
        profile = TaskProfile(objective="fix replace crash")
        c = ContextCandidate(id="test:tests/test_util.py", type="test",
                             source="tests/test_util.py")
        ctx = FeatureContext(
            core_files={"app/main.py"}, related_tests={"tests/test_util.py"}
        )
        f = extract_candidate_features(c, profile, ctx)
        assert f["test_relation"] == 0.6

    def test_experience_candidate_uses_own_rate(self) -> None:
        profile = TaskProfile(objective="fix replace crash")
        c = ContextCandidate(id="exp:development", type="experience",
                             source="experience:development",
                             content_ref="experience:development")
        ctx = FeatureContext(history_rates={"__experience__": 0.3})
        f = extract_candidate_features(c, profile, ctx)
        assert f["history_success"] == 0.3
        assert f["experience_match"] == 0.0

    def test_aggregate_candidate_factors(self) -> None:
        profile = TaskProfile(objective="fix replace crash")
        c = ContextCandidate(id="arch:summary", type="architecture",
                             source="architecture:summary",
                             content_ref="architecture:summary-replace-flow")
        ctx = FeatureContext(keywords=["arch"])
        f = extract_candidate_features(c, profile, ctx)
        assert f["keyword_match"] == 0.8          # 前缀命中 content_ref
        assert f["dependency_distance"] == 0.1
        assert f["symbol_relation"] == 0.0
        assert f["test_relation"] == 0.0

    def test_header_words_in_keyword_match(self) -> None:
        profile = TaskProfile(objective="fix parser crash")
        ctx = FeatureContext(
            keywords=["parser"],
            headers={"app/main.py": "parser tokenize render"},
        )
        f = extract_candidate_features(self._code_candidate(), profile, ctx)
        assert f["keyword_match"] == 1.0          # 内容头词精确命中

    def test_cold_start_neutral_history(self) -> None:
        profile = TaskProfile(objective="fix replace crash")
        ctx = FeatureContext(keywords=["replace"], core_files={"app/main.py"})
        f = extract_candidate_features(self._code_candidate(), profile, ctx)
        assert f["history_success"] == 0.5

    def test_unrelated_file_low_ranking_factors(self) -> None:
        profile = TaskProfile(objective="fix replace crash")
        ctx = FeatureContext(keywords=["zzz"], core_files={"app/main.py"})
        f = extract_candidate_features(self._code_candidate("docs/readme.md"), profile, ctx)
        assert f["keyword_match"] == 0.0
        assert f["dependency_distance"] == 0.1
