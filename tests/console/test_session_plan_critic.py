"""S10-062 批次 A — PlanCritic 执行前缺口检查测试套件。

覆盖: 持久化缺口 / 测试缺口 / UI 缺口 / 角色缺口 / 无缺口 / severity /
confidence 推导 (信号强度 + 封顶 0.95) / 多缺口并存 / review 纯函数
(不修改 plan/DAG, 不落盘) / 失败安全 (None/非预期输入)。

装配: tmp_path + fixtures; 禁真实 LLM/网络 (纯 deterministic)。
"""

from __future__ import annotations

import json
from copy import deepcopy
from importlib import import_module

PC = import_module("factory-console.session.plan_critic")

#: 角色缺口检查会用到的合法角色 (ROLES 8 键 — 与实现同源)
VALID_ROLES = tuple(PC.ROLES.keys())


def critic() -> "PC.PlanCritic":
    return PC.PlanCritic()


def task(**kw) -> dict:
    base = {"id": "T001", "name": "task", "required_role": "backend",
            "description": "实现功能"}
    base.update(kw)
    return base


def mobile_product(**kw) -> dict:
    base = {"name": "ScorePocket", "platform": "mobile",
            "requirements": ["用户可记录分数", "数据需要持久化"]}
    base.update(kw)
    return base


def eng_persistence(**kw) -> dict:
    base = {"name": "ScorePocket", "platform": "mobile",
            "architecture": "layered",
            "modules": [{"name": "storage", "description": "持久化模块"}]}
    base.update(kw)
    return base


def full_plan() -> list[dict]:
    """覆盖持久化/测试/UI/角色的完整计划 (无缺口 fixture)。"""
    return [
        task(id="T001", name="backend api", required_role="backend",
             description="实现数据持久化存储"),
        task(id="T002", name="ui", required_role="frontend",
             description="实现界面展示"),
        task(id="T003", name="tests", required_role="qa",
             description="补充测试"),
    ]


# ==================================================================
# 1. 持久化缺口 (missing_implementation)
# ==================================================================


class TestPersistenceGap:
    def test_gap_when_requirement_without_task(self):
        gaps = critic().review(
            plan=[task(id="T001", description="纯 API")],
            product=mobile_product(),
            engineering=eng_persistence(),
        )
        types = [g.gap_type for g in gaps]
        assert "missing_implementation" in types

    def test_no_gap_when_plan_has_persistence_task(self):
        gaps = critic().review(
            plan=[task(id="T001", description="实现数据持久化存储")],
            product=mobile_product(),
            engineering=eng_persistence(),
        )
        assert not [g for g in gaps if g.gap_type == "missing_implementation"]

    def test_no_gap_when_no_persistence_requirement(self):
        gaps = critic().review(
            plan=[task(id="T001", description="纯 API")],
            product={"name": "x", "platform": "mobile",
                     "requirements": ["记录分数"]},
            engineering={"name": "x", "architecture": "layered",
                         "modules": []},
        )
        assert not [g for g in gaps if g.gap_type == "missing_implementation"]

    def test_gap_type_and_action(self):
        gaps = critic().review(
            plan=[task(id="T001", description="纯 API")],
            product=mobile_product(),
            engineering=eng_persistence(),
        )
        g = next(x for x in gaps if x.gap_type == "missing_implementation")
        assert g.detected is True
        assert g.recommended_action == "INSERT_TASK"

    def test_severity_high(self):
        gaps = critic().review(
            plan=[task(id="T001", description="纯 API")],
            product=mobile_product(),
            engineering=eng_persistence(),
        )
        g = next(x for x in gaps if x.gap_type == "missing_implementation")
        assert g.severity == "high"

    def test_confidence_rises_with_two_sources(self):
        # product + engineering 都命中 → 0.80 + 0.05
        gaps = critic().review(
            plan=[task(id="T001", description="纯 API")],
            product=mobile_product(),
            engineering=eng_persistence(),
        )
        g = next(x for x in gaps if x.gap_type == "missing_implementation")
        assert g.confidence == 0.85

    def test_confidence_single_source(self):
        # 仅 engineering 命中 → 0.80
        gaps = critic().review(
            plan=[task(id="T001", description="纯 API")],
            product={"name": "x", "platform": "mobile",
                     "requirements": ["记录分数"]},
            engineering=eng_persistence(),
        )
        g = next(x for x in gaps if x.gap_type == "missing_implementation")
        assert g.confidence == 0.80


