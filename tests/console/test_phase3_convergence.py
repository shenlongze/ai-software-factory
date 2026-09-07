"""Phase 3 — Conversation → NodeRun 收敛测试。"""
import json

from factory_console import node_runtime as nr
from factory_console.session.agent_loop import _node_run_context


def _mk(tmp_path):
    r = str(tmp_path)
    nr.register_node(r, node_id="requirement-analysis", name="ra", node_type="requirement-analysis")
    return r


class TestNodeRunContext:
    def test_empty_without_active_run(self, tmp_path):
        r = _mk(tmp_path)
        assert _node_run_context(r, "P-A") == ""

    def test_injects_active_run_facts(self, tmp_path):
        r = _mk(tmp_path)
        run = nr.create_node_run(r, "requirement-analysis", project_id="P-A",
                                 input_data={"request": "x"})
        nr.transition_node_run(r, run["run_id"], "RUNNING")
        nr.update_checkpoint(r, run["run_id"], patch={
            "completed_dimensions": ["范围与目标"], "iteration": 1})
        ctx = _node_run_context(r, "P-A")
        assert run["run_id"] in ctx and "范围与目标" in ctx
        assert "requirement_analysis_round" in ctx

    def test_injects_pending_decision(self, tmp_path):
        r = _mk(tmp_path)
        run = nr.create_node_run(r, "requirement-analysis", project_id="P-A")
        nr.transition_node_run(r, run["run_id"], "RUNNING")
        d = nr.request_decision(r, run["run_id"], question="平台?",
                                options=["PC", "移动端"])
        ctx = _node_run_context(r, "P-A")
        assert d["decision_id"] in ctx and "平台?" in ctx

    def test_completed_run_not_injected(self, tmp_path):
        r = _mk(tmp_path)
        run = nr.create_node_run(r, "requirement-analysis", project_id="P-A")
        nr.transition_node_run(r, run["run_id"], "RUNNING")
        nr.transition_node_run(r, run["run_id"], "VERIFYING")
        nr.transition_node_run(r, run["run_id"], "COMPLETED")
        assert _node_run_context(r, "P-A") == ""
