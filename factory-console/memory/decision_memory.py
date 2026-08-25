"""factory-console/memory/decision_memory.py — K-3 M4-3 决策记忆回流 (E5, S10-119)。

审批决策 → 审计 DECISION_LEARNED → 组织记忆落盘 decision_memory.json →
下次同类审批带历史 ("历史同类决策: N 次, 批准率 X%") + 少审提示。

- record(decision_id, type, outcome, context) — 追加决策记忆 + 发射
  DECISION_LEARNED 审计事件 (失败安全, 审计故障不中断记忆落盘);
- history(type, context_key) — 同类决策统计 {total, approved, rejected,
  approval_rate, records} — 下次审批展示口径;
- records(type=None) / load / save — 读回/持久化 (失败安全)。

设计: docs/sprint10/S10-119-k3-learning-loop-plan.md §1.3 (M4-3, E5)
边界:
- 纯标准库 (json/uuid/datetime/pathlib), 零第三方依赖
- 失败安全: 缺失/损坏 → 空列表; 落盘异常不抛; 审计发射失败不阻断
- DECISION_LEARNED 事件类型已在 audit_event.EVENT_TYPES 注册 (S10-069) — 复用
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: 组织决策记忆文件名 (workspace/memory/decision_memory.json)
DECISION_MEMORY_FILE_NAME = "decision_memory.json"

#: 审批决策类型注册表 (新增审批场景在此登记 — 同类型统计口径)
DECISION_TYPES: tuple[str, ...] = (
    "project_plan_approval",   # 工程计划架构审批 (approve_project_plan)
    "review",                  # 评审审批 (review_approve/review_reject)
)


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (learned_at 时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


def decision_memory_file(workspace: Any = None) -> Path:
    """workspace/memory/decision_memory.json (缺省 ~/.factory/memory/)。"""
    from .experience_store import memory_dir

    return memory_dir(workspace) / DECISION_MEMORY_FILE_NAME


@dataclass
class DecisionRecord:
    """单条决策记忆 (E5): decision_id/type/outcome/context/learned_at。"""

    decision_id: str = field(default_factory=lambda: f"dec-{uuid.uuid4().hex[:12]}")
    type: str = "project_plan_approval"
    outcome: str = "approved"      # approved | rejected
    context: str = ""              # 项目/评审 id — 同类判定键
    learned_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        """→ dict (JSON 落盘/展示口径)。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "DecisionRecord":
        """dict → DecisionRecord (缺失字段缺省; 非 dict → ValueError)。"""
        if not isinstance(data, dict):
            raise ValueError(
                f"DecisionRecord.from_dict 需要 dict, 收到 {type(data).__name__}"
            )
        return cls(
            decision_id=str(data.get("decision_id") or f"dec-{uuid.uuid4().hex[:12]}"),
            type=str(data.get("type") or "project_plan_approval"),
            outcome=str(data.get("outcome") or "approved"),
            context=str(data.get("context") or ""),
            learned_at=str(data.get("learned_at") or _now_iso()),
        )


