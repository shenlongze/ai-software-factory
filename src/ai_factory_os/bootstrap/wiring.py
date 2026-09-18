"""bootstrap.wiring —— 跨域装配（SSoT §一: bootstrap 是**唯一可 import 全部**的层）。

为什么需要这个文件（2026-09-15, 端到端实测暴露）:
    各域用 `bind_lookups()` 声明"我需要什么跨域能力", 但**从来没有人注入** ——
    于是 hook 永远为空。后果实测到了:
        · 会话里派生的 PRD **没进项目**（`rec["project_id"]` 一直是空）
        · 于是 `factory progress` 按【项目】统计时链路全是 0 份,
          而 `factory trace` 按【会话】看却样样都有
        · 即: 数据都在, **关联缺** —— "记录全链路"卡在这里

位置依据:
    SSoT §一 七层 —— `bootstrap/` = 「装配与启动（唯一可 import 全部）」
    ⇒ 注入点在本层, 不在各域内部, 也不在 CLI（apps/ 是消费者）。

装配清单（当前只有一项, 按需增长）:
    conversation.formalization.ensure_project_binding
        → 建"会话 ↔ 项目"绑定（幂等）; 让 PRD 落进 `projects/<P-id>/product_truth/`,
          这样 `factory progress` 按项目才看得见链路 ✓

★ 过渡说明（与 CLI 借 `llm_raw` 同类）:
    实现暂借老区 `canonical_golden_path.ensure_project_binding`（它依赖老区实体层
    `unified_contract`）。等"会话↔项目绑定"这一能力迁入新地基后, 只需换本文件里的
    一行 import —— 注入点(schema)不用动。
"""
from __future__ import annotations

from pathlib import Path

__all__ = ["wire", "wired"]

_wired: dict[str, str] = {}


def wire(*, verbose: bool = False) -> dict[str, str]:
    """把跨域能力注入到各域的 hook 里。**幂等**（重复调用安全）。

    返回 {装配项: 状态} —— 便于命令/doctor 显示装配实况（而不是"看起来配上了"）。
    失败安全: 任一项装配失败**不抛出**（链路不该因为一个 hook 装不上就整体不可用）,
              但会如实记进返回值的状态里, 不静默。
    """
    if _wired:
        return dict(_wired)

    # ── conversation.formalization: 会话 ↔ 项目绑定
    try:
        from ai_factory_os.services.conversation import formalization as _F
        from factory_console.canonical_golden_path import (
            ensure_project_binding as _bind,
        )
        _F.bind_lookups(ensure_project_binding=_bind)
        _wired["conversation.formalization.ensure_project_binding"] = "ok（借老区实现）"
    except Exception as exc:  # noqa: BLE001 — 装配失败不阻断链路, 但要如实记
        _wired["conversation.formalization.ensure_project_binding"] = (
            f"unavailable: {type(exc).__name__}: {exc}"
        )

    # ── organization.artifact_lifecycle: 审批读取（破环2 的注入点）
    try:
        from ai_factory_os.services.organization import artifact_lifecycle as _AL
        from ai_factory_os.services.governance.store import ApprovalStore   # ★ 已切新地基

        def _get_approval(root, approval_id):    # 老签名 → 新 store（返回 dict 或 None）
            rec = ApprovalStore(Path(root) / "governance").get(approval_id)
            return rec.to_dict() if rec is not None else None

        _AL.bind_lookups(get_approval=_get_approval)
        _wired["organization.artifact_lifecycle.get_approval"] = "ok（新地基 governance）"
    except Exception as exc:  # noqa: BLE001
        _wired["organization.artifact_lifecycle.get_approval"] = f"unavailable: {type(exc).__name__}: {exc}"

    if verbose:
        for k, v in _wired.items():
            print(f"  wire: {k} → {v}")
    return dict(_wired)


def wired() -> dict[str, str]:
    """已装配项（未 wire 过 → 空 dict）。"""
    return dict(_wired)


def _reset_for_tests() -> None:
    """仅供测试: 清空已装配标记。"""
    _wired.clear()
