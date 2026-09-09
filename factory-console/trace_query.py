"""factory-console/trace_query.py — factory trace 只读全链查询 (S1 第 5 刀 M2b)。

一条命令回答: 会话从哪来 → 理解 → PRD → Plan → 树 → 各叶执行 → 产物 → 审计。
只读; 不建新存储; 不改 Domain 语义; 缺环如实标 MISSING。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from factory_console import golden_path as gp
from factory_console import product_understanding as pu
from factory_console import task_decomposition as td


def build_trace(root: str | Path, conversation_id: str) -> dict[str, Any]:
    """构造一条 conversation 的全链 trace (真实事实; 缺环 MISSING)。"""
    root_s = str(root)
    out: dict[str, Any] = {"conversation_id": conversation_id}

    # 1. 会话 / 理解
    conv = pu.get_conversation(root_s, conversation_id)
    if conv is None:
        out["conversation"] = "MISSING"
        return out
    snap = pu.understanding_snapshot(root_s, conversation_id)
    out["conversation"] = {
        "title": conv.get("title", ""),
        "understanding_version": snap.get("version"),
        "fact_count": len(snap.get("facts") or []),
        "facts": [
            {"type": f.get("type"), "content": str(f.get("content"))[:80],
             "status": f.get("status")}
            for f in (snap.get("facts") or [])[:20]
        ],
        "messages": len(conv.get("messages") or []),
    }
    if not out["conversation"]["messages"]:
        # 消息存 conversation.messages (含角色); 兼容空时回退 understanding.messages
        u = conv.get("understanding") or {}
        out["conversation"]["messages"] = len(
            (u.get("messages") if isinstance(u, dict) else None) or [])

    # 2. PRD
    st = gp.path_status(root_s, conversation_id)
    prd_rows = []
    for p in st.get("prds", []):
        full = _get_prd(root_s, conversation_id, p["id"])
        content = (full or {}).get("content", {}) if full else {}
        prd_rows.append({
            "id": p["id"], "version": p["version"], "status": p["status"],
            "source_understanding_version":
                p.get("source_product_understanding_version"),
            "functional_requirements":
                (content.get("functional_requirements", []) if isinstance(content, dict)
                 else []),
        })
    out["prds"] = prd_rows or "MISSING"

    # 3. Plan + 树
    plan_rows = []
    for p in st.get("plans", []):
        plan_rows.append({
            "id": p["id"], "status": p["status"],
            "leaf_count": _plan_leaf_count(root_s, p["id"]),
            "tree": td.tree_summary(td.load_task_tree(root_s, p["id"])),
        })
    out["plans"] = plan_rows or "MISSING"

    # 4. 各叶 NodeRun + artifact (从 approved plan 的 workflow/production run 找)
    out["node_runs"] = _collect_node_runs(root_s, conversation_id, st)
    out["audit"] = _collect_audit(root_s, conversation_id)
    return out


def render_trace(trace: dict[str, Any]) -> str:
    """trace dict → 终端可读文本。"""
    L: list[str] = []
    L.append(f"Trace: {trace['conversation_id']}")
    conv = trace.get("conversation")
    if conv == "MISSING" or not isinstance(conv, dict):
        L.append("  conversation: MISSING")
        return "\n".join(L)
    L.append(f"  title: {conv.get('title')}")
    L.append(f"  understanding: v{conv.get('understanding_version')} "
             f"· {conv.get('fact_count')} facts · {conv.get('messages')} messages")
    for f in conv.get("facts", [])[:10]:
        L.append(f"    [{f['type']}/{f.get('status')}] {f['content']}")

    prds = trace.get("prds")
    if prds == "MISSING":
        L.append("  PRD: MISSING")
    else:
        for p in prds:
            L.append(f"  PRD {p['id']} v{p['version']} {p['status']} "
                     f"(src_uv={p.get('source_understanding_version')})")
            for fr in p.get("functional_requirements", [])[:6]:
                L.append(f"    - {str(fr)[:80]}")

    plans = trace.get("plans")
    if plans == "MISSING":
        L.append("  Plan: MISSING")
    else:
        for p in plans:
            t = p.get("tree") or {}
            L.append(f"  Plan {p['id']} {p['status']} · {p.get('leaf_count')} leaves"
                     f" · degraded={t.get('degraded')}")

    runs = trace.get("node_runs")
    if isinstance(runs, list):
        if not runs:
            L.append("  NodeRuns: (无执行)")
        for nr in runs:
            L.append(f"  Run {nr.get('node_id')} → {nr.get('state')}"
                     f" · executor={nr.get('executor') or '-'}"
                     f" · started={nr.get('started_at') or '-'}"
                     f" · artifact={nr.get('artifact_id') or '-'}"
                     f" · verification={nr.get('verification') or '-'}"
                     + (f" · error={nr.get('error')[:100]}"
                        if nr.get("error") else ""))
            if nr.get("artifact"):
                a = nr["artifact"]
                L.append(f"    artifact {a.get('artifact_id')}: "
                         f"{a.get('kind') or a.get('type') or ''} "
                         f"{str(a.get('payload', ''))[:120]}")

    audit = trace.get("audit")
    if isinstance(audit, list):
        if not audit:
            L.append("  audit: (无事件)")
        for e in audit:
            L.append(f"  audit {e.get('event_type')} "
                     f"trace={e.get('trace_id') or '-'} actor={e.get('actor_id') or '-'}")
    return "\n".join(L)


# ------------------------------------------------------------------ helpers

def _get_prd(root: str, conversation_id: str, prd_id: str) -> dict[str, Any] | None:
    try:
        from factory_console import application_formalization as fmt
        return fmt.get_prd(root, conversation_id, prd_id)
    except Exception:  # noqa: BLE001
        return None


def _plan_leaf_count(root: str, plan_id: str) -> int:
    tree = td.load_task_tree(root, plan_id)
    return len(td.tree_leaves(tree)) if tree else 0


def _collect_node_runs(root: str, conversation_id: str,
                       st: dict[str, Any]) -> list[dict[str, Any]] | str:
    """从 audit / production_runs 聚合本会话各叶 NodeRun (只读, 缺环 MISSING)。"""
    runs: list[dict[str, Any]] = []
    seen: set[str] = set()
    # production_run 记录 (project_id=conversation_id)
    try:
        from factory_console import production_run as pr
        all_pruns = pr.list_production_runs(root)
        for pru in all_pruns or []:
            pid = pru.get("project_id") or pru.get("input", {}).get("project_id", "")
            if str(pid) != str(conversation_id):
                continue
            detail = pr.get_production_run(root, pru["run_id"]) or {}
            for nr in detail.get("node_runs", []):
                nid = nr.get("node_id")
                if nid in seen:
                    continue
                seen.add(nid)
                row = _node_run_row(root, nid, nr)
                if row:
                    runs.append(row)
    except Exception:  # noqa: BLE001 — 查询失败 → 如实 MISSING
        pass
    return runs


def _node_run_row(root: str, node_id: str, nr: dict[str, Any]
                  ) -> dict[str, Any] | None:
    from factory_console import node_runtime as nrt
    row: dict[str, Any] = {
        "node_id": node_id,
        "state": nr.get("state"),
        "run_id": nr.get("run_id"),
        "artifact_id": nr.get("artifact_id"),
        "reason": nr.get("reason"),
    }
    if not nr.get("run_id"):
        row["error"] = nr.get("reason")
        return row
    full = nrt.get_node_run(root, nr["run_id"]) or {}
    row["executor"] = full.get("executor") or (full.get("input") or {}).get(
        "executor_name")
    row["started_at"] = full.get("started_at")
    row["completed_at"] = full.get("completed_at")
    row["verification"] = (full.get("verification") or {}).get(
        "status") if isinstance(full.get("verification"), dict) else None
    row["error"] = full.get("failure_reason")
    if full.get("artifact_id"):
        row["artifact"] = _artifact_row(root, full["artifact_id"])
    return row


def _artifact_row(root: str, artifact_id: str) -> dict[str, Any] | None:
    try:
        from factory_console import artifact_lifecycle as al
        art = al.get_artifact(root, artifact_id) or {}
        payload = art.get("payload")
        return {
            "artifact_id": artifact_id,
            "kind": art.get("kind") or art.get("type"),
            "payload": json.dumps(payload, ensure_ascii=False)[:200]
            if payload else "",
        }
    except Exception:  # noqa: BLE001
        return None


def _collect_audit(root: str, conversation_id: str) -> list[dict[str, Any]] | str:
    """audit_events.json 中 trace_id=conversation_id 的认知/执行事件 (只读)。"""
    try:
        p = Path(root) / "audit" / "audit_events.json"
        if not p.exists():
            return []
        data = json.loads(p.read_text(encoding="utf-8"))
        evs = data if isinstance(data, list) else data.get("events", [])
        out = []
        for e in evs:
            tid = e.get("trace_id")
            if str(tid) == str(conversation_id):
                out.append({
                    "event_type": e.get("event_type") or e.get("type"),
                    "trace_id": tid,
                    "actor_id": e.get("actor_id"),
                    "metadata": e.get("metadata") or {},
                })
        return out
    except Exception:  # noqa: BLE001
        return "MISSING"
