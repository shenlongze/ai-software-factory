"""factory-console/session/board.py — 任务监控面板 (S10-106+).

监控 AI Factory 项目进展:
- render_board: 主线 todolist + 进度条 + 标签（读待办清单）
- render_graph: 任务依赖图（读 plan.json tasks/edges/critical_path）
- render_timeline: 生命线/时序图（读 audit_events 最近事件）

Founder 痛点: 测试中脱离主线, 做多周边, 线没走完, 脑袋记不住 —
主线/周边分清楚 + 进度可见 + 图/生命线可视化。

设计: §5.10 递归进度 · §5.11 多维视图 · §5.7 可视化 · S10-106
边界: rich 可用 → 富文本; 无 rich → 纯文本降级; 数据缺失 → 容错
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

#: 待办清单默认路径（主线任务源）
DEFAULT_BACKLOG = Path(__file__).resolve().parents[2] / "docs" / "sprint10" / "待办清单-已发现未落地.md"

#: 主线分组（M 里程碑 + P0）vs 周边（长期）
MAIN_GROUPS = ("M2", "M3", "M4", "M5", "M6", "M7", "P0")
SIDE_GROUPS = ("长期",)


# ---------------------------------------------------------------- 主线面板

def _parse_backlog(path: Path) -> list[dict[str, Any]]:
    """解析待办清单: 每行任务 {group, id, desc, priority, done, source}。"""
    if not path.is_file():
        return []
    groups: list[dict[str, Any]] = []
    cur_group = ""
    cur_title = ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:  # noqa: BLE001
        return []
    for line in lines:
        m = re.match(r"^## (M\d+|P0|长期)[^—]*—?\s*(.*)$", line.strip())
        if m:
            cur_group = m.group(1)
            cur_title = m.group(2).strip()
            groups.append({"id": cur_group, "title": cur_title, "tasks": [], "group_done": False})
            continue
        # 组级完成注释: "✅ M2 六项全部交付" → 该组全部完成
        if cur_group and line.strip().startswith("> ✅") and re.search(cur_group, line):
            groups[-1]["group_done"] = True
            continue
        if not cur_group or not line.strip().startswith("| "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not re.match(r"^(M\d+-|P0-|L-)", cells[0]):
            continue
        groups[-1]["tasks"].append({
            "id": cells[0],
            "desc": cells[1][:40],
            "done": ("✅" in line) or groups[-1]["group_done"],
            "priority": "P0" if "P0" in cells[0] else ("P1" if "P1" in line else ("P2" if "P2" in line else "")),
        })
    # 组级完成注释在表格后 → 二次处理
    for g in groups:
        if g.get("group_done"):
            for t in g["tasks"]:
                t["done"] = True
    return groups


def render_board(path: Path = DEFAULT_BACKLOG) -> str:
    """主线面板: todolist + 进度条 + 标签。"""
    groups = _parse_backlog(path)
    if not groups:
        return "（未找到待办清单）"
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.progress import Progress, BarColumn, TextColumn
        from rich import box

        buf: list[str] = []

        # 主线进度总览
        main_tasks = [t for g in groups if g["id"] in MAIN_GROUPS for t in g["tasks"]]
        done = sum(1 for t in main_tasks if t["done"])
        total = len(main_tasks)
        pct = (done / total * 100) if total else 0
        buf.append(f"🎯 主线任务: {done}/{total} 完成 ({pct:.0f}%)" + (" ⚠️ 有未完成" if done < total else " ✅"))
        buf.append(f"└─ 进度: [{'█' * (done * 20 // total if total else 0)}{'░' * (20 - (done * 20 // total if total else 0))}]")
        side_count = sum(len(g["tasks"]) for g in groups if g["id"] in SIDE_GROUPS)
        buf.append(f"📌 周边(长期)任务: {side_count} 项（非主线, 不阻塞）")
        buf.append("")

        # 分组表
        for g in groups:
            tag = "主线" if g["id"] in MAIN_GROUPS else "周边"
            g_done = sum(1 for t in g["tasks"] if t["done"])
            g_total = len(g["tasks"])
            status = "✅" if g_done == g_total and g_total else "🚧"
            buf.append(f"{g['id']} [{tag}] {status} {g_done}/{g_total} — {g['title']}")
            for t in g["tasks"]:
                mark = "✅" if t["done"] else "⬜"
                pri = f"[{t['priority']}]" if t["priority"] else ""
                buf.append(f"   {mark} {t['id']} {pri} {t['desc']}")

        # 多源加载（设计文档全部任务 — Founder: 现在不全）
        sprints = _parse_sprints()
        if sprints:
            s_done = sum(1 for s in sprints if s["done"])
            buf.append("")
            buf.append(f"🧪 Sprint 任务 (S10): {s_done}/{len(sprints)} 完成 (验收报告证据)")
            for s in sprints:
                mark = "✅" if s["done"] else "🚧"
                buf.append(f"   {mark} {s['id']} {s['title']}")
        s14 = _parse_s14()
        if s14:
            buf.append("")
            buf.append(f"📚 章节任务 (§1.4): {sum(1 for r in s14 if r['status']=='✅')}/{len(s14)} 完成")
            for r in s14:
                buf.append(f"   {r['status']} {r['title']} — {r['todo'][:30]}")
        return "\n".join(buf)
    except ImportError:  # noqa: BLE001 — 无 rich → 纯文本
        return "\n".join(
            f"[{g['id']}] {sum(1 for t in g['tasks'] if t['done'])}/{len(g['tasks'])} — {g['title']}"
            for g in groups
        )


# ---------------------------------------------------------------- 依赖图

def render_graph(workspace: Path, project_id: str = "") -> str:
    """任务依赖图（读 plan.json tasks/edges/critical_path）。"""
    project_dir = Path(workspace) / "projects" / (project_id or "")
    plan_file = project_dir / "plan.json"
    if not plan_file.is_file():
        return "（未找到 plan.json — 项目未生成计划, 或需指定项目）"
    try:
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # noqa: BLE001
        return "（plan.json 损坏）"
    tasks = {t.get("id", ""): t for t in (plan.get("tasks") or [])}
    edges = plan.get("edges") or []
    critical = set(plan.get("critical_path") or [])

    if not tasks:
        return "（plan.json 无任务）"
    lines = ["🔗 任务依赖图 (CRITICAL=★):", ""]
    # 邻接表: 依赖 → 被依赖者（下游）
    dependents: dict[str, list[str]] = {}
    for e in edges:
        if isinstance(e, dict):
            src, dst = e.get("from", ""), e.get("to", "")
        else:
            src, dst = "", ""
        if src and dst:
            dependents.setdefault(src, []).append(dst)
    # 树形渲染（从无依赖的任务开始）
    seen: set[str] = set()

    def walk(tid: str, prefix: str, is_last: bool) -> None:
        if tid in seen:
            return
        seen.add(tid)
        t = tasks.get(tid, {})
        star = "★" if tid in critical else " "
        lines.append(f"{prefix}{'└─' if is_last else '├─'} {tid} {star} {t.get('name','')[:24]}")
        kids = dependents.get(tid, [])
        for i, k in enumerate(kids):
            walk(k, prefix + ("   " if is_last else "│  "), i == len(kids) - 1)

    roots = [tid for tid in tasks if not any(
        (isinstance(e, dict) and e.get("to") == tid) or (not isinstance(e, dict) and False)
        for e in edges)]
    if not roots:
        roots = list(tasks)[:3]
    for i, r in enumerate(roots[:10]):
        walk(r, "", i == len(roots[:10]) - 1)
    return "\n".join(lines)


# ---------------------------------------------------------------- 生命线

def render_timeline(workspace: Path, limit: int = 15) -> str:
    """生命线/时序图（读 audit_events 最近事件, 按时间线渲染）。"""
    audit_file = Path(workspace) / "audit" / "audit_events.json"
    if not audit_file.is_file():
        return "（未找到 audit_events.json）"
    try:
        data = json.loads(audit_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # noqa: BLE001
        return "（审计文件损坏）"
    events = data.get("events") if isinstance(data, dict) else data
    if not isinstance(events, list) or not events:
        return "（暂无审计事件）"
    events = sorted(events, key=lambda e: str(e.get("timestamp") or ""))[-limit:]
    lines = ["⏱ 生命线 (最近事件, 时间→事件→对象):", ""]
    prev_time = ""
    for e in events:
        ts = str(e.get("timestamp") or "")[11:19]  # HH:MM:SS
        marker = "│" if ts == prev_time else f"◉ {ts}"
        prev_time = ts
        ev = e.get("event_type") or e.get("type") or "?"
        obj = e.get("task_id") or e.get("agent_id") or e.get("project_id") or ""
        lines.append(f"{marker} {ev} {('→ ' + obj) if obj else ''}")
        lines.append("│")
    return "\n".join(lines)


# ---------------------------------------------------------------- 任务链 + 关键节点

def render_chain(workspace: Path, project_id: str = "") -> str:
    """任务链/关键路径链（plan.json critical_path, 关键节点★ + 汇聚点▲）。"""
    project_dir = Path(workspace) / "projects" / (project_id or "")
    plan_file = project_dir / "plan.json"
    if not plan_file.is_file():
        return "（未找到 plan.json — 项目未生成计划, 或需指定项目）"
    try:
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # noqa: BLE001
        return "（plan.json 损坏）"
    tasks = {t.get("id", ""): t for t in (plan.get("tasks") or [])}
    cpath = plan.get("critical_path") or []
    merges = plan.get("merges") or []
    if not cpath:
        return "（plan.json 无关键路径 — 环拒绝/未生成, 诚实不伪造）"
    merge_ids = set()
    for m in merges:
        if isinstance(m, dict):
            merge_ids.add(m.get("task") or "")
        elif isinstance(m, str):
            merge_ids.add(m)
    lines = ["🔗 任务链（关键路径, ★=关键节点 ▲=汇聚点）:", ""]
    for i, tid in enumerate(cpath):
        t = tasks.get(tid, {})
        star = "★" if t.get("critical") else " "
        merge = "▲" if tid in merge_ids else " "
        arrow = " → " if i < len(cpath) - 1 else ""
        est = t.get("est_minutes")
        est_s = f" ({est}min)" if est else ""
        lines.append(f"  {star}{merge} {tid}{est_s} {t.get('name','')[:20]}{arrow}")
    total_est = sum(
        int(tasks.get(tid, {}).get("est_minutes") or 0) for tid in cpath
    )
    lines.append(f"\n  总工期: {total_est}min · 关键节点 {len(cpath)} 个 · 汇聚点 {len(merge_ids)} 个")
    return "\n".join(lines)


def render_report(path: Path = DEFAULT_BACKLOG) -> str:
    """--report: 给 Hermes 的 markdown 进度汇报（主线完成/进行中/未开始+周边+建议）。"""
    groups = _parse_backlog(path)
    if not groups:
        return "（未找到待办清单）"
    main_groups = [g for g in groups if g["id"] in MAIN_GROUPS]
    side_groups = [g for g in groups if g["id"] in SIDE_GROUPS]

    done_groups = [g for g in main_groups if g["tasks"] and all(t["done"] for t in g["tasks"])]
    partial_groups = [g for g in main_groups if g["tasks"] and not all(t["done"] for t in g["tasks"]) and any(t["done"] for t in g["tasks"])]
    todo_groups = [g for g in main_groups if g["tasks"] and not any(t["done"] for t in g["tasks"])]

    lines = ["# AI Factory 进度汇报", ""]
    lines.append("## 主线完成")
    if done_groups:
        for g in done_groups:
            lines.append(f"- **{g['id']}** ✅ ({len(g['tasks'])}/{len(g['tasks'])}) — {g['title']}")
    else:
        lines.append("- （无）")
    lines.append("\n## 主线进行中")
    if partial_groups:
        for g in partial_groups:
            d = sum(1 for t in g["tasks"] if t["done"])
            lines.append(f"- **{g['id']}** 🚧 ({d}/{len(g['tasks'])}) — {g['title']}")
    else:
        lines.append("- （无）")
    lines.append("\n## 主线未开始")
    if todo_groups:
        for g in todo_groups:
            lines.append(f"- **{g['id']}** ⬜ (0/{len(g['tasks'])}) — {g['title']}")
    else:
        lines.append("- （无）")
    side_total = sum(len(g["tasks"]) for g in side_groups)
    lines.append(f"\n## 周边（长期, 非主线）")
    lines.append(f"- {side_total} 项（不阻塞主线）")
    lines.append("\n## 建议下一步")
    if todo_groups:
        lines.append(f"- 推进未开始主线: {', '.join(g['id'] for g in todo_groups)}")
    elif partial_groups:
        lines.append(f"- 收尾进行中主线: {', '.join(g['id'] for g in partial_groups)}")
    else:
        lines.append("- 主线全部完成, 进入下一里程碑")
    return "\n".join(lines)


# ---------------------------------------------------------------- HTML 可视化面板

def render_board_html(path: Path = DEFAULT_BACKLOG) -> str:
    """HTML 可视化面板（进度条/标签/分组卡片, 浏览器自适应）。

    /api/board 返回 HTML 而非 JSON — 浏览器直接看监控面板。
    纯标准库生成（无外部模板依赖）; 数据同 render_board（_parse_backlog）。
    """
    groups = _parse_backlog(path)
    if not groups:
        return "<p>（未找到待办清单）</p>"
    main_tasks = [t for g in groups if g["id"] in MAIN_GROUPS for t in g["tasks"]]
    done = sum(1 for t in main_tasks if t["done"])
    total = len(main_tasks)
    pct = round(done / total * 100) if total else 0
    side_count = sum(len(g["tasks"]) for g in groups if g["id"] in SIDE_GROUPS)

    def bar(pct_done: int, pct_total: int) -> str:
        w = round(pct_done / pct_total * 100) if pct_total else 0
        return (
            f'<div class="bar"><div class="bar-fill" style="width:{w}%"></div>'
            f'<span class="bar-label">{pct_done}/{pct_total}</span></div>'
        )

    cards = []
    for g in groups:
        is_main = g["id"] in MAIN_GROUPS
        g_done = sum(1 for t in g["tasks"] if t["done"])
        g_total = len(g["tasks"])
        cls = "main" if is_main else "side"
        status = "✅" if g_done == g_total and g_total else "🚧"
        tag = f'<span class="tag {"t-main" if is_main else "t-side"}">{"主线" if is_main else "周边"}</span>'
        items = []
        for t in g["tasks"]:
            mark = "✅" if t["done"] else "⬜"
            pri = f'<span class="tag t-{t["priority"].lower() if t["priority"] else "none"}">{t["priority"]}</span>' if t["priority"] else ""
            items.append(f'<li class="{"done" if t["done"] else "todo"}">{mark} {t["id"]} {pri} {t["desc"]}</li>')
        g_done_count = g_done
        g_todo_count = g_total - g_done
        data_attrs = f'data-kind="{"main" if is_main else "side"}" data-status="{"done" if g_done == g_total and g_total else ("partial" if g_done else "todo")}"'
        cards.append(
            f'<div class="card {cls}" {data_attrs}><h2>{g["id"]} {tag} {status} {bar(g_done, g_total)} <span class="title">{g["title"]}</span></h2>'
            f'<ul>{"".join(items)}</ul></div>'
        )

    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="30">
<title>AI Factory 监控面板</title>
<style>
  .nav {{ display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }}
  .nav a {{ background: #1a1d24; border: 1px solid #2a2e37; color: #b0b6bf; border-radius: 6px; padding: 6px 14px; font-size: 13px; text-decoration: none; }}
  .nav a.active {{ background: #1565c0; color: #fff; border-color: #1565c0; }}
  .nav a:hover {{ background: #2a2e37; }}
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 16px; background: #0f1115; color: #e6e6e6; }}
  h1 {{ font-size: 20px; margin: 8px 0 4px; }}
  .summary {{ background: #1a1d24; border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; }}
  .summary p {{ margin: 4px 0; }}
  .bar {{ background: #2a2e37; border-radius: 6px; height: 18px; position: relative; margin: 6px 0; }}
  .bar-fill {{ background: #4caf50; border-radius: 6px; height: 100%; transition: width .4s; }}
  .bar-fill.orange {{ background: #ff9800; }}
  .bar-label {{ position: absolute; right: 6px; top: 1px; font-size: 11px; }}
  .groups {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 12px; }}
  .card {{ background: #1a1d24; border-radius: 10px; padding: 12px 14px; border-left: 4px solid #4caf50; }}
  .card.side {{ border-left-color: #78909c; }}
  .card h2 {{ font-size: 15px; margin: 0 0 8px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }}
  .card h2 .title {{ color: #9aa0a6; font-size: 12px; width: 100%; }}
  ul {{ list-style: none; margin: 0; padding: 0; max-height: 260px; overflow-y: auto; }}
  li {{ font-size: 12px; padding: 3px 0; color: #b0b6bf; }}
  li.done {{ color: #7cb57c; }}
  .tag {{ font-size: 10px; padding: 2px 6px; border-radius: 4px; }}
  .t-main {{ background: #1565c0; }} .t-side {{ background: #546e7a; }}
  .t-p0 {{ background: #c62828; }} .t-p1 {{ background: #e65100; }} .t-p2 {{ background: #616161; }}
  .side-tip {{ color: #78909c; font-size: 12px; margin-top: 12px; }}
  .dist {{ margin: 8px 0; }}
  .dist-bar {{ display: flex; height: 10px; border-radius: 5px; overflow: hidden; }}
  .dist-done {{ background: #4caf50; }} .dist-todo {{ background: #616161; }}
  .dist-legend {{ font-size: 11px; color: #9aa0a6; margin-top: 4px; display: flex; gap: 14px; }}
  .dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 3px; }}
  .d-done {{ background: #4caf50; }} .d-todo {{ background: #616161; }} .d-side {{ background: #78909c; }}
  .filters {{ margin: 10px 0 14px; display: flex; gap: 8px; flex-wrap: wrap; }}
  .f-btn {{ background: #1a1d24; border: 1px solid #2a2e37; color: #b0b6bf; border-radius: 6px; padding: 4px 12px; font-size: 12px; cursor: pointer; }}
  .f-btn.active {{ background: #1565c0; color: #fff; border-color: #1565c0; }}
  .card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.4); transition: .2s; }}
  li:hover {{ color: #fff; }}
</style></head><body>
<div class="nav">
  <a href="/api/board" class="active">📋 主线面板</a>
  <a href="/api/board/graph">🔗 依赖图</a>
  <a href="/api/board/chain">⛓ 任务链</a>
  <a href="/api/board/timeline">⏱ 生命线</a>
  <a href="/api/board?view=report">📄 汇报</a>
</div>
<h1>🎯 AI Factory 任务监控面板</h1>
<div class="summary">
  <p>主线任务: <b>{done}/{total}</b> 完成 ({pct}%) {("⚠️ 有未完成" if done < total else "✅ 全部完成")}</p>
  {bar(done, total)}
  <div class="dist" title="状态分布">
    <div class="dist-bar">
      <div class="dist-done" style="width:{pct}%"></div>
      <div class="dist-todo" style="width:{100 - pct}%"></div>
    </div>
    <div class="dist-legend">
      <span><i class="dot d-done"></i>完成 {done}</span>
      <span><i class="dot d-todo"></i>未完成 {total - done}</span>
      <span><i class="dot d-side"></i>周边 {side_count}</span>
    </div>
  </div>
  <p>周边(长期): {side_count} 项（非主线, 不阻塞）</p>
</div>
<div class="filters">
  <button class="f-btn active" data-filter="all">全部</button>
  <button class="f-btn" data-filter="main">主线</button>
  <button class="f-btn" data-filter="side">周边</button>
  <button class="f-btn" data-filter="done">已完成</button>
  <button class="f-btn" data-filter="todo">未完成</button>
  <button class="f-btn" data-filter="partial">进行中</button>
</div>
<div class="groups">{"".join(cards)}</div>
<p class="side-tip">AI Factory v{_pkg_version_lite()} · 会话 /board 有更多视图（graph/chain/timeline/report）</p>
<script>
document.querySelectorAll('.f-btn').forEach(function(btn){{
  btn.addEventListener('click', function(){{
    document.querySelectorAll('.f-btn').forEach(function(b){{ b.classList.remove('active'); }});
    btn.classList.add('active');
    var f = btn.dataset.filter;
    document.querySelectorAll('.card').forEach(function(card){{
      var show = (f === 'all') ||
        (f === 'main' && card.dataset.kind === 'main') ||
        (f === 'side' && card.dataset.kind === 'side') ||
        (f === 'done' && card.dataset.status === 'done') ||
        (f === 'todo' && card.dataset.status === 'todo') ||
        (f === 'partial' && card.dataset.status === 'partial');
      card.style.display = show ? '' : 'none';
    }});
  }});
}});
</script>
</body></html>"""


