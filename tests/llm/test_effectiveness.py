"""S29: Production Optimization Effectiveness & Controlled Workforce Experiment。

覆盖:
- Frozen contract (hypothesis/metric/threshold/min_sample 冻结)
- Control/Treatment isolation
- Recovery-aware sample (initial/final/recovery_attempts)
- Population Contract (完整 denominator, initial vs final 分层)
- Recovery-aware Comparison (initial/final/recovery_rate/mean_attempts)
- PROVEN Gate (12 条件; 样本不足 → INCONCLUSIVE)
- Case A: insufficient samples → INCONCLUSIVE
- Case C: failed samples 保留 denominator
- Case D: recovered samples 保留 initial failure
- Case E: invalid evaluation → 不 PROVEN
- CLI / API
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.effectiveness_service import (  # noqa: E402
    create_effectiveness_experiment, approve_effectiveness_experiment,
    run_effectiveness_sample, experiment_population, effectiveness_compare,
    effectiveness_outcome, effectiveness_lineage,
)

GOOD = "def a():\n    return 1\n"
BAD = "def broken(:\n    pass\n"


def _ok_factory(ws):
    def factory(node_id):
        def fn(input_data):
            (ws / "a.py").write_text(GOOD)
            return {"ok": True, "output": {"code": "ok"},
                    "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n" + GOOD),
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}
        return fn
    return factory


def _fail_then_ok(ws, fails: int = 1):
    state = {"n": 0}

    def factory(node_id):
        def fn(input_data):
            state["n"] += 1
            if state["n"] <= fails:
                (ws / "a.py").write_text(BAD)
                return {"ok": False, "error": "内置 pytest 失败: SyntaxError",
                        "verification": {"result": "FAIL"}}
            (ws / "a.py").write_text(GOOD)
            return {"ok": True, "output": {"code": "ok"},
                    "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n" + GOOD),
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}
        return fn
    return factory


def _repair(ws):
    def repair(failed_artifact, verification, ctx):
        (ws / "a.py").write_text(GOOD)
        return {"ok": True, "output": {"code": "ok"},
                "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n" + GOOD),
                "artifact_type": "code_change", "verification": {"result": "PASS"}}
    return repair


def _setup(tmp_path, min_sample=2):
    ws = Path(tmp_path) / "workspace"
    ws.mkdir(exist_ok=True)
    exp = create_effectiveness_experiment(str(tmp_path), minimum_sample_size=min_sample)
    approve_effectiveness_experiment(str(tmp_path), exp["experiment_id"])
    return ws, exp


# --- Frozen Contract ---

def test_frozen_contract(tmp_path):
    exp = create_effectiveness_experiment(str(tmp_path), metric="final_success_rate",
                                          minimum_sample_size=3, success_threshold=0.05)
    assert exp["frozen"] is True
    assert exp["metric"] == "final_success_rate"
    assert exp["minimum_sample_size"] == 3
    assert exp["success_threshold"] == 0.05
    assert exp["status"] == "APPROVAL_REQUIRED"


# --- Governance ---

def test_unapproved_blocked(tmp_path):
    ws = Path(tmp_path) / "workspace"
    ws.mkdir(exist_ok=True)
    exp = create_effectiveness_experiment(str(tmp_path))
    s = run_effectiveness_sample(str(tmp_path), experiment_id=exp["experiment_id"],
                                 arm="control", workflow_id="wf",
                                 executor_factory=_ok_factory(ws), repair_fn=_repair(ws))
    assert s.get("reason") == "NOT_APPROVED"


# --- Control/Treatment Isolation ---

def test_isolation(tmp_path):
    ws, exp = _setup(tmp_path)
    run_effectiveness_sample(str(tmp_path), experiment_id=exp["experiment_id"],
                             arm="control", workflow_id="wf",
                             executor_factory=_ok_factory(ws), repair_fn=_repair(ws))
    pop = experiment_population(str(tmp_path), exp["experiment_id"])
    assert pop["assigned_control"] == 1
    assert pop["assigned_treatment"] == 0


# --- Recovery-aware Sample ---

def test_recovery_aware_sample(tmp_path):
    """initial FAIL → recovery → final PASS; 保留 initial failure + recovery evidence。"""
    ws, exp = _setup(tmp_path)
    s = run_effectiveness_sample(str(tmp_path), experiment_id=exp["experiment_id"],
                                 arm="treatment", workflow_id="wf",
                                 executor_factory=_fail_then_ok(ws, fails=1),
                                 repair_fn=_repair(ws))
    assert s["initial_outcome"] == "FAIL"
    assert s["final_outcome"] == "PASS"
    assert len(s["recovery_attempts"]) >= 1
    assert s["time_to_recovery"] >= 1
    assert s["eligible"] is True
    # initial failure 保留 (不删)
    assert "FAIL" in s["initial_outcome"]


# --- Population Contract (完整 denominator) ---

def test_population_denominator(tmp_path):
    """失败样本保留: recovered + unrecovered + failed 全在 denominator。"""
    ws, exp = _setup(tmp_path)
    # control: 1 好 + 1 坏(不 repair → unrecovered)
    run_effectiveness_sample(str(tmp_path), experiment_id=exp["experiment_id"],
                             arm="control", workflow_id="wf",
                             executor_factory=_ok_factory(ws), repair_fn=_repair(ws))
    # treatment: 1 坏 → recovery → PASS
    run_effectiveness_sample(str(tmp_path), experiment_id=exp["experiment_id"],
                             arm="treatment", workflow_id="wf",
                             executor_factory=_fail_then_ok(ws, fails=1),
                             repair_fn=_repair(ws))
    pop = experiment_population(str(tmp_path), exp["experiment_id"])
    assert pop["total"] == 2
    assert pop["completed"] == 2
    assert pop["recovered"] == 1
    assert pop["eligible"] == 2


# --- Recovery-aware Comparison ---

def test_recovery_aware_comparison(tmp_path):
    """control 首次 PASS vs treatment 首次 FAIL+recovery → final 相同 → UNCHANGED (诚实)。"""
    ws, exp = _setup(tmp_path)
    for _ in range(2):
        run_effectiveness_sample(str(tmp_path), experiment_id=exp["experiment_id"],
                                 arm="control", workflow_id="wf",
                                 executor_factory=_ok_factory(ws), repair_fn=_repair(ws))
    for _ in range(2):
        run_effectiveness_sample(str(tmp_path), experiment_id=exp["experiment_id"],
                                 arm="treatment", workflow_id="wf",
                                 executor_factory=_fail_then_ok(ws, fails=1),
                                 repair_fn=_repair(ws))
    cmp = effectiveness_compare(str(tmp_path), exp["experiment_id"])
    # final 相同 (1.0 vs 1.0) → UNCHANGED; 但 initial 不同 (1.0 vs 0.0) 记录在案
    # (每次 sample 独立 factory → treatment 全部 initial FAIL → recovery → PASS)
    assert cmp["result"] == "UNCHANGED"
    assert cmp["effectiveness"] == "NOT_YET_PROVEN"
    assert cmp["initial_success_rate"] == {"control": 1.0, "treatment": 0.0}
    assert cmp["final_success_rate"] == {"control": 1.0, "treatment": 1.0}
    assert cmp["recovery_rate"]["treatment"] == 1.0
    assert cmp["mean_recovery_attempts"]["treatment"] == 1.0
    assert cmp["gates"]  # PROVEN Gate 记录


# --- Case A: insufficient samples → INCONCLUSIVE ---

def test_insufficient_samples_inconclusive(tmp_path):
    ws, exp = _setup(tmp_path, min_sample=3)
    run_effectiveness_sample(str(tmp_path), experiment_id=exp["experiment_id"],
                             arm="control", workflow_id="wf",
                             executor_factory=_ok_factory(ws), repair_fn=_repair(ws))
    run_effectiveness_sample(str(tmp_path), experiment_id=exp["experiment_id"],
                             arm="treatment", workflow_id="wf",
                             executor_factory=_ok_factory(ws), repair_fn=_repair(ws))
    cmp = effectiveness_compare(str(tmp_path), exp["experiment_id"])
    assert cmp["result"] == "INCONCLUSIVE"
    assert cmp["effectiveness"] == "NOT_YET_PROVEN"
    assert "minimum_sample_reached" in cmp["reason"]


# --- Case E: invalid evaluation → 不 PROVEN ---

def test_invalid_evaluation_not_proven(tmp_path):
    """eligible 不足 (evaluation 缺失) → INCONCLUSIVE。"""
    ws, exp = _setup(tmp_path)
    # 样本执行但 evaluation 需要 final PASS + workspace; 用坏 factory → FAIL → 不 eligible
    run_effectiveness_sample(str(tmp_path), experiment_id=exp["experiment_id"],
                             arm="control", workflow_id="wf",
                             executor_factory=_fail_then_ok(ws, fails=99),
                             repair_fn=lambda fa, v, ctx: {"ok": False, "error": "repair fail",
                                                           "verification": {"result": "FAIL"}})
    run_effectiveness_sample(str(tmp_path), experiment_id=exp["experiment_id"],
                             arm="treatment", workflow_id="wf",
                             executor_factory=_fail_then_ok(ws, fails=99),
                             repair_fn=lambda fa, v, ctx: {"ok": False, "error": "repair fail",
                                                           "verification": {"result": "FAIL"}})
    cmp = effectiveness_compare(str(tmp_path), exp["experiment_id"])
    assert cmp["result"] == "INCONCLUSIVE"
    assert cmp["effectiveness"] == "NOT_YET_PROVEN"
    pop = experiment_population(str(tmp_path), exp["experiment_id"])
    assert pop["failed"] == 2  # 失败样本保留


# --- Outcome + Lineage ---

def test_outcome_lineage(tmp_path):
    ws, exp = _setup(tmp_path)
    oc = effectiveness_outcome(str(tmp_path), exp["experiment_id"])
    assert oc["result"] in ("IMPROVED", "REGRESSED", "UNCHANGED", "INCONCLUSIVE")
    lg = effectiveness_lineage(str(tmp_path), exp["experiment_id"])
    assert lg["frozen"] is True
    assert lg["experiment_id"] == exp["experiment_id"]


# --- CLI ---

def test_cli_experiment(tmp_path):
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["experiment", "create", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["experiment", "compare", "exp-x", "--data-dir", str(tmp_path)]) == 1
    assert _cli_main(["experiment", "population", "exp-x", "--data-dir", str(tmp_path)]) == 1


# --- API ---

def test_api_experiment(tmp_path):
    ws = Path(tmp_path) / "workspace"
    ws.mkdir(exist_ok=True)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/experiments", json={"minimum_sample_size": 2})
    assert resp.status_code == 200
    exp = resp.json()
    assert exp["frozen"] is True
    resp = client.get(f"/api/experiments/{exp['experiment_id']}")
    assert resp.status_code == 200
    resp = client.post(f"/api/experiments/{exp['experiment_id']}/approve")
    assert resp.status_code == 200
    resp = client.post(f"/api/experiments/{exp['experiment_id']}/run",
                       json={"arm": "control", "workflow_id": "wf"})
    assert resp.status_code == 200
    resp = client.get(f"/api/experiments/{exp['experiment_id']}/samples")
    assert resp.status_code == 200
    resp = client.get(f"/api/experiments/{exp['experiment_id']}/population")
    assert resp.status_code == 200
    resp = client.get(f"/api/experiments/{exp['experiment_id']}/compare")
    assert resp.status_code == 200
    resp = client.get(f"/api/experiments/{exp['experiment_id']}/outcome")
    assert resp.status_code == 200
    resp = client.get(f"/api/experiments/{exp['experiment_id']}/evidence")
    assert resp.status_code == 200
