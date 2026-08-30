"""S38: Learning Evaluation & Governed Promotion。

覆盖:
- S37 LearningCandidate → PromotionCandidate (统一 Contract)
- Evaluation (baseline vs candidate, evidence-based, cost-aware)
- INCONCLUSIVE (样本不足, 不伪装)
- Experiment (budget: max_runs → STOP)
- Governance (Risk 分类; HIGH/CRITICAL → Human Gate 不可绕过)
- Canary (PASS → promote; FAIL → 阻止 promote)
- Promotion (GOVERNED/CANARY PASS 后; immutable Snapshot)
- Lifecycle 非法迁移拒绝
- Evaluator Plugin 替换 (Core 零修改)
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

from factory_console.learning_engine_v2 import (  # noqa: E402
    create_observation, create_hypothesis, create_candidate,
    evaluate_candidate as learn_eval,
)
from factory_console.promotion_service import (  # noqa: E402
    create_promotion_candidate, evaluate_candidate, create_experiment,
    experiment_record_run, classify_risk, governance_mode, decide_promotion,
    create_canary, canary_record_run, canary_compare, promote,
    promotion_candidates, promotion_snapshots, EVALUATOR_PLUGINS,
)


def _validated_learning(tmp_path, pattern="P", success=5, scope="node", min_samples=3):
    for i in range(success):
        create_observation(str(tmp_path), source_type="production_run",
                           source_id=f"r{i}", pattern_key=pattern, outcome="SUCCESS",
                           scope=scope)
    hyp = create_hypothesis(str(tmp_path), statement="S", observation_ids=[])
    lc = create_candidate(str(tmp_path), hypothesis_id=hyp["hypothesis_id"],
                          candidate_type="STRATEGY", content="S", scope=scope)
    learn_eval(str(tmp_path), lc["candidate_id"], evidence_count=success,
               success_count=success, failure_count=0, min_samples=min_samples)
    return lc


def _promo_flow(tmp_path, risk="LOW", sample=8, b={"success": 0.6, "verification": 0.7, "quality": 0.6, "cost": 0.01},
                c={"success": 0.8, "verification": 0.85, "quality": 0.8, "cost": 0.012}):
    lc = _validated_learning(tmp_path)
    pc = create_promotion_candidate(str(tmp_path), learning_candidate_id=lc["candidate_id"],
                                    risk=risk)
    ev = evaluate_candidate(str(tmp_path), pc["promotion_candidate_id"],
                            baseline_metrics=b, candidate_metrics=c, sample_count=sample)
    return pc, ev


# --- S37 → S38 桥接 ---

def test_promotion_candidate_from_learning(tmp_path):
    lc = _validated_learning(tmp_path)
    pc = create_promotion_candidate(str(tmp_path), learning_candidate_id=lc["candidate_id"],
                                    target="strategy", risk="MEDIUM")
    assert pc["promotion_candidate_id"].startswith("prom-")
    assert pc["learning_candidate_id"] == lc["candidate_id"]
    assert pc["lifecycle"] == "CANDIDATE"
    with pytest.raises(ValueError, match="不存在"):
        create_promotion_candidate(str(tmp_path), learning_candidate_id="lrn-nonexistent")


# --- Evaluation ---

def test_evaluation_improved(tmp_path):
    pc, ev = _promo_flow(tmp_path, sample=8)
    assert ev["result"] == "IMPROVED"
    assert ev["deltas"]["delta_success"] > 0
    assert ev["cost_type"] == "estimated"
    # lifecycle: CANDIDATE → EVALUATING → EVALUATED
    c = [x for x in promotion_candidates(str(tmp_path)) if x["promotion_candidate_id"] == pc["promotion_candidate_id"]][0]
    assert c["lifecycle"] == "EVALUATED"


def test_evaluation_inconclusive(tmp_path):
    pc, ev = _promo_flow(tmp_path, sample=1)  # 样本不足
    assert ev["result"] == "INCONCLUSIVE"
    c = [x for x in promotion_candidates(str(tmp_path)) if x["promotion_candidate_id"] == pc["promotion_candidate_id"]][0]
    assert c["lifecycle"] == "INCONCLUSIVE"


def test_evaluation_regressed(tmp_path):
    pc, ev = _promo_flow(tmp_path, sample=8,
                         b={"success": 0.8, "verification": 0.85, "quality": 0.8, "cost": 0.01},
                         c={"success": 0.5, "verification": 0.5, "quality": 0.5, "cost": 0.02})
    assert ev["result"] == "REGRESSED"


# --- Experiment Budget ---

def test_experiment_budget_stop(tmp_path):
    lc = _validated_learning(tmp_path)
    pc = create_promotion_candidate(str(tmp_path), learning_candidate_id=lc["candidate_id"], risk="LOW")
    evaluate_candidate(str(tmp_path), pc["promotion_candidate_id"],
                       baseline_metrics={"success": 0.5}, candidate_metrics={"success": 0.8},
                       sample_count=5)
    decide_promotion(str(tmp_path), pc["promotion_candidate_id"], decision="APPROVE", actor="human")
    exp = create_experiment(str(tmp_path), candidate_id=pc["promotion_candidate_id"], max_runs=3)
    for _ in range(5):
        exp = experiment_record_run(str(tmp_path), exp["experiment_id"], cost=0.01, result="ok")
    assert exp["status"] == "STOPPED"
    assert exp["stop_reason"] == "budget_exhausted"
    assert exp["runs_used"] == 5  # 超限停止 (记录不伪造)


# --- Governance: Risk + Human Gate ---

def test_risk_classification(tmp_path):
    assert classify_risk(str(tmp_path), blast_radius="node") == "LOW"
    assert classify_risk(str(tmp_path), blast_radius="project") == "MEDIUM"
    assert classify_risk(str(tmp_path), blast_radius="workforce") == "HIGH"
    assert classify_risk(str(tmp_path), production_impact=True, capability_change=True) == "CRITICAL"


def test_governance_modes(tmp_path):
    assert governance_mode("LOW", evidence_sufficient=True) == "AUTO_APPROVE"
    assert governance_mode("MEDIUM") == "REVIEW_REQUIRED"
    assert governance_mode("HIGH") == "HUMAN_APPROVAL_REQUIRED"
    assert governance_mode("CRITICAL") == "HUMAN_APPROVAL_REQUIRED"


def test_high_risk_human_gate(tmp_path):
    pc, _ = _promo_flow(tmp_path, risk="HIGH")
    # 非 human → 拒绝
    with pytest.raises(PermissionError, match="Human Gate"):
        decide_promotion(str(tmp_path), pc["promotion_candidate_id"],
                         decision="APPROVE", actor="system")
    # human → 通过
    g = decide_promotion(str(tmp_path), pc["promotion_candidate_id"],
                         decision="APPROVE", actor="human")
    assert g["mode"] == "HUMAN_APPROVAL_REQUIRED"
    c = [x for x in promotion_candidates(str(tmp_path)) if x["promotion_candidate_id"] == pc["promotion_candidate_id"]][0]
    assert c["lifecycle"] == "GOVERNED"


def test_promotion_rejected(tmp_path):
    pc, _ = _promo_flow(tmp_path, risk="LOW")
    g = decide_promotion(str(tmp_path), pc["promotion_candidate_id"],
                         decision="REJECT", actor="human")
    assert g["decision"] == "REJECTED"
    c = [x for x in promotion_candidates(str(tmp_path)) if x["promotion_candidate_id"] == pc["promotion_candidate_id"]][0]
    assert c["lifecycle"] == "REJECTED"


# --- Canary + Promote ---

def test_canary_pass_promote(tmp_path):
    pc, _ = _promo_flow(tmp_path, risk="MEDIUM")
    decide_promotion(str(tmp_path), pc["promotion_candidate_id"], decision="APPROVE", actor="human")
    can = create_canary(str(tmp_path), candidate_id=pc["promotion_candidate_id"], max_runs=3)
    for _ in range(3):
        canary_record_run(str(tmp_path), can["canary_id"], result="ok", verification="PASS")
    cmp = canary_compare(str(tmp_path), can["canary_id"], baseline_success=0.8)
    assert cmp["status"] == "PASS"
    snap = promote(str(tmp_path), pc["promotion_candidate_id"], canary_id=can["canary_id"])
    assert snap["snapshot_id"].startswith("psnap-")
    assert snap["learning_candidate_id"] == pc["learning_candidate_id"]
    assert len(promotion_snapshots(str(tmp_path))) == 1
    c = [x for x in promotion_candidates(str(tmp_path)) if x["promotion_candidate_id"] == pc["promotion_candidate_id"]][0]
    assert c["lifecycle"] == "PROMOTED"


def test_canary_fail_blocks_promotion(tmp_path):
    pc, _ = _promo_flow(tmp_path, risk="LOW")
    decide_promotion(str(tmp_path), pc["promotion_candidate_id"], decision="APPROVE", actor="human")
    can = create_canary(str(tmp_path), candidate_id=pc["promotion_candidate_id"], max_runs=2)
    canary_record_run(str(tmp_path), can["canary_id"], result="fail", verification="FAIL")
    cmp = canary_compare(str(tmp_path), can["canary_id"], baseline_success=0.8)
    assert cmp["status"] == "FAIL"
    with pytest.raises(ValueError, match="Canary 未 PASS"):
        promote(str(tmp_path), pc["promotion_candidate_id"], canary_id=can["canary_id"])


def test_promote_requires_governed(tmp_path):
    pc, _ = _promo_flow(tmp_path, risk="LOW")
    # 未 Governed → 不可 promote
    with pytest.raises(ValueError, match="不可 Promotion"):
        promote(str(tmp_path), pc["promotion_candidate_id"])


# --- Lifecycle 非法迁移 ---

def test_promotion_lifecycle_invalid(tmp_path):
    lc = _validated_learning(tmp_path)
    pc = create_promotion_candidate(str(tmp_path), learning_candidate_id=lc["candidate_id"], risk="LOW")
    from factory_console.promotion_service import _transition
    with pytest.raises(ValueError, match="非法状态迁移"):
        _transition(str(tmp_path), pc["promotion_candidate_id"], target="PROMOTED")  # CANDIDATE→PROMOTED 非法


# --- Evaluator Plugin 替换 (Core 零修改) ---

def test_evaluator_plugin_replacement(tmp_path):
    lc = _validated_learning(tmp_path)
    pc = create_promotion_candidate(str(tmp_path), learning_candidate_id=lc["candidate_id"], risk="LOW")
    # 注册 evaluator plugin
    def conservative(b, c):
        return {"status": "INCONCLUSIVE", "deltas": {}, "confidence": "observed",
                "explain": "conservative evaluator"}
    EVALUATOR_PLUGINS["evaluator.conservative"] = conservative
    ev = evaluate_candidate(str(tmp_path), pc["promotion_candidate_id"],
                            baseline_metrics={"success": 0.6}, candidate_metrics={"success": 0.8},
                            sample_count=8, evaluator_plugin="evaluator.conservative")
    assert ev["result"] == "INCONCLUSIVE"  # plugin 策略生效 (Core 未修改)
    del EVALUATOR_PLUGINS["evaluator.conservative"]


# --- CLI ---

def test_cli_promotion(tmp_path):
    lc = _validated_learning(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["promotion", "candidate", "--learning-candidate", lc["candidate_id"],
                      "--risk", "LOW", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["promotion", "history", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_promotion(tmp_path):
    lc = _validated_learning(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/promotions/candidates",
                       json={"learning_candidate_id": lc["candidate_id"], "risk": "LOW"})
    assert resp.status_code == 200
    pc = resp.json()
    resp = client.post(f"/api/promotions/candidates/{pc['promotion_candidate_id']}/evaluate",
                       json={"baseline_metrics": {"success": 0.6, "verification": 0.7, "quality": 0.6, "cost": 0.01},
                             "candidate_metrics": {"success": 0.8, "verification": 0.85, "quality": 0.8, "cost": 0.012},
                             "sample_count": 8})
    assert resp.status_code == 200
    assert resp.json()["result"] == "IMPROVED"
    resp = client.post(f"/api/promotions/candidates/{pc['promotion_candidate_id']}/decide",
                       json={"decision": "APPROVE", "actor": "human"})
    assert resp.status_code == 200
    resp = client.post(f"/api/promotions/candidates/{pc['promotion_candidate_id']}/canary",
                       json={"max_runs": 3})
    assert resp.status_code == 200
    can = resp.json()
    resp = client.get("/api/promotions/history")
    assert resp.status_code == 200
    assert "candidates" in resp.json()
    # 高风险 non-human 拒绝 (API)
    pc2 = client.post("/api/promotions/candidates",
                      json={"learning_candidate_id": lc["candidate_id"], "risk": "HIGH"}).json()
    resp = client.post(f"/api/promotions/candidates/{pc2['promotion_candidate_id']}/decide",
                       json={"decision": "APPROVE", "actor": "system"})
    assert resp.status_code == 400  # Human Gate
