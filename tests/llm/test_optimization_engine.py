"""S40: Governed Self-Optimization。

覆盖:
- OptimizationOpportunity (evidence-driven, 非 LLM; 来源白名单)
- OptimizationCandidate (Proposal; multi-candidate)
- Optimization Strategy Plugin (type=optimization; disabled 拒绝; 替换不修改 Core)
- Evaluation → PROMOTE/REJECT/NO_CHANGE (可解释 reason)
- Case A: Improvement → PROMOTE; Case B: Insufficient → NO_CHANGE;
- Case C: Cost Worse → REJECT; Case D: Governance Denied → REJECT
- Anti-Thrashing (cooldown/max_changes)
- Optimization Budget (max_* → STOP)
- New Evidence → S37 Observation
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

from factory_console.plugin_kernel import (  # noqa: E402
    bootstrap, register_plugin, plugin_status,
)
from factory_console.optimization_engine import (  # noqa: E402
    create_opportunity, create_candidate, candidates, register_opt_plugin,
    _provider_opt_plugin, evaluate_optimization, run_optimization,
    check_thrashing, check_budget, optimization_metrics, decisions,
    opportunities, OPT_PLUGINS,
)


def _setup(tmp_path):
    bootstrap(str(tmp_path))
    register_plugin(str(tmp_path), plugin_id="opt.provider", name="ProviderOpt",
                    version="1.0", type="optimization",
                    capabilities=["optimize.provider"], permissions=["optimize.execute"])
    plugin_status(str(tmp_path), "opt.provider", target="ENABLED")
    register_opt_plugin("opt.provider", _provider_opt_plugin)


def _opp_and_cands(tmp_path, source="performance", risk="MEDIUM"):
    _setup(tmp_path)
    opp = create_opportunity(str(tmp_path), source=source, target_type="provider",
                             target_id="provider.a", metric="success_rate",
                             current_value=0.82, risk=risk)
    cands = []
    for cp in _provider_opt_plugin(opp):
        cands.append(create_candidate(str(tmp_path), opportunity_id=opp["opportunity_id"],
                                      strategy_plugin_id="opt.provider",
                                      target=cp["candidate_target"],
                                      proposed_change=cp["proposed_change"],
                                      risk=risk))  # 继承 opportunity risk (测试可控)
    return opp, cands


# --- Opportunity 必须来自真实 Evidence ---

def test_opportunity_requires_evidence(tmp_path):
    _setup(tmp_path)
    opp = create_opportunity(str(tmp_path), source="performance", target_type="provider",
                             target_id="p", metric="success_rate", current_value=0.82)
    assert opp["opportunity_id"].startswith("opp-")
    assert opp["evidence_refs"] == ["performance:p"]
    with pytest.raises(ValueError, match="非法 opportunity 来源"):
        create_opportunity(str(tmp_path), source="llm", target_type="provider",
                           target_id="p", metric="m", current_value=0.5)


# --- Multi-candidate ---

def test_multi_candidate(tmp_path):
    opp, cands = _opp_and_cands(tmp_path)
    all_c = candidates(str(tmp_path), opportunity_id=opp["opportunity_id"])
    assert len(all_c) >= 3  # multi-candidate
    assert all(c["status"] == "PROPOSED" for c in all_c)
    assert all(c["opportunity_id"] == opp["opportunity_id"] for c in all_c)


# --- Evaluation: Case A/B/C ---

def test_evaluation_promote(tmp_path):
    opp, cands = _opp_and_cands(tmp_path)
    d = evaluate_optimization(str(tmp_path), cands[0]["candidate_id"],
                              baseline_metrics={"success": 0.82, "verification": 0.85,
                                                "recovery": 0.1, "cost": 0.05, "latency": 1.0},
                              candidate_metrics={"success": 0.87, "verification": 0.9,
                                                 "recovery": 0.05, "cost": 0.04, "latency": 0.9},
                              sample_count=20)
    assert d["decision"] == "PROMOTE"
    assert "success" in d["reason"]  # 可解释
    assert d["deltas"]["delta_success"] > 0


def test_evaluation_no_change_insufficient(tmp_path):
    """样本不足 → NO_CHANGE (不伪装)。"""
    opp, cands = _opp_and_cands(tmp_path)
    d = evaluate_optimization(str(tmp_path), cands[1]["candidate_id"],
                              baseline_metrics={"success": 0.82},
                              candidate_metrics={"success": 0.9},
                              sample_count=1)
    assert d["decision"] == "NO_CHANGE"
    assert "样本不足" in d["reason"]


def test_evaluation_reject_cost(tmp_path):
    """成本显著恶化 → REJECT。"""
    opp, cands = _opp_and_cands(tmp_path)
    d = evaluate_optimization(str(tmp_path), cands[2]["candidate_id"],
                              baseline_metrics={"success": 0.82, "verification": 0.85,
                                                "recovery": 0.1, "cost": 0.05, "latency": 1.0},
                              candidate_metrics={"success": 0.84, "verification": 0.86,
                                                 "recovery": 0.09, "cost": 0.09, "latency": 1.2},
                              sample_count=20)
    assert d["decision"] == "REJECT"
    assert "成本" in d["reason"] or "cost" in d["reason"]


# --- run_optimization 全链 (PROMOTE → Snapshot) ---

def test_run_optimization_promote(tmp_path):
    opp, cands = _opp_and_cands(tmp_path)
    r = run_optimization(str(tmp_path), cands[0]["candidate_id"],
                         baseline_metrics={"success": 0.82, "verification": 0.85,
                                           "recovery": 0.1, "cost": 0.05, "latency": 1.0},
                         candidate_metrics={"success": 0.87, "verification": 0.9,
                                            "recovery": 0.05, "cost": 0.04, "latency": 0.9},
                         sample_count=20)
    assert r["decision"] == "PROMOTE"
    assert r["promoted"] is True
    assert r["snapshot_id"].startswith("psnap-")
    # New Evidence → S37 Observation
    from factory_console.learning_engine_v2 import observations
    obs = observations(str(tmp_path))
    assert any(o["source_type"] == "optimization" for o in obs)


# --- Case D: Governance Denied (HIGH risk non-human) ---

def test_governance_denied(tmp_path):
    opp, cands = _opp_and_cands(tmp_path, risk="HIGH")
    # HIGH risk + non-human → REJECT (human_gate)
    r = run_optimization(str(tmp_path), cands[0]["candidate_id"],
                         baseline_metrics={"success": 0.82, "verification": 0.85,
                                           "recovery": 0.1, "cost": 0.05, "latency": 1.0},
                         candidate_metrics={"success": 0.87, "verification": 0.9,
                                            "recovery": 0.05, "cost": 0.04, "latency": 0.9},
                         sample_count=20, human_actor="system")
    assert r["decision"] == "REJECT"
    assert "human_gate" in r["reason"]


# --- Anti-Thrashing ---

def test_anti_thrashing(tmp_path):
    opp, cands = _opp_and_cands(tmp_path)
    # 造 2 个 PROMOTE decisions
    for i in range(2):
        evaluate_optimization(str(tmp_path), cands[i]["candidate_id"],
                              baseline_metrics={"success": 0.82, "verification": 0.85,
                                                "recovery": 0.1, "cost": 0.05, "latency": 1.0},
                              candidate_metrics={"success": 0.87, "verification": 0.9,
                                                 "recovery": 0.05, "cost": 0.04, "latency": 0.9},
                              sample_count=20)
    t = check_thrashing(str(tmp_path), metric="success_rate", max_changes_per_period=2)
    assert t["blocked"] is True  # 周期内已达 max_changes → 防震荡
    assert t["recent_promotions"] == 2


# --- Budget ---

def test_budget_stop(tmp_path):
    _setup(tmp_path)
    b = check_budget(str(tmp_path), max_candidates=0)  # 0 候选上限
    assert b["allowed"] is False
    assert "candidates" in b["over"]


# --- Optimization Plugin disabled → 拒绝 ---

def test_opt_plugin_disabled(tmp_path):
    _setup(tmp_path)
    plugin_status(str(tmp_path), "opt.provider", target="DISABLED")
    opp = create_opportunity(str(tmp_path), source="performance", target_type="provider",
                             target_id="p", metric="m", current_value=0.5)
    # Plugin 解析被拒 (run_optimization 内部 _resolve 不在公开路径; 直接测注册表治理)
    from factory_console.optimization_engine import _resolve_opt_plugin
    with pytest.raises(PermissionError, match="未启用"):
        _resolve_opt_plugin(str(tmp_path), "opt.provider")
    plugin_status(str(tmp_path), "opt.provider", target="ENABLED")


# --- Strategy Plugin 替换 (Core 零修改) ---

def test_opt_plugin_replacement(tmp_path):
    _setup(tmp_path)
    register_plugin(str(tmp_path), plugin_id="opt.alt", name="AltOpt", version="2.0",
                    type="optimization", capabilities=["optimize.provider"],
                    permissions=["optimize.execute"])
    plugin_status(str(tmp_path), "opt.alt", target="ENABLED")

    def alt_plugin(opp):
        return [{"candidate_target": "alt", "proposed_change": "alt strategy",
                 "expected_outcome": 0.9, "expected_cost": 0.01, "risk": "LOW"}]
    register_opt_plugin("opt.alt", alt_plugin)
    assert "opt.alt" in OPT_PLUGINS  # 注册成功 (Core 零修改)
    assert OPT_PLUGINS["opt.alt"]({})[0]["proposed_change"] == "alt strategy"


# --- Metrics 诚实 ---

def test_metrics_honest(tmp_path):
    _setup(tmp_path)
    m = optimization_metrics(str(tmp_path))
    assert m["optimization_attempts"] == 0
    assert m["optimization_cost_per_improvement"] == "NOT_AVAILABLE"  # 无数据诚实
    opp = create_opportunity(str(tmp_path), source="performance", target_type="provider",
                             target_id="provider.a", metric="success_rate",
                             current_value=0.82)
    cands = [create_candidate(str(tmp_path), opportunity_id=opp["opportunity_id"],
                              strategy_plugin_id="opt.provider",
                              target=cp["candidate_target"],
                              proposed_change=cp["proposed_change"], risk="MEDIUM")
             for cp in _provider_opt_plugin(opp)]
    run_optimization(str(tmp_path), cands[0]["candidate_id"],
                     baseline_metrics={"success": 0.82, "verification": 0.85,
                                       "recovery": 0.1, "cost": 0.05, "latency": 1.0},
                     candidate_metrics={"success": 0.87, "verification": 0.9,
                                        "recovery": 0.05, "cost": 0.04, "latency": 0.9},
                     sample_count=20)
    m2 = optimization_metrics(str(tmp_path))
    assert m2["optimization_attempts"] >= 1
    assert m2["optimization_success_rate"] > 0


# --- CLI ---

def test_cli_optimize(tmp_path):
    _setup(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["optimize", "opportunity", "--target-id", "p1", "--value", "0.82",
                      "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["optimize", "thrashing", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["optimize", "budget", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["optimize", "history", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_optimize(tmp_path):
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/optimizations/opportunities",
                       json={"source": "performance", "target_type": "provider",
                             "target_id": "p", "metric": "success_rate",
                             "current_value": 0.82})
    assert resp.status_code == 200
    opp = resp.json()
    assert opp["opportunity_id"].startswith("opp-")
    resp = client.post("/api/optimizations/opportunities",
                       json={"source": "llm", "target_type": "provider",
                             "target_id": "p", "metric": "m", "current_value": 0.5})
    assert resp.status_code == 400  # 非法来源
    resp = client.get("/api/optimizations/metrics")
    assert resp.status_code == 200
    resp = client.get("/api/optimizations/history")
    assert resp.status_code == 200
    assert "opportunities" in resp.json()
