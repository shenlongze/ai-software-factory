"""metrics/reports.py — 指标报告输出 (纯文本/对齐表格, 无 ANSI)。

设计依据:
- phase5b-status.md: 报告输出 (文本/表格)
- ADR-0015 决策 6: 渲染为纯文本 (无转义码), 管道/CI/测试断言安全;
  format_metrics 为「FactoryMetrics → str」纯函数, CLI _print_metrics 与测试共用。

表格对齐复用 cli/main.py _render_table 同款算法 (KISS, 标准库零依赖)。
"""

from __future__ import annotations

from typing import Any

from .models import FactoryMetrics


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    """对齐表格文本行 (无表头时返回空)。"""
    if not rows:
        return []
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    lines = [
        "  " + "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)),
        "  " + "  ".join("-" * widths[i] for i in range(len(headers))),
    ]
    lines += ["  " + "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)) for row in rows]
    return lines


def format_metrics(metrics: FactoryMetrics) -> str:
    """FactoryMetrics → 文本报告 (六域 + 失败原因直方图)。"""
    t, x, w, v = metrics.tasks, metrics.executions, metrics.workflows, metrics.validation
    lines: list[str] = ["Factory Metrics"]
    if metrics.project_id:
        lines.append(f"  project   {metrics.project_id}")
    lines += ["", "Tasks"]
    lines += _table(
        ["total", "completed", "failed", "success_rate", "by_status"],
        [[t.total, t.completed, t.failed, f"{t.success_rate:.1%}", _kv(t.by_status)]],
    )
    lines += ["", "Executions"]
    lines += _table(
        ["total", "success", "failed", "first_attempt_success_rate", "by_status"],
        [[x.total, x.success, x.failed, f"{x.first_attempt_success_rate:.1%}", _kv(x.by_status)]],
    )
    lines += ["", "Agents"]
    agent_rows = [
        [agent_id, a.assignment_count, a.success_count, a.failed_count, f"{a.success_rate:.1%}"]
        for agent_id, a in sorted(metrics.agents.items())
    ]
    lines += _table(["agent", "assignments", "success", "failed", "success_rate"], agent_rows)
    lines.append(f"  registered agents: {metrics.agents_total}")
    lines += ["", "Workflows"]
    lines += _table(
        ["run_count", "completed", "failed", "success_rate", "definitions", "by_status"],
        [[w.run_count, w.completed, w.failed, f"{w.success_rate:.1%}", w.definitions, _kv(w.by_status)]],
    )
    lines += ["", "Validation"]
    lines += _table(
        ["rules", "PASS", "FAIL", "SKIP", "ERROR", "pass_rate", "runs", "failed_runs"],
        [[v.total_rules, v.pass_count, v.fail_count, v.skip_count, v.error_count,
          f"{v.pass_rate:.1%}", v.runs, v.failed_runs]],
    )
    lines += ["", "Failure Reasons"]
    reason_rows = [[reason, count] for reason, count in metrics.failures.failure_reason_count.items()]
    lines += _table(["reason", "count"], reason_rows)
    if not reason_rows:
        lines.append("  (none)")
    return "\n".join(lines)


def format_workspace_comparison(comparison) -> str:
    """WorkspaceComparison → 项目对比文本报告 (Phase 6B, ADR-0017)。

    与 format_metrics 同为「模型 → str」纯函数, CLI 与测试共用; 无 ANSI,
    管道/CI/测试断言安全。表格列: Project/Tasks/Executions/Workflows/Validation。
    """
    from .models import WorkspaceComparison

    assert isinstance(comparison, WorkspaceComparison)
    lines = ["Workspace Metrics", f"  projects  {comparison.total}"]
    lines += ["", "Project Comparison"]
    headers = [
        "project", "tasks", "done", "failed", "task_rate",
        "executions", "success", "failed", "exec_rate",
        "workflow_runs", "wf_rate", "validation_rules", "val_rate",
    ]
    rows = [
        [
            p.project, p.tasks_total, p.tasks_completed, p.tasks_failed,
            f"{p.task_success_rate:.1%}", p.execution_count, p.execution_success,
            p.execution_failed, f"{p.execution_success_rate:.1%}",
            p.workflow_runs, f"{p.workflow_success_rate:.1%}",
            p.validation_rules, f"{p.validation_pass_rate:.1%}",
        ]
        for p in comparison.projects
    ]
    lines += _table(headers, rows)
    if not rows:
        lines.append("  (no projects)")
    t = comparison.totals
    lines += ["", "Totals (all projects)"]
    lines += _table(
        headers,
        [[
            t.project, t.tasks_total, t.tasks_completed, t.tasks_failed,
            f"{t.task_success_rate:.1%}", t.execution_count, t.execution_success,
            t.execution_failed, f"{t.execution_success_rate:.1%}",
            t.workflow_runs, f"{t.workflow_success_rate:.1%}",
            t.validation_rules, f"{t.validation_pass_rate:.1%}",
        ]],
    )
    return "\n".join(lines)


def _kv(d: dict[str, int]) -> str:
    """'STATUS n | STATUS n' 紧凑计数段; 空 → '-'. """
    return " | ".join(f"{k} {d[k]}" for k in sorted(d)) if d else "-"
