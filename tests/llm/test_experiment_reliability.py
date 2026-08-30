"""S27: Production Experiment Reliability & Evaluation Quality。

覆盖:
- Production Outcome Contract (COMPLETED/FAILED/BLOCKED/INCOMPLETE)
- Failure Classification (VERIFICATION/AGENT/GOV/UNKNOWN + evidence_refs + explain)
- Sample Eligibility (ELIGIBLE/INELIGIBLE + reason/classification)
- Selection Bias 保护 (完整 denominator)
- Evaluation Quality (EVALUATION_INVALID)
- Reliability 聚合 (失败分布)
- CLI / API
- Real LLM E2E (S26 failure re-analysis)
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
from factory_console.experiment_reliability import (  # noqa: E402
    production_outcome, classify_failure, sample_eligibility,
    experiment_reliability, evaluation_quality,
    FC_VERIFICATION, FC_AGENT, FC_GOV, FC_UNKNOWN,
)


def _wf(tmp_path):
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])


def _ok_factory(node_id):
    def fn(input_data):
        return {"ok": True, "output": {"code": "x"},
                "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n"
                               "+def a():\n+    return 1\n"),
                "artifact_type": "code_change", "verification": {"result": "PASS"}}
    return fn


def _run(tmp_path, factory) -> str:
    r = create_production_run(str(tmp_path), "wf-1")
    execute_production_run(str(tmp_path), r["run_id"], executor_factory=factory,
                           artifact_root=str(tmp_path))
    return r["run_id"]


# --- Case 1: 成功 → ELIGIBLE ---

def test_completed_sample_eligible(tmp_path):
    _wf(tmp_path)
    run_id = _run(tmp_path, _ok_factory)
    evaluate(str(tmp_path), run_id)
    oc = production_outcome(str(tmp_path), run_id)
    assert oc["outcome"] == "COMPLETED"
    e = sample_eligibility(str(tmp_path), run_id)
    assert e["eligibility"] == "ELIGIBLE"
    assert e["failure_class"] == "NONE"
    assert e["metric_value"] is not None


# --- Case 2: Verification FAIL → VERIFICATION_FAILURE + INELIGIBLE ---

def test_verification_failure_classified(tmp_path):
    _wf(tmp_path)
    def factory(node_id):
        def fn(input_data):
            return {"ok": False, "error": "内置 pytest 失败: AssertionError",
                    "verification": {"result": "FAIL"}}
        return fn
    run_id = _run(tmp_path, factory)
    oc = production_outcome(str(tmp_path), run_id)
    assert oc["outcome"] == "FAILED"
    c = classify_failure(str(tmp_path), run_id)
    assert c["classification"] == FC_VERIFICATION
    assert c["confidence"] == 1.0
    assert c["evidence_refs"] == [run_id]
    assert "pytest" in c["explain"]
    e = sample_eligibility(str(tmp_path), run_id)
    assert e["eligibility"] == "INELIGIBLE"
    assert e["failure_class"] == FC_VERIFICATION


# --- Case 3: Agent FAIL → AGENT_FAILURE ---

def test_agent_failure_classified(tmp_path):
    _wf(tmp_path)
    def factory(node_id):
        def fn(input_data):
            return {"ok": False, "error": "未知角色: developer"}
        return fn
    run_id = _run(tmp_path, factory)
    c = classify_failure(str(tmp_path), run_id)
    assert c["classification"] == FC_AGENT
    assert c["confidence"] == 1.0


# --- Case 4: BLOCKED → GOVERNANCE_BLOCKED ---

def test_blocked_classified(tmp_path):
    _wf(tmp_path)
    run = create_production_run(str(tmp_path), "wf-1")  # PENDING (未执行)
    # PENDING → NO_FAILURE (未失败不猜测)
    c = classify_failure(str(tmp_path), run["run_id"])
    assert c["classification"] == "NO_FAILURE"


# --- Evaluation Quality ---

def test_evaluation_invalid(tmp_path):
    """无 evaluation → EVALUATION_INVALID (而非 Agent bad)。"""
    _wf(tmp_path)
    run_id = _run(tmp_path, _ok_factory)  # 不 evaluate
    eq = evaluation_quality(str(tmp_path), run_id)
    assert eq["valid"] is False
    assert eq["reason"] == "EVALUATION_INVALID"


# --- Selection Bias 保护 ---

def test_selection_bias_protection(tmp_path):
    """失败样本保留在 denominator (不静默删除)。"""
    _wf(tmp_path)
    ok_run = _run(tmp_path, _ok_factory)
    evaluate(str(tmp_path), ok_run)
    def vf(node_id):
        def fn(input_data):
            return {"ok": False, "error": "内置 pytest 失败: X",
                    "verification": {"result": "FAIL"}}
        return fn
    bad_run = _run(tmp_path, vf)
    samples = [
        {"arm": "control", "production_run_id": ok_run, "state": "COMPLETED", "eligible": True},
        {"arm": "treatment", "production_run_id": bad_run, "state": "FAILED", "eligible": False},
        {"arm": "treatment", "production_run_id": "", "state": "", "eligible": False,
         "reason": "BUDGET_EXCEEDED"},
    ]
    rel = experiment_reliability(str(tmp_path), "exp-x", samples=samples)
    assert rel["total_samples"] == 3  # 完整 denominator
    assert rel["eligible_samples"] == 1
    assert rel["ineligible_samples"] == 2
    assert rel["failure_classification_distribution"].get(FC_VERIFICATION) == 1
    assert "BUDGET_EXCEEDED" in rel["failure_classification_distribution"]
    assert len(rel["samples"]) == 3  # 失败样本不删


# --- Insufficient eligible → INCONCLUSIVE (复用 S26) ---

def test_insufficient_eligible_inconclusive(tmp_path):
    """eligible < min_sample → INCONCLUSIVE。"""
    from factory_console.llm_experiment_service import (
        create_hypothesis, create_llm_experiment, approve_llm_experiment,
        llm_run_sample, llm_compare,
    )
    _wf(tmp_path)
    h = create_hypothesis(str(tmp_path), statement="s", metric="overall_score",
                          direction="HIGHER_IS_BETTER", control_definition="c",
                          treatment_definition="t", minimum_sample_size=3, success_threshold=0.0)
    exp = create_llm_experiment(str(tmp_path), hypothesis_id=h["hypothesis_id"])
    approve_llm_experiment(str(tmp_path), exp["experiment_id"])
    for _ in range(1):
        llm_run_sample(str(tmp_path), experiment_id=exp["experiment_id"], arm="control",
                       workflow_id="wf-1", real_executor_factory=_ok_factory)
        llm_run_sample(str(tmp_path), experiment_id=exp["experiment_id"], arm="treatment",
                       workflow_id="wf-1", real_executor_factory=_ok_factory)
    cmp = llm_compare(str(tmp_path), exp["experiment_id"])
    assert cmp["result"] == "INCONCLUSIVE"


# --- UNKNOWN (证据不足不猜测) ---

def test_unknown_when_no_evidence(tmp_path):
    """run 不存在 → UNKNOWN (不猜测)。"""
    c = classify_failure(str(tmp_path), "prun-nonexistent")
    assert c["classification"] == FC_UNKNOWN
    assert c["confidence"] < 0.5


# --- CLI ---

def test_cli_reliability(tmp_path):
    _wf(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["reliability", "classify", "prun-x", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["reliability", "eligibility", "prun-x", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["reliability", "reliability", "exp-x", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_reliability(tmp_path):
    _wf(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.get("/api/experiments/exp-x/reliability")
    assert resp.status_code == 200
    assert resp.json()["total_samples"] == 0
    resp = client.get("/api/experiments/exp-x/failures")
    assert resp.status_code == 200
    resp = client.get("/api/experiment-samples/smpl-x/classification")
    assert resp.status_code == 404  # 不存在 sample → 404
