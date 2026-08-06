"""test_provider_events_8b1.py — provider.* 事件 payload 增量 (Phase 8B-1, ADR-0023)。

Phase 8B-1 增强 (providers/events.py): record_provider_selected 增 execution_id +
selection_source (payload 键 source); record_provider_execution_* 增 execution_id —
全部可选增量 kwargs, Phase 8A 载荷契约零破坏 (不带增量参数时 payload 不含新键)。
本文件覆盖增量键 + 回归兼容 (logger None → None / 旧键形状不变)。
"""

from __future__ import annotations

from events.models import EventType

from providers.events import (
    record_provider_execution_completed,
    record_provider_execution_failed,
    record_provider_execution_started,
    record_provider_selected,
)


class TestProviderSelectedIncrements:
    def test_execution_id_in_payload(self, logger):
        ev = record_provider_selected(
            logger, provider_id="hermes", execution_id="EX-001",
            selection_source="project", source="cli",
        )
        assert ev is not None
        assert ev.payload["provider_id"] == "hermes"
        assert ev.payload["execution_id"] == "EX-001"

    def test_selection_source_maps_to_payload_source(self, logger):
        ev = record_provider_selected(
            logger, provider_id="hermes", selection_source="explicit", source="cli",
        )
        assert ev.payload["source"] == "explicit"

    def test_event_source_is_cli_param(self, logger):
        ev = record_provider_selected(
            logger, provider_id="hermes", source="cli",
        )
        assert ev.source == "cli"

    def test_stage_defaults_to_selected(self, logger):
        ev = record_provider_selected(logger, provider_id="hermes")
        assert ev.stage == "selected"
        assert ev.type is EventType.PROVIDER_SELECTED

    def test_no_extras_keeps_legacy_payload(self, logger):
        """Phase 8A 回归: 不带增量参数 → payload 不含 execution_id/source 键。"""
        ev = record_provider_selected(logger, provider_id="hermes", model="m1")
        assert "execution_id" not in ev.payload
        assert "source" not in ev.payload
        assert ev.payload["model"] == "m1"

    def test_model_and_default_passthrough(self, logger):
        ev = record_provider_selected(
            logger, provider_id="hermes", model="m1", default=True, stage="default",
        )
        assert ev.payload["model"] == "m1"
        assert ev.payload["default"] is True

    def test_logger_none_returns_none(self):
        assert record_provider_selected(
            None, provider_id="hermes", execution_id="EX-001",
        ) is None


class TestProviderExecutionStartedIncrements:
    def test_execution_id_in_payload(self, logger):
        ev = record_provider_execution_started(
            logger, provider_id="hermes", execution_id="EX-001", source="cli",
        )
        assert ev.payload["execution_id"] == "EX-001"
        assert ev.payload["provider_id"] == "hermes"

    def test_no_execution_id_keeps_legacy_payload(self, logger):
        ev = record_provider_execution_started(logger, provider_id="hermes", model="m1")
        assert "execution_id" not in ev.payload
        assert ev.payload["model"] == "m1"

    def test_request_id_passthrough(self, logger):
        ev = record_provider_execution_started(
            logger, provider_id="hermes", request_id="REQ-9",
        )
        assert ev.payload["request_id"] == "REQ-9"

    def test_stage_running_and_type(self, logger):
        ev = record_provider_execution_started(logger, provider_id="hermes")
        assert ev.stage == "running"
        assert ev.type is EventType.PROVIDER_EXECUTION_STARTED

    def test_logger_none_returns_none(self):
        assert record_provider_execution_started(
            None, provider_id="hermes", execution_id="EX-001",
        ) is None


class TestProviderExecutionCompletedIncrements:
    def test_execution_id_in_payload(self, logger):
        ev = record_provider_execution_completed(
            logger, provider_id="hermes", execution_id="EX-001", source="cli",
        )
        assert ev.payload["execution_id"] == "EX-001"

    def test_usage_passthrough(self, logger):
        ev = record_provider_execution_completed(
            logger, provider_id="hermes", usage={"tokens": 42},
        )
        assert ev.payload["usage"] == {"tokens": 42}

    def test_no_usage_omits_key(self, logger):
        ev = record_provider_execution_completed(logger, provider_id="hermes")
        assert "usage" not in ev.payload

    def test_stage_completed_and_result_ok(self, logger):
        ev = record_provider_execution_completed(logger, provider_id="hermes")
        assert ev.stage == "completed"
        assert ev.result == "OK"
        assert ev.type is EventType.PROVIDER_EXECUTION_COMPLETED

    def test_logger_none_returns_none(self):
        assert record_provider_execution_completed(
            None, provider_id="hermes", execution_id="EX-001",
        ) is None


class TestProviderExecutionFailedIncrements:
    def test_execution_id_and_error_in_payload(self, logger):
        ev = record_provider_execution_failed(
            logger, provider_id="hermes", error="boom", execution_id="EX-001", source="cli",
        )
        assert ev.payload["execution_id"] == "EX-001"
        assert ev.payload["error"] == "boom"

    def test_no_execution_id_keeps_legacy_payload(self, logger):
        ev = record_provider_execution_failed(logger, provider_id="hermes", error="boom")
        assert "execution_id" not in ev.payload
        assert ev.payload["error"] == "boom"

    def test_stage_failed_and_result_error(self, logger):
        ev = record_provider_execution_failed(logger, provider_id="hermes", error="boom")
        assert ev.stage == "failed"
        assert ev.result == "ERROR"
        assert ev.type is EventType.PROVIDER_EXECUTION_FAILED

    def test_model_passthrough(self, logger):
        ev = record_provider_execution_failed(
            logger, provider_id="hermes", error="boom", model="m1",
        )
        assert ev.payload["model"] == "m1"

    def test_logger_none_returns_none(self):
        assert record_provider_execution_failed(
            None, provider_id="hermes", error="boom", execution_id="EX-001",
        ) is None
