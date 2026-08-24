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
