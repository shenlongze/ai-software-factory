"""factory-console/session/review_gate.py — ReviewRecord + ReviewGate (S10-063 批次 A)。

Production Governance (GAP G5, 设计 §5): 人工评审闸 — REQUEST_REVIEW →
WAITING_FOR_REVIEW → APPROVED/REJECTED/CANCELLED → CONTINUE/BLOCK。
触发: 高成本/高风险/反复失败/多次 replan/LLM confidence 低/proposal 不稳定/
无法解决 conflict/超 budget (调用方触发, 本模块只记录 + 状态流转)。

组件:
- ReviewRecord — 评审记录 {review_id, reason, trigger, decision, status,
  created_at, reviewed_at, reviewer, context, affected_tasks, estimated_cost,
  risk} + to_dict/from_dict; status ∈ open/approved/rejected/cancelled
- ReviewGate   — request (status="open") / approve / reject / cancel /
  pending() (全部 open) / status(project_id) ("none"|"waiting"|"approved"|
  "rejected" — 最近状态) / save/load → review_records.json (失败安全);
  for_project(project_dir) — 项目级评审文件

真正停止语义: status="open" 即 WAITING_FOR_REVIEW — 调用方 (后续批次接入
orchestrator) 必须停止执行循环, 本模块负责状态单一来源。

设计: docs/sprint10/S10-063-production-governance-design.md §5
边界: 纯标准库 (json/uuid/pathlib/dataclasses/datetime), 零依赖, 不修改任何
现有模块; 失败安全 (缺失/损坏 → [], 未知 review_id → None, 永不抛)。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: 缺省评审记录文件 (~/.factory/teams/review_records.json — 设计 §5 资产口径;
#: 项目级记录 → projects/<slug>/review_records.json, 由调用方显式指定)
DEFAULT_REVIEW_FILE = Path.home() / ".factory" / "teams" / "review_records.json"

#: 项目级评审文件名 (projects/<slug>/review_records.json)
REVIEW_RECORDS_FILE_NAME = "review_records.json"

# ---------------------------------------------------------------- 状态常量

STATUS_OPEN = "open"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_CANCELLED = "cancelled"

#: 全部合法评审状态
REVIEW_STATUSES: tuple[str, ...] = (
    STATUS_OPEN,
    STATUS_APPROVED,
    STATUS_REJECTED,
    STATUS_CANCELLED,
)

#: 评审风险档位 (与 ExecutionPolicy.risk 对齐)
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (创建/评审时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ReviewRecord:
    """人工评审记录 (设计 §5): 全字段 + to_dict/from_dict。

    review_id      — 唯一评审 id (uuid4 hex);
    reason         — 为什么需要评审 (可解释);
    trigger        — 触发源 (budget/policy/loop_guard/conflict/replanning...);
    decision       — 评审后决策 ("approved"/"rejected"/"cancelled"/"" 未决);
    status         — open/approved/rejected/cancelled;
    created_at     — 发起时间 (UTC ISO); reviewed_at — 评审时间 (未评 → "");
    reviewer       — 评审人 (approve/reject 时注入);
    context        — 上下文快照 (project_id/sprint_id/执行状态等, dict);
    affected_tasks — 受影响任务 id 列表;
    estimated_cost — 关联估算成本 (USD); risk — low/medium/high。
    """

    review_id: str = ""
    reason: str = ""
    trigger: str = ""
    decision: str = ""
    status: str = STATUS_OPEN
    created_at: str = ""
    reviewed_at: str = ""
    reviewer: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    affected_tasks: list[str] = field(default_factory=list)
    estimated_cost: float = 0.0
    risk: str = RISK_MEDIUM

    def to_dict(self) -> dict[str, Any]:
        """→ dict (落盘 review_records.json / 审计视图)。"""
        return {
            "review_id": self.review_id,
            "reason": self.reason,
            "trigger": self.trigger,
            "decision": self.decision,
            "status": self.status,
            "created_at": self.created_at,
            "reviewed_at": self.reviewed_at,
            "reviewer": self.reviewer,
            "context": dict(self.context or {}),
            "affected_tasks": list(self.affected_tasks),
            "estimated_cost": float(self.estimated_cost),
            "risk": self.risk,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "ReviewRecord":
        """dict → ReviewRecord (缺失字段 → 缺省, 前向兼容/失败安全)。"""
        if not isinstance(data, dict):
            return cls()
        status = str(data.get("status") or STATUS_OPEN)
        if status not in REVIEW_STATUSES:
            status = STATUS_OPEN
        risk = str(data.get("risk") or RISK_MEDIUM)
        if risk not in (RISK_LOW, RISK_MEDIUM, RISK_HIGH):
            risk = RISK_MEDIUM
        return cls(
            review_id=str(data.get("review_id") or ""),
            reason=str(data.get("reason") or ""),
            trigger=str(data.get("trigger") or ""),
            decision=str(data.get("decision") or ""),
            status=status,
            created_at=str(data.get("created_at") or ""),
            reviewed_at=str(data.get("reviewed_at") or ""),
            reviewer=str(data.get("reviewer") or ""),
            context=dict(data.get("context") or {}),
            affected_tasks=[
                str(t) for t in (data.get("affected_tasks") or [])
                if isinstance(t, (str, int))
            ],
            estimated_cost=float(data.get("estimated_cost") or 0.0),
            risk=risk,
        )


class ReviewGate:
    """人工评审闸 (设计 §5): request/approve/reject/cancel/pending/status +
    持久化 (review_records.json, 失败安全)。

    request(...) — 新评审 (status="open", WAITING_FOR_REVIEW);
    approve(review_id, reviewer) / reject / cancel — 状态流转 + 决策/时间戳;
    pending() — 全部 open 评审; status(project_id) — "none"|"waiting"|
    "approved"|"rejected" (最近状态; 有 open → "waiting");
    project_id 通过 context["project_id"] 关联 (request 可传 project_id=)。
    """

    FILE_NAME = REVIEW_RECORDS_FILE_NAME

    STATUS_OPEN = STATUS_OPEN
    STATUS_APPROVED = STATUS_APPROVED
    STATUS_REJECTED = STATUS_REJECTED
    STATUS_CANCELLED = STATUS_CANCELLED

    def __init__(self, file: Optional[Path] = None) -> None:
        self._file = Path(file) if file is not None else DEFAULT_REVIEW_FILE

    # ------------------------------------------------------------ request

    def request(
        self,
        reason: str,
        trigger: str = "",
        context: Any = None,
        affected_tasks: Any = None,
        estimated_cost: float = 0.0,
        risk: str = RISK_MEDIUM,
        project_id: str = "",
    ) -> ReviewRecord:
        """发起评审 → ReviewRecord (status="open"), append 落盘 (失败安全)。

        project_id 非空 → 注入 context["project_id"] (status(project_id) 过滤)。
        """
        ctx = dict(context or {})
        if project_id:
            ctx["project_id"] = str(project_id)
        record = ReviewRecord(
            review_id=str(uuid.uuid4()),
            reason=str(reason or ""),
            trigger=str(trigger or ""),
            status=STATUS_OPEN,
            created_at=_now_iso(),
            context=ctx,
            affected_tasks=[
                str(t) for t in (affected_tasks or [])
                if isinstance(t, (str, int))
            ],
            estimated_cost=float(estimated_cost or 0.0),
            risk=risk if risk in (RISK_LOW, RISK_MEDIUM, RISK_HIGH) else RISK_MEDIUM,
        )
        records = self.load()
        records.append(record.to_dict())
        self.save(records)
        return record

    # ------------------------------------------------------------ 状态流转

    def approve(self, review_id: str, reviewer: str = "") -> Optional[ReviewRecord]:
        """批准评审 → status="approved", decision="approved" (未知 id → None)。"""
        return self._transition(review_id, STATUS_APPROVED, reviewer)

    def reject(self, review_id: str, reviewer: str = "") -> Optional[ReviewRecord]:
        """拒绝评审 → status="rejected", decision="rejected" (未知 id → None)。"""
        return self._transition(review_id, STATUS_REJECTED, reviewer)

    def cancel(self, review_id: str) -> Optional[ReviewRecord]:
        """取消评审 → status="cancelled", decision="cancelled" (未知 id → None)。"""
        return self._transition(review_id, STATUS_CANCELLED, "")

    def _transition(
        self, review_id: str, status: str, reviewer: str
    ) -> Optional[ReviewRecord]:
        """状态流转 + 落盘 (失败安全: 未知 review_id → None, 不抛)。"""
        records = self.load()
        for i, rec in enumerate(records):
            if rec.get("review_id") != review_id:
                continue
            rec["status"] = status
            rec["decision"] = status
            rec["reviewed_at"] = _now_iso()
            if reviewer:
                rec["reviewer"] = str(reviewer)
            records[i] = rec
            self.save(records)
            return ReviewRecord.from_dict(rec)
        return None

    # ------------------------------------------------------------ 查询

    def pending(self) -> list[ReviewRecord]:
        """全部 open 评审 (WAITING_FOR_REVIEW — 调用方必须停止执行循环)。"""
        return [
            ReviewRecord.from_dict(r)
            for r in self.load()
            if r.get("status") == STATUS_OPEN
        ]

    def all_records(self) -> list[ReviewRecord]:
        """全部评审记录 (读回, 失败安全 → [])。"""
        return [ReviewRecord.from_dict(r) for r in self.load()]

    def status(self, project_id: Optional[str] = None) -> str:
        """项目评审状态 (设计 §5): "none"|"waiting"|"approved"|"rejected"。

        - 无该项目评审 → "none";
        - 存在 open → "waiting" (WAITING_FOR_REVIEW — 必须停止);
        - 否则 → 最近一条非 cancelled 记录的状态 (approved/rejected);
        - 全部 cancelled → "none"。
        """
        records = self.load()
        if project_id is not None:
            records = [
                r for r in records
                if r.get("context", {}).get("project_id") == project_id
            ]
        if not records:
            return "none"
        for rec in records:
            if rec.get("status") == STATUS_OPEN:
                return "waiting"
        for rec in reversed(records):
            status = rec.get("status")
            if status == STATUS_APPROVED:
                return "approved"
            if status == STATUS_REJECTED:
                return "rejected"
        return "none"

    # ------------------------------------------------------------ 读/写

    def save(self, records: Any) -> None:
        """整表落盘 (失败安全: 读写异常 → 不抛)。"""
        if not isinstance(records, list):
            records = []
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — 失败安全
            pass

    def load(self) -> list[dict[str, Any]]:
        """读回全部评审记录 (缺失/损坏 → [], 失败安全)。"""
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [
                    ReviewRecord.from_dict(d).to_dict()
                    for d in data
                    if isinstance(d, dict)
                ]
        except Exception:  # noqa: BLE001 — 缺失/损坏 → 空记录
            pass
        return []

    def records_file(self) -> Path:
        """当前落盘文件路径。"""
        return Path(self._file)

    @classmethod
    def for_project(cls, project_dir: Any) -> "ReviewGate":
        """项目级评审闸实例 → projects/<slug>/review_records.json。"""
        return cls(file=Path(project_dir) / REVIEW_RECORDS_FILE_NAME)
