"""S10-067 — Memory Learning Core 测试套件。

覆盖: ExperienceRecord 模型 / ExperienceStore / ExperienceExtractor /
PatternLearner + LearningEngine / ExperienceRetriever / Recommender /
LearningTrace — 验收 A-G (Core 全工作 + 4 数据源提取 + 模式学习 + 检索推荐审计)。
装配: tmp_path + fixtures; 禁真实网络/LLM。

设计: docs/sprint10/S10-067-memory-learning-design.md §2-§6
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

MEM = import_module("factory-console.memory")
EXP = import_module("factory-console.memory.experience")
STORE = import_module("factory-console.memory.experience_store")
EXTR = import_module("factory-console.memory.extraction")
LE = import_module("factory-console.memory.learning_engine")
RET = import_module("factory-console.memory.retrieval")
REC = import_module("factory-console.memory.recommendation")
TRACE = import_module("factory-console.memory.learning_trace")


def _record(**kw):
    """ExperienceRecord 工厂 (缺省失败模式记录)。"""
    base = {
        "type": EXP.FAILURE_PATTERN,
        "project": "demo",
        "task": "登录功能",
        "agent": "backend-1",
        "role": "Backend Engineer",
        "context": "run_task 登录功能",
        "problem": "provider error: anthropic api key missing",
        "action": "agent.execute_task",
        "result": "failed",
        "success": False,
        "confidence": 0.8,
        "source": "execution_records",
    }
    base.update(kw)
    return EXP.ExperienceRecord(**base)


def _fixture_workspace(tmp_path: Path) -> Path:
    """4 数据源 fixture workspace (exec + repair + replanning + gap + validation)。"""
    ws = tmp_path / "ws"
    (ws / "exec").mkdir(parents=True)
    (ws / "exec" / EXTR.EXECUTION_RECORDS_FILE).write_text(
        json.dumps([
            {"intent": "run_task", "action": "agent.execute_task", "agent": "backend-1",
             "task": "登录功能", "result": "failed",
             "error": "provider error: anthropic api key missing",
             "timestamp": "2026-08-14T00:00:00+00:00"},
            {"intent": "run_task", "action": "agent.execute_task", "agent": "backend-1",
             "task": "数据库设计", "result": "success",
             "timestamp": "2026-08-14T00:00:01+00:00"},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    pd = ws / "projects" / "demo"
    pd.mkdir(parents=True)
    (pd / EXTR.REPAIR_TASK_FILE).write_text(
        json.dumps([
            {"repair_id": "repair-1", "original_task_id": "T1",
             "original_task_name": "登录功能",
             "failure_reason": "缺少 ANTHROPIC_API_KEY 配置",
             "retry_count": 1, "status": "completed",
             "created_at": "2026-08-15T00:00:00+00:00"},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    (pd / EXTR.REPLANNING_DECISIONS_FILE).write_text(
        json.dumps([
            {"decision": "INSERT_TASK", "reason": "计划缺 1 个任务",
             "new_tasks": [{"id": "T005", "name": "实现持久化存储"}],
             "plan_version": 1, "timestamp": "2026-08-16T00:00:00+00:00"},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    (pd / EXTR.GAP_ANALYSIS_FILE).write_text(
        json.dumps([
            {"detected": True, "gap_type": "missing_implementation",
             "description": "缺少持久化实现", "recommended_action": "INSERT_TASK",
             "confidence": 0.8, "timestamp": "2026-08-16T00:00:00+00:00"},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    (pd / EXTR.VALIDATION_RESULT_FILE).write_text(
        json.dumps({"success": False, "tests_total": 4, "tests_passed": 3,
                    "tests_failed": 1, "errors": ["登录测试失败"], "project": "demo"}),
        encoding="utf-8",
    )
    return ws


# ================================================================== 1. ExperienceRecord 模型

class TestExperienceRecord:
    def test_types_has_six(self):
        assert len(EXP.TYPES) == 6

    def test_types_include_success(self):
        assert EXP.SUCCESS_PATTERN in EXP.TYPES

    def test_types_include_failure(self):
        assert EXP.FAILURE_PATTERN in EXP.TYPES

    def test_types_include_debug(self):
        assert EXP.DEBUG_EXPERIENCE in EXP.TYPES

    def test_types_include_planning(self):
        assert EXP.PLANNING_EXPERIENCE in EXP.TYPES

    def test_types_include_agent(self):
        assert EXP.AGENT_EXPERIENCE in EXP.TYPES

    def test_types_include_user_feedback(self):
        assert EXP.USER_FEEDBACK in EXP.TYPES

    def test_defaults(self):
        r = EXP.ExperienceRecord()
        assert r.id.startswith("exp-")
        assert r.project == "" and r.task == "" and r.agent == ""
        assert r.success is True

    def test_to_dict_fields(self):
        r = _record()
        d = r.to_dict()
        for key in ("id", "type", "project", "task", "agent", "role", "context",
                    "problem", "action", "result", "success", "confidence",
                    "source", "created_at"):
            assert key in d

    def test_from_dict_roundtrip(self):
        r = _record()
        r2 = EXP.ExperienceRecord.from_dict(r.to_dict())
        assert r2.to_dict() == r.to_dict()

    def test_from_dict_unknown_type_raises(self):
        import pytest
        with pytest.raises(ValueError):
            EXP.ExperienceRecord.from_dict({"type": "NOT_A_TYPE"})

    def test_from_dict_non_dict_raises(self):
        import pytest
        with pytest.raises(ValueError):
            EXP.ExperienceRecord.from_dict("nope")

    def test_from_dict_missing_type_defaults(self):
        r = EXP.ExperienceRecord.from_dict({"problem": "x"})
        assert r.type == EXP.SUCCESS_PATTERN

    def test_confidence_invalid_coerced(self):
        r = EXP.ExperienceRecord.from_dict(
            {"type": EXP.SUCCESS_PATTERN, "confidence": "abc"})
        assert r.confidence == 0.5

    def test_confidence_clamped_high(self):
        r = EXP.ExperienceRecord.from_dict(
            {"type": EXP.SUCCESS_PATTERN, "confidence": 3.0})
        assert r.confidence == 1.0

    def test_confidence_clamped_low(self):
        r = EXP.ExperienceRecord.from_dict(
            {"type": EXP.SUCCESS_PATTERN, "confidence": -1.0})
        assert r.confidence == 0.0

    def test_id_unique_by_default(self):
        assert _record().id != _record().id

    def test_make_record_id_deterministic(self):
        a = EXP.make_record_id("execution_records", "demo", "t", "p", "a", "r")
        b = EXP.make_record_id("execution_records", "demo", "t", "p", "a", "r")
        assert a == b and a.startswith("exp-")

    def test_ensure_type_valid(self):
        assert EXP.ensure_type(EXP.DEBUG_EXPERIENCE) == EXP.DEBUG_EXPERIENCE

    def test_ensure_type_invalid_raises(self):
        import pytest
        with pytest.raises(ValueError):
            EXP.ensure_type("bogus")


# ================================================================== 2. ExperienceStore

class TestExperienceStore:
    def test_add_persists_file(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "memory" / "experience_store.json")
        store.add(_record())
        assert (tmp_path / "memory" / "experience_store.json").is_file()

    def test_add_returns_record(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "s.json")
        r = store.add(_record())
        assert r.id

    def test_records_all(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "s.json")
        store.add(_record())
        store.add(_record(type=EXP.SUCCESS_PATTERN, success=True))
        assert len(store.records()) == 2

    def test_records_type_filter(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "s.json")
        store.add(_record())
        store.add(_record(type=EXP.SUCCESS_PATTERN, success=True))
        assert len(store.records(type=EXP.SUCCESS_PATTERN)) == 1

    def test_records_project_filter(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "s.json")
        store.add(_record(project="demo"))
        store.add(_record(project="other"))
        assert [r.project for r in store.records(project="demo")] == ["demo"]

    def test_records_both_filters(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "s.json")
        store.add(_record(project="demo", type=EXP.FAILURE_PATTERN))
        store.add(_record(project="other", type=EXP.FAILURE_PATTERN))
        assert len(store.records(project="demo", type=EXP.FAILURE_PATTERN)) == 1

    def test_dedupe_by_id(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "s.json")
        r = _record()
        store.add(r)
        store.add(r)  # 同 id → 覆盖不重复
        assert len(store.records()) == 1

    def test_add_invalid_type_raises(self, tmp_path):
        import pytest
        store = STORE.ExperienceStore(tmp_path / "s.json")
        with pytest.raises(ValueError):
            store.add({"type": "BAD", "problem": "x"})

    def test_stats_total(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "s.json")
        store.add(_record())
        store.add(_record(type=EXP.SUCCESS_PATTERN, success=True))
        assert store.stats()["total"] == 2

    def test_stats_by_type(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "s.json")
        store.add(_record())
        store.add(_record(type=EXP.SUCCESS_PATTERN, success=True))
        assert store.stats()["by_type"][EXP.FAILURE_PATTERN] == 1
        assert store.stats()["by_type"][EXP.SUCCESS_PATTERN] == 1

    def test_stats_by_success(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "s.json")
        store.add(_record())
        store.add(_record(type=EXP.SUCCESS_PATTERN, success=True))
        s = store.stats()["by_success"]
        assert s["success"] == 1 and s["failed"] == 1

    def test_stats_by_agent(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "s.json")
        store.add(_record(agent="backend-1"))
        store.add(_record(agent="backend-1"))
        assert store.stats()["by_agent"]["backend-1"] == 2

    def test_load_missing_file_empty(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "nope.json")
        assert store.records() == []

    def test_load_corrupt_file_empty(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text("not json", encoding="utf-8")
        store = STORE.ExperienceStore(p)
        assert store.records() == []

    def test_save_creates_parent_dirs(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "a" / "b" / "s.json")
        store.add(_record())
        assert (tmp_path / "a" / "b" / "s.json").is_file()

    def test_from_workspace_path(self, tmp_path):
        store = STORE.ExperienceStore.from_workspace(tmp_path)
        assert store.path == tmp_path / "memory" / "experience_store.json"

    def test_get_by_id(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "s.json")
        r = store.add(_record())
        assert store.get(r.id) is not None
        assert store.get("missing") is None

    def test_add_all(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "s.json")
        n = store.add_all([_record(), _record(type=EXP.SUCCESS_PATTERN, success=True)])
        assert n == 2 and len(store.records()) == 2

    def test_add_all_skips_invalid(self, tmp_path):
        store = STORE.ExperienceStore(tmp_path / "s.json")
        n = store.add_all([_record(), {"type": "BAD"}])
        assert n == 1 and len(store.records()) == 1


# ================================================================== 3. ExperienceExtractor

class TestExtractionRecords:
    def test_failed_to_failure_pattern(self):
        out = EXTR.ExperienceExtractor.extract_from_records(
            [{"task": "登录", "result": "failed", "error": "boom"}])
        assert out[0].type == EXP.FAILURE_PATTERN
        assert out[0].success is False

    def test_failure_problem_is_error(self):
        out = EXTR.ExperienceExtractor.extract_from_records(
            [{"task": "登录", "result": "failed", "error": "boom"}])
        assert out[0].problem == "boom"

    def test_success_to_success_pattern(self):
        out = EXTR.ExperienceExtractor.extract_from_records(
            [{"task": "数据库", "result": "success"}])
        assert out[0].type == EXP.SUCCESS_PATTERN
        assert out[0].success is True

    def test_records_empty(self):
        assert EXTR.ExperienceExtractor.extract_from_records([]) == []

    def test_records_non_dict_skipped(self):
        out = EXTR.ExperienceExtractor.extract_from_records([{"task": "a", "result": "failed"}, "junk"])
        assert len(out) == 1

    def test_records_agent_captured(self):
        out = EXTR.ExperienceExtractor.extract_from_records(
            [{"task": "a", "agent": "backend-1", "result": "failed", "error": "e"}])
        assert out[0].agent == "backend-1"

    def test_records_context(self):
        out = EXTR.ExperienceExtractor.extract_from_records(
            [{"intent": "run_task", "task": "登录", "result": "failed", "error": "e"}])
        assert "登录" in out[0].context

    def test_records_deterministic_ids(self):
        recs = [{"task": "登录", "result": "failed", "error": "e"}]
        a = EXTR.ExperienceExtractor.extract_from_records(recs)[0].id
        b = EXTR.ExperienceExtractor.extract_from_records(recs)[0].id
        assert a == b


class TestExtractionRepairs:
    def test_repair_to_debug_experience(self):
        out = EXTR.ExperienceExtractor.extract_from_repairs(
            [{"failure_reason": "缺密钥", "status": "completed", "original_task_name": "登录"}])
        assert out[0].type == EXP.DEBUG_EXPERIENCE

    def test_repair_problem_is_failure_reason(self):
        out = EXTR.ExperienceExtractor.extract_from_repairs(
            [{"failure_reason": "缺密钥", "status": "pending"}])
        assert out[0].problem == "缺密钥"

    def test_repair_completed_success(self):
        out = EXTR.ExperienceExtractor.extract_from_repairs(
            [{"failure_reason": "x", "status": "completed"}])
        assert out[0].success is True

    def test_repair_failed_status(self):
        out = EXTR.ExperienceExtractor.extract_from_repairs(
            [{"failure_reason": "x", "status": "failed"}])
        assert out[0].success is False

    def test_repairs_empty(self):
        assert EXTR.ExperienceExtractor.extract_from_repairs([]) == []


class TestExtractionReplanning:
    def test_replanning_to_planning_experience(self):
        out = EXTR.ExperienceExtractor.extract_from_replanning(
            [{"decision": "INSERT_TASK", "reason": "计划缺口", "new_tasks": []}])
        assert out[0].type == EXP.PLANNING_EXPERIENCE

    def test_replanning_problem_is_reason(self):
        out = EXTR.ExperienceExtractor.extract_from_replanning(
            [{"decision": "INSERT_TASK", "reason": "计划缺任务"}])
        assert out[0].problem == "计划缺任务"

    def test_replanning_action_includes_new_task(self):
        out = EXTR.ExperienceExtractor.extract_from_replanning(
            [{"decision": "INSERT_TASK", "reason": "r",
              "new_tasks": [{"id": "T005", "name": "持久化"}]}])
        assert "T005" in out[0].action

    def test_replanning_empty(self):
        assert EXTR.ExperienceExtractor.extract_from_replanning([]) == []


class TestExtractionGaps:
    def test_gap_to_planning_experience(self):
        out = EXTR.ExperienceExtractor.extract_from_gaps(
            [{"detected": True, "gap_type": "missing_implementation",
              "description": "缺持久化", "recommended_action": "INSERT_TASK"}])
        assert out[0].type == EXP.PLANNING_EXPERIENCE

    def test_gap_problem_is_description(self):
        out = EXTR.ExperienceExtractor.extract_from_gaps(
            [{"detected": True, "gap_type": "x", "description": "缺持久化实现"}])
        assert out[0].problem == "缺持久化实现"

    def test_gap_action_is_recommended(self):
        out = EXTR.ExperienceExtractor.extract_from_gaps(
            [{"detected": True, "gap_type": "x", "recommended_action": "INSERT_TASK"}])
        assert "INSERT_TASK" in out[0].action

    def test_gap_detected_success_false(self):
        out = EXTR.ExperienceExtractor.extract_from_gaps(
            [{"detected": True, "gap_type": "x"}])
        assert out[0].success is False

    def test_gap_not_detected_success_true(self):
        out = EXTR.ExperienceExtractor.extract_from_gaps(
            [{"detected": False, "gap_type": "x"}])
        assert out[0].success is True

    def test_gap_confidence_passthrough(self):
        out = EXTR.ExperienceExtractor.extract_from_gaps(
            [{"detected": True, "gap_type": "x", "confidence": 0.8}])
        assert out[0].confidence == 0.8

    def test_gaps_empty(self):
        assert EXTR.ExperienceExtractor.extract_from_gaps([]) == []


class TestExtractionValidation:
    def test_validation_failed_to_debug(self):
        out = EXTR.ExperienceExtractor.extract_from_validation(
            [{"success": False, "errors": ["登录测试失败"]}])
        assert out[0].type == EXP.DEBUG_EXPERIENCE

    def test_validation_problem_includes_error(self):
        out = EXTR.ExperienceExtractor.extract_from_validation(
            [{"success": False, "errors": ["登录测试失败"]}])
        assert "登录测试失败" in out[0].problem

    def test_validation_success_skipped(self):
        out = EXTR.ExperienceExtractor.extract_from_validation(
            [{"success": True, "tests_passed": 4}])
        assert out == []


class TestExtractionAll:
    def test_extract_all_aggregates_sources(self, tmp_path):
        out = EXTR.ExperienceExtractor.extract_all(_fixture_workspace(tmp_path))
        # 2 exec + 1 repair + 1 replanning + 1 gap + 1 validation = 6
        assert len(out) == 6

    def test_extract_all_types(self, tmp_path):
        out = EXTR.ExperienceExtractor.extract_all(_fixture_workspace(tmp_path))
        types = {r.type for r in out}
        assert EXP.FAILURE_PATTERN in types
        assert EXP.SUCCESS_PATTERN in types
        assert EXP.DEBUG_EXPERIENCE in types
        assert EXP.PLANNING_EXPERIENCE in types

    def test_extract_all_project_annotation(self, tmp_path):
        out = EXTR.ExperienceExtractor.extract_all(_fixture_workspace(tmp_path))
        project_records = [r for r in out if r.project == "demo"]
        assert len(project_records) == 4  # repair + replanning + gap + validation

    def test_extract_all_empty_workspace(self, tmp_path):
        ws = tmp_path / "empty"
        ws.mkdir()
        assert EXTR.ExperienceExtractor.extract_all(ws) == []

    def test_extract_all_missing_files_fail_safe(self, tmp_path):
        ws = tmp_path / "ws2"
        (ws / "exec").mkdir(parents=True)
        (ws / "exec" / EXTR.EXECUTION_RECORDS_FILE).write_text("corrupt!!", encoding="utf-8")
        assert EXTR.ExperienceExtractor.extract_all(ws) == []

    def test_extract_all_idempotent(self, tmp_path):
        ws = _fixture_workspace(tmp_path)
        a = [r.id for r in EXTR.ExperienceExtractor.extract_all(ws)]
        b = [r.id for r in EXTR.ExperienceExtractor.extract_all(ws)]
        assert a == b


# ================================================================== 4. PatternLearner + LearningEngine

class TestPatternLearner:
    def test_learn_empty(self):
        assert LE.PatternLearner().learn([]) == []

    def test_learn_groups_by_topic(self):
        records = [
            _record(problem="数据库设计不足"),
            _record(problem="缺少数据库索引"),
        ]
        patterns = LE.PatternLearner().learn(records)
        assert any(p.pattern_id == "database_pattern" for p in patterns)

    def test_learn_pattern_fields(self):
        patterns = LE.PatternLearner().learn([_record()])
        p = patterns[0]
        assert p.pattern_id and p.name and p.description
        assert isinstance(p.success_rate, float)
        assert isinstance(p.count, int)
        assert 0 <= p.confidence <= 1

    def test_learn_success_rate(self):
        patterns = LE.PatternLearner().learn([
            _record(problem="登录失败", success=False),
            _record(problem="登录失败", success=True),
        ])
        p = next(p for p in patterns if p.pattern_id == "auth_pattern")
        assert p.success_rate == 0.5

    def test_learn_confidence_grows_with_count(self):
        learner = LE.PatternLearner()
        one = learner.learn([_record()])[0].confidence
        three = learner.learn([_record(), _record(), _record()])[0].confidence
        assert three > one

    def test_learn_confidence_caps(self):
        records = [_record() for _ in range(20)]
        patterns = LE.PatternLearner().learn(records)
        assert all(p.confidence <= 0.95 for p in patterns)

    def test_learn_sorted_by_confidence(self):
        records = [_record() for _ in range(5)] + [_record(problem="数据库x")]
        patterns = LE.PatternLearner().learn(records)
        confs = [p.confidence for p in patterns]
        assert confs == sorted(confs, reverse=True)

    def test_learn_agent_fields(self):
        profiles = LE.PatternLearner().learn_agent([_record()])
        p = profiles[0]
        assert p.agent_id == "backend-1"
        assert p.total_tasks == 1 and p.success_count == 0
        assert p.success_rate == 0.0

    def test_learn_agent_success_rate(self):
        records = [
            _record(success=False),
            _record(success=True, result="success"),
        ]
        profiles = LE.PatternLearner().learn_agent(records)
        assert profiles[0].success_rate == 0.5

    def test_learn_agent_common_problems(self):
        records = [
            _record(problem="缺密钥"),
            _record(problem="缺密钥"),
            _record(problem="超时"),
        ]
        profiles = LE.PatternLearner().learn_agent(records)
        assert "缺密钥" in profiles[0].common_problems

    def test_learn_agent_best_domains(self):
        records = [
            _record(problem="数据库设计", success=True),
            _record(problem="登录失败", success=False),
        ]
        profiles = LE.PatternLearner().learn_agent(records)
        assert "database" in profiles[0].best_domains

    def test_learn_agent_role(self):
        profiles = LE.PatternLearner().learn_agent([_record(role="Backend Engineer")])
        assert profiles[0].role == "Backend Engineer"

    def test_learn_agent_empty(self):
        assert LE.PatternLearner().learn_agent([]) == []


class TestLearningEngine:
    def test_run_result_fields(self, tmp_path):
        result = LE.LearningEngine().run(_fixture_workspace(tmp_path))
        assert result.extracted_count == 6
        assert isinstance(result.patterns, list)
        assert isinstance(result.agent_profiles, list)
        assert isinstance(result.learned_items, list)

    def test_run_stores_records(self, tmp_path):
        ws = _fixture_workspace(tmp_path)
        engine = LE.LearningEngine(workspace=ws)
        engine.run(ws)
        assert len(engine.store.records()) == 6

    def test_run_writes_trace(self, tmp_path):
        ws = _fixture_workspace(tmp_path)
        LE.LearningEngine(workspace=ws).run(ws)
        trace = TRACE.LearningTrace(ws)
        assert len(trace.records()) == 1

    def test_run_empty_workspace(self, tmp_path):
        ws = tmp_path / "empty"
        ws.mkdir()
        result = LE.LearningEngine().run(ws)
        assert result.extracted_count == 0

    def test_run_idempotent_store(self, tmp_path):
        ws = _fixture_workspace(tmp_path)
        engine = LE.LearningEngine(workspace=ws)
        engine.run(ws)
        engine.run(ws)
        assert len(engine.store.records()) == 6  # 去重, 不翻倍

    def test_run_patterns_non_empty(self, tmp_path):
        result = LE.LearningEngine().run(_fixture_workspace(tmp_path))
        assert result.patterns
        assert any(p["pattern_id"].endswith("_pattern") for p in result.patterns)


# ================================================================== 5. ExperienceRetriever

class TestRetrieverSearch:
    def test_search_keyword_match(self):
        retriever = RET.ExperienceRetriever(records=[_record()])
        hits = retriever.search("api key")
        assert len(hits) == 1

    def test_search_no_match(self):
        retriever = RET.ExperienceRetriever(records=[_record()])
        assert retriever.search("不存在的关键词xyz") == []

    def test_search_type_filter(self):
        records = [_record(), _record(type=EXP.SUCCESS_PATTERN, success=True)]
        retriever = RET.ExperienceRetriever(records=records)
        hits = retriever.search("", type=EXP.SUCCESS_PATTERN)
        assert len(hits) == 1 and hits[0].type == EXP.SUCCESS_PATTERN

    def test_search_project_filter(self):
        records = [_record(project="demo"), _record(project="other")]
        retriever = RET.ExperienceRetriever(records=records)
        assert len(retriever.search("", project="demo")) == 1

    def test_search_confidence_sort(self):
        records = [
            _record(problem="低置信", confidence=0.3),
            _record(problem="高置信", confidence=0.9),
        ]
        retriever = RET.ExperienceRetriever(records=records)
        hits = retriever.search("")
        assert hits[0].confidence >= hits[1].confidence

    def test_search_empty_query_returns_all(self):
        retriever = RET.ExperienceRetriever(records=[_record(), _record()])
        assert len(retriever.search("")) == 2

    def test_search_empty_store(self):
        retriever = RET.ExperienceRetriever(records=[])
        assert retriever.search("x") == []

    def test_search_created_at_tiebreak(self):
        records = [
            _record(problem="旧", created_at="2026-01-01T00:00:00+00:00"),
            _record(problem="新", created_at="2026-02-01T00:00:00+00:00"),
        ]
        retriever = RET.ExperienceRetriever(records=records)
        hits = retriever.search("")
        assert hits[0].created_at >= hits[1].created_at


class TestRetrieverSimilar:
    def test_similar_projects(self):
        records = [
            _record(project="台球项目", problem="台球计分数据库设计不足"),
            _record(project="台球项目", problem="台球排行榜接口失败"),
        ]
        retriever = RET.ExperienceRetriever(records=records)
        similar = retriever.similar_projects(["台球"])
        assert similar and similar[0]["project"] == "台球项目"
        assert similar[0]["record_count"] == 2

    def test_similar_projects_failure_count(self):
        records = [
            _record(project="demo", problem="数据库失败", success=False),
            _record(project="demo", problem="数据库成功", success=True),
        ]
        retriever = RET.ExperienceRetriever(records=records)
        similar = retriever.similar_projects(["数据库"])
        assert similar[0]["failure_count"] == 1

    def test_similar_projects_empty_features(self):
        retriever = RET.ExperienceRetriever(records=[_record()])
        assert retriever.similar_projects([]) == []

    def test_similar_projects_no_match(self):
        retriever = RET.ExperienceRetriever(records=[_record()])
        assert retriever.similar_projects(["找不到"]) == []


# ================================================================== 6. Recommender

class TestRecommender:
    def test_planning_reminder(self):
        records = [_record(project="demo", problem="数据库设计不足", success=False)]
        recommender = REC.Recommender(RET.ExperienceRetriever(records=records))
        reminders = recommender.recommend_for_planning(["数据库"])
        assert reminders and "demo" in reminders[0]

    def test_planning_reminder_advice(self):
        records = [_record(project="demo", problem="数据库设计不足", success=False)]
        recommender = REC.Recommender(RET.ExperienceRetriever(records=records))
        assert "建议" in recommender.recommend_for_planning(["数据库"])[0]

    def test_planning_no_history_fallback(self):
        recommender = REC.Recommender(RET.ExperienceRetriever(records=[]))
        reminders = recommender.recommend_for_planning(["数据库"])
        assert reminders and "暂无" in reminders[0]

    def test_debug_suggestion(self):
        records = [
            _record(type=EXP.DEBUG_EXPERIENCE, problem="登录测试失败",
                    action="验证重跑", success=False),
        ]
        recommender = REC.Recommender(RET.ExperienceRetriever(records=records))
        suggestions = recommender.recommend_for_debug("登录")
        assert suggestions and "历史方案" in suggestions[0]

    def test_debug_suggestion_contains_action(self):
        records = [
            _record(type=EXP.DEBUG_EXPERIENCE, problem="登录失败",
                    action="补充密钥配置", success=True),
        ]
        recommender = REC.Recommender(RET.ExperienceRetriever(records=records))
        assert "补充密钥配置" in recommender.recommend_for_debug("登录")[0]

    def test_debug_no_history_fallback(self):
        recommender = REC.Recommender(RET.ExperienceRetriever(records=[]))
        assert "暂无" in recommender.recommend_for_debug("登录")[0]


# ================================================================== 7. LearningTrace

class TestLearningTrace:
    def test_record_writes_file(self, tmp_path):
        trace = TRACE.LearningTrace(tmp_path)
        trace.record("test", 1, 0.5, "impact")
        assert (tmp_path / "memory" / "learning_trace.json").is_file()

    def test_record_returns_entry(self, tmp_path):
        trace = TRACE.LearningTrace(tmp_path)
        entry = trace.record("test", 2, 0.6, "impact")
        assert entry["source"] == "test" and entry["learned"] == 2

    def test_record_entry_fields(self, tmp_path):
        trace = TRACE.LearningTrace(tmp_path)
        entry = trace.record("test", 1, 0.5, "impact", {"k": "v"})
        assert entry["trace_id"].startswith("trace-")
        assert entry["confidence"] == 0.5
        assert entry["details"] == {"k": "v"}

    def test_records_append(self, tmp_path):
        trace = TRACE.LearningTrace(tmp_path)
        trace.record("a", 1, 0.5, "i")
        trace.record("b", 2, 0.6, "i")
        assert len(trace.records()) == 2

    def test_records_missing_file(self, tmp_path):
        trace = TRACE.LearningTrace(tmp_path)
        assert trace.records() == []

    def test_records_corrupt_file(self, tmp_path):
        p = tmp_path / "memory" / "learning_trace.json"
        p.parent.mkdir(parents=True)
        p.write_text("corrupt", encoding="utf-8")
        assert TRACE.LearningTrace(tmp_path).records() == []
