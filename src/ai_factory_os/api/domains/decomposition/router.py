"""任务拆解 域 HTTP 适配（api/domains/decomposition）。

纪律（见 docs/design/api-structure.md §2）:
  · 只做 HTTP 适配: 解析 → 调用 services/ 的用例 → 包络
  · 禁 import 任何 _pending_migration/** 的模块 ✗
  · 禁跨域直调 services/<别的域>/ ✗（跨域走 contracts/）
  · 禁在 router 里直接读写数据文件 ✗（存储只经 services/ 或 infrastructure/）

本域实况: task_decomposition（真拆解）· task_tree（物化）✓
  ★ 刀2 第三域 —— schedules 5 端点已迁（实现见 services/work/scheduler.py）。
    归属依据: api-structure §6 映射表「decomposition = task-trees(3) · tasks(3) · schedules(5)」。
    两层口径: 服务实现落在 services/work/（服务域），HTTP 面归 decomposition（API 域）。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ai_factory_os.api.deps import data_root
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
