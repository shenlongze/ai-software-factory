"""S13: Production Evaluation — 确定性质量评价 (非 LLM)。

覆盖:
1. Evaluation contract
2. completion evaluation
3. artifact integrity evaluation
4. verification evaluation
5. repair count evaluation
6. lineage evaluation
7. workspace delivery evaluation
8. deterministic score
9. historical failure + final pass (FAIL→Repair→PASS 识别)
10. failed production evaluation
11. evaluation artifact persistence
12. CLI
13. API
14. idempotency
15. reproducibility
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.production_evaluation import (  # noqa: E402
    evaluate, get_evaluation, list_evaluations, WEIGHTS,
)
from factory_console.production_run import (  # noqa: E402
    register_workflow, create_production_run, execute_production_run, get_production_run,
)
from factory_console.node_runtime import (  # noqa: E402
    register_node, create_node_run, execute_node_run,
)
from factory_console.agent_kernel import (  # noqa: E402
    create_agent_run, run_agent, create_handoff,
)
from factory_console.session.agent_entity import AgentEntity  # noqa: E402
from factory_console.session.agent_registry import AgentRegistry  # noqa: E402


def _wf_nodes():
    return [
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"},
        {"node_id": "b", "name": "B", "type": "engineering", "depends_on": ["a"],
         "executor_name": "b", "input_binding": {"x": "artifact:a"}},
    ]


def _good_factory(node_id):
    def fn(input_data):
        patch = (f"diff --git a/{node_id}.py b/{node_id}.py\n--- /dev/null\n+++ b/{node_id}.py\n"
                 "@@ -0,0 +1,2 @@\n+def {node_id}():\n+    return 1\n")
        return {"ok": True, "output": {"code": node_id}, "patch_text": patch,
                "artifact_type": "code_change",
                "verification": {"result": "PASS", "tests": 1}}
    return fn


def _repair_workflow(tmp_path):
    """构造 有 repair 的 ProductionRun: attempt1 FAIL → repair → attempt2 PASS。"""
    from factory_console.professional_workflow import BUILTIN_CALC_TESTS, verify_code_with_pytest
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=_wf_nodes())
    run = create_production_run(str(tmp_path), "wf-1")

    bad_code = ("def add(a, b):\n    return a - b\n\ndef subtract(a, b):\n    return a + b\n\n"
                "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n    return a / b\n")
    good_code = ("def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n\n"
                 "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n"
                 "    if b == 0:\n        raise ValueError('div by zero')\n    return a / b\n")

    def exec_fn(input_data):
        code = input_data.get("_code", bad_code)
        ver = verify_code_with_pytest(code, BUILTIN_CALC_TESTS)
        return {"ok": True, "output": {"content": code}, "patch_text": "",
                "artifact_type": "code_change", "verification": ver, "content": code}

    def repair_fn(failed_artifact, verification, ctx):
        ver = verify_code_with_pytest(good_code, BUILTIN_CALC_TESTS)
        return {"ok": ver["status"] == "PASS", "output": {"content": good_code},
                "patch_text": "", "artifact_type": "code_change", "verification": ver,
                "content": good_code}

    def factory(node_id):
        def fn(input_data):
            # node a 用 repair 流程, node b 直接成功
            if node_id == "a":
                return exec_fn(input_data)
            return _good_factory(node_id)(input_data)
        return fn

    from factory_console.node_runtime import execute_node_run as _enr
    # 直接构造: 手动跑 node a 带 repair
    register_node(str(tmp_path), node_id="a", name="A", node_type="engineering")
    nr = create_node_run(str(tmp_path), "a", input_data={"_code": bad_code})
    done_a = execute_node_run(str(tmp_path), nr["run_id"], executor_fn=exec_fn,
                              executor_name="a", artifact_root=str(tmp_path),
                              max_attempts=2, repair_fn=repair_fn)
    assert done_a["state"] == "COMPLETED"
    assert done_a["attempts"][0]["verification"]["status"] == "FAIL"
    assert done_a["attempts"][1]["verification"]["status"] == "PASS"
    # 把 node a 的结果塞进 production_run (模拟完整 run)
    prun = get_production_run(str(tmp_path), run["run_id"])
    prun["state"] = "COMPLETED"
    prun["status"] = "COMPLETED"
    prun["node_runs"] = [{"node_id": "a", "run_id": nr["run_id"],
                          "state": "COMPLETED", "artifact_id": done_a["artifact_id"]}]
    prun["artifacts"] = [done_a["artifact_id"]]
    from factory_console.production_run import _write
    _write(str(tmp_path), prun)
    return run["run_id"]


# --- 1/8. contract + deterministic score ---

def test_evaluation_contract(tmp_path):
    run_id = _repair_workflow(tmp_path)
    ev = evaluate(str(tmp_path), run_id)
    assert ev["evaluation_id"].startswith("eval-")
    assert ev["production_run_id"] == run_id
    assert "overall_score" in ev and "dimensions" in ev
    assert set(WEIGHTS) <= set(ev["dimensions"])
    # 确定性: 同 evidence → 同 score
    ev2 = evaluate(str(tmp_path), run_id, force=True)
    assert ev2["overall_score"] == ev["overall_score"]


# --- 2. completion ---

def test_completion_dimension(tmp_path):
    run_id = _repair_workflow(tmp_path)
    ev = evaluate(str(tmp_path), run_id)
    assert ev["dimensions"]["completion"]["pass"] is True
    assert ev["dimensions"]["completion"]["score"] == 100


# --- 3. artifact integrity ---

def test_artifact_integrity(tmp_path):
    run_id = _repair_workflow(tmp_path)
    ev = evaluate(str(tmp_path), run_id)
    assert ev["dimensions"]["artifact_integrity"]["pass"] is True


# --- 4/5/9. verification + repair + historical failure ---

def test_verification_historical_failure_repair(tmp_path):
    """FAIL→Repair→PASS: final PASS, historical_failures=1, repair_count=1。"""
    run_id = _repair_workflow(tmp_path)
    ev = evaluate(str(tmp_path), run_id)
    assert ev["dimensions"]["verification"]["pass"] is True
    assert ev["verification_attempts"] == 2
    assert ev["historical_failures"] == 1
    assert ev["repair_count"] == 1
    # 不是把历史 FAIL 当最终 FAIL
    assert ev["status"] == "COMPLETED"
    # repair efficiency: 1 repair → 80
    assert ev["dimensions"]["repair_efficiency"]["score"] == 80


# --- 6. lineage ---

def test_lineage_evaluation(tmp_path):
    run_id = _repair_workflow(tmp_path)
    ev = evaluate(str(tmp_path), run_id)
    assert "lineage_integrity" in ev["dimensions"]
    # 至少不报 broken (可能 handoff 为空 → 仍 PASS 因为无 missing artifact)
    assert ev["dimensions"]["lineage_integrity"]["pass"] is True


# --- 7. workspace delivery ---

def test_workspace_dimension(tmp_path):
    run_id = _repair_workflow(tmp_path)
    ev = evaluate(str(tmp_path), run_id)
    assert ev["dimensions"]["workspace_delivery"]["pass"] is True


# --- 10. failed production ---

def test_failed_production_evaluation(tmp_path):
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=_wf_nodes())

    def bad_factory(node_id):
        def fn(input_data):
            return {"ok": False, "error": "boom", "artifact_type": "report",
                    "verification": {"result": "FAIL"}}
        return fn
    run = create_production_run(str(tmp_path), "wf-1")
    done = execute_production_run(str(tmp_path), run["run_id"], executor_factory=bad_factory,
                                  artifact_root=str(tmp_path))
    assert done["state"] == "FAILED"
    ev = evaluate(str(tmp_path), run["run_id"])
    assert ev["status"] == "FAILED"
    assert ev["dimensions"]["completion"]["pass"] is False
    assert ev["overall_score"] < 100
    assert ev["overall_score"] < 50  # 显著低于成功生产


# --- 11. persistence ---

def test_evaluation_persistence(tmp_path):
    run_id = _repair_workflow(tmp_path)
    ev = evaluate(str(tmp_path), run_id)
    loaded = get_evaluation(str(tmp_path), run_id)
    assert loaded is not None
    assert loaded["evaluation_id"] == ev["evaluation_id"]
    assert len(list_evaluations(str(tmp_path))) == 1


# --- 14. idempotency ---

def test_idempotency(tmp_path):
    """重复 evaluate → 返回现有 (不产生重复)。"""
    run_id = _repair_workflow(tmp_path)
    ev1 = evaluate(str(tmp_path), run_id)
    ev2 = evaluate(str(tmp_path), run_id)
    assert ev1["evaluation_id"] == ev2["evaluation_id"], "幂等: 不重复生成"
    # force 重新计算 → 同结果
    ev3 = evaluate(str(tmp_path), run_id, force=True)
    assert ev3["overall_score"] == ev1["overall_score"]


# --- 15. reproducibility ---

def test_reproducibility(tmp_path):
    """同一 evidence → 重复计算完全一致。"""
    run_id = _repair_workflow(tmp_path)
    ev1 = evaluate(str(tmp_path), run_id, force=True)
    ev2 = evaluate(str(tmp_path), run_id, force=True)
    assert ev1["overall_score"] == ev2["overall_score"]
    assert ev1["dimensions"] == ev2["dimensions"]
    assert ev1["historical_failures"] == ev2["historical_failures"]


# --- 12. CLI ---

def test_cli_evaluate(tmp_path):
    run_id = _repair_workflow(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    rc = _cli_main(["production", "evaluate", run_id, "--data-dir", str(tmp_path)])
    assert rc == 0


# --- 13. API ---

def test_api_evaluate(tmp_path):
    run_id = _repair_workflow(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.get(f"/api/production-runs/{run_id}/evaluation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["production_run_id"] == run_id
    assert "overall_score" in data
