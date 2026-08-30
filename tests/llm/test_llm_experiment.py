"""S26: Real LLM Optimization Experiment & Effectiveness Proof。

覆盖:
- 结构化 Hypothesis (metric/direction/threshold/min_sample 冻结)
- Governance (未批准 → sample 拒绝)
- Budget Guard (超限 → BUDGET_EXCEEDED)
- Sample Eligibility (ELIGIBLE/INELIGIBLE/FAILED)
- Measurement (delta/delta_percent/direction/threshold)
- Outcome 诚实 (确定性 executor → UNCHANGED/NOT_YET_PROVEN)
- PROVEN 硬性保护 (样本不足 → INCONCLUSIVE)
- CLI / API
- Real LLM E2E (真实 provider, 小样本)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.production_run import (  # noqa: E402
    register_workflow,
)
from factory_console.llm_experiment_service import (  # noqa: E402
    create_hypothesis, get_hypothesis, create_llm_experiment, approve_llm_experiment,
    llm_run_sample, llm_compare, llm_outcome,
)


def _wf(tmp_path):
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "developer", "name": "D", "type": "engineering", "executor_name": "d"}])


def _det_factory(node_id):
    def fn(input_data):
        return {"ok": True, "output": {"code": "x"},
                "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n"
                               "+def a():\n+    return 1\n"),
                "artifact_type": "code_change", "verification": {"result": "PASS"}}
    return fn


def _setup_exp(tmp_path, metric="overall_score", min_sample=2):
    _wf(tmp_path)
    h = create_hypothesis(str(tmp_path), statement="reviewer 改善质量", metric=metric,
                          direction="HIGHER_IS_BETTER", control_definition="developer",
                          treatment_definition="developer+reviewer",
                          minimum_sample_size=min_sample, success_threshold=0.0)
    exp = create_llm_experiment(str(tmp_path), hypothesis_id=h["hypothesis_id"], metric=metric)
    approve_llm_experiment(str(tmp_path), exp["experiment_id"])
    return h, exp


# --- Hypothesis Contract (冻结) ---

def test_hypothesis_frozen(tmp_path):
    """Hypothesis: metric/direction/threshold/min_sample 冻结。"""
    h = create_hypothesis(str(tmp_path), statement="s", metric="overall_score",
                          direction="HIGHER_IS_BETTER", control_definition="c",
                          treatment_definition="t", minimum_sample_size=3, success_threshold=5.0)
    assert h["frozen"] is True
    assert h["metric"] == "overall_score"
    assert h["direction"] == "HIGHER_IS_BETTER"
    assert h["minimum_sample_size"] == 3
    assert h["success_threshold"] == 5.0
    assert get_hypothesis(str(tmp_path), h["hypothesis_id"])["frozen"] is True
    # 非法 direction 拒绝
    with pytest.raises(ValueError):
        create_hypothesis(str(tmp_path), statement="s", metric="m", direction="BAD",
                          control_definition="c", treatment_definition="t")


# --- Governance ---

def test_unapproved_llm_experiment_blocked(tmp_path):
    """未批准 → sample 拒绝 (NOT_APPROVED)。"""
    _wf(tmp_path)
    h = create_hypothesis(str(tmp_path), statement="s", metric="overall_score",
                          direction="HIGHER_IS_BETTER", control_definition="c",
                          treatment_definition="t", minimum_sample_size=2, success_threshold=0.0)
    exp = create_llm_experiment(str(tmp_path), hypothesis_id=h["hypothesis_id"])
    s = llm_run_sample(str(tmp_path), experiment_id=exp["experiment_id"], arm="control",
                       workflow_id="wf-1", real_executor_factory=_det_factory)
    assert s.get("reason") == "NOT_APPROVED"
    assert s.get("eligible") is False


def test_approved_llm_experiment_runs(tmp_path):
    """批准后 → 真实样本。"""
    h, exp = _setup_exp(tmp_path)
    s = llm_run_sample(str(tmp_path), experiment_id=exp["experiment_id"], arm="control",
                       workflow_id="wf-1", real_executor_factory=_det_factory)
    assert s.get("eligible") is True
    assert s.get("metric_value") == 100
    assert s.get("production_run_id")


# --- Budget Guard ---

def test_budget_guard(tmp_path):
    """超限 → BUDGET_EXCEEDED (不无限调用)。"""
    h, exp = _setup_exp(tmp_path)
    # 跑满 budget (2 control + 2 treatment)
    for _ in range(2):
        llm_run_sample(str(tmp_path), experiment_id=exp["experiment_id"], arm="control",
                       workflow_id="wf-1", real_executor_factory=_det_factory)
    for _ in range(2):
        llm_run_sample(str(tmp_path), experiment_id=exp["experiment_id"], arm="treatment",
                       workflow_id="wf-1", real_executor_factory=_det_factory)
    s = llm_run_sample(str(tmp_path), experiment_id=exp["experiment_id"], arm="control",
                       workflow_id="wf-1", real_executor_factory=_det_factory)
    assert s.get("reason") == "BUDGET_EXCEEDED"


# --- Sample Eligibility ---

def test_sample_eligibility(tmp_path):
    """Eligible 需要: run COMPLETED + evaluation + metric。"""
    h, exp = _setup_exp(tmp_path)
    s = llm_run_sample(str(tmp_path), experiment_id=exp["experiment_id"], arm="control",
                       workflow_id="wf-1", real_executor_factory=_det_factory)
    assert s["eligible"] is True
    assert s["reason"] == ""


# --- Measurement + Outcome 诚实 ---

def test_llm_compare_honest_unchanged(tmp_path):
    """确定性 executor → UNCHANGED / NOT_YET_PROVEN (不伪造 IMPROVED)。"""
    h, exp = _setup_exp(tmp_path)
    for _ in range(2):
        llm_run_sample(str(tmp_path), experiment_id=exp["experiment_id"], arm="control",
                       workflow_id="wf-1", real_executor_factory=_det_factory)
        llm_run_sample(str(tmp_path), experiment_id=exp["experiment_id"], arm="treatment",
                       workflow_id="wf-1", real_executor_factory=_det_factory)
    cmp = llm_compare(str(tmp_path), exp["experiment_id"])
    assert cmp["result"] == "UNCHANGED"
    assert cmp["effectiveness"] == "NOT_YET_PROVEN"
    assert cmp["control_value"] == 100 and cmp["treatment_value"] == 100
    assert cmp["delta"] == 0
    assert cmp["control_runs"] and cmp["treatment_runs"]
    assert cmp["evidence_refs"]
    oc = llm_outcome(str(tmp_path), exp["experiment_id"])
    assert oc["result"] == "UNCHANGED"
    assert oc["effectiveness"] == "NOT_YET_PROVEN"
    assert oc.get("experience_candidate") is None  # 非 IMPROVED 不写


# --- PROVEN 硬性保护: 样本不足 ---

def test_insufficient_sample_inconclusive(tmp_path):
    """control/treatment < min_sample → INCONCLUSIVE (PROVEN impossible)。"""
    h, exp = _setup_exp(tmp_path, min_sample=3)
    # 只跑 1+1 (需 3+3)
    llm_run_sample(str(tmp_path), experiment_id=exp["experiment_id"], arm="control",
                   workflow_id="wf-1", real_executor_factory=_det_factory)
    llm_run_sample(str(tmp_path), experiment_id=exp["experiment_id"], arm="treatment",
                   workflow_id="wf-1", real_executor_factory=_det_factory)
    cmp = llm_compare(str(tmp_path), exp["experiment_id"])
    assert cmp["result"] == "INCONCLUSIVE"
    assert cmp["effectiveness"] == "NOT_YET_PROVEN"


# --- CLI ---

def test_cli_llm_experiment(tmp_path):
    _wf(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["llm-experiment", "hypothesis", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["llm-experiment", "compare", "exp-x", "--data-dir", str(tmp_path)]) == 1


# --- API ---

def test_api_llm_experiment(tmp_path):
    _wf(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/optimization/hypotheses",
                       json={"statement": "reviewer 改善质量", "metric": "overall_score",
                             "direction": "HIGHER_IS_BETTER", "control_definition": "developer",
                             "treatment_definition": "developer+reviewer",
                             "minimum_sample_size": 2, "success_threshold": 0.0})
    assert resp.status_code == 200
    h = resp.json()
    assert h["frozen"] is True
    resp = client.post("/api/optimization/llm-experiments", json={"hypothesis_id": h["hypothesis_id"]})
    assert resp.status_code == 200
    exp = resp.json()
    assert exp["status"] == "APPROVAL_REQUIRED"
    resp = client.post(f"/api/optimization/llm-experiments/{exp['experiment_id']}/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"
    resp = client.post(f"/api/optimization/llm-experiments/{exp['experiment_id']}/run",
                       json={"arm": "control", "workflow_id": "wf-1"})
    assert resp.status_code == 200
    resp = client.get(f"/api/optimization/llm-experiments/{exp['experiment_id']}/compare")
    assert resp.status_code == 200
    resp = client.get(f"/api/optimization/llm-experiments/{exp['experiment_id']}/outcome")
    assert resp.status_code == 200


# --- Real LLM E2E (真实 provider, 小样本) ---

@pytest.mark.slow
def test_real_llm_experiment_e2e(tmp_path):
    """真实 LLM 对照实验 (deepseek, 2+2 样本)。

    诚实: 结果可能是 IMPROVED/REGRESSED/UNCHANGED/INCONCLUSIVE 任一;
    必须输出真实 evidence (不伪造)。成本: 4 次真实 LLM 调用。
    """
    import os
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("无 LLM key (真实实验跳过)")
    # 真实 LLM factory 认 software_developer 角色
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "software_developer", "name": "D", "type": "engineering",
         "executor_name": "software_developer"}])
    h = create_hypothesis(str(tmp_path), statement="reviewer 改善质量", metric="overall_score",
                          direction="HIGHER_IS_BETTER", control_definition="developer",
                          treatment_definition="developer+reviewer",
                          minimum_sample_size=2, success_threshold=0.0)
    exp = create_llm_experiment(str(tmp_path), hypothesis_id=h["hypothesis_id"])
    approve_llm_experiment(str(tmp_path), exp["experiment_id"])
    from factory_console.professional_workflow import build_real_executor_factory
    factory = build_real_executor_factory(str(tmp_path))
    for _ in range(2):
        llm_run_sample(str(tmp_path), experiment_id=exp["experiment_id"], arm="control",
                       workflow_id="wf-1", real_executor_factory=factory,
                       task_prompt="写一个 Python 计算器 add 函数")
        llm_run_sample(str(tmp_path), experiment_id=exp["experiment_id"], arm="treatment",
                       workflow_id="wf-1", real_executor_factory=factory,
                       task_prompt="写一个 Python 计算器 add 函数")
    cmp = llm_compare(str(tmp_path), exp["experiment_id"])
    oc = llm_outcome(str(tmp_path), exp["experiment_id"])
    # 诚实断言: 结果四态之一, effectiveness 三态之一
    # 真实 LLM 生产可能 FAILED (LLM 输出格式不定) → eligible 样本可能不足 → INCONCLUSIVE (合法)
    assert cmp["result"] in ("IMPROVED", "REGRESSED", "UNCHANGED", "INCONCLUSIVE")
    assert oc["effectiveness"] in ("PROVEN", "REJECTED", "NOT_YET_PROVEN")
    # 真实 evidence 必须记录 (样本含真实 run ids 或真实失败原因)
    # 重新读实验记录 (create 返回的 exp 是旧 dict, samples 在执行后更新)
    import json as _json
    exp_data = _json.loads((Path(tmp_path) / "ops" / "llm_exp" / "experiments.json").read_text(encoding="utf-8"))
    exp_live = next(e for e in exp_data if e["experiment_id"] == exp["experiment_id"])
    samples = exp_live.get("llm_experiment", {}).get("samples", [])
    assert len(samples) == 4
    assert all(s.get("production_run_id") or s.get("reason") for s in samples)
    # 记录真实实验证据 (诚实: 含失败样本, 不筛选)
    evidence = {"hypothesis": h, "experiment_id": exp["experiment_id"],
                "comparison": cmp, "outcome": oc, "real_llm": True,
                "samples": samples}
    (Path(tmp_path) / "s26-real-experiment-evidence.json").write_text(
        __import__("json").dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nREAL LLM EXPERIMENT: {cmp['result']} | effectiveness: {oc['effectiveness']}")
    print(f"  {cmp.get('reason', '')}")
    print(f"  samples: {[(s['arm'], s['eligible'], s.get('reason', '')) for s in samples]}")
