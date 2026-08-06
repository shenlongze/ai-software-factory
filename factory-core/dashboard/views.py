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
_DONE = frozenset({
    "DONE", "SUCCESS", "COMPLETED", "PASS", "AVAILABLE", "OK", "RELEASED", "ACTIVE",
})
_RUNNING = frozenset({
    "RUNNING", "WORKING", "PENDING", "BACKLOG", "CREATED", "SKIP", "ARCHITECTURE",
    "DEVELOPMENT", "TESTING", "ASSIGNED",
})
_FAILED = frozenset({"FAILED", "FAIL", "ERROR", "OFFLINE", "BLOCKED", "DISABLED", "DEPRECATED"})

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


def build_catalog(snapshot: FactorySnapshot) -> Panel:
    """Runtime Catalog 视图: Available Runtime Definitions 表 (默认定义基线 +
    已注册定义, 只读; Phase 5A.1 / ADR-0014)。"""
    c = snapshot.catalog
    summary = _line(_text(f"{c.total} definitions", style="bold"))
    if c.by_type:
        summary.append("  ").append_text(
            Text("types ", style="dim")
        ).append_text(_status_counts_text(c.by_type))
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Definition", "Type", "Capabilities", "Version", "Status"):
        table.add_column(col)
    for d in c.items:
        table.add_row(
            _text(d.get("id", "")),
            _text(d.get("type", "")),
            _text(", ".join(d.get("capabilities", [])) or "-"),
            _text(d.get("version", "")),
            _text(d.get("status", ""), style=_style_status(d.get("status"))),
        )
    if not c.items:
        table.add_row(_text("(no definitions)", style="dim"), "", "", "", "")
    return _panel(Group(summary, table), "Runtime Catalog", border="cyan")


def build_provider(snapshot: FactorySnapshot) -> Panel:
    """Provider 目录视图 (Phase 8A, ADR-0022 + 8B-2 增强): 智能来源定义表
    (默认定义基线 + 已注册定义, 只读)。

    数据源 = snapshot.providers (collector include_provider=True 聚合, 默认
    关闭): 与 Runtime Catalog 语义平行 — Provider = 智能来源目录, Runtime =
    执行机制目录, 两者数据空间完全分离。Default 列以 ★ 标记默认 Provider
    (registry.default(); 未设置 → 无星标)。
    Phase 8B-2 (ADR-0024) 增强: 装配 usage_store 且存在使用记录时, 追加
    使用/成本/性能列 (Calls/Success/Cost — 估算计量, 非真实计费); 无 usage
    数据 → 列集合与 Phase 8A 逐位一致 (默认关, 零回归)。
    Phase 8B-3 (ADR-0025) 增强: 追加 Failure/AvgDur 列 + 综合推荐行
    (capability+cost+performance 三分数加权, 只展示不自动切换) — 仍只在
    存在 usage 数据时出现, 无数据逐位不变 (零回归)。
    """
    p = snapshot.providers
    summary = _line(_text(f"{p.total} providers", style="bold"))
    if p.by_type:
        summary.append("  ").append_text(
            Text("types ", style="dim")
        ).append_text(_status_counts_text(p.by_type))
    if p.default:
        summary.append("  ").append_text(
            Text(f"default {p.default}", style="bold cyan")
        )
    if p.usage_total_calls:
        summary.append("  ").append_text(
            Text(
                f"usage {p.usage_total_calls} calls, ${p.usage_total_cost:.4f} "
                f"({(p.usage_success_rate * 100):.1f}% success / "
                f"{(p.usage_failure_rate * 100):.1f}% failure, "
                f"{p.usage_avg_duration_ms:.0f}ms avg dur)",
                style="dim",
            )
        )
    if p.usage_recommended:
        summary.append("  ").append_text(
            Text(
                f"推荐 {p.usage_recommended} "
                f"(score {p.usage_recommended_score:.3f})",
                style="bold green",
            )
        )
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    columns = ["Provider", "Type", "Models", "Version", "Status", "Default"]
    if p.usage_total_calls:
        columns += ["Calls", "Success", "Failure", "Avg Dur", "Cost"]
    for col in columns:
        table.add_column(col)
    for d in p.items:
        is_default = p.default is not None and d.get("id") == p.default
        row = [
            _text(d.get("id", "")),
            _text(d.get("type", "")),
            _text(", ".join(d.get("models", [])) or "-"),
            _text(d.get("version", "")),
            _text(d.get("status", ""), style=_style_status(d.get("status"))),
            _text("★", style="bold cyan") if is_default else _text(""),
        ]
        if p.usage_total_calls:
            u = p.usage_by_provider.get(d.get("id", "")) or {}
            row += [
                _text(str(u.get("calls", 0))),
                _text(f"{(u.get('success_rate', 0.0) * 100):.0f}%" if u else "-"),
                _text(f"{(u.get('failure_rate', 0.0) * 100):.0f}%" if u else "-"),
                _text(f"{u.get('avg_duration_ms', 0.0):.0f}ms" if u else "-"),
                _text(f"{u.get('total_cost', 0.0):.4f}" if u else "-"),
            ]
        table.add_row(*row)
    if not p.items:
        table.add_row(
            _text("(no providers)", style="dim"),
            *([""] * (len(columns) - 1)),
        )
    return _panel(Group(summary, table), "Provider Catalog", border="cyan")


