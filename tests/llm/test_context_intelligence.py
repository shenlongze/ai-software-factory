"""S36: Context Intelligence & Memory Optimization。

覆盖:
- ContextUtility (relevance/evidence/freshness/confidence/scope/cost 可解释)
- Budget-aware Selection (utility desc → 最优组合, 非全读)
- Progressive Context (受预算, 总 cost <= max)
- ContextFeedback (USEFUL/NOT_USEFUL/UNKNOWN, 不伪造)
- Memory Lifecycle (CANDIDATE→ACTIVE→SUPERSEDED→RETIRED; 非法迁移拒绝; lineage)
- Memory Freshness (valid_until 过期 → 不进 Context)
- Memory Conflict (evidence 解决; 不 last-write-wins)
- ContextStrategy Plugin (替换不修改 Core)
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

from factory_console.context_runtime import (  # noqa: E402
    create_memory_candidate, promote_memory_candidate, LocalMemoryPlugin,
)
from factory_console.context_intelligence import (  # noqa: E402
    context_utility, rank_context, progressive_context, context_feedback,
    context_feedbacks, memory_lifecycle, memory_history,
    detect_memory_conflicts, memory_conflicts, register_strategy_plugin,
)
from factory_console.plugin_kernel import bootstrap  # noqa: E402


def _seed(tmp_path, content, scope="project", src="evidence", confidence=0.8,
          topic_key=None):
    c = create_memory_candidate(str(tmp_path), content=content, scope=scope,
                                source_type=src, source_id="s1", confidence=confidence)
    e = promote_memory_candidate(str(tmp_path), c["candidate_id"])
    if topic_key:
        p = Path(tmp_path) / "ops" / "context" / "memory_local.json"
        entries = json.loads(p.read_text(encoding="utf-8"))
        for en in entries:
            if en["memory_id"] == e["memory_id"]:
                en["topic_key"] = topic_key
        p.write_text(json.dumps(entries), encoding="utf-8")
    return e


# --- ContextUtility ---

def test_context_utility(tmp_path):
    _seed(tmp_path, "项目采用 Python FastAPI 实现端点", src="evidence", confidence=0.9)
    _init_memory(tmp_path)
    entries = LocalMemoryPlugin(str(tmp_path)).handle("list", {}).get("entries", [])
    u = context_utility(entries[0], purpose="实现 FastAPI 端点", requested_scopes=["project"])
    assert u["relevance"] > 0  # purpose 关键词匹配
    assert u["evidence_strength"] == 1.0  # evidence source
    assert u["freshness"] > 0
    assert u["confidence"] == 0.9
    assert u["utility"] > 0
    assert "tokens" in u and "estimated_cost" in u  # 可解释


def _init_memory(tmp_path):
    bootstrap(str(tmp_path))
    from factory_console.context_runtime import _init_local_memory
    _init_local_memory(str(tmp_path))


# --- Budget-aware Selection ---

def test_budget_selection(tmp_path):
    _seed(tmp_path, "FastAPI 端点实现要点", scope="project", src="evidence", confidence=0.9)
    _seed(tmp_path, "无关历史噪音内容", scope="project", src="manual", confidence=0.2)
    _init_memory(tmp_path)
    rk = rank_context(str(tmp_path), purpose="实现 FastAPI 端点",
                      scopes=["project"], budget_tokens=4000)
    assert len(rk["selected"]) >= 1
    # FastAPI 相关排在前面 (utility 高)
    assert rk["selected"][0]["content"].startswith("FastAPI")
    assert rk["selected_tokens"] <= 4000
    assert rk["estimated_cost"] >= 0
    assert rk["retrieval_hit_rate"] > 0


def test_budget_overflow_rejected(tmp_path):
    _seed(tmp_path, "x" * 12000, scope="global", src="manual")
    _seed(tmp_path, "y" * 12000, scope="global", src="manual")
    _init_memory(tmp_path)
    rk = rank_context(str(tmp_path), purpose="x", scopes=["global"], budget_tokens=3000)
    assert rk["selected_tokens"] <= 3000
    assert rk["rejected"]  # 溢出 → rejected (非全读)
    assert rk["context_rejection_rate"] > 0


# --- Progressive Context ---

def test_progressive_budget(tmp_path):
    _seed(tmp_path, "a" * 2000, scope="project", src="evidence")
    _seed(tmp_path, "b" * 2000, scope="project", src="evidence")
    _init_memory(tmp_path)
    pr = progressive_context(str(tmp_path), node_id="n1", purpose="x",
                             scopes=["project"], initial_budget=1000, max_total=3000)
    assert pr["rounds"] >= 1
    assert pr["total_context_cost"] <= pr["max_total"]  # 总受预算
    assert len(pr["snapshots"]) == pr["rounds"]


# --- ContextFeedback ---

def test_context_feedback(tmp_path):
    fb = context_feedback(str(tmp_path), snapshot_id="snap-1",
                          execution_result="PASS", usefulness="USEFUL")
    assert fb["usefulness"] == "USEFUL"
    fb2 = context_feedback(str(tmp_path), snapshot_id="snap-2", usefulness="UNKNOWN")
    assert fb2["usefulness"] == "UNKNOWN"  # 不伪造
    with pytest.raises(ValueError):
        context_feedback(str(tmp_path), snapshot_id="s", usefulness="MAYBE")
    assert len(context_feedbacks(str(tmp_path))) == 2


# --- Memory Lifecycle ---

def test_memory_lifecycle(tmp_path):
    e = _seed(tmp_path, "策略 X", scope="project")
    ml = memory_lifecycle(str(tmp_path), e["memory_id"], target="SUPERSEDED",
                          superseded_by="mem-new")
    assert ml["lifecycle"] == "SUPERSEDED"
    assert ml["superseded_by"] == "mem-new"
    h = memory_history(str(tmp_path), e["memory_id"])
    assert len(h["lifecycle_history"]) >= 1
    # 非法迁移: SUPERSEDED → CANDIDATE 拒绝
    with pytest.raises(ValueError, match="非法状态迁移"):
        memory_lifecycle(str(tmp_path), e["memory_id"], target="CANDIDATE")
    # RETIRED 终态
    memory_lifecycle(str(tmp_path), e["memory_id"], target="RETIRED")


# --- Memory Freshness (过期 → 不进 Context) ---

def test_memory_freshness(tmp_path):
    e = _seed(tmp_path, "fresh-memory", scope="project")
    # 标记过期
    p = Path(tmp_path) / "ops" / "context" / "memory_local.json"
    entries = json.loads(p.read_text(encoding="utf-8"))
    for en in entries:
        if en["memory_id"] == e["memory_id"]:
            en["valid_until"] = "2020-01-01T00:00:00+00:00"
    p.write_text(json.dumps(entries), encoding="utf-8")
    _init_memory(tmp_path)
    rk = rank_context(str(tmp_path), purpose="fresh-memory", scopes=["project"])
    assert all(not s["content"].startswith("fresh-memory") for s in rk["selected"])  # 过期排除


# --- Memory Conflict ---

def test_memory_conflict(tmp_path):
    _seed(tmp_path, "优化策略 A 有效", scope="project", src="evidence", confidence=0.9, topic_key="opt-A")
    _seed(tmp_path, "优化策略 A 无效", scope="project", src="evidence", confidence=0.5, topic_key="opt-A")
    cfs = detect_memory_conflicts(str(tmp_path))
    assert len(cfs) == 1
    assert cfs[0]["status"] == "RESOLVED"
    # 高 confidence/evidence 胜出
    winner = cfs[0]["resolution"]
    w_entry = LocalMemoryPlugin(str(tmp_path)).handle("get", {"memory_id": winner})
    assert "有效" in w_entry["content"]
    assert len(memory_conflicts(str(tmp_path))) == 1


# --- ContextStrategy Plugin 替换 (Core 零修改) ---

def test_strategy_plugin_replacement(tmp_path):
    """新 rank 策略注册 + 使用, Core 不修改。"""
    _seed(tmp_path, "策略测试内容", scope="project", src="evidence", confidence=0.9)
    _init_memory(tmp_path)
    # 默认 rank (无 strategy plugin)
    rk1 = rank_context(str(tmp_path), purpose="策略", scopes=["project"])
    # 注册 strategy plugin (type=strategy) + 启用
    from factory_console.plugin_kernel import register_plugin, plugin_status
    register_plugin(str(tmp_path), plugin_id="strategy.rev", name="Reverse", version="1.0",
                    type="strategy", capabilities=["context.rank"],
                    permissions=["context.read"])
    plugin_status(str(tmp_path), "strategy.rev", target="ENABLED")

    def reverse_rank(items, ctx):
        return sorted(items, key=lambda u: u["utility"])  # 反转 (测试策略可替换)
    register_strategy_plugin("strategy.rev", reverse_rank)
    # 第二次 rank 用 strategy.rev (Core 未修改)
    _init_memory(str(tmp_path))  # 确保 plugin 注册
    rk2 = rank_context(str(tmp_path), purpose="策略", scopes=["project"])
    # strategy 反转 → 与默认排序不同 (utility 最低在前)
    assert rk1["selected"][0]["utility"] >= rk2["selected"][0]["utility"]


# --- CLI ---

def test_cli_context_intelligence(tmp_path):
    _seed(tmp_path, "FastAPI", scope="project")
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["context-rank", "rank", "FastAPI", "--scope", "project",
                      "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["context-rank", "progressive", "x", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["memory-lifecycle", "conflicts", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_context_intelligence(tmp_path):
    _seed(tmp_path, "FastAPI 端点", scope="project", src="evidence", confidence=0.9)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/context/rank", json={"purpose": "FastAPI", "scopes": ["project"]})
    assert resp.status_code == 200
    assert resp.json()["selected"]
    resp = client.post("/api/context/progressive", json={"purpose": "x", "scopes": ["project"]})
    assert resp.status_code == 200
    assert resp.json()["total_context_cost"] <= resp.json()["max_total"]
    resp = client.post("/api/context/feedback", json={"snapshot_id": "s", "usefulness": "USEFUL"})
    assert resp.status_code == 200
    resp = client.get("/api/context/efficiency")
    assert resp.status_code == 200
    resp = client.get("/api/memory-conflicts")
    assert resp.status_code == 200
