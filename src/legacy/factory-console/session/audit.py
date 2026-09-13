"""factory-console/session/audit.py — 执行审计记录 (S10-049 P5) + Production Trace (S10-055 Task 007)。

Agent 执行审计 (最小): 每次 agent.execute_task 执行结果 append 到
~/.factory/exec/execution_records.json (workspace 缺省即 data_dir)。

- record_execution(record) — append 一条记录 (原子写: tmp + os.replace;
  目录不存在自动创建; 失败安全 — 审计失败不阻断主流程)
- load_records() — 读回全部记录 (缺文件/损坏 → [], 失败安全)

记录字段 (设计 §2.6): intent/action/agent/task/result/result_id/timestamp
(+ error 失败详情) — 未来 audit/cost/replay 数据源。

ProductionTrace (S10-055 Task 007, 验收 H): Project→Feature→Task→Agent→
Artifact→Validation→Cost 完整生产审计链:
- build(project_dir, workspace) — 从 execution_state.json (任务/agent/artifact/
  status/validation) + validation_result.json (验证汇总) + execution_records.json
  (成本) 构建 → production_trace.json 内容
- save(project_dir, trace) — production_trace.json 落盘 (项目目录)
- write_production_trace(project_dir, workspace) — build + save 一步完成

设计: docs/sprint10/S10-055-workforce-design.md §2/§3/§4
边界:
- 只做追加式审计/只读聚合, 不复制/不执行业务 (执行仍由 Action 负责)
- 纯标准库 (json/os/pathlib/re), 零新依赖
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

#: 默认审计记录文件 (~/.factory/exec/execution_records.json — workspace 缺省 = data_dir)
DEFAULT_RECORDS_FILE = Path.home() / ".factory" / "exec" / "execution_records.json"


def record_execution(record: dict, records_file: Optional[Path] = None) -> None:
    """append 一条执行记录 (原子写; 目录不存在创建; 失败安全 — 审计不阻断执行)。

    records_file 可注入 (测试/隔离工作区); 缺省 → ~/.factory/exec/execution_records.json。
    """
    try:
        path = Path(records_file) if records_file is not None else DEFAULT_RECORDS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        records = load_records(path)
        records.append(record)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001 — 失败安全: 审计失败不影响主流程
        return


def load_records(records_file: Optional[Path] = None) -> list[dict]:
    """读回全部执行记录; 缺文件/损坏/非列表 → [] (失败安全, 永不抛)。"""
    path = Path(records_file) if records_file is not None else DEFAULT_RECORDS_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001 — 失败安全
        return []


def _trace_cost(record: dict[str, Any]) -> float:
    """记录 cost 字段 → float (缺失/非数字 → 0.0, 失败安全)。

    cost 可能是 "0.0012" 或摘要 "0.5 · 320 tokens" — 取第一个数字 token。
    """
    value = record.get("cost")
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):  # noqa: BLE001 — 失败安全
            return 0.0
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    if not match:
        return 0.0
    try:
        return float(match.group())
    except (TypeError, ValueError):  # noqa: BLE001 — 失败安全
        return 0.0


class ProductionTrace:
    """完整生产审计链 (S10-055 Task 007, 验收 H): Project→Feature→Task→Agent→
    Artifact→Validation→Cost。

    build(project_dir, workspace) — 只读聚合:
    - 项目: project.json name / 目录名 slug
    - 功能: 按 execution_state.json task.feature 分组 (无 feature → "未分组")
    - 任务: {id, name, agent, status, artifact, validation, cost} — cost 从
      execution_records.json 按任务名匹配 (无 → 0.0)
    - 验证: validation_result.json 汇总 {success, tests_total, tests_passed,
      tests_failed, errors}
    - 汇总: tasks_total / tasks_completed / agents / cost_total
    失败安全: 任一数据源缺失/损坏 → 对应零值, 不抛。

    save(project_dir, trace) — production_trace.json 落盘 (项目目录, 中文可读)。
    """

    TRACE_FILE = "production_trace.json"
    UNGROUPED_FEATURE = "未分组"

    @classmethod
    def build(
        cls,
        project_dir: Path,
        workspace: Optional[Path] = None,
    ) -> dict[str, Any]:
        """项目目录 (+ 可选工作区) → 生产审计链 dict (失败安全, 不抛)。"""
        project_dir = Path(project_dir)
        slug = project_dir.name
        name = slug
        project_file = project_dir / "project.json"
        if project_file.is_file():
            try:
                data = json.loads(project_file.read_text(encoding="utf-8"))
                name = str(data.get("name") or slug)
            except Exception:  # noqa: BLE001 — 失败安全
                name = slug
        # ① execution_state.json → 任务/agent/artifact/status/validation
        tasks: list[dict[str, Any]] = []
        state_file = project_dir / "execution_state.json"
        if state_file.is_file():
            try:
                state = json.loads(state_file.read_text(encoding="utf-8"))
                tasks = list(state.get("tasks") or [])
            except Exception:  # noqa: BLE001 — 失败安全: 损坏 → 空任务
                tasks = []
        # ② execution_records.json → 成本 (按任务名匹配; workspace 缺省 → 默认文件)
        records_file = (
            Path(workspace) / "exec" / "execution_records.json"
            if workspace is not None
            else None
        )
        cost_by_task: dict[str, float] = {}
        for record in load_records(records_file):
            task_key = str(record.get("task") or "")
            if task_key and task_key not in cost_by_task:
                cost_by_task[task_key] = _trace_cost(record)
        # ③ validation_result.json → 验证汇总
        validation: dict[str, Any] = {}
        val_file = project_dir / "validation_result.json"
        if val_file.is_file():
            try:
                val = json.loads(val_file.read_text(encoding="utf-8"))
                validation = {
                    "success": bool(val.get("success")),
                    "tests_total": int(val.get("tests_total") or 0),
                    "tests_passed": int(val.get("tests_passed") or 0),
                    "tests_failed": int(val.get("tests_failed") or 0),
                    "errors": list(val.get("errors") or []),
                }
            except Exception:  # noqa: BLE001 — 失败安全: 损坏 → 空验证
                validation = {}
        # 组装: 功能分组 + 任务链 + 汇总
        features: dict[str, dict[str, Any]] = {}
        cost_total = 0.0
        for task in tasks:
            if not isinstance(task, dict):
                continue
            fname = str(task.get("feature") or cls.UNGROUPED_FEATURE)
            feature = features.setdefault(fname, {"name": fname, "tasks": []})
            tname = str(task.get("name") or task.get("id") or "")
            cost = cost_by_task.get(tname, 0.0)
            cost_total += cost
            feature["tasks"].append(
                {
                    "id": str(task.get("id") or ""),
                    "name": tname,
                    "agent": str(task.get("agent") or ""),
                    "status": str(task.get("status") or "pending"),
                    "artifact": str(task.get("artifact") or ""),
                    "validation": task.get("validation"),
                    "cost": round(cost, 6),
                }
            )
        return {
            "project": {"name": name, "slug": slug},
            "features": list(features.values()),
            "tasks_total": len(tasks),
            "tasks_completed": sum(
                1 for t in tasks if isinstance(t, dict) and t.get("status") == "completed"
            ),
            "agents": sorted(
                {
                    str(t.get("agent"))
                    for t in tasks
                    if isinstance(t, dict) and t.get("agent") and str(t.get("agent")) != "None"
                }
            ),
            "validation": validation,
            "cost_total": round(cost_total, 6),
        }

    @classmethod
    def save(cls, project_dir: Path, trace: dict[str, Any]) -> Path:
        """production_trace.json 落盘 (项目目录; 父目录自动创建, 中文可读)。"""
        path = Path(project_dir) / cls.TRACE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path


def write_production_trace(
    project_dir: Path, workspace: Optional[Path] = None
) -> dict[str, Any]:
    """build + save 一步完成 (验收 H 便捷入口): 返回 trace dict, 同时落盘。"""
    trace = ProductionTrace.build(project_dir, workspace=workspace)
    ProductionTrace.save(project_dir, trace)
    return trace
