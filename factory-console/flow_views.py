"""factory-console/flow_views.py — Flow Views 视图层 v0 (S1 第 9 刀)。

单会话 flow + 项目聚合 + 图型全集。只读现有文件, 不落第二份 Truth。

- 视图模型 (build_conv_flow / build_project_view): 从 conversations/task_trees/
  project_agile/runs/audit 派生 (缺环 MISSING, 诚实)。
- 渲染器 (render_md/todo/mermaid_*/echarts_*/html): 纯函数, 同一模型。
- 诚实铁律: 缺失 → 灰块"未实现"; 无验证 → UNKNOWN; 甘特只用真时间戳;
  degraded/截断 warning 必须上板; 宁可灰, 不可假绿。

设计: /Users/agentdev/ai-company-os-planning/2026-09-10-dashboard-system-design.md
"""
from __future__ import annotations

import json
from typing import Any, Callable

from factory_console import project_agile as _pa
from factory_console import product_understanding as _pu
from factory_console import task_decomposition as _td

#: conv flow 9 阶段 (有序; 前 6 认知/计划, 后 3 生产/治理)
CONV_STAGES = [
    ("idea", "Idea/需求想法"),
    ("analysis", "需求分析"),
    ("architecture", "架构选择"),
    ("task_tree", "任务树"),
    ("sprint", "Sprint"),
    ("execution", "执行"),
    ("verification", "验证"),
    ("delivery", "交付"),
    ("audit", "审计"),
]
#: NodeRun 状态白名单 (以 node_runtime 代码常量为准)
NODE_RUN_STATES = ("PENDING", "RUNNING", "VERIFYING", "COMPLETED", "FAILED",
                   "REPAIRING", "WAITING_FOR_USER", "BLOCKED")
#: Sprint 状态机 (以 project_agile 代码常量为准)
SPRINT_STATES = ("planned", "active", "review", "closed")

_GREY = "未实现"
_UNKNOWN = "UNKNOWN"


# ------------------------------------------------------------------ 视图模型 (只读派生)


def _conv_doc(root: str, cid: str) -> dict[str, Any] | None:
    return _pu._load_conv(root, cid)


def _stage_state(cid: str, doc: dict[str, Any] | None,
                 prds: list[dict], plans: list[dict],
                 tree: dict[str, Any] | None,
                 active_sp: dict[str, Any] | None,
                 runs: list[dict], audit_n: int) -> dict[str, Any]:
    """派生 9 阶段状态 (真实事实; 缺环 → 灰块/UNKNOWN)。"""
    # idea/analysis: 理解 facts
    facts = []
    if doc:
        u = doc.get("understanding") or {}
        facts = list((u.get("facts") or {}).values())
    st = {
        "idea": "有" if any(f.get("type") == "IDEA" for f in facts)
        else _GREY,
        "analysis": "有" if any(f.get("type") in
                                ("REQUIREMENT", "CONSTRAINT", "DECISION")
                                for f in facts) else _GREY,
        "architecture": _GREY,  # 架构选择域未建 (记录: 无此环节 Truth)
        "task_tree": ("有" if tree else _GREY),
        "sprint": ("active" if active_sp else
                   ("有(历史)" if plans else _GREY)),
        "execution": ("有" if runs else _GREY),
        "verification": ("PASS" if any(
            (r.get("verification") or {}).get("status") == "PASS"
            for r in runs if isinstance(r.get("verification"), dict))
            else ("FAIL" if any(
                (r.get("verification") or {}).get("status") == "FAIL"
                for r in runs if isinstance(r.get("verification"), dict))
                else _UNKNOWN)),
        "delivery": ("有产物" if any(r.get("artifact_id") for r in runs)
                     else _GREY),
        "audit": (f"{audit_n} 事件" if audit_n else _GREY),
    }
    # degraded/截断 warning 上板
    if tree and tree.get("degraded"):
        st["task_tree"] = "有 ⚠️degraded"
    if tree and tree.get("warnings"):
        st["task_tree"] += f" ({len(tree['warnings'])} warning)"
    return st


