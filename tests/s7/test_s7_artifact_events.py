"""tests/s7/test_s7_artifact_events.py — S7-002 事件契约 (Unit, ADR-0039)。

覆盖 (任务清单: +5~6 artifact.* 事件 + payload 契约 + 向后兼容):
- org.artifact.created: 既有 4 字段不动 (向后兼容) + S7-002 扩展
  (project_id/status/version) + 事件顶层 project_id/task_id
- org.artifact.updated: from_status/to_status/changed_fields/version
- org.artifact.validated: missing/errors 明细
- org.artifact.consumed / org.artifact.archived: from/to + version
- org.artifact.failed: reason + missing/errors (审计唯一事实源)
- org.artifact.viewed: count + filters (读命令审计, ADR-0002)
- logger=None 全静默; 既有事件类型零破坏 (枚举增成员, 不删改)

依赖: 本目录 conftest (registry + 事件库 fixtures)。
"""

from __future__ import annotations

import pytest

from events.models import EventType

from org import events as org_events

from s7_helpers import (
    event_sequence,
    payload_of,
    seed_project_chain,
    seed_stage,
)


def _prd_payload() -> dict:
    return {"problem": "p", "user": "u", "features": ["f1"]}


@pytest.fixture
def lifecycle(project_store, logger):
    from org.projects import ProjectLifecycle

    return ProjectLifecycle(project_store, logger=logger)


class TestCreatedEvent:
    def test_created_payload_backward_compatible(self, registry, lifecycle, event_store):
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", ref="r", artifact_id="A-1")
        payload = payload_of(event_store, "org.artifact.created")
        # S7-001 既有 4 字段原样保留
        assert payload["artifact_id"] == "A-1"
        assert payload["stage_id"] == "STG-1"
        assert payload["type"] == "prd"
        assert payload["ref"] == "r"
        # S7-002 扩展字段
        assert payload["project_id"] == ""
        assert payload["status"] == "created"
        assert payload["version"] == "1"

    def test_created_event_top_level_ids(self, registry, lifecycle, event_store):
        seed_project_chain(lifecycle)
        registry.create(
            "STG-1", "code", project_id="P-1", task_id="T-1", artifact_id="A-1"
        )
        evs = [e for e in event_store.query() if e.type == EventType.ORG_ARTIFACT_CREATED]
        assert len(evs) == 1
        assert evs[0].project_id == "P-1"
        assert evs[0].task_id == "T-1"

    def test_created_source_org(self, registry, lifecycle, event_store):
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", artifact_id="A-1")
        evs = [e for e in event_store.query() if e.type == EventType.ORG_ARTIFACT_CREATED]
        assert evs[0].source == "org"


class TestTransitionEvents:
    def _created_generated(self, registry, lifecycle):
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", artifact_id="A-1")
        registry.mark_generated("A-1")

    def test_updated_event_reconstructs(self, registry, lifecycle, event_store):
        """字段更新事件可重建 (mark_generated 也发一条 updated → 取最后一条)。"""
        self._created_generated(registry, lifecycle)
        registry.update("A-1", version="3", location="file:///x")
        updated_events = [
            e for e in event_store.query() if e.type.value == "org.artifact.updated"
        ]
        payload = dict(updated_events[-1].payload)
        assert payload["artifact_id"] == "A-1"
        assert payload["type"] == "prd"
        assert payload["from_status"] == "generated"  # 更新时产物当前状态
        assert payload["to_status"] == "generated"    # 字段更新不改状态
        assert payload["version"] == "3"
        assert payload["changed_fields"] == ["location", "version"]

    def test_validated_event_reconstructs(self, registry, lifecycle, event_store):
        self._created_generated(registry, lifecycle)
        registry.validate("A-1", payload=_prd_payload())
        payload = payload_of(event_store, "org.artifact.validated")
        assert payload["artifact_id"] == "A-1"
        assert payload["from_status"] == "generated"
        assert payload["to_status"] == "validated"
        assert payload["missing"] == []
        assert payload["errors"] == []
        assert payload["version"] == "1"

    def test_consumed_event_reconstructs(self, registry, lifecycle, event_store):
        self._created_generated(registry, lifecycle)
        registry.validate("A-1", payload=_prd_payload())
        registry.consume("A-1")
        payload = payload_of(event_store, "org.artifact.consumed")
        assert payload["from_status"] == "validated"
        assert payload["to_status"] == "consumed"
        assert payload["version"] == "1"

    def test_failed_event_carries_detail(self, registry, lifecycle, event_store):
        self._created_generated(registry, lifecycle)
        registry.validate("A-1", payload={"problem": "p"})  # 缺 user/features
        payload = payload_of(event_store, "org.artifact.failed")
        assert payload["artifact_id"] == "A-1"
        assert payload["from_status"] == "generated"
        assert payload["to_status"] == "invalid"
        assert payload["reason"]  # 缺失字段明细
        assert payload["missing"] == ["user", "features"]
        assert payload["errors"] == []
        assert payload["version"] == "1"

    def test_archived_event_reconstructs(self, registry, lifecycle, event_store):
        self._created_generated(registry, lifecycle)
        registry.validate("A-1", payload=_prd_payload())
        registry.archive("A-1")
        payload = payload_of(event_store, "org.artifact.archived")
        assert payload["from_status"] == "validated"
        assert payload["to_status"] == "archived"
        assert payload["version"] == "1"

    def test_failed_event_result_field(self, registry, lifecycle, event_store):
        self._created_generated(registry, lifecycle)
        registry.validate("A-1", payload={})
        evs = [e for e in event_store.query() if e.type == EventType.ORG_ARTIFACT_FAILED]
        assert evs[0].result == "FAIL"
        assert evs[0].stage == "invalid"


class TestViewedEvent:
    def test_viewed_record_function_payload(self, logger, event_store):
        org_events.record_artifact_viewed(
            logger, count=3, filters={"project_id": "P-1", "status": "validated"}
        )
        payload = payload_of(event_store, "org.artifact.viewed")
        assert payload["count"] == 3
        assert payload["filters"] == {"project_id": "P-1", "status": "validated"}
        evs = [e for e in event_store.query() if e.type == EventType.ORG_ARTIFACT_VIEWED]
        assert evs[0].source == "cli"
        assert evs[0].stage == "viewed"
        assert evs[0].action == "list artifacts"

    def test_viewed_logger_none_silent(self):
        assert org_events.record_artifact_viewed(None, count=1) is None


class TestSilenceAndCompat:
    def test_logger_none_all_silent(self, no_logger_registry, lifecycle, event_store):
        """logger=None: artifact 域全静默 (seed_stage 自身产生 org.stage.created)。"""
        seed_stage(lifecycle)
        no_logger_registry.create("STG-1", "prd", artifact_id="A-1")
        no_logger_registry.mark_generated("A-1")
        art_seq = [
            t for t in event_sequence(event_store) if t.startswith("org.artifact.")
        ]
        assert art_seq == []

    def test_new_event_types_registered(self):
        """枚举新增 6 成员 (既有事件零删改 — 向后兼容)。"""
        values = {e.value for e in EventType}
        for name in (
            "org.artifact.updated",
            "org.artifact.validated",
            "org.artifact.consumed",
            "org.artifact.failed",
            "org.artifact.archived",
            "org.artifact.viewed",
        ):
            assert name in values
        assert "org.artifact.created" in values  # 既有事件不动
