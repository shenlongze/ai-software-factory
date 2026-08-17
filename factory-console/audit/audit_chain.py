"""factory-console/audit/audit_chain.py — AuditDecisionChain 决策链重建 (S10-069 G5)。

get_chain(trace_id) -> dict — 从 trace_id + correlation_id + parent_event_id
重建完整决策链: {root_event, children, related_events, final_outcome, chain}。

- root_event: 链根事件 (无 parent_event_id 或链内首事件)
- children: root 的直接子事件 (parent_event_id == root.audit_id; 含 tree 深度)
- related_events: 共享 correlation_id 的相关事件 (跨 trace 关联)
- final_outcome: 链末事件的 status/result (最终结果)
- chain: 按时间排序的完整事件序列 (含链内层级树)

设计: docs/sprint10/S10-069-audit-design.md §5
边界:
- 纯标准库; 失败安全: 无事件 → 全空结构; 链内 parent 缺失 → 挂 root
"""

from __future__ import annotations

from typing import Any, Optional

from .audit_event import AuditEvent


def _to_event(item: Any) -> Optional[AuditEvent]:
    """输入归一化 (AuditEvent / dict → AuditEvent; 其余 → None)。"""
    if isinstance(item, AuditEvent):
        return item
    if isinstance(item, dict):
        return AuditEvent.from_dict(item)
    return None


class AuditDecisionChain:
    """决策链 (G5): 从 trace_id 重建 Product→Plan→Task→Agent→…→Delivery。

    get_chain(trace_id) -> dict {root_event, children, related_events,
    final_outcome, chain}。build(trace_id) — 同 get_chain (别名, 设计 §5)。
    """

    def __init__(self, store: Any = None) -> None:
        self._store = store

    # ------------------------------------------------------------ 数据源

    def _trace_events(self, trace_id: str) -> list[AuditEvent]:
        """trace 内全部事件 (store 查询或注入 events 全量过滤; 时间升序)。"""
        events: list[AuditEvent] = []
        if self._store is not None:
            try:
                if hasattr(self._store, "events"):
                    for item in self._store.events():
                        candidate = _to_event(item)
                        if candidate is not None:
                            events.append(candidate)
                else:  # AuditStoreProtocol 兼容: 无 events → query(trace_id)
                    for item in self._store.query(trace_id=trace_id):
                        candidate = _to_event(item)
                        if candidate is not None:
                            events.append(candidate)
            except Exception:  # noqa: BLE001 — 失败安全
                events = []
        events = [e for e in events if e.trace_id == trace_id]
        events.sort(key=lambda e: e.timestamp)
        return events

    # ------------------------------------------------------------ 重建

    def build(self, trace_id: str) -> dict[str, Any]:
        """重建决策链 (设计 §5: 根→子→相关→最终)。"""
        trace = str(trace_id or "")
        events = self._trace_events(trace)
        if not events:
            return {
                "trace_id": trace,
                "root_event": None,
                "children": [],
                "related_events": [],
                "final_outcome": None,
                "chain": [],
                "count": 0,
            }

        # root: 无 parent_event_id 的链内首事件 (缺省 → 时间首事件)
        root: Optional[AuditEvent] = None
        for event in events:
            if not event.parent_event_id:
                root = event
                break
        if root is None:
            root = events[0]

        by_id = {e.audit_id: e for e in events}

        def _tree(node: AuditEvent, depth: int = 0) -> dict[str, Any]:
            kids = [
                e for e in events
                if e.parent_event_id == node.audit_id
            ]
            kids.sort(key=lambda e: e.timestamp)
            return {
                "event": node.to_dict(),
                "depth": depth,
                "children": [_tree(k, depth + 1) for k in kids],
            }

        root_children = [
            e for e in events if e.parent_event_id == root.audit_id
        ]
        root_children.sort(key=lambda e: e.timestamp)

        # related: 共享 correlation_id 且不在 trace 内的事件
        related: list[AuditEvent] = []
        if root.correlation_id:
            try:
                if self._store is not None and hasattr(self._store, "events"):
                    for item in self._store.events():
                        candidate = _to_event(item)
                        if (
                            candidate is not None
                            and candidate.correlation_id == root.correlation_id
                            and candidate.trace_id != trace
                        ):
                            related.append(candidate)
            except Exception:  # noqa: BLE001 — 失败安全
                related = []

        final = events[-1]
        final_outcome: dict[str, Any] = {
            "event_type": final.event_type,
            "status": final.status,
            "result": final.result,
            "timestamp": final.timestamp,
            "audit_id": final.audit_id,
        }

        chain = [_tree(e) for e in events if e.parent_event_id == ""]
        if not chain:
            chain = [_tree(events[0])]

        return {
            "trace_id": trace,
            "root_event": root.to_dict(),
            "children": [c.to_dict() for c in root_children],
            "related_events": [r.to_dict() for r in related],
            "final_outcome": final_outcome,
            "chain": chain,
            "count": len(events),
        }

    def get_chain(self, trace_id: str) -> dict[str, Any]:
        """get_chain(trace_id) — 验收入口 (build 别名)。"""
        return self.build(trace_id)

    def depth(self, trace_id: str) -> int:
        """链深度 (层级树最大深度; 无事件 → 0)。"""
        chain = self.build(trace_id)
        if not chain.get("chain"):
            return 0
        max_depth = 0

        def _walk(nodes: list[dict[str, Any]], depth: int) -> None:
            nonlocal max_depth
            for node in nodes:
                max_depth = max(max_depth, depth)
                _walk(node.get("children") or [], depth + 1)

        _walk(chain["chain"], 1)
        return max_depth
