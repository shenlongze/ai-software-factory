"""tests/s7/test_s7_workflow_events.py — org.workflow.* 事件契约 (Unit, S7-003)。

覆盖 (任务清单: 事件契约 created/started/stage_ready/stage_started/
stage_completed/completed/failed payload + viewed 读审计):
- created:      workflow_id/project_id/name/status/stage_count; stage=status
- started:      workflow_id/project_id/from_status/to_status/status (启动 +
                paused→active 重试恢复, from_status 区分)
- stage_ready / stage_started: workflow_id/project_id/stage_id/role_id/name/status
- stage_completed: 同上 + output_artifact_ids (阶段完成审计产物引用)
- completed:    workflow_id/project_id/status/stage_count/completed_stage_count
- failed:       workflow_id/project_id/status/stage_id/reason (result=FAIL)
- viewed:       count/filters, source="cli" (读命令审计, ADR-0002)
- 事件链序: 全链 created→started→stage_ready→stage_started→stage_completed→
  completed; 失败链 created→started→stage_ready→stage_started→failed
- logger=None 全静默 (8 helper 全返回 None; 同既有 org 模式)

依赖: 本目录 conftest (project_store + logger + event_store) + s7_helpers。

"""

from __future__ import annotations

import pytest

from events.models import EventType

from org import events as org_events
from org.projects import ProjectLifecycle, StageStatus
from org.workflow import WorkflowLifecycle, WorkflowRunner, WorkflowStatus

from s7_helpers import event_sequence, payload_of


@pytest.fixture
def wlife(project_store, logger) -> WorkflowLifecycle:
    return WorkflowLifecycle(project_store, logger=logger)


@pytest.fixture
def wfid(wlife) -> str:
    ProjectLifecycle(wlife.store).create_project("Build App", project_id="P-1")
    return wlife.create_workflow("P-1", "Ship v1", workflow_id="WF-1").id


def _prd_metadata() -> dict:
    return {"problem": "p", "user": "u", "features": ["f1"]}


def _prd_executor(stage, context):
    return {"artifact_type": "prd", "ref": "file:///prd.md", "metadata": _prd_metadata()}


def _wf_events(event_store) -> list[str]:
    """只取 org.workflow.* 事件 (滤掉 org.project/org.stage/org.artifact 伴生事件)。"""
    return [t for t in event_sequence(event_store) if t.startswith("org.workflow.")]


class TestWorkflowCreated:
    def test_payload_contract(self, wlife, wfid, event_store):
        payload = payload_of(event_store, "org.workflow.created")
        assert payload["workflow_id"] == "WF-1"
        assert payload["project_id"] == "P-1"
        assert payload["name"] == "Ship v1"
        assert payload["status"] == "draft"
        assert payload["stage_count"] == 0

    def test_stage_action_source(self, wlife, wfid, event_store):
        ev = event_store.query()[-1]
        assert ev.type == EventType.ORG_WORKFLOW_CREATED
        assert ev.stage == "draft"
        assert ev.action == "create workflow"
        assert ev.result == "OK"
        assert ev.source == "org"  # 写路径事件 source="org"


class TestWorkflowStarted:
    def test_draft_start_payload(self, wlife, wfid, event_store):
        wlife.activate("WF-1")
        payload = payload_of(event_store, "org.workflow.started")
        assert payload["workflow_id"] == "WF-1"
        assert payload["project_id"] == "P-1"
        assert payload["from_status"] == "draft"
        assert payload["to_status"] == "active"

    def test_paused_resume_payload(self, wlife, wfid, event_store):
        """paused → active 恢复 (重试路径): from_status=paused (审计可区分)。"""
        wlife.activate("WF-1")
        wlife.pause("WF-1")
        wlife.activate("WF-1")
        started = [p for p in event_store.query()
                   if p.type.value == "org.workflow.started"]
        assert [p.payload["from_status"] for p in started] == ["draft", "paused"]


class TestStageEvents:
    def test_stage_ready_payload(self, wlife, wfid, event_store):
        wlife.create_stage("WF-1", "developer", name="Dev", stage_id="STG-1")
        wlife.transition_stage("STG-1", StageStatus.READY)
        payload = payload_of(event_store, "org.workflow.stage_ready")
        assert payload["workflow_id"] == "WF-1"
        assert payload["project_id"] == "P-1"
        assert payload["stage_id"] == "STG-1"
        assert payload["role_id"] == "developer"
        assert payload["name"] == "Dev"
        assert payload["status"] == "ready"

    def test_stage_started_payload(self, wlife, wfid, event_store):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        wlife.transition_stage("STG-1", StageStatus.READY)
        wlife.transition_stage("STG-1", StageStatus.RUNNING)
        payload = payload_of(event_store, "org.workflow.stage_started")
        assert payload["stage_id"] == "STG-1"
        assert payload["role_id"] == "developer"
        assert payload["status"] == "running"

    def test_stage_completed_payload_with_outputs(self, wlife, wfid, event_store):
        """stage_completed: output_artifact_ids 随事件带出 (产物引用审计)。"""
        wlife.create_stage("WF-1", "product-manager", stage_id="STG-1")

        def prd_named(stage, context):
            return {"artifact_type": "prd", "artifact_id": "A-1",
                    "ref": "file:///prd.md", "metadata": _prd_metadata()}

        WorkflowRunner(wlife, executor=prd_named).run("WF-1")
        payload = payload_of(event_store, "org.workflow.stage_completed")
        assert payload["stage_id"] == "STG-1"
        assert payload["status"] == "completed"
        assert payload["output_artifact_ids"] == ["A-1"]


