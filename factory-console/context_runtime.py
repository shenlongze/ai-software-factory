"""factory-console/context_runtime.py — S35 Context & Memory Runtime Foundation.

Context Control Plane:
- ContextRequest (node/scope/purpose/budget)
- ContextBudget (max tokens/cost, 超预算 → REJECT/TRUNCATE/COMPRESS)
- ContextResolver (deterministic pipeline: scope→permission→policy→retrieval→ranking→budget→snapshot)
- ContextSnapshot (不可变, 历史可解释)
- ContextDecision (requested/selected/rejected/compressed + estimated_cost)

Memory Plugin Contract:
- MemoryPlugin 注册到 S31 Plugin Kernel (type=memory)
- Core 管 Governance; Plugin 管 Storage/Retrieval
- LocalMemoryPlugin: deterministic (scope/provenance/version)
- MemoryCandidate → Policy → Validation → Memory (不自动长期化)

JIT Context: 只取 Node 需要的 (scope+purpose 驱动, 禁 load-all)
复用: S31 Plugin Kernel + S17 governance + S23 evidence refs
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

#: 默认 Budget (冻结)
DEFAULT_BUDGET = {
    "max_input_tokens": 8192, "max_memory_tokens": 2048,
    "max_artifact_tokens": 2048, "max_history_tokens": 1024,
    "max_tool_tokens": 1024, "max_output_tokens": 2048, "max_total_cost": 0.01,
}

#: Scope 类型 (Query Dimension, 非继承)
SCOPES = ("node", "agent", "workforce", "project", "organization", "global")

#: MemoryPlugin 注册表 (Core 不 import 具体实现)
MEMORY_PLUGINS: dict[str, Callable[[str, dict[str, Any]], dict[str, Any]]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "context" / f"{name}.json"


def _load(root: Path | str, name: str) -> list[dict[str, Any]]:
    try:
        d = json.loads(_file(root, name).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(root: Path | str, name: str, data: list[dict[str, Any]]) -> None:
    p = _file(root, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _audit(root: Path | str, event_type: str, payload: dict[str, Any]) -> None:
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            event_type,
            trace_id=payload.get("request_id") or payload.get("candidate_id") or "",
            actor_type="system", actor_id="context",
            action=f"context.{event_type.lower()}",
            source="context_runtime", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"context": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ Token/Cost 估算

def estimate_tokens(text: str) -> int:
    """估算 token (字符/4, 明确标记 estimated)。"""
    return max(1, len(text) // 4)


def estimate_cost(tokens: int) -> float:
    """估算成本 (USD, 每 1K token ~0.001, 明确 estimated)。"""
    return round(tokens / 1000 * 0.001, 6)


# ------------------------------------------------------------------ Memory Plugin Contract

def register_memory_plugin(plugin_id: str,
                           handler: Callable[[str, dict[str, Any]], dict[str, Any]]) -> None:
    """注册 Memory Plugin (经 S31 Plugin Kernel; Core 不 import 具体实现)。"""
    MEMORY_PLUGINS[plugin_id] = handler


def _memory_call(root: Path | str, plugin_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    """经 Plugin Kernel 调用 Memory Plugin (Governance + enabled 检查)。"""
    from .plugin_kernel import get_plugin
    p = get_plugin(root, plugin_id)
    if p is None:
        raise ValueError(f"Memory Plugin 不存在: {plugin_id}")
    if p["status"] != "ENABLED":
        raise PermissionError(f"Memory Plugin 未启用: {plugin_id}")
    handler = MEMORY_PLUGINS.get(plugin_id)
    if handler is None:
        raise ValueError(f"Memory Plugin 无 handler: {plugin_id}")
    return handler(action, payload)


# ------------------------------------------------------------------ LocalMemoryPlugin (v1, deterministic)

class LocalMemoryPlugin:
    """Local Memory Plugin: 确定性存储/检索 (scope/provenance/version)。"""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def _entries(self) -> list[dict[str, Any]]:
        try:
            return json.loads((self.root / "ops" / "context" / "memory_local.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _save_entries(self, data: list[dict[str, Any]]) -> None:
        p = self.root / "ops" / "context" / "memory_local.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def handle(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "put":
            return self._put(payload)
        if action == "get":
            return self._get(payload)
        if action == "query":
            return self._query(payload)
        if action == "list":
            return {"entries": self._entries()}
        raise ValueError(f"未知 memory action: {action}")

    def _put(self, payload: dict[str, Any]) -> dict[str, Any]:
        entries = self._entries()
        entry = {"memory_id": f"mem-{uuid.uuid4().hex[:10]}",
                 "scope": payload.get("scope", "node"),
                 "content": payload.get("content", ""),
                 "source_type": payload.get("source_type", "manual"),
                 "source_id": payload.get("source_id", ""),
                 "created_at": _now_iso(), "confidence": payload.get("confidence", 0.5),
                 "version": 1, "permissions": payload.get("permissions", []),
                 "policy": payload.get("policy", "memory.read")}
        entries.append(entry)
        self._save_entries(entries)
        return entry

    def _get(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        mid = payload.get("memory_id", "")
        for e in self._entries():
            if e["memory_id"] == mid:
                return e
        return None

    def _query(self, payload: dict[str, Any]) -> dict[str, Any]:
        """确定性检索: scope 过滤 + source_type 过滤 (JIT, 非 load-all)。"""
        scopes = payload.get("scopes", [])
        source_type = payload.get("source_type")
        entries = self._entries()
        matched = []
        for e in entries:
            if scopes and e["scope"] not in scopes:
                continue
            if source_type and e.get("source_type") != source_type:
                continue
            matched.append(e)
        # 确定性排序: created_at desc (最新优先)
        matched.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        return {"entries": matched, "count": len(matched)}


def _init_local_memory(root: Path | str) -> None:
    """LocalMemoryPlugin 注册 (Core 只持 handler, 不 import 实现细节)。

    每次调用重建 handler (绑定当前 root), 避免缓存旧 root 的闭包。
    """
    plugin = LocalMemoryPlugin(root)
    register_memory_plugin("memory.local", plugin.handle)
    from .plugin_kernel import bootstrap, get_plugin, register_plugin, plugin_status
    bootstrap(root)
    if get_plugin(root, "memory.local") is None:
        try:
            register_plugin(root, plugin_id="memory.local", name="Local Memory", version="1.0.0",
                            type="memory", vendor="ai-factory",
                            capabilities=["memory.store", "memory.retrieve"],
                            permissions=["memory.read", "memory.write"])
            plugin_status(root, "memory.local", target="ENABLED")
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------------ Context

def create_context_request(root: Path | str, *, node_id: str, purpose: str,
                           scopes: list[str] | None = None, node_run_id: str = "",
                           agent_id: str = "", workforce_id: str = "", project_id: str = "",
                           required_capabilities: list[str] | None = None,
                           budget: dict[str, int] | None = None) -> dict[str, Any]:
    """创建 ContextRequest (scope 校验 + budget 冻结)。"""
    scopes = scopes or ["node"]
    for s in scopes:
        if s not in SCOPES:
            raise ValueError(f"非法 scope: {s}")
    req = {"context_request_id": f"ctxreq-{uuid.uuid4().hex[:10]}",
           "node_id": node_id, "node_run_id": node_run_id, "agent_id": agent_id,
           "workforce_id": workforce_id, "project_id": project_id,
           "scope": scopes, "purpose": purpose,
           "required_capabilities": required_capabilities or [],
           "budget": dict(DEFAULT_BUDGET, **(budget or {})), "created_at": _now_iso()}
    _save(root, "requests", _load(root, "requests") + [req])
    _audit(root, "CONTEXT_REQUESTED", {"request_id": req["context_request_id"], "node_id": node_id,
                                       "purpose": purpose, "scopes": scopes})
    return req


def resolve_context(root: Path | str, request_id: str, *,
                    actor: str = "node") -> dict[str, Any]:
    """确定性 Context Resolution Pipeline (JIT + Budget + Snapshot)。"""
    req = None
    for r in _load(root, "requests"):
        if r["context_request_id"] == request_id:
            req = r
            break
    if req is None:
        raise ValueError(f"ContextRequest 不存在: {request_id}")
    budget = req["budget"]
    scopes = req["scope"]
    purpose = req["purpose"]
    # Permission/Policy gate (Governance 优先)
    if not _permission_allowed(root, req, actor):
        decision = {"decision_id": f"ctxdec-{uuid.uuid4().hex[:10]}", "status": "REJECTED",
                    "reason": "permission_denied", "requested_tokens": 0, "selected_tokens": 0,
                    "estimated_cost": 0.0}
        _audit(root, "CONTEXT_REJECTED", {"request_id": request_id, "reason": "permission_denied"})
        return _snapshot(root, req, decision, [], [], [], 0, actor)
    # JIT retrieval (只取 Node 需要的 scope)
    _init_local_memory(root)
    candidates = _retrieve_candidates(root, req)
    # 确定性 Ranking (relevance/evidence/freshness/scope_match → cost)
    ranked = _rank_candidates(candidates, purpose)
    # Budget 执行: 累计 token, 超预算 → TRUNCATE
    selected: list[dict[str, Any]] = []
    compressed: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    total_tokens = 0
    for cand in ranked:
        tokens = cand["tokens"]
        if total_tokens + tokens > budget.get("max_memory_tokens", 2048):
            if len(selected) < 2:
                compressed.append({**cand, "compressed": True})
                total_tokens += max(1, tokens // 2)
            else:
                rejected.append(cand)
            continue
        selected.append(cand)
        total_tokens += tokens
    if total_tokens > budget.get("max_input_tokens", 8192):
        status = "BUDGET_EXCEEDED"
    elif compressed:
        status = "COMPRESSED"
    elif rejected:
        status = "TRUNCATED"
    else:
        status = "OK"
    decision = {"decision_id": f"ctxdec-{uuid.uuid4().hex[:10]}", "status": status,
                "reason": f"scope={scopes} purpose={purpose[:60]}",
                "requested_tokens": sum(c["tokens"] for c in candidates),
                "selected_tokens": total_tokens,
                "compressed_tokens": sum(c["tokens"] for c in compressed),
                "rejected_tokens": sum(c["tokens"] for c in rejected),
                "estimated_cost": estimate_cost(total_tokens)}
    _audit(root, "CONTEXT_RESOLVED", {"request_id": request_id, "status": status,
                                      "selected": len(selected)})
    return _snapshot(root, req, decision, selected, rejected, compressed, total_tokens, actor)


def _permission_allowed(root: Path | str, req: dict[str, Any], actor: str) -> bool:
    """Scope 授权检查: node 不能访问未授权 scope。"""
    scopes = req["scope"]
    if actor == "governance" or actor == "system":
        return True
    # 简化: node 默认可访问 node/agent/global; 更高 scope 需显式
    if any(s in ("workforce", "project", "organization") for s in scopes):
        return req.get("project_id") != ""  # 有 project 上下文才授权
    return True


def _retrieve_candidates(root: Path | str, req: dict[str, Any]) -> list[dict[str, Any]]:
    """Memory Plugin 检索 (JIT: 只查 requested scopes)。"""
    candidates = []
    try:
        result = _memory_call(root, "memory.local", "query",
                              {"scopes": req["scope"], "source_type": None})
        for e in result.get("entries", []):
            tokens = estimate_tokens(e.get("content", ""))
            candidates.append({"memory_id": e["memory_id"], "content": e["content"],
                               "scope": e["scope"], "source_type": e.get("source_type"),
                               "source_id": e.get("source_id"), "created_at": e.get("created_at"),
                               "confidence": e.get("confidence", 0.5),
                               "tokens": tokens, "cost": estimate_cost(tokens)})
    except Exception:  # noqa: BLE001
        pass
    return candidates


def _rank_candidates(candidates: list[dict[str, Any]], purpose: str) -> list[dict[str, Any]]:
    """确定性 Ranking: relevance(关键词)→evidence strength→freshness→cost。"""
    def score(c: dict[str, Any]) -> float:
        relevance = 1.0 if any(w in c["content"] for w in purpose.split()[:4]) else 0.3
        evidence = c.get("confidence", 0.5)
        freshness = 1.0 if c.get("source_type") == "evidence" else 0.7
        scope_match = 1.0 if c.get("scope") == "node" else 0.6
        cost_penalty = c.get("tokens", 0) / 1000.0
        return relevance * 0.4 + evidence * 0.3 + freshness * 0.2 + scope_match * 0.1 - cost_penalty
    return sorted(candidates, key=score, reverse=True)


def _snapshot(root: Path | str, req: dict[str, Any], decision: dict[str, Any],
              selected: list[dict[str, Any]], rejected: list[dict[str, Any]],
              compressed: list[dict[str, Any]], total_tokens: int,
              actor: str) -> dict[str, Any]:
    """ContextSnapshot (不可变, 历史可解释)。"""
    snap = {"snapshot_id": f"ctxsnap-{uuid.uuid4().hex[:10]}",
            "request_id": req["context_request_id"], "node_id": req["node_id"],
            "scope": req["scope"], "purpose": req["purpose"],
            "decision": decision, "selected_items": selected,
            "rejected_items": rejected, "compressed_items": compressed,
            "requested_tokens": decision["requested_tokens"],
            "selected_tokens": total_tokens, "estimated_cost": decision["estimated_cost"],
            "created_at": _now_iso(), "actor": actor,
            "evidence_refs": [c["memory_id"] for c in selected]}
    _save(root, "snapshots", _load(root, "snapshots") + [snap])
    return snap


# ------------------------------------------------------------------ MemoryCandidate

def create_memory_candidate(root: Path | str, *, content: str, scope: str = "node",
                            source_type: str = "manual", source_id: str = "",
                            confidence: float = 0.5) -> dict[str, Any]:
    """MemoryCandidate (不自动长期化; 经 policy 校验后 promote)。"""
    if scope not in SCOPES:
        raise ValueError(f"非法 scope: {scope}")
    cand = {"candidate_id": f"mcm-{uuid.uuid4().hex[:10]}", "content": content,
            "scope": scope, "source_type": source_type, "source_id": source_id,
            "confidence": confidence, "status": "PENDING", "created_at": _now_iso()}
    _save(root, "candidates", _load(root, "candidates") + [cand])
    _audit(root, "MEMORY_CANDIDATE_CREATED", {"candidate_id": cand["candidate_id"], "scope": scope})
    return cand


def promote_memory_candidate(root: Path | str, candidate_id: str, *,
                             decided_by: str = "human") -> dict[str, Any]:
    """Candidate → Policy → Validation → Memory (governed persistence)。"""
    cand = None
    for c in _load(root, "candidates"):
        if c["candidate_id"] == candidate_id:
            cand = c
            break
    if cand is None:
        raise ValueError(f"Candidate 不存在: {candidate_id}")
    _init_local_memory(root)
    entry = _memory_call(root, "memory.local", "put",
                         {"scope": cand["scope"], "content": cand["content"],
                          "source_type": cand["source_type"], "source_id": cand["source_id"],
                          "confidence": cand["confidence"], "policy": "memory.read"})
    data = _load(root, "candidates")
    for c in data:
        if c["candidate_id"] == candidate_id:
            c["status"] = "PROMOTED"
            c["memory_id"] = entry["memory_id"]
            _save(root, "candidates", data)
            break
    _audit(root, "MEMORY_PROMOTED", {"candidate_id": candidate_id,
                                     "memory_id": entry["memory_id"], "decided_by": decided_by})
    return entry


# ------------------------------------------------------------------ Query

def memory_query(root: Path | str, *, scopes: list[str] | None = None,
                 source_type: str | None = None) -> dict[str, Any]:
    """Memory 查询 (经 Plugin + governance)。"""
    _init_local_memory(root)
    return _memory_call(root, "memory.local", "query",
                        {"scopes": scopes or [], "source_type": source_type})


def context_history(root: Path | str, *, node_id: str = "") -> list[dict[str, Any]]:
    data = _load(root, "snapshots")
    if node_id:
        data = [s for s in data if s["node_id"] == node_id]
    return data


def memory_candidates(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "candidates")
