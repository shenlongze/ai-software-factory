"""tests/product/test_product_lifecycle_decision_chain_9d.py — 决策链 + Task 生成 + 事件链 (Phase 9d, ADR-0029)。

覆盖: 决策链 (Product → Architecture → Task Plan 三节点类型序/源锚点/产物引用),
Task 生成 (TaskStore.create, Core 零修改 — task.workflow 关联 feature-delivery,
标题含 task_plan 锚点, project 从 idea.context 推导), task 阶段前置校验
(task_store 未装配 / 决策链缺失 → 响亮报错), 事件链序 (lifecycle.started →
stage.entered → stage.completed → decision.created → lifecycle.completed),
status_viewed/templates_viewed 审计, logger=None 静默。
"""

from __future__ import annotations

import pytest

from events.models import EventType

from product.lifecycle import ProductLifecycleEngine
from product.models import DecisionType
from product.service import ProductError

from product_helpers import event_sequence, seed_artifact, seed_idea


def _make_engine(store, service=None, **kw):
    return ProductLifecycleEngine(store, service, **kw)


def _run_full_chain(engine, service, idea_id: str):
    """完整决策链: start → idea → research → prd → approval(prd) → approve →
    ui → approval(ui) → approve → architecture → task → completed。"""
    engine.start_lifecycle(idea_id)
    for artifact_type in ("research", "prd", "ui", "architecture"):
        seed_artifact(service, artifact_type, idea_id=idea_id)
    lc = engine.advance(idea_id)  # idea→research
    lc = engine.advance(idea_id)  # research→prd
    lc = engine.advance(idea_id)  # prd→approval (paused)
    req = service._store.get_request(lc.current_stage.approval_request_id)
    service.decide_approval(req.id, "approved")
    lc = engine.handle_approval_outcome(idea_id)  # approval→ui
    lc = engine.advance(idea_id)  # ui→approval(ui) (paused)
    req2 = service._store.get_request(lc.current_stage.approval_request_id)
    service.decide_approval(req2.id, "approved")
    lc = engine.handle_approval_outcome(idea_id)  # approval→architecture
    lc = engine.advance(idea_id)  # architecture→task
    return engine.advance(idea_id)  # task→completed