# ==================================================================
# 2. 测试缺口 (missing_test)
# ==================================================================


class TestTestGap:
    def test_gap_when_no_qa_task(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="backend"),
                  task(id="T002", required_role="frontend")],
            product={"name": "x", "platform": "backend",
                     "requirements": []},
            engineering={},
        )
        assert [g.gap_type for g in gaps].count("missing_test") == 1

    def test_no_gap_when_qa_role_task(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="qa")],
            product={"name": "x", "platform": "backend", "requirements": []},
            engineering={},
        )
        assert not [g for g in gaps if g.gap_type == "missing_test"]

    def test_no_gap_when_tester_role_task(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="tester")],
            product={"name": "x", "platform": "backend", "requirements": []},
            engineering={},
        )
        assert not [g for g in gaps if g.gap_type == "missing_test"]

    def test_no_gap_when_task_text_mentions_tests(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="backend",
                       description="为模块增加 pytest 测试")],
            product={"name": "x", "platform": "backend", "requirements": []},
            engineering={},
        )
        assert not [g for g in gaps if g.gap_type == "missing_test"]

    def test_empty_plan_no_test_gap(self):
        # 空计划不触发测试缺口 (避免三重误报)
        gaps = critic().review(
            plan=[],
            product={"name": "x", "platform": "backend", "requirements": []},
            engineering={},
        )
        assert not [g for g in gaps if g.gap_type == "missing_test"]

    def test_severity_medium_and_action(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="backend")],
            product={"name": "x", "platform": "backend", "requirements": []},
            engineering={},
        )
        g = next(x for x in gaps if x.gap_type == "missing_test")
        assert g.severity == "medium"
        assert g.recommended_action == "INSERT_TASK"
        assert g.confidence == 0.80


# ==================================================================
# 3. UI 缺口 (ui_gap)
# ==================================================================


class TestUIGap:
    def test_gap_when_mobile_without_frontend(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="backend")],
            product=mobile_product(),
            engineering={},
        )
        assert [g.gap_type for g in gaps].count("ui_gap") == 1

    def test_gap_when_web_without_frontend(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="backend")],
            product={"name": "x", "platform": "web", "requirements": []},
            engineering={},
        )
        assert [g.gap_type for g in gaps].count("ui_gap") == 1

    def test_no_gap_when_backend_platform(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="backend")],
            product={"name": "x", "platform": "backend", "requirements": []},
            engineering={},
        )
        assert not [g for g in gaps if g.gap_type == "ui_gap"]

    def test_gap_when_product_mentions_ui_marker(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="backend")],
            product={"name": "x", "platform": "backend",
                     "requirements": ["需要界面展示"]},
            engineering={},
        )
        assert [g.gap_type for g in gaps].count("ui_gap") == 1

    def test_no_gap_when_frontend_task_present(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="frontend")],
            product=mobile_product(),
            engineering={},
        )
        assert not [g for g in gaps if g.gap_type == "ui_gap"]

    def test_severity_low(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="backend")],
            product=mobile_product(),
            engineering={},
        )
        g = next(x for x in gaps if x.gap_type == "ui_gap")
        assert g.severity == "low"
        assert g.recommended_action == "INSERT_TASK"

    def test_confidence_explicit_platform(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="backend")],
            product=mobile_product(),
            engineering={},
        )
        g = next(x for x in gaps if x.gap_type == "ui_gap")
        assert g.confidence == 0.75  # 0.70 + 0.05 (显式平台)

    def test_confidence_marker_only(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="backend")],
            product={"name": "x", "platform": "backend",
                     "requirements": ["需要界面展示"]},
            engineering={},
        )
        g = next(x for x in gaps if x.gap_type == "ui_gap")
        assert g.confidence == 0.70


