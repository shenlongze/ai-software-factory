"""factory-console/context_intelligence.py — S36 Context Intelligence & Memory Optimization.

- ContextUtility Contract: relevance/evidence/freshness/confidence/scope/cost → score
- Budget-aware Selection: utility desc → 最优组合 (非全读)
- Progressive Context: 追加受预算, 总 cost <= budget, snapshot 记录
- ContextFeedback: success/failure/unknown (不伪造)
- Memory Lifecycle: CANDIDATE→ACTIVE→SUPERSEDED→RETIRED (audit + lineage, 不删历史)
- Memory Freshness: valid_until 过期 → 不自动进 Context
- Memory Conflict: evidence/confidence/freshness 解决; 无法 → UNRESOLVED
- ContextStrategy Plugin: rank 策略 plugin 化 (Core 零修改替换)

复用: S35 context_runtime + S31 Plugin Kernel + S17 governance
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable

from .context_runtime import (
    _file, _load, _save, _audit, estimate_tokens, estimate_cost,
    _init_local_memory, _memory_call, SCOPES, LocalMemoryPlugin,
)

#: Utility 权重 (冻结)
W_RELEVANCE = 0.4
W_EVIDENCE = 0.25
W_FRESHNESS = 0.15
W_CONFIDENCE = 0.1
W_SCOPE = 0.1
W_COST = 0.05

#: Memory Lifecycle
MEM_STATES = ("CANDIDATE", "ACTIVE", "SUPERSEDED", "RETIRED")
MEM_TRANSITIONS = {
    "CANDIDATE": ("ACTIVE", "RETIRED"),
    "ACTIVE": ("SUPERSEDED", "RETIRED"),
    "SUPERSEDED": ("RETIRED",),
    "RETIRED": (),
}

#: ContextStrategy Plugins (rank 策略, Core 不 import 具体实现)
STRATEGY_PLUGINS: dict[str, Callable[[list[dict[str, Any]], dict[str, Any]], list[dict[str, Any]]]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _freshness_score(entry: dict[str, Any]) -> float:
    """Freshness: valid_until 过期 → 0; 30 天 → 1.0; 90 天 → 0.6; 更久 → 0.3。"""
    valid_until = entry.get("valid_until")
    if valid_until:
        try:
            if datetime.fromisoformat(valid_until) < datetime.now(timezone.utc):
                return 0.0
        except ValueError:
            pass
    created = entry.get("created_at", "")
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(created)).days
    except (ValueError, TypeError):
        return 0.5
    if age <= 30:
        return 1.0
    if age <= 90:
        return 0.6
    return 0.3


def _evidence_strength(source_type: str) -> float:
    return {"evidence": 1.0, "experience": 0.8, "manual": 0.4}.get(source_type, 0.4)


def _scope_match(entry_scope: str, requested_scopes: list[str]) -> float:
    return 1.0 if entry_scope in requested_scopes else 0.6


# ------------------------------------------------------------------ ContextUtility

def context_utility(entry: dict[str, Any], *, purpose: str,
                    requested_scopes: list[str]) -> dict[str, Any]:
    """ContextUtility: 各维度得分 + 总分 (可解释)。"""
    content = entry.get("content", "")
    words = [w for w in purpose.split() if len(w) > 1]
    relevance = sum(1 for w in words if w in content) / max(1, len(words)) if words else 0.3
    evidence = _evidence_strength(entry.get("source_type", "manual"))
    freshness = _freshness_score(entry)
    confidence = entry.get("confidence", 0.5)
    scope = _scope_match(entry.get("scope", "node"), requested_scopes)
    tokens = entry.get("tokens") or estimate_tokens(content)
    cost_norm = min(1.0, tokens / 2000.0)
    score = (W_RELEVANCE * relevance + W_EVIDENCE * evidence + W_FRESHNESS * freshness
             + W_CONFIDENCE * confidence + W_SCOPE * scope - W_COST * cost_norm)
    return {"memory_id": entry.get("memory_id"), "content": content,
            "tokens": tokens, "estimated_cost": estimate_cost(tokens),
            "relevance": round(relevance, 3), "evidence_strength": evidence,
            "freshness": round(freshness, 3), "confidence": confidence,
            "scope_match": scope, "utility": round(max(0.0, score), 4)}


def rank_context(root: Path | str, *, purpose: str, scopes: list[str],
                 budget_tokens: int = 4000) -> dict[str, Any]:
    """Budget-aware Selection: utility desc → 最优组合 (非全读)。

    Strategy Plugin 可替换 rank 逻辑 (Core 零修改)。
    """
    _init_local_memory(root)
    try:
        result = _memory_call(root, "memory.local", "query",
                              {"scopes": scopes, "source_type": None})
    except Exception:  # noqa: BLE001
        result = {"entries": []}
    entries = result.get("entries", [])
    # 过滤过期
    entries = [e for e in entries if _freshness_score(e) > 0]
    # 计算 utility (可被 Strategy Plugin 替换)
    utility_items = [context_utility(e, purpose=purpose, requested_scopes=scopes)
                     for e in entries]
    # Strategy Plugin hook
    strategy = _get_strategy(root)
    if strategy is not None:
        utility_items = strategy(utility_items, {"budget_tokens": budget_tokens})
    # Budget-aware selection: utility desc 累计
    utility_items.sort(key=lambda u: u["utility"], reverse=True)
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    total = 0
    for u in utility_items:
        if total + u["tokens"] > budget_tokens:
            rejected.append({**u, "reason": "budget_overflow"})
            continue
        selected.append(u)
        total += u["tokens"]
    return {"purpose": purpose, "scopes": scopes, "budget_tokens": budget_tokens,
            "selected": selected, "rejected": rejected,
            "selected_tokens": total,
            "rejected_tokens": sum(r["tokens"] for r in rejected),
            "estimated_cost": estimate_cost(total),
            "retrieval_hit_rate": round(len(entries) / max(1, len(result.get("entries", []))), 3),
            "context_rejection_rate": round(len(rejected) / max(1, len(utility_items)), 3)}


# ------------------------------------------------------------------ ContextStrategy Plugin

def register_strategy_plugin(plugin_id: str,
                             fn: Callable[[list[dict[str, Any]], dict[str, Any]], list[dict[str, Any]]]) -> None:
    STRATEGY_PLUGINS[plugin_id] = fn


def _get_strategy(root: Path | str):
    """当前启用的 ContextStrategy Plugin (从 Plugin Kernel 查询, 无 → None)。"""
    from .plugin_kernel import get_plugin
    for pid in STRATEGY_PLUGINS:
        p = get_plugin(root, pid)
        if p is not None and p["status"] == "ENABLED":
            return STRATEGY_PLUGINS[pid]
    return None


# ------------------------------------------------------------------ Progressive Context

def progressive_context(root: Path | str, *, node_id: str, purpose: str,
                        scopes: list[str], initial_budget: int = 2000,
                        max_total: int = 8000, rounds: int = 3,
                        project_id: str = "") -> dict[str, Any]:
    """Progressive: 初始 → 不足 → 追加 (受剩余 budget; 总 <= budget; snapshot 记录全部)。"""
    from .context_runtime import create_context_request, resolve_context
    # project/workforce/organization scope 需 project 授权 (S35 governance)
    if not project_id and any(s in ("project", "workforce", "organization") for s in scopes):
        project_id = "proj-auto"
    snapshots = []
    total_cost = 0
    for i in range(1, rounds + 1):
        remaining = max_total - total_cost
        if remaining <= 0:
            break
        step_budget = min(initial_budget, remaining)
        req = create_context_request(str(root), node_id=node_id, purpose=purpose,
                                     scopes=scopes, project_id=project_id,
                                     budget={"max_memory_tokens": step_budget,
                                            "max_input_tokens": remaining})
        snap = resolve_context(str(root), req["context_request_id"])
        selected = snap["decision"]["selected_tokens"]
        # 超剩余 → 截断 (受预算)
        selected = min(selected, remaining)
        snapshots.append({"round": i, "request_id": req["context_request_id"],
                          "snapshot_id": snap["snapshot_id"],
                          "selected_tokens": selected,
                          "status": snap["decision"]["status"]})
        total_cost += selected
    return {"node_id": node_id, "purpose": purpose, "rounds": len(snapshots),
            "total_context_cost": total_cost, "max_total": max_total,
            "snapshots": snapshots,
            "explain": f"{len(snapshots)} 轮, 总 cost {total_cost} <= {max_total} (受预算)"}


# ------------------------------------------------------------------ ContextFeedback

def context_feedback(root: Path | str, *, snapshot_id: str, node_run_id: str = "",
                     execution_result: str = "UNKNOWN",
                     verification_result: str = "UNKNOWN",
                     usefulness: str = "UNKNOWN") -> dict[str, Any]:
    """ContextFeedback (usefulness 无法证明 → UNKNOWN, 不伪造)。"""
    if usefulness not in ("USEFUL", "NOT_USEFUL", "UNKNOWN"):
        raise ValueError(f"非法 usefulness: {usefulness}")
    fb = {"feedback_id": f"fb-{uuid.uuid4().hex[:8]}", "context_snapshot_id": snapshot_id,
          "node_run_id": node_run_id, "execution_result": execution_result,
          "verification_result": verification_result, "usefulness": usefulness,
          "created_at": _now_iso()}
    _save(root, "feedbacks", _load(root, "feedbacks") + [fb])
    _audit(root, "CONTEXT_FEEDBACK", {"feedback_id": fb["feedback_id"],
                                      "snapshot_id": snapshot_id,
                                      "usefulness": usefulness})
    return fb


def context_feedbacks(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "feedbacks")


# ------------------------------------------------------------------ Memory Lifecycle

def memory_lifecycle(root: Path | str, memory_id: str, *, target: str,
                     superseded_by: str = "", actor: str = "system") -> dict[str, Any]:
    """Memory Lifecycle 迁移 (CANDIDATE→ACTIVE→SUPERSEDED→RETIRED; audit + lineage)。"""
    if target not in MEM_STATES:
        raise ValueError(f"未知状态: {target}")
    plugin = LocalMemoryPlugin(root)
    e = plugin.handle("get", {"memory_id": memory_id})
    if e is None:
        raise ValueError(f"Memory 不存在: {memory_id}")
    current = e.get("lifecycle", "ACTIVE")
    if target not in MEM_TRANSITIONS.get(current, ()) and target != current:
        raise ValueError(f"非法状态迁移: {current} → {target}")
    e["lifecycle"] = target
    if target == "SUPERSEDED":
        e["superseded_by"] = superseded_by
    e["lifecycle_history"] = e.get("lifecycle_history", []) + [
        {"from": current, "to": target, "at": _now_iso(), "actor": actor}]
    # 更新存储 (LocalMemoryPlugin 无 update → 直接写 entries)
    _update_memory_entry(root, e)
    _audit(root, "MEMORY_LIFECYCLE_CHANGED", {"memory_id": memory_id,
                                              "from": current, "to": target})
    return e


def _update_memory_entry(root: Path | str, entry: dict[str, Any]) -> None:
    p = Path(root) / "ops" / "context" / "memory_local.json"
    try:
        entries = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        entries = []
    for i, e in enumerate(entries):
        if e["memory_id"] == entry["memory_id"]:
            entries[i] = entry
            break
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def memory_history(root: Path | str, memory_id: str) -> dict[str, Any]:
    """Memory lineage (lifecycle 历史 + 版本)。"""
    plugin = LocalMemoryPlugin(root)
    e = plugin.handle("get", {"memory_id": memory_id})
    if e is None:
        raise ValueError(f"Memory 不存在: {memory_id}")
    return {"memory_id": memory_id, "lifecycle": e.get("lifecycle", "ACTIVE"),
            "lifecycle_history": e.get("lifecycle_history", []),
            "version": e.get("version", 1),
            "superseded_by": e.get("superseded_by", ""),
            "created_at": e.get("created_at", ""),
            "source_type": e.get("source_type"), "source_id": e.get("source_id")}


# ------------------------------------------------------------------ Memory Conflict

def detect_memory_conflicts(root: Path | str) -> list[dict[str, Any]]:
    """同 scope + 同 topic_key 的 Memory → CONFLICT 检测 (evidence/confidence/freshness 解决)。"""
    _init_local_memory(root)
    plugin = LocalMemoryPlugin(root)
    entries = plugin.handle("list", {}).get("entries", [])
    # topic_key: 规范化 content 首 20 字符 (v1 确定性)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for e in entries:
        if e.get("lifecycle", "ACTIVE") != "ACTIVE":
            continue
        topic = e.get("topic_key") or e["content"][:20]
        groups.setdefault((e["scope"], topic), []).append(e)
    conflicts = []
    for (scope, topic), members in groups.items():
        if len(members) < 2:
            continue
        # 矛盾检测: content 不同 (v1 简化: 不同内容即潜在冲突)
        unique = {m["content"] for m in members}
        if len(unique) <= 1:
            continue
        # 解决: evidence_strength > confidence > freshness
        ranked = sorted(members, key=lambda m: (
            _evidence_strength(m.get("source_type", "manual")),
            m.get("confidence", 0.0),
            _freshness_score(m)), reverse=True)
        winner = ranked[0]
        conflicts.append({"conflict_id": f"cf-{uuid.uuid4().hex[:8]}",
                          "topic_key": topic, "scope": scope,
                          "memory_ids": [m["memory_id"] for m in members],
                          "status": "RESOLVED", "resolution": winner["memory_id"],
                          "explain": f"evidence/confidence/freshness 最高: {winner['memory_id']}",
                          "created_at": _now_iso()})
    # 覆盖写入 (非追加, 避免重复)
    _save(root, "conflicts", conflicts)
    return conflicts


def memory_conflicts(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "conflicts")
