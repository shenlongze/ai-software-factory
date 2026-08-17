"""S10-072 — Audit 生产链自动 + Decision Chain E2E (P0-D)。

验证: 生产 Debug 链路 (repair/validate/governance) 自动产生 Audit 事件,
Decision Chain 可重建, 无需人工 audit record。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

DP = import_module("factory-console.session.debug.debug_pipeline")


def _buggy(tmp_path: Path) -> Path:
    ws = tmp_path / "proj"
    ws.mkdir(exist_ok=True)
    (ws / "scoring.py").write_text("def score(shots):\n    return 4  # BUG\n", encoding="utf-8")
    (ws / "test_scoring.py").write_text(
        "from scoring import score\n\ndef test_score():\n    assert score(3) == 6\n", encoding="utf-8")
    return ws


class TestAuditAuto:
    def test_governance_check_auto(self, tmp_path):
        ws = _buggy(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="p", task_id="T1", agent_id="a1", error_message="timeout")
        s = p.analyze(s)
        s = p.repair(s)
        events = json.loads((ws / "audit" / "audit_events.json").read_text(encoding="utf-8"))
        assert any(e["event_type"] == "GOVERNANCE_CHECK" for e in events)
        gov = next(e for e in events if e["event_type"] == "GOVERNANCE_CHECK")
        assert gov["policy"]  # policy 决策记录

    def test_repair_auto(self, tmp_path):
        ws = _buggy(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="p", task_id="T1", agent_id="a1",
                    error_message="assert 4 == 6: expected 6 got 4")
        s = p.analyze(s)
        s = p.repair(s)
        events = json.loads((ws / "audit" / "audit_events.json").read_text(encoding="utf-8"))
        assert any(e["event_type"] == "REPAIR_COMPLETED" for e in events)

    def test_validation_auto(self, tmp_path):
        ws = _buggy(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="p", task_id="T1", agent_id="a1",
                    error_message="assert 4 == 6: expected 6 got 4")
        s = p.analyze(s)
        s = p.repair(s)
        s = p.validate(s, result=None)
        events = json.loads((ws / "audit" / "audit_events.json").read_text(encoding="utf-8"))
        assert any(e["event_type"] == "VALIDATION_PASSED" for e in events)

    def test_debug_reference_attached(self, tmp_path):
        ws = _buggy(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="p", task_id="T1", agent_id="a1",
                    error_message="assert 4 == 6: expected 6 got 4")
        s = p.analyze(s)
        s = p.repair(s)
        events = json.loads((ws / "audit" / "audit_events.json").read_text(encoding="utf-8"))
        assert all(e.get("debug_reference") for e in events)

    def test_no_manual_audit_needed(self, tmp_path):
        """生产 Debug 链不依赖人工 audit record。"""
        ws = _buggy(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="p", task_id="T1", agent_id="a1",
                    error_message="assert 4 == 6: expected 6 got 4")
        s = p.analyze(s)
        s = p.repair(s)
        s = p.validate(s, result=None)
        af = ws / "audit" / "audit_events.json"
        assert af.is_file()
        events = json.loads(af.read_text(encoding="utf-8"))
        assert len(events) >= 3  # GOVERNANCE + REPAIR + VALIDATION (全自动)


class TestEventTypes:
    def test_validation_types_registered(self):
        AE = import_module("factory-console.audit.audit_event")
        for t in ("VALIDATION_PASSED", "VALIDATION_FAILED", "REPAIR_FAILED",
                  "GOVERNANCE_CHECK", "REPAIR_COMPLETED"):
            assert t in AE.EVENT_TYPES

    def test_emit_validation_event(self, tmp_path):
        AE = import_module("factory-console.audit.audit_emitter")
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        ev = AE.AuditEmitter(workspace=ws).emit("VALIDATION_PASSED", project_id="p")
        assert ev is not None
