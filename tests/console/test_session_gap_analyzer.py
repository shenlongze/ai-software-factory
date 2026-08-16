"""S10-061 批次 A — GapAnalyzer 模型层测试套件。

覆盖: 9 种 gap_type 检测 / 无 gap / evidence / severity / confidence /
source_task_id / duplicate_of / recommended_action / 信号优先级 /
词边界防误报 / gap_analysis.json 落盘 (append, 失败安全) / 重复检测。

装配: tmp_path + fixtures; 禁真实 LLM/网络 (纯 deterministic 规则)。
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

GA = import_module("factory-console.session.gap_analyzer")


def _analyzer(tmp_path: Path) -> "GA.GapAnalyzer":
    return GA.GapAnalyzer(file=tmp_path / "gap_analysis.json")


def _gap(tmp_path: Path, **kwargs) -> "GA.GapAnalysis":
    return _analyzer(tmp_path).analyze(**kwargs)


# ================================================================== 1. 结构


class TestGapAnalysisStructure:
    def test_all_fields_present(self, tmp_path):
        g = _gap(tmp_path, validation={"success": False}, task={"id": "T001"})
        for f in (
            "detected", "gap_type", "description", "evidence", "severity",
            "source_task_id", "confidence", "duplicate_of",
            "recommended_action", "reason",
        ):
            assert hasattr(g, f), f"GapAnalysis 缺字段: {f}"

    def test_defaults(self):
        g = GA.GapAnalysis()
        assert g.detected is False
        assert g.gap_type == ""
        assert g.severity == "low"
        assert g.confidence == 0.0
        assert g.duplicate_of is None
        assert g.recommended_action == "NO_ACTION"

    def test_to_dict_all_keys(self, tmp_path):
        g = _gap(tmp_path, validation={"success": False}, task={"id": "T001"})
        d = g.to_dict()
        for k in (
            "detected", "gap_type", "description", "evidence", "severity",
            "source_task_id", "confidence", "duplicate_of",
            "recommended_action", "reason", "timestamp",
        ):
            assert k in d

    def test_from_dict_roundtrip(self, tmp_path):
        g = _gap(tmp_path, validation={"success": False}, task={"id": "T001"})
        g2 = GA.GapAnalysis.from_dict(g.to_dict())
        assert g2.to_dict() == g.to_dict()

    def test_from_dict_missing_keys_fail_safe(self):
        g = GA.GapAnalysis.from_dict({"gap_type": "missing_test"})
        assert g.gap_type == "missing_test"
        assert g.detected is False
        assert g.severity == "low"
        assert g.recommended_action == "NO_ACTION"

    def test_from_dict_non_dict(self):
        g = GA.GapAnalysis.from_dict("nonsense")
        assert g.detected is False
        assert g.gap_type == ""

    def test_from_dict_invalid_gap_type_normalized(self):
        g = GA.GapAnalysis.from_dict({"gap_type": "banana"})
        assert g.gap_type == "unknown"

    def test_from_dict_invalid_action_normalized(self):
        g = GA.GapAnalysis.from_dict({"recommended_action": "EXPLODE"})
        assert g.recommended_action == "NO_ACTION"

    def test_from_dict_invalid_severity_normalized(self):
        g = GA.GapAnalysis.from_dict({"severity": "apocalyptic"})
        assert g.severity == "low"

    def test_to_dict_fills_timestamp(self):
        g = GA.GapAnalysis().to_dict()
        assert g["timestamp"]

    def test_evidence_serialized_as_list(self, tmp_path):
        g = _gap(tmp_path, agent_output="missing test", task={"id": "T001"})
        assert isinstance(g.to_dict()["evidence"], list)
        assert all(isinstance(e, str) for e in g.to_dict()["evidence"])


# ================================================================== 2. 9 种 gap_type 检测


class TestGapTypes:
    def test_validation_failure_detected(self, tmp_path):
        g = _gap(tmp_path, validation={"success": False}, task={"id": "T001"})
        assert g.detected is True
        assert g.gap_type == "validation_failure"

    def test_missing_test_detected(self, tmp_path):
        g = _gap(tmp_path, agent_output="missing test coverage", task={"id": "T1"})
        assert g.gap_type == "missing_test"

    def test_missing_implementation_detected(self, tmp_path):
        g = _gap(tmp_path, agent_output="needs persistence layer", task={"id": "T1"})
        assert g.gap_type == "missing_implementation"

    def test_missing_requirement_detected(self, tmp_path):
        g = _gap(tmp_path, agent_output="requirement changed", task={"id": "T1"})
        assert g.gap_type == "missing_requirement"

    def test_dependency_gap_detected(self, tmp_path):
        g = _gap(tmp_path, agent_output="missing dependency", task={"id": "T1"})
        assert g.gap_type == "dependency_gap"

    def test_integration_gap_detected(self, tmp_path):
        g = _gap(tmp_path, agent_output="needs integration with api", task={"id": "T1"})
        assert g.gap_type == "integration_gap"

    def test_ui_gap_detected(self, tmp_path):
        g = _gap(tmp_path, agent_output="ui missing", task={"id": "T1"})
        assert g.gap_type == "ui_gap"

    def test_architecture_gap_detected(self, tmp_path):
        g = _gap(tmp_path, agent_output="architecture issue", task={"id": "T1"})
        assert g.gap_type == "architecture_gap"

    def test_unknown_detected_on_failure_no_signal(self, tmp_path):
        g = _gap(
            tmp_path,
            failures=[{"task_id": "T9", "name": "x", "error": "boom"}],
        )
        assert g.detected is True
        assert g.gap_type == "unknown"

    def test_no_gap_not_detected(self, tmp_path):
        g = _gap(tmp_path)
        assert g.detected is False
        assert g.gap_type == ""
        assert g.recommended_action == "NO_ACTION"

    def test_gap_types_enum_has_9(self):
        assert len(GA.GapAnalyzer.GAP_TYPES) == 9
        for t in (
            "missing_requirement", "missing_implementation", "missing_test",
            "validation_failure", "dependency_gap", "integration_gap",
            "architecture_gap", "ui_gap", "unknown",
        ):
            assert t in GA.GapAnalyzer.GAP_TYPES

    def test_actions_enum_has_6(self):
        for a in (
            "NO_ACTION", "REPAIR", "MODIFY_TASK", "INSERT_TASK",
            "BLOCK", "REQUEST_REVIEW",
        ):
            assert a in GA.GapAnalyzer.ACTIONS


# ================================================================== 3. 中文信号


class TestChineseMarkers:
    def test_chinese_missing_test(self, tmp_path):
        g = _gap(tmp_path, agent_output="测试缺失", task={"id": "T1"})
        assert g.gap_type == "missing_test"

    def test_chinese_missing_implementation(self, tmp_path):
        g = _gap(tmp_path, agent_output="缺少持久化", task={"id": "T1"})
        assert g.gap_type == "missing_implementation"

    def test_chinese_missing_requirement(self, tmp_path):
        g = _gap(tmp_path, agent_output="需求变更了", task={"id": "T1"})
        assert g.gap_type == "missing_requirement"

    def test_chinese_dependency(self, tmp_path):
        g = _gap(tmp_path, agent_output="依赖缺失", task={"id": "T1"})
        assert g.gap_type == "dependency_gap"

    def test_chinese_integration(self, tmp_path):
        g = _gap(tmp_path, agent_output="需要集成联调", task={"id": "T1"})
        assert g.gap_type == "integration_gap"

    def test_chinese_ui(self, tmp_path):
        g = _gap(tmp_path, agent_output="界面缺失", task={"id": "T1"})
        assert g.gap_type == "ui_gap"

    def test_chinese_architecture(self, tmp_path):
        g = _gap(tmp_path, agent_output="架构有缺陷", task={"id": "T1"})
        assert g.gap_type == "architecture_gap"


# ================================================================== 4. 信号优先级


class TestSignalPriority:
    def test_validation_failure_wins_over_markers(self, tmp_path):
        g = _gap(
            tmp_path,
            validation={"success": False, "errors": ["e"]},
            agent_output="missing test and persistence",
            task={"id": "T1"},
        )
        assert g.gap_type == "validation_failure"

    def test_missing_test_before_requirement(self, tmp_path):
        g = _gap(tmp_path, agent_output="requirement ok but missing test")
        assert g.gap_type == "missing_test"

    def test_dependency_before_ui(self, tmp_path):
        g = _gap(tmp_path, agent_output="ui 界面需要 dependency")
        assert g.gap_type == "dependency_gap"

    def test_ui_word_boundary_no_false_positive(self, tmp_path):
        g = _gap(tmp_path, agent_output="build the guide quickly")
        assert g.detected is False

    def test_test_word_boundary_no_false_positive(self, tmp_path):
        g = _gap(tmp_path, agent_output="latest contest result")
        assert g.detected is False

    def test_ui_before_architecture_conflict(self, tmp_path):
        # 规则顺序: ui 先于 architecture → 同时命中时 ui_gap
        g = _gap(tmp_path, agent_output="架构问题但 ui 也要改")
        assert g.gap_type == "ui_gap"


# ================================================================== 5. severity / confidence


class TestSeverityConfidence:
    def test_severity_per_type(self, tmp_path):
        cases = {
            "validation_failure": "high",
            "missing_implementation": "high",
            "dependency_gap": "high",
            "architecture_gap": "critical",
            "missing_test": "medium",
            "missing_requirement": "medium",
            "integration_gap": "medium",
            "ui_gap": "low",
            "unknown": "medium",
        }
        for gtype, sev in cases.items():
            if gtype == "validation_failure":
                g = _gap(tmp_path, validation={"success": False}, task={"id": "T1"})
            elif gtype == "unknown":
                g = _gap(tmp_path, failures=[{"task_id": "T9", "error": "x"}])
            else:
                marker = {
                    "missing_test": "missing test",
                    "missing_implementation": "persistence",
                    "missing_requirement": "requirement",
                    "dependency_gap": "dependency",
                    "integration_gap": "integration",
                    "ui_gap": "ui",
                    "architecture_gap": "architecture",
                }[gtype]
                g = _gap(tmp_path, agent_output=marker, task={"id": "T1"})
            assert g.gap_type == gtype
            assert g.severity == sev, f"{gtype}: {g.severity} != {sev}"

    def test_confidence_boost_multiple_markers(self, tmp_path):
        g = _gap(
            tmp_path,
            agent_output="测试缺失 缺测试 没有测试",
            task={"id": "T1"},
        )
        assert g.gap_type == "missing_test"
        assert g.confidence > 0.80  # 基础 0.80 + 多信号词提升

    def test_confidence_capped(self, tmp_path):
        g = _gap(
            tmp_path,
            validation={"success": False, "errors": ["e1", "e2"]},
            agent_output="missing test 测试缺失 缺测试",
            failures=[{"task_id": "T1", "error": "x"}],
            task={"id": "T1"},
        )
        assert g.gap_type == "validation_failure"
        assert g.confidence <= 0.95

    def test_confidence_unknown_low(self, tmp_path):
        g = _gap(tmp_path, failures=[{"task_id": "T9", "error": "x"}])
        assert g.gap_type == "unknown"
        assert g.confidence < 0.5

    def test_confidence_in_range(self, tmp_path):
        for out in ("missing test", "persistence", "requirement",
                    "dependency", "integration", "ui", "architecture"):
            g = _gap(tmp_path, agent_output=out, task={"id": "T1"})
            assert 0.0 <= g.confidence <= 1.0

    def test_no_gap_confidence_zero(self, tmp_path):
        g = _gap(tmp_path)
        assert g.confidence == 0.0


# ================================================================== 6. source_task_id


class TestSourceTask:
    def test_source_from_task(self, tmp_path):
        g = _gap(tmp_path, agent_output="missing test", task={"id": "T042"})
        assert g.source_task_id == "T042"

    def test_source_from_failures(self, tmp_path):
        g = _gap(
            tmp_path,
            failures=[{"task_id": "T7", "name": "登录", "error": "x"}],
        )
        assert g.source_task_id == "T7"

    def test_source_empty_without_context(self, tmp_path):
        g = _gap(tmp_path, agent_output="missing test")
        assert g.source_task_id == ""

    def test_task_wins_over_failures(self, tmp_path):
        g = _gap(
            tmp_path,
            task={"id": "T1"},
            failures=[{"task_id": "T7", "error": "x"}],
        )
        assert g.source_task_id == "T1"


# ================================================================== 7. recommended_action


class TestRecommendedAction:
    def test_action_per_type(self, tmp_path):
        cases = {
            "validation_failure": "REPAIR",
            "missing_test": "INSERT_TASK",
            "missing_implementation": "INSERT_TASK",
            "missing_requirement": "INSERT_TASK",
            "dependency_gap": "INSERT_TASK",
            "integration_gap": "INSERT_TASK",
            "ui_gap": "INSERT_TASK",
            "architecture_gap": "REQUEST_REVIEW",
            "unknown": "REQUEST_REVIEW",
        }
        for gtype, action in cases.items():
            if gtype == "validation_failure":
                g = _gap(tmp_path, validation={"success": False}, task={"id": "T1"})
            elif gtype == "unknown":
                g = _gap(tmp_path, failures=[{"task_id": "T9", "error": "x"}])
            else:
                marker = {
                    "missing_test": "missing test",
                    "missing_implementation": "persistence",
                    "missing_requirement": "requirement",
                    "dependency_gap": "dependency",
                    "integration_gap": "integration",
                    "ui_gap": "ui",
                    "architecture_gap": "architecture",
                }[gtype]
                g = _gap(tmp_path, agent_output=marker, task={"id": "T1"})
            assert g.recommended_action == action, f"{gtype}: {g.recommended_action}"

    def test_no_gap_no_action(self, tmp_path):
        g = _gap(tmp_path)
        assert g.recommended_action == "NO_ACTION"


# ================================================================== 8. evidence


class TestEvidence:
    def test_evidence_contains_validation_error(self, tmp_path):
        g = _gap(
            tmp_path,
            validation={"success": False, "errors": ["导入失败"]},
            task={"id": "T1"},
        )
        joined = " ".join(g.evidence)
        assert "validation.success=false" in joined
        assert "导入失败" in joined

    def test_evidence_contains_marker_hit(self, tmp_path):
        g = _gap(tmp_path, agent_output="缺测试 测试缺失", task={"id": "T1"})
        joined = " ".join(g.evidence)
        assert "命中信号词" in joined

    def test_evidence_contains_failures(self, tmp_path):
        g = _gap(
            tmp_path,
            failures=[{"task_id": "T9", "name": "x", "error": "timeout"}],
        )
        joined = " ".join(g.evidence)
        assert "T9" in joined and "timeout" in joined

    def test_evidence_non_empty_for_detected_gap(self, tmp_path):
        g = _gap(tmp_path, agent_output="missing test", task={"id": "T1"})
        assert g.evidence


# ================================================================== 9. duplicate_of


class TestDuplicateOf:
    def test_duplicate_same_gap_recorded(self, tmp_path):
        a = _analyzer(tmp_path)
        g1 = a.analyze(agent_output="missing test", task={"id": "T1"})
        a.record(g1)
        g2 = a.analyze(agent_output="missing test", task={"id": "T1"})
        assert g2.duplicate_of == "T1"

    def test_no_duplicate_first_time(self, tmp_path):
        g = _gap(tmp_path, agent_output="missing test", task={"id": "T1"})
        assert g.duplicate_of is None

    def test_no_duplicate_different_source(self, tmp_path):
        a = _analyzer(tmp_path)
        a.record(a.analyze(agent_output="missing test", task={"id": "T1"}))
        g2 = a.analyze(agent_output="missing test", task={"id": "T2"})
        assert g2.duplicate_of is None

    def test_no_duplicate_different_type_same_source(self, tmp_path):
        a = _analyzer(tmp_path)
        a.record(a.analyze(agent_output="missing test", task={"id": "T1"}))
        g2 = a.analyze(agent_output="persistence", task={"id": "T1"})
        assert g2.duplicate_of is None

    def test_duplicate_from_prev_decisions(self, tmp_path):
        g = _gap(
            tmp_path,
            agent_output="missing test",
            task={"id": "T1"},
            prev_decisions=[
                {
                    "decision": "INSERT_TASK",
                    "affected_tasks": ["T1"],
                    "reason": "插入测试任务",
                }
            ],
        )
        assert g.duplicate_of == "T1"

    def test_duplicate_ignores_other_decisions(self, tmp_path):
        g = _gap(
            tmp_path,
            agent_output="missing test",
            task={"id": "T1"},
            prev_decisions=[
                {"decision": "KEEP_PLAN", "affected_tasks": ["T1"]}
            ],
        )
        assert g.duplicate_of is None

    def test_duplicate_record_reason_mentions_it(self, tmp_path):
        a = _analyzer(tmp_path)
        a.record(a.analyze(agent_output="missing test", task={"id": "T1"}))
        g2 = a.analyze(agent_output="missing test", task={"id": "T1"})
        assert "duplicate_of" in g2.reason


# ================================================================== 10. 落盘


class TestRecord:
    def test_record_appends(self, tmp_path):
        a = _analyzer(tmp_path)
        a.record(a.analyze(agent_output="missing test", task={"id": "T1"}))
        a.record(a.analyze(agent_output="persistence", task={"id": "T2"}))
        recs = a.previous_analyses()
        assert len(recs) == 2
        assert recs[0]["gap_type"] == "missing_test"
        assert recs[1]["gap_type"] == "missing_implementation"

    def test_record_returns_normalized_dict(self, tmp_path):
        a = _analyzer(tmp_path)
        g = a.analyze(validation={"success": False}, task={"id": "T1"})
        out = a.record(g)
        assert out["gap_type"] == "validation_failure"
        assert out["detected"] is True
        assert out["timestamp"]

    def test_record_writes_file(self, tmp_path):
        a = _analyzer(tmp_path)
        a.record(a.analyze(agent_output="missing test", task={"id": "T1"}))
        data = json.loads(
            (tmp_path / "gap_analysis.json").read_text(encoding="utf-8")
        )
        assert len(data) == 1
        assert data[0]["source_task_id"] == "T1"

    def test_previous_analyses_missing_file(self, tmp_path):
        assert _analyzer(tmp_path).previous_analyses() == []

    def test_previous_analyses_corrupt_file(self, tmp_path):
        f = tmp_path / "gap_analysis.json"
        f.write_text("{not json!!", encoding="utf-8")
        assert _analyzer(tmp_path).previous_analyses() == []

    def test_previous_analyses_non_list(self, tmp_path):
        f = tmp_path / "gap_analysis.json"
        f.write_text(json.dumps({"a": 1}), encoding="utf-8")
        assert _analyzer(tmp_path).previous_analyses() == []

    def test_record_fail_safe_bad_path(self, tmp_path):
        a = GA.GapAnalyzer(file=tmp_path)  # 目标是目录 → 写失败安全
        a.record(a.analyze(agent_output="missing test", task={"id": "T1"}))
        assert a.previous_analyses() == []

    def test_record_creates_parent_dirs(self, tmp_path):
        f = tmp_path / "deep" / "nested" / "gap_analysis.json"
        a = GA.GapAnalyzer(file=f)
        a.record(a.analyze(agent_output="missing test", task={"id": "T1"}))
        assert f.exists()

    def test_analyses_for_filter(self, tmp_path):
        a = _analyzer(tmp_path)
        a.record(a.analyze(agent_output="missing test", task={"id": "T1"}))
        a.record(a.analyze(agent_output="persistence", task={"id": "T2"}))
        assert len(a.analyses_for("T1")) == 1
        assert len(a.analyses_for("T2")) == 1
        assert a.analyses_for("T9") == []

    def test_file_name_constant(self):
        assert GA.GAP_ANALYSIS_FILE_NAME == "gap_analysis.json"
        assert GA.GapAnalyzer.FILE_NAME == "gap_analysis.json"

    def test_analyses_file_path(self, tmp_path):
        a = _analyzer(tmp_path)
        assert a.analyses_file() == tmp_path / "gap_analysis.json"


# ================================================================== 11. 输入容错


class TestInputTolerance:
    def test_result_agent_output_source(self, tmp_path):
        g = _gap(tmp_path, result={"agent_output": "missing test"})
        assert g.gap_type == "missing_test"

    def test_result_output_source(self, tmp_path):
        g = _gap(tmp_path, result={"output": "persistence needed"})
        assert g.gap_type == "missing_implementation"

    def test_explicit_agent_output_wins(self, tmp_path):
        g = _gap(
            tmp_path,
            agent_output="missing test",
            result={"agent_output": "persistence"},
        )
        assert g.gap_type == "missing_test"

    def test_project_workspace_artifacts_tolerated(self, tmp_path):
        g = _gap(
            tmp_path,
            project={"slug": "demo"},
            workspace={"project": "demo", "files": ["a.py"]},
            artifacts={"files": ["a.py"]},
            agent_output="missing test",
            task={"id": "T1"},
            existing_tasks=[{"id": "T1", "name": "x"}],
            dag=object(),
        )
        assert g.gap_type == "missing_test"

    def test_validation_success_true_no_gap(self, tmp_path):
        g = _gap(tmp_path, validation={"success": True})
        assert g.detected is False

    def test_validation_missing_success_key_uses_output(self, tmp_path):
        g = _gap(tmp_path, validation={"errors": ["x"]}, agent_output="missing test")
        assert g.gap_type == "missing_test"

    def test_non_dict_inputs_fail_safe(self, tmp_path):
        g = _gap(tmp_path, task="T1", validation="no", failures=["x"], result="r")
        assert g.detected is False
        assert g.recommended_action == "NO_ACTION"

    def test_unknown_requires_failures_not_just_error_output(self, tmp_path):
        # 只有 error 文本但无 failures 列表 → 无信号 → 无缺口
        g = _gap(tmp_path, agent_output="failed")
        assert g.detected is False