def build_conv_flow(root: str, conversation_id: str) -> dict[str, Any]:
    """conv flow 视图模型 (9 阶段 + 树摘要 + sprint 统计 + 每叶 node_run + 审计)。"""
    doc = _conv_doc(root, conversation_id)
    if doc is None:
        return {"scope": "conversation", "id": conversation_id,
                "exists": False}
    # PRD/Plan (经 golden_path.path_status)
    from factory_console import golden_path as _gp
    st_path = _gp.path_status(root, conversation_id)
    prds = st_path.get("prds", [])
    plans = st_path.get("plans", [])
    # 树: 取最新 plan 的树
    tree = None
    tree_plan_id = ""
    for p in reversed(plans):
        t = _td.load_task_tree(root, p["id"])
        if t:
            tree = t
            tree_plan_id = p["id"]
            break
    # project/sprint 上下文
    pid = _pa.conversation_project_id(root, conversation_id)
    proj_info = None
    active_sp = None
    if pid:
        proj_info = _pa.get_project_by_conversation(root, conversation_id)
        active_sp = _pa.get_active_sprint(root, pid)
    # node_runs (从 audit 关联 + production_run 反查; 简化: trace_query 复用)
    from factory_console.trace_query import build_trace
    tr = build_trace(root, conversation_id)
    runs = tr.get("node_runs") if isinstance(tr.get("node_runs"), list) else []
    audit_list = tr.get("audit") if isinstance(tr.get("audit"), list) else []
    # 阶段状态
    stages = _stage_state(conversation_id, doc, prds, plans, tree, active_sp,
                          runs, len(audit_list))
    # 树摘要
    tree_summary = None
    tree_full: list[dict[str, Any]] = []
    if tree:
        tree_summary = _td.tree_summary(tree)
        tree_full = (tree.get("nodes") or []) if isinstance(tree, dict) else []
    return {
        "scope": "conversation",
        "id": conversation_id,
        "exists": True,
        "title": (doc or {}).get("title", ""),
        "stages": stages,
        "stage_list": [{"key": k, "label": lb, "state": stages.get(k)}
                       for k, lb in CONV_STAGES],
        "tree": tree_summary,
        "tree_plan_id": tree_plan_id,
        # 渲染器用完整 nodes (mindmap 等需父子链; 只读引用, 非第二份 Truth)
        "_tree_full": tree_full,
        "prds": prds,
        "plans": plans,
        "project": proj_info,
        "sprint": ({"sprint_id": active_sp.get("sprint_id"),
                    "title": active_sp.get("title"),
                    "status": active_sp.get("status"),
                    "stats": active_sp.get("stats")} if active_sp else None),
        "node_runs": runs,
        "audit_count": len(audit_list),
        "honest": {"missing": [k for k, s in stages.items()
                               if s in (_GREY, _UNKNOWN)]},
    }


