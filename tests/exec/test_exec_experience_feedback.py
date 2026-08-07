"""tests/exec/test_exec_experience_feedback.py — Context Experience 集成测试 (Sprint 4 T4.4)。

覆盖 (真实小项目 + mock Provider, 零 LLM 零网络; ≥15 集成用例):
- Execution→Experience: AgentRuntime 全链成功/失败自动提取落库 (extractor 装配)
- Experience→Ranking: 持久化 symbol_miss 失败史 → experience_match 提权 (与启发式区分)
- Experience→Progressive: ≥2 条成功记录阶段序共识 → 渐进加载阶段重排
- Experience→Budget: 成功记录实际用量 → 预算推荐 clamp ±20%
- backward compat: 无经验库/空库 → 旧语义逐位不变 (零回归)

helper 复用 tests/exec/exec_helpers.py (唯一名共享模块)。
basename 唯一: test_exec_experience_feedback.py (test_exec_* 前缀)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from exec.agent_runtime import AgentRuntime
from exec.context import ContextAssembler
from exec.experience_ctx import (
    FAILURE_OPERATION,
    FAILURE_SYMBOL_MISS,
    ContextExperienceRecord,
    ContextExperienceStore,
    ExperienceExtractor,
)
from exec.progressive import ProgressiveLoader, StageSpec
from exec.ranking import RankingPipeline
from exec_helpers import FakeProvider, make_request, write_files  # noqa: E402

# ================================================================ fixtures / 数据

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
    "util/__init__.py": "",
    "util/helper.py": "def helper():\n    return 42\n",
    "tests/test_main.py": (
        "from app.main import run\n"
        "\n"
        "def test_run():\n"
        "    assert run() == 42\n"
    ),
}

#: 持久化提权场景: 仓库有 renderer.dart (basename 不含任务符号 my_widget —
#: 启发式不命中, 只靠经验库 symbol_miss 失败史提权)
MISS_PROJECT: dict[str, str] = dict(MINI_PROJECT)
MISS_PROJECT["widgets/renderer.dart"] = (
    "class Renderer {\n"
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
        task_id: str = "T-FB-1",
        id: str = "REQ-FB-1",
    ) -> None:
        self.objective = objective
        self.requirement = requirement
        self.source_files = source_files or []
        self.task_id = task_id
        self.id = id


def _replace_task() -> _Task:
    return _Task(
        "修复 replace_current 局部替换",
        "1. 局部替换; 2. 无全文替换",
        source_files=["app/main.py"],
    )


def _miss_task() -> _Task:
    return _Task(
        "修复 my_widget 渲染异常",
        "renderer 渲染错误",
        source_files=["widgets/renderer.dart"],
    )


def make_record(
    *,
    record_id: str,
    task_type: str = "bug_fix",
    failure_type: str = "",
    status: str = "success",
    source: str = "app/main.py",
    stages: list[str] | None = None,
    actual_usage: int = 0,
) -> ContextExperienceRecord:
    """经验记录工厂 (唯一缺省 id — 防 save 互相覆盖)。"""
    return ContextExperienceRecord(
        id=record_id,
        task_type=task_type,
        task_summary="fix replace_current in app/main.py",
        context_used={
            "candidates": [
                {"id": f"code:{source}", "type": "code", "source": source,
                 "level": "full"},
            ],
            "content_refs": [source],
        },
        ranking_trace={"total_candidates": 5, "ranked_ids": [f"code:{source}"],
                       "scores": {}},
        progressive_trace={"stages": stages or ["overview", "symbol", "detail"]},
        budget_trace={"actual_usage": actual_usage},
        execution_result={"status": status, "error": "", "duration": 1.0,
                          "usage": {}, "employee_id": "E-1", "request_id": "EXR-1"},
        validation_result={"passed": True, "attempts": 1, "output": ""},
        failure_type=failure_type,
        quality_score=0.9 if status == "success" else 0.3,
        recommendation="",
        missing_symbols=[],
        missing_context=[],
    )


@pytest.fixture
def exp_store(tmp_path: Path) -> ContextExperienceStore:
    return ContextExperienceStore(tmp_path / "factory" / "exec")


@pytest.fixture
def mini_project(tmp_path: Path) -> Path:
    write_files(tmp_path / "proj", MINI_PROJECT)
    return tmp_path / "proj"


@pytest.fixture
def miss_project(tmp_path: Path) -> Path:
    write_files(tmp_path / "proj2", MISS_PROJECT)
    return tmp_path / "proj2"


# ================================================================ 1. Execution→Experience

class TestExecutionToExperience:
    """AgentRuntime 全链: 任务结束自动提取 ContextExperienceRecord (成功+失败)。"""

    def _runtime(
        self, project_dir: Path, tmp_path: Path, *, extractor: Any = None,
        ranking_enabled: bool = True,
    ) -> AgentRuntime:
        provider = FakeProvider(content="<operations>[]</operations>")
        (tmp_path / "wr").mkdir(exist_ok=True)
        return AgentRuntime(
            provider,
            work_root=str(tmp_path / "wr"),
            experience_extractor=extractor,
            ranking_enabled=ranking_enabled,
        )

    def test_execute_success_extracts_record(
        self, mini_project: Path, tmp_path: Path, exp_store: ContextExperienceStore
    ) -> None:
        """成功执行 → 自动提取 + 落库 (is_success=True, 状态 success)。"""
        rt = self._runtime(
            mini_project, tmp_path, extractor=ExperienceExtractor(exp_store)
        )
        result = rt.execute(make_request(project_dir=mini_project))
        assert result.status.value == "success"
        records = exp_store.list_all()
        assert len(records) == 1
        rec = records[0]
        assert rec.is_success
        assert rec.execution_result["status"] == "success"
        assert rec.task_type  # 提取自 request (task_id 锚点)

    def test_execute_success_record_carries_ranking_trace(
        self, mini_project: Path, tmp_path: Path, exp_store: ContextExperienceStore
    ) -> None:
        """成功记录携带 ranking_trace/context_used (来自 last_ranking_result)。"""
        rt = self._runtime(
            mini_project, tmp_path, extractor=ExperienceExtractor(exp_store),
            ranking_enabled=True,
        )
        rt.execute(make_request(project_dir=mini_project))
        rec = exp_store.list_all()[0]
        assert rec.ranking_trace.get("total_candidates", 0) > 0
        assert rec.context_used.get("candidates")
        assert rec.budget_trace.get("actual_usage", 0) >= 0

    def test_execute_failure_extracts_failed_record(
        self, mini_project: Path, tmp_path: Path, exp_store: ContextExperienceStore
    ) -> None:
        """Provider 失败 → 失败记录自动提取 (failure_type 分类 + 状态 failed)。"""
        provider = FakeProvider(error="no parseable patch: boom")
        (tmp_path / "wrf").mkdir(exist_ok=True)
        rt = AgentRuntime(
            provider,
            work_root=str(tmp_path / "wrf"),
            experience_extractor=ExperienceExtractor(exp_store),
            ranking_enabled=True,
        )
        result = rt.execute(make_request(project_dir=mini_project))
        assert result.status.value == "failed"
        records = exp_store.list_all()
        assert len(records) == 1
        rec = records[0]
        assert not rec.is_success
        assert rec.execution_result["status"] == "failed"
        assert rec.failure_type == FAILURE_OPERATION

    def test_execute_early_failure_extracts_by_text(
        self, tmp_path: Path, exp_store: ContextExperienceStore
    ) -> None:
        """早期失败 (无 assembler/无上下文) → 仍提取失败记录 (按错误文本分类)。"""
        provider = FakeProvider(content="<operations>[]</operations>")
        (tmp_path / "wre").mkdir(exist_ok=True)
        rt = AgentRuntime(
            provider,
            work_root=str(tmp_path / "wre"),
            experience_extractor=ExperienceExtractor(exp_store),
            ranking_enabled=True,
        )
        req = make_request(project_dir=tmp_path / "no-such-dir")
        result = rt.execute(req)
        assert result.status.value == "failed"
        records = exp_store.list_all()
        assert len(records) == 1
        rec = records[0]
        assert not rec.is_success
        # 早期失败无 ranking 产物 → trace 缺省空, 链路不破坏
        assert rec.ranking_trace == {}

    def test_execute_without_extractor_no_record(
        self, mini_project: Path, tmp_path: Path, exp_store: ContextExperienceStore
    ) -> None:
        """无 extractor 装配 → 零记录 (backward compat: 旧链路逐位不变)。"""
        rt = self._runtime(mini_project, tmp_path, extractor=None)
        result = rt.execute(make_request(project_dir=mini_project))
        assert result.status.value == "success"
        assert exp_store.count() == 0


# ================================================================ 2. Experience→Ranking

class TestExperienceToRanking:
    """持久化 symbol_miss 失败史 → experience_match 提权 (与启发式区分)。"""

    def test_persisted_symbol_miss_boosts_file(
        self, miss_project: Path, exp_store: ContextExperienceStore
    ) -> None:
        """renderer.dart basename 不含任务符号 (启发式不命中) — 经验库失败史提权。"""
        exp_store.save(make_record(
            record_id="exp-miss", task_type="bug_fix",
            status="failed", failure_type=FAILURE_SYMBOL_MISS,
            source="widgets/renderer.dart",
        ))
        res = RankingPipeline(miss_project, experience_store=exp_store).run(
            _miss_task()
        )
        assert "widgets/renderer.dart" in res.feature_context.symbol_miss_files
        cand = next(c for c in res.ranked if c.source == "widgets/renderer.dart")
        assert cand.factor_scores.get("experience_match", 0.0) == pytest.approx(0.2 * 0.07)

    def test_no_experience_zero_boost(
        self, miss_project: Path, exp_store: ContextExperienceStore
    ) -> None:
        """无经验库 → experience_match = 0 (冷启动旧语义)。"""
        res = RankingPipeline(miss_project).run(_miss_task())
        # 无 store: 无持久化失败史; 启发式 (basename) 也不命中 renderer.dart
        assert "widgets/renderer.dart" not in res.feature_context.symbol_miss_files
        cand = next(c for c in res.ranked if c.source == "widgets/renderer.dart")
        assert cand.factor_scores.get("experience_match", 0.0) == 0.0

    def test_file_success_rate_injected(
        self, mini_project: Path, exp_store: ContextExperienceStore
    ) -> None:
        """文件级成功率注入 history_success (2 成功 1 失败 → 2/3)。"""
        exp_store.save_many([
            make_record(record_id="ok1", source="app/main.py"),
            make_record(record_id="ok2", source="app/main.py"),
            make_record(record_id="bad", source="app/main.py", status="failed",
                        failure_type=FAILURE_OPERATION),
        ])
        res = RankingPipeline(mini_project, experience_store=exp_store).run(
            _replace_task()
        )
        assert res.feature_context.history_rates["app/main.py"] == pytest.approx(round(2 / 3, 3))
        cand = next(c for c in res.ranked if c.source == "app/main.py")
        # file_success_rates 先 round(2/3, 3)=0.667 再乘权重 0.08 → 0.05336
        assert cand.factor_scores.get("history_success", 0.0) == pytest.approx(
            round(2 / 3, 3) * 0.08
        )


# ================================================================ 3. Experience→Progressive

class TestExperienceToProgressive:
    """成功记录阶段序共识 → 渐进加载阶段重排 (≥2 条共识)。"""

    def test_stage_reorder_with_two_consensus(
        self, mini_project: Path, exp_store: ContextExperienceStore
    ) -> None:
        """2 条成功记录均走 [overview, detail, symbol] → 阶段重排。"""
        exp_store.save_many([
            make_record(record_id="s1", stages=["overview", "detail", "symbol"]),
            make_record(record_id="s2", stages=["overview", "detail", "symbol"]),
        ])
        res = RankingPipeline(mini_project, experience_store=exp_store).run(
            _replace_task(), progressive=True
        )
        prog = res.progressive
        assert prog is not None
        # 必载 overview 位置不动; 非必载多数投票 detail 先于 symbol
        assert prog.stages == ["overview", "detail", "symbol"]

    def test_no_experience_default_order(
        self, mini_project: Path, exp_store: ContextExperienceStore
    ) -> None:
        """空经验库 → 默认阶段序 (backward compat)。"""
        res = RankingPipeline(mini_project, experience_store=exp_store).run(
            _replace_task(), progressive=True
        )
        assert res.progressive is not None
        assert res.progressive.stages == ["overview", "symbol", "detail"]


# ================================================================ 4. Experience→Budget

class TestExperienceToBudget:
    """成功记录实际用量 → 预算推荐 clamp ±20% (经验影响 ≤20% 硬限制)。"""

    def test_recommendation_clamped_to_span(
        self, mini_project: Path, exp_store: ContextExperienceStore
    ) -> None:
        """推荐 30000 (超 1.2×20000=24000) → clamp 到 24000 (不直接生效)。"""
        exp_store.save_many([
            make_record(record_id="u1", actual_usage=30000),
            make_record(record_id="u2", actual_usage=30000),
        ])
        res = RankingPipeline(mini_project, experience_store=exp_store).run(
            _replace_task()
        )
        # bug_fix 策略预算 20000; 1.2×20000 = 24000 → 推荐被 clamp
        assert res.budget.budget_chars == 24000
        assert 0.8 * 20000 <= res.budget.budget_chars <= 1.2 * 20000

    def test_recommendation_in_span_used(
        self, mini_project: Path, exp_store: ContextExperienceStore
    ) -> None:
        """推荐 18000 (在 [0.8×, 1.2×] 内) → 直接用。"""
        exp_store.save_many([
            make_record(record_id="v1", actual_usage=18000),
            make_record(record_id="v2", actual_usage=18000),
        ])
        res = RankingPipeline(mini_project, experience_store=exp_store).run(
            _replace_task()
        )
        assert res.budget.budget_chars == 18000

    def test_no_success_records_old_semantics(
        self, mini_project: Path, exp_store: ContextExperienceStore
    ) -> None:
        """无成功记录 → 推荐 None → min(policy, hard_cap) 旧语义。"""
        exp_store.save(make_record(
            record_id="only-bad", status="failed", failure_type=FAILURE_OPERATION,
            actual_usage=30000,
        ))
        res = RankingPipeline(mini_project, experience_store=exp_store).run(
            _replace_task()
        )
        # bug_fix 策略 20000 < hard_cap 30000 → 策略预算
        assert res.budget.budget_chars == 20000


# ================================================================ 5. backward compat

class TestBackwardCompat:
    """无经验库/空库 → 旧语义逐位不变 (零回归)。"""

    def test_empty_store_identical_to_no_store(
        self, mini_project: Path, exp_store: ContextExperienceStore
    ) -> None:
        """空经验库 vs 无经验库 → 关键输出逐位一致。"""
        with_store = RankingPipeline(
            mini_project, experience_store=exp_store
        ).run(_replace_task())
        without = RankingPipeline(mini_project).run(_replace_task())
        assert with_store.budget.budget_chars == without.budget.budget_chars
        assert with_store.budget.selected_ids == without.budget.selected_ids
        assert with_store.ranked[0].id == without.ranked[0].id

    def test_extract_without_store_pure_memory(self) -> None:
        """extractor 无 store → 返回记录不落库 (纯内存, 旧行为)。"""
        ex = ExperienceExtractor()
        rec = ex.extract(result=_SimpleResult(status="success"))
        assert rec is not None
        assert rec.is_success

    def test_context_assembler_last_ranking_result_none_by_default(
        self, mini_project: Path
    ) -> None:
        """旧 assemble() 路径 → last_ranking_result=None (纯新增属性零回归)。"""
        ctx = ContextAssembler(mini_project)
        assert ctx.last_ranking_result is None

    def test_legacy_assembled_renderable(
        self, mini_project: Path, exp_store: ContextExperienceStore
    ) -> None:
        """经验 store 装配 + 旧 assemble() → 渲染正常 (零破坏)。"""
        ctx = ContextAssembler(mini_project, experience_store=exp_store)
        out = ctx.assemble(_replace_task())
        prompt = out.render_prompt()
        assert "## Task" in prompt


# ================================================================ 6. 全链闭环

class TestFullLoop:
    """extract → 落库 → find_similar → 下游消费 (端到端)。"""

    def test_full_loop_extract_similar_consume(
        self, mini_project: Path, tmp_path: Path, exp_store: ContextExperienceStore
    ) -> None:
        """成功执行落库 → find_similar 命中 → 二次执行消费 (预算推荐链路)。"""
        rt = AgentRuntime(
            FakeProvider(content="<operations>[]</operations>"),
            work_root=str(tmp_path / "wrloop"),
            experience_extractor=ExperienceExtractor(exp_store),
            ranking_enabled=True,
        )
        (tmp_path / "wrloop").mkdir(exist_ok=True)
        rt.execute(make_request(project_dir=mini_project))
        assert exp_store.count() == 1
        # find_similar 全链: extract 的 task_type 取 request.task_id (T-101) —
        # 查询须按实际记录 task_type 过滤
        similar = exp_store.find_similar(task_type="T-101", limit=1)
        assert len(similar) == 1
        # 下游消费: 含经验的 pipeline 正常出结果 (预算推荐/提权失败安全)
        res = RankingPipeline(mini_project, experience_store=exp_store).run(
            _replace_task()
        )
        assert res.assembled is not None and res.assembled.render_prompt()


class _SimpleResult:
    """最小 duck-typed ExecutionResult (extractor 输入)。"""

    def __init__(self, *, status: str, error: str = "") -> None:
        self.status = status
        self.is_success = status == "success"
        self.error = error
        self.duration = 1.0
        self.usage = {}
        self.employee_id = "E-1"
        self.request_id = "EXR-1"