class DecisionMemory:
    """组织决策记忆 (M4-3/E5): record + history + 持久化 (失败安全)。

    record: 追加 + DECISION_LEARNED 审计发射 (失败安全) → 返回记录 dict;
    history(type, context_key): 同类决策统计 (N 次/批准率) — 下次审批展示;
    records(type=None): 读回 (可按类型过滤); load/save: 持久化。
    """

    def __init__(
        self,
        workspace: Any = None,
        file: Optional[Path] = None,
        *,
        audit_emitter: Any = None,
    ) -> None:
        """file 显式注入 (测试隔离); 缺省 → workspace/memory/decision_memory.json。

        audit_emitter: 审计发射器注入 (测试); 缺省 → AuditEmitter(workspace)。
        """
        self.path = Path(file) if file is not None else decision_memory_file(workspace)
        self._workspace = workspace
        self._audit_emitter = audit_emitter
        self._records: list[DecisionRecord] = []
        self.load()

    # ------------------------------------------------------------ 读写

    def load(self) -> list[DecisionRecord]:
        """读 decision_memory.json → 记录列表 (缺失/损坏 → [] 失败安全)。"""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空
            self._records = []
            return self._records
        loaded: list[DecisionRecord] = []
        if isinstance(data, list):
            for item in data:
                try:
                    loaded.append(DecisionRecord.from_dict(item))
                except Exception:  # noqa: BLE001 — 单条损坏跳过
                    continue
        self._records = loaded
        return self._records

    def save(self) -> Path:
        """落盘 decision_memory.json (失败安全: 落盘异常不抛)。"""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(
                    [r.to_dict() for r in self._records],
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — 失败安全
            pass
        return self.path

    # ------------------------------------------------------------ 记录

    def record(
        self,
        decision_id: str,
        type: str,
        outcome: str,
        context: str = "",
        *,
        actor_id: str = "",
        project_id: str = "",
    ) -> dict[str, Any]:
        """审批决策 → 决策记忆 + DECISION_LEARNED 审计 (失败安全)。

        返回记录 dict; 同 decision_id 覆盖 (幂等 — 重审不产生重复记忆)。
        """
        record = DecisionRecord(
            decision_id=str(decision_id or f"dec-{uuid.uuid4().hex[:12]}"),
            type=str(type or "project_plan_approval"),
            outcome=str(outcome or "approved"),
            context=str(context or ""),
        )
        replaced = False
        for i, existing in enumerate(self._records):
            if existing.decision_id == record.decision_id:
                self._records[i] = record
                replaced = True
                break
        if not replaced:
            self._records.append(record)
        self.save()
        # DECISION_LEARNED 审计 (失败安全 — 审计故障不中断记忆落盘)
        self._emit_learned(record, actor_id=actor_id, project_id=project_id)
        return record.to_dict()

    def _emit_learned(
        self, record: DecisionRecord, *, actor_id: str, project_id: str
    ) -> None:
        """发射 DECISION_LEARNED 审计事件 (失败安全, 不抛)。"""
        try:
            if self._audit_emitter is not None:
                emitter = self._audit_emitter
            else:
                from ..audit.audit_emitter import AuditEmitter

                emitter = AuditEmitter(workspace=self._workspace)
            emitter.emit(
                "DECISION_LEARNED",
                project_id=project_id,
                actor_type="user",
                actor_id=actor_id or "user",
                decision=record.to_dict(),
                decision_reason=(
                    f"决策已学习: {record.type} = {record.outcome} "
                    f"(context={record.context or '-'})"
                ),
            )
        except Exception:  # noqa: BLE001 — 失败安全: 审计故障不阻断
            pass

    # ------------------------------------------------------------ 查询

    def records(self, type: Optional[str] = None) -> list[dict[str, Any]]:
        """读回决策记忆 (可按类型过滤; 失败安全 → [])。"""
        out = self._records
        if type is not None:
            out = [r for r in out if r.type == str(type)]
        return [r.to_dict() for r in out]

    def history(
        self,
        type: Optional[str] = None,
        context_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """同类决策历史 (M4-3/E5 展示口径): N 次/批准率/明细。

        type 与 context_key 均为 None → 全量统计; context_key 非空 → 只统计
        context 含该键的同类决策 (项目级/评审级同类判定)。
        返回 {total, approved, rejected, approval_rate, records}。
        """
        out = self._records
        if type is not None:
            out = [r for r in out if r.type == str(type)]
        if context_key:
            key = str(context_key)
            out = [r for r in out if key in r.context]
        total = len(out)
        approved = sum(1 for r in out if r.outcome == "approved")
        rejected = sum(1 for r in out if r.outcome == "rejected")
        rate = round(approved / total, 4) if total else 0.0
        return {
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "approval_rate": rate,
            "records": [r.to_dict() for r in out],
        }


__all__ = [
    "DECISION_MEMORY_FILE_NAME",
    "DECISION_TYPES",
    "DecisionMemory",
    "DecisionRecord",
    "decision_memory_file",
]
