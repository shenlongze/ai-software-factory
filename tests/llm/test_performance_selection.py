"""S33: Performance-aware Workforce Selection。

覆盖:
- Performance 从真实 Production Evidence 投影 (无样本 → 0 诚实)
- 确定性 Ranking (capability → eligible → permission → policy → score)
- Governance 优先于 Performance (self_elevate → rejected)
- Cold-start (sample_count=0 不锁死)
- Performance Snapshot (历史可解释)
- 真实替换实验 (Evidence 变化 → Selection 变化)
- CLI / API
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.plugin_kernel import (  # noqa: E402
    bootstrap, register_plugin, plugin_status, _load as pl_load, _save as pl_save,
)
from factory_console.performance_selection import (  # noqa: E402
    rank_plugins, select_plugin, plugin_performance, selection_history,
    cold_start_strategy, plugin_performance_history,
)
from factory_console.workforce_os import _get_or_create_agent_profile  # noqa: E402
from factory_console.workforce_composition import bind_agent_profile  # noqa: E402
from factory_console.workforce import create_task  # noqa: E402
from factory_console.production_run import (  # noqa: E402
    register_workflow, create_production_run, execute_production_run,
)


def _add_provider(tmp_path, pid: str, name: str) -> None:
    register_plugin(str(tmp_path), plugin_id=pid, name=name, version="1.0", type="provider",
                    capabilities=["llm.complete"], permissions=["use_llm"])
    plugin_status(str(tmp_path), pid, target="ENABLED")


def _add_evidence(tmp_path, agent_id: str, runs: int = 2) -> None:
    """给 agent 造 runs 真实 evidence (COMPLETED + PASS)。"""
    register_workflow(str(tmp_path), workflow_id="wf", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])

    def gf(node_id):
        def fn(input_data):
            return {"ok": True, "output": {"code": "x"},
                    "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n"
                                   "+def a():\n+    return 1\n"),
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}
        return fn
    for _ in range(runs):
        r = create_production_run(str(tmp_path), "wf")
        execute_production_run(str(tmp_path), r["run_id"], executor_factory=gf,
                               artifact_root=str(tmp_path))
        create_task(str(tmp_path), role="software_developer", objective="x",
                    production_run_id=r["run_id"])
        tasks_path = Path(tmp_path) / "workforce" / "tasks.json"
        data = json.loads(tasks_path.read_text(encoding="utf-8"))
        data[-1]["agent_id"] = agent_id
        tasks_path.write_text(json.dumps(data), encoding="utf-8")


def _setup_two_providers(tmp_path) -> str:
    bootstrap(str(tmp_path))
    _add_provider(tmp_path, "provider.a", "A")
    _add_provider(tmp_path, "provider.b", "B")
    pa = _get_or_create_agent_profile(str(tmp_path), "software_developer")
    bind_agent_profile(str(tmp_path), agent_profile_id=pa["agent_id"],
                       provider_plugin_id="provider.a")
    _add_evidence(tmp_path, pa["agent_id"], runs=2)
    return pa["agent_id"]


# --- Performance 从真实 Evidence 投影 ---

def test_performance_from_evidence(tmp_path):
    _setup_two_providers(tmp_path)
    pa = plugin_performance(str(tmp_path), "provider.a")
    assert pa["sample_count"] == 2
    assert pa["success_rate"] == 1.0
    assert pa["ranking_score"] > 0
    pb = plugin_performance(str(tmp_path), "provider.b")
    assert pb["sample_count"] == 0
    assert pb["ranking_score"] == 0.0
    assert "无 Production Evidence" in pb["explain"]  # 诚实


# --- 确定性 Ranking ---

def test_deterministic_ranking(tmp_path):
    _setup_two_providers(tmp_path)
    rk1 = rank_plugins(str(tmp_path), required_capability="llm.complete")
    rk2 = rank_plugins(str(tmp_path), required_capability="llm.complete")
    assert rk1["ranking"] == rk2["ranking"]  # 相同输入 → 相同排序
    # A (有 evidence) 排前
    assert rk1["ranking"].index("provider.a") < rk1["ranking"].index("provider.b")


# --- Governance 优先于 Performance ---

def test_governance_over_performance(tmp_path):
    _setup_two_providers(tmp_path)
    # B 加 self_elevate (即使 B 之后有 evidence 也不被选)
    data = pl_load(str(tmp_path), "plugins")
    for p in data:
        if p["plugin_id"] == "provider.b":
            p["permissions"] = ["self_elevate"]
    pl_save(str(tmp_path), "plugins", data)
    rk = rank_plugins(str(tmp_path), required_capability="llm.complete")
    assert any(r["plugin_id"] == "provider.b" and "permission_denied" in r["reason"]
               for r in rk["rejected"])
    assert "provider.b" not in rk["ranking"]


# --- Selection + Snapshot ---

def test_selection_and_snapshot(tmp_path):
    _setup_two_providers(tmp_path)
    sel = select_plugin(str(tmp_path), required_capability="llm.complete")
    assert sel["selected"] is True
    assert sel["plugin_id"] == "provider.a"
    assert "sample_count=2" in sel["reason"]  # 可解释
    assert sel["snapshot_id"]
    history = selection_history(str(tmp_path))
    assert len(history) == 1
    assert history[0]["selected_plugin"] == "provider.a"
    # 历史 snapshot 保留当时 performance
    assert history[0]["performance"]["sample_count"] == 2


# --- 真实替换实验: Evidence 变化 → Selection 变化 ---

def test_evidence_driven_selection_change(tmp_path):
    aid = _setup_two_providers(tmp_path)
    # 初始: A 有 evidence → A 被选
    sel1 = select_plugin(str(tmp_path), required_capability="llm.complete")
    assert sel1["plugin_id"] == "provider.a"
    # B 获得 10 runs evidence (真实) → B ranking_score 上升
    from factory_console.workforce_os import _get_or_create_agent_profile
    pb = _get_or_create_agent_profile(str(tmp_path), "qa_engineer")
    bind_agent_profile(str(tmp_path), agent_profile_id=pb["agent_id"],
                       provider_plugin_id="provider.b")
    _add_evidence_b(tmp_path, pb["agent_id"], runs=10)
    sel2 = select_plugin(str(tmp_path), required_capability="llm.complete")
    # B 样本多 → confidence 高 → B 被选 (Evidence 驱动, 非 hard-coded)
    assert sel2["plugin_id"] == "provider.b"
    assert sel1["plugin_id"] != sel2["plugin_id"]


def _add_evidence_b(tmp_path, agent_id: str, runs: int = 10) -> None:
    register_workflow(str(tmp_path), workflow_id="wf", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])

    def gf(node_id):
        def fn(input_data):
            return {"ok": True, "output": {"code": "x"},
                    "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n"
                                   "+def a():\n+    return 1\n"),
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}
        return fn
    for _ in range(runs):
        r = create_production_run(str(tmp_path), "wf")
        execute_production_run(str(tmp_path), r["run_id"], executor_factory=gf,
                               artifact_root=str(tmp_path))
        create_task(str(tmp_path), role="qa_engineer", objective="x",
                    production_run_id=r["run_id"])
        tasks_path = Path(tmp_path) / "workforce" / "tasks.json"
        data = json.loads(tasks_path.read_text(encoding="utf-8"))
        data[-1]["agent_id"] = agent_id
        tasks_path.write_text(json.dumps(data), encoding="utf-8")


# --- Cold-start ---

def test_cold_start(tmp_path):
    bootstrap(str(tmp_path))
    _add_provider(tmp_path, "provider.x", "X")
    _add_provider(tmp_path, "provider.y", "Y")
    cs = cold_start_strategy(str(tmp_path), required_capability="llm.complete")
    assert cs["strategy"] == "registration_order"  # 全部无 evidence → 注册顺序, 不锁死
    assert "不锁死" in cs["note"]
    # 有 evidence 时 → evidence_priority
    aid = _get_or_create_agent_profile(str(tmp_path), "software_developer")["agent_id"]
    bind_agent_profile(str(tmp_path), agent_profile_id=aid, provider_plugin_id="provider.x")
    _add_evidence(tmp_path, aid, runs=1)
    cs2 = cold_start_strategy(str(tmp_path), required_capability="llm.complete")
    assert cs2["strategy"] == "evidence_priority"


# --- Performance History ---

def test_performance_history(tmp_path):
    _setup_two_providers(tmp_path)
    select_plugin(str(tmp_path), required_capability="llm.complete")
    hist = plugin_performance_history(str(tmp_path), "provider.a")
    assert len(hist) == 1
    assert hist[0]["selected_plugin"] == "provider.a"


# --- CLI ---

def test_cli_select(tmp_path):
    _setup_two_providers(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["select", "select", "llm.complete", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["select", "rank", "llm.complete", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["select", "perf", "provider.a", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["select", "history", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["select", "cold-start", "llm.complete", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_select(tmp_path):
    _setup_two_providers(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/workforces/select-ranked", json={"capability": "llm.complete"})
    assert resp.status_code == 200
    assert resp.json()["selected"] is True
    resp = client.get("/api/plugins/provider.a/performance")
    assert resp.status_code == 200
    assert resp.json()["sample_count"] == 2
    resp = client.get("/api/plugins/provider.a/performance-history")
    assert resp.status_code == 200
    resp = client.get("/api/selection/history")
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1
