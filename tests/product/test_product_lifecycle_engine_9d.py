"""tests/product/test_product_lifecycle_engine_9d.py — ProductLifecycleEngine 编排 (Phase 9d, ADR-0029)。

覆盖: start (实例/首阶段/重复启动/idea 缺失/模板缺失), advance 推进
(artifact_generation 前置产物校验 / approval 阶段须经审批 / 非 running 拒推),
approval 暂停 (进入即 paused + pending 请求回填), 审批终态联动
(handle_approval_outcome: approved 推进 / rejected 停留 / 无生命周期 no-op),
手动 pause/resume, 全链 completed (状态 + completed_at + next_actions),
status 快照形状 (current_stage/pending_approval/artifacts/decisions/next_actions)。
"""

from __future__ import annotations

import pytest

from product.lifecycle import ProductLifecycleEngine
from product.models import LifecycleStatus, StageKind
from product.service import ProductError, ProductNotFoundError

from product_helpers import seed_artifact, seed_idea


def _make_engine(store, service=None, **kw):
    return ProductLifecycleEngine(store, service, **kw)


def _advance_to_approval(engine, service, idea):
    """idea → research → prd → approval(prd) paused (各产物就位)。"""
    assert engine.advance(idea.id).current_stage.name == "research"
    seed_artifact(service, "research", idea_id=idea.id)
    assert engine.advance(idea.id).current_stage.name == "prd"
    seed_artifact(service, "prd", idea_id=idea.id)
    lc = engine.advance(idea.id)
    assert lc.current_stage.name == "approval"
    assert lc.current_stage.kind == StageKind.APPROVAL.value
    assert lc.status == LifecycleStatus.PAUSED.value
    return lc


