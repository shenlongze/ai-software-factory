"""tests/exec/test_exec_ranking_pipeline.py — Context Ranking Engine 集成测试 (Sprint 4 T4.1 子任务 7)。

覆盖 (真实小项目 RepositoryIntelligence + mock 组件, 零 LLM 零网络):
- CandidateGenerator: 复用 select_symbols/select_files/select_tests/经验聚合 → 候选池
- RankingPipeline 全链: Task → 候选 → 特征 → 评分 → TopK → 预算 → 组装 AssembledContext
- 预算降级链: 中档预算单步收缩 / 小预算多步降级 / 超小预算 overflow 警示
- symbol miss → line_range 提示 + experience_match 提权
- 经验聚合成功率 → 经验候选 history_success 因子
- context.ranking_assemble 新路径 + 失败安全回退旧 assemble
- agent_runtime ranking_enabled 开关 (默认 False 旧路径 / True 新路径 / 失败安全)

helper 复用 tests/exec/exec_helpers.py (唯一名共享模块 — 不跨目录依赖)。
basename 唯一: test_exec_ranking_pipeline.py (test_exec_* 前缀)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from exec.context import ContextAssembler
from exec.progressive import ProgressiveLoader, StageSpec
from exec.ranking import (
    CODE_PROGRESSIVE_STAGES,
    LEVEL_FULL,
    LEVEL_SYMBOL,
    CodeProgressiveProvider,
    RankingPipeline,
    normalize_weights,
)
from exec.repo_intelligence import RepositoryIntelligence
from exec_helpers import FakeProvider, make_request, write_files  # noqa: E402

# ================================================================ fixtures

MINI_PROJECT: dict[str, str] = {
    "app/main.py": (
        "from util import helper\n"
        "\n"
        "def run():\n"
        "    return helper()\n"
        "\n"
        "def replace_current(text):\n"
        "    return text\n"
    ),
    "app/extra.py": (
        "from app.main import run\n"
        "\n"
        "def run_extra():\n"
        "    return run()\n"
    ),
    "app/deep.py": (
        "from app.extra import run_extra\n"
        "\n"
        "def deep():\n"
        "    return run_extra()\n"
    ),
    "util/__init__.py": "",
    "util/helper.py": "def helper():\n    return 42\n",
    "tests/test_main.py": (
        "from app.main import run\n"
        "\n"
        "def test_run():\n"
        "    assert run() == 42\n"
    ),
}

#: symbol miss 场景: 任务引用 my_widget, 仓库无该符号定义 (文件同名)
MISS_PROJECT: dict[str, str] = dict(MINI_PROJECT)
MISS_PROJECT["widgets/my_widget.dart"] = (
    "class WidgetRenderer {\n"
    "  String render() => '';\n"
    "}\n"
)


class _Task:
    """duck-typed 任务 (objective/requirement/source_files/task_id + id — 对齐 ExecutionRequest)。"""

    def __init__(
        self,
        objective: str,
        requirement: str = "",
        source_files: list[str] | None = None,
        task_id: str = "T-RANK-1",
        id: str = "REQ-RANK-1",
    ) -> None:
        self.objective = objective
        self.requirement = requirement
        self.source_files = source_files or []
        self.task_id = task_id
        self.id = id


class _Ev:
    """duck-typed Evidence (description)。"""

    def __init__(self, description: str) -> None:
        self.description = description


class _Rec:
    """duck-typed ExperienceRecord (context.py 只访问 negative_signal/evidence)。"""

    def __init__(
        self,
        *,
        negative_signal: bool = False,
        evidence: list[Any] | None = None,
    ) -> None:
        self.negative_signal = negative_signal
        self.evidence = evidence or []


class FakeAnalyzer:
    """duck-typed ExperienceAnalyzer (records 查询; context.py/ranking 兼容)。"""

    def __init__(self, records: list[Any] | None = None) -> None:
        self._records = list(records or [])

    def records(self, **kwargs: Any) -> list[Any]:
        return list(self._records)


@pytest.fixture
def mini_project(tmp_path: Path) -> Path:
    write_files(tmp_path / "proj", MINI_PROJECT)
    return tmp_path / "proj"


@pytest.fixture
def miss_project(tmp_path: Path) -> Path:
    write_files(tmp_path / "proj2", MISS_PROJECT)
    return tmp_path / "proj2"


def _replace_task() -> _Task:
    return _Task(
        "修复 replace_current 局部替换",
        "1. 局部替换; 2. 无全文替换",
        source_files=["app/main.py"],
    )


# ================================================================ 1. Candidate Generator

class TestCandidateGenerator:
    def test_pool_covers_all_types(self, mini_project: Path) -> None:
        """候选池含 code/test/history/experience/architecture 五类 (聚合不占名额)。"""
        res = RankingPipeline(mini_project).run(_replace_task())
        types = {c.type for c in res.batch.candidates}
        assert {"code", "test", "history", "experience", "architecture"} <= types
        # 核心目标文件在池中
        assert any(c.id == "code:app/main.py" for c in res.batch.candidates)
        # 测试文件只以 test 候选出现 (不重复为 code 候选)
        code_ids = {c.id for c in res.batch.candidates if c.type == "code"}
        assert "code:tests/test_main.py" not in code_ids
        assert any(c.id == "test:tests/test_main.py" for c in res.batch.candidates)

    def test_selection_reuses_context_selectors(self, mini_project: Path) -> None:
        """生成器复用选择器: 核心 = 显式源文件 ∪ 符号命中; 相关 = 影响面/同模块。"""
        res = RankingPipeline(mini_project).run(_replace_task())
        assert res.batch.core_files == ["app/main.py"]
        # 影响面 (import main 的 extra) 进相关; 测试文件也进相关 (作为 test 候选源)
        assert "app/extra.py" in res.batch.related_files
        assert "app/deep.py" in res.batch.related_files
        assert res.batch.test_mapping.get("app/main.py") == ["tests/test_main.py"]

    def test_token_cost_estimated_not_preloaded(self, mini_project: Path) -> None:
        """候选只估 token_cost (内容延迟加载契约 — content_ref 是引用非全文)。"""
        res = RankingPipeline(mini_project).run(_replace_task())
        cand = next(c for c in res.batch.candidates if c.id == "code:app/main.py")
        assert cand.token_cost >= 1
        assert cand.content_ref == "app/main.py"
        assert cand.source == "app/main.py"


# ================================================================ 2. Pipeline 全链

class TestRankingPipelineChain:
    def test_full_chain_returns_assembled(self, mini_project: Path) -> None:
        """六步全链 → AssembledContext (6 节渲染 + 质量分 + 预算统计)。"""
        res = RankingPipeline(mini_project).run(_replace_task())
        assert res.batch.candidates
        assert res.ranked
        assert res.budget.selected_ids
        assert res.assembled is not None
        assert 0.0 <= res.assembled.context_score <= 1.0
        prompt = res.assembled.render_prompt()
        for sec in (
            "## Task",
            "## Architecture context",
            "## Relevant source files",
            "## Change history",
            "## Experience / past lessons",
            "## Related tests",
        ):
            assert sec in prompt
        # 审计摘要可导出
        d = res.to_dict()
        assert d["task_type"] == "bug_fix"
        assert d["candidates"] == len(res.batch.candidates)
        assert d["selected_ids"] == res.budget.selected_ids

    def test_symbol_file_ranked_first(self, mini_project: Path) -> None:
        """replace_current 定义文件 (核心目标) 排第一 (keyword+symbol 双高)。"""
        res = RankingPipeline(mini_project).run(_replace_task())
        assert res.ranked[0].id == "code:app/main.py"
        assert res.ranked[0].relevance_score > 0.5
        # reason 可复算: 贡献和 == 评分
        contrib = sum(res.ranked[0].factor_scores.values())
        assert contrib == pytest.approx(res.ranked[0].relevance_score, abs=1e-3)

    def test_core_full_and_related_symbol_levels(self, mini_project: Path) -> None:
        """级别映射: 距离 0/1 (核心目标+直接依赖) full; 距离 2 相关 symbol; 测试 symbol。"""
        res = RankingPipeline(mini_project).run(_replace_task())
        assert res.budget.levels["code:app/main.py"] == LEVEL_FULL
        assert res.budget.levels["code:app/extra.py"] == LEVEL_FULL
        assert res.budget.levels["code:app/deep.py"] == LEVEL_SYMBOL
        assert res.budget.levels["test:tests/test_main.py"] == LEVEL_SYMBOL

    def test_full_level_renders_line_numbered_content(self, mini_project: Path) -> None:
        """full 级 → 行号前缀全文内联 (N| 定位参考)。"""
        res = RankingPipeline(mini_project).run(_replace_task())
        slices = {f.rel_path: f for f in res.assembled.code.core_files}
        main = slices["app/main.py"]
        assert main.kind == "core"
        assert "def replace_current" in main.content
        assert main.content.splitlines()[0].startswith("1|")
        # related 级 → symbol 索引
        related = {f.rel_path: f for f in res.assembled.code.related_files}
        assert "app/deep.py" in related
        assert related["app/deep.py"].kind == "related"

    def test_test_slices_in_assembled(self, mini_project: Path) -> None:
        """测试候选 → TestContext 节 (symbol 索引级, 不全文)。"""
        res = RankingPipeline(mini_project).run(_replace_task())
        assert res.assembled.test.mapping.get("app/main.py") == ["tests/test_main.py"]
        tests = {f.rel_path: f for f in res.assembled.test.test_files}
        assert "tests/test_main.py" in tests
        assert tests["tests/test_main.py"].kind == "test"


# ================================================================ 3. 预算降级链

class TestPipelineBudget:
    def test_mid_budget_single_step_shrink(self, mini_project: Path) -> None:
        """中档预算 → 第一步 (相关符号收缩 ×0.5) 即达标; 核心保持 full。"""
        res = RankingPipeline(mini_project, budget=250).run(_replace_task())
        assert res.budget.degraded_steps[0] == "related_symbol_shrink"
        assert res.budget.context_overflow is False
        assert res.budget.total_chars <= res.budget.budget_chars
        assert res.budget.levels["code:app/main.py"] == LEVEL_FULL

    def test_small_budget_multi_step_degradation(self, mini_project: Path) -> None:
        """小预算 → 降级链走多步 (核心 full→symbol 逐个 + 丢最低分相关)。"""
        res = RankingPipeline(mini_project, budget=200).run(_replace_task())
        steps = res.budget.degraded_steps
        assert steps[0] == "related_symbol_shrink"
        assert any(s.startswith("core_full_to_symbol:") for s in steps)
        assert any(s.startswith("drop_related:") for s in steps)
        # 核心降级为 symbol 级 (预算下不再全文内联)
        assert res.budget.levels["code:app/main.py"] == LEVEL_SYMBOL
        # 降级链走完仍超 → 诚实 overflow (本工程 one_line 固定 60 会跳升, 数学上无法落回)
        assert res.budget.context_overflow is True
        assert res.budget.total_chars > res.budget.budget_chars

    def test_overflow_warning_and_score_halved(self, mini_project: Path) -> None:
        """超小预算 → overflow 标记 + 经验节警示 + 质量分减半 (执行前警示)。"""
        normal = RankingPipeline(mini_project).run(_replace_task())
        res = RankingPipeline(mini_project, budget=50).run(_replace_task())
        assert res.budget.context_overflow is True
        assert res.assembled is not None  # 降级不炸链
        assert any("预算" in a for a in res.assembled.experience.advice)
        assert res.assembled.context_score < normal.assembled.context_score


# ================================================================ 4. symbol miss → line_range

class TestPipelineSymbolMiss:
    def test_miss_detected_and_line_range_hint(self, miss_project: Path) -> None:
        """任务符号未定义 → miss 记录 + line_range 定位提示 (进经验建议节)。"""
        res = RankingPipeline(miss_project).run(
            _Task("修复 my_widget 渲染异常", source_files=["widgets/my_widget.dart"])
        )
        assert res.symbol_miss == ["my_widget"]
        assert any("line_range" in a for a in res.assembled.experience.advice)
        assert "my_widget" in res.assembled.experience.advice[0]

    def test_miss_file_experience_boost(self, miss_project: Path) -> None:
        """同名文件提权: experience_match 因子 = 0.2 (贡献 0.014 = 0.2×0.07)。"""
        res = RankingPipeline(miss_project).run(
            _Task("修复 my_widget 渲染异常", source_files=["widgets/my_widget.dart"])
        )
        assert res.feature_context.symbol_miss_files == {"widgets/my_widget.dart"}
        cand = next(c for c in res.ranked if c.source == "widgets/my_widget.dart")
        assert cand.factor_scores.get("experience_match", 0.0) == pytest.approx(0.2 * 0.07)

    def test_no_miss_no_hint(self, mini_project: Path) -> None:
        """符号已定义 → 无 miss, 无 line_range 提示 (首轮经验零提权)。"""
        res = RankingPipeline(mini_project).run(_replace_task())
        assert res.symbol_miss == []
        assert not any("line_range" in a for a in res.assembled.experience.advice)


# ================================================================ 5. 经验权重影响

class TestPipelineExperience:
    def test_experience_rate_affects_aggregate_score(self, mini_project: Path) -> None:
        """经验聚合成功率 → 经验候选 history_success 因子 (0.0 vs 冷启动 0.5)。"""
        cold = RankingPipeline(mini_project).run(_replace_task())
        cold_exp = next(c for c in cold.ranked if c.type == "experience")
        assert cold_exp.factor_scores.get("history_success", 0.0) == pytest.approx(0.5 * 0.08)
        # 3 条失败记录 → 成功率 0.0
        analyzer = FakeAnalyzer([_Rec(negative_signal=True) for _ in range(3)])
        res = RankingPipeline(mini_project, analyzer=analyzer).run(_replace_task())
        assert res.feature_context.history_rates.get("__experience__") == 0.0
        exp_cand = next(c for c in res.ranked if c.type == "experience")
        assert exp_cand.factor_scores.get("history_success", 1.0) == 0.0

    def test_experience_advice_flows_into_assembled(self, mini_project: Path) -> None:
        """operation_error 失败史 → 经验节 advice (行号优先) + record_count。"""
        analyzer = FakeAnalyzer([
            _Rec(negative_signal=True, evidence=[_Ev("failure_reason: operation_error: x")]),
        ])
        res = RankingPipeline(mini_project, analyzer=analyzer).run(_replace_task())
        assert res.assembled.experience.record_count == 1
        assert any("line_range" in a or "行号" in a for a in res.assembled.experience.advice)

    def test_weights_override_recomputable(self, mini_project: Path) -> None:
        """权重覆盖 (部分键) → normalize 等比缩放; 评分仍可复算。"""
        res = RankingPipeline(mini_project, weights={"keyword_match": 0.8}).run(_replace_task())
        w = normalize_weights({"keyword_match": 0.8})
        assert abs(sum(w.values()) - 1.0) < 1e-9
        top = res.ranked[0]
        assert sum(top.factor_scores.values()) == pytest.approx(top.relevance_score, abs=1e-3)
        # keyword 权重缩放后 ≠ 默认权重下的贡献 (经验权重确实改变评分)
        default = RankingPipeline(mini_project).run(_replace_task())
        assert top.factor_scores.get("keyword_match", 0.0) != pytest.approx(
            default.ranked[0].factor_scores.get("keyword_match", 0.0), abs=1e-6
        )


# ================================================================ 6. context.ranking_assemble 新路径

class TestRankingAssemble:
    def test_ranking_assemble_new_path(self, mini_project: Path) -> None:
        """ContextAssembler.ranking_assemble → AssembledContext (6 节渲染, 旧 assemble 不动)。"""
        ctx = ContextAssembler(mini_project).ranking_assemble(_replace_task())
        assert ctx is not None
        assert 0.0 <= ctx.context_score <= 1.0
        prompt = ctx.render_prompt()
        assert "## Relevant source files" in prompt
        assert "## Task" in prompt
        # 旧路径仍可用 (并存不互斥)
        old = ContextAssembler(mini_project).assemble(_replace_task())
        assert old is not None and old.render_prompt()

    def test_ranking_assemble_fallback_old_path(
        self, mini_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """新路径异常 → 回退旧 assemble (执行链不破坏)。"""
        import exec.ranking as ranking_mod

        fallback_called: list[str] = []

        class _BrokenPipeline:
            def run(self, *a: Any, **kw: Any) -> Any:
                raise RuntimeError("pipeline broken")

        orig_assemble = ContextAssembler.assemble

        def _record_assemble(self: Any, task: Any) -> Any:
            fallback_called.append("assemble")
            return orig_assemble(self, task)

        monkeypatch.setattr(ranking_mod, "RankingPipeline", _BrokenPipeline)
        monkeypatch.setattr(ContextAssembler, "assemble", _record_assemble)
        ctx = ContextAssembler(mini_project).ranking_assemble(_replace_task())
        assert fallback_called == ["assemble"]
        assert ctx is not None and ctx.render_prompt()


# ================================================================ 7. agent_runtime 开关

class TestAgentRuntimeRankingSwitch:
    def _run(self, project_dir: Path, root: Path, ranking_enabled: bool) -> tuple[Any, Any, list[str]]:
        from exec.agent_runtime import AgentRuntime

        calls: list[str] = []
        orig_assemble = ContextAssembler.assemble
        orig_ranking = ContextAssembler.ranking_assemble

        def _assemble(self: Any, task: Any) -> Any:
            calls.append("assemble")
            return orig_assemble(self, task)

        def _ranking(self: Any, task: Any) -> Any:
            calls.append("ranking_assemble")
            return orig_ranking(self, task)

        (root / f"wr{len(calls)}").mkdir(exist_ok=True)
        provider = FakeProvider(content="<operations>[]</operations>")
        rt = AgentRuntime(
            provider, work_root=str(root / f"wr{len(calls)}"),
            ranking_enabled=ranking_enabled,
        )
        # 类属性 patch (execute 内 from .context import ContextAssembler 后按类查找方法)
        import exec.context as context_mod

        monkey = pytest.MonkeyPatch()
        monkey.setattr(context_mod.ContextAssembler, "assemble", _assemble)
        monkey.setattr(context_mod.ContextAssembler, "ranking_assemble", _ranking)
        try:
            req = make_request(project_dir=project_dir, objective="fix the run function bug")
            result = rt.execute(req)
        finally:
            monkey.undo()
        return result, provider, calls

    def test_default_disabled_uses_old_path(self, mini_project: Path, tmp_path: Path) -> None:
        """默认 False → assemble 旧路径 (ranking_assemble 零调用)。"""
        result, provider, calls = self._run(mini_project, tmp_path, ranking_enabled=False)
        assert result.status.value == "success"
        assert calls == ["assemble"]
        assert "## Task" in provider.calls[0].task_context

    def test_enabled_uses_new_path(self, mini_project: Path, tmp_path: Path) -> None:
        """ranking_enabled=True → ranking_assemble 新路径 (assemble 零调用)。"""
        result, provider, calls = self._run(mini_project, tmp_path, ranking_enabled=True)
        assert result.status.value == "success"
        assert calls == ["ranking_assemble"]
        assert "## Relevant source files" in provider.calls[0].task_context
        assert result.context_score is not None

    def test_enabled_failure_safe(self, mini_project: Path, tmp_path: Path) -> None:
        """新路径抛异常 → execute 外层兜底 → 旧链路继续 (context_score 诚实 None)。"""
        from exec.agent_runtime import AgentRuntime

        import exec.context as context_mod

        def _boom(self: Any, task: Any) -> Any:
            raise RuntimeError("ranking broken")

        provider = FakeProvider(content="<operations>[]</operations>")
        (tmp_path / "wrboom").mkdir(exist_ok=True)
        rt = AgentRuntime(
            provider, work_root=str(tmp_path / "wrboom"), ranking_enabled=True
        )
        monkey = pytest.MonkeyPatch()
        monkey.setattr(context_mod.ContextAssembler, "ranking_assemble", _boom)
        try:
            req = make_request(project_dir=mini_project, objective="fix the run function bug")
            result = rt.execute(req)
        finally:
            monkey.undo()
        assert result.status.value == "success"  # 上下文失败不破坏执行链
        assert result.context_score is None  # 组装失败 → 诚实 None (不臆造分数)


# ================================================================ 8. T4.2 Progressive 集成

class TestProgressivePipelineChain:
    """T4.2: RankingPipeline.run(progressive=True) 3 阶段渐进全链 (集成)。"""

    def test_progressive_true_three_stage_chain(self, mini_project: Path) -> None:
        """progressive=True → 3 阶段 (overview/symbol/detail) + 审计 Trace + 组装产物。"""
        res = RankingPipeline(mini_project).run(_replace_task(), progressive=True)
        prog = res.progressive
        assert prog is not None
        assert prog.stages == ["overview", "symbol", "detail"]
        # 每阶段一个审计条目 (含末阶段 stop)
        assert [e.stage for e in prog.trace.entries] == ["overview", "symbol", "detail"]
        assert prog.trace.entries[-1].decision == "stop"
        assert prog.total_chars > 0
        # 组装产物可直接渲染 (6 节语义)
        assert prog.assembled is not None
        prompt = prog.assembled.render_prompt()
        assert "## Task" in prompt
        assert "## Relevant source files" in prompt

    def test_progressive_result_audit_dict(self, mini_project: Path) -> None:
        """RankingPipelineResult.to_dict 含渐进 Trace (可审计); 阶段条目字段完整。"""
        res = RankingPipeline(mini_project).run(_replace_task(), progressive=True)
        d = res.to_dict()
        assert "progressive" in d
        pd = d["progressive"]
        assert pd["stages"] == ["overview", "symbol", "detail"]
        assert "trace" in pd and "entries" in pd["trace"]
        assert len(pd["trace"]["entries"]) == 3
        entry = pd["trace"]["entries"][0]
        for key in ("stage", "loaded_items", "reason", "token_cost",
                    "decision", "decision_reason", "final_usage"):
            assert key in entry
        assert pd["total_chars"] == res.progressive.total_chars  # to_dict 与对象一致

    def test_progressive_symbol_miss_signal_and_advice(self, miss_project: Path) -> None:
        """渐进路径同样处理 symbol miss: Trace 信号 + line_range 建议进经验节。"""
        res = RankingPipeline(miss_project).run(
            _Task("修复 my_widget 渲染异常", source_files=["widgets/my_widget.dart"]),
            progressive=True,
        )
        prog = res.progressive
        assert prog.trace.symbol_miss == ["my_widget"]
        assert "symbol_miss:my_widget" in prog.trace.to_experience_signals()
        advice = prog.assembled.experience.advice
        assert any("line_range" in a for a in advice)
        assert any("my_widget" in a for a in advice)

    def test_progressive_budget_overflow_marked(self, mini_project: Path) -> None:
        """渐进路径预算超限 → Trace context_overflow 诚实标记 (不静默) + 降级警示。"""
        long_req = "1. 修复; " * 200  # ~1200 chars — 超 overview 阶段预算 (hard_cap 500)
        res = RankingPipeline(mini_project, hard_cap=500).run(
            _Task("修复 run 函数", long_req, source_files=["app/main.py"]),
            progressive=True,
        )
        prog = res.progressive
        assert prog is not None
        assert prog.trace.context_overflow  # 锚点超预算 → 降级重试仍超 → 诚实标记
        assert any("超限降级" in w for w in prog.trace.warnings)
        assert "context_overflow" in prog.trace.to_experience_signals()


class TestProgressiveFallback:
    """T4.2: 渐进路径异常 → 回退一次性组装 (执行链不破坏)。"""

    def test_progressive_provider_error_falls_back(self, mini_project: Path) -> None:
        """CodeProgressiveProvider 装配抛错 → progressive=None + 一次性组装兜底。"""
        import exec.ranking as ranking_mod

        class _BrokenProvider:
            def __init__(self, *a: Any, **kw: Any) -> None:
                raise RuntimeError("provider broken")

        monkey = pytest.MonkeyPatch()
        monkey.setattr(ranking_mod, "CodeProgressiveProvider", _BrokenProvider)
        try:
            res = RankingPipeline(mini_project).run(_replace_task(), progressive=True)
        finally:
            monkey.undo()
        assert res.progressive is None  # 回退: 无渐进产物
        assert res.assembled is not None and res.assembled.render_prompt()
        # 回退后审计字段仍在 (一次性路径语义完整)
        assert res.budget is not None and res.ranked

    def test_progressive_loader_error_falls_back(self, mini_project: Path) -> None:
        """ProgressiveLoader.run 抛错 → 同样回退一次性组装 (progressive=None)。"""
        import exec.ranking as ranking_mod

        class _BrokenLoader:
            def __init__(self, *a: Any, **kw: Any) -> None:
                pass

            def run(self, *a: Any, **kw: Any) -> Any:
                raise RuntimeError("loader broken")

        monkey = pytest.MonkeyPatch()
        monkey.setattr(ranking_mod, "ProgressiveLoader", _BrokenLoader)
        try:
            res = RankingPipeline(mini_project).run(_replace_task(), progressive=True)
        finally:
            monkey.undo()
        assert res.progressive is None
        assert "## Task" in res.assembled.render_prompt()


class TestProgressiveStageSpecGeneric:
    """T4.2: StageSpec 声明式配置 — 引擎通用, 阶段表可替换。"""

    def test_code_progressive_stages_declarative(self) -> None:
        """CODE_PROGRESSIVE_STAGES = 3 个 StageSpec (overview 必载 1-2K / symbol 3-5K / detail 剩余)。"""
        assert [s.stage for s in CODE_PROGRESSIVE_STAGES] == ["overview", "symbol", "detail"]
        assert CODE_PROGRESSIVE_STAGES[0].required is True
        assert CODE_PROGRESSIVE_STAGES[0].max_chars > 0
        assert CODE_PROGRESSIVE_STAGES[1].max_chars > 0
        # detail 是末阶段: max_chars=0 → loader 给剩余预算
        assert CODE_PROGRESSIVE_STAGES[2].max_chars == 0

    def test_custom_stage_spec_drives_engine(self, mini_project: Path) -> None:
        """自定义 2 阶段 StageSpec 驱动同一引擎 (Agent 通用化 — Finance 语义照常)。"""
        res = RankingPipeline(mini_project).run(_replace_task())
        provider = CodeProgressiveProvider(
            mini_project,
            ri=RepositoryIntelligence(mini_project).analyze(),
            profile=res.profile, batch=res.batch, budget=res.budget,
            symbol_miss=res.symbol_miss,
        )
        custom = [
            StageSpec(stage="overview", label="Overview", max_chars=1500,
                      extractor="overview", required=True),
            StageSpec(stage="detail", label="Detail", max_chars=0,
                      extractor="detail", required=False),
        ]
        loader = ProgressiveLoader(
            stages=custom, extractor=provider.extract,
            finalizer=provider.finalize, hard_cap=30_000,
        )
        result = loader.run(task_type=res.profile.task_type)
        assert result.stages == ["overview", "detail"]  # 引擎按配置走, 不硬编码 3 阶段
        assert result.assembled is not None

    def test_unknown_stage_extract_safe(self, mini_project: Path) -> None:
        """未知 stage 提取 → 空结果 (candidates_found=False + missing_info — 引擎兜底)。"""
        res = RankingPipeline(mini_project).run(_replace_task())
        provider = CodeProgressiveProvider(
            mini_project,
            ri=RepositoryIntelligence(mini_project).analyze(),
            profile=res.profile, batch=res.batch, budget=res.budget,
            symbol_miss=res.symbol_miss,
        )
        load = provider.extract(StageSpec(stage="unknown", label="?", max_chars=100,
                                          extractor="?", required=False))
        assert load.items == []
        assert load.candidates_found is False
        assert load.missing_info is True


class TestProgressiveRankingAssemble:
    """T4.2: context.ranking_assemble progressive 参数 (默认 False 旧路径兼容)。"""

    def test_default_false_passes_false(self, mini_project: Path) -> None:
        """默认 (不传) → RankingPipeline.run(progressive=False) — 旧路径逐位兼容。"""
        import exec.ranking as ranking_mod

        seen: list[Any] = []

        class _RecordingPipeline:
            def __init__(self, *a: Any, **kw: Any) -> None:
                pass

            def run(self, task: Any, **kw: Any) -> Any:
                seen.append(kw.get("progressive"))
                return RankingPipeline(mini_project).run(task, progressive=False)

        monkey = pytest.MonkeyPatch()
        monkey.setattr(ranking_mod, "RankingPipeline", _RecordingPipeline)
        try:
            ctx = ContextAssembler(mini_project).ranking_assemble(_replace_task())
        finally:
            monkey.undo()
        assert seen == [False]
        assert ctx is not None and ctx.render_prompt()

    def test_true_passes_true(self, mini_project: Path) -> None:
        """progressive=True → run(progressive=True) — 渐进路径透传。"""
        import exec.ranking as ranking_mod

        seen: list[Any] = []

        class _RecordingPipeline:
            def __init__(self, *a: Any, **kw: Any) -> None:
                pass

            def run(self, task: Any, **kw: Any) -> Any:
                seen.append(kw.get("progressive"))
                return RankingPipeline(mini_project).run(task, progressive=True)

        monkey = pytest.MonkeyPatch()
        monkey.setattr(ranking_mod, "RankingPipeline", _RecordingPipeline)
        try:
            ctx = ContextAssembler(mini_project).ranking_assemble(_replace_task(), progressive=True)
        finally:
            monkey.undo()
        assert seen == [True]
        assert ctx is not None and ctx.render_prompt()

    def test_progressive_true_real_chain(self, mini_project: Path) -> None:
        """progressive=True 真实链 → AssembledContext 正常产出 (非 monkeypatch)。"""
        ctx = ContextAssembler(mini_project).ranking_assemble(_replace_task(), progressive=True)
        assert ctx is not None
        assert 0.0 <= ctx.context_score <= 1.0
        assert "## Task" in ctx.render_prompt()

    def test_progressive_true_pipeline_error_falls_back(self, mini_project: Path) -> None:
        """progressive=True 且新路径异常 → 回退旧 assemble (既有 fallback 语义保持)。"""
        import exec.ranking as ranking_mod

        fallback_called: list[str] = []

        class _BrokenPipeline:
            def run(self, *a: Any, **kw: Any) -> Any:
                raise RuntimeError("pipeline broken")

        orig_assemble = ContextAssembler.assemble

        def _record_assemble(self: Any, task: Any) -> Any:
            fallback_called.append("assemble")
            return orig_assemble(self, task)

        monkey = pytest.MonkeyPatch()
        monkey.setattr(ranking_mod, "RankingPipeline", _BrokenPipeline)
        monkey.setattr(ContextAssembler, "assemble", _record_assemble)
        try:
            ctx = ContextAssembler(mini_project).ranking_assemble(
                _replace_task(), progressive=True
            )
        finally:
            monkey.undo()
        assert fallback_called == ["assemble"]
        assert ctx is not None and ctx.render_prompt()


class TestProgressiveAgentRuntime:
    """T4.2: ranking_enabled 开关与渐进参数互不干扰 (集成)。"""

    def test_ranking_enabled_calls_assemble_without_progressive(self,
                                                                mini_project: Path,
                                                                tmp_path: Path) -> None:
        """ranking_enabled=True → ranking_assemble 收到默认 progressive=False (无参调用兼容)。"""
        from exec.agent_runtime import AgentRuntime

        import exec.context as context_mod

        seen: list[Any] = []
        orig_ranking = ContextAssembler.ranking_assemble

        def _ranking(self: Any, task: Any, **kw: Any) -> Any:
            seen.append(kw)  # 记录实际收到 kwargs
            return orig_ranking(self, task)

        provider = FakeProvider(content="<operations>[]</operations>")
        (tmp_path / "wrprog").mkdir(exist_ok=True)
        rt = AgentRuntime(
            provider, work_root=str(tmp_path / "wrprog"), ranking_enabled=True
        )
        monkey = pytest.MonkeyPatch()
        monkey.setattr(context_mod.ContextAssembler, "ranking_assemble", _ranking)
        try:
            req = make_request(project_dir=mini_project, objective="fix the run function bug")
            result = rt.execute(req)
        finally:
            monkey.undo()
        assert result.status.value == "success"
        assert seen == [{}]  # agent_runtime 不传 progressive → 参数缺省 (默认 False 生效)

    def test_ranking_disabled_still_old_path(self, mini_project: Path, tmp_path: Path) -> None:
        """ranking_enabled=False → assemble 旧路径 (ranking_assemble 零调用, 含渐进参数零影响)。"""
        from exec.agent_runtime import AgentRuntime

        import exec.context as context_mod

        calls: list[str] = []
        orig_assemble = ContextAssembler.assemble
        orig_ranking = ContextAssembler.ranking_assemble

        def _assemble(self: Any, task: Any) -> Any:
            calls.append("assemble")
            return orig_assemble(self, task)

        def _ranking(self: Any, task: Any, **kw: Any) -> Any:
            calls.append("ranking_assemble")
            return orig_ranking(self, task)

        provider = FakeProvider(content="<operations>[]</operations>")
        (tmp_path / "wrold").mkdir(exist_ok=True)
        rt = AgentRuntime(
            provider, work_root=str(tmp_path / "wrold"), ranking_enabled=False
        )
        monkey = pytest.MonkeyPatch()
        monkey.setattr(context_mod.ContextAssembler, "assemble", _assemble)
        monkey.setattr(context_mod.ContextAssembler, "ranking_assemble", _ranking)
        try:
            req = make_request(project_dir=mini_project, objective="fix the run function bug")
            result = rt.execute(req)
        finally:
            monkey.undo()
        assert result.status.value == "success"
        assert calls == ["assemble"]


class TestProgressiveRegression:
    """T4.2 Regression: 旧路径 (progressive 缺省 False) 逐位不变。"""

    def test_default_run_progressive_none(self, mini_project: Path) -> None:
        """缺省 run() → progressive=None + to_dict 无 progressive 键 (一次性组装语义)。"""
        res = RankingPipeline(mini_project).run(_replace_task())
        assert res.progressive is None
        assert "progressive" not in res.to_dict()
        assert res.assembled is not None and res.assembled.render_prompt()

    def test_old_path_identical_quality_semantics(self, mini_project: Path) -> None:
        """旧路径上下文质量分语义不变 (0-1 区间 + 可渲染)。"""
        res = RankingPipeline(mini_project).run(_replace_task())
        assert 0.0 <= res.assembled.context_score <= 1.0
        assert res.assembled.total_chars > 0
        assert "## Experience" in res.assembled.render_prompt()
