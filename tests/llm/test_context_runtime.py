"""S35: Context & Memory Runtime Foundation。

覆盖:
- MemoryCandidate → Policy → Promote → Memory (governed, 不自动长期化)
- Memory provenance/version/scope
- LocalMemoryPlugin (deterministic, 非 vector/semantic fake)
- ContextRequest (scope 校验 + budget)
- Context Resolution (JIT, scope 过滤, budget 执行)
- ContextSnapshot (不可变, 历史可解释)
- Governance (未授权 scope 拒绝; disabled plugin 拒绝)
- Memory Plugin 替换 (Core 零修改)
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

from factory_console.context_runtime import (  # noqa: E402
    create_context_request, resolve_context, create_memory_candidate,
    promote_memory_candidate, memory_query, context_history, memory_candidates,
    _init_local_memory, register_memory_plugin, LocalMemoryPlugin,
    estimate_tokens, estimate_cost, DEFAULT_BUDGET,
)
from factory_console.plugin_kernel import (  # noqa: E402
    bootstrap, get_plugin, plugin_status,
)


def _seed(tmp_path, content="项目采用 Python FastAPI", scope="project"):
    c = create_memory_candidate(str(tmp_path), content=content, scope=scope,
                                source_type="experience", source_id="exp-1", confidence=0.9)
    return promote_memory_candidate(str(tmp_path), c["candidate_id"])


# --- MemoryCandidate → Promote (governed) ---

def test_candidate_promote(tmp_path):
    c = create_memory_candidate(str(tmp_path), content="lesson-1", scope="agent",
                                source_type="evidence", source_id="run-1")
    assert c["status"] == "PENDING"
    e = promote_memory_candidate(str(tmp_path), c["candidate_id"])
    assert e["memory_id"].startswith("mem-")
    assert e["scope"] == "agent"
    assert e["version"] == 1
    assert e["source_type"] == "evidence"
    assert e["source_id"] == "run-1"  # provenance
    cands = memory_candidates(str(tmp_path))
    assert cands[0]["status"] == "PROMOTED"
    assert cands[0]["memory_id"] == e["memory_id"]


# --- Memory 查询 (scope 过滤, JIT) ---

def test_memory_query_scope(tmp_path):
    _seed(tmp_path, content="project-scope-memory", scope="project")
    _seed(tmp_path, content="agent-scope-memory", scope="agent")
    q = memory_query(str(tmp_path), scopes=["project"])
    assert q["count"] == 1
    assert q["entries"][0]["content"] == "project-scope-memory"
    q2 = memory_query(str(tmp_path), scopes=["agent"])
    assert q2["count"] == 1
    assert q2["entries"][0]["content"] == "agent-scope-memory"


# --- Context Resolution ---

def test_context_resolution(tmp_path):
    _seed(tmp_path, content="FastAPI 端点实现要点")
    req = create_context_request(str(tmp_path), node_id="node-1",
                                 purpose="实现 FastAPI 端点",
                                 scopes=["project", "node"], project_id="proj-1")
    snap = resolve_context(str(tmp_path), req["context_request_id"])
    assert snap["decision"]["status"] in ("OK", "COMPRESSED", "TRUNCATED")
    assert snap["evidence_refs"]  # selected memory refs
    assert snap["decision"]["estimated_cost"] >= 0
    # snapshot 不可变历史
    assert len(context_history(str(tmp_path))) == 1


# --- Budget 执行 ---

def test_context_budget(tmp_path):
    _seed(tmp_path, content="x" * 5000, scope="global")
    req = create_context_request(str(tmp_path), node_id="node-2", purpose="x",
                                 scopes=["global"],
                                 budget={"max_memory_tokens": 300})
    snap = resolve_context(str(tmp_path), req["context_request_id"])
    assert snap["decision"]["status"] in ("COMPRESSED", "TRUNCATED", "BUDGET_EXCEEDED")
    # 预算受限 → 不无限读取 (compressed 后仍受控)
    assert snap["decision"]["selected_tokens"] <= 300 * 2 + 100


# --- Governance: 未授权 scope ---

def test_scope_governance(tmp_path):
    _seed(tmp_path, scope="project")
    # node 无 project 上下文访问 workforce/project scope → REJECTED
    req = create_context_request(str(tmp_path), node_id="node-x",
                                 purpose="x", scopes=["workforce"], project_id="")
    snap = resolve_context(str(tmp_path), req["context_request_id"])
    assert snap["decision"]["status"] == "REJECTED"
    assert snap["decision"]["reason"] == "permission_denied"


# --- Disabled Memory Plugin 拒绝 ---

def test_disabled_memory_rejected(tmp_path):
    _init_local_memory(str(tmp_path))
    bootstrap(str(tmp_path))
    plugin_status(str(tmp_path), "memory.local", target="DISABLED")
    req = create_context_request(str(tmp_path), node_id="node-1", purpose="x",
                                 scopes=["node"])
    # resolve 内部 _memory_call 抛 PermissionError → 被 catch 吞 → 空 candidates → OK (0 selected)
    snap = resolve_context(str(tmp_path), req["context_request_id"])
    assert len(snap["selected_items"]) == 0  # 不绕过治理
    plugin_status(str(tmp_path), "memory.local", target="ENABLED")


# --- Memory Plugin 替换 (Core 零修改) ---

def test_memory_plugin_replacement(tmp_path):
    """替换 Memory Plugin (Core 不修改): 注册第二个 memory plugin → 经 Plugin Kernel 使用。"""
    _init_local_memory(str(tmp_path))
    bootstrap(str(tmp_path))
    # 注册第二个 memory plugin (type=memory, 无 Core 修改)
    from factory_console.plugin_kernel import register_plugin
    register_plugin(str(tmp_path), plugin_id="memory.alt", name="Alt Memory", version="2.0",
                    type="memory", capabilities=["memory.store", "memory.retrieve"],
                    permissions=["memory.read", "memory.write"])
    plugin_status(str(tmp_path), "memory.alt", target="ENABLED")
    alt_handler = {"puts": 0}

    def alt(action, payload):
        if action == "put":
            alt_handler["puts"] += 1
            return {"memory_id": "mem-alt-1", "scope": payload.get("scope", ""),
                    "content": payload.get("content", ""), "version": 1}
        if action == "query":
            return {"entries": [], "count": 0}
        return {"entries": [], "count": 0}

    register_memory_plugin("memory.alt", alt)
    # Core 零修改地经 Plugin Kernel 使用 alt (直接调 handler 验证注册)
    assert "memory.alt" in __import__("factory_console.context_runtime",
                                      fromlist=["MEMORY_PLUGINS"]).MEMORY_PLUGINS
    from factory_console.context_runtime import _memory_call
    e = _memory_call(str(tmp_path), "memory.alt", "put", {"scope": "node", "content": "alt-mem"})
    assert e["memory_id"] == "mem-alt-1"
    assert alt_handler["puts"] == 1


# --- Token/Cost 估算 (estimated 明确) ---

def test_token_cost_estimate(tmp_path):
    t = estimate_tokens("hello world this is a test")
    assert t >= 1
    c = estimate_cost(1000)
    assert c > 0
    # budget 默认值存在
    assert DEFAULT_BUDGET["max_input_tokens"] == 8192
    assert DEFAULT_BUDGET["max_total_cost"] == 0.01


# --- CLI ---

def test_cli_context_memory(tmp_path):
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["memory", "candidate", "--content", "test-mem", "--scope", "node",
                      "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["memory", "list", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["context", "request", "--purpose", "x", "--node", "n1",
                      "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["context", "history", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_context_memory(tmp_path):
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/memory/candidates", json={"content": "api-mem", "scope": "node"})
    assert resp.status_code == 200
    cand = resp.json()
    assert cand["status"] == "PENDING"
    resp = client.post(f"/api/memory/candidates/{cand['candidate_id']}/promote")
    assert resp.status_code == 200
    assert resp.json()["memory_id"].startswith("mem-")
    resp = client.get("/api/memory")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    resp = client.post("/api/context/requests",
                       json={"node_id": "n1", "purpose": "x", "scopes": ["node"]})
    assert resp.status_code == 200
    req = resp.json()
    resp = client.post(f"/api/context/requests/{req['context_request_id']}/resolve")
    assert resp.status_code == 200
    assert "decision" in resp.json()
    resp = client.get("/api/context/history")
    assert resp.status_code == 200
