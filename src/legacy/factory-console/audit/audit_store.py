"""factory-console/audit/audit_store.py — AuditStore 统一审计存储 (S10-069 G2)。

append/get/query/get_chain/export/stats/verify — 落盘 audit_events.json
(workspace/audit/audit_events.json, 缺省 ~/.factory/audit/audit_events.json)。

- append: 脱敏 (纵深防御) + 封存 (previous_event_hash + event_hash 链) +
  原子写 (tmp + os.replace) — tamper-evident 基础
- 接口化: AuditStoreProtocol — 未来可换 SQLite/PG/ES (当前 JSON, 设计 §3)
- 失败安全: 读 (缺失/损坏 → []) / 写 (异常 → 不抛, 记录仍返回)

设计: docs/sprint10/S10-069-audit-design.md §3
边界:
- 纯标准库 (json/os/hashlib/pathlib), 零新依赖
- 只追加语义: append 不修改历史条目 (审计日志铁律)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

from .audit_chain import AuditDecisionChain
from .audit_context import AuditContextBudget
from .audit_event import AuditEvent, redact
from .audit_integrity import AuditIntegrity
from .audit_query import AuditQuery

#: 审计存储文件名 (workspace/audit/audit_events.json)
AUDIT_FILE_NAME = "audit_events.json"

#: 缺省审计存储文件 (~/.factory/audit/audit_events.json)
DEFAULT_AUDIT_FILE = Path.home() / ".factory" / "audit" / AUDIT_FILE_NAME


@runtime_checkable
class AuditStoreProtocol(Protocol):
    """AuditStore 接口 (设计 §3 — 未来 SQLite/PG/ES 实现同契约)。

    契约: append(event) -> AuditEvent; get(audit_id) -> Optional[AuditEvent];
    query(**filters) -> list[AuditEvent]; get_chain(trace_id) -> dict;
    export(project_id) -> list[dict]; stats() -> dict; verify() -> dict;
    events() -> list[AuditEvent] (全量, 查询引擎数据源)。
    """

    def append(self, event: Any) -> AuditEvent: ...

    def get(self, audit_id: str) -> Optional[AuditEvent]: ...

    def query(self, **filters: Any) -> list[AuditEvent]: ...

    def get_chain(self, trace_id: str) -> dict[str, Any]: ...

    def export(self, project_id: Optional[str] = None) -> list[dict[str, Any]]: ...

    def stats(self) -> dict[str, Any]: ...

    def verify(self) -> dict[str, Any]: ...

    def events(self) -> list[AuditEvent]: ...


class AuditStore:
    """统一审计存储 (JSON 实现): append/get/query/get_chain/export/stats/verify。"""

    FILE_NAME = AUDIT_FILE_NAME

    def __init__(self, workspace: Any = None, file: Any = None) -> None:
        """workspace → workspace/audit/audit_events.json; file 显式覆盖 (测试)。"""
        if file is not None:
            self._file: Path = Path(file)
        elif workspace is not None:
            self._file = Path(workspace) / "audit" / AUDIT_FILE_NAME
        else:
            self._file = DEFAULT_AUDIT_FILE
        self._query_engine = AuditQuery(self)
        self._chain = AuditDecisionChain(self)
        self._budget = AuditContextBudget()

    # ------------------------------------------------------------ 写

    def append(self, event: Any) -> AuditEvent:
        """追加事件 (设计 §3): 归一化 → 脱敏 → 封存 (hash 链) → 原子落盘。

        dict → AuditEvent.from_dict; event_type 校验在 AuditEvent.create
        (直接传 AuditEvent 实例不校验类型 — 信任调用方/测试构造)。
        返回封存后事件 (落盘失败也返回 — 失败安全)。
        """
        normalized = (
            event if isinstance(event, AuditEvent) else AuditEvent.from_dict(event)
        )
        # 纵深防御: 自由 dict 字段就地脱敏 (即使调用方未脱敏)
        normalized.evidence = redact(normalized.evidence)
        normalized.approval = redact(normalized.approval)
        normalized.result = redact(normalized.result)
        normalized.impact = redact(normalized.impact)
        normalized.metadata = redact(normalized.metadata)
        # JSON 归一化: 保证落盘/重读/canonical hash 三者一致 (default=str)
        payload = json.loads(
            json.dumps(
                normalized.to_dict(redact_sensitive=False),
                ensure_ascii=False,
                default=str,
            )
        )
        normalized = AuditEvent.from_dict(payload)
        records = self.load()
        previous_hash = records[-1].get("event_hash", "") if records else ""
        normalized.seal(previous_event_hash=previous_hash)
        records.append(normalized.to_dict(redact_sensitive=False))
        self.save(records)
        return normalized

    def save(self, records: Any) -> None:
        """整表落盘 (原子写: tmp + os.replace; 失败安全 — 审计不阻断调用流)。"""
        if not isinstance(records, list):
            records = []
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._file.with_suffix(self._file.suffix + ".tmp")
            tmp.write_text(
                json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp, self._file)
        except Exception:  # noqa: BLE001 — 失败安全
            pass

    # ------------------------------------------------------------ 读

    def load(self) -> list[dict[str, Any]]:
        """读回全部事件 dict (缺失/损坏 → [], 失败安全)。"""
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except Exception:  # noqa: BLE001 — 失败安全
            pass
        return []

    def events(self) -> list[AuditEvent]:
        """全部事件 (AuditEvent 列表 — 查询引擎/链重建数据源)。"""
        return [AuditEvent.from_dict(d) for d in self.load()]

    def records(self) -> list[dict[str, Any]]:
        """全部事件 dict (load 别名 — CLI/API 视图)。"""
        return self.load()

    def get(self, audit_id: str) -> Optional[AuditEvent]:
        """按 audit_id 取事件; 未找到 → None。"""
        target = str(audit_id or "")
        if not target:
            return None
        for event in self.events():
            if event.audit_id == target:
                return event
        return None

    # ------------------------------------------------------------ 查询

    def query(self, **filters: Any) -> list[AuditEvent]:
        """筛选查询 (AuditQuery 引擎): query(project_id=..., status=...)。"""
        return AuditQuery.filter_events(self.events(), **filters)

    def get_chain(self, trace_id: str) -> dict[str, Any]:
        """决策链重建 (AuditDecisionChain.get_chain — 设计 §5)。"""
        return self._chain.get_chain(trace_id)

    def export(self, project_id: Optional[str] = None) -> list[dict[str, Any]]:
        """导出: 全部事件 dict (project_id 给定 → 仅该项目, 设计 §13)。"""
        events = self.events()
        if project_id:
            value = str(project_id)
            events = [e for e in events if e.project_id == value]
        return [e.to_dict() for e in events]

    # ------------------------------------------------------------ 统计/校验

    def stats(self) -> dict[str, Any]:
        """统计: total + by_event_type/by_status/by_actor_type/by_project +
        verify 摘要 (G12 防篡改可见性)。"""
        events = self.events()
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        by_actor: dict[str, int] = {}
        by_project: dict[str, int] = {}
        for event in events:
            by_type[event.event_type or "?"] = by_type.get(event.event_type or "?", 0) + 1
            by_status[event.status or "?"] = by_status.get(event.status or "?", 0) + 1
            by_actor[event.actor_type or "?"] = by_actor.get(event.actor_type or "?", 0) + 1
            by_project[event.project_id or "?"] = by_project.get(event.project_id or "?", 0) + 1
        verify = AuditIntegrity.verify(events)
        return {
            "total": len(events),
            "by_event_type": by_type,
            "by_status": by_status,
            "by_actor_type": by_actor,
            "by_project": by_project,
            "integrity": verify,
            "file": str(self._file),
        }

    def verify(self) -> dict[str, Any]:
        """全链完整性校验 (tamper-evident — AuditIntegrity.verify_chain)。"""
        events = self.events()
        return {
            "ok": AuditIntegrity.verify_chain(events),
            **AuditIntegrity.verify(events),
            "file": str(self._file),
        }

    # ------------------------------------------------------------ 工具

    def budget(self) -> AuditContextBudget:
        """Context Budget 实例 (查询结果 → LLM Context 保护)。"""
        return self._budget

    def file(self) -> Path:
        """落盘文件路径。"""
        return Path(self._file)