def _pkg_version_lite() -> str:
    """轻量读版本（HTML 面板底部显示, 失败 → dev）。"""
    try:
        import tomllib
        p = Path(__file__).resolve().parents[2] / "pyproject.toml"
        return tomllib.loads(p.read_text(encoding="utf-8"))["project"]["version"]
    except Exception:  # noqa: BLE001
        return "dev"


# ---------------------------------------------------------------- HTML 图/链可视化

def render_graph_html(workspace: Path, project_id: str = "") -> str:
    """任务依赖图 HTML 可视化（节点+连线, CRITICAL★ 红色高亮, 纯 CSS/SVG）。"""
    project_dir = Path(workspace) / "projects" / (project_id or "")
    plan_file = project_dir / "plan.json"
    if not plan_file.is_file():
        return "<p>（未找到 plan.json — 项目未生成计划, 或需指定项目）</p>"
    try:
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # noqa: BLE001
        return "<p>（plan.json 损坏）</p>"
    tasks = {t.get("id", ""): t for t in (plan.get("tasks") or [])}
    edges = plan.get("edges") or []
    critical = set(plan.get("critical_path") or [])
    if not tasks:
        return "<p>（plan.json 无任务）</p>"

    def node_html(tid: str, t: dict) -> str:
        is_crit = tid in critical
        crit_cls = "crit" if is_crit else ""
        crit_mark = " ★" if is_crit else ""
        est = t.get("est_minutes")
        est_s = f"<span class='est'>{est}min</span>" if est else ""
        return (f'<div class="node {crit_cls}" title="{t.get("name","")}">'
                f'<div class="nid">{tid}{crit_mark}</div>'
                f'<div class="nname">{t.get("name","")[:16]}</div>{est_s}</div>')

    nodes = "".join(node_html(tid, t) for tid, t in tasks.items())
    # 边列表（用于 CSS 连线提示或箭头文本）
    edge_rows = []
    for e in edges:
        if isinstance(e, dict):
            src, dst = e.get("from", ""), e.get("to", "")
        else:
            continue
        if src and dst:
            edge_rows.append(f"<li>{src} → {dst}</li>")
    edges_html = "".join(edge_rows) if edge_rows else "<li>（无依赖边）</li>"

    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>任务依赖图 — {project_id or "项目"}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 16px; background: #0f1115; color: #e6e6e6; }}
  h1 {{ font-size: 18px; }} .legend {{ color: #9aa0a6; font-size: 12px; margin-bottom: 10px; }}
  .graph {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
  .node {{ background: #1a1d24; border: 2px solid #2a2e37; border-radius: 8px; padding: 8px 12px; min-width: 110px; }}
  .node.crit {{ border-color: #e53935; background: #2a1416; }}
  .nid {{ font-weight: bold; color: #ffb74d; }} .node.crit .nid {{ color: #ff7043; }}
  .nname {{ font-size: 11px; color: #b0b6bf; }} .est {{ font-size: 10px; color: #78909c; }}
  .arrow {{ color: #546e7a; font-size: 20px; }}
  .edges {{ margin-top: 16px; background: #1a1d24; border-radius: 8px; padding: 10px 14px; }}
  .edges ul {{ column-count: 2; font-size: 12px; color: #9aa0a6; }}
</style></head><body>
<h1>🔗 任务依赖图 <span class="legend">(★=CRITICAL 关键路径, 红色边框)</span></h1>
<div class="graph">{nodes}</div>
<div class="edges"><b>依赖边:</b><ul>{edges_html}</ul></div>
</body></html>"""


def render_chain_html(workspace: Path, project_id: str = "") -> str:
    """任务链 HTML 可视化（关键路径横向卡片链 + 箭头, ★关键节点 ▲汇聚点）。"""
    project_dir = Path(workspace) / "projects" / (project_id or "")
    plan_file = project_dir / "plan.json"
    if not plan_file.is_file():
        return "<p>（未找到 plan.json）</p>"
    try:
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # noqa: BLE001
        return "<p>（plan.json 损坏）</p>"
    tasks = {t.get("id", ""): t for t in (plan.get("tasks") or [])}
    cpath = plan.get("critical_path") or []
    if not cpath:
        return "<p>（无关键路径 — 环拒绝/未生成, 诚实不伪造）</p>"
    merges = plan.get("merges") or []
    merge_ids = set()
    for m in merges:
        if isinstance(m, dict):
            merge_ids.add(m.get("task") or "")
        elif isinstance(m, str):
            merge_ids.add(m)

    chain_parts = []
    for i, tid in enumerate(cpath):
        t = tasks.get(tid, {})
        is_merge = tid in merge_ids
        marks = "★" + ("▲" if is_merge else "")
        cls = "crit" if t.get("critical") else ""
        est = t.get("est_minutes")
        est_s = f"<span class='est'>{est}min</span>" if est else ""
        chain_parts.append(
            f'<div class="cnode {cls}"><div class="cid">{marks} {tid}</div>'
            f'<div class="cname">{t.get("name","")[:14]}</div>{est_s}</div>'
        )
        if i < len(cpath) - 1:
            chain_parts.append('<div class="carrow">→</div>')
    total_est = sum(int(tasks.get(tid, {}).get("est_minutes") or 0) for tid in cpath)
    chain = "".join(chain_parts)

    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>任务链 — {project_id or "项目"}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 16px; background: #0f1115; color: #e6e6e6; }}
  h1 {{ font-size: 18px; }} .legend {{ color: #9aa0a6; font-size: 12px; }}
  .chain {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 12px; }}
  .cnode {{ background: #1a1d24; border: 2px solid #e53935; border-radius: 8px; padding: 8px 12px; min-width: 100px; }}
  .cid {{ font-weight: bold; color: #ff7043; }} .cname {{ font-size: 11px; color: #b0b6bf; }}
  .est {{ font-size: 10px; color: #78909c; }} .carrow {{ color: #e53935; font-size: 22px; }}
  .total {{ margin-top: 14px; color: #9aa0a6; font-size: 13px; }}
  @media (max-width: 600px) {{ .chain {{ flex-direction: column; }} .carrow {{ transform: rotate(90deg); }} }}
</style></head><body>
<h1>⛓ 任务链（关键路径）<span class="legend">★=关键节点 ▲=汇聚点</span></h1>
<div class="chain">{chain}</div>
<div class="total">总工期: {total_est}min · 关键节点 {len(cpath)} 个 · 汇聚点 {len(merge_ids)} 个</div>
</body></html>"""


# ---------------------------------------------------------------- 主线控制（从仪表盘到控制系统）

def mark_backlog_item(path: Path, item_id: str, done: bool = True) -> str:
    """标记待办清单项完成/未完成（更新行内 ✅, board 进度实时准确）。

    行内无 ✅ → 加 " ✅" 前缀; 有 ✅ 且 done=False → 去掉。失败安全。
    """
    if not path.is_file():
        return "（未找到待办清单）"
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:  # noqa: BLE001
        return "（待办清单读取失败）"
    target = str(item_id).strip()
    found = False
    for i, line in enumerate(lines):
        if line.startswith("|") and target in line and re.match(r"^\|\s*" + re.escape(target) + r"\s*\|", line):
            found = True
            if done and "✅" not in line:
                # 在 id 后插入 ✅（保持表格结构: | id | ✅ desc | ...）
                # 找第一个 | 后的 id 结束位置
                parts = line.split("|", 3)
                if len(parts) >= 3:
                    lines[i] = parts[0] + "|" + parts[1] + "| ✅ " + parts[2].lstrip() + "|" + "|".join(parts[3:])
            elif not done and "✅" in line:
                lines[i] = line.replace(" ✅ ", " ").replace("✅ ", "")
            break
    if not found:
        return f"（未找到待办项: {target}）"
    try:
        path.write_text("".join(lines), encoding="utf-8")
    except OSError:  # noqa: BLE001
        return "（待办清单写入失败）"
    return f"{'✅ 已标记完成' if done else '⬜ 已标记未完成'}: {target}"


def save_report(path: Path = DEFAULT_BACKLOG, out_dir: Path | None = None) -> str:
    """--report --save: 生成汇报并落盘到 docs/sprint10/（自动同步 Hermes 的素材）。"""
    report = render_report(path)
    if out_dir is None:
        out_dir = Path(__file__).resolve().parents[2] / "docs" / "sprint10"
    out_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    out = out_dir / f"progress-report-{ts}.md"
    try:
        out.write_text(report, encoding="utf-8")
    except OSError:  # noqa: BLE001
        return "（汇报落盘失败）"
    return f"汇报已生成: {out}"


# ---------------------------------------------------------------- 自动钩子（主线状态自动同步）

#: 代码证据 → 主线项映射（自动 sync 只标证据强=代码存在的项, 诚实不误标）
MAINLINE_CODE_EVIDENCE: dict[str, str] = {
    "M3-1": "factory-console/session/decomposer.py",       # M3a 递归原子拆解
    "M3-2": "factory-console/session/critical_path.py",    # M3b 关键路径
    "M3-3": "factory-console/session/scheduler.py",        # M3c 并行调度
    "M3-4": "factory-console/session/scheduler.py",        # M3e 动态分配(全链)
}


def sync_mainline(path: Path = DEFAULT_BACKLOG) -> list[str]:
    """自动钩子: 从代码存在性推断主线完成 → 自动标记待办清单。

    只标"代码证据存在"的项（真实现了才有代码）; 其余保持手动维护
    （诚实不误标, M3-5/6/7 等需人工判断）。返回本次新标记的 id 列表。
    """
    root = Path(__file__).resolve().parents[2]
    marked: list[str] = []
    for item_id, rel in MAINLINE_CODE_EVIDENCE.items():
        if (root / rel).exists():
            # 只标记"未标"的（幂等）
            groups = _parse_backlog(path)
            already = any(
                t["id"] == item_id and t["done"]
                for g in groups for t in g["tasks"]
            )
            if not already:
                r = mark_backlog_item(path, item_id, done=True)
                if "已标记" in r:
                    marked.append(item_id)
    return marked


# ---------------------------------------------------------------- 多源加载（设计文档全部任务）

def _parse_sprints(sprint_dir: Path | None = None) -> list[dict[str, Any]]:
    """S10 Sprint 任务: 扫描 docs/sprint10/ 文件名 → {id, title, done, files}。

    完成判断: 该 S10 有 *-acceptance*.md（Hermes 验收报告 = 完成的可靠证据）。
    """
    if sprint_dir is None:
        sprint_dir = Path(__file__).resolve().parents[2] / "docs" / "sprint10"
    if not sprint_dir.is_dir():
        return []
    sprints: dict[str, dict[str, Any]] = {}
    try:
        files = sorted(sprint_dir.iterdir())
    except OSError:  # noqa: BLE001
        return []
    for f in files:
        if not f.name.startswith("S10-") or f.suffix != ".md":
            continue
        m = re.match(r"(S10-\d+)", f.name)
        if not m:
            continue
        sid = m.group(1)
        s = sprints.setdefault(sid, {"id": sid, "title": sid, "done": False, "files": 0})
        s["files"] += 1
        if "acceptance" in f.name:
            s["done"] = True
            # 标题: 取 acceptance 文件名中 '-' 后的描述
            rest = f.name.replace(f"{sid}-", "").replace("-acceptance.md", "").replace("-prompt.md", "")
            if rest and rest != f.name:
                s["title"] = rest[:30]
    return [sprints[k] for k in sorted(sprints.keys())]


def _parse_s14(doc_path: Path | None = None) -> list[dict[str, Any]]:
    """§1.4 状态表（方案书章节级任务）: {id, title, status, todo}。"""
    if doc_path is None:
        doc_path = Path(__file__).resolve().parents[2] / "AI Software Factory — 完整产品方案书.md"
    if not doc_path.is_file():
        return []
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError:  # noqa: BLE001
        return []
    m = re.search(r"图例: ✅ 已实现.*?(?=\n### 1\.5|\n## )", text, re.S)
    if not m:
        return []
    rows = []
    for line in m.group(0).splitlines():
        if not line.startswith("|") or "章节" in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        # 只解析章节状态行（第一列 = 中文数字/附录 章节名; 过滤 §1.4.5 层级表格行）
        first = cells[0]
        if not re.match(r"^[一二三四五六七八九十]+ |^附录", first):
            continue
        rows.append({
            "id": first.replace(" ", "_"),
            "title": first,
            "status": cells[1],
            "todo": cells[3],
        })
    return rows


def render_timeline_html(workspace: Path, limit: int = 20) -> str:
    """生命线 HTML（时间轴: 时间→事件→对象, 纯 CSS 竖线时间轴）。"""
    audit_file = Path(workspace) / "audit" / "audit_events.json"
    if not audit_file.is_file():
        return "<p>（未找到 audit_events.json）</p>"
    try:
        data = json.loads(audit_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # noqa: BLE001
        return "<p>（审计文件损坏）</p>"
    events = data.get("events") if isinstance(data, dict) else data
    if not isinstance(events, list) or not events:
        return "<p>（暂无审计事件）</p>"
    events = sorted(events, key=lambda e: str(e.get("timestamp") or ""))[-limit:]

    items = []
    for e in events:
        ts = str(e.get("timestamp") or "")
        time_s = ts[11:19] if len(ts) >= 19 else ts
        date_s = ts[5:10] if len(ts) >= 10 else ""
        ev = e.get("event_type") or e.get("type") or "?"
        obj = e.get("task_id") or e.get("agent_id") or e.get("project_id") or ""
        # 事件类型 → 颜色
        color = "#4caf50" if "COMPLETE" in ev or "PASS" in ev or "CREATED" in ev else \
                "#ff9800" if "START" in ev or "RUN" in ev else "#e53935" if "FAIL" in ev or "REJECT" in ev else "#78909c"
        items.append(
            f'<li><span class="dot" style="background:{color}"></span>'
            f'<span class="t">{date_s} {time_s}</span>'
            f'<span class="e">{ev}</span>'
            f'<span class="o">{obj}</span></li>'
        )

    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>生命线 — 最近事件</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 16px; background: #0f1115; color: #e6e6e6; }}
  h1 {{ font-size: 18px; }}
  ul.timeline {{ list-style: none; margin: 14px 0 0; padding: 0; position: relative; }}
  ul.timeline:before {{ content: ""; position: absolute; left: 8px; top: 0; bottom: 0; width: 2px; background: #2a2e37; }}
  li {{ position: relative; padding: 6px 0 6px 30px; font-size: 13px; }}
  .dot {{ position: absolute; left: 4px; top: 10px; width: 10px; height: 10px; border-radius: 50%; }}
  .t {{ color: #78909c; margin-right: 10px; font-size: 12px; }}
  .e {{ color: #e6e6e6; margin-right: 10px; font-weight: 500; }}
  .o {{ color: #ffb74d; font-size: 12px; }}
  @media (max-width: 600px) {{ .t {{ display: block; }} }}
</style></head><body>
<h1>⏱ 生命线（最近 {len(items)} 事件）</h1>
<ul class="timeline">{"".join(items)}</ul>
</body></html>"""


def render_report_html(path: Path = DEFAULT_BACKLOG) -> str:
    """汇报 HTML（markdown 汇报 → 简单 HTML 渲染, 浏览器可读）。"""
    report = render_report(path)
    html_body = []
    for line in report.splitlines():
        if line.startswith("# "):
            html_body.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            html_body.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("- "):
            html_body.append(f"<li>{line[2:]}</li>")
        elif line.strip():
            html_body.append(f"<p>{line}</p>")
    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Factory 进度汇报</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 16px; background: #0f1115; color: #e6e6e6; }}
  h1 {{ font-size: 20px; }} h2 {{ font-size: 16px; color: #ffb74d; border-bottom: 1px solid #2a2e37; padding-bottom: 4px; }}
  li {{ font-size: 13px; color: #b0b6bf; margin: 3px 0; }}
  p {{ color: #9aa0a6; font-size: 13px; }}
</style></head><body>{"".join(html_body)}
<p style="margin-top:20px;color:#78909c">会话 /board report --save 可落盘为 markdown</p>
</body></html>"""
