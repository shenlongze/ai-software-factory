"""tests/product/test_product_state_machine_9c.py — Approval 决策状态机 (Phase 9C, ADR-0028)。

覆盖: pending → approved|rejected|changes_requested|delegated 全转换, 大小写/9a 遗留
别名 (denied → rejected) 归一, 非法 decision 抛错, 四终态不可重复 decide (重复决定抛错),
终态可逆 (rejected/changes_requested/delegated 后可重新提交同版本新请求; approved 仅
version 递增后可再申请 — 禁覆盖历史), 队列唯一性守卫 (同 artifact pending 重复申请拒绝)。

服务层终态断言一律从 store 重取 (decide 经 model_copy 新实例, 入参对象过期 —
Phase 9a 教训)。
"""

from __future__ import annotations

import pytest

from product.models import ApprovalStatus
from product.service import ProductError, ProductNotFoundError, VALID_DECISIONS

from product_helpers import seed_artifact, seed_idea


class TestValidDecisions:
    def test_valid_decisions_are_four_terminal_values(self):
        assert set(VALID_DECISIONS) == {"approved", "rejected", "changes_requested", "delegated"}

    def test_denied_not_in_valid_decisions(self):
        # denied 为 9a 遗留输入别名 (服务层映射 rejected), 非状态机终态值
        assert "denied" not in VALID_DECISIONS


class TestStateTransitions:
    def test_approved_transition(self, service):
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        service.decide_approval(r.id, "approved")
        assert service.get_approval_request(r.id).status == ApprovalStatus.APPROVED.value

    def test_rejected_transition(self, service):
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        service.decide_approval(r.id, "rejected", comment="no")
        assert service.get_approval_request(r.id).status == ApprovalStatus.REJECTED.value

    def test_changes_requested_transition(self, service):
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        service.decide_approval(r.id, "changes_requested", comment="改一下")
        assert (
            service.get_approval_request(r.id).status
            == ApprovalStatus.CHANGES_REQUESTED.value
        )

    def test_delegated_transition(self, service):
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        service.decide_approval(r.id, "delegated", by="lead")
        assert service.get_approval_request(r.id).status == ApprovalStatus.DELEGATED.value
        assert service.get_approval_request(r.id).decided_by == "lead"

    def test_uppercase_decision_normalized(self, service):
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        service.decide_approval(r.id, "APPROVED")
        assert service.get_approval_request(r.id).status == "approved"

    def test_denied_alias_maps_to_rejected(self, service):
        # 9a 遗留输入别名 → rejected (CLI deny 动词与旧调用兼容, ADR-0028 决策 1)
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        request2, decision, _ = service.decide_approval(r.id, "denied", comment="旧调用")
        assert request2.status == "rejected"
        assert decision.decision == "rejected"

    def test_mixed_case_alias_maps(self, service):
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        service.decide_approval(r.id, "DeNiEd")
        assert service.get_approval_request(r.id).status == "rejected"

    def test_decision_comment_and_by_recorded(self, service):
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        service.decide_approval(r.id, "changes_requested", by="reviewer", comment="缺竞品分析")
        got = service.get_approval_request(r.id)
        assert got.decided_by == "reviewer"
        assert got.comment == "缺竞品分析"
        assert got.decided_at  # 决策时间回填


class TestInvalidTransitions:
    @pytest.mark.parametrize("decision", ["maybe", "", "granted", "denied-but-not", "APPROVE"])
    def test_invalid_decision_raises(self, service, decision):
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        with pytest.raises(ProductError, match="invalid approval decision"):
            service.decide_approval(r.id, decision)

    def test_invalid_decision_leaves_request_pending(self, service):
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        with pytest.raises(ProductError):
            service.decide_approval(r.id, "bogus")
        assert service.get_approval_request(r.id).status == "pending"  # 状态未被污染

    def test_decide_missing_request_raises(self, service):
        with pytest.raises(ProductNotFoundError):
            service.decide_approval("APR-999", "approved")

    @pytest.mark.parametrize("first", ["approved", "rejected", "changes_requested", "delegated"])
    def test_terminal_requests_cannot_be_decided_again(self, service, first):
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        service.decide_approval(r.id, first)
        with pytest.raises(ProductError, match="already"):
            service.decide_approval(r.id, "approved")

    def test_approved_then_deny_alias_also_rejected(self, service):
        # 终态不可逆: approved 后任何 decide (含 9a deny 别名) 都拒绝
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        service.decide_approval(r.id, "approved")
        with pytest.raises(ProductError, match="already approved"):
            service.decide_approval(r.id, "denied")


