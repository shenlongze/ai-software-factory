"""tests/s7/test_s7_artifact_lifecycle.py — S7-002 生命周期状态机 (Unit, ADR-0039)。

覆盖 (任务清单: CREATED→GENERATED→VALIDATED→CONSUMED→ARCHIVED+INVALID,
受控转换表, 转换事件 audit):
- 合法主链: created→generated→validated→consumed→archived 全程 + 每转换事件
- 失败路径: fail → invalid (invalid_reason 落库) + org.artifact.failed
- 恢复: invalid→generated (重生成) / invalid→archived (废弃)
- 非法跳转全拒绝 (ArtifactStateError): created→archived/validated/consumed,
  generated→consumed/archived, validated→generated, invalid→validated/consumed,
  archived 终态
- 幂等: 同状态不重复发事件; validate 已 validated 幂等
- validate 契约驱动: 通过→validated (missing/errors 空) / 失败→invalid
  (failed 事件携带 missing/errors 明细)

依赖: 本目录 conftest (registry + 事件库 fixtures)。
"""

from __future__ import annotations

import pytest

from org.artifact import ArtifactStateError
from org.lifecycle import NotFoundError
from org.projects import ArtifactStatus

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


def _created(registry, lifecycle, artifact_id: str = "A-1"):
    seed_stage(lifecycle)
    return registry.create("STG-1", "prd", artifact_id=artifact_id)


class TestLegalChain:
    def test_full_chain_to_archived(self, registry, lifecycle):
        a = _created(registry, lifecycle)
        a = registry.mark_generated("A-1")
        assert a.status == ArtifactStatus.GENERATED
        a, result = registry.validate("A-1", payload=_prd_payload())
        assert a.status == ArtifactStatus.VALIDATED and result.ok
        a = registry.consume("A-1")
        assert a.status == ArtifactStatus.CONSUMED
        a = registry.archive("A-1")
        assert a.status == ArtifactStatus.ARCHIVED
        assert a.archived_at is not None

    def test_chain_event_sequence(self, registry, lifecycle, event_store):
        _created(registry, lifecycle)
        registry.mark_generated("A-1")
        registry.validate("A-1", payload=_prd_payload())
        registry.consume("A-1")
        registry.archive("A-1")
        # seed_stage 自身产生 org.stage.created — 只断言 artifact 域转换序列
        seq = [t for t in event_sequence(event_store) if t.startswith("org.artifact.")]
        assert seq == [
            "org.artifact.created",
            "org.artifact.updated",      # →generated
            "org.artifact.validated",
            "org.artifact.consumed",
            "org.artifact.archived",
        ]

    def test_generated_transition_uses_updated_event(self, registry, lifecycle, event_store):
        _created(registry, lifecycle)
        registry.mark_generated("A-1")
        payload = payload_of(event_store, "org.artifact.updated")
        assert payload["artifact_id"] == "A-1"
        assert payload["from_status"] == "created"
        assert payload["to_status"] == "generated"
        assert payload["changed_fields"] == ["status"]

    def test_validated_event_payload(self, registry, lifecycle, event_store):
        _created(registry, lifecycle)
        registry.mark_generated("A-1")
        registry.validate("A-1", payload=_prd_payload())
        payload = payload_of(event_store, "org.artifact.validated")
        assert payload["artifact_id"] == "A-1"
        assert payload["from_status"] == "generated"
        assert payload["to_status"] == "validated"
        assert payload["missing"] == []
        assert payload["errors"] == []

    def test_consumed_event_payload(self, registry, lifecycle, event_store):
        _created(registry, lifecycle)
        registry.mark_generated("A-1")
        registry.validate("A-1", payload=_prd_payload())
        registry.consume("A-1")
        payload = payload_of(event_store, "org.artifact.consumed")
        assert payload["artifact_id"] == "A-1"
        assert payload["from_status"] == "validated"
        assert payload["to_status"] == "consumed"

    def test_archived_event_payload(self, registry, lifecycle, event_store):
        _created(registry, lifecycle)
        registry.mark_generated("A-1")
        registry.validate("A-1", payload=_prd_payload())
        registry.archive("A-1")
        payload = payload_of(event_store, "org.artifact.archived")
        assert payload["artifact_id"] == "A-1"
        assert payload["from_status"] == "validated"
        assert payload["to_status"] == "archived"

    def test_consume_requires_validated(self, registry, lifecycle):
        _created(registry, lifecycle)
        registry.mark_generated("A-1")
        with pytest.raises(ArtifactStateError, match="invalid artifact transition"):
            registry.consume("A-1")  # generated 未 validated 不可消费


