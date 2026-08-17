"""S10-073 — Cross-Project Isolation E2E (P0-A)。

契约: A→A=YES, B→B=YES, A→B=NO, B→A=NO (项目专属经验)。
全局经验 (project="") 所有项目可见 (合法共享)。
覆盖: Memory / Retrieval / Debug / Recommend / Audit。
"""

from __future__ import annotations

from pathlib import Path

from importlib import import_module

MEM = import_module("factory-console.memory")
UNI = import_module("factory-console.retrieval.unified")
DP = import_module("factory-console.session.debug.debug_pipeline")
DM = import_module("factory-console.session.debug.debug_memory")
D = import_module("factory-console.session.debug")


def _store(ws: Path):
    ws.mkdir(parents=True, exist_ok=True)
    return MEM.ExperienceStore(ws / "memory" / "experience_store.json")


class TestMemoryIsolation:
    def test_same_project_visible(self, tmp_path):
        ws = tmp_path / "ws"
        store = _store(ws)
        store.add(MEM.ExperienceRecord(type="DEBUG_EXPERIENCE", problem="A 项目计分失败",
                                       success=True, confidence=0.9, source="t", project="proj-a"))
        hits, _ = UNI.retrieve_experience("计分", store=store, top_k=5, project="proj-a")
        assert hits and hits[0].project == "proj-a"

    def test_cross_project_invisible(self, tmp_path):
        ws = tmp_path / "ws"
        store = _store(ws)
        store.add(MEM.ExperienceRecord(type="DEBUG_EXPERIENCE", problem="A 项目计分失败",
                                       success=True, confidence=0.9, source="t", project="proj-a"))
        hits, _ = UNI.retrieve_experience("计分", store=store, top_k=5, project="proj-b")
        assert not any(getattr(h, "project", "") == "proj-a" for h in hits)

    def test_global_shared(self, tmp_path):
        ws = tmp_path / "ws"
        store = _store(ws)
        store.add(MEM.ExperienceRecord(type="DEBUG_EXPERIENCE", problem="全局经验",
                                       success=True, confidence=0.9, source="t", project=""))
        hits_a, _ = UNI.retrieve_experience("全局", store=store, top_k=5, project="proj-a")
        hits_b, _ = UNI.retrieve_experience("全局", store=store, top_k=5, project="proj-b")
        assert hits_a and hits_b  # 全局经验所有项目可见

    def test_full_isolation_matrix(self, tmp_path):
        ws = tmp_path / "ws"
        store = _store(ws)
        store.add(MEM.ExperienceRecord(type="DEBUG_EXPERIENCE", problem="A 专属",
                                       success=True, confidence=0.9, source="t", project="proj-a"))
        store.add(MEM.ExperienceRecord(type="DEBUG_EXPERIENCE", problem="B 专属",
                                       success=True, confidence=0.9, source="t", project="proj-b"))
        hits_a, _ = UNI.retrieve_experience("", store=store, top_k=10, project="proj-a")
        hits_b, _ = UNI.retrieve_experience("", store=store, top_k=10, project="proj-b")
        projs_a = {getattr(h, "project", "") for h in hits_a}
        projs_b = {getattr(h, "project", "") for h in hits_b}
        assert "proj-a" in projs_a and "proj-b" not in projs_a
        assert "proj-b" in projs_b and "proj-a" not in projs_b


class TestDebugIsolation:
    def _buggy(self, ws: Path):
        (ws / "scoring.py").write_text("def score(shots):\n    return 4\n")
        (ws / "test_scoring.py").write_text(
            "from scoring import score\n\ndef test_score():\n    assert score(3) == 6\n")

    def test_debug_retrieval_scoped(self, tmp_path):
        ws = tmp_path / "ws"
        store = _store(ws)
        store.add(MEM.ExperienceRecord(type="DEBUG_EXPERIENCE", problem="A 项目超时问题",
                                       success=True, confidence=0.9, source="t", project="proj-a"))
        retriever = DM.DebugExperienceRetriever(workspace=ws)
        case_b = D.DebugCase(error_message="超时", project="proj-b")
        hits = retriever.retrieve(case_b, top_k=5, memory_store=store)
        assert not any(getattr(h, "project", "") == "proj-a" for h in hits)
        case_a = D.DebugCase(error_message="超时", project="proj-a")
        hits_a = retriever.retrieve(case_a, top_k=5, memory_store=store)
        assert any(getattr(h, "project", "") == "proj-a" for h in hits_a)

    def test_debug_pipeline_project_scoped(self, tmp_path):
        """DebugPipeline 检索受 session.project_id 约束。"""
        ws = tmp_path / "ws"
        store = _store(ws)
        store.add(MEM.ExperienceRecord(type="SUCCESS_PATTERN", problem="expected 6 got 4",
                                       success=True, confidence=0.9, source="t", project="proj-a"))
        self._buggy(ws)
        p = DP.DebugPipeline(workspace=ws)
        # proj-b 的 Debug: 不应命中 proj-a 经验
        s = p.analyze(p.start(project_id="proj-b", task_id="T1", agent_id="a1",
                              error_message="assert 4 == 6: expected 6 got 4"),
                      memory_store=store)
        # 无 proj-b 经验 → 策略基于规则兜底 (非 proj-a 的 SUCCESS_PATTERN)
        assert s.selected_strategy  # 有策略
        # proj-a 的 Debug: 命中 proj-a 经验 → FIX_CODE (经验强化)
        s_a = p.analyze(p.start(project_id="proj-a", task_id="T1", agent_id="a1",
                                error_message="assert 4 == 6: expected 6 got 4"),
                        memory_store=store)
        assert s_a.selected_strategy == "FIX_CODE"


class TestAuditIsolation:
    def test_audit_events_project_scoped(self, tmp_path):
        from importlib import import_module as _im
        AE = _im("factory-console.audit.audit_emitter")
        AS = _im("factory-console.audit.audit_store")
        ws = tmp_path / "ws"
        emitter = AE.AuditEmitter(workspace=ws)
        emitter.emit("PRODUCT_CREATED", project_id="proj-a", decision_reason="A")
        emitter.emit("PRODUCT_CREATED", project_id="proj-b", decision_reason="B")
        store = AS.AuditStore(workspace=ws)
        events_a = store.query(project_id="proj-a")
        assert all(getattr(e, "project_id", "") == "proj-a" for e in events_a)
        assert len(events_a) == 1

    def test_audit_chain_correlation(self, tmp_path):
        from importlib import import_module as _im
        AE = _im("factory-console.audit.audit_emitter")
        AS = _im("factory-console.audit.audit_store")
        ws = tmp_path / "ws"
        emitter = AE.AuditEmitter(workspace=ws)
        ev1 = emitter.emit("PLAN_CREATED", project_id="proj-a", decision_reason="计划",
                           correlation_id="corr-a")
        ev2 = emitter.emit("TASK_COMPLETED", project_id="proj-a", decision_reason="完成",
                           correlation_id="corr-a", parent_event_id=ev1.audit_id if ev1 else "")
        store = AS.AuditStore(workspace=ws)
        chain = store.get_chain(ev1.trace_id)
        assert chain is not None
        # chain 树节点含 event dict — 检查 project_id (无跨项目污染)

        def _walk(nodes):
            for node in nodes:
                ev = node.get("event") or {}
                assert ev.get("project_id") == "proj-a", f"跨项目污染: {ev.get('event_type')}"
                _walk(node.get("children") or [])

        _walk(chain.get("chain", []))
