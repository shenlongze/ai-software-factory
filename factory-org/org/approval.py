"""factory-org/org/approval.py — Approval Gate 人工审批门 (Sprint 9 S9-001)。

设计依据 (sprint9-architecture.md §2 Human Approval Gate):
```
Workflow stage 增加 approval_required 属性 (product/design/release 三挡板)
  执行到该 stage 完成 → 创建 ApprovalGate (PENDING) → workflow PAUSED
  → 人工确认 (CLI/Console: approve/reject) → 继续/停止
    approve → gate APPROVED → workflow 恢复 (PAUSED→ACTIVE, 继续下一 stage)
    reject  → gate REJECTED → workflow FAILED (停止, 记录原因)
```

本模块 = Approval Gate 领域模型 + 受控状态机 + 持久化 (与 org 其他 store
同模式: JSON 原子写, 损坏失败安全)。**零业务编排** — 与 Workflow 的接线
(创建/恢复/停止) 在 org/workflow.py (WorkflowLifecycle 扩展, 见 S9-001
报告 §Workflow 集成); 本模块只依赖 models.py + store.py (Removal Isolation,
同 S7-001/002 模式)。

状态机 (APPROVAL_TRANSITIONS 受控转换表, 单向无环):
```
PENDING → APPROVED (放行, 终态) / REJECTED (否决, 终态)
approved/rejected 为终态: 不可再流转 (决定不可撤销 — 审计铁律)
```

存储: <root>/org/approvals.json (ApprovalGateStore; 与 WorkflowSection 同
目录独立文件)。gate id 前缀 AG- (new_id("AG"))。

约束: 事件经 org/events.py record_approval_* (logger=None 全静默);
本模块零顶层 imports events (同 provider/product store 模式)。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, field_validator

from .models import _OrgModel, utcnow
from .store import _SectionStore


# ------------------------------------------------------------------ 枚举


class ApprovalStatus(str, Enum):
    """审批门状态 (PENDING → APPROVED/REJECTED; 后二者为终态, 决定不可撤销)。

    approved/rejected 不可再流转 (APPROVAL_TRANSITIONS 空) — 审批决定审计
    铁律: 一次决定, 永久记录 (改决定须新建门, 不留覆盖痕迹)。
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

    @classmethod
    def parse(cls, value: Any) -> "ApprovalStatus":
        """宽容解析: 大小写不敏感; 枚举对象直接返回; 非法值抛 ValueError。"""
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"invalid approval status: {value!r} (expected one of: {valid})"
            ) from None


#: 审批门合法流转 (受控转换表; 单向无环; approved/rejected 终态)。
APPROVAL_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "pending": ("approved", "rejected"),
    "approved": (),
    "rejected": (),
}


# ------------------------------------------------------------------ 异常


class ApprovalError(Exception):
    """Approval Gate 基础异常 (CLI 错误映射: rc 1)。"""


class ApprovalStateError(ApprovalError):
    """非法审批状态转换 (非 PENDING 决定 / 终态再流转 — 受控转换表拒绝)。"""


# ------------------------------------------------------------------ 模型


class ApprovalGate(_OrgModel):
    """审批门 (人工审批节点; 绑定一个 stage 及其所属 workflow)。

    字段 (S9-001 任务清单):
    - id: 门 id (AG-xxx)
    - stage_id: 被审批 stage (approval_required stage COMPLETED 后创建)
    - workflow_id: 所属 workflow (审批决定后恢复/停止的目标 — 冗余 scoping,
      同 Role.company_id 先例, workflow 维度查询/恢复零 join)
    - status: PENDING/APPROVED/REJECTED (受控转换表 APPROVAL_TRANSITIONS)
    - reviewer / comment: 决策人与理由 (approve/reject 时落库, 审计)
    - requested_at: 门创建时间; approved_at / rejected_at: 决定时间
    """

    id: str
    stage_id: str
    workflow_id: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewer: str = ""
    comment: str = ""
    requested_at: datetime = Field(default_factory=utcnow)
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> ApprovalStatus:
        return ApprovalStatus.parse(v)

    @property
    def is_pending(self) -> bool:
        """待审判断 (PENDING — 可 approve/reject)。"""
        return self.status == ApprovalStatus.PENDING

    @property
    def is_terminal(self) -> bool:
        """终态判断 (approved/rejected 后不可再流转)。"""
        return self.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)


def transition_approval(
    gate: ApprovalGate,
    to_status: ApprovalStatus | str,
    *,
    reviewer: str = "",
    comment: str = "",
) -> ApprovalGate:
    """受控状态转换 (APPROVAL_TRANSITIONS; 非 PENDING 决定 → ApprovalStateError)。

    - PENDING → APPROVED: approved_at 落库; reviewer/comment 记录决策人
    - PENDING → REJECTED: rejected_at 落库; 同上
    - PENDING → PENDING 同状态幂等 (返回原实例, 不重复写)
    - approved/rejected 终态: **任何**再流转 (含同状态重复决定) 响亮拒绝
      (决定不可撤销 — 审计铁律: 一次决定, 永久记录; 改决定须新建门)。
    返回新实例 (model_copy, 与 org 全库同模式 — 调用方负责 store.save)。
    """
    target = ApprovalStatus.parse(to_status)
    if gate.is_terminal:
        raise ApprovalStateError(
            f"invalid approval transition: {gate.status.value} → "
            f"{target.value} (decision is final — {gate.status.value} gates "
            f"are terminal, 决定不可撤销; create a new gate to re-request)"
        )
    if target == gate.status:
        return gate  # 幂等: PENDING → PENDING 同状态不重复流转
    allowed = APPROVAL_TRANSITIONS.get(gate.status.value, ())
    if target.value not in allowed:
        raise ApprovalStateError(
            f"invalid approval transition: {gate.status.value} → "
            f"{target.value} (allowed from {gate.status.value}: "
            f"{', '.join(allowed) or 'none'})"
        )
    updates: dict[str, Any] = {
        "status": target,
        "reviewer": reviewer,
        "comment": comment,
        "updated_at": utcnow(),
    }
    if target == ApprovalStatus.APPROVED:
        updates["approved_at"] = utcnow()
    elif target == ApprovalStatus.REJECTED:
        updates["rejected_at"] = utcnow()
    return gate.model_copy(update=updates)


# ------------------------------------------------------------------ 持久化


class ApprovalGateStore(_SectionStore[ApprovalGate]):
    """ApprovalGate 持久化 (approvals.json; 与 org 其他 store 同模式)。

    原子写 (临时文件 + os.replace) + 损坏失败安全 (CorruptOrgStoreError 响亮
    拒绝, 绝不静默返回空) — 同 WorkflowSection/CompanyStore 语义。
    """

    _filename = "approvals.json"
    _section = "approvals"
    _model = ApprovalGate
