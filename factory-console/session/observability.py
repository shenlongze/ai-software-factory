"""factory-console/session/observability.py — Execution Observability (S10-083 P0)。

Execution Timeline / Project Status 视图。
数据全部来自真实执行事件存储:
- exec/execution_records.json  (每次执行: intent/action/agent/task/result/timestamp)
- exec/artifacts.json          (产物注册: 类型/agent/路径/created_at)
- exec/*.report.md             (usage: tokens/cost — 真实 LLM 用量)
- audit/audit_events.json      (审计事件链)

禁止补造事件 — 展示 = 存储聚合。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 缺失/损坏 → 空 (失败安全)
        return {}


def _load_records(exec_dir: Path) -> list[dict]:
    data = _load_json(exec_dir / "execution_records.json")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("records", "executions"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def _load_artifacts(exec_dir: Path) -> list[dict]:
    data = _load_json(exec_dir / "artifacts.json")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        arts = data.get("artifacts", {})
        if isinstance(arts, dict):
            return list(arts.values())
        if isinstance(arts, list):
            return arts
    return []


_USAGE_RE = re.compile(r"total_tokens['\"]?\s*:\s*(\d+)")
_COST_RE = re.compile(r"estimated_cost_usd['\"]?\s*:\s*([\d.eE+-]+)")


def _report_usage(exec_dir: Path, result_id: str) -> dict:
    """从 report.md 提取真实 usage (tokens/cost); 无 report → 空 (不伪造)。"""
    report = exec_dir / f"{result_id}.report.md"
    if not report.is_file():
        return {}
    try:
        text = report.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return {}
    tokens = _USAGE_RE.search(text)
    cost = _COST_RE.search(text)
    return {
        "tokens": int(tokens.group(1)) if tokens else None,
        "cost_usd": float(cost.group(1)) if cost else None,
    }


def execution_timeline(workspace: Path, *, project_id: str = "", limit: int = 20) -> list[dict]:
    """执行时间线 (真实事件, 时间正序, 最新在前)。

    聚合: execution_records (每次执行) + report usage (tokens/cost)。
    """
    exec_dir = workspace / "exec"
    records = _load_records(exec_dir)
    if project_id:
        # 记录本身无 project 字段 → 按 result_id 关联 artifacts 无果时用目录名过滤
        # (project 目录 = result 文件前缀; 简化: 全部展示, 标注)
        pass
    events: list[dict] = []
    for rec in records:
        rid = str(rec.get("result_id") or "")
        usage = _report_usage(exec_dir, rid) if rid else {}
        events.append({
            "timestamp": str(rec.get("timestamp") or ""),
            "agent": str(rec.get("agent") or ""),
            "action": str(rec.get("action") or ""),
            "task": str(rec.get("task") or ""),
            "intent": str(rec.get("intent") or ""),
            "result": str(rec.get("result") or ""),
            "result_id": rid,
            "tokens": usage.get("tokens"),
            "cost_usd": usage.get("cost_usd"),
        })
    events.sort(key=lambda e: e["timestamp"], reverse=True)
    # 去重: 同一任务的初次执行 + 重试 (retry_count) 是两条展示记录 → 只保留最新一次
    # (完整重试历史在 execution_state.json; 时间线给用户看"每个任务当前状态")
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict] = []
    for e in events:
        key = (
            str(e.get("agent") or ""),
            str(e.get("action") or ""),
            str(e.get("task") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped[:limit]


def project_status(workspace: Path, project_dir: Path) -> dict:
    """项目状态视图: 阶段/任务/产物/最近事件/代码文件 (真实数据)。"""
    name = project_dir.name
    # lifecycle
    lifecycle = ""
    project_json = project_dir / "project.json"
    if project_json.is_file():
        data = _load_json(project_json)
        lifecycle = str(data.get("status") or data.get("lifecycle") or "")
    # tasks
    tasks: list[dict] = []
    state_file = project_dir / "execution_state.json"
    if state_file.is_file():
        state = _load_json(state_file)
        for t in state.get("tasks", []):
            tasks.append({
                "id": str(t.get("id") or ""),
                "name": str(t.get("name") or ""),
                "agent": str(t.get("agent") or ""),
                "status": str(t.get("status") or ""),
                "applied": bool(t.get("applied")),
                "code_files": int(t.get("code_files") or 0),
                "error": str(t.get("error") or ""),
            })
    # artifacts (exec 层产物注册)
    artifacts = _load_artifacts(project_dir.parent.parent / "exec")
    proj_artifacts = [a for a in artifacts if str(a.get("path") or "").find(name) >= 0]
    # code files
    code_count = 0
    for p in project_dir.rglob("*"):
        if p.is_file() and p.suffix in (".py", ".js", ".ts", ".java", ".go", ".rs", ".dart", ".kt", ".cpp"):
            code_count += 1
    # recent timeline
    recent = execution_timeline(project_dir.parent.parent, limit=8)
    return {
        "project": name,
        "lifecycle": lifecycle,
        "tasks_total": len(tasks),
        "tasks_completed": sum(1 for t in tasks if t["status"] == "completed"),
        "tasks_failed": sum(1 for t in tasks if t["status"] == "failed"),
        "code_files": code_count,
        "artifacts": len(proj_artifacts),
        "tasks": tasks,
        "recent_events": recent,
    }


def format_timeline(events: list[dict], *, limit: int = 20) -> str:
    """用户可理解的时间线展示 (时间/谁/做了什么/结果/token/cost)。"""
    if not events:
        return "暂无执行记录 (首次执行后可见)"
    lines = [f"执行历史 (共显示 {len(events)} 条, 最新在前):"]
    for e in events:
        ts = (e.get("timestamp") or "")[:19].replace("T", " ")
        agent = e.get("agent") or "-"
        action = e.get("action") or e.get("intent") or "-"
        task = (e.get("task") or "")[:24]
        result = e.get("result") or ""
        mark = "✅" if result == "success" else "❌"
        usage = ""
        if e.get("tokens") or e.get("cost_usd") is not None:
            usage = f" | tokens={e.get('tokens')} cost=${e.get('cost_usd')}"
        lines.append(
            f"  {mark} {ts} [{agent}] {action} {task}{usage}"
        )
    return "\n".join(lines)


def format_status(status: dict) -> str:
    """用户可理解的项目状态 (阶段/任务/代码/最近事件)。"""
    lines = [
        f"项目: {status['project']}",
        f"阶段: {status['lifecycle'] or '(未知)'}",
        f"任务: {status['tasks_completed']}/{status['tasks_total']} 完成"
        + (f", {status['tasks_failed']} 失败" if status['tasks_failed'] else ""),
        f"代码文件: {status['code_files']}",
        f"产物: {status['artifacts']}",
    ]
    if status["tasks"]:
        lines.append("任务明细:")
        for t in status["tasks"][:10]:
            mark = {"completed": "✅", "failed": "❌", "running": "⏳"}.get(t["status"], "⬜")
            applied = " applied" if t["applied"] else ""
            err = f" — {t['error'][:60]}" if t.get("error") else ""
            lines.append(f"  {mark} {t['name'][:28]} [{t['agent']}] {t['status']}{applied}{err}")
    if status["recent_events"]:
        lines.append("最近执行:")
        lines.append(format_timeline(status["recent_events"]))
    return "\n".join(lines)