def build_project_view(root: str, project_id: str) -> dict[str, Any]:
    """project 聚合视图模型 (backlog 全量 + Sprint 卡 + 每 PRD 迷你流)。"""
    # 存在性: 项目实体缺失 → exists=False (诚实, 不造空视图)
    try:
        from factory_console.project_os import get_project
        proj = get_project(root, project_id)
    except Exception:  # noqa: BLE001 — ValueError NOT_FOUND / IO
        return {"scope": "project", "id": project_id, "exists": False}
    title = str(proj.get("title") or "") if isinstance(proj, dict) else ""
    data = _pa._load(root, project_id)
    # backlog 全量 (pending / in_sprint / closed 三态)
    backlog_all = data.get("backlog", [])
    by_status: dict[str, int] = {}
    for b in backlog_all:
        s = b.get("status") or "pending"
        by_status[s] = by_status.get(s, 0) + 1
    # 每 backlog 项反查 conversation (迷你流: PRD→Plan→执行→close/回退)
    backlog_flow = []
    for b in backlog_all:
        cid = b.get("conversation_id", "")
        mini = {"prd_id": b.get("prd_id"), "status": b.get("status"),
                "conversation_id": cid}
        if cid:
            conv = _pu._load_conv(root, cid)
            if conv:
                mini["conv_title"] = conv.get("title", "")
            # PRD→Plan→执行 迷你流 (经 conversation 反查 trace; 缺失→灰)
            mini["prd_count"] = 0
            mini["plan_count"] = 0
            mini["exec_completed"] = 0
            mini["exec_total"] = 0
            try:
                from factory_console import golden_path as _gp
                stp = _gp.path_status(root, cid)
                mini["prd_count"] = stp.get("prd_count", 0)
                plans = stp.get("plans") or []
                mini["plan_count"] = len(plans)
                approved = [p for p in plans
                            if p.get("status") == "approved"]
                if approved:
                    from factory_console import task_decomposition as _td2
                    tree = _td2.load_task_tree(root, approved[-1]["id"])
                    if tree:
                        mini["leaf_count"] = _td2.tree_summary(tree).get(
                            "leaf_count", 0)
                from factory_console.trace_query import build_trace as _bt
                tr = _bt(root, cid)
                runs = (tr.get("node_runs")
                        if isinstance(tr.get("node_runs"), list) else [])
                mini["exec_total"] = len(runs)
                mini["exec_completed"] = sum(
                    1 for r in runs if r.get("state") == "COMPLETED")
            except Exception:  # noqa: BLE001 — 反查失败 → 迷你流灰块 (诚实)
                pass
        backlog_flow.append(mini)
    # sprint 卡 (含 per_prd_stats / prd_plan_map)
    sprint_cards = []
    for sp in data.get("sprints", []):
        card = {k: sp.get(k) for k in
                ("sprint_id", "title", "status", "prd_ids", "plan_ids",
                 "stats", "per_prd_stats", "prd_plan_map", "created_at",
                 "started_at", "closed_at")}
        sprint_cards.append(card)
    active = next((s for s in sprint_cards
                   if s.get("status") in ("active", "review")), None)
    return {
        "scope": "project",
        "id": project_id,
        "exists": True,
        "title": title or project_id,
        "backlog": backlog_all,
        "backlog_count": len(backlog_all),
        "backlog_by_status": by_status,
        "backlog_flow": backlog_flow,
        "sprints": sprint_cards,
        "active_sprint": active,
    }


# ------------------------------------------------------------------ 渲染器注册


def _stage_row(key: str, label: str, state: str) -> str:
    """md 阶段行; 灰块/UNKNOWN → 灰提示。"""
    if state in (_GREY, _UNKNOWN):
        return f"| {label} | {state} |"
    return f"| {label} | {state} |"


# 占位: 渲染器在文件后部逐一定义并汇入 _RENDERERS
_RENDERERS: dict[str, Callable[[dict[str, Any]], str]] = {}


# ------------------------------------------------------------------ md 渲染


