"""tests/s7/test_s7_artifact_registry.py — S7-002 ArtifactRegistry CRUD (Unit, ADR-0039)。

覆盖 (任务清单: CRUD + archive 软删 + 关联校验 + 查询组合):
- create: 全字段/宽容类型解析/重复 id 拒绝/org.artifact.created 事件
- 关联校验 (引用完整): stage 必须存在; project 非空须存在; task 须经
  link_task 关联该项目 (项目隔离); producer_role 经 exec 注册表校验
- get/list: 未找到 NotFoundError; 软删语义 (list 默认隐藏 archived)
- update: 字段更新 + org.artifact.updated (changed_fields); archived 不可改
  (ArtifactStateError); 无变更幂等
- archive: 软删 (状态/archived_at/隐藏/仍可 get)
- query: project/stage/task/type/status 组合过滤 (AND); type/status 宽容解析

依赖: 本目录 conftest (registry/no_logger_registry fixtures + 事件库)。
"""

from __future__ import annotations

import pytest

from org.artifact import ArtifactRegistry, ArtifactStateError
from org.lifecycle import DuplicateError, NotFoundError
from org.projects import ArtifactStatus, ArtifactType

from s7_helpers import (
    event_sequence,
    last_event,
    payload_of,
    seed_project_chain,
    seed_stage,
)


@pytest.fixture
def lifecycle(project_store, logger):
    from org.projects import ProjectLifecycle

    return ProjectLifecycle(project_store, logger=logger)


def _prd_payload() -> dict:
    return {"problem": "p", "user": "u", "features": ["f1"]}


def _to_validated(registry, artifact_id: str, payload: dict) -> None:
    """把产物推到 validated (受控链 created→generated→validated) — archive 前置。

    CREATED 不能直接 ARCHIVED (转换表: 仅 validated/consumed/invalid 可归档),
    archive 相关测试须先走受控链 (与设计文档 sprint7-architecture §6 一致)。
    """
    registry.mark_generated(artifact_id)
    registry.validate(artifact_id, payload=payload)


class TestCreate:
    def test_create_minimal(self, registry, lifecycle, project_store):
        seed_stage(lifecycle)
        a = registry.create("STG-1", "prd", artifact_id="A-1")
        assert a.id == "A-1"
        assert a.stage_id == "STG-1"
        assert a.type == ArtifactType.PRD
        assert a.status == ArtifactStatus.CREATED
        assert project_store.get_artifact("A-1") is not None

    def test_create_full_fields(self, registry, lifecycle):
        seed_project_chain(lifecycle)
        a = registry.create(
            "STG-1",
            "code",
            project_id="P-1",
            task_id="T-1",
            ref="file:///src",
            producer_role="developer",
            producer_agent="ag-1",
            version="2",
            location="file:///src/patch.diff",
            metadata={"files": ["a.py"], "changes": "add x"},
            artifact_id="A-1",
        )
        assert a.project_id == "P-1"
        assert a.task_id == "T-1"
        assert a.producer_role == "developer"
        assert a.version == "2"
        assert a.location == "file:///src/patch.diff"
        assert a.metadata == {"files": ["a.py"], "changes": "add x"}

    def test_create_type_case_insensitive(self, registry, lifecycle):
        seed_stage(lifecycle)
        a = registry.create("STG-1", "DESIGN", artifact_id="A-1")
        assert a.type == ArtifactType.DESIGN

    def test_create_duplicate_id_raises(self, registry, lifecycle):
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", artifact_id="A-1")
        with pytest.raises(DuplicateError, match="artifact already exists"):
            registry.create("STG-1", "prd", artifact_id="A-1")

    def test_create_requires_stage(self, registry):
        with pytest.raises(NotFoundError, match="stage not found"):
            registry.create("STG-999", "prd")

    def test_create_project_must_exist(self, registry, lifecycle):
        seed_stage(lifecycle)
        with pytest.raises(NotFoundError, match="project not found"):
            registry.create("STG-1", "prd", project_id="P-999")

    def test_create_task_requires_project(self, registry, lifecycle):
        seed_stage(lifecycle)
        with pytest.raises(ValueError, match="task_id requires project_id"):
            registry.create("STG-1", "prd", task_id="T-1")

    def test_create_task_must_be_linked(self, registry, lifecycle):
        seed_stage(lifecycle)
        lifecycle.create_project("A", project_id="P-1")  # 项目存在但任务未关联
        with pytest.raises(NotFoundError, match="not linked to project"):
            registry.create("STG-1", "prd", project_id="P-1", task_id="T-1")

    def test_create_task_linked_ok(self, registry, lifecycle):
        seed_project_chain(lifecycle)
        a = registry.create(
            "STG-1", "prd", project_id="P-1", task_id="T-1", artifact_id="A-1"
        )
        assert a.task_id == "T-1"
        assert a.project_id == "P-1"

    def test_create_producer_role_unknown_raises(self, registry, lifecycle):
        """producer_role 未注册 → ValueError (exec 注册表单一事实源)。"""
        seed_stage(lifecycle)
        with pytest.raises(ValueError, match="unknown role"):
            registry.create("STG-1", "prd", producer_role="develoepr")

    def test_create_producer_role_valid(self, registry, lifecycle):
        seed_stage(lifecycle)
        a = registry.create(
            "STG-1", "prd", producer_role="product-manager", artifact_id="A-1"
        )
        assert a.producer_role == "product-manager"

    def test_create_event_payload_extended(self, registry, lifecycle, event_store):
        seed_project_chain(lifecycle)
        registry.create(
            "STG-1", "prd", project_id="P-1", task_id="T-1", artifact_id="A-1"
        )
        payload = payload_of(event_store, "org.artifact.created")
        assert payload["artifact_id"] == "A-1"
        assert payload["stage_id"] == "STG-1"
        assert payload["type"] == "prd"
        # S7-002 扩展字段 (向后兼容: 既有 4 字段不动, 新增可重建)
        assert payload["project_id"] == "P-1"
        assert payload["status"] == "created"
        assert payload["version"] == "1"
        # 事件顶层 project_id/task_id (审计锚点)
        ev = last_event(event_store)
        assert ev.project_id == "P-1"
        assert ev.task_id == "T-1"

    def test_logger_none_silent(self, no_logger_registry, lifecycle, event_store):
        """logger=None: artifact 域全静默 (seed_stage 自身产生 org.stage.created)。"""
        seed_stage(lifecycle)
        no_logger_registry.create("STG-1", "prd", artifact_id="A-1")
        art_seq = [
            t for t in event_sequence(event_store) if t.startswith("org.artifact.")
        ]
        assert art_seq == []