class TestTerminalReversible:
    """终态可逆: 非 approved 终态 (rejected/changes_requested/delegated) 后重新提交
    同版本新请求; approved 仅 version 递增后可再申请 (禁覆盖历史)。"""

    @pytest.mark.parametrize("terminal", ["rejected", "changes_requested", "delegated"])
    def test_terminal_requests_allow_requeue_same_version(self, service, terminal):
        a = seed_artifact(service, "prd")
        r1 = service.request_approval(a.id)
        service.decide_approval(r1.id, terminal)
        r2 = service.request_approval(a.id)  # 同版本重新提交 (终态可逆)
        assert r2.id == "APR-002"
        assert r2.status == "pending"
        assert r2.artifact_version == a.version

    def test_approved_same_version_requeue_blocked(self, service):
        a = seed_artifact(service, "prd")
        r1 = service.request_approval(a.id)
        service.decide_approval(r1.id, "approved")
        with pytest.raises(ProductError, match="already approved"):
            service.request_approval(a.id)  # v1 已批准 → 须 revise 到 v2

    def test_approved_new_version_requeue_allowed(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001")
        r1 = service.request_approval(a.id)
        service.decide_approval(r1.id, "approved")
        v2 = service.revise_artifact(a.id, {"title": "v2"})
        assert v2.version == 2
        r2 = service.request_approval(v2.id)  # v2 全新 pending 流程
        assert r2.status == "pending"
        assert r2.artifact_version == 2

    def test_approved_v2_requeue_guard_uses_version(self, service):
        # v2 已批准后同版本再申请 → 拒绝 (按 version 守卫, 非按 artifact)
        a = seed_artifact(service, "prd", idea_id="PI-001")
        r1 = service.request_approval(a.id)
        service.decide_approval(r1.id, "approved")
        v2 = service.revise_artifact(a.id, {"title": "v2"})
        r2 = service.request_approval(v2.id)
        service.decide_approval(r2.id, "approved")
        with pytest.raises(ProductError, match="version 2 already approved"):
            service.request_approval(v2.id)

    def test_approved_artifact_version_snapshot_bound(self, service):
        # Approval 绑定申请时点版本: v1 申请 → approve → revise v2 → v1 请求的
        # artifact_version 恒为 1 (禁覆盖历史的审计锚点)
        a = seed_artifact(service, "prd", idea_id="PI-001")
        r1 = service.request_approval(a.id)
        assert r1.artifact_version == 1
        service.decide_approval(r1.id, "approved")
        v2 = service.revise_artifact(a.id, {"title": "v2"})
        assert v2.version == 2
        assert service.get_approval_request(r1.id).artifact_version == 1


class TestQueueUniquenessGuard:
    def test_duplicate_pending_request_blocked(self, service):
        a = seed_artifact(service, "prd")
        service.request_approval(a.id)
        with pytest.raises(ProductError, match="already pending"):
            service.request_approval(a.id)

    def test_pending_blocked_even_with_other_terminal_requests(self, service):
        # v1 rejected → 重新提交 pending → 再次重复申请被拒 (队列唯一性守卫)
        a = seed_artifact(service, "prd")
        r1 = service.request_approval(a.id)
        service.decide_approval(r1.id, "rejected")
        service.request_approval(a.id)  # 终态可逆: 重新提交
        with pytest.raises(ProductError, match="already pending"):
            service.request_approval(a.id)

    def test_guard_does_not_affect_other_artifacts(self, service):
        a = seed_artifact(service, "prd")
        b = seed_artifact(service, "ui")
        service.request_approval(a.id)
        r2 = service.request_approval(b.id)  # 不同 artifact 不受守卫影响
        assert r2.status == "pending"
        assert r2.gate == "ui"


class TestIdeaLinkage:
    def test_idea_linkage_still_works_9c(self, service):
        idea = seed_idea(service)
        a = seed_artifact(service, "prd", idea_id=idea.id)
        r = service.request_approval(a.id)
        assert r.idea_id == idea.id
        service.decide_approval(r.id, "approved")
        # 关联工作流未启动 → 联动 no-op, 请求终态仍生效
        assert service.get_approval_request(r.id).status == "approved"