def _render_md(view: dict[str, Any]) -> str:
    if not view.get("exists"):
        return f"# {view.get('scope')} {view.get('id')}\n\n(不存在)"
    L = [f"# {view.get('scope')} flow — {view.get('id')}",
         f"> {view.get('title') or ''}"]
    if view.get("scope") == "conversation":
        L += ["", "## 阶段"]
        L += ["| 阶段 | 状态 |", "|---|---|"]
        for key, label, state in [(it["key"], it["label"], it["state"])
                                  for it in view.get("stage_list", [])]:
            L.append(_stage_row(key, label, state))
        t = view.get("tree")
        if t:
            L += ["", f"## 任务树 {view.get('tree_plan_id')}",
                  f"- depth={t.get('depth')} 叶={t.get('leaf_count')} "
                  f"degraded={t.get('degraded')}"]
            for w in (t.get("warnings") or []):
                L.append(f"  - ⚠️ {w}")
        sp = view.get("sprint")
        if sp:
            stt = sp.get("stats") or {}
            L += ["", f"## Sprint {sp.get('title')} [{sp.get('status')}]",
                  f"- 叶: COMPLETED {stt.get('completed',0)} / "
                  f"FAILED {stt.get('failed',0)} / "
                  f"BLOCKED {stt.get('blocked',0)} / "
                  f"total {stt.get('total_leaves',0)}"]
        if view.get("node_runs"):
            L += ["", "## 执行叶"]
            for r in view["node_runs"]:
                L.append(f"- {r.get('node_id')} → {r.get('state')}"
                         f" executor={r.get('executor') or '-'}"
                         f" artifact={r.get('artifact_id') or '-'}")
        else:
            L += ["", "## 执行叶", f"- {_GREY}"]
        L.append(f"\n审计事件: {view.get('audit_count')} 条")
        miss = view.get("honest", {}).get("missing", [])
        if miss:
            L.append(f"\n> 诚实提示: 灰块/UNKNOWN 阶段 = {', '.join(miss)}")
    else:  # project
        by_status = view.get("backlog_by_status") or {}
        L += ["", "## Backlog",
              f"- pending {by_status.get('pending', 0)} / "
              f"in_sprint {by_status.get('in_sprint', 0)} / "
              f"closed {by_status.get('closed', 0)}"]
        for b in view.get("backlog_flow", []):
            state = b.get("status") or "?"
            title = b.get("conv_title") or b.get("prd_id") or "?"
            mini = ""
            if b.get("conversation_id") and (
                    b.get("plan_count") or b.get("exec_total")):
                mini = (f" · Plan {b.get('plan_count')} · 执行 "
                        f"{b.get('exec_completed')}/{b.get('exec_total')}")
            elif b.get("conversation_id"):
                mini = f" · {_GREY} (未走 Golden Path)"
            L.append(f"  - {b.get('prd_id')} ({state}) {title}{mini}")
        if not view.get("backlog"):
            L.append(f"  - {_GREY} (backlog 空)")
        L += ["", "## Sprints"]
        for sp in view.get("sprints", []):
            mark = "◀ active" if sp.get("status") in ("active", "review") else ""
            stt = sp.get("stats") or {}
            per = sp.get("per_prd_stats") or {}
            L.append(f"- {sp.get('title')} [{sp.get('status')}] {mark}"
                     f" PRD={len(sp.get('prd_ids') or [])}"
                     f" 叶 {stt.get('completed', 0)}/{stt.get('total_leaves', 0)}")
            for prd_id, s in list(per.items())[:8]:
                L.append(f"  - {prd_id}: COMPLETED {s.get('completed', 0)} / "
                         f"FAILED {s.get('failed', 0)} / "
                         f"BLOCKED {s.get('blocked', 0)}")
        if not view.get("sprints"):
            L.append(f"  - {_GREY} (无 Sprint)")
    return "\n".join(L)


def _render_todo(view: dict[str, Any]) -> str:
    """叶清单: - [x] ⇔ COMPLETED。"""
    if not view.get("exists"):
        return "(不存在)"
    L: list[str] = []
    runs_by_node = {r.get("node_id"): r for r in view.get("node_runs", [])}
    for leaf in (view.get("tree") or {}).get("leaves", []):
        r = runs_by_node.get(leaf.get("id"))
        done = bool(r and r.get("state") == "COMPLETED")
        L.append(f"- [{'x' if done else ' '}] {leaf.get('title')}")
    if not L:
        L.append(f"- [ ] {_GREY} (无叶)")
    return "\n".join(L)


# ------------------------------------------------------------------ mermaid 渲染


def _esc_md(t: str) -> str:
    return str(t).replace('"', "'").replace("\n", " ")[:80]


def _render_mindmap(view: dict[str, Any]) -> str:
    """递归树 mindmap (深度不限)。"""
    tree = view.get("tree")
    if not tree:
        return "mindmap\n  root((无树))"
    # 从磁盘重读 nodes (tree_summary 只有叶) — 用 view 树 plan 重载
    nodes = _tree_full_nodes(view)
    if not nodes:
        return "mindmap\n  root((无节点))"
    by_id = {n["id"]: n for n in nodes}
    roots = [n for n in nodes if not n.get("parent_id")]
    L = ["mindmap"]

    def _walk(nid: str, indent: int) -> None:
        n = by_id.get(nid)
        if n is None:  # 孤儿父引用 → 防御 (不崩)
            return
        pad = "  " * indent
        L.append(f"{pad}{_esc_md(n.get('title') or n.get('id'))}")
        for kid in nodes:
            if kid.get("parent_id") == nid:
                _walk(kid["id"], indent + 1)

    for r in roots:
        _walk(r["id"], 1)
    return "\n".join(L)