def build_projects(snapshot: FactorySnapshot) -> Panel:
    """Projects View (Phase 6A, ADR-0016): 每项目计数 + success rate。

    数据源 = snapshot.projects (DashboardCollector 只读聚合, 同 --json 出口):
    workspace 项目定义 ∪ 任务 project 值; 每项目任务数/工作流运行数/执行数/
    成功率。status 未知 (任务中出现但未定义) → 中性色。
    """
    p = snapshot.projects
    summary = _line(_text(f"{p.total} projects", style="bold"))
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Project", "Language", "Status", "Tasks", "Workflows", "Executions", "Success Rate"):
        table.add_column(col)
    for item in p.items:
        table.add_row(
            _text(item.id),
            _text(item.language or "-"),
            _text(item.status, style=_style_status(item.status)),
            _text(item.task_count),
            _text(item.workflow_count),
            _text(item.execution_count),
            _text(f"{item.success_rate:.1%}"),
        )
    if not p.items:
        table.add_row(_text("(no projects)", style="dim"), "", "", "", "", "", "")
    return _panel(Group(summary, table), "Projects", border="cyan")


def build_metrics(snapshot: FactorySnapshot) -> Panel:
    """Factory Metrics 视图 (Phase 5B, ADR-0015): 六域指标 + 失败原因直方图。

    数据源 = snapshot.factory_metrics (MetricsCollector 只读聚合, 同 --json 出口)。
    """
    m = snapshot.factory_metrics
    t, x, w, v = m.tasks, m.executions, m.workflows, m.validation

    header = _line(Text("Factory Metrics", style="bold cyan"))
    if m.project_id:
        header.append(f"  [{m.project_id}]", style="magenta")
    parts: list[Any] = [header]

    tasks = _line(
        Text("Tasks      ", style="bold"),
        _text(f"total {t.total}  completed {t.completed}  failed {t.failed}  "
              f"success_rate {t.success_rate:.1%}", style="dim"),
    )
    if t.by_status:
        tasks.append("  ").append_text(_status_counts_text(t.by_status))
    parts.append(tasks)

    execs = _line(
        Text("Executions ", style="bold"),
        _text(f"total {x.total}  success {x.success}  failed {x.failed}  "
              f"first_attempt_success_rate {x.first_attempt_success_rate:.1%}", style="dim"),
    )
    if x.by_status:
        execs.append("  ").append_text(_status_counts_text(x.by_status))
    parts.append(execs)

    parts.append(_line(
        Text("Workflows  ", style="bold"),
        _text(f"{w.run_count} runs  completed {w.completed}  failed {w.failed}  "
              f"success_rate {w.success_rate:.1%}  ({w.definitions} definitions)", style="dim"),
    ))
    parts.append(_line(
        Text("Validation ", style="bold"),
        _text(f"rules {v.total_rules}  PASS {v.pass_count}  FAIL {v.fail_count}  "
              f"SKIP {v.skip_count}  ERROR {v.error_count}  pass_rate {v.pass_rate:.1%}  "
              f"runs {v.runs}  failed_runs {v.failed_runs}", style="dim"),
    ))

    if m.agents:
        agent_table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
        for col in ("Agent", "Assignments", "Success", "Failed", "Rate"):
            agent_table.add_column(col)
        for agent_id, a in sorted(m.agents.items()):
            agent_table.add_row(
                _text(agent_id),
                _text(a.assignment_count),
                _text(a.success_count),
                _text(a.failed_count),
                _text(f"{a.success_rate:.1%}"),
            )
        parts.append(Group(
            _line(Text(f"Agents ({m.agents_total} registered)", style="bold")),
            agent_table,
        ))
    else:
        parts.append(_line(Text("Agents     ", style="bold"), _text("(no agents)", style="dim")))

    if m.failures.failure_reason_count:
        reason_table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
        for col in ("Reason", "Count"):
            reason_table.add_column(col)
        for reason, count in m.failures.failure_reason_count.items():
            reason_table.add_row(_text(reason), _text(count))
        parts.append(Group(Text("Failure Reasons", style="bold"), reason_table))
    else:
        parts.append(_line(Text("Failures    ", style="bold"), _text("(none)", style="dim")))

    return _panel(Group(*parts), "Factory Metrics", border="cyan")


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


