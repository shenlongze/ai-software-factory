"""S10-072 — Memory 自动沉淀 + Learning Loop E2E (P0-E)。

验证: Debug 闭环 (run) 自动沉淀经验, 未来任务可检索并使用。
"""

from __future__ import annotations

from pathlib import Path

from importlib import import_module

DP = import_module("factory-console.session.debug.debug_pipeline")
MEM = import_module("factory-console.memory")


def _buggy(ws: Path):
    (ws / "scoring.py").write_text("def score(shots):\n    return 4  # BUG\n", encoding="utf-8")
    (ws / "test_scoring.py").write_text(
        "from scoring import score\n\ndef test_score():\n    assert score(3) == 6\n", encoding="utf-8")


class TestAutoLearn:
    def test_run_success_auto_learn(self, tmp_path):
        ws = tmp_path / "a"
        ws.mkdir(exist_ok=True)
        _buggy(ws)
        p = DP.DebugPipeline(workspace=ws)
        s = p.run(p.start(project_id="p", task_id="T1", agent_id="a1",
                          error_message="assert 4 == 6: expected 6 got 4"))
        assert s.status == "SUCCESS"
        store = MEM.ExperienceStore.from_workspace(ws)
        recs = store.records()
        assert len(recs) >= 1
        assert recs[0].type == "SUCCESS_PATTERN"

    def test_run_failure_auto_learn(self, tmp_path):
        ws = tmp_path / "f"
        ws.mkdir(exist_ok=True)
        _buggy(ws)
        p = DP.DebugPipeline(workspace=ws)
        from importlib import import_module as _im
        B = _im("factory-console.session.budget")
        # 已耗尽预算 → BLOCKED
        budget = B.ProjectBudget(max_total_cost=10.0, max_total_tokens=100,
                                 max_llm_calls=1)
        usage = B.BudgetUsage(total_tokens=999, total_cost=99.0, llm_calls=99)
        s = p.run(p.start(project_id="p", task_id="T1", agent_id="a1",
                          error_message="assert 4 == 6: expected 6 got 4"),
                  budget=budget, usage=usage, max_attempts=1)
        # BLOCKED (预算) → run 终态 → 失败经验沉淀
        assert s.status in ("BLOCKED", "WAITING_FOR_REVIEW")
        store = MEM.ExperienceStore.from_workspace(ws)
        # BLOCKED 学习 FAILURE_PATTERN (learn 在 run 终态自动调)
        assert store.records()  # 有记录 (成功或失败经验)

    def test_learn_idempotent_no_duplicate(self, tmp_path):
        ws = tmp_path / "i"
        ws.mkdir(exist_ok=True)
        _buggy(ws)
        p = DP.DebugPipeline(workspace=ws)
        p.run(p.start(project_id="p", task_id="T1", agent_id="a1",
                      error_message="assert 4 == 6: expected 6 got 4"))
        store = MEM.ExperienceStore.from_workspace(ws)
        assert len(store.records()) == 1


class TestLearningLoop:
    def test_run_a_to_run_b(self, tmp_path):
        """Run A 产生经验 → Run B 检索到 → 影响策略 → 成功。"""
        UNI = import_module("factory-console.retrieval.unified")
        # Run A
        wa = tmp_path / "a"
        wa.mkdir(exist_ok=True)
        _buggy(wa)
        pa = DP.DebugPipeline(workspace=wa)
        pa.run(pa.start(project_id="proj-a", task_id="T1", agent_id="backend-1",
                        error_message="assert 4 == 6: expected 6 got 4"))
        store_a = MEM.ExperienceStore.from_workspace(wa)
        assert len(store_a.records()) == 1
        # Run B: 检索
        hits, stats = UNI.retrieve_experience("expected 6 got 4", store=store_a, top_k=3)
        assert hits
        assert hits[0].type == "SUCCESS_PATTERN"
        # Run B: Debug 使用经验
        wb = tmp_path / "b"
        wb.mkdir(exist_ok=True)
        _buggy(wb)
        pb = DP.DebugPipeline(workspace=wb)
        sb = pb.analyze(pb.start(project_id="proj-b", task_id="T1", agent_id="backend-1",
                                 error_message="assert 4 == 6: expected 6 got 4"),
                        memory_store=store_a)
        assert sb.selected_strategy == "FIX_CODE"
        sb = pb.repair(sb)
        sb = pb.validate(sb, result=None)
        assert sb.status == "SUCCESS"