def _tree_full_nodes(view: dict[str, Any]) -> list[dict[str, Any]]:
    """从视图树重载完整 nodes (视图模型只存 summary; 渲染需 nodes)。"""
    plan_id = view.get("tree_plan_id", "")
    if not plan_id:
        return []
    # view 无 root 信息 — 用 goal 近似; 渲染器由 build_* 预置 tree_full
    full = view.get("_tree_full")
    return full if full else []


def _ts_gantt(ts: Any) -> str:
    """时间戳 → mermaid gantt 兼容 (YYYY-MM-DDTHH:mm:ss, 剥微秒/时区)。"""
    s = str(ts or "")
    s = s.split(".")[0]  # 剥微秒
    # 剥时区后缀 (+00:00 / Z)
    for sep in ("+", "Z"):
        idx = s.find(sep)
        if idx > 0:
            s = s[:idx]
    return s


def _render_gantt(view: dict[str, Any]) -> str:
    """Sprint×叶 甘特 — 只用真实 started_at/completed_at。"""
    L = ["gantt", "    title 执行甘特 (真实时间戳)",
         "    dateFormat YYYY-MM-DDTHH:mm:ss"]
    any_real = False
    for r in view.get("node_runs", []):
        s, e = r.get("started_at"), r.get("completed_at")
        if s and e:
            any_real = True
            L.append(f"    {_esc_md(r.get('node_id') or '?')} "
                     f":{_ts_gantt(s)}, {_ts_gantt(e)}")
    if not any_real:
        L.append("    section 无真实时间戳数据")
        L.append(f"    {_GREY} : 0, 0")
    return "\n".join(L)


def _render_flow(view: dict[str, Any]) -> str:
    """阶段链 (泳道 = subgraph by domain)。灰块节点明示。"""
    L = ["flowchart LR"]
    # 阶段链
    stage_list = [(it["key"], it["label"], it["state"])
                  for it in view.get("stage_list", [])]
    if not stage_list:
        L.append(f"    X[{_GREY} (单会话阶段链 — project 视图请用 md/sankey)]")
        return "\n".join(L)
    prev = None
    for key, label, state in stage_list:
        nid = f"S_{key}"
        style = ""
        if state in (_GREY, _UNKNOWN):
            style = ":::grey"
        L.append(f"    {nid}[{_esc_md(label)}: {_esc_md(state)}]{style}")
        if prev:
            L.append(f"    {prev} --> {nid}")
        prev = nid
    L.append("    classDef grey fill:#ccc,stroke:#999,color:#333")
    return "\n".join(L)


def _render_dataflow(view: dict[str, Any]) -> str:
    """实体↔叶 边=write/read/migrate (来自叶 data_entities)。"""
    L = ["flowchart LR"]
    any_edge = False
    for leaf in (view.get("tree") or {}).get("leaves", []):
        ln = f"L{abs(hash(leaf.get('id','')) ) % 100000}"
        L.append(f"    {ln}[{_esc_md(leaf.get('title') or '?')}]")
        for ent in leaf.get("data_entities", []):
            en = "E" + _esc_md(ent.get("entity", "")).replace(" ", "_")
            ops = ",".join(ent.get("ops") or [])
            L.append(f"    {en}[{_esc_md(ent.get('entity'))}]")
            L.append(f"    {ln} -- {ops} --> {en}")
            any_edge = True
    if not any_edge:
        L.append(f"    X[{_GREY} (无 data_entities 边)]")
    return "\n".join(L)


