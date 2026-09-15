"""任务拆解 域 HTTP 适配（api/domains/decomposition）。

纪律（见 docs/design/api-structure.md §2）:
  · 只做 HTTP 适配: 解析 → 调用 services/ 的用例 → 包络
  · 禁 import 任何 _pending_migration/** 的模块 ✗
  · 禁跨域直调 services/<别的域>/ ✗（跨域走 contracts/）
  · 禁在 router 里直接读写数据文件 ✗（存储只经 services/ 或 infrastructure/）

本域实况: task_decomposition（真拆解）· task_tree（物化）✓
  ★ 刀2 第三域: schedules 5 端点已迁（实现见 services/work/scheduler.py）。
    归属依据: api-structure §6 映射表 —— task-trees(3) · tasks(3) · schedules(5) 归 decomposition。
    ★★ 两层域名不同, 这里说清（2026-09-15 修正一处放错的位置）:
      · API 面   = `decomposition`（本目录）—— §6 的把端点归到这里的裁决
      · 服务实现 = `services/work/`（scheduler.py / tasks.py）—— SSoT §四 的服务域清单
      我一开始把 tasks.py 放进了 services/decomposition/ —— 既不在 SSoT 的服务域清单里,
      又与同域的 scheduler.py（在 services/work/）不一致; 且因为没建 __init__.py,
      R20 把那个目录当成"不存在"因而没报红（守卫盲区, 另行修）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ai_factory_os.api.deps import data_root
from ai_factory_os.services.work import tasks
from ai_factory_os.services.work import scheduler as sch

router = APIRouter(prefix="/api/decomposition", tags=["任务拆解"])


@router.get("/schedules")
def list_schedules() -> dict[str, Any]:
    """Schedules 列表（S22）。"""
    items = sch.list_schedules(data_root())
    return {"items": items, "count": len(items)}


@router.post("/schedules")
def create_schedule(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """创建 Schedule（S22）。间隔过小 → 400。"""
    try:
        return sch.create_schedule(
            data_root(),
            project_id=str(body.get("project_id", "")),
            release_id=str(body.get("release_id", "")),
            interval_seconds=int(body.get("interval_seconds", 300)),
        )
    except Exception as exc:  # noqa: BLE001 — 非法入参 → 400（与老区一致）
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/schedules/{schedule_id}/enable")
def enable_schedule(schedule_id: str) -> dict[str, Any]:
    """启用 Schedule；不存在 → 404。"""
    try:
        return sch.enable_schedule(data_root(), schedule_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/schedules/{schedule_id}/disable")
def disable_schedule(schedule_id: str) -> dict[str, Any]:
    """停用 Schedule；不存在 → 404。"""
    try:
        return sch.disable_schedule(data_root(), schedule_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: str) -> dict[str, Any]:
    """删除 Schedule（幂等）。"""
    sch.delete_schedule(data_root(), schedule_id)
    return {"deleted": schedule_id, "id": schedule_id}


# ---------------------------------------------------------------- 任务树（task_tree 迁入）


@router.get("/task-trees/{task_tree_id}/progress")
def task_tree_progress(task_tree_id: str) -> dict[str, Any]:
    """任务树进度投影（可重建）。实体层未接线 → 带 unwired 标注；树不存在 → 404。"""
    try:
        return tasks.task_progress(data_root(), task_tree_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/task-trees/{task_tree_id}/status")
def task_tree_status(task_tree_id: str) -> dict[str, Any]:
    """任务树状态（每任务 status + 依赖 + 进度）；树不存在 → 404。"""
    try:
        return tasks.tree_status(data_root(), task_tree_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/status")
def update_task_status(task_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Task 状态更新。

    ★ 写操作 fail-closed: 实体层未接线 → 503 拒绝（绝不静默通过）✓
    """
    try:
        return tasks.update_task_status(
            data_root(), task_id,
            status=str(body.get("status", "")), actor=str(body.get("actor", "system")))
    except RuntimeError as exc:      # 未接线 → 503（能力不可用，不是客户端错）
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:        # 实体不存在 / 类型不对
        raise HTTPException(status_code=404, detail=str(exc)) from exc
