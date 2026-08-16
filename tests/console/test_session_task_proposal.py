"""S10-061 批次 A — TaskProposalEngine / Validator / DuplicateDetector 测试套件。

覆盖: TaskProposal 数据模型 / 规则模板 (gap_type → 正确 proposal) /
task_id 生成不冲突 / TaskProposalValidator 12 项检查 PASS/REJECT + reason /
DuplicateDetector (normalized title / source_gap / objective 重叠) /
未知 gap → None (REQUEST_REVIEW 路径)。

装配: tmp_path + fixtures; 禁真实 LLM/网络 (纯 deterministic)。
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

TP = import_module("factory-console.session.task_proposal")


def TP_Gap(**kw) -> object:
    """GapAnalysis 鸭子对象 (避免跨模块 import 依赖 — 禁改核心)。"""
    base = dict(
        detected=True, gap_type="", source_task_id="", description="",
        confidence=0.0,
    )
    base.update(kw)
    return type("GapStub", (), base)()


def _engine() -> "TP.TaskProposalEngine":
    return TP.TaskProposalEngine()


def _proposal(**kw) -> "TP.TaskProposal":
    base = dict(
        task_id="T003",
        title="为 T002 增加测试",
        description="由 T002 的测试缺口生成",
        objective="为 T002 增加测试覆盖",
        required_role="qa",
        dependencies=["T002"],
        acceptance_criteria=["pytest 通过"],
        validation_command="pytest",
        source_gap="missing_test@T002",
        rationale="测试缺口",
        confidence=0.8,
        priority="medium",
    )
    base.update(kw)
    return TP.TaskProposal(**base)


def _existing(*ids: str) -> list[dict]:
    return [{"id": i, "name": f"任务 {i}"} for i in ids]


class _FakeDag:
    """cycle_detect 桩 (测试检查 6)。"""

    def __init__(self, cycles: set[tuple[str, str]] | None = None) -> None:
        self._cycles = cycles or set()

    def cycle_detect(self, task: str, dep: str) -> bool:
        return (task, dep) in self._cycles


# ================================================================== 1. TaskProposal


class TestTaskProposalModel:
    def test_fields_present(self):
        p = _proposal()
        for f in (
            "task_id", "title", "description", "objective", "required_role",
            "dependencies", "acceptance_criteria", "validation_command",
            "source_gap", "rationale", "confidence", "priority",
        ):
            assert hasattr(p, f), f"TaskProposal 缺字段: {f}"

    def test_defaults(self):
        p = TP.TaskProposal(
            task_id="T1", title="t", description="d", objective="o",
            required_role="qa",
        )
        assert p.dependencies == []
        assert p.acceptance_criteria == []
        assert p.validation_command == "pytest"
        assert p.priority == "medium"
        assert p.confidence == 0.0
        assert p.source_gap == ""

    def test_to_dict_all_keys(self):
        d = _proposal().to_dict()
        for k in (
            "task_id", "title", "description", "objective", "required_role",
            "dependencies", "acceptance_criteria", "validation_command",
            "source_gap", "rationale", "confidence", "priority",
        ):
            assert k in d

    def test_from_dict_roundtrip(self):
        p = _proposal()
        assert TP.TaskProposal.from_dict(p.to_dict()).to_dict() == p.to_dict()

    def test_from_dict_missing_keys_fail_safe(self):
        p = TP.TaskProposal.from_dict({"task_id": "T9"})
        assert p.task_id == "T9"
        assert p.title == ""
        assert p.required_role == ""
        assert p.validation_command == "pytest"

    def test_from_dict_non_dict(self):
        p = TP.TaskProposal.from_dict("nope")
        assert p.task_id == ""

    def test_to_dict_copies_lists(self):
        p = _proposal()
        d = p.to_dict()
        d["dependencies"].append("T999")
        assert "T999" not in p.dependencies


# ================================================================== 2. 规则模板


class TestProposeTemplates:
    def test_missing_test_proposal(self):
        gap = TP_Gap(detected=True, gap_type="missing_test",
                     source_task_id="T002", description="模块缺测试",
                     confidence=0.8)
        p = _engine().propose(gap, _existing("T001", "T002"))
        assert p is not None
        assert p.required_role == "qa"
        assert "测试" in p.objective
        assert "pytest 通过" in p.acceptance_criteria
        assert p.validation_command == "pytest"
        assert p.dependencies == ["T002"]
        assert p.task_id == "T003"

    def test_missing_implementation_proposal(self):
        gap = TP_Gap(detected=True, gap_type="missing_implementation",
                     source_task_id="T002", description="数据需要持久化",
                     confidence=0.8)
        p = _engine().propose(gap, _existing("T001", "T002"))
        assert p.required_role == "backend"
        assert "持久化" in p.objective
        for c in ("数据可保存", "重启可恢复", "pytest 通过"):
            assert c in p.acceptance_criteria
        assert p.validation_command == "pytest"
        assert p.dependencies == ["T002"]

    def test_missing_requirement_proposal(self):
        gap = TP_Gap(detected=True, gap_type="missing_requirement",
                     source_task_id="T002", description="需求不明确",
                     confidence=0.75)
        p = _engine().propose(gap, _existing("T001", "T002"))
        assert p.required_role == "pm"
        assert "需求" in p.objective
        assert "需求文档明确" in p.acceptance_criteria

    def test_ui_gap_proposal(self):
        gap = TP_Gap(detected=True, gap_type="ui_gap",
                     source_task_id="T002", description="缺界面",
                     confidence=0.7)
        p = _engine().propose(gap, _existing("T001", "T002"))
        assert p.required_role == "frontend"
        assert "界面" in p.objective
        assert p.validation_command == "flutter test"

    def test_dependency_gap_proposal(self):
        gap = TP_Gap(detected=True, gap_type="dependency_gap",
                     source_task_id="T002", description="缺依赖",
                     confidence=0.85)
        p = _engine().propose(gap, _existing("T001", "T002"))
        assert p.required_role == "backend"
        assert p.dependencies == []  # 前置能力, 不依赖 source
        assert "依赖" in p.objective

    def test_integration_gap_proposal(self):
        gap = TP_Gap(detected=True, gap_type="integration_gap",
                     source_task_id="T002", description="模块需联调",
                     confidence=0.7)
        p = _engine().propose(gap, _existing("T001", "T002"))
        assert p.required_role == "backend"
        assert "集成" in p.objective
        assert p.dependencies == ["T002"]

    def test_architecture_gap_none(self):
        gap = TP_Gap(detected=True, gap_type="architecture_gap",
                     source_task_id="T002", description="架构风险",
                     confidence=0.65)
        assert _engine().propose(gap, _existing("T001", "T002")) is None

    def test_unknown_gap_none(self):
        gap = TP_Gap(detected=True, gap_type="unknown",
                     source_task_id="T002", description="不明",
                     confidence=0.4)
        assert _engine().propose(gap, _existing("T001", "T002")) is None

    def test_validation_failure_gap_none(self):
        gap = TP_Gap(detected=True, gap_type="validation_failure",
                     source_task_id="T002", description="验证失败",
                     confidence=0.9)
        assert _engine().propose(gap, _existing("T001", "T002")) is None

    def test_detected_false_none(self):
        gap = TP_Gap(detected=False, gap_type="", source_task_id="",
                     description="", confidence=0.0)
        assert _engine().propose(gap) is None

    def test_none_gap_none(self):
        assert _engine().propose(None) is None

    def test_dict_gap_accepted(self):
        p = _engine().propose(
            {
                "detected": True,
                "gap_type": "missing_test",
                "source_task_id": "T002",
                "description": "缺测试",
                "confidence": 0.8,
            },
            _existing("T001", "T002"),
        )
        assert p is not None
        assert p.required_role == "qa"

    def test_empty_dict_gap_none(self):
        assert _engine().propose({}) is None


class TestProposalContent:
    def test_source_gap_format(self):
        gap = TP_Gap(detected=True, gap_type="missing_test",
                     source_task_id="T002", description="x", confidence=0.8)
        p = _engine().propose(gap, _existing("T001", "T002"))
        assert p.source_gap == "missing_test@T002"

    def test_source_gap_type_only_without_source(self):
        gap = TP_Gap(detected=True, gap_type="missing_test",
                     source_task_id="", description="x", confidence=0.8)
        p = _engine().propose(gap, _existing("T001"))
        assert p.source_gap == "missing_test"

    def test_title_uses_source(self):
        gap = TP_Gap(detected=True, gap_type="missing_test",
                     source_task_id="T007", description="x", confidence=0.8)
        p = _engine().propose(gap, _existing("T001"))
        assert "T007" in p.title

    def test_title_without_source_uses_placeholder(self):
        gap = TP_Gap(detected=True, gap_type="missing_test",
                     source_task_id="", description="x", confidence=0.8)
        p = _engine().propose(gap, _existing("T001"))
        assert "当前任务" in p.title

    def test_no_bogus_dependency_without_source(self):
        gap = TP_Gap(detected=True, gap_type="missing_test",
                     source_task_id="", description="x", confidence=0.8)
        p = _engine().propose(gap, _existing("T001"))
        assert p.dependencies == []

    def test_rationale_mentions_gap(self):
        gap = TP_Gap(detected=True, gap_type="missing_test",
                     source_task_id="T002", description="缺测试", confidence=0.8)
        p = _engine().propose(gap, _existing("T001", "T002"))
        assert "missing_test" in p.rationale
        assert "T002" in p.rationale

    def test_priority_per_template(self):
        cases = {
            "missing_test": "medium",
            "missing_implementation": "high",
            "missing_requirement": "high",
            "ui_gap": "medium",
            "dependency_gap": "high",
            "integration_gap": "medium",
        }
        for gtype, prio in cases.items():
            gap = TP_Gap(detected=True, gap_type=gtype,
                         source_task_id="T002", description="x", confidence=0.8)
            p = _engine().propose(gap, _existing("T001", "T002"))
            assert p.priority == prio, gtype

    def test_confidence_carried(self):
        gap = TP_Gap(detected=True, gap_type="missing_test",
                     source_task_id="T002", description="x", confidence=0.83)
        p = _engine().propose(gap, _existing("T001", "T002"))
        assert p.confidence == 0.83

    def test_description_summarized(self):
        gap = TP_Gap(detected=True, gap_type="missing_test",
                     source_task_id="T002",
                     description="很长的描述 " * 20, confidence=0.8)
        p = _engine().propose(gap, _existing("T001", "T002"))
        assert len(p.description) <= 200
        assert "…" in p.description

    def test_validation_command_from_template(self):
        gap = TP_Gap(detected=True, gap_type="ui_gap",
                     source_task_id="T002", description="x", confidence=0.7)
        p = _engine().propose(gap, _existing("T001", "T002"))
        assert p.validation_command == "flutter test"


# ================================================================== 3. task_id 生成


class TestTaskIdGeneration:
    def test_increments_from_max(self):
        eng = _engine()
        gap = TP_Gap(detected=True, gap_type="missing_test",
                     source_task_id="T002", description="x", confidence=0.8)
        p = eng.propose(gap, _existing("T001", "T002", "T003"))
        assert p.task_id == "T004"

    def test_empty_existing_starts_t001(self):
        gap = TP_Gap(detected=True, gap_type="missing_test",
                     source_task_id="", description="x", confidence=0.8)
        p = _engine().propose(gap, [])
        assert p.task_id == "T001"

    def test_no_collision_with_source(self):
        eng = _engine()
        gap = TP_Gap(detected=True, gap_type="missing_test",
                     source_task_id="T002", description="x", confidence=0.8)
        p1 = eng.propose(gap, _existing("T001", "T002"))
        gap2 = TP_Gap(detected=True, gap_type="missing_implementation",
                      source_task_id="T002", description="y", confidence=0.8)
        p2 = eng.propose(gap2, _existing("T001", "T002") + [p1.to_dict()])
        assert p2.task_id != p1.task_id

    def test_sequential_proposals_unique(self):
        eng = _engine()
        seen = set()
        existing = _existing("T001")
        for i in range(5):
            gap = TP_Gap(detected=True, gap_type="missing_test",
                         source_task_id=f"T00{i + 1}", description="x",
                         confidence=0.8)
            p = eng.propose(gap, existing)
            assert p.task_id not in seen
            seen.add(p.task_id)
            existing.append(p.to_dict())

    def test_handles_non_numeric_ids(self):
        gap = TP_Gap(detected=True, gap_type="missing_test",
                     source_task_id="alpha", description="x", confidence=0.8)
        p = _engine().propose(
            gap, [{"id": "alpha"}, {"id": "beta"}]
        )
        assert p.task_id == "T003"

    def test_handles_unpadded_ids(self):
        gap = TP_Gap(detected=True, gap_type="missing_test",
                     source_task_id="T4", description="x", confidence=0.8)
        p = _engine().propose(gap, [{"id": "T4"}, {"id": "T5"}])
        assert p.task_id == "T006"

    def test_task_id_format_t0xx(self):
        gap = TP_Gap(detected=True, gap_type="missing_test",
                     source_task_id="T002", description="x", confidence=0.8)
        p = _engine().propose(gap, _existing("T001", "T002"))
        assert p.task_id.startswith("T0")
        assert p.task_id[1:].isdigit()


# ================================================================== 4. Validator 12 项


class TestValidatorPass:
    def test_all_12_checks_pass(self):
        v = TP.TaskProposalValidator()
        r = v.validate(
            _proposal(), _existing("T001", "T002"), dag=_FakeDag(),
            replan_count=1, max_replan=5,
        )
        assert r["valid"] is True
        assert r["reasons"] == []
        assert len(r["checks"]) == 12
        assert all(c["status"] == "PASS" for c in r["checks"])

    def test_checks_include_pass_reason(self):
        v = TP.TaskProposalValidator()
        r = v.validate(_proposal(), _existing("T001", "T002"))
        assert r["checks"][0]["status"] == "PASS"
        assert "PASS" in r["checks"][0]["reason"]

    def test_accepts_dict_proposal(self):
        v = TP.TaskProposalValidator()
        r = v.validate(_proposal().to_dict(), _existing("T001", "T002"))
        assert r["valid"] is True

    def test_cycle_check_skipped_without_dag(self):
        v = TP.TaskProposalValidator()
        r = v.validate(_proposal(), _existing("T001", "T002"), dag=None)
        assert r["valid"] is True
        assert r["checks"][5]["status"] == "PASS"

    def test_replan_count_none_treated_zero(self):
        v = TP.TaskProposalValidator()
        r = v.validate(_proposal(), _existing("T001", "T002"),
                       replan_count=None, max_replan=5)
        assert r["valid"] is True


class TestValidatorReject:
    def test_reject_task_id_duplicate(self):
        r = TP.TaskProposalValidator().validate(
            _proposal(), _existing("T001", "T002", "T003")
        )
        assert r["valid"] is False
        assert any("检查1" in x for x in r["reasons"])

    def test_reject_empty_task_id(self):
        r = TP.TaskProposalValidator().validate(
            _proposal(task_id=""), _existing("T001", "T002")
        )
        assert not r["valid"]
        assert any("检查1" in x for x in r["reasons"])

    def test_reject_empty_title(self):
        r = TP.TaskProposalValidator().validate(
            _proposal(title="  "), _existing("T001", "T002")
        )
        assert not r["valid"]
        assert any("检查2" in x for x in r["reasons"])

    def test_reject_empty_description(self):
        r = TP.TaskProposalValidator().validate(
            _proposal(description=""), _existing("T001", "T002")
        )
        assert not r["valid"]
        assert any("检查3" in x for x in r["reasons"])

    def test_reject_invalid_role(self):
        r = TP.TaskProposalValidator().validate(
            _proposal(required_role="sre"), _existing("T001", "T002")
        )
        assert not r["valid"]
        assert any("检查4" in x for x in r["reasons"])

    def test_reject_missing_dependency(self):
        r = TP.TaskProposalValidator().validate(
            _proposal(dependencies=["T999"]), _existing("T001", "T002")
        )
        assert not r["valid"]
        assert any("检查5" in x for x in r["reasons"])

    def test_reject_cycle(self):
        dag = _FakeDag(cycles={("T003", "T002")})
        r = TP.TaskProposalValidator().validate(
            _proposal(task_id="T003"), _existing("T001", "T002"), dag=dag
        )
        assert not r["valid"]
        assert any("检查6" in x for x in r["reasons"])

    def test_reject_empty_acceptance(self):
        r = TP.TaskProposalValidator().validate(
            _proposal(acceptance_criteria=[]), _existing("T001", "T002")
        )
        assert not r["valid"]
        assert any("检查7" in x for x in r["reasons"])

    def test_reject_blank_acceptance(self):
        r = TP.TaskProposalValidator().validate(
            _proposal(acceptance_criteria=["", "  "]), _existing("T001", "T002")
        )
        assert not r["valid"]
        assert any("检查7" in x for x in r["reasons"])

    def test_reject_invalid_command(self):
        r = TP.TaskProposalValidator().validate(
            _proposal(validation_command="make check"), _existing("T001", "T002")
        )
        assert not r["valid"]
        assert any("检查8" in x for x in r["reasons"])

    def test_reject_duplicate_proposal(self):
        existing = _existing("T001", "T002")
        existing.append({"id": "T003", "name": "为 T002 增加测试"})
        r = TP.TaskProposalValidator().validate(
            _proposal(task_id="T004"), existing
        )
        assert not r["valid"]
        assert any("检查9" in x for x in r["reasons"])

    def test_reject_missing_source_gap(self):
        r = TP.TaskProposalValidator().validate(
            _proposal(source_gap=""), _existing("T001", "T002")
        )
        assert not r["valid"]
        assert any("检查10" in x for x in r["reasons"])

    def test_reject_low_confidence(self):
        r = TP.TaskProposalValidator().validate(
            _proposal(confidence=0.3), _existing("T001", "T002")
        )
        assert not r["valid"]
        assert any("检查11" in x for x in r["reasons"])

    def test_reject_replan_limit(self):
        r = TP.TaskProposalValidator().validate(
            _proposal(), _existing("T001", "T002"),
            replan_count=5, max_replan=5,
        )
        assert not r["valid"]
        assert any("检查12" in x for x in r["reasons"])

    def test_multiple_reasons_aggregated(self):
        r = TP.TaskProposalValidator().validate(
            _proposal(title="", required_role="sre"),
            _existing("T001", "T002"),
        )
        assert not r["valid"]
        assert len(r["reasons"]) >= 2

    def test_custom_confidence_threshold(self):
        v = TP.TaskProposalValidator(confidence_threshold=0.9)
        r = v.validate(
            _proposal(confidence=0.8), _existing("T001", "T002")
        )
        assert not r["valid"]
        assert any("检查11" in x for x in r["reasons"])


# ================================================================== 5. DuplicateDetector


class TestDuplicateDetector:
    def test_dup_normalized_title(self):
        d = TP.DuplicateDetector()
        existing = _existing("T001", "T002")
        existing.append({"id": "T003", "name": "为 T002 增加测试"})
        r = d.check(_proposal(task_id="T004"), existing)
        assert r["duplicate"] is True
        assert r["duplicate_of"] == "T003"
        assert "title" in r["reason"]

    def test_dup_title_case_punct_insensitive(self):
        d = TP.DuplicateDetector()
        existing = _existing("T001")
        existing.append({"id": "T009", "name": " 为 T002 增加测试 !!"})
        r = d.check(
            _proposal(task_id="T004", title="为 T002 增加测试"),
            existing,
        )
        assert r["duplicate"] is True

    def test_dup_source_gap(self):
        d = TP.DuplicateDetector()
        existing = _existing("T001")
        existing.append(
            {"id": "T009", "name": "别的标题", "source_gap": "missing_test@T002"}
        )
        r = d.check(_proposal(task_id="T004"), existing)
        assert r["duplicate"] is True
        assert r["duplicate_of"] == "T009"
        assert "source_gap" in r["reason"]

    def test_dup_objective_overlap(self):
        d = TP.DuplicateDetector()
        existing = _existing("T001")
        existing.append(
            {"id": "T009", "name": "别的标题",
             "objective": "为 T002 增加测试覆盖与断言"}
        )
        r = d.check(_proposal(task_id="T004"), existing)
        assert r["duplicate"] is True
        assert "objective" in r["reason"]

    def test_dup_objective_containment(self):
        d = TP.DuplicateDetector()
        existing = _existing("T001")
        existing.append(
            {"id": "T009", "name": "别的标题",
             "objective": "为 T002 增加测试覆盖"}
        )
        r = d.check(_proposal(task_id="T004"), existing)
        assert r["duplicate"] is True

    def test_no_dup_different_titles(self):
        d = TP.DuplicateDetector()
        existing = _existing("T001", "T002")
        existing.append({"id": "T003", "name": "实现登录接口"})
        r = d.check(_proposal(task_id="T004"), existing)
        assert r["duplicate"] is False
        assert r["duplicate_of"] is None

    def test_no_dup_empty_existing(self):
        d = TP.DuplicateDetector()
        r = d.check(_proposal(task_id="T004"), [])
        assert r["duplicate"] is False

    def test_skips_self(self):
        d = TP.DuplicateDetector()
        existing = _existing("T001")
        existing.append({"id": "T004", "name": "为 T002 增加测试"})
        r = d.check(_proposal(task_id="T004"), existing)
        assert r["duplicate"] is False

    def test_uses_name_field_fallback(self):
        d = TP.DuplicateDetector()
        existing = [{"id": "T001", "name": "为 T002 增加测试"}]
        r = d.check(_proposal(task_id="T004"), existing)
        assert r["duplicate"] is True

    def test_accepts_dict_proposal(self):
        d = TP.DuplicateDetector()
        existing = _existing("T001")
        existing.append({"id": "T009", "name": "为 T002 增加测试"})
        r = d.check(_proposal(task_id="T004").to_dict(), existing)
        assert r["duplicate"] is True

    def test_reason_not_duplicate(self):
        d = TP.DuplicateDetector()
        r = d.check(_proposal(task_id="T004"), _existing("T001", "T002"))
        assert r["reason"] == "未发现重复"


# ================================================================== 6. 常量


class TestConstants:
    def test_valid_roles_match_roles_module(self):
        from importlib import import_module as _im

        roles = _im("factory-console.session.roles")
        assert set(TP.VALID_ROLES) == set(roles.ROLES.keys())

    def test_valid_commands(self):
        assert "pytest" in TP.VALID_VALIDATION_COMMANDS
        assert "flutter test" in TP.VALID_VALIDATION_COMMANDS
        assert "npm test" in TP.VALID_VALIDATION_COMMANDS

    def test_confidence_threshold_default(self):
        assert TP.DEFAULT_CONFIDENCE_THRESHOLD == 0.5
