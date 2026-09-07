"""Requirement Analysis Node (Phase 2) — 单元测试 (mock LLM)。"""
import json

from factory_console import node_runtime as nr
from factory_console import requirement_analysis_node as ran


def _mkrun(root, project_id="P-A", request="飞机大战 Web 版"):
    nr.register_node(root, node_id="requirement-analysis",
                     name="req-analysis", node_type="requirement-analysis")
    run = nr.create_node_run(root, "requirement-analysis", project_id=project_id,
                             input_data={"request": request, "project_id": project_id})
    return run


def _llm_with(findings, summary="维度完成", next_dim=True):
    def fn(prompt):
        return json.dumps({"findings": findings, "summary": summary,
                           "next_dimension_ready": next_dim}, ensure_ascii=False)
    return fn


class TestAnalysisRound:
    def test_first_round_progresses(self, tmp_path):
        r = str(tmp_path)
        run = _mkrun(r)
        out = ran.run_round(r, run["run_id"], _llm_with([]))
        assert out["need_user"] is False
        got = nr.get_node_run(r, run["run_id"])
        cp = got["checkpoint"]
        assert cp["completed_dimensions"] == ["范围与目标"]
        assert cp["iteration"] == 1

    def test_decision_point_waits(self, tmp_path):
        r = str(tmp_path)
        run = _mkrun(r)
        llm = _llm_with([{"dimension": "范围与目标", "type": "ambiguity",
                          "question": "PC 还是移动端?", "needs_decision": True,
                          "decision_options": ["PC", "移动端", "都支持"],
                          "recommendation": "PC"}])
        out = ran.run_round(r, run["run_id"], llm)
        assert out["need_user"] is True and out["state"] == "WAITING_FOR_USER"
        got = nr.get_node_run(r, run["run_id"])
        assert got["state"] == "WAITING_FOR_USER"
        dec = got["decisions"][0]
        assert dec["status"] == "PENDING" and dec["options"] == ["PC", "移动端", "都支持"]
        # Phase 2.1: 决策等待前维度进度已持久化 (不丢)
        cp = got["checkpoint"]
        assert cp["completed_dimensions"] == ["范围与目标"]
        assert "PC 还是移动端?" in cp["open_questions"]

    def test_multiple_decisions_one_per_round(self, tmp_path):
        """多个 needs_decision finding → 每回合仅一个 (其余保留下回合)。"""
        r = str(tmp_path)
        run = _mkrun(r)
        llm = _llm_with([{"dimension": "范围", "type": "ambiguity", "question": "Q1",
                          "needs_decision": True, "decision_options": ["a"]},
                         {"dimension": "范围", "type": "ambiguity", "question": "Q2",
                          "needs_decision": True, "decision_options": ["b"]}])
        out = ran.run_round(r, run["run_id"], llm)
        assert out["need_user"] is True and len(out["pending_questions"]) == 1
        got = nr.get_node_run(r, run["run_id"])
        cp = got["checkpoint"]
        assert cp["completed_dimensions"] == ["范围与目标"]  # 进度已落
        assert len([d for d in got["decisions"] if d["status"] == "PENDING"]) == 1

    def test_human_answer_resumes_and_continues(self, tmp_path):
        r = str(tmp_path)
        run = _mkrun(r)
        llm = _llm_with([{"dimension": "范围与目标", "type": "ambiguity",
                          "question": "平台?", "needs_decision": True,
                          "decision_options": ["PC"]}])
        out = ran.run_round(r, run["run_id"], llm)
        did = out["pending_questions"][0]["decision_id"]
        nr.record_decision(r, run["run_id"], did, chosen="PC", actor="human")
        got = nr.get_node_run(r, run["run_id"])
        assert got["state"] == "RUNNING"
        assert got["decisions"][0]["status"] == "RESOLVED"

    def test_llm_cannot_confirm_decision(self, tmp_path):
        r = str(tmp_path)
        run = _mkrun(r)
        llm = _llm_with([{"dimension": "范围", "type": "ambiguity",
                          "question": "q", "needs_decision": True}])
        out = ran.run_round(r, run["run_id"], llm)
        did = out["pending_questions"][0]["decision_id"]
        try:
            nr.record_decision(r, run["run_id"], did, chosen="x", actor="llm")
            assert False, "LLM 不能确认决策"
        except nr.NodeError:
            pass

    def test_convergence_completes(self, tmp_path):
        r = str(tmp_path)
        run = _mkrun(r)
        nr.transition_node_run(r, run["run_id"], "RUNNING")
        # 全部维度覆盖
        for d in ran.ANALYSIS_DIMENSIONS:
            nr.update_checkpoint(r, run["run_id"], patch={
                "completed_dimensions": ran.ANALYSIS_DIMENSIONS[:ran.ANALYSIS_DIMENSIONS.index(d) + 1],
                "open_questions": []})
        done = ran.finalize_if_done(r, run["run_id"])
        assert done is not None and done["state"] == "COMPLETED"

    def test_open_question_blocks_completion(self, tmp_path):
        r = str(tmp_path)
        run = _mkrun(r)
        nr.transition_node_run(r, run["run_id"], "RUNNING")
        nr.update_checkpoint(r, run["run_id"], patch={
            "completed_dimensions": ran.ANALYSIS_DIMENSIONS,
            "open_questions": ["音效?"]})
        assert ran.finalize_if_done(r, run["run_id"]) is None


class TestConvergenceAfterDecisions:
    def test_resolved_decisions_unblock_completion(self, tmp_path):
        """决策已 RESOLVED 的问题不阻塞收敛 (open_questions 假性累积修复)。"""
        r = str(tmp_path)
        run = _mkrun(r)
        nr.transition_node_run(r, run["run_id"], "RUNNING")
        # 全维度覆盖 + open 含已决策问题
        nr.request_decision(r, run["run_id"], question="平台?",
                            options=["PC"])  # → WAITING
        nr.update_checkpoint(r, run["run_id"], patch={
            "completed_dimensions": ran.ANALYSIS_DIMENSIONS,
            "open_questions": ["平台?", "真未决?"]})
        # 答决策 (resume)
        dec = nr.get_node_run(r, run["run_id"])["decisions"][0]
        nr.record_decision(r, run["run_id"], dec["decision_id"], chosen="PC", actor="human")
        # 未决仍有 "真未决?" → 不收敛
        assert ran.finalize_if_done(r, run["run_id"]) is None
        # 清未决 → 收敛 (resolved 决策问题已过滤)
        nr.update_checkpoint(r, run["run_id"], patch={"open_questions": []})
        done = ran.finalize_if_done(r, run["run_id"])
        assert done is not None and done["state"] == "COMPLETED"
