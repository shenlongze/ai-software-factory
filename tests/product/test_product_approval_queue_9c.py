"""tests/product/test_product_approval_queue_9c.py — Approval Queue + History (Phase 9C, ADR-0028)。

覆盖: approval_queue 行形状 (request + artifact_type/artifact_version/confidence/
required_action 只读联表; artifact 缺失失败安全), required_action 按状态映射 (pending →
decide / approved → none / rejected|changes_requested → revise & re-request /
delegated → await delegate), list_approvals --status 过滤 (含 9a denied 归一),
approval_history 联表 (请求 + 决定, 按 requested_at 升序; 未决定 → decision None),
history artifact 不存在抛错 / 无请求空列表。
"""

from __future__ import annotations

import pytest

from product.service import ProductNotFoundError

from product_helpers import seed_artifact, seed_idea


def _seed_request(service, artifact_type: str = "prd", *, confidence: float = 0.0,
                  idea_id: str | None = None):
    a = seed_artifact(service, artifact_type, idea_id=idea_id, confidence=confidence)
    return service.request_approval(a.id)


class TestApprovalQueue:
    def test_queue_row_shape(self, service):
        _seed_request(service, "prd", confidence=0.85)
        row = service.approval_queue()[0]
        assert row["artifact_id"] == "ART-001"
        assert row["artifact_type"] == "prd"
        assert row["artifact_version"] == 1
        assert row["confidence"] == 0.85
        assert row["required_action"] == "decide"
        assert row["status"] == "pending"
        assert row["gate"] == "prd"

    def test_queue_required_action_mapping(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001")
        r = service.request_approval(a.id)
        service.decide_approval(r.id, "approved")
        # 构造多状态队列: 不同 artifact 各自走不同终态
        rows = {row["status"]: row["required_action"] for row in service.approval_queue()}
        assert rows["approved"] == "none"
        # rejected / changes_requested / delegated 走新请求
        b = seed_artifact(service, "ui", idea_id="PI-001")
        rb = service.request_approval(b.id)
        service.decide_approval(rb.id, "rejected")
        c = seed_artifact(service, "architecture", idea_id="PI-001")
        rc = service.request_approval(c.id)
        service.decide_approval(rc.id, "changes_requested")
        d = seed_artifact(service, "prd", idea_id="PI-001")
        rd = service.request_approval(d.id)
        service.decide_approval(rd.id, "delegated")
        e = seed_artifact(service, "ui", idea_id="PI-001")
        service.request_approval(e.id)  # 留一条 pending (待决定)
        rows = {row["status"]: row["required_action"] for row in service.approval_queue()}
        assert rows["rejected"] == "revise & re-request"
        assert rows["changes_requested"] == "revise & re-request"
        assert rows["delegated"] == "await delegate"
        assert rows["pending"] == "decide"

    def test_queue_status_filter(self, service):
        a = seed_artifact(service, "prd")
        r1 = service.request_approval(a.id)
        b = seed_artifact(service, "ui")
        service.request_approval(b.id)
        service.decide_approval(r1.id, "approved")
        rows = service.approval_queue(status="approved")
        assert [row["id"] for row in rows] == ["APR-001"]
        assert service.approval_queue(status="pending")[0]["id"] == "APR-002"

    def test_queue_denied_alias_filter_normalized(self, service):
        # 9a 遗留 status 过滤: "denied" → rejected 归一 (状态机语义映射)
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        service.decide_approval(r.id, "denied")
        rows = service.approval_queue(status="denied")
        assert len(rows) == 1
        assert rows[0]["status"] == "rejected"

    def test_queue_missing_artifact_fail_safe(self, service):
        # Artifact 被删/不存在 → 联表字段失败安全 (None/0.0), 不抛错
        r = _seed_request(service, "prd")
        import json

        # 直接写文件删 artifact 记录 (模拟 Artifact 被删 / 不存在)
        artifacts_path = service._store.dir / "artifacts.json"
        data = json.loads(artifacts_path.read_text(encoding="utf-8"))
        data["artifacts"].pop("ART-001", None)
        artifacts_path.write_text(json.dumps(data), encoding="utf-8")
        row = service.approval_queue(status="pending")[0]
        assert row["artifact_type"] is None
        assert row["artifact_version"] == r.artifact_version  # 回退到请求快照
        assert row["confidence"] == 0.0

    def test_queue_empty_store(self, service):
        assert service.approval_queue() == []


class TestListApprovalsFilter:
    def test_status_filter_terminal(self, service):
        a = seed_artifact(service, "prd")
        r1 = service.request_approval(a.id)
        b = seed_artifact(service, "ui")
        service.request_approval(b.id)
        service.decide_approval(r1.id, "approved")
        assert [r.id for r in service.list_approvals(status="approved")] == ["APR-001"]
        assert [r.id for r in service.list_approvals(status="pending")] == ["APR-002"]
        assert [r.id for r in service.list_approvals(status="rejected")] == []

    def test_status_filter_denied_alias(self, service):
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        service.decide_approval(r.id, "denied")
        assert [r.id for r in service.list_approvals(status="denied")] == ["APR-001"]
        assert [r.id for r in service.list_approvals(status="rejected")] == ["APR-001"]

    def test_status_filter_case_insensitive(self, service):
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        service.decide_approval(r.id, "approved")
        assert len(service.list_approvals(status="APPROVED")) == 1

    def test_status_filter_combined_with_pending_only(self, service):
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        service.decide_approval(r.id, "approved")
        assert service.list_approvals(pending_only=True, status="approved") == []
        assert len(service.list_approvals(pending_only=True, status="pending")) == 0
        assert len(service.list_approvals(status="approved")) == 1


class TestApprovalHistory:
    def test_history_joins_request_and_decision(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001", confidence=0.7)
        r = service.request_approval(a.id, by="alice", note="请审")
        service.decide_approval(r.id, "changes_requested", by="bob", comment="改")
        rows = service.approval_history(a.id)
        assert len(rows) == 1
        assert rows[0]["id"] == r.id
        assert rows[0]["artifact_version"] == 1
        assert rows[0]["by"] == "alice"
        d = rows[0]["decision"]
        assert d["decision"] == "changes_requested"
        assert d["decided_by"] == "bob"
        assert d["comment"] == "改"

    def test_history_orders_by_requested_at(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001")
        r1 = service.request_approval(a.id)
        service.decide_approval(r1.id, "rejected")
        r2 = service.request_approval(a.id)  # 终态可逆 → 第二条请求
        service.decide_approval(r2.id, "approved")
        rows = service.approval_history(a.id)
        assert [row["id"] for row in rows] == [r1.id, r2.id]  # requested_at 升序

    def test_history_pending_request_has_no_decision(self, service):
        a = seed_artifact(service, "prd")
        service.request_approval(a.id)
        rows = service.approval_history(a.id)
        assert rows[0]["decision"] is None  # 未决定 → 无决定联表

    def test_history_missing_artifact_raises(self, service):
        with pytest.raises(ProductNotFoundError):
            service.approval_history("ART-999")

    def test_history_no_requests_empty(self, service):
        a = seed_artifact(service, "prd")
        assert service.approval_history(a.id) == []

    def test_history_scoped_to_artifact(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001")
        b = seed_artifact(service, "ui", idea_id="PI-001")
        ra = service.request_approval(a.id)
        service.request_approval(b.id)
        service.decide_approval(ra.id, "approved")
        rows_a = service.approval_history(a.id)
        rows_b = service.approval_history(b.id)
        assert [row["id"] for row in rows_a] == [ra.id]
        assert rows_b[0]["decision"] is None