class TestDecisionChain:
    def test_full_chain_three_decisions_in_order(self, store, service, task_store):
        engine = _make_engine(store, service, task_store=task_store)
        idea = seed_idea(service, "决策链")
        _run_full_chain(engine, service, idea.id)
        chain = service.get_decision_chain(idea.id)
        assert [d.type for d in chain] == [
            DecisionType.PRODUCT.value,
            DecisionType.ARCHITECTURE.value,
            DecisionType.TASK_PLAN.value,
        ]
        assert [d.id for d in chain] == ["DEC-001", "DEC-002", "DEC-003"]
        assert all(d.idea_id == idea.id for d in chain)

    def test_product_decision_anchors_approval(self, store, service, task_store):
        engine = _make_engine(store, service, task_store=task_store)
        idea = seed_idea(service, "决策链")
        _run_full_chain(engine, service, idea.id)
        prod = service.get_decision_chain(idea.id)[0]
        assert prod.type == "product"
        assert prod.decision_id is not None  # 驱动决策的 ApprovalDecision id
        assert prod.source_artifact_id is not None  # 被审批的 prd Artifact
        assert prod.approved_reference is not None  # product_decision Artifact

    def test_architecture_decision_references_artifact(self, store, service, task_store):
        engine = _make_engine(store, service, task_store=task_store)
        idea = seed_idea(service, "决策链")
        _run_full_chain(engine, service, idea.id)
        arch = service.get_decision_chain(idea.id)[1]
        assert arch.type == "architecture"
        assert arch.source_artifact_id is not None  # architecture Artifact
        # 决策产物是 architecture_decision 类型 Artifact
        decisions = [a for a in service._store.list_artifacts_by_type("architecture_decision")]
        assert decisions and arch.approved_reference == decisions[-1].id

    def test_task_plan_decision_created(self, store, service, task_store):
        engine = _make_engine(store, service, task_store=task_store)
        idea = seed_idea(service, "决策链")
        _run_full_chain(engine, service, idea.id)
        tp = service.get_decision_chain(idea.id)[2]
        task_plans = [a for a in service._store.list_artifacts_by_type("task_plan")]
        assert task_plans and tp.approved_reference == task_plans[-1].id
        content = task_plans[-1].content
        assert content["product_decision"] is not None
        assert content["architecture_decision"] is not None
        assert len(content["decision_chain"]) == 3

    def test_chain_per_idea_isolated(self, store, service, task_store):
        engine = _make_engine(store, service, task_store=task_store)
        i1 = seed_idea(service, "一")
        i2 = seed_idea(service, "二")
        _run_full_chain(engine, service, i1.id)
        _run_full_chain(engine, service, i2.id)
        assert len(service.get_decision_chain(i1.id)) == 3
        assert len(service.get_decision_chain(i2.id)) == 3
        assert [d.idea_id for d in service._store.list_decision_artifacts()] == [i1.id] * 3 + [i2.id] * 3

    def test_no_decisions_before_approval(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        assert service.get_decision_chain(idea.id) == []


class TestTaskGeneration:
    def test_task_created_via_task_store(self, store, service, task_store):
        engine = _make_engine(store, service, task_store=task_store)
        idea = seed_idea(service, "任务化", context={"project": "markpad"})
        lc = _run_full_chain(engine, service, idea.id)
        tasks = task_store.list()
        assert len(tasks) == 1
        t = tasks[0]
        assert t.title.startswith("Implement 任务化 (task plan ART-")
        assert t.project == "markpad"  # idea.context 推导
        assert t.workflow == "feature-delivery"  # Core 既有字段关联
        assert t.type == "feature"
        # 阶段回填 task_id
        task_stage = lc.stages[-1]
        assert task_stage.task_id == t.id
        assert task_stage.decision_id is not None  # task_plan Artifact

    def test_task_store_missing_raises_loud(self, store, service):
        """task 阶段未装配 TaskStore → 响亮配置缺口 (不静默降级)。"""
        engine = _make_engine(store, service, task_store=None)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        for artifact_type in ("research", "prd", "ui", "architecture"):
            seed_artifact(service, artifact_type, idea_id=idea.id)
        # 构造完整决策链 (product + architecture) — 使 task 阶段走到 task_store 校验
        service.create_decision_artifact("product", decision_id="APD-1",
                                         source_artifact_id="ART-1",
                                         approved_reference="ART-2", idea_id=idea.id)
        service.create_decision_artifact("architecture", source_artifact_id="ART-3",
                                         approved_reference="ART-4", idea_id=idea.id)
        lc = engine._require_lifecycle(idea.id)
        lc.current_stage_index = 7  # task
        engine._store.save_lifecycle(lc)
        with pytest.raises(ProductError, match="needs a TaskStore"):
            engine.advance(idea.id)

    def test_task_stage_decision_chain_checked_first(self, store, service):
        """task 阶段前置校验顺序: 决策链完整性先于 TaskStore 装配 (响亮报错优先级)。"""
        engine = _make_engine(store, service, task_store=None)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        for artifact_type in ("research", "prd", "ui", "architecture"):
            seed_artifact(service, artifact_type, idea_id=idea.id)
        lc = engine._require_lifecycle(idea.id)
        lc.current_stage_index = 7  # task (决策链缺失 + task_store 缺失 → 先报决策链)
        engine._store.save_lifecycle(lc)
        with pytest.raises(ProductError, match="needs the decision chain"):
            engine.advance(idea.id)

    def test_task_stage_needs_full_decision_chain(self, store, service, task_store):
        """task 阶段前置: product + architecture 决策链缺一不可。"""
        engine = _make_engine(store, service, task_store=task_store)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        for artifact_type in ("research", "prd", "ui", "architecture"):
            seed_artifact(service, artifact_type, idea_id=idea.id)
        lc = engine._require_lifecycle(idea.id)
        lc.current_stage_index = 7  # task
        engine._store.save_lifecycle(lc)
        with pytest.raises(ProductError, match="needs the decision chain"):
            engine.advance(idea.id)

    def test_task_stage_without_task_store_loud_error(self, store, service, task_store):
        """决策链完整但 task_store 未装配 → TaskStore 配置缺口响亮报错。"""
        engine = _make_engine(store, service, task_store=None)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        for artifact_type in ("research", "prd", "ui", "architecture"):
            seed_artifact(service, artifact_type, idea_id=idea.id)
        # 构造完整决策链 (product + architecture)
        lc = engine._require_lifecycle(idea.id)
        service.create_decision_artifact("product", decision_id="APD-1",
                                         source_artifact_id="ART-1",
                                         approved_reference="ART-2", idea_id=idea.id)
        service.create_decision_artifact("architecture", source_artifact_id="ART-3",
                                         approved_reference="ART-4", idea_id=idea.id)
        lc.current_stage_index = 7
        engine._store.save_lifecycle(lc)
        with pytest.raises(ProductError, match="needs a TaskStore"):
            engine.advance(idea.id)


class TestLifecycleEvents:
    def test_start_event_sequence(self, store, event_service, logger):
        engine = _make_engine(store, event_service, logger=logger)
        idea = seed_idea(event_service)
        engine.start_lifecycle(idea.id)
        seq = event_sequence(logger.store)
        assert seq[:3] == [
            EventType.IDEA_CREATED.value,
            EventType.PRODUCT_LIFECYCLE_STARTED.value,
            EventType.PRODUCT_STAGE_ENTERED.value,
        ]
        assert seq[-1] == EventType.PRODUCT_STAGE_ENTERED.value

    def test_start_event_payload(self, store, service, logger):
        from product_helpers import payload_of

        engine = _make_engine(store, service, logger=logger)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        payload = payload_of(logger.store, EventType.PRODUCT_LIFECYCLE_STARTED.value)
        assert payload["lifecycle_id"] == "LC-001"
        assert payload["idea_id"] == idea.id
        assert payload["template_name"] == "software_project"
        assert payload["current_stage"] == "idea"

    def test_full_chain_event_order(self, store, service, logger, task_store):
        engine = _make_engine(store, service, logger=logger, task_store=task_store)
        idea = seed_idea(service, "事件链")
        _run_full_chain(engine, service, idea.id)
        seq = event_sequence(logger.store)
        # 5 事件类型链序 (核心契约): started → entered → completed → decision.created → completed
        assert EventType.PRODUCT_LIFECYCLE_STARTED.value in seq
        assert seq.count(EventType.PRODUCT_STAGE_ENTERED.value) == 8  # 8 阶段各进入一次
        assert seq.count(EventType.PRODUCT_STAGE_COMPLETED.value) == 8
        assert seq.count(EventType.PRODUCT_DECISION_CREATED.value) == 3
        assert seq[-1] == EventType.PRODUCT_LIFECYCLE_COMPLETED.value
        # 链序: decision.created 依次对应 product → architecture → task_plan
        decision_events = [e for e in seq if e == EventType.PRODUCT_DECISION_CREATED.value]
        assert len(decision_events) == 3
        # lifecycle.completed 只在最后 (终态事件单一)
        assert seq.count(EventType.PRODUCT_LIFECYCLE_COMPLETED.value) == 1

    def test_decision_created_payload(self, store, service, logger, task_store):
        from product_helpers import payload_of

        engine = _make_engine(store, service, logger=logger, task_store=task_store)
        idea = seed_idea(service, "事件链")
        _run_full_chain(engine, service, idea.id)
        payload = payload_of(logger.store, EventType.PRODUCT_DECISION_CREATED.value)
        assert payload["type"] == "task_plan"
        assert payload["idea_id"] == idea.id
        assert payload["approved_reference"] is not None

    def test_stage_completed_payload(self, store, service, logger):
        from product_helpers import payload_of

        engine = _make_engine(store, service, logger=logger)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)
        engine.advance(idea.id)
        payload = payload_of(logger.store, EventType.PRODUCT_STAGE_COMPLETED.value)
        assert payload["stage"] == "idea"
        assert payload["artifact_id"] is not None  # product_idea 产物回填

    def test_approval_events_interleave(self, store, event_service, logger):
        """approval 阶段进入 → 9c 审批链事件 (created → pending → required) 插在
        stage.entered(approval) 之后; 引擎服务须带 logger (审批事件经服务层发出)。"""
        engine = _make_engine(store, event_service, logger=logger)
        idea = seed_idea(event_service)
        engine.start_lifecycle(idea.id)
        for artifact_type in ("research", "prd"):
            seed_artifact(event_service, artifact_type, idea_id=idea.id)
        engine.advance(idea.id)
        engine.advance(idea.id)
        engine.advance(idea.id)  # → approval (paused)
        seq = event_sequence(logger.store)
        # 复用 9c 审批链 (approval.created → pending → required) 在 stage.entered(approval) 之后
        assert seq[-4:] == [
            EventType.PRODUCT_STAGE_ENTERED.value,
            EventType.APPROVAL_CREATED.value,
            EventType.APPROVAL_PENDING.value,
            EventType.APPROVAL_REQUIRED.value,
        ]

    def test_logger_none_silent(self, store, service):
        engine = _make_engine(store, service, logger=None)
        idea = seed_idea(service)
        engine.start_lifecycle(idea.id)  # 不发事件, 不抛错
        engine.advance(idea.id)
        assert engine._store.list_lifecycles()[0].status == "running"