# ------------------------------------------------------------------ Workspace 视图 (Phase 6B, ADR-0017)

def build_workspace(snapshot: FactorySnapshot) -> Group:
    """Workspace Summary 视图组 (dashboard --workspace 默认): 跨项目运营总览。

    组成: Workspace Summary 头面板 + Projects (项目对比) + Agent Utilization +
    Runtime Usage + Factory Metrics + Workspace Events 时间线 — 全部数据来自
    snapshot 只读投影 (collector workspace 模式聚合, ADR-0017 决策 3)。
    """
    return Group(
        build_workspace_header(snapshot),
        build_projects(snapshot),
        build_agent_utilization(snapshot),
        build_runtime_usage(snapshot),
        build_metrics(snapshot),
        build_workspace_events(snapshot),
    )


def build_workspace_header(snapshot: FactorySnapshot) -> Panel:
    """Workspace Summary 头面板: 跨项目六域一句话汇总 (同 build_header 风格)。"""
    title = Text("AI Software Factory Workspace", style="bold cyan")
    t, a, x, w, m = (
        snapshot.tasks, snapshot.agents, snapshot.executions,
        snapshot.workflows, snapshot.metrics,
    )
    p = snapshot.projects
    au = snapshot.agent_utilization
    ru = snapshot.runtime_usage
    body = Group(
        title,
        _line(Text("Projects    ", style="bold"), _text(f" {p.total}"),
              _text(f"  ({len(snapshot.recent_events)} recent events)", style="dim")),
        _line(Text("Tasks       ", style="bold"), _status_counts_text(t.by_status),
              _text(f"  (total {t.total}, active {t.active}, done {t.done})", style="dim")),
        _line(Text("Agents      ", style="bold"), _status_counts_text(a.by_status),
              _text(f"  (total {a.total}, utilized {au.total})", style="dim")),
        _line(Text("Executions  ", style="bold"), _status_counts_text(x.by_status),
              _text(f"  (total {x.total}, rate {x.success_rate:.1%}, runtimes {ru.total})", style="dim")),
        _line(Text("Workflows   ", style="bold"), _status_counts_text(w.runs_by_status),
              _text(f"  ({w.definitions} definitions)", style="dim")),
        _line(Text("Validation  ", style="bold"),
              _text(f" PASS {m.validation.pass_count} / FAIL {m.validation.fail_count} / "
                    f"SKIP {m.validation.skip_count}  (Events {m.event_count})", style="dim")),
    )
    return _panel(body, "Workspace Summary", border="cyan")