def _render_sequence(view: dict[str, Any]) -> str:
    """用户↔系统阶段交互 (9 阶段 + 审计事件数)。"""
    L = ["sequenceDiagram",
         "    participant U as 用户",
         "    participant S as AI Factory OS"]
    stage_list = [(it["key"], it["label"], it["state"])
                  for it in view.get("stage_list", [])]
    if not stage_list:
        L.append(f"    S-->>U: {_GREY} (单会话阶段交互 — project 视图请用 md)")
        return "\n".join(L)
    for key, label, state in stage_list:
        if state in (_GREY, _UNKNOWN):
            L.append(f"    S-->>U: {_esc_md(label)} [{state}]")
        else:
            L.append(f"    U->>S: {_esc_md(label)}")
            L.append(f"    S-->>U: {_esc_md(state)}")
    return "\n".join(L)


def _render_state(view: dict[str, Any]) -> str:
    """Sprint + NodeRun 状态机 (以代码常量为准)。"""
    L = ["stateDiagram-v2",
         "    [*] --> planned", "    planned --> active",
         "    active --> review", "    review --> closed",
         "    closed --> planned : 未完成回 backlog",
         "    [*] --> PENDING", "    PENDING --> RUNNING",
         "    RUNNING --> VERIFYING", "    VERIFYING --> COMPLETED",
         "    RUNNING --> FAILED", "    VERIFYING --> FAILED",
         "    RUNNING --> BLOCKED"]
    return "\n".join(L)


def _render_dag(view: dict[str, Any]) -> str:
    """叶 depends_on 依赖 DAG。"""
    L = ["flowchart LR"]
    any_edge = False
    leaves = (view.get("tree") or {}).get("leaves", [])
    by_id = {leaf["id"]: leaf for leaf in leaves}
    for leaf in leaves:
        ln = f"L{abs(hash(leaf.get('id',''))) % 100000}"
        L.append(f"    {ln}[{_esc_md(leaf.get('title') or '?')}]")
        for dep in leaf.get("depends_on", []):
            if dep in by_id:
                dn = f"L{abs(hash(dep)) % 100000}"
                L.append(f"    {dn} --> {ln}")
                any_edge = True
    if not any_edge:
        L.append(f"    X[{_GREY} (无依赖边)]")
    return "\n".join(L)


# ------------------------------------------------------------------ echarts 渲染


def _render_echarts_graph(view: dict[str, Any]) -> str:
    """graph nodes/edges JSON option (与 view model 同源)。"""
    nodes = []
    edges = []
    tree = view.get("tree") or {}
    for leaf in tree.get("leaves", []):
        nodes.append({"id": leaf.get("id"), "name": leaf.get("title"),
                      "category": leaf.get("change_type", "task")})
        for dep in leaf.get("depends_on", []):
            edges.append({"source": dep, "target": leaf.get("id")})
    opt = {"series": [{"type": "graph", "layout": "force",
                       "data": nodes, "links": edges}]}
    return json.dumps(opt, ensure_ascii=False, indent=2)