class TestGetList:
    def test_get(self, registry, lifecycle):
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", artifact_id="A-1")
        assert registry.get("A-1").id == "A-1"

    def test_get_not_found(self, registry):
        with pytest.raises(NotFoundError, match="artifact not found"):
            registry.get("A-999")

    def test_list_sorted_and_hides_archived(self, registry, lifecycle):
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", artifact_id="A-1")
        registry.create("STG-1", "design", artifact_id="A-2")
        registry.create("STG-1", "code", artifact_id="A-3")
        _to_validated(registry, "A-3", {"files": ["f.py"], "changes": "x"})
        archived = registry.archive("A-3")
        assert archived.is_archived
        assert [a.id for a in registry.list()] == ["A-1", "A-2"]
        assert [a.id for a in registry.list(include_archived=True)] == [
            "A-1", "A-2", "A-3",
        ]


class TestUpdate:
    def test_update_fields(self, registry, lifecycle, project_store):
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", ref="r1", version="1", artifact_id="A-1")
        updated = registry.update(
            "A-1", ref="r2", version="2", location="file:///x", metadata=_prd_payload()
        )
        assert updated.ref == "r2"
        assert updated.version == "2"
        assert updated.location == "file:///x"
        assert updated.metadata == _prd_payload()
        assert project_store.get_artifact("A-1").version == "2"

    def test_update_event_payload(self, registry, lifecycle, event_store):
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", artifact_id="A-1")
        registry.update("A-1", version="2", location="file:///x")
        payload = payload_of(event_store, "org.artifact.updated")
        assert payload["artifact_id"] == "A-1"
        assert payload["from_status"] == "created"
        assert payload["to_status"] == "created"  # 字段更新不改状态
        assert payload["version"] == "2"
        assert payload["changed_fields"] == ["location", "version"]

    def test_update_no_change_idempotent(self, registry, lifecycle, event_store):
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", artifact_id="A-1")
        before = len(event_store.query())
        registry.update("A-1")  # 无变更
        assert len(event_store.query()) == before  # 不发事件

    def test_update_archived_immutable(self, registry, lifecycle):
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", artifact_id="A-1")
        _to_validated(registry, "A-1", _prd_payload())
        registry.archive("A-1")
        with pytest.raises(ArtifactStateError, match="archived artifact is immutable"):
            registry.update("A-1", version="2")

    def test_update_producer_role_validated(self, registry, lifecycle):
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", artifact_id="A-1")
        updated = registry.update("A-1", producer_role="tester")
        assert updated.producer_role == "tester"

    def test_update_producer_role_unknown_raises(self, registry, lifecycle):
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", artifact_id="A-1")
        with pytest.raises(ValueError, match="unknown role"):
            registry.update("A-1", producer_role="bogus")


