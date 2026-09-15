"""监控 域 HTTP 适配（api/domains/metrics）。

纪律（见 docs/design/api-structure.md §2）:
  · 只做 HTTP 适配: 解析 → 调用 services/metrics/ 的用例 → 包络
  · 禁 import 任何 _pending_migration/** 的模块 ✗
  · 禁跨域直调 services/<别的域>/ ✗（跨域走 contracts/）
  · 禁在 router 里直接读写数据文件 ✗

本域实况（刀2 第二域）: Control Tower 4 个只读投影端点，实现已从
  `_pending_migration/factory_console/control_tower.py` 搬进
  `services/metrics/control_tower.py`（跨域数据源改为注入钩子）。
  路径按 §4 归一: `/api/control-tower/*` → `/api/metrics/control-tower/*`。
  响应形状沿用老区（直接返回投影对象，不套 ok 包络）。

注: 本域另有 `monitor`(1) 与 `decisions`(1) 两个端点未迁（依赖 session.board /
  organization.management / 老区 console service，依赖面更大）—— 留待后续刀。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ai_factory_os.api.deps import data_root
from ai_factory_os.services.metrics import control_tower as ct

router = APIRouter(prefix="/api/metrics", tags=["监控"])


@router.get("/control-tower")
def control_tower_overview() -> dict[str, Any]:
    """Control Tower 总览（work / workforce / governance / realtime 合成投影）。"""
    return ct.control_tower(data_root())


@router.get("/control-tower/workforce")
def control_tower_workforce() -> dict[str, Any]:
    """Workforce 状态（谁在干什么，从真实 task 投影）。"""
    return ct.workforce_status(data_root())


@router.get("/control-tower/governance")
def control_tower_governance() -> dict[str, Any]:
    """Governance 待办（PENDING approvals）。"""
    return ct.governance_pending(data_root())


@router.get("/control-tower/realtime")
def control_tower_realtime() -> dict[str, Any]:
    """最近事件流（correlation 可追溯）。"""
    return ct.realtime_stream(data_root())