# ==================================================================
# 4. 角色缺口 (dependency_gap)
# ==================================================================


class TestRoleGap:
    def test_gap_when_task_missing_role(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="")],
            product={"name": "x", "platform": "backend", "requirements": []},
            engineering={},
        )
        role_gaps = [g for g in gaps if g.gap_type == "dependency_gap"]
        assert len(role_gaps) == 1

    def test_gap_when_task_missing_role_key(self):
        gaps = critic().review(
            plan=[{"id": "T001", "name": "x", "description": "y"}],
            product={"name": "x", "platform": "backend", "requirements": []},
            engineering={},
        )
        assert [g.gap_type for g in gaps].count("dependency_gap") == 1

    def test_gap_when_role_invalid(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="wizard")],
            product={"name": "x", "platform": "backend", "requirements": []},
            engineering={},
        )
        assert [g.gap_type for g in gaps].count("dependency_gap") == 1

    def test_gap_when_role_not_in_capabilities(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="backend")],
            product={"name": "x", "platform": "backend", "requirements": []},
            engineering={},
            capabilities=["frontend"],
        )
        assert [g.gap_type for g in gaps].count("dependency_gap") == 1

    def test_no_gap_when_valid_role(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="backend")],
            product={"name": "x", "platform": "backend", "requirements": []},
            engineering={},
        )
        assert not [g for g in gaps if g.gap_type == "dependency_gap"]

    def test_no_gap_for_all_valid_roles(self):
        plan = [task(id=f"T{i}", required_role=r)
                for i, r in enumerate(VALID_ROLES, start=1)]
        gaps = critic().review(
            plan=plan,
            product={"name": "x", "platform": "backend", "requirements": []},
            engineering={},
        )
        assert not [g for g in gaps if g.gap_type == "dependency_gap"]

    def test_role_gap_fields(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="")],
            product={"name": "x", "platform": "backend", "requirements": []},
            engineering={},
        )
        g = next(x for x in gaps if x.gap_type == "dependency_gap")
        assert g.source_task_id == "T001"
        assert g.recommended_action == "MODIFY_TASK"
        assert g.severity == "medium"
        assert g.confidence == 0.85


# ==================================================================
# 5. 多缺口 / 无缺口 / 失败安全
# ==================================================================


class TestMultipleAndNone:
    def test_all_gaps_together(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="", description="纯 API")],
            product=mobile_product(),
            engineering=eng_persistence(),
        )
        types = {g.gap_type for g in gaps}
        assert "missing_implementation" in types
        assert "missing_test" in types
        assert "ui_gap" in types
        assert "dependency_gap" in types

    def test_no_gaps_for_full_plan(self):
        gaps = critic().review(
            plan=full_plan(),
            product=mobile_product(),
            engineering=eng_persistence(),
            capabilities=list(PC.ROLES.keys()),
        )
        assert gaps == []

    def test_plan_none_returns_gaps_not_raise(self):
        gaps = critic().review(
            plan=None,
            product=mobile_product(),
            engineering=eng_persistence(),
        )
        assert isinstance(gaps, list)
        # 持久化/UI 缺口在空计划下仍可检出
        types = {g.gap_type for g in gaps}
        assert "missing_implementation" in types

    def test_all_none_returns_empty(self):
        assert critic().review() == []

    def test_plan_dict_with_tasks_key(self):
        gaps = critic().review(
            plan={"tasks": [task(id="T001", required_role="backend",
                                 description="纯 API")]},
            product=mobile_product(),
            engineering=eng_persistence(),
        )
        assert [g.gap_type for g in gaps].count("missing_implementation") == 1

    def test_non_dict_tasks_skipped(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="backend", description="纯 API"),
                  "not-a-dict", 42],
            product=mobile_product(),
            engineering=eng_persistence(),
        )
        # 非 dict 任务不影响结果
        assert [g.gap_type for g in gaps].count("missing_implementation") == 1

    def test_non_dict_product_engineering_fail_safe(self):
        gaps = critic().review(
            plan=[task(id="T001", required_role="backend")],
            product="nope",
            engineering=[1, 2],
        )
        assert isinstance(gaps, list)
        assert not [g for g in gaps if g.gap_type == "missing_implementation"]
        assert not [g for g in gaps if g.gap_type == "ui_gap"]


