"""factory-console/audit/audit_explain.py — AuditExplain 结构化"为什么" (S10-069 G3/G7)。

why_created/why_agent/why_stopped/why_debug/why_cost/who_approved →
{summary, evidence, decision, related_events, cost, policy, approval, outcome}。
默认结构化 (不调 LLM — 设计 §13); 可选 LLM 由上层接入 (ContextBudget 保护)。

设计: docs/sprint10/S10-069-audit-design.md §6
- 关联 (reference 不复制): CostLedger → cost (懒加载复用, 失败安全);
  ReviewGate/approval 字段 → who_approved; memory_reference → 经验引用
边界:
- 纯标准库; 失败安全: 无事件 → 空结构 + 明确 summary (不抛)
"""

from __future__ import annotations

from typing import Any, Optional

from .audit_event import AuditEvent
from .audit_query import AuditQuery


def _event_list(items: Any) -> list[AuditEvent]:
    """AuditEvent/dict 混合 → AuditEvent 列表 (失败安全)。"""
    out: list[AuditEvent] = []
    for item in items or []:
        if isinstance(item, AuditEvent):
            out.append(item)
        elif isinstance(item, dict):
            out.append(AuditEvent.from_dict(item))
    return out


def _cost_of(event: AuditEvent) -> float:
    """事件成本提取 (result/metadata 的 cost 类字段; 无 → 0.0)。"""
    for container in (event.result, event.metadata):
        if not isinstance(container, dict):
            continue
        for key in ("cost", "estimated_cost", "cost_usd", "total_cost"):
            value = container.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return 0.0


