"""factory-console/session/actions_audit.py — 审计动作 (R1, v1.1.254).

从 actions.py (4991 行巨兽) 拆出: 审计/追溯/决策/成本/导出/统计 (自包含, 仅用自身 _audit_* helper)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .action import (
    STATUS_CANCELLED,
    STATUS_ERROR,
    STATUS_OK,
    ActionResult,
    ExecutionContext,
)


def _audit_params(context) -> dict:
    """取 audit action 参数 (intent.params 优先; 兼容测试 FakeContext.params)。"""
    intent = getattr(context, "intent", None)
    if intent is not None and getattr(intent, "params", None):
        return intent.params
    return getattr(context, "params", None) or {}


def _audit_workspace(context) -> Path:
    """audit action 工作区 (context.workspace 缺省 → ~/.factory)。"""
    return Path(getattr(context, "workspace", None) or DEFAULT_WORKSPACE)


def _audit_store(context) -> Any:
    """AuditStore 实例 (工作区同 audit action 口径)。"""
    from ..audit import AuditStore

    return AuditStore(_audit_workspace(context))


def _audit_events_lines(events, header: str, limit: int = 20) -> list[str]:
    """事件列表 → 展示行 (类型/时间/摘要 — 统一 CLI 视图)。"""
    lines = [header]
    for event in events[:limit]:
        digest = event.decision_reason or event.decision or event.action or ""
        lines.append(
            f"• [{event.event_type}] {event.timestamp[:19]} "
            f"{event.task_id or event.agent_id or event.project_id or ''} "
            f"{digest[:60]}"
        )
    if not events:
        lines.append("无审计事件。")
    return lines


def audit_events(context: ExecutionContext) -> ActionResult:
    """审计记录 (S10-069): \"查看审计记录/审计记录\" → 事件列表 (按时间倒序)。"""
    context.require("user")
    params = _audit_params(context)
    try:
        store = _audit_store(context)
        events = store.events()
        project = str(params.get("project") or "")
        event_type = str(params.get("event_type") or "")
        if project:
            events = [e for e in events if e.project_id == project]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        events.sort(key=lambda e: e.timestamp, reverse=True)
        limit = int(params.get("limit") or 20)
        lines = _audit_events_lines(
            events, f"审计记录 (共 {len(events)} 条, 最新在前):", limit=limit)
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data={"count": len(events)})
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计记录查询失败: {exc}", error=str(exc))


def audit_trace(context: ExecutionContext) -> ActionResult:
    """审计追踪 (S10-069): \"审计追踪/查看审计链路\" (参数 trace_id)。"""
    context.require("user")
    params = _audit_params(context)
    try:
        store = _audit_store(context)
        trace_id = str(params.get("trace_id") or "")
        if not trace_id:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message="缺少 trace_id 参数 (如: 审计追踪 <trace_id>)",
                error="no trace_id")
        events = store.query(trace_id=trace_id)
        events.sort(key=lambda e: e.timestamp)
        lines = _audit_events_lines(
            events, f"审计追踪 {trace_id} (共 {len(events)} 条):")
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data={"trace_id": trace_id, "count": len(events)})
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计追踪失败: {exc}", error=str(exc))


def audit_chain(context: ExecutionContext) -> ActionResult:
    """审计决策链 (S10-069): \"审计决策链\" (参数 trace_id) → 根→子→相关→最终。"""
    context.require("user")
    params = _audit_params(context)
    try:
        store = _audit_store(context)
        trace_id = str(params.get("trace_id") or "")
        if not trace_id:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message="缺少 trace_id 参数 (如: 审计决策链 <trace_id>)",
                error="no trace_id")
        chain = store.get_chain(trace_id)
        root = chain.get("root_event") or {}
        lines = [f"审计决策链 {trace_id} (共 {chain.get('count')} 个事件):"]
        lines.append(f"• 根事件: [{root.get('event_type')}] "
                     f"{root.get('timestamp', '')[:19]} "
                     f"{(root.get('decision_reason') or root.get('decision') or '')[:60]}")
        for child in chain.get("children") or []:
            lines.append(f"  ├─ [{child.get('event_type')}] "
                         f"{child.get('timestamp', '')[:19]} "
                         f"{(child.get('decision_reason') or child.get('decision') or '')[:50]}")
        outcome = chain.get("final_outcome") or {}
        lines.append(f"• 最终: {outcome.get('event_type')} — "
                     f"状态 {outcome.get('status') or '未知'}")
        if chain.get("related_events"):
            lines.append(f"• 相关事件 (跨 trace): {len(chain['related_events'])} 条")
        if not chain.get("count"):
            lines = [f"审计决策链 {trace_id}: 无事件 (trace 不存在)。"]
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines), data=chain)
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计决策链失败: {exc}", error=str(exc))


