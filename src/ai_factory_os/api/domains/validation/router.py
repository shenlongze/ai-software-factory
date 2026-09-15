"""验收 域 HTTP 适配（api/domains/validation）。

纪律（见 docs/design/api-structure.md §2）:
  · 只做 HTTP 适配: 解析 → 调用 services/validation/ 的用例 → 包络
  · 禁 import 任何 _pending_migration/** 的模块 ✗
  · 禁跨域直调 services/<别的域>/ ✗（跨域走 contracts/）
  · 禁在 router 里直接读写数据文件 ✗

本域实况（刀2 首域）:
  · 3 个端点（老区 `/api/acceptances/*`）—— 实现已从
    `_pending_migration/factory_console/acceptance_truth.py` 搬进
    `services/validation/acceptance.py`（跨域读取改为注入钩子，见该模块 docstring）
  · 路径按 §4 归一: `/api/acceptances/*` → `/api/validation/acceptances/*`
  · 响应形状**沿用老区**（`{"ok": true, ...}`），不在此刀改形状 —— 迁移期不让调用方断；
    包络统一（§4 的 `{items,count}` / 错误码）留待刀5
  · 老区 `/api/approval-gates` **不在本域** —— 它是"org 审批门"，归 governance
    （api-structure §6 把 approval-gates 在 validation 与 governance 两行都登记了，重复登记）
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ai_factory_os.api.deps import data_root
from ai_factory_os.services.validation import acceptance as acc

router = APIRouter(prefix="/api/validation", tags=["验收"])


def _root() -> Path:
    return data_root()


@router.post("/acceptances/{acceptance_id}/approve")
def approve_acceptance(acceptance_id: str,
                       body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """用户 Approve（reviewer 必需；ver 必须 PASS —— 不能批准未验证产品）。"""
    try:
        result = acc.approve(
            _root(), acceptance_id,
            reviewer=str((body or {}).get("reviewer") or "user"),
            comment=str((body or {}).get("comment") or ""))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.post("/acceptances/{acceptance_id}/request-change")
def request_change_acceptance(acceptance_id: str,
                             body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """用户 Request Change（置 CHANGE_REQUESTED + 记录 comment；新 production 由 workflow 触发）。"""
    try:
        result = acc.request_change(
            _root(), acceptance_id,
            reviewer=str((body or {}).get("reviewer") or "user"),
            comment=str((body or {}).get("comment") or ""))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.post("/acceptances/{acceptance_id}/release")
def release_acceptance(acceptance_id: str) -> dict[str, Any]:
    """由验收创建 canonical Release（仅 APPROVED + ver PASS；gate 真实执行）。"""
    try:
        out = acc.create_release_for_acceptance(_root(), acceptance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:            # 跨域动作未接线（bootstrap 未注入）
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True, **out}
