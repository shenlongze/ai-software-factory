"""factory-console/api/audit.py — S10-069 Audit Intelligence API 路由函数。

纯函数路由 (无 Web 依赖, 同 debug.py/memory.py 模式 — 未来 FastAPI 薄层
做 HTTP 绑定):

- audit_events:   GET  /api/audit/events     {workspace?, project?, event_type?,
                   limit?} → {ok, data: {events, count, total}}
- audit_trace:    GET  /api/audit/trace/{trace_id} {workspace?} → {ok, data}
- audit_chain:    GET  /api/audit/chain/{trace_id}  {workspace?} → 决策链
- audit_task:     GET  /api/audit/task/{task_id}    {workspace?} → 任务事件
- audit_agent:    GET  /api/audit/agent/{agent_id}  {workspace?} → Agent 事件
- audit_decisions: GET /api/audit/decisions  {workspace?, project?} → 决策事件
- audit_explain:  POST /api/audit/explain   {question, workspace?, task_id?,
                   agent_id?, project?} → 结构化"为什么" (默认不调 LLM)
- audit_cost:     GET  /api/audit/cost/{project_id} {workspace?} → 成本审计
- audit_stats:    GET  /api/audit/stats     {workspace?} → 统计
- audit_export:   POST /api/audit/export    {workspace?, project?} → 导出

错误语义 (失败安全铁律): 异常 → {"ok": False, "error": str} — 绝不裸抛。

设计: docs/sprint10/S10-069-audit-design.md §10
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..audit import AuditStore
from ..memory.experience_store import DEFAULT_WORKSPACE

__all__ = [
    "AuditChainRequest",
    "AuditCostRequest",
    "AuditDecisionsRequest",
    "AuditEventsRequest",
    "AuditExplainRequest",
    "AuditExportRequest",
    "AuditResponse",
    "AuditStatsRequest",
    "AuditTaskRequest",
    "AuditTraceRequest",
    "audit_agent",
    "audit_chain",
    "audit_cost",
    "audit_decisions",
    "audit_events",
    "audit_explain",
    "audit_export",
    "audit_stats",
    "audit_task",
    "audit_trace",
]


# ---------------------------------------------------------------- Schemas

class AuditEventsRequest(BaseModel):
    """GET /api/audit/events 请求体: workspace + project/event_type/limit 筛选。"""

    workspace: Optional[str] = None
    project: Optional[str] = None
    event_type: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=1000)


class AuditTraceRequest(BaseModel):
    """GET /api/audit/trace/{trace_id} 请求体: workspace。"""

    trace_id: str = ""
    workspace: Optional[str] = None


class AuditChainRequest(BaseModel):
    """GET /api/audit/chain/{trace_id} 请求体: workspace。"""

    trace_id: str = ""
    workspace: Optional[str] = None


class AuditTaskRequest(BaseModel):
    """GET /api/audit/task/{task_id} 请求体: workspace。"""

    task_id: str = ""
    workspace: Optional[str] = None


class AuditAgentRequest(BaseModel):
    """GET /api/audit/agent/{agent_id} 请求体: workspace。"""

    agent_id: str = ""
    workspace: Optional[str] = None


class AuditDecisionsRequest(BaseModel):
    """GET /api/audit/decisions 请求体: workspace + project。"""

    workspace: Optional[str] = None
    project: Optional[str] = None


class AuditExplainRequest(BaseModel):
    """POST /api/audit/explain 请求体: 问题 + 可选定位参数。"""

    question: str = ""
    workspace: Optional[str] = None
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    project: Optional[str] = None


class AuditCostRequest(BaseModel):
    """GET /api/audit/cost/{project_id} 请求体: workspace。"""

    project_id: str = ""
    workspace: Optional[str] = None


class AuditStatsRequest(BaseModel):
    """GET /api/audit/stats 请求体: workspace。"""

    workspace: Optional[str] = None


class AuditExportRequest(BaseModel):
    """POST /api/audit/export 请求体: workspace + project (可选过滤)。"""

    workspace: Optional[str] = None
    project: Optional[str] = None


class AuditResponse(BaseModel):
    """统一响应包装: ok + data (成功) / error (失败) — HTTP 层可映射。"""

    ok: bool = True
    data: Optional[Any] = None
    error: Optional[str] = None


# ---------------------------------------------------------------- 内部

def _to_response(data: Any, error: Optional[str] = None) -> dict[str, Any]:
    """响应模型 → dict (Pydantic v2 model_dump — HTTP 层直接序列化)。"""
    return AuditResponse(ok=error is None, data=data, error=error).model_dump()


def _workspace(workspace: Any = None) -> Path:
    """workspace → Path (None/空 → 默认工厂根 ~/.factory)。"""
    return Path(workspace) if workspace else DEFAULT_WORKSPACE


def _store(workspace: Any = None) -> AuditStore:
    """AuditStore 实例 (workspace 口径同 Core/CLI)。"""
    return AuditStore(_workspace(workspace))


def _events_payload(events: list[Any], limit: int = 50) -> dict[str, Any]:
    """事件列表 → API 载荷 (事件 dict + count/total — 分页视图)。"""
    dicts = [e.to_dict() for e in events]
    return {
        "events": dicts[: int(limit or 50)],
        "count": min(len(dicts), int(limit or 50)),
        "total": len(dicts),
    }


# ---------------------------------------------------------------- 10 端点

def audit_events(
    workspace: Any = None,
    project: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 50,
) -> dict[str, Any]:
    """GET /api/audit/events — 审计记录列表 (按时间倒序, 最新在前)。

    {workspace?, project?, event_type?, limit?} → {ok, data: {events, count,
    total}, error}。筛选空 → 全部事件。
    """
    try:
        store = _store(workspace)
        events = store.events()
        if project:
            value = str(project)
            events = [e for e in events if e.project_id == value]
        if event_type:
            value = str(event_type)
            events = [e for e in events if e.event_type == value]
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return _to_response(_events_payload(events, limit=limit))
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"审计记录查询失败: {exc}")


def audit_trace(trace_id: str = "", workspace: Any = None) -> dict[str, Any]:
    """GET /api/audit/trace/{trace_id} — 审计追踪 (某 trace 全链路事件)。"""
    try:
        target = str(trace_id or "").strip()
        if not target:
            return _to_response(None, "trace_id 不能为空")
        store = _store(workspace)
        events = store.query(trace_id=target)
        events.sort(key=lambda e: e.timestamp)
        return _to_response(_events_payload(events, limit=1000))
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"审计追踪失败: {exc}")


def audit_chain(trace_id: str = "", workspace: Any = None) -> dict[str, Any]:
    """GET /api/audit/chain/{trace_id} — 审计决策链 (根→子→相关→最终)。"""
    try:
        target = str(trace_id or "").strip()
        if not target:
            return _to_response(None, "trace_id 不能为空")
        store = _store(workspace)
        return _to_response(store.get_chain(target))
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"审计决策链失败: {exc}")


def audit_task(task_id: str = "", workspace: Any = None) -> dict[str, Any]:
    """GET /api/audit/task/{task_id} — 审计任务 (某任务全生命周期事件)。"""
    try:
        target = str(task_id or "").strip()
        if not target:
            return _to_response(None, "task_id 不能为空")
        store = _store(workspace)
        events = store.query(task_id=target)
        events.sort(key=lambda e: e.timestamp)
        return _to_response(_events_payload(events, limit=1000))
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"审计任务失败: {exc}")


def audit_agent(agent_id: str = "", workspace: Any = None) -> dict[str, Any]:
    """GET /api/audit/agent/{agent_id} — 审计 Agent (某 Agent 全部事件)。"""
    try:
        target = str(agent_id or "").strip()
        if not target:
            return _to_response(None, "agent_id 不能为空")
        store = _store(workspace)
        events = store.query(agent_id=target)
        events.sort(key=lambda e: e.timestamp)
        return _to_response(_events_payload(events, limit=1000))
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"审计Agent失败: {exc}")


def audit_decisions(
    workspace: Any = None, project: Optional[str] = None
) -> dict[str, Any]:
    """GET /api/audit/decisions — 审计决策 (含 decision 字段的事件)。"""
    try:
        store = _store(workspace)
        events = [e for e in store.events() if e.decision or e.decision_reason]
        if project:
            value = str(project)
            events = [e for e in events if e.project_id == value]
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return _to_response(_events_payload(events, limit=500))
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"审计决策查询失败: {exc}")


def audit_explain(
    question: str = "",
    workspace: Any = None,
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    project: Optional[str] = None,
) -> dict[str, Any]:
    """POST /api/audit/explain — 结构化"为什么" (默认不调 LLM)。

    {question, workspace?, task_id?, agent_id?, project?} → {ok, data:
    {question, answer_type, summary, evidence, decision, related_events,
    cost, policy, approval, outcome}, error}。
    """
    try:
        from ..audit import AuditExplain

        explainer = AuditExplain(_store(workspace))
        return _to_response(
            explainer.explain(
                question,
                task_id=task_id,
                agent_id=agent_id,
                project=project,
            )
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"审计解释失败: {exc}")


def audit_cost(project_id: str = "", workspace: Any = None) -> dict[str, Any]:
    """GET /api/audit/cost/{project_id} — 项目成本审计 (事件聚合 + reference)。"""
    try:
        from ..audit import AuditExplain

        explainer = AuditExplain(_store(workspace))
        return _to_response(explainer.why_cost(str(project_id or "")))
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"成本审计失败: {exc}")


def audit_stats(workspace: Any = None) -> dict[str, Any]:
    """GET /api/audit/stats — 审计统计 (total + by_type/status/actor + integrity)。"""
    try:
        store = _store(workspace)
        return _to_response(store.stats())
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"审计统计失败: {exc}")


def audit_export(
    workspace: Any = None, project: Optional[str] = None
) -> dict[str, Any]:
    """POST /api/audit/export — 导出审计 (全部/项目事件 dict 列表)。"""
    try:
        store = _store(workspace)
        payload = store.export(project_id=project)
        return _to_response({"export": payload, "count": len(payload),
                             "file": str(store.file())})
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"审计导出失败: {exc}")
