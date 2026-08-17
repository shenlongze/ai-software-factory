"""factory-console/audit/audit_query.py — AuditQuery 筛选引擎 (S10-069 G6)。

10 类筛选 (设计 §4): by_project/by_task/by_agent/by_trace/by_event_type/
by_actor/by_decision/by_status/by_risk/by_time → 筛选 + 排序 + 分页 + Top-K。
链式 API: AuditQuery(store).by_project("p1").by_status("failed").apply()

设计: docs/sprint10/S10-069-audit-design.md §4
边界:
- 纯标准库; 时间比较用 ISO 字符串 (UTC ISO 字典序 == 时间序)
- 失败安全: 空 store → []; 非法筛选值 → 空结果 (不抛)
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .audit_event import AuditEvent


class AuditQuery:
    """审计查询 (G6): 筛选 + 排序 + 分页 + Top-K。

    store: AuditStoreProtocol (query 数据源 — events() 读全部);
    每 by_* 返回 self (链式); apply() 执行 → list[AuditEvent]。
    """

    def __init__(self, store: Any = None, events: Optional[Iterable[Any]] = None) -> None:
        self._store = store
        self._source: Optional[list[AuditEvent]] = None
        if events is not None:
            self._source = [
                e if isinstance(e, AuditEvent) else AuditEvent.from_dict(e)
                for e in events
            ]
        self._filters: list[Any] = []
        self._sort_key: Optional[str] = None
        self._sort_desc: bool = False
        self._offset: int = 0
        self._limit: Optional[int] = None
        self._top_k: Optional[int] = None

    # ------------------------------------------------------------ 数据源

    def _all(self) -> list[AuditEvent]:
        """全部事件 (store.events() 或构造时注入 source; 失败安全 → [])。"""
        if self._source is not None:
            return list(self._source)
        if self._store is not None:
            try:
                return list(self._store.events())
            except Exception:  # noqa: BLE001 — 失败安全
                return []
        return []

    # ------------------------------------------------------------ 10 筛选

    def by_project(self, project_id: Any) -> "AuditQuery":
        """按项目筛选 (project_id 相等)。"""
        value = str(project_id or "")
        self._filters.append(lambda e: e.project_id == value)
        return self

    def by_task(self, task_id: Any) -> "AuditQuery":
        """按任务筛选 (task_id 相等)。"""
        value = str(task_id or "")
        self._filters.append(lambda e: e.task_id == value)
        return self

    def by_agent(self, agent_id: Any) -> "AuditQuery":
        """按 Agent 筛选 (agent_id 相等)。"""
        value = str(agent_id or "")
        self._filters.append(lambda e: e.agent_id == value)
        return self

    def by_trace(self, trace_id: Any) -> "AuditQuery":
        """按 trace 筛选 (trace_id 相等 — 决策链重建的输入)。"""
        value = str(trace_id or "")
        self._filters.append(lambda e: e.trace_id == value)
        return self

    def by_event_type(self, event_type: Any) -> "AuditQuery":
        """按事件类型筛选 (event_type 相等; 可传 tuple/list → 任一命中)。"""
        value = str(event_type or "")
        if value:
            self._filters.append(lambda e: e.event_type == value)
        return self

    def by_event_types(self, event_types: Iterable[Any]) -> "AuditQuery":
        """按事件类型集合筛选 (任一命中 — why_debug/who_approved 组合查询)。"""
        values = {str(v) for v in (event_types or []) if str(v)}
        if values:
            self._filters.append(lambda e: e.event_type in values)
        return self

    def by_actor(self, actor_type: Any, actor_id: Any = None) -> "AuditQuery":
        """按执行者筛选 (actor_type 相等; actor_id 可选 — 谁)。"""
        type_value = str(actor_type or "")
        id_value = str(actor_id or "") if actor_id is not None else None
        if type_value:
            self._filters.append(lambda e: e.actor_type == type_value)
        if id_value:
            self._filters.append(lambda e: e.actor_id == id_value)
        return self

    def by_decision(self, decision: Any = None) -> "AuditQuery":
        """按决策筛选: decision 非空 (无参 — 含决策的事件);
        decision 给定 → 相等匹配 (决策审计)。"""
        if decision is None or str(decision) == "":
            self._filters.append(lambda e: bool(e.decision))
        else:
            value = str(decision)
            self._filters.append(lambda e: e.decision == value)
        return self

    def by_status(self, status: Any) -> "AuditQuery":
        """按状态筛选 (status 相等 — 最终结果/生命周期状态)。"""
        value = str(status or "")
        if value:
            self._filters.append(lambda e: e.status == value)
        return self

    def by_risk(self, risk: Any = None) -> "AuditQuery":
        """按风险筛选: risk 非空 (无参 — 有风险标记的事件); 给定 → 相等。"""
        if risk is None or str(risk) == "":
            self._filters.append(lambda e: bool(e.risk))
        else:
            value = str(risk)
            self._filters.append(lambda e: e.risk == value)
        return self

    def by_time(self, start: Any = None, end: Any = None) -> "AuditQuery":
        """按时间窗口筛选 (ISO 字符串比较 — 字典序 == 时间序)。"""
        start_value = str(start or "")
        end_value = str(end or "")
        if start_value:
            self._filters.append(lambda e: e.timestamp >= start_value)
        if end_value:
            self._filters.append(lambda e: e.timestamp <= end_value)
        return self

    # ------------------------------------------------------------ 排序/分页/Top-K

    def sort_by(self, key: str = "timestamp", desc: bool = False) -> "AuditQuery":
        """排序 (缺省 timestamp 升序; desc=True → 最新在前)。"""
        self._sort_key = str(key or "timestamp")
        self._sort_desc = bool(desc)
        return self

    def paginate(self, offset: int = 0, limit: Optional[int] = None) -> "AuditQuery":
        """分页 (offset 跳过; limit 截断 — None → 不截断)。"""
        self._offset = max(0, int(offset or 0))
        self._limit = int(limit) if limit is not None else None
        return self

    def top_k(self, k: int) -> "AuditQuery":
        """Top-K (取前 k 条 — Context Budget 前置筛选)。"""
        self._top_k = max(0, int(k or 0))
        return self

    # ------------------------------------------------------------ 执行

    def apply(self) -> list[AuditEvent]:
        """执行筛选链 → list[AuditEvent] (排序 → Top-K → 分页)。"""
        events = self._all()
        for predicate in self._filters:
            events = [e for e in events if predicate(e)]
        if self._sort_key:
            key = self._sort_key
            events.sort(
                key=lambda e: getattr(e, key, "") or "",
                reverse=self._sort_desc,
            )
        if self._top_k is not None and self._top_k > 0:
            events = events[: self._top_k]
        if self._limit is not None and self._limit >= 0:
            events = events[self._offset : self._offset + self._limit]
        elif self._offset:
            events = events[self._offset :]
        return events

    def count(self) -> int:
        """筛选结果计数 (不取全量 — 统计口径)。"""
        return len(self.apply())

    def to_dicts(self) -> list[dict[str, Any]]:
        """筛选结果 → dict 列表 (API/CLI 视图)。"""
        return [e.to_dict() for e in self.apply()]

    # ------------------------------------------------------------ 静态便捷

    @staticmethod
    def filter_events(
        events: Iterable[Any], **filters: Any
    ) -> list[AuditEvent]:
        """静态筛选: filter_events(events, project_id=..., event_type=...)。

        支持键: project_id/task_id/agent_id/trace_id/event_type/actor_type/
        actor_id/decision/status/risk/start/end — 与 by_* 同语义。
        """
        query = AuditQuery(events=events)
        mapping = {
            "project_id": "by_project",
            "task_id": "by_task",
            "agent_id": "by_agent",
            "trace_id": "by_trace",
            "event_type": "by_event_type",
            "actor_type": "by_actor",
            "status": "by_status",
        }
        for key, value in filters.items():
            if value is None:
                continue
            if key in mapping:
                getattr(query, mapping[key])(value)
            elif key == "actor_id":
                query.by_actor(filters.get("actor_type", ""), value)
            elif key == "decision":
                query.by_decision(value)
            elif key == "risk":
                query.by_risk(value)
            elif key == "start":
                query.by_time(start=value, end=filters.get("end"))
            elif key == "end":
                query.by_time(start=filters.get("start"), end=value)
        return query.apply()
