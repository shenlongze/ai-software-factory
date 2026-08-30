"""S23: Production Intelligence & Root-Cause Intelligence。

覆盖:
- RCA: incident → signals → correlations → root cause candidates → evidence
- Evidence weighting (deterministic confidence)
- Hallucination Protection (不存在 evidence_ref → reject)
- Recommendation (risk/requires_approval) + Decision + Outcome lineage
- Historical Pattern (相似 incident)
- Re-analysis (新 analysis_id 不覆盖)
- CLI / API
- Real E2E: 退化 incident → RCA → recommendation
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
    register_workflow, create_production_run, execute_production_run, get_production_run,
)
from factory_console.production_evaluation import evaluate  # noqa: E402
from factory_console.governance_service import (  # noqa: E402
    request_approval, approve,
)
from factory_console.release_service import (  # noqa: E402
    create as rel_create, execute as rel_execute, get_release,
)
from factory_console.health_service import (  # noqa: E402
    health_check, create_incident,
)
from factory_console.production_intelligence import (  # noqa: E402
    analyze_incident, get_analysis, list_analyses, analysis_evidence,
    list_recommendations, decide_recommendation, record_outcome, intelligence_metrics,
    _validate_evidence_refs,
)


def _patch(fname: str, body: str = "def x():\n    return 1\n") -> str:
    lines = "".join(f"+{ln}\n" for ln in body.rstrip("\n").split("\n"))
    return f"diff --git a/{fname} b/{fname}\n--- /dev/null\n+++ b/{fname}\n@@ -0,0 +1,{len(body.rstrip(chr(10)).split(chr(10)))} @@\n{lines}"


def _make_release(tmp_path, fname: str = "a.py", body: str = "def x():\n    return 1\n") -> str:
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])
    run = create_production_run(str(tmp_path), "wf-1")
    patch = _patch(fname, body)

    def factory(node_id):
        def fn(input_data):
            return {"ok": True, "output": {"code": "x"}, "patch_text": patch,
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}
        return fn
    execute_production_run(str(tmp_path), run["run_id"], executor_factory=factory,
                           artifact_root=str(tmp_path))
    run2 = get_production_run(str(tmp_path), run["run_id"])
    evaluate(str(tmp_path), run["run_id"])
    arts = list(run2.get("artifacts", []))
    a = request_approval(str(tmp_path), production_run_id=run["run_id"],
                         artifact_ids=arts, requested_by="dev-agent")
    approve(str(tmp_path), a["approval_id"], decided_by="human")
    rel = rel_create(str(tmp_path), run["run_id"])
    rel_execute(str(tmp_path), rel["release_id"])
    return get_release(str(tmp_path), rel["release_id"])["release_id"]


def _make_incident(tmp_path) -> str:
    """Release → 退化 → health UNHEALTHY → incident。返回 incident_id。"""
    rel_id = _make_release(tmp_path)
    ws = Path(tmp_path) / "workspace"
    (ws / "a.py").write_text("def broken(:\n    return\n", encoding="utf-8")
    hc = health_check(str(tmp_path), rel_id)
    assert hc["result"] == "UNHEALTHY"
    inc = create_incident(str(tmp_path), hc)
    return inc["incident_id"]


# --- E2E-1: Incident → RCA ---

def test_rca_full_chain(tmp_path):
    """Incident → signals → correlations → root cause candidates → evidence。"""
    inc_id = _make_incident(tmp_path)
    an = analyze_incident(str(tmp_path), inc_id)
    assert an["status"] == "COMPLETED"
    assert an["incident_id"] == inc_id
    # signals
    assert len(an["signals"]) >= 2
    assert any(s["signal_type"] == "health_check_failed" for s in an["signals"])
    # correlations
    assert len(an["correlations"]) >= 1
    # root cause candidates
    assert len(an["root_cause_candidates"]) >= 1
    rel_reg = next(c for c in an["root_cause_candidates"] if c["category"] == "release_regression")
    assert rel_reg["status"] in ("SUPPORTED", "POSSIBLE")
    assert rel_reg["confidence"] > 0
    assert rel_reg["evidence_refs"], "root cause 必须有 evidence"
    # evidence 可追溯
    ev = analysis_evidence(str(tmp_path), an["analysis_id"])
    assert all(e["resolved"] for e in ev)
    assert any(e["ref"].startswith("hchk-") for e in ev)


# --- Evidence weighting ---

def test_evidence_weighting(tmp_path):
    """correlation + health evidence → confidence 计算 (deterministic)。"""
    inc_id = _make_incident(tmp_path)
    an = analyze_incident(str(tmp_path), inc_id)
    rel_reg = next(c for c in an["root_cause_candidates"] if c["category"] == "release_regression")
    # release_state + health_check_failed correlation → conf ≥ 0.4
    assert rel_reg["confidence"] >= 0.4
    # confidence 可解释: supporting signals 有 weight
    assert all("weight" in s for s in rel_reg["supporting_signals"])


# --- Hallucination Protection ---

def test_hallucination_protection(tmp_path):
    """不存在的 evidence_ref → invalid (reject)。"""
    valid, invalid = _validate_evidence_refs(str(tmp_path), ["inc-fake123", "rel-nonexistent"])
    assert valid == []
    assert len(invalid) == 2


def test_analysis_evidence_missing_ref(tmp_path):
    """analysis 引用不存在 ref → resolved=False (不 trusted)。"""
    inc_id = _make_incident(tmp_path)
    an = analyze_incident(str(tmp_path), inc_id)
    # 手动注入伪造 ref → evidence 查询应标记 missing
    import json
    p = Path(tmp_path) / "ops" / "intelligence" / "analyses.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    for a in data:
        if a["analysis_id"] == an["analysis_id"]:
            a["evidence_refs"] = a.get("evidence_refs", []) + ["rel-fake999"]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    ev = analysis_evidence(str(tmp_path), an["analysis_id"])
    fake = [e for e in ev if e["ref"] == "rel-fake999"]
    assert fake and fake[0]["resolved"] is False


# --- E2E-2: RCA → Recommendation ---

def test_recommendation_generation(tmp_path):
    """高置信 release regression → ROLLBACK_RELEASE 推荐 (requires_approval=True)。"""
    inc_id = _make_incident(tmp_path)
    an = analyze_incident(str(tmp_path), inc_id)
    rollback_recs = [r for r in an["recommendations"] if r["type"] == "ROLLBACK_RELEASE"]
    if rollback_recs:
        r = rollback_recs[0]
        assert r["risk"] == "HIGH"
        assert r["requires_approval"] is True
        assert r["status"] == "PENDING"
        assert r["evidence_refs"]


# --- E2E-3: Recommendation → Decision → Outcome ---

def test_recommendation_decision_outcome(tmp_path):
    """Recommendation 决策 + outcome 回写 (lineage)。"""
    inc_id = _make_incident(tmp_path)
    an = analyze_incident(str(tmp_path), inc_id)
    recs = list_recommendations(str(tmp_path), analysis_id=an["analysis_id"])
    assert recs, "必须有 recommendations"
    r = decide_recommendation(str(tmp_path), recs[0]["recommendation_id"], decision="APPROVED")
    assert r["status"] == "APPROVED"
    # 重复决策拒绝
    with pytest.raises(ValueError):
        decide_recommendation(str(tmp_path), recs[0]["recommendation_id"], decision="APPROVED")
    r2 = record_outcome(str(tmp_path), recs[0]["recommendation_id"],
                        outcome="rollback_completed", verification_result="PASS")
    assert r2["outcome"] == "rollback_completed"
    assert r2["verification_result"] == "PASS"


# --- E2E-4: Historical Pattern ---

def test_historical_pattern(tmp_path):
    """两个相似 incident → 第二个 analysis 有 historical pattern。"""
    inc1 = _make_incident(tmp_path)
    analyze_incident(str(tmp_path), inc1)
    inc2 = _make_incident(tmp_path)
    an2 = analyze_incident(str(tmp_path), inc2)
    # patterns 应该找到 (同 failed_checks)
    assert len(an2.get("patterns", [])) >= 1
    assert an2["patterns"][0]["evidence_type"] == "historical_pattern"


# --- E2E-5: Re-analysis 不覆盖 ---

def test_reanalysis_new_id(tmp_path):
    """re-analysis → 新 analysis_id (不覆盖旧)。"""
    inc_id = _make_incident(tmp_path)
    a1 = analyze_incident(str(tmp_path), inc_id)
    a2 = analyze_incident(str(tmp_path), inc_id)
    assert a1["analysis_id"] != a2["analysis_id"]
    analyses = list_analyses(str(tmp_path), incident_id=inc_id)
    assert len(analyses) == 2


# --- Metrics ---

def test_intelligence_metrics(tmp_path):
    inc_id = _make_incident(tmp_path)
    analyze_incident(str(tmp_path), inc_id)
    m = intelligence_metrics(str(tmp_path))
    assert m["incident_count"] == 1
    assert m["analyzed_incident_count"] == 1
    assert m["root_cause_candidate_count"] >= 1
    assert 0 <= m["inconclusive_rate"] <= 1


# --- CLI ---

def test_cli_intelligence(tmp_path):
    inc_id = _make_incident(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["intelligence", "analyze", inc_id, "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["intelligence", "history", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["intelligence", "metrics", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["intelligence", "show", "an-x", "--data-dir", str(tmp_path)]) == 1


# --- API ---

def test_api_intelligence(tmp_path):
    inc_id = _make_incident(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/intelligence/analyses", json={"incident_id": inc_id})
    assert resp.status_code == 200
    an = resp.json()
    assert an["status"] == "COMPLETED"
    resp = client.get(f"/api/intelligence/analyses/{an['analysis_id']}")
    assert resp.status_code == 200
    resp = client.get(f"/api/incidents/{inc_id}/root-causes")
    assert resp.status_code == 200
    assert "root_cause_candidates" in resp.json()
    resp = client.get(f"/api/incidents/{inc_id}/recommendations")
    assert resp.status_code == 200
    resp = client.get(f"/api/intelligence/{an['analysis_id']}/evidence")
    assert resp.status_code == 200
    assert "evidence" in resp.json()


# --- Correlation ≠ Causation ---

def test_correlation_not_causation(tmp_path):
    """correlations 必须标注 observation (非 causation)。"""
    inc_id = _make_incident(tmp_path)
    an = analyze_incident(str(tmp_path), inc_id)
    for c in an["correlations"]:
        assert "correlation ≠ causation" in c["note"]
