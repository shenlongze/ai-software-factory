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
        sdk = _parse_sdk_tasks()
        if sdk:
            buf.append("")
            buf.append(f"🚀 SDK 任务 (§22.3): {sum(1 for t in sdk if t['done'])}/{len(sdk)} 完成 (4 阶段路线)")
            for t in sdk:
                mark = "✅" if t["done"] else "⬜"
                buf.append(f"   {mark} {t['id']} {t['title']} ({t['version']}) — {t['todo'][:40]}")
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

def render_timeline(workspace: Path, limit: int = 15, project_id: str = "") -> str:
    """生命线/时序图（读 audit_events 最近事件, 按时间线渲染）。

    project_id 非空 → 只显示该项目的核心事件 (项目化, 方案 A)。
    """
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
    slug = Path(str(project_id or "")).name
    if slug:
        # 项目过滤: 只保留该项目的核心事件 (需求确认事件大多无 project_id, 一并过滤)
        events = [e for e in events if str(e.get("project_id") or "") == slug]
        if not events:
            return f"（{slug} 暂无审计事件）"
    # 降噪: 需求确认折叠为汇总行; 核心事件最近 limit 条
    confirm_count = sum(1 for e in events if (e.get("event_type") or "") == "DISCOVERY_CONFIRMED")
    core = [e for e in events if (e.get("event_type") or "") != "DISCOVERY_CONFIRMED"]
    core = sorted(core, key=lambda e: str(e.get("timestamp") or ""))[-limit:]
    lines = ["⏱ 生命线 (最近事件, 时间→事件→对象):", ""]
    if confirm_count:
        lines.append(f"◉ 需求确认 ×{confirm_count} (产品发现流程, 已折叠)")
    prev_time = ""
    for e in core:
        ts = str(e.get("timestamp") or "")[11:19]  # HH:MM:SS
        marker = "│" if ts == prev_time else f"◉ {ts}"
        prev_time = ts
        ev = e.get("event_type") or e.get("type") or "?"
        label = EVENT_LABELS.get(ev, ev)
        obj = _timeline_obj_name(workspace, e)
        lines.append(f"{marker} {label} {obj}".rstrip())
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