# ==================================================================
# 6. severity / confidence 推导 + 纯函数性
# ==================================================================


class TestSeverityConfidence:
    def test_confidence_cap(self):
        # 多来源叠加也不超过 0.95
        gaps = critic().review(
            plan=[task(id="T001", description="纯 API")],
            product=mobile_product(),
            engineering=eng_persistence(),
        )
        for g in gaps:
            assert g.confidence <= 0.95

    def test_confidence_deterministic(self):
        kwargs = dict(
            plan=[task(id="T001", description="纯 API")],
            product=mobile_product(),
            engineering=eng_persistence(),
        )
        a = critic().review(**kwargs)
        b = critic().review(**kwargs)
        assert [g.to_dict()["confidence"] for g in a] == [
            g.to_dict()["confidence"] for g in b
        ]

    def test_gap_analysis_serializable(self):
        gaps = critic().review(
            plan=[task(id="T001", description="纯 API")],
            product=mobile_product(),
            engineering=eng_persistence(),
        )
        d = gaps[0].to_dict()
        assert d["detected"] is True
        assert d["timestamp"]
        assert isinstance(d["evidence"], list)

    def test_severity_in_known_set(self):
        gaps = critic().review(
            plan=[task(id="T001", description="纯 API")],
            product=mobile_product(),
            engineering=eng_persistence(),
        )
        for g in gaps:
            assert g.gap_type in PC.TYPE_PROFILE
            assert g.severity in (
                "low", "medium", "high", "critical",
            )

    def test_each_gap_has_reason_and_description(self):
        gaps = critic().review(
            plan=[task(id="T001", description="纯 API")],
            product=mobile_product(),
            engineering=eng_persistence(),
        )
        for g in gaps:
            assert g.reason
            assert g.description


class TestNoMutation:
    def test_plan_input_not_mutated(self):
        plan = full_plan()
        before = deepcopy(plan)
        critic().review(plan=plan, product=mobile_product(),
                        engineering=eng_persistence())
        assert plan == before

    def test_product_engineering_not_mutated(self):
        product = mobile_product()
        engineering = eng_persistence()
        p_before = deepcopy(product)
        e_before = deepcopy(engineering)
        critic().review(plan=full_plan(), product=product,
                        engineering=engineering)
        assert product == p_before
        assert engineering == e_before

    def test_review_creates_no_files(self, tmp_path):
        before = sorted(p.name for p in tmp_path.iterdir())
        critic().review(plan=full_plan(), product=mobile_product(),
                        engineering=eng_persistence())
        after = sorted(p.name for p in tmp_path.iterdir())
        assert before == after

    def test_review_is_pure_no_global_state(self):
        # 两次调用结果逐字段一致 (含 timestamp 不同 — 仅比较业务字段)
        kwargs = dict(plan=full_plan(), product=mobile_product(),
                      engineering=eng_persistence())
        a = critic().review(**kwargs)
        b = critic().review(**kwargs)
        assert len(a) == len(b) == 0
        assert json.dumps([g.to_dict() for g in a], sort_keys=True) == \
            json.dumps([g.to_dict() for g in b], sort_keys=True)