def build_agent_utilization(snapshot: FactorySnapshot) -> Panel:
    """Agent Utilization View (ADR-0017): 跨项目 Agent 使用统计表。

    数据源 = snapshot.agent_utilization (collector workspace 模式聚合):
    每 agent 参与项目 / 分配次数 / 成败 / 成功率。
    """
    au = snapshot.agent_utilization
    summary = _line(_text(f"{au.total} agents", style="bold"),
                    _text(f" · {sum(a.assignments for a in au.items)} assignments", style="bold"))
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Agent", "Role", "Status", "Projects", "Assignments", "Success", "Failed", "Success Rate"):
        table.add_column(col)
    for a in au.items:
        table.add_row(
            _text(a.agent_id),
            _text(a.role or "-"),
            _text(a.status or "-", style=_style_status(a.status)),
            _text(", ".join(a.projects) or "-"),
            _text(a.assignments),
            _text(a.success_count),
            _text(a.failed_count),
            _text(f"{a.success_rate:.1%}", style=_style_status("PASS" if a.success_rate >= 0.5 else "FAIL")),
        )
    if not au.items:
        table.add_row(_text("(no agents)", style="dim"), "", "", "", "", "", "", "")
    return _panel(Group(summary, table), "Agent Utilization", border="green")


def build_runtime_usage(snapshot: FactorySnapshot) -> Panel:
    """Runtime Usage View (ADR-0017): runtime/execution_count/success_rate 表。

    数据源 = snapshot.runtime_usage (collector workspace 模式聚合, execution
    记录请求状态为权威); projects = 使用该 runtime 的项目。
    """
    ru = snapshot.runtime_usage
    summary = _line(_text(f"{ru.total} runtimes", style="bold"),
                    _text(f" · {sum(r.execution_count for r in ru.items)} executions", style="bold"))
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Runtime", "Executions", "Success", "Failed", "Success Rate", "Projects"):
        table.add_column(col)
    for r in ru.items:
        table.add_row(
            _text(r.runtime_id),
            _text(r.execution_count),
            _text(r.success),
            _text(r.failed),
            _text(f"{r.success_rate:.1%}", style=_style_status("PASS" if r.success_rate >= 0.5 else "FAIL")),
            _text(", ".join(r.projects) or "-"),
        )
    if not ru.items:
        table.add_row(_text("(no executions)", style="dim"), "", "", "", "", "")
    return _panel(Group(summary, table), "Runtime Usage", border="yellow")


def build_workspace_events(snapshot: FactorySnapshot) -> Panel:
    """Workspace Events 时间线 (ADR-0017): 跨项目最近事件 (含 Project 列)。"""
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("seq", "timestamp", "type", "project", "task", "action", "result"):
        table.add_column(col)
    for e in snapshot.recent_events:
        table.add_row(
            _text(e.get("seq", "")),
            _text(str(e.get("timestamp", ""))[:19]),
            _text(e.get("type", "")),
            _text(e.get("project_id") or "-"),
            _text(e.get("task_id") or "-"),
            _text(e.get("action") or "-"),
            _text(e.get("result") or "-", style=_style_status(e.get("result"))),
        )
    if not snapshot.recent_events:
        table.add_row(_text("(no events)", style="dim"), "", "", "", "", "", "")
    return _panel(table, "Workspace Events", border="blue")


# ------------------------------------------------------------------ Git View (Phase 6C, ADR-0018)

