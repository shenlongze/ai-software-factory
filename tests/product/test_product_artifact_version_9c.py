"""tests/product/test_product_artifact_version_9c.py — Artifact Version Integration (Phase 9C, ADR-0028)。

覆盖: revise_artifact 产出新版本 (version +1, 禁覆盖历史 — 旧版本原样保留, supersedes
指向前版), Lineage 继承 (provider/agent/source_events/confidence), content 增量合并
+ revision_note, artifact_version_history 版本链 (同 idea 同类型按 version 升序;
无 idea 锚点 → 仅自身), Approval 绑定 version (申请时点快照; v1 已批准 → revise v2 →
重新审批; 同版本重复批准被守卫拒绝)。
"""

from __future__ import annotations

import pytest

from pydantic import ValidationError

from product.models import Artifact
from product.service import ProductError, ProductNotFoundError

from product_helpers import seed_artifact, seed_idea


class TestReviseArtifact:
    def test_revise_creates_new_version_with_supersedes(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001", content={"title": "v1"})
        v2 = service.revise_artifact(a.id, {"title": "v2"})
        assert v2.id != a.id  # 新 id (id 即版本身份)
        assert v2.version == 2
        assert v2.supersedes == a.id
        assert v2.type == "prd"
        assert v2.content["title"] == "v2"
        assert v2.content["idea_id"] == "PI-001"  # idea 锚点自然保留

    def test_revise_does_not_overwrite_old_version(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001")
        service.revise_artifact(a.id, {"title": "v2"})
        old = service.get_artifact(a.id)  # 旧版本原样保留 (禁覆盖历史)
        assert old.version == 1
        assert old.content.get("title") != "v2"

    def test_revise_increments_chain(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001")
        v2 = service.revise_artifact(a.id, {"title": "v2"})
        v3 = service.revise_artifact(v2.id, {"title": "v3"})
        assert v3.version == 3
        assert v3.supersedes == v2.id
        assert v2.supersedes == a.id

    def test_revise_inherits_lineage(self, service):
        a = seed_artifact(
            service, "prd", idea_id="PI-001", provider_id="hermes", agent_id="ag-1",
            confidence=0.8, source_events=["ev-1", "ev-2"],
        )
        v2 = service.revise_artifact(a.id, {"title": "v2"})
        assert v2.provider_id == "hermes"
        assert v2.agent_id == "ag-1"
        assert v2.confidence == 0.8
        assert v2.source_events == ["ev-1", "ev-2"]

    def test_revise_explicit_overrides_lineage(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001", provider_id="hermes", confidence=0.8)
        v2 = service.revise_artifact(
            a.id, {"title": "v2"}, provider_id="openai", confidence=0.9,
            source_events=["ev-9"],
        )
        assert v2.provider_id == "openai"
        assert v2.confidence == 0.9
        assert v2.source_events == ["ev-9"]

    def test_revise_merges_content_incrementally(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001", content={"title": "t", "keep": 1})
        v2 = service.revise_artifact(a.id, {"title": "t2"})
        assert v2.content["keep"] == 1  # 旧字段保留
        assert v2.content["title"] == "t2"  # 新字段覆盖

    def test_revise_adds_revision_note(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001")
        v2 = service.revise_artifact(a.id, {"title": "v2"}, note="按 reviewer 意见修改")
        assert v2.content["revision_note"] == "按 reviewer 意见修改"

    def test_revise_status_default_and_override(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001")
        assert service.revise_artifact(a.id).status == "revised"
        v2 = service.revise_artifact(a.id, {"title": "x"}, status="completed")
        assert v2.status == "completed"

    def test_revise_missing_artifact_raises(self, service):
        with pytest.raises(ProductNotFoundError):
            service.revise_artifact("ART-999")

    def test_revise_created_by_is_reviser(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001")
        v2 = service.revise_artifact(a.id, {"title": "v2"}, by="alice")
        assert v2.created_by == "alice"


class TestVersionHistory:
    def test_history_returns_chain_sorted_by_version(self, service):
        idea = seed_idea(service)
        a = seed_artifact(service, "prd", idea_id=idea.id, content={"title": "v1"})
        v2 = service.revise_artifact(a.id, {"title": "v2"})
        v3 = service.revise_artifact(v2.id, {"title": "v3"})
        chain = service.artifact_version_history(v3.id)
        assert [c.version for c in chain] == [1, 2, 3]
        assert [c.id for c in chain] == [a.id, v2.id, v3.id]

    def test_history_from_old_version_also_full_chain(self, service):
        idea = seed_idea(service)
        a = seed_artifact(service, "prd", idea_id=idea.id)
        v2 = service.revise_artifact(a.id, {"title": "v2"})
        service.revise_artifact(v2.id, {"title": "v3"})
        assert [c.version for c in service.artifact_version_history(a.id)] == [1, 2, 3]

    def test_history_without_idea_anchor_returns_self(self, service):
        # 无 idea 锚点 (content.idea_id 缺失) → 无法归族, KISS: 仅自身
        a = seed_artifact(service, "prd")
        service.revise_artifact(a.id, {"title": "v2"})
        assert [c.id for c in service.artifact_version_history(a.id)] == [a.id]

    def test_history_scoped_by_type(self, service):
        idea = seed_idea(service)
        p1 = seed_artifact(service, "prd", idea_id=idea.id)
        u1 = seed_artifact(service, "ui", idea_id=idea.id)  # 同 idea 不同类型
        service.revise_artifact(p1.id, {"title": "p2"})
        assert [c.type for c in service.artifact_version_history(p1.id)] == ["prd", "prd"]
        assert [c.id for c in service.artifact_version_history(u1.id)] == [u1.id]

    def test_history_missing_artifact_raises(self, service):
        with pytest.raises(ProductNotFoundError):
            service.artifact_version_history("ART-999")


class TestApprovalVersionBinding:
    def test_request_snapshots_artifact_version(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001")
        r = service.request_approval(a.id)
        assert r.artifact_version == 1

    def test_v2_request_snapshots_v2(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001")
        v2 = service.revise_artifact(a.id, {"title": "v2"})
        r = service.request_approval(v2.id)
        assert r.artifact_version == 2

    def test_v1_approved_revise_v2_reapproval_chain(self, service):
        """冒烟核心: v1 → approved; changes/rejected → revise v2 → 重新审批 (终态可逆 + 版本递增)。"""
        a = seed_artifact(service, "prd", idea_id="PI-001")
        r1 = service.request_approval(a.id)
        service.decide_approval(r1.id, "approved")
        v2 = service.revise_artifact(a.id, {"title": "v2"})
        r2 = service.request_approval(v2.id)  # v2 全新审批
        assert r2.artifact_version == 2
        service.decide_approval(r2.id, "changes_requested", comment="继续改")
        v3 = service.revise_artifact(v2.id, {"title": "v3"})
        r3 = service.request_approval(v3.id)
        assert r3.artifact_version == 3
        service.decide_approval(r3.id, "approved")
        assert service.get_approval_request(r3.id).status == "approved"
        assert service.get_approval_request(r1.id).status == "approved"  # 历史不变

    def test_same_version_double_approval_blocked_after_revise(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001")
        r1 = service.request_approval(a.id)
        service.decide_approval(r1.id, "rejected")
        r2 = service.request_approval(a.id)  # 终态可逆: v1 再申请
        service.decide_approval(r2.id, "approved")
        # v1 已批准 → revise 前同版本再申请被拒 (禁覆盖历史)
        with pytest.raises(ProductError, match="already approved"):
            service.request_approval(a.id)

    def test_model_rejects_nonpositive_version(self):
        with pytest.raises(ValidationError):
            Artifact(id="ART-X", type="prd", version=0)

    def test_model_rejects_negative_confidence(self):
        with pytest.raises(ValidationError):
            Artifact(id="ART-X", type="prd", confidence=-0.1)