def _render_echarts_sankey(view: dict[str, Any]) -> str:
    """PRD→Sprint→叶完成量 sankey。"""
    data, links = [], []
    if view.get("scope") == "project":
        for sp in view.get("sprints", []):
            stt = sp.get("stats") or {}
            sp_node = f"Sprint {sp.get('title','')[:12]}"
            data.append({"name": sp_node})
            # project 级: PRD → sprint 聚合 (经 backlog)
            for prd_id in sp.get("prd_ids", [])[:10]:
                data.append({"name": prd_id[:12]})
                links.append({"source": prd_id[:12], "target": sp_node,
                              "value": 1})
            links.append({"source": sp_node, "target": "完成",
                          "value": stt.get("completed", 0)})
        data.append({"name": "完成"})
    else:
        data = [{"name": "PRD"}, {"name": "Sprint"}, {"name": "完成"}]
        links = [{"source": "PRD", "target": "Sprint", "value": 1},
                 {"source": "Sprint", "target": "完成",
                  "value": (view.get("sprint") or {}).get(
                      "stats", {}).get("completed", 0)}]
    opt = {"series": [{"type": "sankey", "data": data, "links": links}]}
    return json.dumps(opt, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ html 渲染


def _render_html(view: dict[str, Any]) -> str:
    """自包含 HTML (内嵌 md 表格 + ECharts/Mermaid CDN; 离线降级表格)。"""
    md = _render_md(view)
    esc = md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    scope = view.get("scope", "flow")
    vid = str(view.get("id", ""))
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{scope} flow — {vid}</title>
<style>body{{font-family:sans-serif;margin:24px;color:#222}}
pre{{background:#f6f8fa;padding:16px;border-radius:8px;overflow:auto}}
.offline-note{{color:#888;font-size:12px}}</style>
</head><body>
<h1>{scope} flow — {vid}</h1>
<!-- CDN 依赖: ECharts https://cdn.jsdelivr.net/npm/echarts@5
     Mermaid https://cdn.jsdelivr.net/npm/mermaid@10
     离线降级: 下列表格为纯文本可读; 图型需联网加载 CDN -->
<pre>{esc}</pre>
<div class="offline-note">注: 本 HTML 内嵌纯文本表格 (离线可读);
ECharts/Mermaid 图型需联网加载 CDN (见 HTML 注释)。</div>
</body></html>"""


# ------------------------------------------------------------------ 主入口

_RENDERERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "md": _render_md,
    "todo": _render_todo,
    "mermaid:mindmap": _render_mindmap,
    "mermaid:gantt": _render_gantt,
    "mermaid:flow": _render_flow,
    "mermaid:dataflow": _render_dataflow,
    "mermaid:sequence": _render_sequence,
    "mermaid:state": _render_state,
    "mermaid:dag": _render_dag,
    "echarts:graph": _render_echarts_graph,
    "echarts:sankey": _render_echarts_sankey,
    "html": _render_html,
}

ALL_FORMATS: tuple[str, ...] = tuple(_RENDERERS.keys())


def render_view(view: dict[str, Any], fmt: str = "md") -> str:
    """按格式渲染视图模型。未知格式 → md (回退)。"""
    fn = _RENDERERS.get(fmt) or _RENDERERS["md"]
    return fn(view)


def build_flow(scope: str, flow_id: str, fmt: str = "md",
               root: str | None = None) -> dict[str, Any]:
    """统一构建 (CLI/API 同源); root 缺省 → 默认数据目录。"""
    return build_flow_for(root or _default_root(), scope, flow_id, fmt)


def _default_root() -> str:
    try:
        from factory_console.config import ConfigProvider
        return str(ConfigProvider().get_data_dir())
    except Exception:  # noqa: BLE001
        from pathlib import Path
        return str(Path.home() / ".factory")


def build_flow_for(root: str, scope: str, flow_id: str,
                   fmt: str = "md") -> dict[str, Any]:
    """CLI/API 同源入口: root 显式传入。"""
    if scope == "conversation":
        view = build_conv_flow(root, flow_id)
    elif scope == "project":
        view = build_project_view(root, flow_id)
    else:
        return {"ok": False, "error": f"未知 scope: {scope}",
                "format": fmt, "content": "", "view": {}}
    # 渲染器需要完整树 nodes (mindmap) — 视图模型补 _tree_full
    if view.get("exists") and view.get("scope") == "conversation":
        plan_id = view.get("tree_plan_id", "")
        if plan_id:
            tree = _td.load_task_tree(root, plan_id)
            view["_tree_full"] = (tree or {}).get("nodes", [])
    content = render_view(view, fmt)
    return {"ok": True, "format": fmt, "content": content, "view": view,
            "scope": scope, "id": flow_id}


def flow_route(scope: str, flow_id: str, fmt: str = "md",
               kind: str = "") -> dict[str, Any]:
    """API 路由 (纯函数; 仿 api/audit.py — 失败安全 {"ok": False})。"""
    try:
        if kind and not fmt.startswith(kind):
            fmt = f"{kind}:{fmt}" if ":" not in fmt else fmt
        return build_flow_for(_default_root(), scope, flow_id, fmt)
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return {"ok": False, "error": str(exc), "format": fmt,
                "content": "", "view": {}}


__all__ = [
    "CONV_STAGES", "ALL_FORMATS",
    "build_conv_flow", "build_project_view", "build_flow_for", "flow_route",
    "render_view",
]
