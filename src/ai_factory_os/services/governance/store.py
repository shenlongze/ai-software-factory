"""services.governance.store — 审批记录持久化（无业务规则，只读写）。

沿革：factory-exec/exec/store.py → services/approval_runtime/store.py → 此处（刀20）。
格式不变：`<exec_dir>/approvals.json`，结构 `{"approvals": {id: record}}`。
原子写（tmp + os.replace），id 排序。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ApprovalStoreError(Exception):
    """审批存储失败（损坏/校验失败）。"""


@dataclass
class ApprovalRecord:
    """审批记录。

    ★ 2026-09-15 合并（Founder: 老区不需要了, 但它的字段语义要留住）:
      老区 governance_service 独有 4 个字段已补入 —— subject_type / subject_id /
      artifact_ids / history, 以及 requested_by（用于 requester≠approver 校验）。
      这样它那 84 条真实数据能无损迁过来（见 docs 记录的合并裁决）。
    """

    id: str
    request_id: str
    decision: str = "pending"
    risk_level: str = "low"
    required_roles: list[str] = field(default_factory=list)
    decided_by: str = ""
    comment: str = ""
    applied: bool = False
    applied_at: str | None = None
    created_at: str = ""
    decided_at: str | None = None
    # ── 自老区合并（审批"针对什么" + 溯源）
    subject_type: str = ""          # 审批对象类型（conversation / production_run / artifact …）
    subject_id: str = ""            # 审批对象 ID
    artifact_ids: list[str] = field(default_factory=list)   # 绑定不可变产物
    requested_by: str = ""          # 请求者（decide 校验 requester != approver）
    history: list[dict[str, Any]] = field(default_factory=list)  # append-only 状态变更轨迹

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ApprovalRecord:
        return cls(
            id=str(d.get("id", "")),
            request_id=str(d.get("request_id", "")),
            decision=str(d.get("decision", "pending")),
            risk_level=str(d.get("risk_level", "low")),
            required_roles=list(d.get("required_roles") or []),
            decided_by=str(d.get("decided_by", "")),
            comment=str(d.get("comment", "")),
            applied=bool(d.get("applied", False)),
            applied_at=d.get("applied_at"),
            created_at=str(d.get("created_at") or ""),
            decided_at=d.get("decided_at"),
        )


class ApprovalStore:
    """审批记录持久化（approvals.json）。"""

    _filename = "approvals.json"
    _section = "approvals"

    def __init__(self, exec_dir: str | Path):
        self._dir = Path(exec_dir)

    @property
    def dir(self) -> Path:
        return self._dir

    def _path(self) -> Path:
        return self._dir / self._filename

    def _read_all(self) -> dict[str, dict[str, Any]]:
        path = self._path()
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ApprovalStoreError(f"corrupt approval store: {path}: {exc}") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get(self._section), dict):
            raise ApprovalStoreError(
                f"corrupt approval store: {path}: missing section {self._section!r}")
        return raw[self._section]

    def _write(self, records: dict[str, dict[str, Any]]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path()
        tmp = self._dir / f".{self._filename}.{os.getpid()}.tmp"
        payload = {self._section: dict(sorted(records.items()))}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        os.replace(tmp, path)

    def save(self, record: ApprovalRecord) -> None:
        if not record.created_at:  # 兼容旧 pydantic 模型（created_at 必填 datetime）
            record.created_at = datetime.now(timezone.utc).isoformat()
        records = self._read_all()
        records[record.id] = record.to_dict()
        self._write(records)

    def get(self, approval_id: str) -> ApprovalRecord | None:
        data = self._read_all().get(approval_id)
        return ApprovalRecord.from_dict(data) if data is not None else None

    def list_all(self) -> list[ApprovalRecord]:
        return sorted((ApprovalRecord.from_dict(d) for d in self._read_all().values()),
                      key=lambda r: r.id)

    def count(self) -> int:
        return len(self._read_all())