def audit_decision(context: ExecutionContext) -> ActionResult:
    """审计决策 (S10-069): \"审计决策\" → 含 decision 字段的事件。"""
    context.require("user")
    params = _audit_params(context)
    try:
        store = _audit_store(context)
        events = [e for e in store.events() if e.decision or e.decision_reason]
        project = str(params.get("project") or "")
        if project:
            events = [e for e in events if e.project_id == project]
        events.sort(key=lambda e: e.timestamp, reverse=True)
        lines = [f"审计决策 (共 {len(events)} 条):"]
        for event in events[:20]:
            lines.append(
                f"• [{event.event_type}] {event.timestamp[:19]} "
                f"决策={event.decision or '—'} 原因={event.decision_reason[:60]}")
        if not events:
            lines.append("无决策事件。")
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data={"count": len(events)})
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计决策查询失败: {exc}", error=str(exc))


def audit_explain(context: ExecutionContext) -> ActionResult:
    """审计解释 (S10-069): \"为什么创建这个任务/为什么选择这个Agent/为什么停了\"
    → 结构化\"为什么\" (AuditExplain, 默认不调 LLM)。"""
    context.require("user")
    params = _audit_params(context)
    try:
        from ..audit import AuditExplain

        store = _audit_store(context)
        intent = getattr(context, "intent", None)
        question = str(params.get("question") or "")
        if not question and intent is not None and getattr(intent, "raw", ""):
            question = intent.raw
        if not question:
            question = "为什么"
        task_id = str(params.get("task_id") or "")
        agent_id = str(params.get("agent_id") or "")
        project = str(params.get("project") or "") or str(
            getattr(context, "project", None) or "")
        debug_id = str(params.get("debug_id") or "")
        explainer = AuditExplain(store)
        result = explainer.explain(
            question,
            task_id=task_id or None,
            agent_id=agent_id or None,
            project=project or None,
            debug_id=debug_id or None,
        )
        lines = [
            f"审计解释 ({result.get('answer_type')}):",
            result.get("summary", ""),
        ]
        if result.get("decision"):
            decision = result["decision"]
            lines.append(f"• 决策: {decision.get('decision') or '—'} — "
                         f"{decision.get('reason') or ''}")
        if result.get("approval"):
            approval = result["approval"]
            reviewer = approval.get("reviewer") or approval.get("actor_id") or "?"
            lines.append(f"• 审批: {reviewer} ({approval.get('decision') or 'approved'})")
        cost = result.get("cost") or {}
        if cost.get("events"):
            lines.append(f"• 成本: ${cost.get('total', 0.0):.4f} "
                         f"({cost.get('events')} 条事件)")
        lines.append(f"• 相关事件: {len(result.get('related_events') or [])} 条")
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines), data=result)
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计解释失败: {exc}", error=str(exc))


def audit_task(context: ExecutionContext) -> ActionResult:
    """审计任务 (S10-069): \"审计任务\" (参数 task_id) → 任务全生命周期事件。"""
    context.require("user")
    params = _audit_params(context)
    try:
        store = _audit_store(context)
        task_id = str(params.get("task_id") or "")
        if not task_id:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message="缺少 task_id 参数 (如: 审计任务 <task_id>)",
                error="no task_id")
        events = store.query(task_id=task_id)
        events.sort(key=lambda e: e.timestamp)
        lines = _audit_events_lines(
            events, f"审计任务 {task_id} (共 {len(events)} 条):")
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data={"task_id": task_id, "count": len(events)})
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计任务失败: {exc}", error=str(exc))


