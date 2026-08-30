"""S24: Workforce Optimization & Production Optimization。

覆盖:
- Optimization Analysis (真实 production runs → signals/candidates)
- Baseline (真实数据 COMPLETED; 不足 → BASELINE_INSUFFICIENT)
- Experiment (Governance approval 必须; 未批准 blocked)
- Measurement (delta/delta_percent + evidence_refs)
- Comparison (IMPROVED/REGRESSED/UNCHANGED/INCONCLUSIVE)
- Outcome (诚实: 确定性 executor → UNCHANGED 不伪造; 仅 IMPROVED 写 Experience)
- Lineage (fact → analysis → baseline → experiment → measurement → outcome)
- CLI / API
- Real E2E
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.production_run import (  # noqa: E402
    register_workflow, create_production_run, execute_production_run,
)
from factory_console.production_evaluation import evaluate  # noqa: E402
from factory_console.optimization_service import (  # noqa: E402
    analyze, create_baseline, create_experiment, approve_experiment,
    run_experiment, compare, outcome, lineage, get_baseline,
)


def _make_run(tmp_path, fail_once: bool = False) -> str:
    """真实 ProductionRun + evaluation。fail_once=True → repair_count>0。"""
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])
    run = create_production_run(str(tmp_path), "wf-1")
    patch = ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n"
             "+def a():\n+    return 1\n")

    def factory(node_id):
        def fn(input_data):
            return {"ok": True, "output": {"code": "x"}, "patch_text": patch,
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}
        return fn
    execute_production_run(str(tmp_path), run["run_id"], executor_factory=factory,
                           artifact_root=str(tmp_path))
    evaluate(str(tmp_path), run["run_id"])
    return run["run_id"]


def _setup(tmp_path, n: int = 4) -> list[str]:
    return [_make_run(tmp_path) for _ in range(n)]


# --- Baseline: 真实数据 vs 不足 ---

def test_baseline_real_data(tmp_path):
    """4 真实 runs → Baseline COMPLETED (真实指标, 非 mock)。"""
    _setup(tmp_path, 4)
    bl = create_baseline(str(tmp_path))
    assert bl["status"] == "COMPLETED"
    assert bl["sample_size"] == 4
    assert "mean" in bl["metrics"]
    assert bl["evidence_refs"], "baseline 必须引用真实 runs"
    assert bl["production_run_refs"]


def test_baseline_insufficient(tmp_path):
    """无 COMPLETED runs → BASELINE_INSUFFICIENT (正式结果, 不造数据)。"""
    bl = create_baseline(str(tmp_path))
    assert bl["status"] == "BASELINE_INSUFFICIENT"
    assert "INSUFFICIENT" in bl["explain"]


# --- Analysis ---

def test_optimization_analysis(tmp_path):
    """Analysis: 真实 signals + candidates (evidence_refs 可追溯)。"""
    _setup(tmp_path, 4)
    an = analyze(str(tmp_path))
    assert an["status"] == "COMPLETED"
    assert len(an["evidence_refs"]) == 4
    assert any(s["signal_type"] == "avg_repair_count" for s in an["signals"])
    # candidates explain itself
    for c in an["candidates"]:
        assert c.get("explain"), "candidate 必须 explain itself"


# --- Experiment + Governance ---

def test_experiment_requires_approval(tmp_path):
    """未批准实验 → run blocked; 批准后 → allowed。"""
    _setup(tmp_path, 4)
    bl = create_baseline(str(tmp_path))
    exp = create_experiment(str(tmp_path), baseline_id=bl["baseline_id"],
                            control_definition="c", treatment_definition="t",
                            metric="repair_count")
    assert exp["status"] == "APPROVAL_REQUIRED"
    assert exp["governance"]["approval_id"]
    # 未批准 → run 拒绝
    with pytest.raises(ValueError):
        run_experiment(str(tmp_path), exp["experiment_id"], run_id=_setup(tmp_path, 1)[0], arm="control")
    # 批准后 → allowed
    exp2 = approve_experiment(str(tmp_path), exp["experiment_id"])
    assert exp2["status"] == "APPROVED"


# --- Real E2E: 全链 + 诚实 Outcome ---

def test_real_experiment_e2e_honest_unchanged(tmp_path):
    """确定性 executor → Baseline==Treatment → UNCHANGED (不伪造 IMPROVED, 不写 Experience)。"""
    rids = _setup(tmp_path, 4)
    bl = create_baseline(str(tmp_path))
    exp = create_experiment(str(tmp_path), baseline_id=bl["baseline_id"],
                            control_definition="current", treatment_definition="optimized",
                            metric="repair_count")
    approve_experiment(str(tmp_path), exp["experiment_id"])
    for i, arm in enumerate(["control", "control", "treatment", "treatment"]):
        run_experiment(str(tmp_path), exp["experiment_id"], run_id=rids[i], arm=arm)
    cmp = compare(str(tmp_path), exp["experiment_id"])
    # 确定性 executor: 所有 run repair_count=0 → UNCHANGED
    assert cmp["result"] == "UNCHANGED", cmp
    assert len(cmp["measurements"]) == 1
    m = cmp["measurements"][0]
    assert m["delta"] == 0
    assert m["evidence_refs"], "measurement 必须引用真实 runs"
    oc = outcome(str(tmp_path), exp["experiment_id"])
    assert oc["result"] == "UNCHANGED"
    assert oc["experience_written"] is False, "UNCHANGED 不得写 Experience"
    # lineage 完整
    lg = lineage(str(tmp_path), exp["experiment_id"])
    assert set(lg["chain"].keys()) == {"experiment", "baseline", "comparison", "outcome"}


def test_experiment_insufficient_sample_inconclusive(tmp_path):
    """样本不足 → INCONCLUSIVE。"""
    rids = _setup(tmp_path, 2)
    bl = create_baseline(str(tmp_path))
    exp = create_experiment(str(tmp_path), baseline_id=bl["baseline_id"],
                            control_definition="c", treatment_definition="t", metric="repair_count")
    approve_experiment(str(tmp_path), exp["experiment_id"])
    run_experiment(str(tmp_path), exp["experiment_id"], run_id=rids[0], arm="control")
    run_experiment(str(tmp_path), exp["experiment_id"], run_id=rids[1], arm="treatment")
    cmp = compare(str(tmp_path), exp["experiment_id"])
    assert cmp["result"] == "INCONCLUSIVE"  # 每臂 1 样本 < MIN_SAMPLE=2


# --- Measurement 真实指标 ---

def test_measurement_delta(tmp_path):
    """真实 delta/delta_percent (机器可测指标)。"""
    rids = _setup(tmp_path, 4)
    bl = create_baseline(str(tmp_path))
    exp = create_experiment(str(tmp_path), baseline_id=bl["baseline_id"],
                            control_definition="c", treatment_definition="t",
                            metric="evaluation_score")
    approve_experiment(str(tmp_path), exp["experiment_id"])
    for i, arm in enumerate(["control", "control", "treatment", "treatment"]):
        run_experiment(str(tmp_path), exp["experiment_id"], run_id=rids[i], arm=arm)
    cmp = compare(str(tmp_path), exp["experiment_id"])
    m = cmp["measurements"][0]
    assert "control_value" in m and "treatment_value" in m
    assert "delta" in m and "delta_percent" in m
    assert m["sample_size"] == {"control": 2, "treatment": 2}


# --- CLI ---

def test_cli_optimization(tmp_path):
    _setup(tmp_path, 4)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["optimization", "analyze", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["optimization", "baseline", "--data-dir", str(tmp_path)]) == 0
    # experiment 需要 baseline id
    bl = create_baseline(str(tmp_path))
    assert _cli_main(["optimization", "experiment", bl["baseline_id"], "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["optimization", "lineage", "exp-x", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_optimization(tmp_path):
    _setup(tmp_path, 4)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/optimization/analyze")
    assert resp.status_code == 200
    an = resp.json()
    assert an["status"] == "COMPLETED"
    resp = client.post("/api/optimization/baselines")
    assert resp.status_code == 200
    bl = resp.json()
    assert bl["status"] == "COMPLETED"
    resp = client.post("/api/optimization/experiments",
                       json={"baseline_id": bl["baseline_id"], "metric": "repair_count"})
    assert resp.status_code == 200
    exp = resp.json()
    assert exp["status"] == "APPROVAL_REQUIRED"
    resp = client.get(f"/api/optimization/experiments/{exp['experiment_id']}")
    assert resp.status_code == 200
    resp = client.get(f"/api/optimization/experiments/{exp['experiment_id']}/compare")
    assert resp.status_code == 200
    resp = client.get(f"/api/optimization/experiments/{exp['experiment_id']}/outcome")
    assert resp.status_code == 200
    resp = client.get(f"/api/optimization/{exp['experiment_id']}/lineage")
    assert resp.status_code == 200
