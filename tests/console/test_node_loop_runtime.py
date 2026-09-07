"""Node Loop 泛化 (E1/E2) — node_runtime 测试。"""
import pytest

from factory_console import node_runtime as nr


@pytest.fixture()
def rt(tmp_path):
    nr.register_node(str(tmp_path), node_id="requirement-analysis",
                     name="requirement-analysis", node_type="requirement-analysis")
    return str(tmp_path)


class TestDecisionGate:
    def test_request_decision_waits(self, rt):
        run = nr.create_node_run(rt, "requirement-analysis", project_id="P-A")
        nr.transition_node_run(rt, run["run_id"], "RUNNING")
        d = nr.request_decision(rt, run["run_id"], question="平台?",
                                options=["PC", "移动端"])
        got = nr.get_node_run(rt, run["run_id"])
        assert got["state"] == "WAITING_FOR_USER"
        assert d["status"] == "PENDING"

    def test_decision_requires_human(self, rt):
        run = nr.create_node_run(rt, "requirement-analysis")
        nr.transition_node_run(rt, run["run_id"], "RUNNING")
        d = nr.request_decision(rt, run["run_id"], question="q")
        with pytest.raises(nr.NodeError):
            nr.record_decision(rt, run["run_id"], d["decision_id"], chosen="x", actor="llm")

    def test_human_decision_resumes(self, rt):
        run = nr.create_node_run(rt, "requirement-analysis")
        nr.transition_node_run(rt, run["run_id"], "RUNNING")
        d = nr.request_decision(rt, run["run_id"], question="q")
        nr.record_decision(rt, run["run_id"], d["decision_id"], chosen="PC", actor="human")
        got = nr.get_node_run(rt, run["run_id"])
        assert got["state"] == "RUNNING"
        assert got["decisions"][0]["status"] == "RESOLVED"
        assert got["decisions"][0]["chosen"] == "PC"

    def test_illegal_transition_rejected(self, rt):
        run = nr.create_node_run(rt, "requirement-analysis")
        nr.transition_node_run(rt, run["run_id"], "RUNNING")
        with pytest.raises(nr.NodeError):
            nr.transition_node_run(rt, run["run_id"], "COMPLETED")  # 需经 VERIFYING


class TestCheckpointResume:
    def test_checkpoint_roundtrip(self, rt):
        run = nr.create_node_run(rt, "requirement-analysis")
        nr.update_checkpoint(rt, run["run_id"], patch={
            "completed_dimensions": ["范围"], "open_questions": ["平台?"],
            "next_work": ["分析交互"]})
        nr.bump_iteration(rt, run["run_id"])
        got = nr.get_node_run(rt, run["run_id"])
        assert got["checkpoint"]["completed_dimensions"] == ["范围"]
        assert got["checkpoint"]["iteration"] == 1

    def test_active_run_project_filter(self, rt):
        r1 = nr.create_node_run(rt, "requirement-analysis", project_id="P-A")
        r2 = nr.create_node_run(rt, "requirement-analysis", project_id="P-B")
        nr.transition_node_run(rt, r1["run_id"], "RUNNING")
        active = nr.get_active_run(rt, "requirement-analysis", project_id="P-A")
        assert active["run_id"] == r1["run_id"]
        # P-B PENDING 也非 active (未 RUNNING)
        active_b = nr.get_active_run(rt, "requirement-analysis", project_id="P-B")
        assert active_b is None or active_b["run_id"] == r2["run_id"]

    def test_completed_run_not_active(self, rt):
        r = nr.create_node_run(rt, "requirement-analysis")
        nr.transition_node_run(rt, r["run_id"], "RUNNING")
        nr.transition_node_run(rt, r["run_id"], "VERIFYING")
        nr.transition_node_run(rt, r["run_id"], "COMPLETED")
        assert nr.get_active_run(rt, "requirement-analysis") is None