def build_git(snapshot: FactorySnapshot) -> Panel:
    """Git View (Phase 6C, ADR-0018): Projects/Repositories/Changes/Commits。

    数据源 = snapshot.git (collector include_git=True 聚合, GitService 只读):
    Repositories 表 (每项目仓库上下文, 非 git 目录 → error 行照常展示 —
    失败安全), Changes 表 (跨项目工作区变更 + task 关联), Commits 表
    (跨项目最近提交, 按时间倒序)。
    """
    g = snapshot.git
    summary = _line(
        _text(f"{g.total} repositories", style="bold"),
        _text(f" · {len(g.changes)} changes · {len(g.commits)} commits", style="bold"),
    )
    repo_table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Project", "Repository", "Branch", "Commit", "Changes", "Error"):
        repo_table.add_column(col)
    for r in g.repos:
        repo_table.add_row(
            _text(r.project_id or "-"),
            _text(r.repository),
            _text(r.branch or "-", style=_style_status("RUNNING" if r.branch else None)),
            _text((r.current_commit or "(no commits)")[:12]),
            _text(len(r.changes)),
            _text(r.error or "-", style="red" if r.error else "dim"),
        )
    if not g.repos:
        repo_table.add_row(_text("(no repositories)", style="dim"), "", "", "", "", "")

    change_table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Repository", "File", "Status", "+", "-", "Task"):
        change_table.add_column(col)
    for c in g.changes:
        change_table.add_row(
            _text(c.repository),
            _text(", ".join(c.files)),
            _text(c.status, style=_style_status("RUNNING" if c.status != "deleted" else "FAILED")),
            _text(c.insertions),
            _text(c.deletions),
            _text(c.task_id or "-"),
        )
    if not g.changes:
        change_table.add_row(_text("(no changes)", style="dim"), "", "", "", "", "")

    commit_table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Hash", "Message", "Branch", "Task", "Date"):
        commit_table.add_column(col)
    for c in g.commits:
        commit_table.add_row(
            _text(c.hash[:12]),
            _text(c.message or "-"),
            _text(c.branch or "-"),
            _text(c.task_id or "-"),
            _text(str(c.created_at)[:19]),
        )
    if not g.commits:
        commit_table.add_row(_text("(no commits)", style="dim"), "", "", "", "")

    return _panel(Group(summary, repo_table, change_table, commit_table), "Git", border="green")


# ------------------------------------------------------------------ Change View (Phase 6D, ADR-0019)

def build_change(snapshot: FactorySnapshot) -> Panel:
    """Change View (Phase 6D, ADR-0019): Execution Git Snapshots + L4 验证。

    数据源 = snapshot.change (collector include_change=True 聚合, 默认关闭):
    Snapshots 表 (执行↔git 关联: before/after commit + 变更文件数, 旧执行记录
    无快照 → 空表), Validations 表 (change.validation.completed 事件: 最近 L4
    判定 task_id/status/message — 状态着色同 validation 语义)。
    """
    c = snapshot.change
    summary = _line(
        _text(f"{c.total} execution snapshots", style="bold"),
        _text(f" · {c.validation_total} validations", style="bold"),
    )
    snap_table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Execution", "Task", "Project", "Repository", "Before", "After", "Files"):
        snap_table.add_column(col)
    for s in c.snapshots:
        snap_table.add_row(
            _text(s.get("execution_id", "")),
            _text(s.get("task_id") or "-"),
            _text(s.get("project_id") or "-"),
            _text(s.get("repository") or "-"),
            _text((s.get("before_commit") or "(none)")[:12]),
            _text((s.get("after_commit") or "(none)")[:12]),
            _text(len(s.get("changed_files", []))),
        )
    if not c.snapshots:
        snap_table.add_row(_text("(no snapshots)", style="dim"), "", "", "", "", "", "")

    val_table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Task", "Status", "Message", "Seq"):
        val_table.add_column(col)
    for v in c.validations:
        val_table.add_row(
            _text(v.get("task_id", "")),
            _text(v.get("status", ""), style=_style_status(v.get("status"))),
            _text(v.get("message") or "-"),
            _text(v.get("seq", "")),
        )
    if not c.validations:
        val_table.add_row(_text("(no validations)", style="dim"), "", "", "")

    return _panel(Group(summary, snap_table, val_table), "Change", border="cyan")


# ------------------------------------------------------------------ Change Flow View (Phase 6E, ADR-0020)

