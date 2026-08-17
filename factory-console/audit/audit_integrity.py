"""factory-console/audit/audit_integrity.py — AuditIntegrity 防篡改校验 (S10-069 G12)。

event_hash + previous_event_hash → tamper-evident 审计链:
- hash_event(event) — sha256 重算 (同 AuditEvent.hash_event 口径)
- verify_event(event) — 单事件 hash 自洽
- verify_chain(events) — 全链校验: 每个事件 hash 自洽 + prev_hash 链完整
  (事件 i 的 previous_event_hash == 事件 i-1 的 event_hash)

设计: docs/sprint10/S10-069-audit-design.md §8
边界:
- 纯标准库; 失败安全: 空链 → True (无事件可校验); 非 AuditEvent/dict 输入跳过
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .audit_event import AuditEvent


def _as_event(item: Any) -> Optional[AuditEvent]:
    """输入归一化: AuditEvent 原样; dict → from_dict; 其余 → None。"""
    if isinstance(item, AuditEvent):
        return item
    if isinstance(item, dict):
        return AuditEvent.from_dict(item)
    return None


class AuditIntegrity:
    """审计完整性 (G12): hash_event / verify_event / verify_chain。

    verify_chain(events) -> bool: 事件按落盘顺序传入; 每事件 event_hash
    必须等于重算值 (sha256(audit_id + canonical_json + prev_hash)) 且
    previous_event_hash 必须等于前一事件 event_hash (首事件可为空)。
    任一断裂 → False (tamper-evident)。
    """

    @staticmethod
    def hash_event(event: Any) -> str:
        """事件 hash (sha256) — AuditEvent.hash_event 同口径 (兼容 dict)。"""
        normalized = _as_event(event)
        if normalized is None:
            return ""
        return normalized.compute_hash()

    @staticmethod
    def verify_event(event: Any) -> bool:
        """单事件完整性: event_hash 非空且等于重算值。"""
        normalized = _as_event(event)
        if normalized is None:
            return False
        return normalized.is_sealed()

    @classmethod
    def verify_chain(cls, events: Iterable[Any]) -> bool:
        """全链校验 (tamper-evident): hash 自洽 + prev_hash 链完整。

        空链 → True (无事件可校验 — 失败安全); 未封存事件 (event_hash 空)
        → False (审计事件必须封存后才可校验)。
        """
        normalized: list[AuditEvent] = [
            e for e in (_as_event(item) for item in (events or []))
            if e is not None
        ]
        if not normalized:
            return True
        previous_hash = ""
        for index, event in enumerate(normalized):
            if not event.event_hash:
                return False
            if event.event_hash != event.compute_hash():
                return False
            expected_prev = previous_hash if index > 0 else ""
            if event.previous_event_hash != expected_prev:
                return False
            previous_hash = event.event_hash
        return True

    @classmethod
    def verify(cls, events: Iterable[Any]) -> dict[str, Any]:
        """校验结果详情 (store.verify / API stats 用): 逐事件报告。"""
        normalized: list[AuditEvent] = [
            e for e in (_as_event(item) for item in (events or []))
            if e is not None
        ]
        broken: list[dict[str, Any]] = []
        previous_hash = ""
        for index, event in enumerate(normalized):
            issues: list[str] = []
            if not event.event_hash:
                issues.append("missing event_hash")
            elif event.event_hash != event.compute_hash():
                issues.append("hash mismatch")
            expected_prev = previous_hash if index > 0 else ""
            if event.previous_event_hash != expected_prev:
                issues.append("previous_event_hash broken")
            if issues:
                broken.append({"index": index, "audit_id": event.audit_id,
                               "issues": issues})
            previous_hash = event.event_hash
        return {
            "ok": not broken,
            "verified": len(normalized) - len(broken),
            "total": len(normalized),
            "broken": broken,
        }
