"""factory-console/api/workflow_start.py — Workflow 启动/对话路由函数 (S10-006.5 P1-A)。

POST /projects/{id}/start       → 启动真实 Agent 执行链 (后台线程)
POST /projects/{id}/chat        → 持续开发对话 (已启动 → 记录消息;
                                   未启动 → 消息作为 idea 更新 + 触发 start)
GET  /projects/{id}/run-status  → 运行状态 + 进度 (轮询驱动 Timeline)

设计 (只组合, 不重写 — 复用 S10-006.5 P1-A workflow_runner 骨架):
- 启动/执行全部在 workflow_runner.start_project_workflow (key 校验 → 后台
  线程跑 6 阶段真实链); 本模块只做 项目存在性/入参校验 + 参数装配 (org 数据
  空间路径 + events db 路径) + 错误分类 (404/409/503/400 语义)。
- 失败安全: 项目不存在 → None (404); key 缺失/存储不可用 → WorkflowStartError
  (503, 诚实失败 — 不假装执行); 项目已有运行 → WorkflowConflictError (409);
  空消息 → ValueError (400)。
- 事件可读: 链经 EventLogger 写 org.* 事件到 events.db (与 Timeline 同库)
  → GET /projects/{id}/timeline 直接可见 (真实事件, 非伪造)。
- 测试注入: chain_factory/run_async 透传 (测试传假链同步执行; 生产默认
  真实链后台执行)。

chat 语义 (与 chat_store.py 分工 — 本模块组合, 存储模块单一职责):
- 项目运行中 → 只记录消息 (append), 返回 {status: "recorded"} — 不重复启动。
- 项目未运行 → 消息作为新 idea 更新 (org Project.goal) + 记录 + 触发 start
  (新 run 以更新后的 idea 为输入 — 持续开发闭环); start 因 key 缺失失败 →
  WorkflowStartError (503, 消息已记录/idea 已更新, 失败诚实返回)。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..workflow_runner import (
    WorkflowConflictError,
    WorkflowStartError,
    is_project_running,
    start_project_workflow,
)

__all__ = ["chat_route", "run_status_route", "start_project_workflow_route"]


# ------------------------------------------------------------------ 参数装配


def _project_paths(service: Any, project_id: str) -> dict[str, Any] | None:
    """项目运行数据空间 (org_dir + runs_dir); 项目不存在/存储缺失 → None。

    只读服务接口: workflow_run_paths (org ProjectStore 缺失 → None) +
    project_exists (项目不存在 → None — HTTP 层 404)。
    """
    if not service.project_exists(project_id):
        return None
    paths = service.workflow_run_paths()
    if paths is None:
        return None
    return paths


def _resolve_idea(service: Any, project_id: str) -> str:
    """项目 idea (org Project.goal → name 兜底; 空 → \"\" 由调用方判 400)。"""
    return service.project_idea(project_id) or ""


# ------------------------------------------------------------------ 路由函数


def start_project_workflow_route(
    service: Any,
    project_id: str,
    *,
    events_db_path: str | Path | None = None,
    chain_factory: Any = None,
    run_async: bool = True,
    logger: Any = None,
) -> dict[str, Any] | None:
    """POST /projects/{id}/start — 启动真实 Agent 执行链 (后台线程)。

    返回 {status: \"started\", project_id, run_id, note} (HTTP 200 立即回包,
    执行在后台 — 事件/产物落库后 Timeline 可见)。错误语义:
    - 项目不存在 → None (404)
    - events db 缺失 / workflow 存储不可用 / LLM key 缺失 → WorkflowStartError
      (503, 诚实失败 — 不假装执行)
    - 项目已有运行中的 workflow → WorkflowConflictError (409, 诚实拒绝重复启动)
    """
    paths = _project_paths(service, project_id)
    if paths is None:
        return None
    if events_db_path is None:
        raise WorkflowStartError("event store unavailable (无法落库运行事件)")
    idea = _resolve_idea(service, project_id)
    if not idea:
        raise ValueError("project idea is empty (无法启动空想法)")
    return start_project_workflow(
        project_id=project_id,
        idea=idea,
        org_dir=paths["org_dir"],
        events_db_path=events_db_path,
        runs_dir=paths["runs_dir"],
        chain_factory=chain_factory,
        run_async=run_async,
    )


def chat_route(
    service: Any,
    project_id: str,
    message: str,
    *,
    events_db_path: str | Path | None = None,
    chain_factory: Any = None,
    run_async: bool = True,
    logger: Any = None,
) -> dict[str, Any] | None:
    """POST /projects/{id}/chat — 持续开发对话 (最小版)。

    返回形状:
    - 项目运行中 → {status: \"recorded\", project_id, run_id: None, message,
      recorded: true} (只落消息, 不重复启动)
    - 项目未运行 → idea 更新 + 记录 + 触发 start →
      {status: \"started\", project_id, run_id, message, recorded: true}
      (新 run 以更新后的 idea 为输入 — 持续开发闭环)
    错误语义: 项目不存在 → None (404); 空消息 → ValueError (400);
    start 触发失败 (key 缺失等) → WorkflowStartError (503 — 消息已记录,
    诚实失败: 不会假装已启动)。
    """
    paths = _project_paths(service, project_id)
    if paths is None:
        return None
    text = (message or "").strip()
    if not text:
        raise ValueError("message is empty (空消息不发送)")
    store = service.get_conversation_store()
    recorded = False
    if store is not None:
        store.append(project_id, text)
        recorded = True

    if is_project_running(project_id):
        return {
            "status": "recorded",
            "project_id": project_id,
            "run_id": None,
            "message": text,
            "recorded": recorded,
        }
    # 未启动 → 消息作为新 idea (org Project.goal 更新) + 触发 start
    service.update_project_idea(project_id, text)
    started = start_project_workflow_route(
        service,
        project_id,
        events_db_path=events_db_path,
        chain_factory=chain_factory,
        run_async=run_async,
        logger=logger,
    )
    if started is None:  # 理论不可达 (上面已判存在) — 失败安全兜底
        raise WorkflowStartError("project unavailable")
    return {
        "status": "started",
        "project_id": project_id,
        "run_id": started["run_id"],
        "message": text,
        "recorded": recorded,
    }


def run_status_route(
    service: Any,
    project_id: str,
    *,
    logger: Any = None,
) -> dict[str, Any] | None:
    """GET /projects/{id}/run-status — 运行状态 + 进度 (轮询驱动 Timeline)。

    返回形状:
    {
      project_id, status: none|running|completed|failed, current_run_id,
      runs: [{run_id, status, stages, totals, errors, updated_at}], updated_at
    }
    - status 判定: 运行中 (模块级 _RUNNING) → running; 无任何 run → none
      (前端显示\"开始开发\"); 否则取最近 run 的 report 状态 (completed/failed)。
    - 进度: 每阶段写 progress.json (stages/totals/errors 实时可见 — 成本/
      调用数/tokens); 整链完成/失败写 report.json (验收断言 + totals)。
    错误语义: 项目不存在 → None (404); workflow 存储缺失 → WorkflowStartError
    (503, 失败安全)。
    """
    paths = _project_paths(service, project_id)
    if paths is None:
        return None
    runs_dir = Path(paths["runs_dir"]) / project_id
    runs: list[dict[str, Any]] = []
    if runs_dir.is_dir():
        for run_dir in sorted(runs_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            runs.append(_read_run(run_dir))
    # 最近 run 排序 (run_id = R{毫秒时间戳} — 字典序即时间序, 倒序取最新)
    runs.sort(key=lambda r: r["run_id"], reverse=True)
    running = is_project_running(project_id)
    if running:
        status = "running"
    elif not runs:
        status = "none"
    else:
        status = runs[0]["status"] if runs[0]["status"] in ("completed", "failed") else "none"
    return {
        "project_id": project_id,
        "status": status,
        "current_run_id": runs[0]["run_id"] if runs else None,
        "runs": runs,
        "updated_at": runs[0].get("updated_at") if runs else None,
    }


def _read_run(run_dir: Path) -> dict[str, Any]:
    """单 run 状态读取 (report.json 优先; 无 report → progress.json; 都无 → pending)。

    诚实读取: 文件损坏 → 该 run 按 pending 返回 (失败安全, 不拖垮状态查询)。
    """
    run_id = run_dir.name
    report_path = run_dir / "report.json"
    progress_path = run_dir / "progress.json"
    report = _read_json(report_path)
    if report is not None:
        return {
            "run_id": run_id,
            "status": str(report.get("status") or "unknown"),
            "stages": report.get("stages", []),
            "totals": report.get("totals", {}),
            "errors": report.get("errors", []),
            "updated_at": report.get("finished_at"),
        }
    progress = _read_json(progress_path)
    if progress is not None:
        return {
            "run_id": run_id,
            "status": str(progress.get("status") or "running"),
            "stages": progress.get("stages", []),
            "totals": progress.get("totals", {}),
            "errors": progress.get("errors", []),
            "updated_at": progress.get("updated_at"),
        }
    return {
        "run_id": run_id,
        "status": "pending",
        "stages": [],
        "totals": {},
        "errors": [],
        "updated_at": None,
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None
    return None
