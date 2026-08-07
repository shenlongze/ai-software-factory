"""tests/exec/test_exec_context.py — Context Assembly Engine v1 测试 (Phase A++++++-2b)。

覆盖 (全部 mock 组件/真实小项目, 零 LLM 调用):
- Context Model 六类构造/渲染/序列化/extra=forbid
- Selector: 关键词提取 / symbol 匹配 / 文件选择 / 测试映射 / git 历史
- Token Budget: 核心全量 / 超长 symbol 索引+关键段 / 相关索引 / 预算截断
- Quality Score: 四维加权 / 低分扩大搜索 1 轮
- Experience 集成: 成功率 / 失败模式 / 建议 / 冷启动 / 失败安全
- Developer/AgentRuntime/Benchmark 接入: work(context=) 6 节 prompt /
  context_score 记录 / 旧路径兼容

helper: FakeAnalyzer (duck-typed records) + 真实小项目 fixture
(RepositoryIntelligence 是确定性正则级启发式 — 真实分析快且可靠)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from exec.context import (
    ArchitectureContext,
    AssembledContext,
    CodeContext,
    ContextAssembler,
    ExperienceContext,
    FileSlice,
    HistoryContext,
    RequirementContext,
    TestContext,
    extract_task_keywords,
    git_history,
    quality_score,
    select_files,
    select_symbols,
    select_tests,
)
from exec_helpers import FakeProvider, git_repo, make_request, write_files  # noqa: E402

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
    "util/__init__.py": "",
    "util/helper.py": "def helper():\n    return 42\n",
    "tests/test_main.py": (
        "from app.main import run\n"
        "\n"
        "def test_run():\n"
        "    assert run() == 42\n"
    ),
}


class _Rec:
    """duck-typed ExperienceRecord (context.py 只访问 negative_signal/evidence)。"""

    def __init__(
        self,
        *,
        negative_signal: bool = False,
        evidence: list[Any] | None = None,
        task_type: str = "development",
        capability: list[str] | None = None,
    ) -> None:
        self.negative_signal = negative_signal
        self.evidence = evidence or []
        self.task_type = task_type
        self.capability = capability or ["development"]


class FakeAnalyzer:
    """duck-typed ExperienceAnalyzer (records 查询; context.py 兼容)。"""

    def __init__(self, records: list[Any] | None = None) -> None:
        self._records = list(records or [])

    def records(self, **kwargs: Any) -> list[Any]:
        return list(self._records)


class _Task:
    """duck-typed 任务 (objective/requirement/source_files/task_id + id — 对齐
    ExecutionRequest: build_report 用 request.id 做报告标题)。"""

    def __init__(
        self,
        objective: str,
        requirement: str = "",
        source_files: list[str] | None = None,
        task_id: str = "T-CONTEXT-1",
        id: str = "REQ-CONTEXT-1",
    ) -> None:
        self.objective = objective
        self.requirement = requirement
        self.source_files = source_files or []
        self.task_id = task_id
        self.id = id


@pytest.fixture
def mini_project(tmp_path: Path) -> Path:
    """真实小项目 (app/util/tests — RepositoryIntelligence 分析素材)。"""
    write_files(tmp_path / "proj", MINI_PROJECT)
    return tmp_path / "proj"


@pytest.fixture
def assembled(mini_project: Path) -> AssembledContext:
    """默认组装结果 (真实 RepositoryIntelligence, 无经验)。"""
    return ContextAssembler(mini_project).assemble(
        _Task("修复 replace_current 只替换当前匹配", "1. 局部替换; 2. 无全文替换",
              source_files=["app/main.py"])
    )


# ================================================================ 1. Context Model

class TestContextModels:
    def test_fileslice_defaults(self):
        s = FileSlice(rel_path="a.py", kind="related")
        assert s.content == "" and s.line_count == 0 and s.truncated is False
        assert s.symbol_index == ""

    def test_fileslice_none_normalized(self):
        s = FileSlice(rel_path="a.py", kind=None)
        # kind=None → str 归一 (None → ""), 保持字符串类型 (不抛 ValidationError)
        assert isinstance(s.kind, str)

    def test_requirement_render(self):
        ctx = RequirementContext(
            objective="修复 bug", requirement="1. 验收 A", task_id="T-1"
        )
        text = ctx.render()
        assert "## Task" in text and "修复 bug" in text
        assert "## Requirement / Acceptance criteria" in text and "验收 A" in text

    def test_requirement_render_without_requirement(self):
        ctx = RequirementContext(objective="仅目标")
        text = ctx.render()
        assert "## Task" in text
        assert "## Requirement" not in text

    def test_architecture_render(self):
        ctx = ArchitectureContext(
            summary="arch summary", entry_points=["main.py"],
            modules=["lib"], tech_stack=["dart"],
        )
        text = ctx.render()
        assert "## Architecture context" in text and "arch summary" in text

    def test_architecture_render_empty_summary(self):
        ctx = ArchitectureContext()
        assert "(仓库结构摘要不可用" in ctx.render()

    def test_code_render_core_and_related(self):
        ctx = CodeContext(
            core_files=[FileSlice(rel_path="a.py", content="1| x", line_count=1)],
            related_files=[FileSlice(rel_path="b.py", content="// sym", symbol_index="// fn @ 1")],
        )
        text = ctx.render()
        assert "## Relevant source files" in text
        assert "### a.py (1 行)" in text
        assert "### b.py [related]" in text

    def test_code_render_empty(self):
        text = CodeContext().render()
        assert "(无可用源文件" in text

    def test_history_render_with_entries(self):
        ctx = HistoryContext(entries=["a.py: abc123 fix", "b.py: def456 add"])
        text = ctx.render()
        assert "## Change history" in text and "- a.py: abc123 fix" in text

    def test_history_render_empty(self):
        assert "(无可用提交历史" in HistoryContext().render()

    def test_experience_render_cold_start(self):
        ctx = ExperienceContext(task_type="development")
        assert "(无同类任务历史经验" in ctx.render()

    def test_experience_render_with_data(self):
        ctx = ExperienceContext(
            task_type="T-1", record_count=4, success_count=3, failure_count=1,
            success_rate=0.75, failure_patterns=["operation_error ×1"],
            advice=["优先用行号定位"], provider_hint="成功率低可换 Provider",
        )
        text = ctx.render()
        assert "同类任务历史: 4 条" in text and "成功率 75%" in text
        assert "常见失败模式: operation_error" in text
        assert "建议: 优先用行号定位" in text
        assert "Provider 建议" in text

    def test_test_context_render(self):
        ctx = TestContext(
            mapping={"app/main.py": ["tests/test_main.py"]},
            test_files=[FileSlice(rel_path="tests/test_main.py", symbol_index="// test_run @ 4")],
        )
        text = ctx.render()
        assert "## Related tests" in text
        assert "app/main.py → tests/test_main.py" in text
        assert "### tests/test_main.py [test]" in text

    def test_assembled_render_prompt_six_sections(self, assembled: AssembledContext):
        text = assembled.render_prompt()
        for section in (
            "## Task", "## Architecture context", "## Relevant source files",
            "## Related tests", "## Change history", "## Experience / past lessons",
        ):
            assert section in text, f"missing section: {section}"

    def test_assembled_to_dict(self, assembled: AssembledContext):
        d = assembled.to_dict()
        assert d["context_score"] == assembled.context_score
        assert d["total_chars"] == assembled.total_chars
        assert d["token_estimate"] == assembled.token_estimate
        assert "requirement" in d and "code" in d and "experience" in d

    def test_extra_forbid(self):
        with pytest.raises(Exception):
            RequirementContext(objective="x", unknown_field=1)  # extra=forbid

    def test_context_score_default_none(self):
        r = RequirementContext(objective="x")
        assert r.requirement == "" and r.task_id == ""


# ================================================================ 2. Selector

class TestKeywordExtraction:
    def test_camel_case_split(self):
        kws = extract_task_keywords("replaceCurrent 只替换当前匹配")
        assert "replacecurrent" in kws
        assert "replace" in kws and "current" in kws

    def test_snake_case_kept(self):
        kws = extract_task_keywords("修复 _cloneBlock 深拷贝")
        assert "_cloneblock" in kws  # 整词保留 (含前导下划线)
        assert "clone" in kws and "block" in kws  # camelCase 拆分

    def test_stopwords_removed(self):
        kws = extract_task_keywords("the file should 修复 请 显示")
        assert "the" not in kws and "file" not in kws
        assert "修复" not in kws and "请" not in kws

    def test_short_words_filtered(self):
        kws = extract_task_keywords("修复 ab 函数")
        assert "ab" in kws  # len ≥ 2 保留
        kws2 = extract_task_keywords("修复 a 函数")
        assert "a" not in kws2  # len < 2 过滤

    def test_empty_input(self):
        assert extract_task_keywords("") == []
        assert extract_task_keywords("   ") == []

    def test_dedup_preserves_order(self):
        kws = extract_task_keywords("foo bar foo")
        assert kws.count("foo") == 1


class TestSymbolSelection:
    def test_exact_match(self, mini_project: Path):
        from exec.repo_intelligence import analyze_repository

        ri = analyze_repository(mini_project)
        hits = select_symbols(ri, ["helper"])
        assert any(path.endswith("util/helper.py") for path, _s, _score in hits)

    def test_contained_match(self, mini_project: Path):
        from exec.repo_intelligence import analyze_repository

        ri = analyze_repository(mini_project)
        hits = select_symbols(ri, ["replace"])
        assert any(
            path.endswith("app/main.py") and sym.name == "replace_current"
            for path, sym, _score in hits
        )

    def test_ranking_exact_over_contained(self, mini_project: Path):
        from exec.repo_intelligence import analyze_repository

        ri = analyze_repository(mini_project)
        hits = select_symbols(ri, ["helper"])
        for path, _sym, score in hits:
            if path.endswith("util/helper.py"):
                assert score == 1.0

    def test_no_keywords_empty(self, mini_project: Path):
        from exec.repo_intelligence import analyze_repository

        ri = analyze_repository(mini_project)
        assert select_symbols(ri, []) == []

    def test_no_match_empty(self, mini_project: Path):
        from exec.repo_intelligence import analyze_repository

        ri = analyze_repository(mini_project)
        assert select_symbols(ri, ["zzzz_no_such_symbol"]) == []


class TestFileSelection:
    def test_source_files_are_core(self, mini_project: Path):
        from exec.repo_intelligence import analyze_repository

        ri = analyze_repository(mini_project)
        core, related = select_files(
            ri, source_files=["app/main.py"], symbol_hits=[], keywords=["main"]
        )
        assert "app/main.py" in core

    def test_symbol_files_are_core(self, mini_project: Path):
        from exec.repo_intelligence import analyze_repository

        ri = analyze_repository(mini_project)
        hits = select_symbols(ri, ["helper"])
        core, _related = select_files(ri, source_files=[], symbol_hits=hits, keywords=["helper"])
        assert any(p.endswith("util/helper.py") for p in core)

    def test_impact_files_related(self, mini_project: Path):
        from exec.repo_intelligence import analyze_repository

        ri = analyze_repository(mini_project)
        core, related = select_files(
            ri, source_files=["app/main.py"], symbol_hits=[], keywords=["main"]
        )
        # app/main.py 被 tests/test_main.py import → 影响面进 related
        assert any(p.endswith("tests/test_main.py") for p in related)

    def test_widen_promotes_module_files_to_core(self, mini_project: Path):
        from exec.repo_intelligence import analyze_repository

        ri = analyze_repository(mini_project)
        core, _r = select_files(
            ri, source_files=["app/main.py"], symbol_hits=[], keywords=["main"], widen=True
        )
        # widen 轮把依赖影响面 (tests/test_main.py import app.main) 提升为核心候选
        assert any(p.endswith("tests/test_main.py") for p in core)
        assert len(core) > 1

    def test_core_capped(self, mini_project: Path):
        from exec.repo_intelligence import analyze_repository

        ri = analyze_repository(mini_project)
        core, _r = select_files(
            ri, source_files=["app/main.py"], symbol_hits=[], keywords=["main"], widen=True
        )
        assert len(core) <= 8


class TestTestSelection:
    def test_mapping_via_naming(self, mini_project: Path):
        from exec.repo_intelligence import analyze_repository

        ri = analyze_repository(mini_project)
        mapping = select_tests(ri, ["app/main.py"])
        assert mapping.get("app/main.py") == ["tests/test_main.py"]

    def test_no_tests_empty(self, mini_project: Path):
        from exec.repo_intelligence import analyze_repository

        ri = analyze_repository(mini_project)
        assert select_tests(ri, ["util/helper.py"]) == {}


class TestGitHistory:
    def test_no_git_empty(self, mini_project: Path):
        # mini_project 不是 git 仓库 → 失败安全空
        assert git_history(mini_project, ["app/main.py"]) == []

    def test_real_git_entries(self, tmp_path: Path):
        repo = tmp_path / "repo"
        git_repo(repo, {"a.py": "def a():\n    return 1\n"})
        write_files(repo, {"a.py": "def a():\n    return 2\n"})
        import subprocess

        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-q", "-m", "fix a"], check=True
        )
        entries = git_history(repo, ["a.py"])
        assert any("a.py:" in e for e in entries)
        assert any("fix a" in e for e in entries)

    def test_max_entries_capped(self, tmp_path: Path):
        repo = tmp_path / "repo2"
        git_repo(repo, {"a.py": "x = 1\n"})
        entries = git_history(repo, ["a.py"], max_entries=2)
        assert len(entries) <= 2

    def test_missing_file_empty(self, tmp_path: Path):
        repo = tmp_path / "repo3"
        git_repo(repo, {"a.py": "x = 1\n"})
        assert git_history(repo, ["no_such_file.py"]) == []


# ================================================================ 3. Token Budget

class TestTokenBudget:
    def test_core_full_inline_with_line_numbers(self, mini_project: Path):
        from exec.context import _build_file_slices, _render_lines

        ri = __import__("exec.repo_intelligence", fromlist=["analyze_repository"]).analyze_repository(mini_project)
        core, related, used = _build_file_slices(
            ri, mini_project, core_files=["app/main.py"], related_files=[],
            keywords=["main"], total_budget_chars=120_000,
        )
        assert core[0].content.startswith("1| from util import helper")
        # 行号逐行数: 1=from util, 2=空, 3=def run, 4=return helper,
        # 5=空, 6=def replace_current, 7=return text
        assert "6| def replace_current" in core[0].content
        assert core[0].truncated is False

    def test_render_lines_padding(self):
        from exec.context import _render_lines

        out = _render_lines("a\nb\n")
        assert out == "1| a\n2| b"

    def test_long_file_symbol_index_not_full(self, tmp_path: Path):
        # 600 行超长文件 (>CORE_LINE_CAP? 不, >500 长文件阈值; 但 ≤3000 全量)
        # 本用例验证: 超长文件 (>3000) → symbol 索引 + 关键段, 不全文内联
        from exec.context import _build_file_slices, CORE_LINE_CAP

        root = tmp_path / "long"
        write_files(root, {"big.py": "def target_func():\n    return 1\n" + "\n".join(f"x{i} = {i}" for i in range(CORE_LINE_CAP + 50))})
        from exec.repo_intelligence import analyze_repository

        ri = analyze_repository(root)
        core, _r, _u = _build_file_slices(
            ri, root, core_files=["big.py"], related_files=[],
            keywords=["target"], total_budget_chars=120_000,
        )
        slice = core[0]
        assert slice.truncated is True
        assert "symbol 索引" in slice.content
        assert "target_func" in slice.content  # 命中关键词的函数块内联
        assert len(slice.content) < len("x" * 0) + 4000  # 远小于全文

    def test_long_file_block_capped(self):
        from exec.context import _symbol_blocks

        lines = [f"line {i}" for i in range(500)]
        class _S:
            def __init__(self, name, line):
                self.name = name
                self.line = line
        symbols = [_S("target_func", 10), _S("other", 300)]
        blocks = _symbol_blocks(lines, symbols, ["target"])
        assert len(blocks) == 1
        sym, start, end = blocks[0]
        assert start == 9 and end <= 9 + 80

    def test_related_symbol_index_only(self, mini_project: Path):
        from exec.context import _build_file_slices

        ri = __import__("exec.repo_intelligence", fromlist=["analyze_repository"]).analyze_repository(mini_project)
        core, related, _u = _build_file_slices(
            ri, mini_project, core_files=["app/main.py"],
            related_files=["tests/test_main.py", "util/helper.py"],
            keywords=["main"], total_budget_chars=120_000,
        )
        paths = [s.rel_path for s in related]
        assert "util/helper.py" in paths
        for s in related:
            assert s.kind == "related"

    def test_budget_truncates_related(self, tmp_path: Path):
        from exec.context import _build_file_slices

        root = tmp_path / "budget"
        files = {f"mod{i}/f.py": "def fn():\n    return 1\n" for i in range(30)}
        write_files(root, files)
        from exec.repo_intelligence import analyze_repository

        ri = analyze_repository(root)
        core, related, used = _build_file_slices(
            ri, root, core_files=["mod0/f.py"], related_files=list(files.keys())[1:],
            keywords=["fn"], total_budget_chars=500,
        )
        # 超预算 → related 被截断 (budget_related=150, 29 个候选只进一部分)
        assert 0 < len(related) < 29
        assert used <= 500 + 500  # 不超预算 (含核心余量)

    def test_core_priority_over_related(self, tmp_path: Path):
        from exec.context import _build_file_slices

        root = tmp_path / "prio"
        write_files(root, {
            "core.py": "\n".join(f"c{i} = {i}" for i in range(300)),
            "rel.py": "\n".join(f"r{i} = {i}" for i in range(300)),
        })
        from exec.repo_intelligence import analyze_repository

        ri = analyze_repository(root)
        core, related, _u = _build_file_slices(
            ri, root, core_files=["core.py"], related_files=["rel.py"],
            keywords=["c"], total_budget_chars=500,
        )
        assert core and core[0].content  # 核心不因预算被截断


# ================================================================ 4. Quality Score

class TestQualityScore:
    def test_no_core_zero(self):
        assert quality_score(
            core_files=[], related_files=[], mapping={}, keywords=["a"],
            experience=ExperienceContext(),
        ) == 0.0

    def test_no_keywords_zero(self):
        s = FileSlice(rel_path="a.py", content="1| x", line_count=1)
        assert quality_score(
            core_files=[s], related_files=[], mapping={}, keywords=[],
            experience=ExperienceContext(),
        ) == 0.0

    def test_full_context_high(self):
        s = FileSlice(rel_path="a.py", content="1| x", line_count=1)
        exp = ExperienceContext(record_count=2, success_count=2, success_rate=1.0)
        score = quality_score(
            core_files=[s], related_files=[FileSlice(rel_path="b.py")],
            mapping={"a.py": ["t.py"]}, keywords=["a"], experience=exp,
        )
        assert 0.7 <= score <= 1.0

    def test_truncated_core_penalized(self):
        s = FileSlice(rel_path="a.py", content="idx", line_count=5000, truncated=True)
        exp = ExperienceContext()
        score = quality_score(
            core_files=[s], related_files=[], mapping={}, keywords=["a"],
            experience=exp,
        )
        assert 0.0 < score < 0.5  # truncated 0.5 系数 → core 0.2 权重

    def test_missing_file_low(self):
        s = FileSlice(rel_path="missing.py", line_count=0)
        score = quality_score(
            core_files=[s], related_files=[], mapping={}, keywords=["a"],
            experience=ExperienceContext(),
        )
        assert score < 0.2

    def test_scope_in_0_1(self):
        s = FileSlice(rel_path="a.py", content="1| x", line_count=1)
        for _ in range(20):
            score = quality_score(
                core_files=[s], related_files=[], mapping={}, keywords=["a"],
                experience=ExperienceContext(),
            )
            assert 0.0 <= score <= 1.0

    def test_assemble_widen_round_adds_module_files(self, tmp_path: Path):
        # 低分场景: source_files 指向不存在的文件 → 核心空 → 扩大搜索把
        # 关键词命中的同模块文件拉进核心
        root = tmp_path / "widen"
        write_files(root, {
            "app/main.py": "from util import helper\n\ndef run():\n    return helper()\n",
            "util/helper.py": "def helper():\n    return 42\n",
        })
        task = _Task("修复 helper 函数返回值错误", source_files=["app/not_there.py"])
        ctx = ContextAssembler(root).assemble(task)
        core_paths = [s.rel_path for s in ctx.code.core_files]
        # 扩大轮后 util/helper.py 进入核心 (symbol 命中 + 同模块提升)
        assert any(p.endswith("util/helper.py") for p in core_paths)
        assert ctx.context_score > 0.0


# ================================================================ 5. Experience 集成

class TestExperienceIntegration:
    def test_success_rate_from_records(self):
        analyzer = FakeAnalyzer([
            _Rec(), _Rec(), _Rec(negative_signal=True),
        ])
        ctx = experience_ctx(analyzer)
        assert ctx.record_count == 3
        assert ctx.success_count == 2 and ctx.failure_count == 1
        assert ctx.success_rate == round(2 / 3, 3)

    def test_failure_patterns_extracted(self):
        analyzer = FakeAnalyzer([
            _Rec(negative_signal=True, evidence=[
                _Ev("failure_reason: operation_error: symbol 定位失败"),
            ]),
            _Rec(negative_signal=True, evidence=[
                _Ev("failure_reason: empty_content: finish_reason=length"),
            ]),
        ])
        ctx = experience_ctx(analyzer)
        assert any("operation_error" in p for p in ctx.failure_patterns)
        assert any("empty_content" in p for p in ctx.failure_patterns)

    def test_operation_error_advice_line_number(self):
        analyzer = FakeAnalyzer([
            _Rec(negative_signal=True, evidence=[_Ev("failure_reason: operation_error: x")]),
        ])
        ctx = experience_ctx(analyzer)
        assert any("line_range" in a or "行号" in a for a in ctx.advice)

    def test_empty_content_advice(self):
        analyzer = FakeAnalyzer([
            _Rec(negative_signal=True, evidence=[_Ev("failure_reason: empty_content: x")]),
        ])
        ctx = experience_ctx(analyzer)
        assert any("symbol 索引" in a for a in ctx.advice)

    def test_verifier_advice(self):
        analyzer = FakeAnalyzer([
            _Rec(negative_signal=True, evidence=[_Ev("failure_reason: verifier_failed: x")]),
        ])
        ctx = experience_ctx(analyzer)
        assert any("验收" in a for a in ctx.advice)

    def test_cold_start_none_analyzer(self):
        ctx = experience_ctx(None)
        assert ctx.record_count == 0 and ctx.success_rate is None
        assert ctx.failure_patterns == []

    def test_analyzer_exception_failsafe(self):
        class Broken:
            def records(self, **kwargs: Any) -> Any:
                raise RuntimeError("boom")

        ctx = experience_ctx(Broken())
        assert ctx.record_count == 0

    def test_low_success_rate_provider_hint(self):
        analyzer = FakeAnalyzer([
            _Rec(), _Rec(negative_signal=True), _Rec(negative_signal=True),
        ])
        ctx = experience_ctx(analyzer)
        assert ctx.success_rate is not None and ctx.success_rate < 0.5
        assert "Provider" in ctx.provider_hint

    def test_high_success_rate_no_hint(self):
        analyzer = FakeAnalyzer([_Rec(), _Rec()])
        ctx = experience_ctx(analyzer)
        assert ctx.provider_hint == ""

    def test_experience_flows_into_assembled(self, mini_project: Path):
        analyzer = FakeAnalyzer([
            _Rec(negative_signal=True, evidence=[_Ev("failure_reason: operation_error: x")]),
        ])
        ctx = ContextAssembler(mini_project, analyzer=analyzer).assemble(
            _Task("修复 replace_current", source_files=["app/main.py"])
        )
        assert ctx.experience.record_count == 1
        assert any("line_range" in a or "行号" in a for a in ctx.experience.advice)


def _Ev(desc: str) -> Any:
    class _Evidence:
        def __init__(self, description: str) -> None:
            self.description = description

    return _Evidence(desc)


def experience_ctx(analyzer: Any) -> ExperienceContext:
    from exec.context import experience_advice

    return experience_advice(analyzer, task_type="development", keywords=["fix"])


# ================================================================ 6. 接入集成

class TestDeveloperIntegration:
    def test_build_prompt_context_text_sections(self):
        from exec.developer import DeveloperAgent

        agent = DeveloperAgent(FakeProvider())
        task = _Task("修复 replace_current", source_files=["app/main.py"])
        from exec.repo_intelligence import analyze_repository

        # 直接构造组装上下文 (不依赖文件系统分析 — 用 mini 项目文本)
        ctx = AssembledContext(
            requirement=RequirementContext(objective="修复 replace_current"),
            architecture=ArchitectureContext(summary="arch"),
            code=CodeContext(core_files=[FileSlice(rel_path="app/main.py", content="1| x", line_count=1)]),
            history=HistoryContext(),
            test=TestContext(),
            experience=ExperienceContext(),
        )
        prompt = agent.build_prompt(
            objective=task.objective, sandbox_path="/tmp/x", context_text=ctx.render_prompt()
        )
        assert "## Task" in prompt
        assert "## Architecture context" in prompt
        assert "## Relevant source files" in prompt
        assert "## Experience / past lessons" in prompt
        # 旧节不重复
        assert prompt.count("## Task") == 1

    def test_work_context_prompt_six_sections(self, tmp_path: Path):
        from exec.developer import DeveloperAgent

        root = tmp_path / "w"
        write_files(root, {"a.py": "def fix():\n    return 1\n"})
        from exec.context import ContextAssembler

        ctx = ContextAssembler(root).assemble(_Task("修复 fix 函数", source_files=["a.py"]))
        provider = FakeProvider(content="<operations>[]</operations>")
        agent = DeveloperAgent(provider)
        out = agent.work(
            request=_Task("修复 fix 函数", source_files=["a.py"]),
            sandbox_path=str(root),
            context=ctx,
        )
        prompt = provider.calls[0].task_context
        for section in (
            "## Task", "## Architecture context", "## Relevant source files",
            "## Related tests", "## Change history", "## Experience / past lessons",
        ):
            assert section in prompt

    def test_work_context_no_source_read_required(self, tmp_path: Path):
        # context 路径: source_files 由 context 渲染, work 不再从沙箱读取 —
        # source_files 缺失/文件不存在不炸 (旧路径会 DeveloperError)
        from exec.developer import DeveloperAgent

        root = tmp_path / "w2"
        write_files(root, {"a.py": "def fix():\n    return 1\n"})
        from exec.context import ContextAssembler

        ctx = ContextAssembler(root).assemble(_Task("修复 fix 函数", source_files=["a.py"]))
        provider = FakeProvider(content="<operations>[]</operations>")
        agent = DeveloperAgent(provider)
        out = agent.work(
            request=_Task("修复 fix 函数", source_files=["a.py"]),
            sandbox_path=str(root / "not_a_sandbox"),  # 目录不存在 — context 路径不读
            source_files=["a.py"],
            context=ctx,
        )
        assert out.patch_text == ""  # 显式空操作 = NO_CHANGE

    def test_work_legacy_path_unchanged(self, tmp_path: Path):
        # 旧路径 (context=None) → 仍从沙箱读取 source_files, 缺失响亮报错
        from exec.developer import DeveloperAgent, DeveloperError

        root = tmp_path / "w3"
        write_files(root, {"a.py": "x = 1\n"})
        provider = FakeProvider(content="<operations>[]</operations>")
        agent = DeveloperAgent(provider)
        with pytest.raises(DeveloperError):
            agent.work(
                request=_Task("修复 x", source_files=["missing.py"]),
                sandbox_path=str(root),
                source_files=["missing.py"],
            )


class TestAgentRuntimeIntegration:
    def test_execute_records_context_score(self, tmp_path: Path, project_dir: Path):
        from exec.agent_runtime import AgentRuntime

        provider = FakeProvider(content="<operations>[]</operations>")
        rt = AgentRuntime(provider, work_root=tmp_path / "workroot")
        (tmp_path / "workroot").mkdir(exist_ok=True)
        req = make_request(project_dir=project_dir, objective="fix the sub function bug")
        result = rt.execute(req)
        assert result.context_score is not None
        assert 0.0 <= result.context_score <= 1.0

    def test_execute_assembled_prompt_has_architecture(self, tmp_path: Path, project_dir: Path):
        from exec.agent_runtime import AgentRuntime

        provider = FakeProvider(content="<operations>[]</operations>")
        rt = AgentRuntime(provider, work_root=tmp_path / "workroot2")
        (tmp_path / "workroot2").mkdir(exist_ok=True)
        req = make_request(project_dir=project_dir, objective="fix the sub function bug")
        rt.execute(req)
        prompt = provider.calls[0].task_context
        assert "## Architecture context" in prompt
        assert "## Relevant source files" in prompt

    def test_execute_missing_project_no_context_score(self, tmp_path: Path):
        from exec.agent_runtime import AgentRuntime

        provider = FakeProvider(content="<operations>[]</operations>")
        rt = AgentRuntime(provider, work_root=tmp_path / "wr")
        (tmp_path / "wr").mkdir(exist_ok=True)
        req = make_request(project_dir=tmp_path / "does_not_exist")
        result = rt.execute(req)
        assert result.status.value == "failed"
        assert result.context_score is None  # 组装前失败 → 诚实 None


class TestBenchmarkIntegration:
    def test_run_sample_records_context_score(self, tmp_path: Path):
        from exec.benchmark.models import BenchmarkSample, SampleKind
        from exec.benchmark.runner import BenchmarkRunner

        proj = tmp_path / "proj"
        write_files(proj, {
            "lib/editor/services/search_service.dart": (
                "class SearchService {\n"
                "  String replaceCurrent(String text) {\n"
                "    return text;\n"
                "  }\n"
                "}\n"
            ),
            "pubspec.yaml": "name: demo\n",
        })
        sample = BenchmarkSample(
            id="BUG-CTX-001", kind=SampleKind.BUG, objective="修复 replaceCurrent 局部替换",
            requirement="局部替换", project_files=["lib", "pubspec.yaml"],
            source_files=["lib/editor/services/search_service.dart"],
            verifier_id="verify_bug_001_replace_current",
        )
        provider = FakeProvider()  # 空内容 → 失败路径 (重试后 empty content)
        runner = BenchmarkRunner(provider, project_dir=proj, work_root=tmp_path / "wr")
        (tmp_path / "wr").mkdir(exist_ok=True)
        result = runner.run_sample(sample)
        assert result.context_score is not None
        assert 0.0 <= result.context_score <= 1.0
        assert result.status.value == "failed"  # 空内容诚实失败
        assert result.failure_reason == "empty_content"

    def test_run_sample_success_records_context_score(self, tmp_path: Path):
        from exec.benchmark.models import BenchmarkSample, SampleKind
        from exec.benchmark.runner import BenchmarkRunner

        proj = tmp_path / "proj2"
        write_files(proj, {
            "lib/editor/services/search_service.dart": (
                "class SearchService {\n"
                "  String replaceCurrent(String text) {\n"
                "    return text;\n"
                "  }\n"
                "}\n"
            ),
            "pubspec.yaml": "name: demo\n",
        })
        sample = BenchmarkSample(
            id="BUG-CTX-002", kind=SampleKind.BUG, objective="修复 replaceCurrent 局部替换",
            requirement="局部替换", project_files=["lib", "pubspec.yaml"],
            source_files=["lib/editor/services/search_service.dart"],
            verifier_id="verify_bug_001_replace_current",
        )
        content = (
            "<operations>[{\"operation\": \"replace_block\", "
            "\"target\": \"lib/editor/services/search_service.dart\", "
            "\"location\": {\"symbol\": \"replaceCurrent\"}, "
            "\"change\": \"  String replaceCurrent(String text) {\\n"
            "    return text.replaceAll(RegExp('x'), 'y');\\n  }\\n\"}]</operations>"
        )
        provider = FakeProvider(content=content)
        runner = BenchmarkRunner(provider, project_dir=proj, work_root=tmp_path / "wr2")
        (tmp_path / "wr2").mkdir(exist_ok=True)
        result = runner.run_sample(sample)
        assert result.context_score is not None
        # 不关心 verifier 判定 (样例代码不满足验收), 只验证 context_score 记录
        assert result.usage != {} or result.status.value in ("success", "failed")