class TestStart:
    def test_start_creates_running_lifecycle(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        lc = engine.start_lifecycle(idea.id)
        assert lc.id.startswith("LC-")
        assert lc.idea_id == idea.id
        assert lc.template_name == "software_project"
        assert lc.status == LifecycleStatus.RUNNING.value
        assert lc.current_stage_index == 0
        assert lc.current_stage.name == "idea"
        assert lc.current_stage.status == "running"
        assert lc.current_stage.entered_at is not None
        assert lc.completed_at is None

    def test_start_enters_first_stage_only(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        lc = engine.start_lifecycle(idea.id)
        completed = [s for s in lc.stages if s.status == "completed"]
        assert completed == []  # 不自动推进 — 每步产物/审批由用户驱动

    def test_start_missing_idea_raises(self, store, service):
        engine = _make_engine(store, service)
        with pytest.raises(ProductNotFoundError, match="idea not found"):
            engine.start_lifecycle("PI-999")

    def test_start_duplicate_raises(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        with pytest.raises(ProductError, match="already started"):
            engine.start_lifecycle(idea.id)

    def test_start_second_idea_gets_next_id(self, store, service):
        engine = _make_engine(store, service)
        i1 = seed_idea(service, "一")
        i2 = seed_idea(service, "二")
        lc1 = engine.start_lifecycle(i1.id)
        lc2 = engine.start_lifecycle(i2.id)
        assert lc2.id != lc1.id
        assert engine._store.list_lifecycles() == [lc1, lc2]

    def test_start_unknown_template_raises(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        with pytest.raises(ProductNotFoundError, match="no lifecycle template"):
            engine.start_lifecycle(idea.id, template="nope")

    def test_started_lifecycle_persisted(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        reloaded = ProductLifecycleEngine(store, service)
        assert reloaded._store.get_lifecycle_by_idea(idea.id).id == "LC-001"


class TestAdvance:
    def test_advance_idea_to_research(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        lc = engine.advance(idea.id)
        assert lc.current_stage.name == "research"
        assert lc.current_stage.status == "running"
        assert lc.status == LifecycleStatus.RUNNING.value
        assert lc.stages[0].status == "completed"
        assert lc.stages[0].artifact_id is not None  # 产物回填 (product_idea)

    def test_advance_requires_artifact(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        engine.advance(idea.id)  # → research
        with pytest.raises(ProductError, match="needs a 'research' artifact"):
            engine.advance(idea.id)

    def test_advance_on_approval_stage_raises(self, store, service):
        """approval 阶段 (running 态 — 手动恢复后仍停留) → advance 响亮报错
        (approval 阶段只能经审批决定推进, 不响应手动 advance)。"""
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        _advance_to_approval(engine, service, idea)
        engine.resume(idea.id)  # 手动恢复 → running, 但当前阶段仍是 approval
        with pytest.raises(ProductError, match="advance via approval"):
            engine.advance(idea.id)

    def test_advance_when_paused_raises(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        _advance_to_approval(engine, service, idea)
        with pytest.raises(ProductError, match="is not running"):
            engine.advance(idea.id)

    def test_advance_missing_lifecycle_raises(self, store, service):
        engine = _make_engine(store, service)
        with pytest.raises(ProductNotFoundError, match="no product lifecycle"):
            engine.advance("PI-999")

    def test_advance_after_completed_raises(self, store, service, task_store):
        engine = _make_engine(store, service, task_store=task_store)
        idea = seed_idea(service, "全链")
        self._seed_and_advance_all(engine, service, idea)
        with pytest.raises(ProductError, match="is not running"):
            engine.advance(idea.id)

    def _seed_and_advance_all(self, engine, service, idea):
        engine.start_lifecycle(idea.id)
        for artifact_type in ("research", "prd", "ui", "architecture"):
            seed_artifact(service, artifact_type, idea_id=idea.id)
        # idea → research → prd → approval(prd) → [decide] → ui → approval(ui)
        # → [decide] → architecture → [advance] → task → [advance] → completed
        lc = engine.advance(idea.id)  # idea→research
        lc = engine.advance(idea.id)  # research→prd
        lc = engine.advance(idea.id)  # prd→approval (paused)
        req = service._store.get_request(lc.current_stage.approval_request_id)
        service.decide_approval(req.id, "approved")
        lc = engine.handle_approval_outcome(idea.id)  # approval→ui
        lc = engine.advance(idea.id)  # ui→approval(ui) (paused)
        req2 = service._store.get_request(lc.current_stage.approval_request_id)
        service.decide_approval(req2.id, "approved")
        lc = engine.handle_approval_outcome(idea.id)  # approval→architecture
        lc = engine.advance(idea.id)  # architecture→task
        return engine.advance(idea.id)  # task→completed

    def test_advance_decision_stage_needs_product_decision_first(self, store, service):
        """architecture 阶段前置: 源产物 + Product Decision 链完整才可推进。"""
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        for artifact_type in ("research", "prd", "ui", "architecture"):
            seed_artifact(service, artifact_type, idea_id=idea.id)
        # 不批准 prd 审批, 直接把当前阶段推进到 architecture (构造: 手工改索引)
        lc = engine._require_lifecycle(idea.id)
        lc.current_stage_index = lc.stages.index(lc.stages[6])  # architecture
        engine._store.save_lifecycle(lc)
        with pytest.raises(ProductError, match="needs the Product Decision"):
            engine.advance(idea.id)


class TestApprovalPauseAndOutcome:
    def test_approval_stage_pauses_and_requests(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        lc = _advance_to_approval(engine, service, idea)
        assert lc.status == LifecycleStatus.PAUSED.value
        request = service._store.get_request(lc.current_stage.approval_request_id)
        assert request is not None
        assert request.status == "pending"
        assert request.gate == "prd"

    def test_approval_stage_reuses_existing_pending(self, store, service):
        """9b 生成已自动申请审批 → 进入 approval 阶段复用 pending 请求 (幂等)。"""
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        engine.advance(idea.id)
        seed_artifact(service, "research", idea_id=idea.id)
        engine.advance(idea.id)
        prd = seed_artifact(service, "prd", idea_id=idea.id)
        existing = service.request_approval(prd.id, by="generator")
        lc = engine.advance(idea.id)
        assert lc.current_stage.approval_request_id == existing.id  # 复用不重申请
        assert service._store.list_requests() == [existing]

    def test_handle_approval_outcome_approved_advances(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        lc = _advance_to_approval(engine, service, idea)
        req = service._store.get_request(lc.current_stage.approval_request_id)
        service.decide_approval(req.id, "approved", by="pm")
        lc2 = engine.handle_approval_outcome(idea.id)
        assert lc2.current_stage.name == "ui"
        assert lc2.status == LifecycleStatus.RUNNING.value
        assert lc2.stages[3].status == "completed"

    def test_handle_approval_outcome_rejected_stays_paused(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        lc = _advance_to_approval(engine, service, idea)
        req = service._store.get_request(lc.current_stage.approval_request_id)
        service.decide_approval(req.id, "rejected", comment="重做")
        lc2 = engine.handle_approval_outcome(idea.id)
        assert lc2.status == LifecycleStatus.PAUSED.value  # 停留 (修改后重新审批)
        assert lc2.stages[3].status == "running"  # 阶段未完成
        assert lc2.current_stage.name == "approval"

    def test_handle_approval_outcome_pending_noop(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        _advance_to_approval(engine, service, idea)
        assert engine.handle_approval_outcome(idea.id).status == LifecycleStatus.PAUSED.value

    def test_handle_approval_outcome_no_lifecycle_none(self, store, service):
        engine = _make_engine(store, service)
        assert engine.handle_approval_outcome("PI-999") is None
        assert engine.handle_approval_outcome(None) is None

    def test_handle_approval_outcome_non_approval_stage_noop(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        lc = engine.handle_approval_outcome(idea.id)  # 当前 idea 阶段非 approval
        assert lc.current_stage.name == "idea"


class TestManualPauseResume:
    def test_pause_running_to_paused(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        lc = engine.pause(idea.id, reason="manual")
        assert lc.status == LifecycleStatus.PAUSED.value
        assert engine._require_lifecycle(idea.id).status == LifecycleStatus.PAUSED.value

    def test_pause_paused_raises(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        engine.pause(idea.id)
        with pytest.raises(ProductError, match="cannot pause"):
            engine.pause(idea.id)

    def test_pause_completed_raises(self, store, service, task_store):
        engine = _make_engine(store, service, task_store=task_store)
        idea = seed_idea(service, "全链")
        TestAdvance()._seed_and_advance_all(engine, service, idea)
        with pytest.raises(ProductError, match="cannot pause"):
            engine.pause(idea.id)

    def test_resume_paused_to_running(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        engine.pause(idea.id)
        lc = engine.resume(idea.id)
        assert lc.status == LifecycleStatus.RUNNING.value
        assert lc.current_stage.name == "idea"  # 停留当前阶段

    def test_resume_running_raises(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        with pytest.raises(ProductError, match="not paused"):
            engine.resume(idea.id)

    def test_resume_missing_lifecycle_raises(self, store, service):
        engine = _make_engine(store, service)
        with pytest.raises(ProductNotFoundError, match="no product lifecycle"):
            engine.resume("PI-999")

    def test_paused_advance_requires_resume(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        engine.pause(idea.id)
        with pytest.raises(ProductError, match="resume it first"):
            engine.advance(idea.id)


class TestCompleted:
    def test_full_chain_completes(self, store, service, task_store):
        engine = _make_engine(store, service, task_store=task_store)
        idea = seed_idea(service, "全链")
        TestAdvance()._seed_and_advance_all(engine, service, idea)
        lc = engine._require_lifecycle(idea.id)
        assert lc.status == LifecycleStatus.COMPLETED.value
        assert lc.completed_at is not None
        assert all(s.status == "completed" for s in lc.stages)

    def test_completed_next_actions(self, store, service, task_store):
        engine = _make_engine(store, service, task_store=task_store)
        idea = seed_idea(service, "全链")
        TestAdvance()._seed_and_advance_all(engine, service, idea)
        actions = engine.status(idea.id)["next_actions"]
        assert actions == ["lifecycle completed — tasks are ready for Core Workflow execution"]


class TestStatusSnapshot:
    def test_status_current_stage_and_pending(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        snap = engine.status(idea.id)
        assert snap["lifecycle"]["id"] == "LC-001"
        assert snap["current_stage"]["name"] == "idea"
        assert snap["pending_approval"] is None
        assert snap["next_actions"][0].startswith("generate product_idea artifact")

    def test_status_pending_approval_present(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        lc = _advance_to_approval(engine, service, idea)
        snap = engine.status(idea.id)
        assert snap["current_stage"]["name"] == "approval"
        assert snap["pending_approval"]["id"] == lc.current_stage.approval_request_id
        assert snap["pending_approval"]["status"] == "pending"
        assert snap["next_actions"][0].startswith("decide approval")

    def test_status_artifacts_and_decisions(self, store, service, task_store):
        engine = _make_engine(store, service, task_store=task_store)
        idea = seed_idea(service, "全链")
        TestAdvance()._seed_and_advance_all(engine, service, idea)
        snap = engine.status(idea.id)
        types = [a["type"] for a in snap["artifacts"]]
        assert "product_idea" in types and "research" in types
        assert "prd" in types and "ui" in types and "architecture" in types
        assert [d["type"] for d in snap["decisions"]] == ["product", "architecture", "task_plan"]
        assert snap["current_stage"] is None  # completed → 无当前阶段

    def test_status_missing_lifecycle_raises(self, store, service):
        engine = _make_engine(store, service)
        with pytest.raises(ProductNotFoundError, match="no product lifecycle"):
            engine.status("PI-999")

    def test_status_decision_stage_next_action(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        for artifact_type in ("research", "prd", "ui", "architecture"):
            seed_artifact(service, artifact_type, idea_id=idea.id)
        lc = engine._require_lifecycle(idea.id)
        # 直接跳到 architecture 阶段 (decision): 前置 Product Decision 缺失时
        # status 仍可读 (只读不校验), next_actions 给出推进指令
        lc.current_stage_index = 6
        engine._store.save_lifecycle(lc)
        snap = engine.status(idea.id)
        assert snap["current_stage"]["kind"] == "decision"
        assert snap["next_actions"][0].startswith("advance to produce architecture decision")