class AuditExplain:
    """结构化解释 (G7): 从审计事件回答"为什么/谁/花了多少"。

    全部方法返回统一结构:
      {question, answer_type, summary, evidence, decision, related_events,
       cost, policy, approval, outcome}
    默认结构化 (不调 LLM); 缺数据 → summary 明确说明 (不猜测)。
    """

    def __init__(self, store: Any = None) -> None:
        self._store = store

    # ------------------------------------------------------------ 数据源

    def _events(self) -> list[AuditEvent]:
        """store 全量事件 (失败安全 → [])。"""
        if self._store is None:
            return []
        try:
            if hasattr(self._store, "events"):
                return _event_list(self._store.events())
            return _event_list(self._store.query())
        except Exception:  # noqa: BLE001 — 失败安全
            return []

    def _filter(self, **filters: Any) -> list[AuditEvent]:
        """筛选 (AuditQuery 引擎)。"""
        return AuditQuery.filter_events(self._events(), **filters)

    # ------------------------------------------------------------ 解释模板

    def _base(
        self, question: str, answer_type: str, summary: str
    ) -> dict[str, Any]:
        """统一结构骨架。"""
        return {
            "question": question,
            "answer_type": answer_type,
            "summary": summary,
            "evidence": [],
            "decision": None,
            "related_events": [],
            "cost": {"total": 0.0, "events": 0, "references": []},
            "policy": None,
            "approval": None,
            "outcome": None,
        }

    def _finalize(
        self, result: dict[str, Any], events: list[AuditEvent], limit: int = 8
    ) -> dict[str, Any]:
        """填充统一结构: evidence/decision/related/policy/approval/outcome。"""
        events = _event_list(events)
        result["related_events"] = [
            e.to_dict() for e in events[-limit:]
        ]
        for event in events:
            if event.decision or event.decision_reason:
                result["decision"] = {
                    "decision": event.decision,
                    "reason": event.decision_reason,
                    "event_type": event.event_type,
                    "audit_id": event.audit_id,
                    "timestamp": event.timestamp,
                }
            if event.policy or event.policy_result:
                result["policy"] = {
                    "policy": event.policy,
                    "result": event.policy_result,
                    "event_type": event.event_type,
                }
            if isinstance(event.approval, dict) and event.approval:
                result["approval"] = {
                    **event.approval,
                    "event_type": event.event_type,
                    "audit_id": event.audit_id,
                }
            if event.result:
                result["outcome"] = {
                    "status": event.status,
                    "result": event.result,
                    "event_type": event.event_type,
                    "timestamp": event.timestamp,
                }
        return result

    # ------------------------------------------------------------ why_*

    def why_created(self, task_id: str) -> dict[str, Any]:
        """为什么创建这个任务: TASK_CREATED 事件 + 决策/原因 + 关联计划。"""
        task = str(task_id or "")
        created = self._filter(task_id=task, event_type="TASK_CREATED")
        related = self._filter(task_id=task)
        if not created:
            return self._base(
                f"为什么创建任务 {task}",
                "why_created",
                f"未找到任务 {task} 的 TASK_CREATED 审计事件 (任务可能未记录审计)。",
            )
        event = created[0]
        decision_text = event.decision_reason or event.decision or "任务由上游计划生成"
        summary = f"任务 {task} 由 {event.actor_type}/{event.actor_id or '系统'} " \
                  f"创建 ({event.timestamp[:19]}): {decision_text}"
        result = self._base(f"为什么创建任务 {task}", "why_created", summary)
        result["evidence"] = [
            {
                "audit_id": e.audit_id,
                "event_type": e.event_type,
                "action": e.action,
                "decision_reason": e.decision_reason,
                "timestamp": e.timestamp,
            }
            for e in related[:6]
        ]
        return self._finalize(result, related)

    def why_agent(self, agent_id: str) -> dict[str, Any]:
        """为什么选择这个 Agent: TASK_ASSIGNED/AGENT_STARTED 的决策原因。"""
        agent = str(agent_id or "")
        assigned = self._filter(agent_id=agent, event_type="TASK_ASSIGNED")
        started = self._filter(agent_id=agent, event_type="AGENT_STARTED")
        related = self._filter(agent_id=agent)
        events = assigned + started
        if not events:
            return self._base(
                f"为什么选择 Agent {agent}",
                "why_agent",
                f"未找到 Agent {agent} 的 TASK_ASSIGNED/AGENT_STARTED 审计事件。",
            )
        reasons = []
        for event in events[:5]:
            reason = event.decision_reason or event.decision
            if reason:
                reasons.append(
                    f"{event.task_id or '任务'}: {reason}"
                    f" ({event.timestamp[:19]})"
                )
        if not reasons:
            reasons = ["选择原因未记录 (无 decision_reason/decision 字段)"]
        summary = f"Agent {agent} 被选择参与 {len(events)} 次任务分配/启动。" \
                  f"原因: {'; '.join(reasons[:3])}"
        result = self._base(f"为什么选择 Agent {agent}", "why_agent", summary)
        result["evidence"] = [
            {
                "audit_id": e.audit_id,
                "event_type": e.event_type,
                "task_id": e.task_id,
                "decision_reason": e.decision_reason,
                "timestamp": e.timestamp,
            }
            for e in events[:6]
        ]
        return self._finalize(result, related)

    def why_stopped(self, project_id: str) -> dict[str, Any]:
        """为什么停了: TASK_BLOCKED/BUDGET_BLOCKED/REVIEW_REQUESTED/
        REVIEW_REJECTED 阻塞类事件 + 审批状态。"""
        project = str(project_id or "")
        blocked = self._filter(
            project_id=project,
            event_type=None,
        )
        blocked = [
            e for e in blocked
            if e.event_type in (
                "TASK_BLOCKED", "BUDGET_BLOCKED", "BUDGET_WARNING",
                "REVIEW_REQUESTED", "REVIEW_REJECTED",
            )
        ]
        related = self._filter(project_id=project)
        if not blocked:
            last = related[-1] if related else None
            if last is None:
                summary = f"项目 {project} 无审计事件记录。"
            else:
                summary = (
                    f"项目 {project} 无阻塞类事件; 最近事件: "
                    f"{last.event_type} ({last.timestamp[:19]}) — "
                    f"状态 {last.status or '未知'}"
                )
            result = self._base(f"为什么项目 {project} 停了", "why_stopped", summary)
            return self._finalize(result, related)
        reasons = []
        for event in blocked[:5]:
            reason = event.decision_reason or event.decision or event.policy_result
            if not reason and isinstance(event.result, dict):
                reason = event.result.get("reason")
            reasons.append(f"{event.event_type}: {reason or '未记录原因'}")
        summary = f"项目 {project} 停于 {len(blocked)} 个阻塞/待审事件: " \
                  f"{'; '.join(reasons[:3])}"
        result = self._base(f"为什么项目 {project} 停了", "why_stopped", summary)
        result["evidence"] = [
            {
                "audit_id": e.audit_id,
                "event_type": e.event_type,
                "decision_reason": e.decision_reason,
                "policy": e.policy,
                "policy_result": e.policy_result,
                "status": e.status,
                "timestamp": e.timestamp,
            }
            for e in blocked[:6]
        ]
        return self._finalize(result, blocked + related)

    def why_debug(self, debug_id: str) -> dict[str, Any]:
        """为什么修/调试链路: debug_reference 关联事件 (TEST_FAILED→DEBUG→
        REPAIR→PASS) + 用了什么经验 (memory_reference)。"""
        debug = str(debug_id or "")
        debug_events = [
            e for e in self._events()
            if e.debug_reference == debug
        ]
        related = debug_events
        if not related and not debug:
            # 兜底: 无 debug_id → 按 ROOT_CAUSE/REPAIR 类型找 (最近 8 条)
            related = self._filter(
                event_type=None,
            )
            related = [
                e for e in related
                if e.event_type in (
                    "TEST_FAILED", "DEBUG_STARTED", "ROOT_CAUSE_IDENTIFIED",
                    "DEBUG_STRATEGY_SELECTED", "REPAIR_STARTED",
                    "REPAIR_COMPLETED", "TEST_PASSED",
                )
            ][-8:]
        if not related:
            return self._base(
                f"为什么调试 {debug}",
                "why_debug",
                f"未找到 debug_reference={debug} 的调试审计事件。",
            )
        cause = next(
            (e for e in related if e.event_type == "ROOT_CAUSE_IDENTIFIED"),
            None,
        )
        strategy = next(
            (e for e in related if e.event_type == "DEBUG_STRATEGY_SELECTED"),
            None,
        )
        memory_refs = sorted(
            {e.memory_reference for e in related if e.memory_reference}
        )
        repaired = any(e.event_type == "REPAIR_COMPLETED" for e in related)
        passed = any(e.event_type == "TEST_PASSED" for e in related)
        parts = []
        if cause:
            parts.append(f"根因: {cause.decision_reason or cause.decision or '已识别'}")
        if strategy:
            parts.append(f"策略: {strategy.decision or strategy.decision_reason or '已选择'}")
        if memory_refs:
            parts.append(f"复用经验: {', '.join(memory_refs[:3])}")
        if repaired and passed:
            parts.append("修复完成并通过验证")
        summary = f"调试 {debug}: {'; '.join(parts) if parts else '链路事件 ' + str(len(related)) + ' 条'}"
        result = self._base(f"为什么调试 {debug}", "why_debug", summary)
        result["evidence"] = [
            {
                "audit_id": e.audit_id,
                "event_type": e.event_type,
                "decision": e.decision,
                "decision_reason": e.decision_reason,
                "memory_reference": e.memory_reference,
                "timestamp": e.timestamp,
            }
            for e in related[:8]
        ]
        result["memory_references"] = memory_refs
        return self._finalize(result, related)

    def why_cost(self, project_id: str) -> dict[str, Any]:
        """为什么花了这么多: LLM_CALL/TOOL_CALL/AGENT_* 成本事件聚合 +
        CostLedger reference 关联 (懒加载复用, 失败安全)。"""
        project = str(project_id or "")
        cost_events = [
            e for e in self._events()
            if (not project or e.project_id == project)
            and e.event_type in ("LLM_CALL", "TOOL_CALL", "AGENT_STARTED",
                                 "AGENT_COMPLETED")
        ]
        total = sum(_cost_of(e) for e in cost_events)
        references = sorted(
            {e.cost_reference for e in cost_events if e.cost_reference}
        )
        ledger_total: Optional[float] = None
        try:  # 懒加载复用 CostLedger (reference 关联, 不重实现)
            from ..session.cost_ledger import CostLedger

            ledger = CostLedger(self._store.file().parent.parent / "cost" / "cost_records.json")
            aggregate = ledger.aggregate(project_id=project or None)
            ledger_total = float(aggregate.get("total_cost") or 0.0)
        except Exception:  # noqa: BLE001 — 失败安全: 无 CostLedger 不影响
            ledger_total = None
        summary = (
            f"项目 {project or '(全部)'} 产生 {len(cost_events)} 条成本事件, "
            f"事件内成本合计 ${total:.4f}"
            + (
                f"; CostLedger 聚合 ${ledger_total:.4f}"
                if ledger_total is not None else ""
            )
        )
        result = self._base(f"项目 {project or '(全部)'} 成本", "why_cost", summary)
        result["cost"] = {
            "total": round(total, 4),
            "events": len(cost_events),
            "references": references,
            "ledger_total": ledger_total,
        }
        result["evidence"] = [
            {
                "audit_id": e.audit_id,
                "event_type": e.event_type,
                "agent_id": e.agent_id,
                "cost_reference": e.cost_reference,
                "cost": _cost_of(e),
                "timestamp": e.timestamp,
            }
            for e in cost_events[-8:]
        ]
        return self._finalize(result, cost_events)

    def who_approved(self, project_id: str) -> dict[str, Any]:
        """谁批准了: REVIEW_APPROVED 事件 (approval.reviewer / actor_id)。"""
        project = str(project_id or "")
        approved = [
            e for e in self._events()
            if e.event_type == "REVIEW_APPROVED"
            and (not project or e.project_id == project)
        ]
        related = [
            e for e in self._events()
            if e.event_type in ("REVIEW_REQUESTED", "REVIEW_APPROVED",
                                "REVIEW_REJECTED")
            and (not project or e.project_id == project)
        ]
        if not approved:
            return self._base(
                f"谁批准了项目 {project or '(全部)'}",
                "who_approved",
                f"未找到项目 {project or '(全部)'} 的 REVIEW_APPROVED 审计事件。",
            )
        approvers = []
        for event in approved:
            approval = event.approval if isinstance(event.approval, dict) else {}
            reviewer = (
                approval.get("reviewer")
                or event.actor_id
                or "未记录审批人"
            )
            approvers.append(
                f"{reviewer} 批准 {event.task_id or event.project_id or '任务'}"
                f" ({event.timestamp[:19]})"
            )
        summary = f"项目 {project or '(全部)'} 有 {len(approved)} 次批准: " \
                  f"{'; '.join(approvers[:3])}"
        result = self._base(
            f"谁批准了项目 {project or '(全部)'}", "who_approved", summary
        )
        result["evidence"] = [
            {
                "audit_id": e.audit_id,
                "event_type": e.event_type,
                "approval": e.approval,
                "actor_id": e.actor_id,
                "task_id": e.task_id,
                "timestamp": e.timestamp,
            }
            for e in approved[:6]
        ]
        return self._finalize(result, related)

    # ------------------------------------------------------------ 通用入口

    def explain(
        self,
        question: str = "",
        *,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        project: Optional[str] = None,
        debug_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """自然问题分发 (默认结构化, 不调 LLM — 设计 §13 边界)。

        关键词路由 (确定性, 无歧义):
          "为什么创建/为什么建" → why_created(task_id)
          "为什么选择/为什么是" → why_agent(agent_id)
          "为什么停/为什么暂停" → why_stopped(project)
          "为什么修/调试/debug/为什么失败" → why_debug(debug_id)
          "成本/花了多少/费用" → why_cost(project)
          "谁批准/谁审批/批准" → who_approved(project)
          未命中 → 最近事件摘要 (question 原样回显)。
        """
        text = str(question or "").strip()
        if not text:
            return self._base("", "unknown", "缺少问题 (question 为空)。")
        # question 关键词优先 (S10-069 修复: 不应因 task_id/agent_id 已提供而跳过分发)
        if any(k in text for k in ("为什么创建", "为什么建")):
            return self.why_created(task_id or "")
        if any(k in text for k in ("为什么选择", "为什么是")):
            return self.why_agent(agent_id or "")
        if any(k in text for k in ("为什么停", "为什么暂停", "为什么中断", "为什么项目停了", "停了", "为什么停止")):
            return self.why_stopped(project or "")
        if any(k in text for k in ("为什么修", "为什么失败", "调试", "debug", "根因")):
            return self.why_debug(debug_id or "")
        if any(k in text for k in ("成本", "花了多少", "费用")):
            return self.why_cost(project or "")
        if any(k in text for k in ("谁批准", "谁审批", "批准", "approve")):
            return self.who_approved(project or "")
        events = self._events()
        if not events:
            return self._base(text, "unknown", "工作区无审计事件记录。")
        last = events[-1]
        summary = (
            f"最近审计事件: {last.event_type} ({last.timestamp[:19]}) — "
            f"状态 {last.status or '未知'}; 无法从问题关键词确定解释类型, "
            f"请使用 为什么创建/为什么选择/为什么停/为什么修/成本/谁批准。"
        )
        result = self._base(text, "unknown", summary)
        return self._finalize(result, events[-5:])
