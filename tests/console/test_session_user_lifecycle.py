"""S10-065 — UserLifecycle 测试套件 (Batch B)。

覆盖: 内部状态 → 用户视角状态映射 / governance 优先 / DESCRIPTIONS / 失败安全。
"""

from __future__ import annotations

from importlib import import_module

UL = import_module("factory-console.session.user_lifecycle")


class TestMapping:
    def test_idea(self):
        assert UL.UserLifecycle.map("idea", "", "") == UL.UserLifecycle.IDEA

    def test_product_defined(self):
        assert UL.UserLifecycle.map("product_defined", "", "") == UL.UserLifecycle.PRODUCT_DEFINED

    def test_engineering_ready_planning(self):
        assert UL.UserLifecycle.map("engineering_ready", "", "") == UL.UserLifecycle.PLANNING

    def test_execution_ready(self):
        assert UL.UserLifecycle.map("execution_ready", "", "") == UL.UserLifecycle.READY

    def test_development_production(self):
        assert UL.UserLifecycle.map("development", "", "") == UL.UserLifecycle.PRODUCTION

    def test_testing_validation(self):
        assert UL.UserLifecycle.map("testing", "", "") == UL.UserLifecycle.VALIDATION

    def test_validation_pass(self):
        assert UL.UserLifecycle.map("validation_pass", "", "") == UL.UserLifecycle.VALIDATION

    def test_user_acceptance(self):
        assert UL.UserLifecycle.map("user_acceptance", "", "") == UL.UserLifecycle.ACCEPTANCE

    def test_delivered(self):
        assert UL.UserLifecycle.map("delivered", "", "") == UL.UserLifecycle.DELIVERED

    def test_discovery_state(self):
        assert UL.UserLifecycle.map("discovering", "", "") == UL.UserLifecycle.DISCOVERY


class TestGovernancePriority:
    def test_blocked(self):
        assert UL.UserLifecycle.map("development", "blocked", "") == UL.UserLifecycle.BLOCKED

    def test_governance_blocked(self):
        assert UL.UserLifecycle.map("development", "", "blocked") == UL.UserLifecycle.BLOCKED

    def test_waiting_review(self):
        assert UL.UserLifecycle.map("development", "", "waiting_for_review") == UL.UserLifecycle.REVIEW

    def test_review_required(self):
        assert UL.UserLifecycle.map("development", "review_required", "") == UL.UserLifecycle.REVIEW

    def test_pending_review(self):
        assert UL.UserLifecycle.map("development", "", "", pending_review=True) == UL.UserLifecycle.REVIEW

    def test_failed(self):
        assert UL.UserLifecycle.map("development", "failed", "") == UL.UserLifecycle.FAILED

    def test_cancelled(self):
        assert UL.UserLifecycle.map("", "cancelled", "") == UL.UserLifecycle.CANCELLED


class TestDescriptions:
    def test_all_states_described(self):
        for s in UL.UserLifecycle.STATUSES:
            assert s in UL.DESCRIPTIONS, f"{s} 缺描述"

    def test_description_text(self):
        assert len(UL.DESCRIPTIONS[UL.UserLifecycle.DELIVERED]) > 0

    def test_unknown_fallback(self):
        assert UL.UserLifecycle.map("bogus_state", "", "") == UL.UserLifecycle.PRODUCTION


class TestConstants:
    def test_statuses(self):
        assert UL.UserLifecycle.STATUSES == (
            "idea", "discovery", "product_defined", "planning", "ready",
            "production", "validation", "review", "acceptance", "delivered",
            "blocked", "failed", "cancelled",
        )

    def test_no_internal_break(self):
        """映射层不破坏内部 Lifecycle (惰性 import)。"""
        from importlib import import_module
        P = import_module("factory-console.session.pipeline")
        assert P.Lifecycle.DEVELOPMENT == "development"
