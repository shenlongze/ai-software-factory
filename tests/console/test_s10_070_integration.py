"""S10-070 — AuditEmitter + AutoLearner + ContextLedger + RetrievalOrchestrator 测试。

覆盖: emit/emit_production 自动接入 / learn_from_workspace 自动沉淀 /
ContextLedger 总预算 / RetrievalOrchestrator 多来源去重排序。
装配: tmp_path + fixtures; 禁真实网络。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

AE = import_module("factory-console.audit.audit_emitter")
AL = import_module("factory-console.memory.auto_learn")
CL = import_module("factory-console.session.context_ledger")
RO = import_module("factory-console.retrieval")


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# ================================================================== 1. AuditEmitter


class TestAuditEmitter:
    def test_emit(self, tmp_path):
        ws = _ws(tmp_path)
        ev = AE.AuditEmitter(workspace=ws).emit(
            "PRODUCT_CREATED", project_id="demo", decision_reason="创建")
        assert ev is not None
        assert ev.audit_id
        assert (ws / "audit" / "audit_events.json").is_file()

    def test_emit_redact(self, tmp_path):
        ws = _ws(tmp_path)
        ev = AE.AuditEmitter(workspace=ws).emit(
            "TASK_CREATED", project_id="demo",
            metadata={"api_key": "sk-secret", "safe": 1})
        assert ev is not None
        events = json.loads((ws / "audit" / "audit_events.json").read_text(encoding="utf-8"))
        assert "sk-secret" not in json.dumps(events)

    def test_emit_hash(self, tmp_path):
        ws = _ws(tmp_path)
        e = AE.AuditEmitter(workspace=ws)
        e.emit("TASK_CREATED", project_id="demo")
        e.emit("AGENT_STARTED", project_id="demo")
        events = json.loads((ws / "audit" / "audit_events.json").read_text(encoding="utf-8"))
        assert events[1]["previous_event_hash"] == events[0]["event_hash"]

    def test_emit_production(self, tmp_path):
        ws = _ws(tmp_path)
        ev = AE.AuditEmitter(workspace=ws).emit_production(
            project_id="demo", decision_reason="交付完成")
        assert ev is not None
        assert ev.event_type == "PROJECT_DELIVERED"

    def test_fail_safe(self, tmp_path):
        """Audit 故障 (坏 event_type) 不中断。"""
        ws = _ws(tmp_path)
        ev = AE.AuditEmitter(workspace=ws).emit("BAD_EVENT_TYPE_NOT_REAL")
        assert ev is None  # 失败安全

    def test_actions_wire(self, tmp_path):
        """actions 薄接: create_product → PRODUCT_CREATED 自动产生。"""
        from importlib import import_module as _im
        ACT = _im("factory-console.session.actions")
        ws = _ws(tmp_path)

        from importlib import import_module as _im
        PR = _im("factory-console.session.product")

        class Session:
            def __init__(self):
                self.product_intent = PR.ProductIntent(
                    name="TestApp", problem="p", user="u", platform="mobile",
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
        events = json.loads(audit_file.read_text(encoding="utf-8"))
        assert events[0]["event_type"] == "PRODUCT_CREATED"


# ================================================================== 2. AutoLearner


class TestAutoLearner:
    def _seed(self, ws: Path):
        (ws / "exec").mkdir(parents=True, exist_ok=True)
        (ws / "exec" / "execution_records.json").write_text(json.dumps([
            {"intent": "run_task", "action": "agent.execute_task",
             "agent": "backend-1", "task": "登录功能", "result": "failed",
             "error": "api key missing", "timestamp": "2026-01-01T00:00:00+00:00"},
            {"intent": "run_task", "action": "agent.execute_task",
             "agent": "backend-1", "task": "数据库设计", "result": "success",
             "timestamp": "2026-01-01T00:00:01+00:00"},
        ], ensure_ascii=False), encoding="utf-8")

    def test_should_learn(self, tmp_path):
        ws = _ws(tmp_path)
        assert AL.AutoLearner().should_learn(ws) is False
        self._seed(ws)
        assert AL.AutoLearner().should_learn(ws) is True

    def test_learn_from_workspace(self, tmp_path):
        ws = _ws(tmp_path)
        self._seed(ws)
        result = AL.AutoLearner().learn_from_workspace(ws)
        assert result is not None
        assert result.extracted_count >= 2
        store_file = ws / "memory" / "experience_store.json"
        assert store_file.is_file()

    def test_learn_fail_safe(self, tmp_path):
        ws = _ws(tmp_path)
        result = AL.AutoLearner().learn_from_workspace(ws)
        assert result is not None  # 无数据 → 空结果不崩


# ================================================================== 3. ContextLedger


class TestContextLedger:
    def test_allocate(self):
        led = CL.ContextLedger()
        assert led.allocate("memory", 500) is True
        assert led.total() == 500

    def test_over_budget(self):
        led = CL.ContextLedger(max_tokens=1000)
        assert led.allocate("memory", 800) is True
        assert led.allocate("audit", 800) is False  # 超总预算

    def test_remaining(self):
        led = CL.ContextLedger(max_tokens=1000)
        led.allocate("memory", 300)
        assert led.remaining() == 700

    def test_check(self):
        led = CL.ContextLedger(max_tokens=1000)
        ok, reason = led.check(800)
        assert ok is True
        ok2, _ = led.check(1200)
        assert ok2 is False

    def test_stats(self):
        led = CL.ContextLedger(max_tokens=1000)
        led.allocate("memory", 300)
        led.allocate("audit", 200)
        stats = led.stats()
        assert stats["total"] == 500
        assert stats["max"] == 1000
        assert stats["remaining"] == 500


# ================================================================== 4. RetrievalOrchestrator


class TestRetrievalModels:
    def test_request(self):
        r = RO.RetrievalRequest(query="计分", top_k=5)
        assert r.query == "计分"

    def test_candidate(self):
        c = RO.RetrievalCandidate(content="x", source_type=RO.RetrievalSource.EXPERIENCE,
                                  source_id="1", score=0.9)
        assert c.source_id == "1"

    def test_sources(self):
        assert RO.RetrievalSource.EXPERIENCE.value == "experience"
        assert RO.RetrievalSource.EXTERNAL_RAG.value == "external_rag"


class TestRetrievers:
    def _memory_store(self, tmp_path):
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        ws = _ws(tmp_path)
        store = MEM.ExperienceStore(ws / "memory" / "experience_store.json")
        store.add(MEM.ExperienceRecord(
            type="DEBUG_EXPERIENCE", problem="计分 API 失败", action="fix",
            success=True, confidence=0.9, source="test", project="demo"))
        return store

    def test_experience_retriever(self, tmp_path):
        store = self._memory_store(tmp_path)
        r = RO.ExperienceRetriever(memory_store=store)
        hits = r.retrieve(RO.RetrievalRequest(query="计分"))
        assert hits and hits[0].source_type == RO.RetrievalSource.EXPERIENCE

    def test_experience_no_match(self, tmp_path):
        store = self._memory_store(tmp_path)
        r = RO.ExperienceRetriever(memory_store=store)
        hits = r.retrieve(RO.RetrievalRequest(query="不存在的东西"))
        assert hits == []

    def test_audit_retriever(self, tmp_path):
        from importlib import import_module as _im
        AS = _im("factory-console.audit.audit_store")
        AE2 = _im("factory-console.audit.audit_event")
        ws = _ws(tmp_path)
        store = AS.AuditStore(workspace=ws)
        store.append(AE2.AuditEvent(event_type="TASK_BLOCKED", project_id="demo",
                                    decision_reason="预算耗尽"))
        r = RO.AuditRetriever(audit_store=store)
        hits = r.retrieve(RO.RetrievalRequest(query="预算"))
        assert hits and hits[0].source_type == RO.RetrievalSource.AUDIT

    def test_project_retriever(self, tmp_path):
        ws = _ws(tmp_path)
        pd = ws / "projects" / "demo"
        pd.mkdir(parents=True)
        (pd / "product.json").write_text(json.dumps(
            {"name": "台球计分", "problem": "计分麻烦"}), encoding="utf-8")
        r = RO.ProjectRetriever(workspace=ws)
        hits = r.retrieve(RO.RetrievalRequest(query="台球", project_id="demo"))
        assert hits and hits[0].source_type == RO.RetrievalSource.PROJECT


class TestOrchestrator:
    def _orchestrator(self, tmp_path):
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        ws = _ws(tmp_path)
        mem_store = MEM.ExperienceStore(ws / "memory" / "experience_store.json")
        mem_store.add(MEM.ExperienceRecord(
            type="DEBUG_EXPERIENCE", problem="计分 API 失败", action="fix",
            success=True, confidence=0.9, source="test", project="demo"))
        orch = RO.RetrievalOrchestrator()
        orch.register(RO.RetrievalSource.EXPERIENCE, RO.ExperienceRetriever(memory_store=mem_store))
        orch.register(RO.RetrievalSource.PROJECT, RO.ProjectRetriever(workspace=ws))
        return orch

    def test_retrieve_multi_source(self, tmp_path):
        orch = self._orchestrator(tmp_path)
        hits, stats = orch.retrieve(RO.RetrievalRequest(query="计分", top_k=5))
        assert hits
        assert stats["candidates_count"] >= 1

    def test_deduplicate(self, tmp_path):
        ws = _ws(tmp_path)
        orch = RO.RetrievalOrchestrator()
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        store = MEM.ExperienceStore(ws / "memory" / "experience_store.json")
        store.add(MEM.ExperienceRecord(
            type="DEBUG_EXPERIENCE", problem="计分", success=True, confidence=0.8,
            source="test", project="demo"))
        store.add(MEM.ExperienceRecord(
            type="DEBUG_EXPERIENCE", problem="计分", success=True, confidence=0.9,
            source="test", project="demo"))
        orch.register(RO.RetrievalSource.EXPERIENCE, RO.ExperienceRetriever(memory_store=store))
        hits, stats = orch.retrieve(RO.RetrievalRequest(query="计分", top_k=5))
        # 去重: 2 条同 problem → 不同 id → 不重复 (source_id 唯一)
        assert stats["candidates_count"] == 2

    def test_top_k(self, tmp_path):
        orch = self._orchestrator(tmp_path)
        hits, stats = orch.retrieve(RO.RetrievalRequest(query="计分", top_k=1))
        assert len(hits) <= 1

    def test_budget(self, tmp_path):
        orch = self._orchestrator(tmp_path)
        hits, stats = orch.retrieve(RO.RetrievalRequest(query="计分", max_tokens=10))
        assert stats["max_tokens"] == 10
        assert stats["estimated_tokens"] <= 10

    def test_stats_fields(self, tmp_path):
        orch = self._orchestrator(tmp_path)
        hits, stats = orch.retrieve(RO.RetrievalRequest(query="计分"))
        for k in ("candidates_count", "selected_count", "discarded_count",
                  "estimated_tokens", "max_tokens", "latency"):
            assert k in stats