def audit_agent(context: ExecutionContext) -> ActionResult:
    """审计Agent (S10-069): \"审计Agent\" (参数 agent_id) → Agent 全部事件。"""
    context.require("user")
    params = _audit_params(context)
    try:
        store = _audit_store(context)
        agent_id = str(params.get("agent_id") or "")
        if not agent_id:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message="缺少 agent_id 参数 (如: 审计Agent <agent_id>)",
                error="no agent_id")
        events = store.query(agent_id=agent_id)
        events.sort(key=lambda e: e.timestamp)
        lines = _audit_events_lines(
            events, f"审计Agent {agent_id} (共 {len(events)} 条):")
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data={"agent_id": agent_id, "count": len(events)})
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计Agent失败: {exc}", error=str(exc))


def audit_cost(context: ExecutionContext) -> ActionResult:
    """成本审计 (S10-069): \"查看项目成本审计/成本审计\" → 项目成本事件聚合。"""
    context.require("user")
    params = _audit_params(context)
    try:
        from ..audit import AuditExplain

        store = _audit_store(context)
        project_id = str(params.get("project_id") or "") or str(
            params.get("project") or "") or str(
            getattr(context, "project", None) or "")
        explainer = AuditExplain(store)
        result = explainer.why_cost(project_id)
        cost = result.get("cost") or {}
        lines = [
            f"成本审计 (项目 {project_id or '(全部)'}):",
            f"• 成本事件: {cost.get('events', 0)} 条, "
            f"合计 ${cost.get('total', 0.0):.4f}",
        ]
        if cost.get("references"):
            lines.append(f"• CostLedger 引用: {', '.join(cost['references'][:5])}")
        if cost.get("ledger_total") is not None:
            lines.append(f"• CostLedger 聚合: ${cost['ledger_total']:.4f}")
        if not cost.get("events"):
            lines.append("无成本事件 (LLM_CALL/TOOL_CALL/AGENT_*)。")
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines), data=cost)
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"成本审计失败: {exc}", error=str(exc))


def audit_export(context: ExecutionContext) -> ActionResult:
    """导出审计 (S10-069): \"导出审计\" → audit_export.json 落盘 (项目过滤可选)。"""
    context.require("user")
    params = _audit_params(context)
    try:
        store = _audit_store(context)
        project = str(params.get("project") or "")
        payload = store.export(project_id=project or None)
        ws = _audit_workspace(context)
        out_file = ws / "audit" / "audit_export.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        lines = [
            f"导出审计完成 (共 {len(payload)} 条):",
            f"• 文件: {out_file}",
            f"• 项目过滤: {project or '(全部)'}",
        ]
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data={"file": str(out_file), "count": len(payload)})
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"导出审计失败: {exc}", error=str(exc))


def audit_stats(context: ExecutionContext) -> ActionResult:
    """审计统计 (S10-069): \"审计统计\" → total + by_type/status/actor + 完整性。"""
    context.require("user")
    try:
        store = _audit_store(context)
        stats = store.stats()
        integrity = stats.get("integrity") or {}
        lines = [
            f"审计统计 (共 {stats['total']} 条事件):",
            "按事件类型: " + ", ".join(
                f"{k}={v}" for k, v in (stats.get("by_event_type") or {}).items())
            if stats.get("by_event_type") else "按事件类型: 无",
            "按状态: " + ", ".join(
                f"{k}={v}" for k, v in (stats.get("by_status") or {}).items())
            if stats.get("by_status") else "按状态: 无",
            "按执行者: " + ", ".join(
                f"{k}={v}" for k, v in (stats.get("by_actor_type") or {}).items())
            if stats.get("by_actor_type") else "按执行者: 无",
            f"完整性: {'通过' if integrity.get('ok') else '异常'} "
            f"(校验 {integrity.get('verified')}/{integrity.get('total')})",
            f"存储: {stats['file']}",
        ]
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines), data=stats)
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计统计失败: {exc}", error=str(exc))