def render_board_html(path: Path = DEFAULT_BACKLOG, workspace: Optional[Path | str] = None) -> str:
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
    # S10-110 P0-2: 项目监控聚合指标 (workspace 缺省 None → 不显示, 向后兼容)
    stats = dashboard_stats(workspace) if workspace is not None else None

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

    # S10-110 P0-2: 项目监控总览 (仅 workspace 提供时显示)
    monitor_html = ""
    if stats is not None:
        dist_items = "".join(
            f"<span><i class='dot d-{k}'></i>{STATUS_LABELS.get(k, k)} {v}</span>"
            for k, v in sorted(stats["status_dist"].items())
        )
        monitor_html = (
            "<p style='margin-top:10px;border-top:1px solid #2a2e37;padding-top:8px'>"
            f"📁 项目监控: <b>{stats['projects']}</b> 个 · 生命周期均值 <b>{stats['avg_lifecycle_pct']}%</b> · "
            f"进行中任务 <b id='mon-running'>{stats['running_tasks']}</b> · "
            f"失败 <b id='mon-failed'>{stats['failed_tasks']}</b></p>"
            f"<div class='dist-legend' id='mon-dist'>{dist_items}</div>"
        )

    # S10-110 P1-1: §22 SDK 任务 (第四数据源) — 作为独立卡片组
    sdk_tasks = _parse_sdk_tasks()
    sdk_html = ""
    if sdk_tasks:
        sdk_items = "".join(
            f"<li class=\"{'done' if t['done'] else 'todo'}\">{'✅' if t['done'] else '⬜'} "
            f"{t['id']} {t['title']} <span style='color:#78909c'>({t['version']})</span> — {t['todo'][:48]}</li>"
            for t in sdk_tasks
        )
        sdk_html = (
            "<div class='card main' data-kind='main' data-status='todo'>"
            f"<h2>🚀 SDK 路线 (§22.3) <span class='tag t-main'>主线</span> 🚧 "
            f"<span class='title'>4 阶段路线: 内核收尾 → SDK化 → 生态 → 商业化</span></h2>"
            f"<ul>{sdk_items}</ul></div>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
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
{_board_nav("main", "", workspace)}
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
  {monitor_html}
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
{sdk_html}
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
// S10-110 P0-1: 轻量增量刷新 (每 5s fetch /api/board/summary, 不整页刷新)
setInterval(function(){{
  fetch('/api/board/summary').then(function(r){{ return r.json(); }}).then(function(d){{
    if (!d) return;
    var mon = document.getElementById('mon-running');
    if (mon) mon.textContent = d.running_tasks;
    var mf = document.getElementById('mon-failed');
    if (mf) mf.textContent = d.failed_tasks;
  }}).catch(function(){{ /* 网络抖动忽略 */ }});
}}, 5000);
</script>
{_auto_refresh_script(30)}
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
        return (f"<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>"
                f"<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
                f"<title>依赖图 — {project_id or '项目'}</title></head>"
                f"<body style='background:#0f1115;color:#e6e6e6;font-family:sans-serif;padding:16px'>"
                f"{_board_nav('graph', project_id, workspace)}"
                f"<p>📭 项目未生成计划（无 plan.json）</p>"
                f"<p>真实数据: 项目需执行 M3b（拆解→关键路径）才会生成 plan.json — "
                f"在会话中 '开始开发' 即可</p>"
                f"<p>查看效果: <a href='/api/board/graph?project=demo' style='color:#8ab4f8'>demo 示例图</a></p>"
                f"{_auto_refresh_script(0)}</body></html>")
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
{_board_nav("graph", project_id, workspace)}
<h1>🔗 任务依赖图 <span class="legend">(★=CRITICAL 关键路径, 红色边框)</span></h1>
<div class="graph">{nodes}</div>
<div class="edges"><b>依赖边:</b><ul>{edges_html}</ul></div>
{_auto_refresh_script(0)}</body></html>"""


def render_chain_html(workspace: Path, project_id: str = "") -> str:
    """任务链 HTML 可视化（关键路径横向卡片链 + 箭头, ★关键节点 ▲汇聚点）。"""
    project_dir = Path(workspace) / "projects" / (project_id or "")
    plan_file = project_dir / "plan.json"
    if not plan_file.is_file():
        return (f"<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>"
                f"<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
                f"<title>任务链 — {project_id or '项目'}</title></head>"
                f"<body style='background:#0f1115;color:#e6e6e6;font-family:sans-serif;padding:16px'>"
                f"{_board_nav('chain', project_id, workspace)}"
                f"<p>📭 项目未生成计划（无 plan.json）</p>"
                f"<p>真实数据: 项目需执行 M3b 才会生成 — 会话中 '开始开发'</p>"
                f"<p>查看效果: <a href='/api/board/chain?project=demo' style='color:#8ab4f8'>demo 示例任务链</a></p>"
                f"{_auto_refresh_script(0)}</body></html>")
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
{_board_nav("chain", project_id, workspace)}
<h1>⛓ 任务链（关键路径）<span class="legend">★=关键节点 ▲=汇聚点</span></h1>
<div class="chain">{chain}</div>
<div class="total">总工期: {total_est}min · 关键节点 {len(cpath)} 个 · 汇聚点 {len(merge_ids)} 个</div>
{_auto_refresh_script(0)}</body></html>"""


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
        # S10-110 P1-2: 完成证据放宽 — acceptance(验收)/completion(完成)/
        # final(终报) 任一存在即视为该 Sprint 有完成证据 (早期 Sprint 无 acceptance
        # 但 completion/final 报告同样可靠; plan/prompt/设计 不算)
        if any(k in f.name for k in ("acceptance", "completion", "final")):
            s["done"] = True
            # 标题: 取证据文件名中 '-' 后的描述
            rest = (
                f.name.replace(f"{sid}-", "")
                .replace("-acceptance.md", "").replace("-completion.md", "")
                .replace("-final-report.md", "").replace("-final.md", "")
                .replace("-prompt.md", "")
            )
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


def render_timeline_html(workspace: Path, limit: int = 20, project_id: str = "") -> str:
    """生命线 HTML（时间轴: 时间→事件→对象, 纯 CSS 竖线时间轴）。

    project_id 非空 → 只显示该项目的核心事件 (项目化, 方案 A)。
    """
    audit_file = Path(workspace) / "audit" / "audit_events.json"

    def _shell(msg: str) -> str:
        return (f"<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>"
                f"<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
                f"<title>生命线</title></head>"
                f"<body style='background:#0f1115;color:#e6e6e6;font-family:sans-serif;padding:16px'>"
                f"{_board_nav('timeline', '', workspace)}{msg}{_auto_refresh_script(0)}</body></html>")

    if not audit_file.is_file():
        return _shell("<p>（未找到 audit_events.json）</p>")
    try:
        data = json.loads(audit_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # noqa: BLE001
        return _shell("<p>（审计文件损坏）</p>")
    events = data.get("events") if isinstance(data, dict) else data
    if not isinstance(events, list) or not events:
        return _shell("<p>（暂无审计事件）</p>")
    slug = Path(str(project_id or "")).name
    if slug:
        events = [e for e in events if str(e.get("project_id") or "") == slug]
        if not events:
            return _shell(f"<p>（{slug} 暂无审计事件）</p>")
    # 降噪: 高频"需求确认"(DISCOVERY_CONFIRMED) 折叠为一行汇总; 核心事件单独显示
    confirm_count = sum(1 for e in events if (e.get("event_type") or "") == "DISCOVERY_CONFIRMED")
    core = [e for e in events if (e.get("event_type") or "") != "DISCOVERY_CONFIRMED"]
    core = sorted(core, key=lambda e: str(e.get("timestamp") or ""))[-limit:]

    # 聚合降噪: 同秒同类型同对象事件合并显示 ×N
    agg: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for e in core:
        ts = str(e.get("timestamp") or "")
        time_s = ts[11:19] if len(ts) >= 19 else ts
        date_s = ts[5:10] if len(ts) >= 10 else ""
        ev = e.get("event_type") or e.get("type") or "?"
        obj = _timeline_obj_name(workspace, e)
        key = (date_s, time_s, ev, obj)
        if key in agg:
            agg[key]["count"] += 1
        else:
            agg[key] = {"date": date_s, "time": time_s, "ev": ev, "obj": obj, "count": 1}

    items = []
    if confirm_count:
        items.append(
            f'<li><span class="dot" style="background:#78909c"></span>'
            f'<span class="t">—</span><span class="e">需求确认</span>'
            f' <span class="cnt">×{confirm_count}</span>'
            f'<span class="o">· 产品发现流程（已折叠）</span></li>'
        )
    for row in agg.values():
        ev = row["ev"]
        label = EVENT_LABELS.get(ev, ev)
        obj = row["obj"]
        obj_html = f'<span class="o">· {obj}</span>' if obj else ""
        cnt_html = f' <span class="cnt">×{row["count"]}</span>' if row["count"] > 1 else ""
        # 事件类型 → 颜色
        color = "#4caf50" if "COMPLETE" in ev or "PASS" in ev or "CREATED" in ev else \
                "#ff9800" if "START" in ev or "RUN" in ev else "#e53935" if "FAIL" in ev or "REJECT" in ev else "#78909c"
        items.append(
            f'<li><span class="dot" style="background:{color}"></span>'
            f'<span class="t">{row["date"]} {row["time"]}</span>'
            f'<span class="e">{label}</span>{cnt_html}'
            f'{obj_html}</li>'
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
  .cnt {{ color: #fb8c00; font-size: 11px; background: #3e2723; border-radius: 8px; padding: 1px 7px; margin-right: 8px; }}
  .hint {{ color: #78909c; font-size: 12px; margin-top: 12px; }}
  @media (max-width: 600px) {{ .t {{ display: block; }} }}
</style></head><body>
{_board_nav("timeline", "", workspace)}
<h1>⏱ 生命线（核心事件 {len(agg)} 条 + 需求确认 ×{confirm_count}）</h1>
<ul class="timeline">{"".join(items)}</ul>
{_auto_refresh_script(0)}</body></html>"""


def render_report_html(path: Path = DEFAULT_BACKLOG, workspace: Optional[Path | str] = None, project_id: str = "") -> str:
    """汇报 HTML（markdown 汇报 → 简单 HTML 渲染, 浏览器可读）。

    project_id 非空 → 项目汇报 (方案 A); 否则 AI 主线汇报。
    """
    slug = Path(str(project_id or "")).name
    if slug and workspace is not None:
        report = render_project_report(workspace, slug)
    else:
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
</style></head><body>
{_board_nav("report", "", workspace)}
{"".join(html_body)}
<p style="margin-top:20px;color:#78909c">会话 /board report --save 可落盘为 markdown</p>
{_auto_refresh_script(0)}</body></html>"""


# ---------------------------------------------------------------- 单项目管理视图 (S10-110)

#: 全生命周期 11 段（1-7 现有数据映射; 8-11 占位, 待部署/运维落地）
PROJECT_LIFECYCLE_STAGES: tuple[tuple[str, str], ...] = (
    ("discovery", "发现"),
    ("confirm", "确认"),
    ("prd", "PRD"),
    ("engineering", "工程"),
    ("development", "开发"),
    ("testing", "测试"),
    ("acceptance", "验收"),
    ("delivery", "交付"),
    ("deploy", "部署"),
    ("operations", "运维"),
    ("update", "更新"),
)

#: 执行状态中视为"已完成"的任务状态（execution_state.json tasks[].status）
_DONE_TASK_STATUSES = ("done", "delivered", "approved", "applied")


def _read_product_info(workspace: Path | str, slug: str) -> Optional[dict[str, Any]]:
    """读单项目 product.json → {name,status,problem,user,core_features,_mtime} (失败安全)。"""
    pf = Path(workspace) / "projects" / slug / "product.json"
    if not pf.is_file():
        return None
    try:
        data = json.loads(pf.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — 损坏 → 空壳 (不崩)
        data = {}
    try:
        data["_mtime"] = pf.stat().st_mtime
    except OSError:  # noqa: BLE001
        data["_mtime"] = 0.0
    return data


def _project_stage_status(workspace: Path | str, slug: str) -> list[dict[str, Any]]:
    """单项目生命周期阶段判定 (11 段, 确定性可断言)。

    1-7 映射现有资产; 8-11 (交付/部署/运维/更新) 无数据源 → 占位未开始。
    """
    pdir = Path(workspace) / "projects" / slug
    product_file = pdir / "product.json"
    status = ""
    if product_file.is_file():
        try:
            status = str((json.loads(product_file.read_text(encoding="utf-8")) or {}).get("status") or "")
        except Exception:  # noqa: BLE001
            status = ""

    def has(name: str) -> bool:
        return (pdir / name).is_file()

    rules: list[tuple[str, str, bool]] = [
        ("discovery", "发现", product_file.is_file()),
        ("confirm", "确认", product_file.is_file()),
        ("prd", "PRD", has("PRD.md")),
        ("engineering", "工程", has("engineering.json")),
        ("development", "开发", has("tasks.json")),
        ("testing", "测试", has("validation_result.json")),
        ("acceptance", "验收", status == "user_acceptance"),
        ("delivery", "交付", False),
        ("deploy", "部署", False),
        ("operations", "运维", False),
        ("update", "更新", False),
    ]
    return [{"id": sid, "label": label, "done": done} for sid, label, done in rules]


def _project_task_progress(workspace: Path | str, slug: str) -> dict[str, int]:
    """任务进度 {done,total,pct} — 读 execution_state.json tasks[].status (回退 tasks.json)。"""
    es = Path(workspace) / "projects" / slug / "execution_state.json"
    tasks: list[dict[str, Any]] = []
    if es.is_file():
        try:
            tasks = (json.loads(es.read_text(encoding="utf-8")) or {}).get("tasks") or []
        except Exception:  # noqa: BLE001
            tasks = []
    if not tasks:
        tf = Path(workspace) / "projects" / slug / "tasks.json"
        if tf.is_file():
            try:
                tasks = (json.loads(tf.read_text(encoding="utf-8")) or {}).get("tasks") or []
            except Exception:  # noqa: BLE001
                tasks = []
    if not tasks:
        return {"done": 0, "total": 0, "pct": 0}
    done = sum(1 for t in tasks if str(t.get("status") or "") in _DONE_TASK_STATUSES)
    total = len(tasks)
    return {"done": done, "total": total, "pct": round(done * 100 / total) if total else 0}


def list_projects(workspace: Path | str) -> list[dict[str, Any]]:
    """项目列表 (select 用): {slug,name,status,mtime} — 只读, 失败安全。"""
    root = Path(workspace) / "projects"
    if not root.is_dir():
        return []
    projects: list[dict[str, Any]] = []
    for pdir in sorted(root.iterdir()):
        if not pdir.is_dir():
            continue
        pf = pdir / "product.json"
        if not pf.is_file():
            continue
        try:
            data = json.loads(pf.read_text(encoding="utf-8")) or {}
            name = str(data.get("name") or pdir.name)
            status = str(data.get("status") or "?")
            mtime = pf.stat().st_mtime
        except Exception:  # noqa: BLE001
            name, status, mtime = pdir.name, "?", 0.0
        projects.append({"slug": pdir.name, "name": name, "status": status, "mtime": mtime})
    projects.sort(key=lambda p: p["mtime"], reverse=True)
    return projects


def render_projects_list(workspace: Path | str) -> str:
    """项目列表文本 (select 切换用): slug/名/状态/更新时间。"""
    projects = list_projects(workspace)
    if not projects:
        return "（暂无项目 — 在会话中描述产品想法创建第一个项目）"
    import datetime

    lines = [f"📁 项目列表 ({len(projects)} 个):", ""]
    for p in projects:
        ts = (
            datetime.datetime.fromtimestamp(p["mtime"]).strftime("%m-%d %H:%M")
            if p["mtime"]
            else "?"
        )
        lines.append(f"  {p['slug']:<16} {str(p['name'])[:16]:<18} [{p['status']}] {ts}")
    lines.append("")
    lines.append("查看单项目: /board project <slug>   例: /board project P-e023a04c")
    return "\n".join(lines)


def render_project_lifecycle(workspace: Path | str, project_id: str = "") -> str:
    """单项目管理视图 (只读, S10-110): 全生命周期 11 段 + 文档产物 + 任务进度 + 更新时间。

    隔离铁律: 只读 projects/<slug>/ 该项目文件; 无显式项目 → 空态提示 (不猜项目)。
    """
    slug = Path(str(project_id or "")).name
    if not slug:
        return "（未选择项目 — 用 /board project 查看项目列表）"
    info = _read_product_info(workspace, slug)
    if info is None:
        return f"（项目不存在: {slug} — 用 /board project 查看项目列表）"
    stages = _project_stage_status(workspace, slug)
    done_count = sum(1 for s in stages if s["done"])
    total = len(stages)
    current = next((s for s in stages if not s["done"]), None)
    bar_len = 24
    filled = bar_len * done_count // total if total else 0
    bar = "█" * filled + "░" * (bar_len - filled)
    stage_txt = " ".join(
        ("✅" if s["done"] else "●" if s["id"] == (current or {}).get("id") else "○") + s["label"]
        for s in stages
    )
    lines = [
        f"📌 当前项目: {info.get('name') or slug} ({slug})",
        f"🌱 全生命周期 {done_count}/{total}: {bar}",
        f"   {stage_txt}",
    ]
    if current:
        lines.append(f"   当前卡点: {current['label']}（未开始）")
    pdir = Path(workspace) / "projects" / slug

    def has(name: str) -> str:
        return "✅" if (pdir / name).is_file() else "—"

    lines.append(
        f"📄 文档产物: PRD {has('PRD.md')} · 工程 {has('engineering.json')} · 任务 {has('tasks.json')} · 验证 {has('validation_result.json')}"
    )
    tp = _project_task_progress(workspace, slug)
    if tp["total"]:
        lines.append(f"📊 任务进度: ✅{tp['done']} ⬜{tp['total'] - tp['done']} ({tp['pct']}%)")
    # S10-110 P1-3: 项目内任务清单 (只读 execution_state.json tasks)
    task_lines = _project_task_list(workspace, slug)
    if task_lines:
        lines.append("📋 任务清单:")
        lines.extend(f"  {ln}" for ln in task_lines)
    mtime = info.get("_mtime") or 0
    if mtime:
        import datetime

        ts = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        lines.append(f"🕐 最近更新: {ts}")
    return "\n".join(lines)


def render_projects_list_html(workspace: Path | str) -> str:
    """项目列表 HTML (select 切换): 卡片网格 + 状态色 + 当前项目标记。"""
    projects = list_projects(workspace)
    # 会话当前项目 (session_state.json, 只读; 失败安全)
    current = _read_session_current_project(workspace)
    cards = []
    if not projects:
        cards.append("<p class='empty'>（暂无项目 — 在会话中描述产品想法创建第一个项目）</p>")
    for p in projects:
        st = p["status"]
        cls = {
            "user_acceptance": "st-done", "execution_ready": "st-ready",
            "development": "st-dev", "prd_ready": "st-prd",
            "project_created": "st-new",
        }.get(st, "st-new")
        cur_mark = " <span class='cur'>当前</span>" if p["slug"] == current else ""
        ts = (
            __import__("datetime").datetime.fromtimestamp(p["mtime"]).strftime("%m-%d %H:%M")
            if p["mtime"] else "?"
        )
        cards.append(
            f'<a class="pcard {cls}" href="/api/board?view=project&amp;project={p["slug"]}">'
            f'<span class="pname">{p["name"]}{cur_mark}</span>'
            f'<span class="pslug">{p["slug"]}</span>'
            f'<span class="pstatus">{st}</span>'
            f'<span class="pts">{ts}</span></a>'
        )
    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Factory — 项目列表</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 16px; background: #0f1115; color: #e6e6e6; }}
  .nav a {{ color: #8ab4f8; text-decoration: none; margin-right: 12px; font-size: 13px; }}
  .nav a.active {{ color: #ffb74d; font-weight: 600; }}
  h1 {{ font-size: 20px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }}
  .pcard {{ background: #1a1e26; border-radius: 8px; padding: 12px; text-decoration: none; color: inherit; display: block; border-left: 3px solid #546e7a; }}
  .pcard:hover {{ background: #232833; }}
  .pname {{ display: block; font-size: 15px; font-weight: 600; }}
  .pslug {{ display: block; font-size: 11px; color: #9aa0a6; margin-top: 2px; }}
  .pstatus {{ display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 10px; margin-top: 6px; }}
  .st-done {{ border-left-color: #43a047; }} .st-done .pstatus {{ background: #1b5e20; color: #a5d6a7; }}
  .st-ready {{ border-left-color: #1e88e5; }} .st-ready .pstatus {{ background: #0d47a1; color: #90caf9; }}
  .st-dev {{ border-left-color: #fb8c00; }} .st-dev .pstatus {{ background: #e65100; color: #ffcc80; }}
  .st-prd {{ border-left-color: #8e24aa; }} .st-prd .pstatus {{ background: #4a148c; color: #ce93d8; }}
  .st-new {{ border-left-color: #546e7a; }} .st-new .pstatus {{ background: #37474f; color: #b0bec5; }}
  .pts {{ display: block; font-size: 11px; color: #78909c; margin-top: 6px; }}
  .empty {{ color: #9aa0a6; }}
</style></head><body>
{_board_nav("projects", "", workspace)}
<h1>📁 项目列表（{len(projects)} 个）</h1>
<p style="color:#9aa0a6;font-size:12px">点击项目卡片查看单项目管理视图（全生命周期）</p>
<div class="grid">{"".join(cards)}</div>
{_auto_refresh_script(0)}</body></html>"""


def render_project_lifecycle_html(workspace: Path | str, project_id: str = "") -> str:
    """单项目管理视图 HTML (只读, S10-110): 11 段进度条 + 文档产物 + 任务进度。"""
    slug = Path(str(project_id or "")).name
    info = _read_product_info(workspace, slug) if slug else None
    if info is None:
        return render_projects_list_html(workspace) if not slug else (
            f"<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'><title>项目不存在</title></head>"
            f"<body style='background:#0f1115;color:#e6e6e6;font-family:sans-serif;padding:16px'>"
            f"<p>项目不存在: {slug} — <a href='/api/board?view=projects' style='color:#8ab4f8'>返回项目列表</a></p>"
            f"{_auto_refresh_script(0)}</body></html>"
        )
    stages = _project_stage_status(workspace, slug)
    done_count = sum(1 for s in stages if s["done"])
    total = len(stages)
    pct = round(done_count * 100 / total) if total else 0
    segs = []
    colors = {
        "discovery": "#546e7a", "confirm": "#5c6bc0", "prd": "#8e24aa",
        "engineering": "#1e88e5", "development": "#fb8c00", "testing": "#00897b",
        "acceptance": "#43a047", "delivery": "#6d4c41", "deploy": "#3949ab",
        "operations": "#00838f", "update": "#7b1fa2",
    }
    for s in stages:
        c = colors.get(s["id"], "#555")
        segs.append(
            f'<span class="seg {"on" if s["done"] else "off"}" style="border-color:{c}" title="{s["label"]}">'
            f'{"✓" if s["done"] else "○"}{s["label"]}</span>'
        )
    pdir = Path(workspace) / "projects" / slug

    def has(name: str) -> str:
        return "✅" if (pdir / name).is_file() else "—"

    tp = _project_task_progress(workspace, slug)
    task_html = (
        f"<p>📊 任务进度: ✅<b>{tp['done']}</b> ⬜{tp['total'] - tp['done']} ({tp['pct']}%)</p>"
        if tp["total"] else "<p>📊 任务进度: （暂无任务）</p>"
    )
    mtime = info.get("_mtime") or 0
    import datetime

    ts = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M") if mtime else "?"
    # S10-110 P1-3: 项目内任务清单 (只读, 上限 20)
    task_rows = _project_task_list(workspace, slug)
    # S10-110 完善: 任务状态汇总 (完成/进行中/失败/待办)
    counts = _project_task_status_counts(workspace, slug)
    counts_html = (
        f"<p style='font-size:12px;color:#9aa0a6'>✅完成 {counts['done']} · "
        f"🔵进行中 {counts['running']} · ❌失败 {counts['failed']} · "
        f"⬜待办 {counts['pending']} · 共 {counts['total']}</p>"
    ) if counts["total"] else ""
    tasks_card = ""
    if task_rows:
        rows_html = "".join(f"<tr><td>{r}</td></tr>" for r in task_rows)
        tasks_card = (
            "<div class='card'><h2>📋 任务清单</h2>"
            f"{counts_html}"
            f"<table class='tasks'><tbody>{rows_html}</tbody></table></div>"
        )
    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{info.get('name') or slug} — 项目视图</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 16px; background: #0f1115; color: #e6e6e6; }}
  .nav a {{ color: #8ab4f8; text-decoration: none; margin-right: 12px; font-size: 13px; }}
  .nav a.active {{ color: #ffb74d; font-weight: 600; }}
  h1 {{ font-size: 20px; }} h2 {{ font-size: 15px; color: #ffb74d; }}
  .stages {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0; }}
  .seg {{ border: 1px solid; border-radius: 12px; padding: 3px 10px; font-size: 12px; }}
  .seg.on {{ background: #1b5e20; color: #a5d6a7; border-color: #43a047; }}
  .seg.off {{ color: #78909c; background: #1a1e26; }}
  .bar {{ height: 8px; background: #2a2e37; border-radius: 4px; overflow: hidden; margin: 8px 0; }}
  .bar > div {{ height: 100%; background: linear-gradient(90deg,#43a047,#1e88e5); }}
  .docs {{ display: flex; gap: 12px; flex-wrap: wrap; font-size: 13px; }}
  .card {{ background: #1a1e26; border-radius: 8px; padding: 14px; margin-top: 12px; }}
  table.tasks {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  table.tasks td {{ padding: 5px 8px; border-bottom: 1px solid #2a2e37; color: #b0b6bf; }}
  p {{ font-size: 13px; color: #b0b6bf; }}
  .back {{ color: #8ab4f8; text-decoration: none; font-size: 13px; }}
</style></head><body>
{_board_nav("projects", slug, workspace)}
<h1>📌 {info.get('name') or slug} <span style="font-size:12px;color:#78909c">({slug})</span></h1>
<div class="card">
  <h2>🌱 全生命周期 {done_count}/{total} ({pct}%)</h2>
  <div class="bar"><div style="width:{pct}%"></div></div>
  <div class="stages">{"".join(segs)}</div>
</div>
<div class="card">
  <h2>📄 文档产物</h2>
  <div class="docs">
    <span>PRD {has('PRD.md')}</span><span>工程 {has('engineering.json')}</span>
    <span>任务 {has('tasks.json')}</span><span>验证 {has('validation_result.json')}</span>
  </div>
</div>
{tasks_card}
<div class="card">{task_html}<p>🕐 最近更新: {ts}</p></div>
<p><a class="back" href="/api/board?view=projects">← 返回项目列表</a></p>
{_auto_refresh_script(15)}
</body></html>"""


# ---------------------------------------------------------------- 项目监控聚合 (S10-110 P0-2)

def dashboard_stats(workspace: Path | str) -> dict[str, Any]:
    """项目监控聚合指标（Dashboard 数据源, 只读）:

    {projects, status_dist, avg_lifecycle_pct, running_tasks, failed_tasks}
    """
    projects = list_projects(workspace)
    status_dist: dict[str, int] = {}
    for p in projects:
        st = p["status"]
        status_dist[st] = status_dist.get(st, 0) + 1
    total_done = total_stages = 0
    for p in projects:
        stages = _project_stage_status(workspace, p["slug"])
        total_done += sum(1 for s in stages if s["done"])
        total_stages += len(stages)
    avg_pct = round(total_done * 100 / total_stages) if total_stages else 0
    running = failed = 0
    for p in projects:
        es = Path(workspace) / "projects" / p["slug"] / "execution_state.json"
        if not es.is_file():
            continue
        try:
            tasks = (json.loads(es.read_text(encoding="utf-8")) or {}).get("tasks") or []
        except Exception:  # noqa: BLE001
            continue
        for t in tasks:
            st = str(t.get("status") or "")
            if st in ("running", "in_progress", "started"):
                running += 1
            elif st == "failed":
                failed += 1
    return {
        "projects": len(projects),
        "status_dist": status_dist,
        "avg_lifecycle_pct": avg_pct,
        "running_tasks": running,
        "failed_tasks": failed,
    }


#: 状态中文标签（Dashboard 展示）
STATUS_LABELS: dict[str, str] = {
    "project_created": "已创建",
    "prd_ready": "PRD完成",
    "execution_ready": "工程就绪",
    "development": "开发中",
    "user_acceptance": "已验收",
}


# ---------------------------------------------------------------- §22 SDK 任务 (S10-110 P1-1 第四数据源)

def _parse_sdk_tasks(doc_path: Path | None = None) -> list[dict[str, Any]]:
    """方案书 §22.3 4 阶段路线 → SDK 任务 (第四数据源)。

    解析 '### 22.3 4 阶段路线' 后的代码块: 每行 '阶段 N <标题> (<版本>): <内容>'
    → {id, title, version, todo, done}。完成判定: 版本里程碑已过 (阶段 1 对应
    v1.2 前 = 视为主线未收尾; 这里仅展示, done 按待办清单 M3 完成度推断: 阶段 1
    依赖 M3 收尾, 其余未开始)。
    """
    if doc_path is None:
        doc_path = Path(__file__).resolve().parents[2] / "AI Software Factory — 完整产品方案书.md"
    if not doc_path.is_file():
        return []
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError:  # noqa: BLE001
        return []
    m = re.search(r"### 22\.3 4 阶段路线\s*\n```\n(.*?)\n```", text, re.S)
    if not m:
        return []
    tasks: list[dict[str, Any]] = []
    for line in m.group(1).splitlines():
        line = line.strip()
        mm = re.match(r"阶段\s*(\d+)\s+(.+?)\s*\(([^)]+)\):\s*(.+)", line)
        if not mm:
            continue
        idx, title, version, todo = mm.groups()
        # 完成判定: 阶段 1 依赖 M3 收尾 (M3 4/7 → 未完成); 其余未开始
        done = False
        tasks.append({
            "id": f"SDK-{idx}",
            "title": title.strip(),
            "version": version.strip(),
            "todo": todo.strip(),
            "done": done,
        })
    return tasks


def _project_task_list(workspace: Path | str, slug: str) -> list[str]:
    """项目内任务清单 (只读): 每任务 [状态标记] id name (agent)。失败安全。"""
    es = Path(workspace) / "projects" / slug / "execution_state.json"
    tasks: list[dict[str, Any]] = []
    if es.is_file():
        try:
            tasks = (json.loads(es.read_text(encoding="utf-8")) or {}).get("tasks") or []
        except Exception:  # noqa: BLE001
            tasks = []
    if not tasks:
        tf = Path(workspace) / "projects" / slug / "tasks.json"
        if tf.is_file():
            try:
                tasks = (json.loads(tf.read_text(encoding="utf-8")) or {}).get("tasks") or []
            except Exception:  # noqa: BLE001
                tasks = []
    marks = {
        "done": "✅", "delivered": "✅", "approved": "✅", "applied": "✅",
        "running": "🔵", "in_progress": "🔵", "started": "🔵",
        "failed": "❌", "blocked": "⛔", "pending": "⬜", "todo": "⬜",
    }
    lines = []
    for t in tasks[:20]:  # 上限 20 防刷屏
        tid = str(t.get("id") or "?")
        name = str(t.get("name") or tid)[:36]
        st = str(t.get("status") or "")
        mark = marks.get(st, "⬜")
        agent = str(t.get("agent") or "")
        agent_s = f" [{agent}]" if agent else ""
        lines.append(f"{mark} {tid} {name}{agent_s} ({st or '待办'})")
    return lines


# ---------------------------------------------------------------- 共享导航 (S10-110 返回修复)

def _board_nav(active: str = "project", project: str = "", workspace: Optional[Path | str] = None) -> str:
    """board 页面共享导航（项目优先: 第一步选项目, 第二步看面板）。

    行1: 大项目选择器 (select) + 刷新间隔选择器
    行2: 项目面板 tab (项目视图/任务树/依赖图/任务链/生命线/汇报) + AI 主线 (降级)
    """
    g = project or ""
    base = ("display:inline-block;background:#1a1d24;border:1px solid #2a2e37;"
            "color:#b0b6bf;border-radius:6px;padding:6px 14px;font-size:13px;"
            "text-decoration:none;margin-right:8px;margin-bottom:6px")
    act = "background:#1565c0;color:#fff;border-color:#1565c0"
    demo = "demo"
    # 项目优先: 未选项目时, 项目面板 tab (任务树/依赖图/任务链) 指向项目列表引导,
    # 不再 fallback 到 demo 示例 (Founder: 选择是第一步)
    tabs = [
        ("project", f"/api/board?view=project&project={g}" if g else "/api/board?view=projects", "📊 项目"),
        ("tasks", f"/api/board/tasks?project={g}" if g else "/api/board?view=projects", "🗂 任务树"),
        ("graph", f"/api/board/graph?project={g}" if g else "/api/board?view=projects", "🔗 依赖图"),
        ("chain", f"/api/board/chain?project={g}" if g else "/api/board?view=projects", "⛓ 任务链"),
        ("timeline", f"/api/board/timeline?project={g}" if g else "/api/board/timeline", "⏱ 生命线"),
        ("report", f"/api/board?view=report&project={g}" if g else "/api/board?view=report", "📄 汇报"),
        ("mainline", "/api/board?view=mainline", "📋 AI主线面板"),
    ]
    links = "".join(
        f'<a href="{url}" style="{base};{act}"{" title=当前" if key == active else ""}>{label}</a>'
        if key == active else f'<a href="{url}" style="{base}">{label}</a>'
        for key, url, label in tabs
    )
    row1 = ""
    if workspace is not None:
        row1 += _project_select_html(workspace, project, active, big=True)
    row1 += _refresh_select_html()
    return (f'<div style="margin-bottom:12px"><div style="display:flex;align-items:center;'
            f'flex-wrap:wrap;gap:4px;margin-bottom:8px">{row1}</div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:4px">{links}</div></div>')


# ---------------------------------------------------------------- 任务状态汇总 + 任务树 (S10-110 完善)

def _project_task_status_counts(workspace: Path | str, slug: str) -> dict[str, int]:
    """任务状态汇总 {done,running,failed,pending,total} (只读, 失败安全)。"""
    es = Path(workspace) / "projects" / slug / "execution_state.json"
    tasks: list[dict[str, Any]] = []
    if es.is_file():
        try:
            tasks = (json.loads(es.read_text(encoding="utf-8")) or {}).get("tasks") or []
        except Exception:  # noqa: BLE001
            tasks = []
    counts = {"done": 0, "running": 0, "failed": 0, "pending": 0, "total": len(tasks)}
    for t in tasks:
        st = str(t.get("status") or "")
        if st in _DONE_TASK_STATUSES:
            counts["done"] += 1
        elif st in ("running", "in_progress", "started"):
            counts["running"] += 1
        elif st == "failed":
            counts["failed"] += 1
        else:
            counts["pending"] += 1
    return counts


def _project_task_tree(workspace: Path | str, slug: str) -> list[dict[str, Any]]:
    """项目任务树 (epic → feature → task): 读 execution_state.json (回退 tasks.json)。"""
    es = Path(workspace) / "projects" / slug / "execution_state.json"
    tasks: list[dict[str, Any]] = []
    if es.is_file():
        try:
            tasks = (json.loads(es.read_text(encoding="utf-8")) or {}).get("tasks") or []
        except Exception:  # noqa: BLE001
            tasks = []
    if not tasks:
        tf = Path(workspace) / "projects" / slug / "tasks.json"
        if tf.is_file():
            try:
                tasks = (json.loads(tf.read_text(encoding="utf-8")) or {}).get("tasks") or []
            except Exception:  # noqa: BLE001
                tasks = []
    epics: dict[str, dict[str, Any]] = {}
    for t in tasks:
        epic = str(t.get("epic") or t.get("feature") or "未分组")
        ep = epics.setdefault(epic, {"epic": epic, "features": {}})
        feat = str(t.get("feature") or epic)
        fl = ep["features"].setdefault(feat, {"feature": feat, "tasks": []})
        fl["tasks"].append(t)
    return [ep for ep in epics.values()]


def render_project_tasktree_html(workspace: Path | str, slug: str) -> str:
    """项目任务树 HTML (epic → feature → task, 状态色点; 用户要的"无序图"方向)。"""
    slug = Path(str(slug or "")).name
    info = _read_product_info(workspace, slug) if slug else None
    # 项目存在性: 有 product.json 或任务资产 (tasks/execution_state/plan) 均视为存在
    # (demo 等仅有 plan.json 的示例项目也能进入, 诚实显示"暂无任务")
    pdir = Path(workspace) / "projects" / slug if slug else None
    has_assets = pdir is not None and pdir.is_dir() and any(
        (pdir / n).exists()
        for n in ("product.json", "tasks.json", "execution_state.json", "plan.json")
    )
    if not has_assets:
        return _board_nav("project", slug, workspace) + "<p>（项目不存在或未选择）</p>"
    tree = _project_task_tree(workspace, slug)
    # 名称 fallback: 无 product.json → slug (demo 等示例)
    if info is None:
        info = {"name": slug}
    marks = {"done": "✅", "delivered": "✅", "approved": "✅", "applied": "✅",
             "running": "🔵", "in_progress": "🔵", "started": "🔵",
             "failed": "❌", "blocked": "⛔", "pending": "⬜", "todo": "⬜"}
    cols = {"done": "#43a047", "running": "#1e88e5", "failed": "#e53935",
            "pending": "#78909c", "blocked": "#fb8c00"}
    epic_html = []
    for ep in tree:
        feat_items = []
        for fl in ep["features"].values():
            task_items = []
            for t in fl["tasks"][:30]:
                st = str(t.get("status") or "")
                mark = marks.get(st, "⬜")
                color = cols.get(st, "#78909c")
                agent = str(t.get("agent") or "")
                agent_s = f'<span class="tag">{agent}</span>' if agent else ""
                task_items.append(
                    f'<li class="task {st}"><span class="tmark" style="color:{color}">{mark}</span> '
                    f'{str(t.get("id") or "?")} {str(t.get("name") or "")[:40]}{agent_s} '
                    f'<span class="tstatus">{st or "待办"}</span></li>'
                )
            feat_items.append(
                f'<div class="feat"><div class="feat-name">📦 {fl["feature"]}</div>'
                f'<ul>{"".join(task_items)}</ul></div>'
            )
        epic_html.append(
            f'<div class="epic"><div class="epic-name">🗂 {ep["epic"]}</div>'
            f'<div class="feats">{"".join(feat_items)}</div></div>'
        )
    body = "".join(epic_html) if epic_html else "<p>（暂无任务）</p>"
    counts = _project_task_status_counts(workspace, slug)
    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>任务树 — {info.get('name') or slug}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 16px; background: #0f1115; color: #e6e6e6; }}
  h1 {{ font-size: 18px; }}
  .summary {{ color: #9aa0a6; font-size: 13px; margin: 8px 0 14px; }}
  .epic {{ background: #1a1e26; border-radius: 8px; padding: 12px 14px; margin-bottom: 10px; }}
  .epic-name {{ font-weight: 600; color: #ffb74d; margin-bottom: 8px; }}
  .feat {{ margin: 6px 0 6px 8px; padding-left: 10px; border-left: 2px solid #2a2e37; }}
  .feat-name {{ font-size: 13px; color: #b0bec5; margin-bottom: 4px; }}
  ul {{ list-style: none; margin: 0; padding: 0; }}
  li.task {{ font-size: 12px; padding: 3px 0; color: #b0b6bf; }}
  .tag {{ font-size: 10px; background: #37474f; color: #b0bec5; border-radius: 4px; padding: 1px 6px; margin-left: 6px; }}
  .tstatus {{ font-size: 10px; color: #78909c; margin-left: 6px; }}
</style></head><body>
{_board_nav("tasks", slug, workspace)}
<h1>🗂 项目任务树 — {info.get('name') or slug}</h1>
<div class="summary">✅完成 {counts['done']} · 🔵进行中 {counts['running']} · ❌失败 {counts['failed']} · ⬜待办 {counts['pending']} · 共 {counts['total']}</div>
{body}
{_auto_refresh_script(15)}
</body></html>"""


def _project_select_html(workspace: Path | str, current: str, active: str, *, big: bool = False) -> str:
    """项目选择器 (select dropdown, 第一步): 切换后跳转到当前视图的对应项目。

    graph/chain/tasks → 对应页面带新项目; 其余 → 单项目视图。实时读盘, 无缓存。
    big=True → 置顶大选择器 (项目优先首页)。
    """
    projects = list_projects(workspace)
    if not projects:
        return ""
    route = {
        "graph": "/api/board/graph?project=",
        "chain": "/api/board/chain?project=",
        "tasks": "/api/board/tasks?project=",
    }.get(active, "/api/board?view=project&project=")
    opts = []
    slugs = {p["slug"] for p in projects}
    # URL 项目不在注册列表 (demo 等示例/未注册) → 加显式选项并选中, 避免
    # "界面选墨笺/URL 却是 demo" 的误导 (选择器与 URL 必须一致)
    if current and current not in slugs:
        opts.append(
            f'<option value="{current}" selected>{current} (示例/未注册)</option>'
        )
    for p in projects:
        sel = " selected" if p["slug"] == current else ""
        label = f"{p['name']} ({p['slug']})"
        opts.append(f'<option value="{p["slug"]}"{sel}>{label}</option>')
    style = ("background:#1a1d24;border:1px solid #2a2e37;color:#b0b6bf;"
             "border-radius:6px;padding:6px 10px;font-size:13px;max-width:260px")
    if big:
        style = ("background:#11141a;border:2px solid #1565c0;color:#e6e6e6;"
                 "border-radius:8px;padding:9px 14px;font-size:15px;font-weight:600;"
                 "max-width:340px")
    label = "📁 选择项目:" if big else ""
    return (f'<span style="display:flex;align-items:center;gap:6px">{label}'
            f'<select style="{style}" title="选择项目" '
            f"onchange=\"location='{route}'+encodeURIComponent(this.value)\">"
            f'{"".join(opts)}</select></span>')




def _read_session_current_project(workspace: Path | str) -> str:
    """读会话当前项目 (session_state.json, 只读; 失败安全 → "")。"""
    try:
        state = json.loads(
            (Path(workspace) / "session_state.json").read_text(encoding="utf-8")
        ) or {}
        return str(state.get("current_project") or "")
    except Exception:  # noqa: BLE001
        return ""


#: 刷新间隔选项 (秒; 0=关闭)
REFRESH_OPTIONS: tuple[int, ...] = (5, 15, 30, 60, 0)


def _refresh_select_html() -> str:
    """刷新间隔选择器 (select): 5s/15s/30s/60s/关闭, 切换后 URL 带 ?refresh=N。"""
    opts = "".join(
        f'<option value="{n}">{"关闭" if n == 0 else f"刷新{n}s"}</option>'
        for n in REFRESH_OPTIONS
    )
    style = ("background:#1a1d24;border:1px solid #2a2e37;color:#b0b6bf;"
             "border-radius:6px;padding:6px 10px;font-size:13px;margin-left:8px")
    return (f'<select id="factory-refresh" style="{style}" title="自动刷新间隔" '
            f'onchange="var u=new URL(location.href);'
            f"if(this.value=='0'){{u.searchParams.delete('refresh')}}"
            f"else{{u.searchParams.set('refresh',this.value)}};"
            f"location.href=u.href;\">{opts}</select>")


def _auto_refresh_script(default_n: int) -> str:
    """自动刷新 JS: 读 URL ?refresh= 参数 (缺省 default_n), 设置选择器并定时 reload。

    0 = 关闭自动刷新。所有 board HTML 页面共用 (S10-110 刷新可选)。
    """
    return f"""
<script>
(function(){{
  var p = new URLSearchParams(location.search).get('refresh');
  var n = p ? parseInt(p, 10) : {default_n};
  var sel = document.getElementById('factory-refresh');
  if (sel) sel.value = String(n);
  if (n > 0) setInterval(function(){{ location.reload(); }}, n * 1000);
}})();
</script>"""


# ---------------------------------------------------------------- 项目优先首页 (S10-110 架构调整)

def render_project_home(workspace: Path | str) -> str:
    """项目优先首页 (Founder: 选择应该是第一步, 然后才是看面板)。

    未选/无当前项目 → 项目列表引导; 有当前项目 → 该项目的生命周期视图。
    主线面板 (AI Factory 自身进度) 降级为显式入口 (?view=mainline)。
    """
    current = _read_session_current_project(workspace)
    if current and (Path(workspace) / "projects" / current / "product.json").is_file():
        return render_project_lifecycle_html(workspace, current)
    return render_projects_list_html(workspace)


# ---------------------------------------------------------------- 生命线可读化 (S10-110 优化)

#: 审计事件类型 → 中文标签 (生命线展示; 未知类型显示原名)
EVENT_LABELS: dict[str, str] = {
    "DISCOVERY_CONFIRMED": "需求确认",
    "DISCOVERY_STARTED": "需求收集开始",
    "PRODUCT_CREATED": "产品创建",
    "PLAN_CREATED": "计划生成",
    "PLAN_UPDATED": "计划更新",
    "TASK_STARTED": "任务开始",
    "TASK_COMPLETED": "任务完成",
    "TASK_FAILED": "任务失败",
    "TASK_REPAIRED": "任务修复",
    "ARTIFACT_CREATED": "产物生成",
    "TEST_PASSED": "测试通过",
    "TEST_FAILED": "测试失败",
    "APPROVAL_REQUESTED": "审批请求",
    "APPROVAL_APPROVED": "审批通过",
    "APPROVAL_REJECTED": "审批拒绝",
    "EVIDENCE_CREATED": "证据生成",
    "EXECUTION_STARTED": "执行开始",
    "EXECUTION_COMPLETED": "执行完成",
    "EXECUTION_FAILED": "执行失败",
    "PROJECT_DELIVERED": "项目交付",
    "PROJECT_ARCHIVED": "项目归档",
}

#: 生命线聚合窗口 (秒) — 同窗口同类型同对象事件合并显示 ×N (降噪)
TIMELINE_AGGREGATE_SECONDS = 5


def _timeline_obj_name(workspace: Path | str, e: dict[str, Any]) -> str:
    """事件对象名: project_id → 项目名; task_id → 任务名; agent_id → 原样。失败安全。"""
    pid = str(e.get("project_id") or "")
    if pid:
        info = _read_product_info(workspace, pid)
        if info:
            return f"{info.get('name') or pid}"
        return pid
    tid = str(e.get("task_id") or "")
    if tid:
        return tid
    aid = str(e.get("agent_id") or "")
    if aid:
        return aid
    return ""


# ---------------------------------------------------------------- 项目汇报 (S10-110 方案 A)

def render_project_report(workspace: Path | str, slug: str) -> str:
    """项目汇报 (markdown, 给 Hermes/用户): 生命周期 + 任务状态 + 文档 + 最近事件。"""
    slug = Path(str(slug or "")).name
    info = _read_product_info(workspace, slug)
    if info is None:
        return f"（项目不存在: {slug}）"
    name = info.get("name") or slug
    stages = _project_stage_status(workspace, slug)
    done_count = sum(1 for st in stages if st["done"])
    total = len(stages)
    stage_txt = " → ".join(
        f"{st['label']}{'✅' if st['done'] else '○'}" for st in stages
    )
    counts = _project_task_status_counts(workspace, slug)
    pdir = Path(workspace) / "projects" / slug

    def has(n: str) -> str:
        return "✅" if (pdir / n).is_file() else "—"

    lines = [
        f"# 项目汇报: {name} ({slug})",
        "",
        f"## 生命周期 {done_count}/{total}",
        stage_txt,
        "",
        "## 任务状态",
        f"✅完成 {counts['done']} · 🔵进行中 {counts['running']} · "
        f"❌失败 {counts['failed']} · ⬜待办 {counts['pending']} · 共 {counts['total']}",
        "",
        "## 文档产物",
        f"PRD {has('PRD.md')} · 工程 {has('engineering.json')} · "
        f"任务 {has('tasks.json')} · 验证 {has('validation_result.json')}",
        "",
        "## 最近事件",
    ]
    t = render_timeline(workspace, limit=8, project_id=slug)
    lines.extend(
        f"- {ln.strip()}" for ln in t.splitlines()
        if ln.strip() and ln.strip() != "│"
        and not ln.strip().startswith(("⏱", "◉ 需求确认"))
    )
    return "\n".join(lines)