class TestWorkflowCompleted:
    def test_payload_counts(self, wlife, wfid, event_store):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        WorkflowRunner(wlife, executor=_prd_executor).run("WF-1")
        payload = payload_of(event_store, "org.workflow.completed")
        assert payload["workflow_id"] == "WF-1"
        assert payload["project_id"] == "P-1"
        assert payload["status"] == "completed"
        assert payload["stage_count"] == 1
        assert payload["completed_stage_count"] == 1
        ev = event_store.query()[-1]
        assert ev.result == "OK"
        assert ev.action == "workflow completed"


class TestWorkflowFailed:
    def test_payload_stage_and_reason(self, wlife, wfid, event_store):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")

        def boom(stage, context):
            raise RuntimeError("llm timeout")

        wf = WorkflowRunner(wlife, executor=boom).run("WF-1")
        assert wf.status is WorkflowStatus.FAILED
        payload = payload_of(event_store, "org.workflow.failed")
        assert payload["workflow_id"] == "WF-1"
        assert payload["project_id"] == "P-1"
        assert payload["status"] == "failed"
        assert payload["stage_id"] == "STG-1"  # 失败定位
        assert "RuntimeError" in payload["reason"]
        ev = event_store.query()[-1]
        assert ev.result == "FAIL"
        assert ev.action == "workflow failed"


class TestWorkflowViewed:
    def test_viewed_payload_cli_source(self, logger, event_store):
        """读命令审计: source 缺省 cli (ADR-0002); payload = count/filters。"""
        org_events.record_workflow_viewed(logger, count=3, filters={"project_id": "P-1"})
        payload = payload_of(event_store, "org.workflow.viewed")
        assert payload == {"count": 3, "filters": {"project_id": "P-1"}}
        ev = event_store.query()[-1]
        assert ev.source == "cli"
        assert ev.stage == "viewed"
        assert ev.action == "view workflow"
        assert ev.result == "OK"


class TestEventChain:
    def test_full_run_sequence(self, wlife, wfid, event_store):
        """全链事件序: created→started→stage_ready→stage_started→stage_completed→completed。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        WorkflowRunner(wlife, executor=_prd_executor).run("WF-1")
        assert _wf_events(event_store) == [
            "org.workflow.created",
            "org.workflow.started",
            "org.workflow.stage_ready",
            "org.workflow.stage_started",
            "org.workflow.stage_completed",
            "org.workflow.completed",
        ]

    def test_failed_run_sequence(self, wlife, wfid, event_store):
        """失败链: created→started→stage_ready→stage_started→failed (stage 失败无独立事件)。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")

        def boom(stage, context):
            raise RuntimeError("x")

        WorkflowRunner(wlife, executor=boom).run("WF-1")
        assert _wf_events(event_store) == [
            "org.workflow.created",
            "org.workflow.started",
            "org.workflow.stage_ready",
            "org.workflow.stage_started",
            "org.workflow.failed",
        ]

    def test_blocked_run_no_workflow_terminal_event(self, wlife, wfid, event_store):
        """阻塞挂起: 不假装完成 — 无 completed/failed 事件 (保持 ACTIVE)。"""
        wlife.create_stage("WF-1", "developer", input_artifacts=["A-1"], stage_id="STG-1")
        wlife.registry.create("STG-1", "prd", project_id="P-1", artifact_id="A-1")
        wf = WorkflowRunner(wlife, executor=_prd_executor).run("WF-1")
        assert wf.status is WorkflowStatus.ACTIVE
        assert "org.workflow.completed" not in _wf_events(event_store)
        assert "org.workflow.failed" not in _wf_events(event_store)


class TestLoggerNone:
    def test_all_helpers_silent(self):
        """logger=None: 8 个 workflow helper 全返回 None (同既有 org 模式)。"""
        workflow = None
        stage = None
        assert org_events.record_workflow_created(None, workflow=workflow) is None
        assert org_events.record_workflow_started(None, workflow=workflow, from_status="draft") is None
        assert org_events.record_workflow_stage_ready(None, workflow=workflow, stage=stage) is None
        assert org_events.record_workflow_stage_started(None, workflow=workflow, stage=stage) is None
        assert org_events.record_workflow_stage_completed(None, workflow=workflow, stage=stage) is None
        assert org_events.record_workflow_completed(None, workflow=workflow) is None
        assert org_events.record_workflow_failed(None, workflow=workflow, stage_id="", reason="r") is None
        assert org_events.record_workflow_viewed(None, count=0) is None

    def test_lifecycle_silent_without_logger(self, project_store, db_path):
        """logger=None 生命周期: 零事件落库 (同既有 org 模式)。"""
        from events.store import EventStore

        store = EventStore(db_path)
        try:
            silent = WorkflowLifecycle(project_store, logger=None)
            ProjectLifecycle(project_store).create_project("P", project_id="P-1")
            silent.create_workflow("P-1", "W", workflow_id="WF-1")
            assert store.query() == []  # logger=None → 无任何事件
        finally:
            store.close()
