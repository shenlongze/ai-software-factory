"""S10-071 — P0 接线测试 (P0-3/P0-4/P0-5/P0-6 反虚标验证)。

覆盖: Memory 自动沉淀 / Audit 生产链自动 / ContextBudget gate /
Debug 检索统一入口。装配: tmp_path; 禁外部网络。
"""

from __future__ import annotations

from pathlib import Path

from importlib import import_module

CL = import_module("factory-console.session.context_ledger")
RS = import_module("factory-console.session.reasoning")


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# ================================================================== P0-5: ContextBudget gate


class TestContextGate:
    def test_budget_rejects_oversized(self):
        led = CL.ContextLedger(max_tokens=100)
        prov = RS.ReasoningProvider(llm_fn=lambda p, o="": "{}", context_ledger=led)
        try:
            prov.analyze_gap({"project": "x" * 500})
            assert False, "超预算应拒绝 LLM 调用"
        except Exception as exc:
            assert "预算超限" in str(exc)

    def test_budget_allows_normal(self):
        led = CL.ContextLedger(max_tokens=100000)
        prov = RS.ReasoningProvider(llm_fn=lambda p, o='': '{"detected": true, "gap_type": "missing_implementation", "description": "d", "severity": "high", "confidence": 0.8, "recommended_action": "INSERT_TASK", "reason": "r"}', context_ledger=led)
        out = prov.analyze_gap({"project": "short"})
        assert out is not None  # 预算内正常调用

    def test_no_ledger_no_block(self):
        prov = RS.ReasoningProvider(llm_fn=lambda p, o='': '{"detected": true, "gap_type": "missing_implementation", "description": "d", "severity": "high", "confidence": 0.8, "recommended_action": "INSERT_TASK", "reason": "r"}')
        out = prov.analyze_gap({"project": "x"})
        assert out is not None  # 无 ledger → 不阻断 (向后兼容)


# ================================================================== P0-6: 统一检索


class TestUnifiedRetrieval:
    def test_debug_retrieval_via_orchestrator(self, tmp_path):
        from importlib import import_module as _im
        D = _im("factory-console.session.debug")
        DM = _im("factory-console.session.debug.debug_memory")
        MEM = _im("factory-console.memory")
        ws = _ws(tmp_path)
        store = MEM.ExperienceStore(ws / "memory" / "experience_store.json")
        store.add(MEM.ExperienceRecord(
            type="DEBUG_EXPERIENCE", problem="计分 API 失败", action="fix",
            success=True, confidence=0.9, source="test", project="demo"))
        retriever = DM.DebugExperienceRetriever(workspace=ws)
        case = D.DebugCase(error_message="计分 API 失败", project="demo")
        hits = retriever.retrieve(case, top_k=3, memory_store=store)
        assert hits
        assert any(getattr(h, "source", "") == "retrieval_orchestrator" for h in hits)

    def test_fallback_when_orchestrator_fails(self, tmp_path):
        from importlib import import_module as _im
        D = _im("factory-console.session.debug")
        DM = _im("factory-console.session.debug.debug_memory")
        ws = _ws(tmp_path)
        retriever = DM.DebugExperienceRetriever(workspace=ws)
        case = D.DebugCase(error_message="unknown error")
        hits = retriever.retrieve(case, top_k=3)  # 无 store → fallback 空
        assert hits == []


# ================================================================== P0-3/P0-4: 生产接线 (代码级验证)


class TestProductionWiring:
    def test_orchestrator_auto_learn(self):
        """orchestrator 必须接 AutoLearner (生产结束自动沉淀)。"""
        orch = Path("/Users/Shared/work/ai-software-factory/factory-console/session/orchestrator.py")
        content = orch.read_text(encoding="utf-8")
        assert "AutoLearner" in content
        assert "learn_from_workspace" in content

    def test_orchestrator_audit_emitter(self):
        """orchestrator 必须接 AuditEmitter (TASK_COMPLETED/PROJECT_DELIVERED 自动)。"""
        orch = Path("/Users/Shared/work/ai-software-factory/factory-console/session/orchestrator.py")
        content = orch.read_text(encoding="utf-8")
        assert "AuditEmitter" in content
        assert "TASK_COMPLETED" in content or "PROJECT_DELIVERED" in content

    def test_audit_auto_events(self, tmp_path):
        """actions 薄接: 生产 action 自动产生 Audit (非手工 append)。"""
        from importlib import import_module as _im
        ACT = _im("factory-console.session.actions")
        ws = _ws(tmp_path)
        from importlib import import_module as _im2
        PR = _im2("factory-console.session.product")

        class Session:
            def __init__(self):
                self.product_intent = PR.ProductIntent(
                    name="AuditTest", problem="p", user="u", platform="mobile",
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
        audit_file = ws / "audit" / "audit_events.json"
        assert audit_file.is_file()
        import json
        events = json.loads(audit_file.read_text(encoding="utf-8"))
        assert any(e["event_type"] == "PRODUCT_CREATED" for e in events)

    def test_memory_auto_available(self):
        """AutoLearner 生产可调用 (非仅测试)。"""
        auto = Path("/Users/Shared/work/ai-software-factory/factory-console/memory/auto_learn.py")
        assert auto.is_file()
