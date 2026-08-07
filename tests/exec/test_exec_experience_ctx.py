"""tests/exec/test_exec_experience_ctx.py — Context Experience 单元测试 (Sprint 4 T4.4)。

覆盖 (全部纯本地, 零 LLM 零网络):
- ContextExperienceRecord: 17 字段构造/序列化 round-trip/extra=forbid/校验器/is_success/to_dict
- to_legacy_fields: → 10A-4 ExperienceAnalyzer kwargs 映射
- ContextExperienceStore: save/get/list_all/count/save_many/原子写/损坏失败安全
- query: task_type/failure_type/keywords/success_only 组合过滤
- Similar Matching: record_similarity 加权规则 (0.4/0.3/0.2/0.1) / 缺省维度归一 /
  find_similar_records 阈值+limit / store.find_similar
- ExperienceExtractor: classify_failure 五类优先级 + extract 全链路 Trace + recommendation
- Failure Learning 纯函数: symbol_miss_files_from_experience / file_success_rates /
  budget_recommendation / stage_order_from_experience
- statistics: 总数/任务分布/失败分布/成功率/质量/预算

basename 唯一 (test_exec_* 前缀); helper 复用 tests/exec/exec_helpers.py。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from exec.experience_ctx import (
    FAILURE_CONTEXT_INSUFFICIENT,
    FAILURE_OPERATION,
    FAILURE_SYMBOL_MISS,
    FAILURE_TOKEN_OVERFLOW,
    FAILURE_VALIDATION,
    SIMILARITY_WEIGHTS,
    ContextExperienceRecord,
    ContextExperienceStore,
    ExperienceExtractor,
    budget_recommendation,
    file_success_rates,
    find_similar_records,
    keyword_overlap,
    record_similarity,
    stage_order_from_experience,
    symbol_miss_files_from_experience,
)

# ================================================================ fixtures / factories


def make_record(
    *,
    record_id: str = "exp-1",
    task_type: str = "bug_fix",
    summary: str = "fix replace_current bug in app/main.py",
    failure_type: str = "",
    status: str = "success",
    candidates: list[dict[str, Any]] | None = None,
    content_refs: list[str] | None = None,
    stages: list[str] | None = None,
    actual_usage: int = 0,
    quality: float = 0.9,
    employee_id: str = "E-1",
) -> ContextExperienceRecord:
    """记录工厂 (唯一缺省 id — 防 save 互相覆盖)。"""
    return ContextExperienceRecord(
        id=record_id,
        task_type=task_type,
        task_summary=summary,
        context_used={
            "candidates": candidates
            or [{"id": "code:app/main.py", "type": "code", "source": "app/main.py",
                 "level": "full"}],
            "content_refs": content_refs if content_refs is not None else ["app/main.py"],
        },
        ranking_trace={"total_candidates": 5, "ranked_ids": ["c1", "c2"], "scores": {}},
        progressive_trace={"stages": stages or ["overview", "symbol", "detail"]},
        budget_trace={"actual_usage": actual_usage},
        execution_result={"status": status, "error": "", "duration": 1.0,
                          "usage": {}, "employee_id": employee_id, "request_id": "EXR-1"},
        validation_result={"passed": True, "attempts": 1, "output": ""},
        failure_type=failure_type,
        quality_score=quality,
        recommendation="",
        missing_symbols=[],
        missing_context=[],
    )


@pytest.fixture
def store(tmp_path: Path) -> ContextExperienceStore:
    return ContextExperienceStore(tmp_path / "factory" / "exec")


class _Result:
    """duck-typed ExecutionResult (extractor 输入)。"""

    def __init__(self, *, status: str = "success", error: str = "",
                 duration: float = 1.0, usage: dict[str, Any] | None = None,
                 context_score: float | None = None, employee_id: str = "E-1",
                 request_id: str = "EXR-1") -> None:
        self.status = status
        self.is_success = status == "success"
        self.error = error
        self.duration = duration
        self.usage = usage or {}
        self.context_score = context_score
        self.employee_id = employee_id
        self.request_id = request_id


class _Request:
    """duck-typed ExecutionRequest (extractor 输入)。"""

    def __init__(self, *, task_id: str = "T-101", objective: str = "",
                 requirement: str = "") -> None:
        self.task_id = task_id
        self.objective = objective
        self.requirement = requirement


class _Validation:
    """duck-typed ValidationResult。"""

    def __init__(self, *, passed: bool = True, attempts: int = 1,
                 output: str = "") -> None:
        self.passed = passed
        self.attempts = attempts
        self.output = output


class _Progressive:
    """duck-typed ProgressiveResult (trace 带 symbol_miss/overflow 标志)。"""

    def __init__(self, *, trace: dict[str, Any] | None = None,
                 stages: list[str] | None = None) -> None:
        self.trace = type("T", (), trace or {})() if trace else None
        self.stages = stages or []


class _Budget:
    """duck-typed BudgetResult (attribute + to_dict 双通道 — 同真实类)。"""

    def __init__(self, d: dict[str, Any]) -> None:
        for k, v in d.items():
            setattr(self, k, v)

    def to_dict(self) -> dict[str, Any]:
        return {
            k: v for k, v in vars(self).items() if not k.startswith("_")
        }


# ================================================================ 1. Record 模型/序列化

class TestRecordModel:
    def test_record_17_fields_defaults(self) -> None:
        r = make_record()
        assert r.id == "exp-1"
        assert r.task_type == "bug_fix"
        assert isinstance(r.context_used, dict)
        assert isinstance(r.ranking_trace, dict)
        assert isinstance(r.progressive_trace, dict)
        assert isinstance(r.budget_trace, dict)
        assert isinstance(r.execution_result, dict)
        assert isinstance(r.validation_result, dict)
        assert r.failure_type == ""
        assert r.missing_symbols == []
        assert r.missing_context == []
        assert r.created_at  # 审计锚点非空

    def test_serialization_round_trip(self) -> None:
        r = make_record()
        d = r.to_dict()
        assert set(d) >= {
            "id", "task_type", "task_summary", "context_used", "ranking_trace",
            "progressive_trace", "budget_trace", "execution_result",
            "validation_result", "failure_type", "quality_score",
            "recommendation", "missing_symbols", "missing_context", "created_at",
        }
        r2 = ContextExperienceRecord.model_validate(d)
        assert r2.id == r.id
        assert r2.task_type == r.task_type
        assert r2.execution_result == r.execution_result
        assert r2.context_used == r.context_used
        assert r2.created_at == r.created_at

    def test_extra_forbid(self) -> None:
        with pytest.raises(Exception):
            ContextExperienceRecord.model_validate(
                make_record().to_dict() | {"bogus_field": 1}
            )

    def test_none_inputs_normalized(self) -> None:
        r = ContextExperienceRecord(
            id="exp-n", task_type=None, task_summary=None, context_used=None,
            ranking_trace=None, progressive_trace=None, budget_trace=None,
            execution_result=None, validation_result=None, failure_type=None,
            missing_symbols=None, missing_context=None,
        )
        assert r.task_type == ""
        assert r.context_used == {}
        assert r.ranking_trace == {}
        assert r.missing_symbols == []
        assert r.failure_type == ""

    def test_quality_score_clamped(self) -> None:
        assert make_record(quality=1.7).quality_score == 1.0
        assert make_record(quality=-0.5).quality_score == 0.0

    def test_is_success_semantics(self) -> None:
        ok = make_record(status="success", failure_type="")
        assert ok.is_success
        # 状态 success 但带失败类型 → 不算成功 (诚实: 有失败痕迹)
        assert not make_record(status="success", failure_type=FAILURE_SYMBOL_MISS).is_success
        assert not make_record(status="failed", failure_type=FAILURE_OPERATION).is_success
        assert not make_record(status="failed", failure_type="").is_success

    def test_missing_symbols_list_alias(self) -> None:
        r = make_record()
        r.missing_symbols = ["foo", "bar"]
        assert r.missing_symbols_list == ["foo", "bar"]

    def test_to_legacy_fields_mapping_success(self) -> None:
        r = make_record(employee_id="E-7", quality=0.85)
        f = r.to_legacy_fields()
        assert f["subject_type"] == "agent"
        assert f["subject_id"] == "E-7"
        assert f["task_type"] == "bug_fix"
        assert f["result"] == "success"
        assert f["score"] == 0.8
        assert f["quality_score"] == 0.85
        assert f["capability"] == ["development"]
        assert f["evidence"][0]["source_id"] == r.id

    def test_to_legacy_fields_mapping_failure(self) -> None:
        r = make_record(status="failed", failure_type=FAILURE_VALIDATION,
                        employee_id="")
        f = r.to_legacy_fields()
        assert f["result"] == "failure"
        assert f["score"] == 0.2
        assert f["subject_id"] == "unknown-employee"
        assert "validation_failure" in f["evidence"][0]["description"]


# ================================================================ 2. Store CRUD / 原子写 / 损坏

class TestStoreCrud:
    def test_save_get_list_count(self, store: ContextExperienceStore) -> None:
        r = make_record(record_id="exp-a")
        store.save(r)
        assert store.count() == 1
        assert store.get("exp-a") is not None
        assert store.get("missing") is None
        assert [x.id for x in store.list_all()] == ["exp-a"]

    def test_save_many_and_overwrite_by_id(self, store: ContextExperienceStore) -> None:
        store.save_many([make_record(record_id="a"), make_record(record_id="b")])
        assert store.count() == 2
        # 同 id 覆盖 → 仍 2 条
        store.save_many([make_record(record_id="a", summary="updated")])
        assert store.count() == 2
        assert store.get("a").task_summary == "updated"

    def test_list_all_sorted_by_created_at(self, store: ContextExperienceStore) -> None:
        r_early = make_record(record_id="early")
        r_early.created_at = "2020-01-01T00:00:00Z"
        r_late = make_record(record_id="late")
        r_late.created_at = "2026-01-01T00:00:00Z"
        store.save_many([r_late, r_early])
        assert [x.id for x in store.list_all()] == ["early", "late"]

    def test_file_created_on_first_save(self, tmp_path: Path) -> None:
        s = ContextExperienceStore(tmp_path / "newdir")
        assert not s.path.exists()
        s.save(make_record(record_id="x1"))
        assert s.path.exists()
        assert s.count() == 1

    def test_atomic_write_marker(self, store: ContextExperienceStore) -> None:
        store.save(make_record(record_id="a"))
        import os
        leftovers = [p for p in store.root.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []
        # 数据文件是普通 JSON 列表
        import json
        data = json.loads(store.path.read_text(encoding="utf-8"))
        assert isinstance(data, list) and data[0]["id"] == "a"

    def test_corrupt_file_reads_empty(self, tmp_path: Path) -> None:
        s = ContextExperienceStore(tmp_path / "factory" / "exec")
        s.root.mkdir(parents=True, exist_ok=True)
        s.path.write_text("{not json", encoding="utf-8")
        assert s.count() == 0
        assert s.list_all() == []
        # save 从空重建 (审计增强数据: 损坏不致命)
        s.save(make_record(record_id="a"))
        assert s.count() == 1

    def test_bad_single_record_skipped(self, tmp_path: Path) -> None:
        import json
        s = ContextExperienceStore(tmp_path / "factory" / "exec")
        s.root.mkdir(parents=True, exist_ok=True)
        good = make_record(record_id="good").to_dict()
        s.path.write_text(
            json.dumps([good, {"id": "bad", "task_type": 123, "junk": "x"}], ensure_ascii=False),
            encoding="utf-8",
        )
        # 单条坏 → 跳过 (extra=forbid 或校验失败都跳过), 好条保留
        assert [r.id for r in s.list_all()] == ["good"]

    def test_query_combined_filters(self, store: ContextExperienceStore) -> None:
        store.save_many([
            make_record(record_id="a", task_type="bug_fix", summary="fix sub bug",
                        failure_type=FAILURE_SYMBOL_MISS, status="failed"),
            make_record(record_id="b", task_type="bug_fix", summary="fix add bug"),
            make_record(record_id="c", task_type="feature", summary="add module",
                        failure_type=FAILURE_OPERATION, status="failed"),
        ])
        assert len(store.query()) == 3
        assert [r.id for r in store.query(task_type="bug_fix")] == ["a", "b"]
        assert [r.id for r in store.query(failure_type=FAILURE_SYMBOL_MISS)] == ["a"]
        assert [r.id for r in store.query(success_only=True)] == ["b"]
        # 空字符串 = 无过滤
        assert len(store.query(task_type="")) == 3
        # 关键词 (摘要 + 内容引用)
        assert [r.id for r in store.query(keywords=["sub"])] == ["a"]
        assert [r.id for r in store.query(keywords=["nope"])] == []


# ================================================================ 3. Similar Matching

class TestSimilarMatching:
    def test_keyword_overlap_jaccard(self) -> None:
        assert keyword_overlap(["a", "b"], ["a", "b"]) == 1.0
        assert keyword_overlap(["a", "b"], ["a"]) == pytest.approx(1 / 2)
        assert keyword_overlap([], ["a"]) == 0.0
        assert keyword_overlap(["a"], []) == 0.0

    def test_record_similarity_task_type_weight(self) -> None:
        r = make_record(task_type="bug_fix")
        assert record_similarity(r, task_type="bug_fix") == 1.0
        assert record_similarity(r, task_type="feature") == 0.0

    def test_record_similarity_keyword_dimension(self) -> None:
        r = make_record(summary="fix replace_current bug", task_type="bug_fix")
        # keyword 维: 完全重合 → 该维满分; 归一后 = keyword 权重 0.3
        sim = record_similarity(r, keywords=["replace_current"])
        assert sim > 0.0
        assert sim <= 0.3 + 1e-9  # 只提供 keyword → 按权重和 0.3 归一

    def test_record_similarity_symbol_dimension(self) -> None:
        r = make_record(failure_type=FAILURE_SYMBOL_MISS, status="failed",
                        content_refs=[])  # 空引用 → symbol 维纯净
        r.missing_symbols = ["my_widget"]
        sim = record_similarity(r, symbols=["my_widget"])
        assert sim == pytest.approx(1.0)  # 只提供 symbol → 归一满分

    def test_record_similarity_failure_type_weight(self) -> None:
        r = make_record(failure_type=FAILURE_OPERATION, status="failed")
        assert record_similarity(r, failure_type=FAILURE_OPERATION) == 1.0
        assert record_similarity(r, failure_type=FAILURE_SYMBOL_MISS) == 0.0

    def test_record_similarity_multi_dimension_recomputable(self) -> None:
        r = make_record(task_type="bug_fix", failure_type=FAILURE_OPERATION, status="failed")
        score = record_similarity(r, task_type="bug_fix", failure_type=FAILURE_OPERATION)
        expect = (SIMILARITY_WEIGHTS["task_type"] * 1.0
                  + SIMILARITY_WEIGHTS["failure_type"] * 1.0) \
            / (SIMILARITY_WEIGHTS["task_type"] + SIMILARITY_WEIGHTS["failure_type"])
        assert score == pytest.approx(expect)

    def test_record_similarity_no_query_dimensions_zero(self) -> None:
        assert record_similarity(make_record()) == 0.0

    def test_find_similar_records_threshold_and_limit(self, store: ContextExperienceStore) -> None:
        store.save_many([
            make_record(record_id="a", task_type="bug_fix"),
            make_record(record_id="b", task_type="feature"),
        ])
        hits = store.find_similar(task_type="bug_fix", limit=5)
        assert [r.id for r, s in hits] == ["a"]
        # 阈值: task_type 不匹配 → 0 分 < 0.3 → 剔除
        assert store.find_similar(task_type="refactor") == []

    def test_find_similar_sorted_by_score_desc(self) -> None:
        r_best = make_record(record_id="best", task_type="bug_fix",
                             summary="fix replace_current in main",
                             failure_type=FAILURE_SYMBOL_MISS, status="failed")
        r_ok = make_record(record_id="ok", task_type="bug_fix")
        hits = find_similar_records(
            [r_ok, r_best],
            task_type="bug_fix",
            keywords=["replace_current"],
            failure_type=FAILURE_SYMBOL_MISS,
        )
        assert [r.id for r, s in hits] == ["best", "ok"]

    def test_find_similar_records_limit_cap(self, store: ContextExperienceStore) -> None:
        store.save_many([make_record(record_id=f"r{i}", task_type="bug_fix")
                         for i in range(5)])
        assert len(store.find_similar(task_type="bug_fix", limit=2)) == 2


# ================================================================ 4. Extractor 失败分类 (五类)

class TestClassifyFailure:
    def test_success_is_empty(self) -> None:
        ex = ExperienceExtractor()
        assert ex.classify_failure(_Result(status="success")) == ""

    def test_symbol_miss_priority(self) -> None:
        ex = ExperienceExtractor()
        # trace 显式记录优先
        prog = _Progressive(trace={"symbol_miss": ["my_widget"]})
        assert ex.classify_failure(_Result(status="failed"), progressive=prog) \
            == FAILURE_SYMBOL_MISS
        # 错误文本 "symbol" 特征
        assert ex.classify_failure(
            _Result(status="failed", error="symbol my_widget not defined")
        ) == FAILURE_SYMBOL_MISS

    def test_token_overflow(self) -> None:
        ex = ExperienceExtractor()
        # 预算 overflow 标志
        budget = _Budget({"context_overflow": True})
        assert ex.classify_failure(_Result(status="failed"), budget=budget) \
            == FAILURE_TOKEN_OVERFLOW
        # 文本特征
        assert ex.classify_failure(
            _Result(status="failed", error="context token budget overflow")
        ) == FAILURE_TOKEN_OVERFLOW

    def test_validation_failure(self) -> None:
        ex = ExperienceExtractor()
        v = _Validation(passed=False)
        assert ex.classify_failure(_Result(status="failed"), validation=v) \
            == FAILURE_VALIDATION
        assert ex.classify_failure(
            _Result(status="failed", error="validation failed: syntax error")
        ) == FAILURE_VALIDATION

    def test_context_insufficient(self) -> None:
        ex = ExperienceExtractor()
        prog = _Progressive(trace={"unable_to_locate": True})
        assert ex.classify_failure(_Result(status="failed"), progressive=prog) \
            == FAILURE_CONTEXT_INSUFFICIENT
        assert ex.classify_failure(
            _Result(status="failed"), context_score=0.3
        ) == FAILURE_CONTEXT_INSUFFICIENT

    def test_operation_failure_lowest_priority(self) -> None:
        ex = ExperienceExtractor()
        assert ex.classify_failure(
            _Result(status="failed", error="no parseable patch")
        ) == FAILURE_OPERATION
        assert ex.classify_failure(
            _Result(status="failed", error="operation failed")
        ) == FAILURE_OPERATION

    def test_unknown_failure_empty(self) -> None:
        ex = ExperienceExtractor()
        assert ex.classify_failure(_Result(status="failed", error="weird thing")) == ""


# ================================================================ 5. Extractor extract 全链

class TestExtract:
    def test_extract_success_full_trace(self, store: ContextExperienceStore) -> None:
        ex = ExperienceExtractor(store)
        rec = ex.extract(
            result=_Result(status="success"),
            request=_Request(task_id="T-1", objective="fix the sub bug"),
            ranking=type("R", (), {
                "ranked": [type("C", (), {"id": "code:a.py", "type": "code",
                                          "source": "a.py", "relevance_score": 0.9,
                                          "content_ref": "a.py"})],
                "selection": type("S", (), {"selected_ids": ["code:a.py"]}),
                "budget": _Budget({"levels": {"code:a.py": "full"}, "selected_ids": ["code:a.py"]}),
            })(),
            progressive=_Progressive(trace={"stages": ["overview", "symbol"]},
                                     stages=["overview", "symbol"]),
            budget=_Budget({"budget_chars": 5000, "total_chars": 3000}),
            validation=_Validation(passed=True, attempts=2, output="ok"),
            context_score=0.85,
            employee_id="E-1",
        )
        assert rec.is_success
        assert rec.task_type == "T-1"
        assert rec.task_summary == "fix the sub bug"
        assert rec.execution_result["status"] == "success"
        assert rec.validation_result["passed"] is True
        assert rec.validation_result["attempts"] == 2
        assert rec.quality_score == 0.85
        assert rec.ranking_trace["total_candidates"] == 1
        assert rec.context_used["candidates"][0]["id"] == "code:a.py"
        assert store.get(rec.id) is not None  # 落库

    def test_extract_failure_symbol_miss(self, store: ContextExperienceStore) -> None:
        ex = ExperienceExtractor(store)
        rec = ex.extract(
            result=_Result(status="failed", error="symbol my_widget not defined"),
            request=_Request(task_id="T-2", objective="wire my_widget"),
            progressive=_Progressive(trace={"symbol_miss": ["my_widget"]}),
            symbols_missed=["my_widget"],
            employee_id="E-1",
        )
        assert not rec.is_success
        assert rec.failure_type == FAILURE_SYMBOL_MISS
        assert rec.missing_symbols == ["my_widget"]
        assert rec.recommendation  # 失败 → 建议非空
        assert "line_range" in rec.recommendation

    def test_extract_failure_validation(self, store: ContextExperienceStore) -> None:
        ex = ExperienceExtractor(store)
        rec = ex.extract(
            result=_Result(status="failed"),
            request=_Request(task_id="T-3", objective="refactor"),
            validation=_Validation(passed=False, attempts=2, output="1 failed"),
            employee_id="E-1",
        )
        assert rec.failure_type == FAILURE_VALIDATION
        assert rec.validation_result["passed"] is False
        assert rec.validation_result["output"] == "1 failed"

    def test_extract_failure_overflow_missing_context(self, store: ContextExperienceStore) -> None:
        ex = ExperienceExtractor(store)
        rec = ex.extract(
            result=_Result(status="failed", error="token overflow"),
            request=_Request(task_id="T-4", objective="big refactor"),
            budget=_Budget({"context_overflow": True}),
            employee_id="E-1",
        )
        assert rec.failure_type == FAILURE_TOKEN_OVERFLOW

    def test_extract_failure_context_insufficient(self, store: ContextExperienceStore) -> None:
        ex = ExperienceExtractor(store)
        rec = ex.extract(
            result=_Result(status="failed"),
            request=_Request(task_id="T-5", objective="understand"),
            context_score=0.4,
            employee_id="E-1",
        )
        assert rec.failure_type == FAILURE_CONTEXT_INSUFFICIENT
        assert "core files" in rec.missing_context

    def test_extract_no_store_memory_only(self) -> None:
        ex = ExperienceExtractor()  # store=None → 只构造不落库
        rec = ex.extract(result=_Result(status="success"),
                         request=_Request(task_id="T-6", objective="x"))
        assert rec.is_success
        assert ex.store is None

    def test_extract_minimal_inputs(self) -> None:
        """只有 result → 全 trace 缺省空, 提取不破坏 (KISS 兜底)。"""
        ex = ExperienceExtractor()
        rec = ex.extract(result=_Result(status="failed", error="execution error: boom"))
        assert not rec.is_success
        assert rec.task_type == "development"  # 缺省任务类型
        assert rec.failure_type == ""  # 未知错误不硬套五类


# ================================================================ 6. Failure Learning 纯函数

class TestFailureLearning:
    def test_symbol_miss_files_from_experience(self) -> None:
        bad = make_record(record_id="b1", status="failed",
                          failure_type=FAILURE_SYMBOL_MISS,
                          candidates=[{"id": "c", "type": "code",
                                       "source": "widgets/my_widget.dart", "level": "symbol"}])
        ok = make_record(record_id="ok1")  # 成功记录不参与
        out = symbol_miss_files_from_experience([bad, ok])
        assert out == {"widgets/my_widget.dart"}

    def test_symbol_miss_files_filtered_by_files(self) -> None:
        bad = make_record(record_id="b1", status="failed",
                          failure_type=FAILURE_SYMBOL_MISS,
                          candidates=[{"id": "c", "type": "code",
                                       "source": "app/main.py", "level": "symbol"}])
        out = symbol_miss_files_from_experience([bad], files=["app/main.py", "other.py"])
        assert out == {"app/main.py"}  # 防幻影路径

    def test_file_success_rates(self) -> None:
        ok = make_record(record_id="ok", candidates=[{"id": "c", "type": "code",
                                                      "source": "a.py", "level": "full"}])
        bad = make_record(record_id="bad", status="failed",
                          failure_type=FAILURE_OPERATION,
                          candidates=[{"id": "c", "type": "code",
                                       "source": "a.py", "level": "full"},
                                      {"id": "d", "type": "code",
                                       "source": "b.py", "level": "symbol"}])
        rates = file_success_rates([ok, bad])
        assert rates["a.py"] == 0.5
        assert rates["b.py"] == 0.0
        assert "c.py" not in rates  # 未出现 → 无键 (冷启动 0.5)

    def test_budget_recommendation_success_only(self) -> None:
        recs = [
            make_record(record_id="s1", task_type="bug_fix", actual_usage=4000),
            make_record(record_id="s2", task_type="bug_fix", actual_usage=6000),
            make_record(record_id="f1", task_type="bug_fix", status="failed",
                        failure_type=FAILURE_OPERATION, actual_usage=30000),
        ]
        assert budget_recommendation(recs, task_type="bug_fix") == 5000
        # 其他任务类型不参与
        assert budget_recommendation(recs, task_type="feature") is None
        # 无成功记录 → None
        assert budget_recommendation(recs[2:], task_type="bug_fix") is None

    def test_stage_order_from_experience_default_when_cold(self) -> None:
        defaults = ["overview", "symbol", "detail"]
        assert stage_order_from_experience([], defaults) == defaults
        # 单条成功记录 → 票数 < 2 → 默认序
        recs = [make_record(record_id="s1", stages=["overview", "detail", "symbol"])]
        assert stage_order_from_experience(recs, defaults) == defaults

    def test_stage_order_from_experience_reorder_with_consensus(self) -> None:
        defaults = ["overview", "symbol", "detail"]
        recs = [
            make_record(record_id="s1", stages=["overview", "detail", "symbol"]),
            make_record(record_id="s2", stages=["overview", "detail", "symbol"]),
        ]
        order = stage_order_from_experience(recs, defaults)
        # 必载阶段 overview 位置不动; 非必载多数投票 detail 先于 symbol
        assert order == ["overview", "detail", "symbol"]

    def test_stage_order_required_stage_position_fixed(self) -> None:
        defaults = ["overview", "symbol", "detail"]
        recs = [
            make_record(record_id="s1", stages=["symbol", "overview", "detail"]),
            make_record(record_id="s2", stages=["symbol", "overview", "detail"]),
        ]
        order = stage_order_from_experience(recs, defaults)
        assert order[0] == "overview"  # 必载恒先
        assert set(order) == set(defaults)

    def test_stage_order_failure_records_excluded(self) -> None:
        defaults = ["overview", "symbol", "detail"]
        recs = [
            make_record(record_id="f1", status="failed", failure_type=FAILURE_OPERATION,
                        stages=["overview", "detail", "symbol"]),
            make_record(record_id="f2", status="failed", failure_type=FAILURE_OPERATION,
                        stages=["overview", "detail", "symbol"]),
        ]
        # 失败经验不参与排序 → 默认序
        assert stage_order_from_experience(recs, defaults) == defaults


# ================================================================ 7. Store statistics

class TestStatistics:
    def test_statistics_empty(self, store: ContextExperienceStore) -> None:
        st = store.statistics()
        assert st["total"] == 0
        assert st["success_rate"] == 0.0
        assert st["avg_quality_score"] == 0.0
        assert st["avg_budget_actual"] is None

    def test_statistics_aggregation(self, store: ContextExperienceStore) -> None:
        store.save_many([
            make_record(record_id="a", task_type="bug_fix", actual_usage=4000,
                        quality=0.9),
            make_record(record_id="b", task_type="bug_fix", actual_usage=6000,
                        quality=0.7),
            make_record(record_id="c", task_type="feature", status="failed",
                        failure_type=FAILURE_OPERATION, actual_usage=0, quality=0.3),
        ])
        st = store.statistics()
        assert st["total"] == 3
        assert st["by_task_type"] == {"bug_fix": 2, "feature": 1}
        assert st["by_failure_type"] == {FAILURE_OPERATION: 1}
        assert st["success_count"] == 2
        assert st["failure_count"] == 1
        assert st["success_rate"] == pytest.approx(round(2 / 3, 3))
        assert st["avg_quality_score"] == pytest.approx(round((0.9 + 0.7 + 0.3) / 3, 3))
        assert st["avg_budget_actual"] == 5000