def build_changeflow(snapshot: FactorySnapshot) -> Panel:
    """Change Flow View (Phase 6E, ADR-0020): Triggers + Evaluations + Links。

    数据源 = snapshot.changeflow (collector include_changeflow=True 聚合, 默认
    关闭): Triggers 表 (id/event_type/project/task_type/required_validation/
    target_workflow — 声明式驱动规则注册表), Evaluations 表
    (change.trigger.evaluated: 最近评估判定 task_id/status/trigger/rules 数/
    触发工作流/run_id/error — 状态着色同 validation 语义), Workflow Links 表
    (started/completed 配对: task/workflow/run/trigger/终态 result)。
    """
    c = snapshot.changeflow
    summary = _line(
        _text(f"{c.trigger_total} triggers", style="bold"),
        _text(f" · {c.evaluation_total} evaluations", style="bold"),
        _text(f" · {c.workflow_links_total} workflow links", style="bold"),
    )

    trigger_table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Trigger", "Event", "Project", "Task Type", "Validation", "Target Workflow"):
        trigger_table.add_column(col)
    for t in c.triggers:
        trigger_table.add_row(
            _text(t.get("id", "")),
            _text(t.get("event_type", "")),
            _text(t.get("project_id") or "-"),
            _text(t.get("task_type") or "-"),
            _text(t.get("required_validation", ""), style=_style_status(t.get("required_validation"))),
            _text(t.get("target_workflow", "")),
        )
    if not c.triggers:
        trigger_table.add_row(_text("(no triggers)", style="dim"), "", "", "", "", "")

    eval_table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Task", "Status", "Trigger", "Rules", "Workflow", "Run", "Error"):
        eval_table.add_column(col)
    for v in c.evaluations:
        eval_table.add_row(
            _text(v.get("task_id", "")),
            _text(v.get("status", ""), style=_style_status(v.get("status"))),
            _text(v.get("trigger_id") or "-"),
            _text(v.get("rules", 0)),
            _text(v.get("triggered_workflow") or "-"),
            _text(v.get("run_id") or "-"),
            _text((v.get("error") or "-")[:40]),
        )
    if not c.evaluations:
        eval_table.add_row(_text("(no evaluations)", style="dim"), "", "", "", "", "", "")

    link_table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Task", "Workflow", "Run", "Trigger", "Result"):
        link_table.add_column(col)
    for lk in c.workflow_links:
        link_table.add_row(
            _text(lk.get("task_id", "")),
            _text(lk.get("workflow_id", "")),
            _text(lk.get("run_id") or "-"),
            _text(lk.get("trigger_id") or "-"),
            _text(lk.get("status", ""), style=_style_status(lk.get("status"))),
        )
    if not c.workflow_links:
        link_table.add_row(_text("(no workflow links)", style="dim"), "", "", "", "")

    return _panel(Group(summary, trigger_table, eval_table, link_table), "Change Flow", border="cyan")


# ------------------------------------------------------------------ Understanding View (Phase 7, ADR-0021)

def _style_confidence(confidence: float) -> str:
    """置信度 → 颜色 (0.8+ 绿 / 0.6+ 黄 / 其余红)。"""
    if confidence >= 0.8:
        return "green"
    if confidence >= 0.6:
        return "yellow"
    return "red"


def build_understanding(snapshot: FactorySnapshot) -> Panel:
    """Understanding View (Phase 7, ADR-0021): 项目阶段 + 置信度 + 缺失产物。

    数据源 = snapshot.understanding (collector include_understanding=True 聚合,
    默认关闭): Projects 表 (每项目 path/stage/confidence/present/missing —
    阶段着色同 validation 语义, 置信度按强度着色), 每行对应一次只读理解分析
    (UnderstandingService, 规则推断禁 LLM)。
    """
    u = snapshot.understanding
    summary = _line(
        _text(f"{u.total} projects analyzed", style="bold"),
        _text(" · Understanding = 只读规则分析 (禁 LLM)", style="dim"),
    )
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Project", "Path", "Stage", "Confidence", "Present", "Missing"):
        table.add_column(col)
    for item in u.items:
        table.add_row(
            _text(item.project),
            _text(item.path),
            _text(item.stage, style=_style_status(item.stage)),
            _text(f"{item.confidence:.2f}", style=_style_confidence(item.confidence)),
            _text(", ".join(item.present) or "-"),
            _text(", ".join(item.missing) or "-"),
        )
    if not u.items:
        table.add_row(_text("(no projects analyzed)", style="dim"), "", "", "", "", "")

    return _panel(Group(summary, table), "Understanding", border="magenta")


