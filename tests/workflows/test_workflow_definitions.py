"""tests/workflows/test_workflow_definitions.py — 内置工作流定义。"""

from __future__ import annotations

from workflows.definitions import BUILTIN_WORKFLOWS, get_builtin, list_builtins

from workflow_helpers import FEATURE_STEP_IDS


class TestBuiltins:
    def test_feature_delivery_steps(self):
        w = BUILTIN_WORKFLOWS["feature-delivery"]
        assert w.step_ids() == FEATURE_STEP_IDS  # architecture→development→testing→validation

    def test_desktop_feature_steps(self):
        """phase4a-status.md: desktop-feature 必须为 architecture→development→testing→validation。"""
        w = BUILTIN_WORKFLOWS["desktop-feature"]
        assert w.step_ids() == FEATURE_STEP_IDS

    def test_bug_fix_steps(self):
        w = BUILTIN_WORKFLOWS["bug-fix"]
        assert w.step_ids() == ["reproduce", "diagnose", "fix", "verify"]

    def test_release_steps(self):
        w = BUILTIN_WORKFLOWS["release"]
        assert w.step_ids() == ["build", "test", "stage", "publish"]

    def test_steps_sequential_order(self):
        """所有内置定义: order 连续 1..n 且 step 顺序即执行顺序。"""
        for w in BUILTIN_WORKFLOWS.values():
            assert [s.order for s in w.ordered_steps()] == list(range(1, len(w.steps) + 1))
            assert [s.id for s in w.ordered_steps()] == w.step_ids()

    def test_steps_carry_required_metadata(self):
        """required_skill/required_role 为声明性元数据, 每步可空但定义齐全。"""
        w = BUILTIN_WORKFLOWS["feature-delivery"]
        for s in w.steps:
            assert s.required_skill is not None
            assert s.required_role is not None

    def test_get_builtin_copy(self):
        w1 = get_builtin("feature-delivery")
        w2 = get_builtin("feature-delivery")
        assert w1 is not None and w2 is not None
        assert w1 == w2
        assert w1 is not w2  # 深拷贝: 调用方修改不影响内置表
        w1.name = "改了"
        assert BUILTIN_WORKFLOWS["feature-delivery"].name != "改了"

    def test_get_builtin_missing_returns_none(self):
        assert get_builtin("no-such-workflow") is None

    def test_list_builtins_sorted(self):
        ids = [w.id for w in list_builtins()]
        assert ids == sorted(ids)
        assert "feature-delivery" in ids