class TestArchiveSoftDelete:
    def test_archive_sets_terminal_state(self, registry, lifecycle):
        seed_stage(lifecycle)
        a = registry.create("STG-1", "prd", artifact_id="A-1")
        registry.mark_generated("A-1")
        registry.validate("A-1", payload=_prd_payload())
        archived = registry.archive("A-1")
        assert archived.status == ArtifactStatus.ARCHIVED
        assert archived.archived_at is not None
        assert archived.is_archived

    def test_archive_requires_validated_path(self, registry, lifecycle):
        """CREATED 不能直接 ARCHIVED (受控转换表)。"""
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", artifact_id="A-1")
        with pytest.raises(ArtifactStateError, match="invalid artifact transition"):
            registry.archive("A-1")

    def test_archive_still_gettable(self, registry, lifecycle):
        """软删可查 (审计/恢复): get 仍返回, list 默认隐藏。"""
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", artifact_id="A-1")
        _to_validated(registry, "A-1", _prd_payload())
        registry.archive("A-1")
        assert registry.get("A-1").is_archived
        assert registry.list() == []
        assert [a.id for a in registry.query(status="archived")] == ["A-1"]


class TestQuery:
    def _seed(self, registry, lifecycle):
        seed_project_chain(lifecycle, project_id="P-1", task_id="T-1")
        seed_project_chain(lifecycle, project_id="P-2", task_id="T-2", stage_id="STG-2")
        registry.create("STG-1", "prd", project_id="P-1", task_id="T-1", artifact_id="A-1")
        registry.create("STG-1", "design", project_id="P-1", task_id="T-1", artifact_id="A-2")
        registry.create("STG-2", "code", project_id="P-2", task_id="T-2", artifact_id="A-3")

    def test_query_no_filters_all(self, registry, lifecycle):
        self._seed(registry, lifecycle)
        assert [a.id for a in registry.query()] == ["A-1", "A-2", "A-3"]

    def test_query_by_project(self, registry, lifecycle):
        self._seed(registry, lifecycle)
        assert [a.id for a in registry.query(project_id="P-1")] == ["A-1", "A-2"]

    def test_query_by_stage(self, registry, lifecycle):
        self._seed(registry, lifecycle)
        assert [a.id for a in registry.query(stage_id="STG-2")] == ["A-3"]

    def test_query_by_task(self, registry, lifecycle):
        self._seed(registry, lifecycle)
        assert [a.id for a in registry.query(task_id="T-2")] == ["A-3"]

    def test_query_by_type_case_insensitive(self, registry, lifecycle):
        self._seed(registry, lifecycle)
        assert [a.id for a in registry.query(type_="DESIGN")] == ["A-2"]
        assert [a.id for a in registry.query(type_=ArtifactType.CODE)] == ["A-3"]

    def test_query_by_status(self, registry, lifecycle):
        self._seed(registry, lifecycle)
        registry.mark_generated("A-1")
        assert [a.id for a in registry.query(status="generated")] == ["A-1"]

    def test_query_and_combination(self, registry, lifecycle):
        """project + stage + type AND 组合过滤。"""
        self._seed(registry, lifecycle)
        got = registry.query(project_id="P-1", stage_id="STG-1", type_="design")
        assert [a.id for a in got] == ["A-2"]
        assert registry.query(project_id="P-1", type_="code") == []

    def test_query_hides_archived_unless_status(self, registry, lifecycle):
        seed_project_chain(lifecycle)
        registry.create("STG-1", "prd", project_id="P-1", artifact_id="A-1")
        registry.create("STG-1", "design", project_id="P-1", artifact_id="A-2")
        _to_validated(registry, "A-2", {"architecture": "a", "api": "b", "database": "c"})
        registry.archive("A-2")
        assert [a.id for a in registry.query(project_id="P-1")] == ["A-1"]
        assert [a.id for a in registry.query(project_id="P-1", status="archived")] == ["A-2"]
        assert [a.id for a in registry.query(include_archived=True)] == ["A-1", "A-2"]

    def test_query_empty_result(self, registry, lifecycle):
        seed_stage(lifecycle)
        assert registry.query(stage_id="STG-1") == []
        assert registry.query(type_="release") == []


class TestInteropWithS7001:
    def test_project_lifecycle_create_artifact_then_registry(self, lifecycle, registry):
        """S7-001 create_artifact 产物可经 Registry 流转 (共享 store 数据一致)。"""
        seed_stage(lifecycle)
        lifecycle.create_artifact("STG-1", "prd", ref="r", artifact_id="A-1")
        a = registry.get("A-1")
        assert a.status == ArtifactStatus.CREATED  # 新模型默认状态
        assert a.version == "1"
        generated = registry.mark_generated("A-1")
        assert generated.status == ArtifactStatus.GENERATED