# ------------------------------------------------------------------ Product View (Phase 9A, ADR-0026)

def build_product(snapshot: FactorySnapshot) -> Panel:
    """Product Intelligence View (Phase 9A, ADR-0026): Idea/Artifact/Approval/Workflow。

    数据源 = snapshot.product (collector include_product=True 聚合, 默认关闭):
    Ideas 表 (ProductIdea — Idea 即 Artifact 约定), Approvals 表
    (ApprovalRequest: 任何 Artifact 可申请, 状态 pending/approved/denied 着色),
    Workflows 表 (ProductWorkflow 骨架: running/awaiting_approval —
    awaiting_approval 即审批门暂停, yellow 强调)。Summary 行含 Artifact 抽象
    全类型计数 (含 product_decision — Approval Gate 闭环产物)。
    """
    p = snapshot.product
    summary = _line(
        _text(f"{p.idea_total} ideas", style="bold"),
        _text(f" · {p.artifact_total} artifacts", style="bold"),
    )
    if p.artifact_total:
        summary.append("  ").append_text(_status_counts_text(p.artifacts_by_type))
    summary.append("  ").append_text(_line(
        Text(f"{p.product_decisions} product decisions", style="bold"),
    ))
    summary.append("  ").append_text(_line(
        Text(
            f"approvals {p.approval_pending} pending / {p.approval_approved} approved / "
            f"{p.approval_denied} denied",
            style="dim",
        ),
    ))
    summary.append("  ").append_text(_line(
        Text(f"workflows {p.workflow_total}", style="bold"),
    ))
    if p.workflows_by_status:
        summary.append("  ").append_text(_status_counts_text(p.workflows_by_status))

    idea_table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Idea", "Title", "Status", "Goals", "Created"):
        idea_table.add_column(col)
    for i in p.ideas:
        idea_table.add_row(
            _text(i.get("id", "")),
            _text(i.get("title", "")),
            _text(i.get("status", ""), style=_style_status(i.get("status"))),
            _text(", ".join(i.get("goals", [])) or "-"),
            _text(str(i.get("created_at", ""))[:19]),
        )
    if not p.ideas:
        idea_table.add_row(_text("(no ideas)", style="dim"), "", "", "", "")

    approval_table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Request", "Artifact", "Gate", "Status", "Idea", "By"):
        approval_table.add_column(col)
    for a in p.approvals:
        approval_table.add_row(
            _text(a.get("id", "")),
            _text(a.get("artifact_id", "")),
            _text(a.get("gate", "")),
            _text(a.get("status", ""), style=_style_status(a.get("status"))),
            _text(a.get("idea_id") or "-"),
            _text(a.get("by") or "-"),
        )
    if not p.approvals:
        approval_table.add_row(_text("(no approvals)", style="dim"), "", "", "", "", "")

    workflow_table = Table(show_header=True, header_style="bold", box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Workflow", "Idea", "Status", "Current Stage", "Stages", "Product Decision"):
        workflow_table.add_column(col)
    for w in p.workflows:
        workflow_table.add_row(
            _text(w.get("id", "")),
            _text(w.get("idea_id", "")),
            _text(w.get("status", ""), style=_style_status(w.get("status"))),
            _text(w.get("current_stage") or "-"),
            _text(" → ".join(w.get("stages", [])) or "-"),
            _text(w.get("product_decision") or "-"),
        )
    if not p.workflows:
        workflow_table.add_row(_text("(no workflows)", style="dim"), "", "", "", "", "")

    return _panel(
        Group(summary, idea_table, approval_table, workflow_table),
        "Product Intelligence",
        border="cyan",
    )