class TestFailureAndRecovery:
    def test_fail_sets_invalid_with_reason(self, registry, lifecycle):
        _created(registry, lifecycle)
        a = registry.fail("A-1", reason="generation crashed")
        assert a.status == ArtifactStatus.INVALID
        assert a.invalid_reason == "generation crashed"

    def test_failed_event_payload(self, registry, lifecycle, event_store):
        _created(registry, lifecycle)
        registry.fail("A-1", reason="boom")
        payload = payload_of(event_store, "org.artifact.failed")
        assert payload["artifact_id"] == "A-1"
        assert payload["from_status"] == "created"
        assert payload["to_status"] == "invalid"
        assert payload["reason"] == "boom"
        assert payload["missing"] == []
        assert payload["errors"] == []

    def test_invalid_can_regenerate(self, registry, lifecycle):
        _created(registry, lifecycle)
        registry.fail("A-1", reason="boom")
        a = registry.mark_generated("A-1")
        assert a.status == ArtifactStatus.GENERATED

    def test_invalid_can_be_discarded(self, registry, lifecycle):
        _created(registry, lifecycle)
        registry.fail("A-1", reason="boom")
        a = registry.archive("A-1")
        assert a.status == ArtifactStatus.ARCHIVED

    def test_validate_failure_to_invalid_with_detail(self, registry, lifecycle, event_store):
        _created(registry, lifecycle)
        a, result = registry.validate("A-1", payload={"problem": "p"})  # 缺 user/features
        assert a.status == ArtifactStatus.INVALID
        assert not result.ok
        assert result.missing == ["user", "features"]
        payload = payload_of(event_store, "org.artifact.failed")
        assert payload["missing"] == ["user", "features"]
        assert payload["to_status"] == "invalid"
        assert a.invalid_reason  # reason 落库 (缺失字段明细)

    def test_validate_rule_failure_to_invalid(self, registry, lifecycle):
        _created(registry, lifecycle)
        a, result = registry.validate(
            "A-1", payload={"problem": "p", "user": "u", "features": []}
        )
        assert a.status == ArtifactStatus.INVALID
        assert not result.ok
        assert result.missing == []
        assert any("features" in e for e in result.errors)

    def test_validate_uses_stored_metadata_when_no_payload(self, registry, lifecycle):
        """payload 缺省用产物 metadata (创建/更新时写入的契约载荷)。"""
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", metadata=_prd_payload(), artifact_id="A-1")
        registry.mark_generated("A-1")
        a, result = registry.validate("A-1")
        assert result.ok and a.status == ArtifactStatus.VALIDATED


class TestIllegalTransitions:
    @pytest.mark.parametrize(
        "setup,to_status",
        [
            ("created", "archived"),    # 任务硬性要求: CREATED 不能直接 ARCHIVED
            ("created", "validated"),   # 须经 generated
            ("created", "consumed"),
            ("generated", "consumed"),  # 须经 validated
            ("generated", "archived"),
            ("validated", "generated"),  # 不可回退
            ("invalid", "validated"),   # 失败须先重生成
            ("invalid", "consumed"),
        ],
    )
    def test_illegal_jumps_rejected(self, registry, lifecycle, setup, to_status):
        seed_stage(lifecycle)
        registry.create("STG-1", "prd", artifact_id="A-1")
        if setup == "generated":
            registry.mark_generated("A-1")
        elif setup == "validated":
            registry.mark_generated("A-1")
            registry.validate("A-1", payload=_prd_payload())
        elif setup == "invalid":
            registry.fail("A-1", reason="boom")
        with pytest.raises(ArtifactStateError, match="invalid artifact transition"):
            registry.transition("A-1", to_status)

    def test_archived_is_terminal(self, registry, lifecycle):
        _created(registry, lifecycle)
        registry.mark_generated("A-1")
        registry.validate("A-1", payload=_prd_payload())
        registry.archive("A-1")
        for target in ("generated", "validated", "consumed", "invalid"):
            with pytest.raises(ArtifactStateError, match="invalid artifact transition"):
                registry.transition("A-1", target)

    def test_transition_target_parse_case_insensitive(self, registry, lifecycle):
        _created(registry, lifecycle)
        a = registry.transition("A-1", "GENERATED")
        assert a.status == ArtifactStatus.GENERATED

    def test_transition_unknown_status_raises(self, registry, lifecycle):
        _created(registry, lifecycle)
        with pytest.raises(ValueError, match="invalid artifact status"):
            registry.transition("A-1", "bogus")

    def test_transition_not_found_artifact(self, registry):
        with pytest.raises(NotFoundError, match="artifact not found"):
            registry.transition("A-999", "generated")


class TestIdempotency:
    def test_same_state_no_event(self, registry, lifecycle, event_store):
        _created(registry, lifecycle)
        registry.mark_generated("A-1")
        before = len(event_store.query())
        registry.transition("A-1", "generated")  # 幂等
        assert len(event_store.query()) == before

    def test_validate_validated_idempotent(self, registry, lifecycle, event_store):
        _created(registry, lifecycle)
        registry.mark_generated("A-1")
        registry.validate("A-1", payload=_prd_payload())
        before = len(event_store.query())
        a, result = registry.validate("A-1", payload=_prd_payload())
        assert result.ok
        assert a.status == ArtifactStatus.VALIDATED
        assert len(event_store.query()) == before  # 不重复发事件

    def test_validate_invalid_idempotent(self, registry, lifecycle, event_store):
        _created(registry, lifecycle)
        registry.validate("A-1", payload={})  # →invalid
        before = len(event_store.query())
        a, result = registry.validate("A-1", payload={})
        assert not result.ok
        assert a.status == ArtifactStatus.INVALID
        assert len(event_store.query()) == before
