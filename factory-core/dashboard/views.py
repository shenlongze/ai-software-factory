"""dashboard/views.py — 各视图构建 (纯函数: Snapshot → Rich renderable)。

设计依据:
- dashboard-design.md §2: 视图规格 (本项目落地六视图: Overview/Tasks/Agents/
  Workflows/Executions/Recovery, phase4c4-status.md 范围)
- 颜色语义 (dashboard-design.md §1.4): done/ok=绿, running=黄, blocked/failed=红
- 只读投影: 视图 = "查询结果 → Rich 组件" 纯函数, 无状态无副作用; CLI 与测试
  共用同一组构建函数 (dashboard-design.md §6.2 查询函数共享)。

所有动态单元格一律包 Text() — 避免 Rich markup 解释 (id 含 [] 等字符时安全)。
"""

from __future__ import annotations

from typing import Any

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import FactorySnapshot

# 状态 → 颜色 (dashboard-design.md §1.4 颜色语义)
_DONE = frozenset({"DONE", "SUCCESS", "COMPLETED", "PASS", "AVAILABLE", "OK", "RELEASED"})
_RUNNING = frozenset({
    "RUNNING", "WORKING", "PENDING", "BACKLOG", "CREATED", "SKIP", "ARCHITECTURE",
    "DEVELOPMENT", "TESTING", "ASSIGNED",
})
_FAILED = frozenset({"FAILED", "FAIL", "ERROR", "OFFLINE", "BLOCKED", "DISABLED"})

_COLOR_DONE = "green"
_COLOR_RUNNING = "yellow"
_COLOR_FAILED = "red"
_COLOR_NEUTRAL = "white"


def _style_status(status: str | None) -> str:
    """状态 → Rich 颜色 (未识别归中性色)。"""
    up = (status or "").upper()
    if up in _DONE:
        return _COLOR_DONE
    if up in _RUNNING:
        return _COLOR_RUNNING
    if up in _FAILED:
        return _COLOR_FAILED
    return _COLOR_NEUTRAL


def _text(value: Any, *, style: str | None = None) -> Text:
    return Text(str(value)) if style is None else Text(str(value), style=style)


def _line(*segments: Any) -> Text:
    """拼接一段文本行: Text 对象直接续接, 其他值 str() 化 (markup 安全)。"""
    t = Text()
    for seg in segments:
        t.append_text(seg) if isinstance(seg, Text) else t.append(str(seg))
    return t


def _status_counts_text(counts: dict[str, int]) -> Text:
    """'STATUS n | STATUS n' 形式计数段 (状态着色)。空 → '(none)'。"""
    t = Text()
    if not counts:
        t.append("(none)", style="dim")
        return t
    first = True
    for status in sorted(counts):
        if not first:
            t.append("  ")
        first = False
        t.append(f"{status} ", style=_style_status(status))
        t.append(str(counts[status]), style="bold")
    return t


def _kv_summary(d: dict[str, str]) -> str:
    """{id: 状态} 摘要: 'A-001=WORKING, A-002=AVAILABLE'; 空 → '-'. """
    return ", ".join(f"{k}={v}" for k, v in sorted(d.items())) or "-"


def _panel(renderable: Any, title: str, *, border: str = "blue") -> Panel:
    return Panel(renderable, title=title, border_style=border)


# ------------------------------------------------------------------ 视图构建

def build_header(snapshot: FactorySnapshot) -> Panel:
    """顶部 Overview 总览 Panel: 六域一句话汇总 (phase4c4-status 示例输出风格)。"""
    title = Text("AI Software Factory", style="bold cyan")
    if snapshot.project_id:
        title.append(f"  [{snapshot.project_id}]", style="magenta")
    t, a, w, x, c, m = (
        snapshot.tasks, snapshot.agents, snapshot.workflows,
        snapshot.executions, snapshot.checkpoints, snapshot.metrics,
    )
    body = Group(
        title,  # 标题行 (冒烟/测试断言 "AI Software Factory"); panel 标题仍为 "Overview"
        _line(Text("Tasks      ", style="bold"), _status_counts_text(t.by_status),
              _text(f"  (total {t.total}, active {t.active}, done {t.done})", style="dim")),
        _line(Text("Agents     ", style="bold"), _status_counts_text(a.by_status),
              _text(f"  (total {a.total})", style="dim")),
        _line(Text("Executions ", style="bold"), _status_counts_text(x.by_status),
              _text(f"  (total {x.total}, rate {x.success_rate:.1%})", style="dim")),
        _line(Text("Workflows  ", style="bold"), _status_counts_text(w.runs_by_status),
              _text(f"  ({w.definitions} definitions)", style="dim")),
        _line(Text("Checkpoints", style="bold"), _text(f" {c.total}"),
              _text(f"  Events {m.event_count}  Validation PASS {m.validation.pass_count} / "
                    f"FAIL {m.validation.fail_count} / SKIP {m.validation.skip_count}",
                    style="dim")),
    )
    return _panel(body, "Overview", border="cyan")


