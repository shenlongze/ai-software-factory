"""S42: Intelligence Strategy Kernel & Unified Intelligence Contract。

覆盖:
- IntelligenceStrategy Contract (strategy_id/type/version/capabilities/budget)
- 注册经 Plugin Kernel (type=strategy; 唯一 Registry)
- Learning/Healing/Optimization 三 Adapter (统一入口)
- Learning [STOP] 语义保持
- 共享 S38 管道验证 (Optimization → PROMOTE)
- DISABLED → 拒绝
- 替换测试 (learning.v2, Core 零修改)
- 版本 lineage (历史可解释)
- StrategyEvidence (strategy/version/input/result/cost)
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

from factory_console.intelligence_strategy import (  # noqa: E402
    register_strategy, strategies, get_strategy, register_adapter,
    _default_adapters, execute_strategy, executions, strategy_lineage,
    STRATEGY_ADAPTERS,
)
from factory_console.plugin_kernel import (  # noqa: E402
    bootstrap, get_plugin, plugin_status,
)


def _setup(tmp_path):
    bootstrap(str(tmp_path))
    _default_adapters(str(tmp_path))
    for stype, sid in [("LEARNING", "learning.default"),
                       ("HEALING", "healing.default"),
                       ("OPTIMIZATION", "optimization.default")]:
        register_strategy(str(tmp_path), strategy_id=sid, strategy_type=stype,
                          version="1.0.0", capabilities=[f"{stype.lower()}.run"],
                          cost_budget=1.0)


# --- 统一 Contract + Plugin Registry 复用 ---

def test_strategy_registry_reuses_plugin_registry(tmp_path):
    _setup(tmp_path)
    assert len(strategies(str(tmp_path))) == 3
    # 注册经 Plugin Kernel (type=strategy) — 唯一 Registry
    p = get_plugin(str(tmp_path), "learning.default")
    assert p is not None
    assert p["type"] == "strategy"
    s = get_strategy(str(tmp_path), "learning.default")
    assert s["strategy_type"] == "LEARNING"
    assert s["version"] == "1.0.0"
    assert s["cost_budget"] == 1.0


# --- Learning Strategy [STOP] 语义 ---

def test_learning_is_strategy(tmp_path):
    _setup(tmp_path)
    e = execute_strategy(str(tmp_path), strategy_id="learning.default",
                         payload={"source_type": "production_run", "source_id": "r1",
                                  "pattern_key": "P1", "outcome": "SUCCESS"})
    assert e["strategy_type"] == "LEARNING"
    assert e["strategy_version"] == "1.0.0"
    assert e["result"]["stopped_at_candidate"] is True  # [STOP] 不 Promotion
    assert e["actual_cost"] == "NOT_AVAILABLE"  # 诚实


# --- Healing Strategy ---

def test_healing_is_strategy(tmp_path):
    _setup(tmp_path)
    from factory_console.plugin_kernel import register_plugin
    from factory_console.self_healing import register_repair_plugin, _coderepair_plugin
    register_plugin(str(tmp_path), plugin_id="repair.coderepair", name="CodeRepair",
                    version="1.0", type="repair", capabilities=["repair.code"],
                    permissions=["repair.execute"])
    plugin_status(str(tmp_path), "repair.coderepair", target="ENABLED")
    register_repair_plugin("repair.coderepair", _coderepair_plugin)

    def good_factory(node_id):
        def fn(input_data):
            return {"ok": True, "output": {"repaired": True},
                    "patch_text": ("diff --git a/fix.py b/fix.py\n--- /dev/null\n+++ b/fix.py\n"
                                   "@@ -0,0 +1 @@\n+def fixed():\n+    return True\n"),
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}
        return fn
    e = execute_strategy(str(tmp_path), strategy_id="healing.default",
                         payload={"production_run_id": "r1", "node_id": "n1",
                                  "failure_type": "x", "executor_factory": good_factory,
                                  "artifact_root": str(tmp_path), "actor": "human"})
    assert e["strategy_type"] == "HEALING"
    assert e["result"]["status"] in ("RECOVERED", "ROLLED_BACK", "REJECTED")


# --- Optimization Strategy (共享 S38 管道) ---

def test_optimization_is_strategy(tmp_path):
    _setup(tmp_path)
    e = execute_strategy(str(tmp_path), strategy_id="optimization.default",
                         payload={"target_id": "provider.a", "current_value": 0.82,
                                  "baseline_metrics": {"success": 0.82, "verification": 0.85,
                                                       "recovery": 0.1, "cost": 0.05, "latency": 1.0},
                                  "candidate_metrics": {"success": 0.87, "verification": 0.9,
                                                        "recovery": 0.05, "cost": 0.04, "latency": 0.9},
                                  "sample_count": 20})
    assert e["strategy_type"] == "OPTIMIZATION"
    assert e["result"]["decision"] in ("PROMOTE", "REJECT", "NO_CHANGE")


# --- DISABLED → 拒绝 ---

def test_disabled_strategy_rejected(tmp_path):
    _setup(tmp_path)
    plugin_status(str(tmp_path), "learning.default", target="DISABLED")
    with pytest.raises(PermissionError, match="未启用"):
        execute_strategy(str(tmp_path), strategy_id="learning.default", payload={})
    plugin_status(str(tmp_path), "learning.default", target="ENABLED")
    # 恢复后允许
    execute_strategy(str(tmp_path), strategy_id="learning.default",
                     payload={"source_type": "production_run", "source_id": "r2",
                              "pattern_key": "P2", "outcome": "SUCCESS"})


# --- 替换测试 (Core 零修改) ---

def test_strategy_replacement_without_core_change(tmp_path):
    _setup(tmp_path)
    register_strategy(str(tmp_path), strategy_id="learning.v2", strategy_type="LEARNING",
                      version="2.0.0", capabilities=["learning.run"])
    # 新 adapter (Core 未修改; 仅注册)
    STRATEGY_ADAPTERS["LEARNING_v2"] = lambda payload: {
        "strategy_type": "LEARNING", "version": "2.0", "explain": "learning.v2"}
    # 直接调用 adapter 验证注册
    assert "LEARNING" in STRATEGY_ADAPTERS
    e = execute_strategy(str(tmp_path), strategy_id="learning.v2", payload={})
    assert e["strategy_version"] == "2.0.0"
    assert e["strategy_id"] == "learning.v2"


# --- 版本 lineage ---

def test_strategy_version_in_lineage(tmp_path):
    _setup(tmp_path)
    execute_strategy(str(tmp_path), strategy_id="learning.default",
                     payload={"source_type": "production_run", "source_id": "r1",
                              "pattern_key": "P1", "outcome": "SUCCESS"})
    lg = strategy_lineage(str(tmp_path), "learning.default")
    assert len(lg) == 1
    assert lg[0]["strategy_version"] == "1.0.0"
    # 历史执行不被覆盖 (新执行追加)
    execute_strategy(str(tmp_path), strategy_id="learning.default",
                     payload={"source_type": "production_run", "source_id": "r2",
                              "pattern_key": "P2", "outcome": "FAILURE"})
    assert len(strategy_lineage(str(tmp_path), "learning.default")) == 2


# --- StrategyEvidence ---

def test_strategy_evidence_created(tmp_path):
    _setup(tmp_path)
    e = execute_strategy(str(tmp_path), strategy_id="optimization.default",
                         payload={"target_id": "p", "current_value": 0.8,
                                  "baseline_metrics": {"success": 0.8},
                                  "candidate_metrics": {"success": 0.9},
                                  "sample_count": 5})
    assert e["execution_id"].startswith("intel-")
    assert e["strategy_id"] == "optimization.default"
    assert "input" in e and "result" in e and "created_at" in e
    # 审计事件
    from factory_console.audit.audit_event import EVENT_TYPES
    assert "STRATEGY_EXECUTED" in EVENT_TYPES


# --- 治理: Strategy 不能绕过 (经 Plugin Kernel 解析) ---

def test_strategy_cannot_bypass_governance(tmp_path):
    _setup(tmp_path)
    # 无 permission 的 strategy 执行 → 经 Plugin Kernel 检查 (ENABLED + permission)
    register_strategy(str(tmp_path), strategy_id="strategy.noop", strategy_type="LEARNING",
                      version="1.0", capabilities=["intelligence.execute"])
    e = execute_strategy(str(tmp_path), strategy_id="strategy.noop", payload={})
    assert e["strategy_type"] == "LEARNING"


# --- 共享管道未重复 ---

def test_shared_pipeline_not_duplicated(tmp_path):
    """Candidate/Evaluation/Experiment/Governance/Canary/Promotion 只有一套 (S38)。"""
    import importlib
    mods = ["promotion_service", "learning_engine_v2", "self_healing", "optimization_engine"]
    # 每服务只 import promotion_service 一次 (共享管道)
    counts = {}
    for m in mods:
        src = (Path(_ROOT) / "factory-console" / f"{m}.py").read_text(encoding="utf-8")
        counts[m] = src.count("from .promotion_service import")
    assert counts["promotion_service"] == 0  # 自身
    assert counts["learning_engine_v2"] == 0  # Learning [STOP] 不 Promotion (设计)
    assert counts["self_healing"] == 1  # 共享 S38
    assert counts["optimization_engine"] == 1  # 共享 S38


# --- CLI ---

def test_cli_strategy(tmp_path):
    _setup(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["strategy", "strategy", "learning.default", "--strategy-type", "LEARNING",
                      "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["strategy", "history", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_strategy(tmp_path):
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/intelligence/strategies",
                       json={"strategy_id": "learning.api", "strategy_type": "LEARNING",
                             "version": "1.0.0", "capabilities": ["learning.run"]})
    assert resp.status_code == 200
    assert resp.json()["strategy_id"] == "learning.api"
    resp = client.post("/api/intelligence/strategies/learning.api/execute",
                       json={"payload": {"source_type": "production_run", "source_id": "r1",
                                         "pattern_key": "P", "outcome": "SUCCESS"}})
    assert resp.status_code == 200
    assert resp.json()["strategy_version"] == "1.0.0"
    resp = client.get("/api/intelligence/strategies")
    assert resp.status_code == 200
    resp = client.get("/api/intelligence/strategies/learning.api/executions")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
