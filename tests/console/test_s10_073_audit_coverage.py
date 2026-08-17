"""S10-073 — Audit 覆盖 + Decision Chain E2E (P0-B)。

验证: 生产链 15/16 阶段自动 Audit (TOOL 需侵入 AgentRuntime, 标记 PARTIAL),
Decision Chain 自动产生可查询, 失败路径也有事件。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from importlib import import_module


def _emit_calls() -> set:
    emit = set()
    for f in sorted(list((Path("/Users/Shared/work/ai-software-factory/factory-console").rglob("*.py")))):
        if "test" in str(f) or "__pycache__" in str(f):
            continue
        for m in re.finditer(r'emit\(\s*"([A-Z_]+)"', f.read_text(encoding="utf-8", errors="ignore")):
            emit.add(m.group(1))
    return emit


STAGES = {
    "DISCOVERY": ["DISCOVERY_STARTED", "DISCOVERY_COMPLETED", "DISCOVERY_CONFIRMED"],
    "PRODUCT": ["PRODUCT_CREATED"],
    "INTELLIGENCE": ["PRODUCT_INTELLIGENCE"],
    "PLAN": ["PLAN_CREATED", "PLAN_CHANGED"],
    "AGENT": ["AGENT_STARTED", "AGENT_COMPLETED", "AGENT_ASSIGNED", "AGENT_DECISION"],
    "TASK": ["TASK_CREATED", "TASK_STARTED", "TASK_COMPLETED", "TASK_FAILED"],
    "EXECUTION": ["TASK_STARTED", "AGENT_STARTED"],
    "TOOL": ["TOOL_CALL"],
    "CODE": ["ARTIFACT_CREATED", "CODE_CHANGED"],
    "TEST": ["TEST_STARTED", "TEST_FAILED", "TEST_PASSED"],
    "DEBUG": ["DEBUG_STARTED"],
    "REPAIR": ["REPAIR_STARTED", "REPAIR_COMPLETED", "REPAIR_FAILED"],
    "GOVERNANCE": ["GOVERNANCE_CHECK", "BUDGET_WARNING", "BUDGET_BLOCKED"],
    "REVIEW": ["REVIEW_REQUESTED", "REVIEW_APPROVED", "REVIEW_REJECTED"],
    "MEMORY": ["MEMORY_LEARNED", "MEMORY_RETRIEVED"],
    "DELIVERY": ["PROJECT_DELIVERED", "DELIVERY_CREATED"],
}


class TestAuditCoverage:
    def test_15_of_16_stages(self):
        emitted = _emit_calls()
        covered = [s for s, evs in STAGES.items() if any(e in emitted for e in evs)]
        assert len(covered) >= 15, f"覆盖 {len(covered)}/16 — 缺: {[s for s in STAGES if s not in covered]}"

    def test_tool_is_known_gap(self):
        """TOOL_CALL 未自动 = 已知 PARTIAL (工具调用在 AgentRuntime 内部, 约束不修改核心)。"""
        emitted = _emit_calls()
        assert "TOOL_CALL" not in emitted  # 诚实标记, 不假装完成

    def test_key_stages_auto(self):
        emitted = _emit_calls()
        for stage, evs in (("PLAN", ["PLAN_CREATED"]), ("AGENT", ["AGENT_ASSIGNED"]),
                           ("TEST", ["TEST_PASSED", "TEST_FAILED"]),
                           ("EXECUTION", ["TASK_STARTED"]),
                           ("CODE", ["ARTIFACT_CREATED"]),
                           ("DISCOVERY", ["DISCOVERY_CONFIRMED"])):
            assert any(e in emitted for e in evs), f"{stage} 未自动"

    def test_event_types_registered(self):
        AE = import_module("factory-console.audit.audit_event")
        for evt in ("DISCOVERY_CONFIRMED", "TASK_STARTED", "TASK_FAILED",
                    "AGENT_ASSIGNED", "ARTIFACT_CREATED", "TEST_PASSED", "TEST_FAILED"):
            assert evt in AE.EVENT_TYPES


class TestDecisionChainE2E:
    def _run_debug_chain(self, tmp_path):
        """真实 Debug 链 → Audit 事件自动 → Decision Chain 可查询。"""
        DP = import_module("factory-console.session.debug.debug_pipeline")
        ws = tmp_path / "proj"
        ws.mkdir(exist_ok=True)
        (ws / "scoring.py").write_text("def score(shots):\n    return 4  # BUG\n", encoding="utf-8")
        (ws / "test_scoring.py").write_text(
            "from scoring import score\n\ndef test_score():\n    assert score(3) == 6\n", encoding="utf-8")
        p = DP.DebugPipeline(workspace=ws)
        s = p.run(p.start(project_id="proj", task_id="T1", agent_id="backend-1",
                          error_message="assert 4 == 6: expected 6 got 4"))
        assert s.status == "SUCCESS"
        return ws

    def test_debug_chain_events_auto(self, tmp_path):
        ws = self._run_debug_chain(tmp_path)
        events = json.loads((ws / "audit" / "audit_events.json").read_text(encoding="utf-8"))
        types = {e["event_type"] for e in events}
        assert "GOVERNANCE_CHECK" in types
        assert "REPAIR_COMPLETED" in types
        assert "VALIDATION_PASSED" in types

    def test_chain_queryable(self, tmp_path):
        AS = import_module("factory-console.audit.audit_store")
        ws = self._run_debug_chain(tmp_path)
        store = AS.AuditStore(workspace=ws)
        events = store.events()
        assert events
        chain = store.get_chain(events[0].trace_id)
        assert chain is not None
        assert chain["count"] >= 1

    def test_failure_path_events(self, tmp_path):
        """失败路径也有事件 (任务失败 → TASK_FAILED)。"""
        AE = import_module("factory-console.audit.audit_emitter")
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        emitter = AE.AuditEmitter(workspace=ws)
        emitter.emit("TASK_FAILED", project_id="proj-x", task_id="T1",
                     decision_reason="测试失败", result={"error": "boom"})
        events = json.loads((ws / "audit" / "audit_events.json").read_text(encoding="utf-8"))
        assert events[0]["event_type"] == "TASK_FAILED"
        assert events[0]["project_id"] == "proj-x"
        assert events[0]["result"]["error"] == "boom"

    def test_production_actions_auto_audit(self, tmp_path):
        """生产 action (create_product) 自动 Audit — 非人工。"""
        ACT = import_module("factory-console.session.actions")
        PR = import_module("factory-console.session.product")
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)

        class Session:
            def __init__(self):
                self.product_intent = PR.ProductIntent(
                    name="AutoAudit", problem="p", user="u", platform="mobile",
                    core_features=["a"])

            def to_dict(self):
                return {}

        class Ctx:
            workspace = ws
            params = {}
            project = ""
            user = "alice"
            session = Session()
            intent = None

            def require(self, level):
                pass

        r = ACT.create_product(Ctx())
        assert r.ok
        af = ws / "audit" / "audit_events.json"
        assert af.is_file()
        events = json.loads(af.read_text(encoding="utf-8"))
        assert any(e["event_type"] == "PRODUCT_CREATED" for e in events)