def build_recent_events(snapshot: FactorySnapshot, *, limit: int = 10) -> Panel:
    """最近事件表 (最近优先, 上限 limit)。"""
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("seq", "timestamp", "type", "task", "action", "result"):
        table.add_column(col)
    for e in snapshot.recent_events[:limit]:
        table.add_row(
            _text(e.get("seq", "")),
            _text(str(e.get("timestamp", ""))[:19]),
            _text(e.get("type", "")),
            _text(e.get("task_id") or "-"),
            _text(e.get("action") or "-"),
            _text(e.get("result") or "-", style=_style_status(e.get("result"))),
        )
    if not snapshot.recent_events:
        table.add_row(_text("(no events)", style="dim"), "", "", "", "", "")
    return _panel(table, "Recent Events", border="blue")


def build_tasks(snapshot: FactorySnapshot) -> Panel:
    """Task 列表视图 (每任务一行)。"""
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Task", "Status", "Project", "Type", "Title", "Owner"):
        table.add_column(col)
    for t in snapshot.tasks.items:
        table.add_row(
            _text(t.get("id", "")),
            _text(t.get("status", ""), style=_style_status(t.get("status"))),
            _text(t.get("project", "")),
            _text(t.get("type", "")),
            _text(t.get("title", "")),
            _text(t.get("owner") or "-"),
        )
    if not snapshot.tasks.items:
        table.add_row(_text("(no tasks)", style="dim"), "", "", "", "", "")
    return _panel(table, "Tasks", border="green")


def build_agents(snapshot: FactorySnapshot) -> Panel:
    """Agent 面板视图。"""
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Agent", "Role", "Status", "Current Task", "Skills"):
        table.add_column(col)
    for a in snapshot.agents.items:
        table.add_row(
            _text(a.get("id", "")),
            _text(a.get("role", "")),
            _text(a.get("status", ""), style=_style_status(a.get("status"))),
            _text(a.get("current_task") or "-"),
            _text(", ".join(a.get("skills", [])) or "-"),
        )
    if not snapshot.agents.items:
        table.add_row(_text("(no agents)", style="dim"), "", "", "", "")
    return _panel(table, "Agents", border="green")


def build_workflows(snapshot: FactorySnapshot) -> Panel:
    """工作流视图: 定义数 + 运行实例表。"""
    w = snapshot.workflows
    summary = _line(_text(f"{w.definitions} definitions", style="bold"),
                    _text(f" · {w.runs_total} runs", style="bold"))
    if w.runs_by_status:
        summary.append("  ").append_text(_status_counts_text(w.runs_by_status))
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Run", "Workflow", "Task", "Status", "Current Step"):
        table.add_column(col)
    for r in w.runs_items:
        wf_name = r.get("workflow_name") or r.get("workflow_id") or "-"
        table.add_row(
            _text(r.get("run_id", "")),
            _text(wf_name),
            _text(r.get("task_id", "")),
            _text(r.get("status", ""), style=_style_status(r.get("status"))),
            _text(r.get("current_step") or "-"),
        )
    if not w.runs_items:
        table.add_row(_text("(no runs)", style="dim"), "", "", "", "")
    return _panel(Group(summary, table), "Workflows", border="magenta")


def build_executions(snapshot: FactorySnapshot) -> Panel:
    """执行记录视图 (请求 + 结果联表)。"""
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Execution", "Task", "Runtime", "Status", "Result"):
        table.add_column(col)
    for x in snapshot.executions.items:
        res = x.get("result")
        res_status = (res or {}).get("status") if isinstance(res, dict) else None
        table.add_row(
            _text(x.get("id", "")),
            _text(x.get("task_id", "")),
            _text(x.get("runtime_id") or "-"),
            _text(x.get("status", ""), style=_style_status(x.get("status"))),
            _text(res_status or "-", style=_style_status(res_status)),
        )
    if not snapshot.executions.items:
        table.add_row(_text("(no executions)", style="dim"), "", "", "", "")
    return _panel(table, "Executions", border="yellow")


def build_recovery(snapshot: FactorySnapshot) -> Panel:
    """恢复视图: recovery 事件计数 + Checkpoint 快照表。"""
    m = snapshot.metrics
    counts = _line(
        Text("recovery events", style="bold"),
        _text(f" started {m.recovery_started}  completed {m.recovery_completed}  failed {m.recovery_failed}"),
    )
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Checkpoint", "Task", "Event Seq", "Current Step", "Agents", "Executions"):
        table.add_column(col)
    for c in snapshot.checkpoints.items:
        agents = c.get("agents") or {}
        executions = c.get("executions") or {}
        table.add_row(
            _text(c.get("id", "")),
            _text(c.get("task_id", "")),
            _text(c.get("event_seq", 0)),
            _text(c.get("current_step") or "-"),
            _text(_kv_summary(agents)),
            _text(_kv_summary(executions)),
        )
    if not snapshot.checkpoints.items:
        table.add_row(_text("(no checkpoints)", style="dim"), "", "", "", "", "")
    return _panel(Group(counts, table), "Recovery", border="red")
