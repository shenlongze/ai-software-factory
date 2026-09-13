"""factory-console/session/handoff_bus.py — 交接总线 (M2 A4, S10-087, 多 Agent 协作)。

"我要做CRM" → 7 个真实 Agent 实体交接产出: HandoffBus.route(role_graph) +
send(producer→consumer); 消息 {from, to, artifacts[], decisions[], constraints[]};
资产 parent_artifact 互引; 冲突 → ReviewGate 挂起等审批。

契约 (S10-087-M2 §2 / A4):
1. 血缘双字段: ArtifactRegistry.write(..., created_by=agent_id,
   parent_event_id=<上一资产 event_id>, metadata={"parent_artifact": <上一资产 id>})
2. created_by 一律 agent_id (agt- 前缀, 非 role 字符串)
3. 冲突 → ConflictResolver (S10-057) → ReviewGate.request → status=pending_review
   (挂起等审批); route 遇到 pending → HandoffBlocked 明确报错 (不静默跳过)
4. 失败明确报错 (HandoffError/HandoffBlocked); 消息落盘 m2_handoffs.json (失败安全)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .agent_entity import AgentEntity
from .artifact_registry import ArtifactRecord, ArtifactRegistry
from .conflicts import ConflictResolver, DECISION_NO_CONFLICT, DECISION_REQUEST_REVIEW
from .expert_factory import ROLE_DEFINITIONS
from .product import ProductIntent
from .review_gate import ReviewGate

#: 消息状态
MSG_STATUS_DELIVERED = "delivered"          # 资产已交接
MSG_STATUS_PENDING_REVIEW = "pending_review"  # 冲突挂起等审批

#: M2 交接消息落盘文件名 (projects/<slug>/ — 独立于 orchestrator handoff_messages.json)
HANDOFF_MESSAGES_FILE_NAME = "m2_handoffs.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class HandoffMessage:
    """跨 Agent 交接消息: 生产者产出 → 消费者消费。"""

    message_id: str
    from_agent: str
    to_agent: str
    artifacts: list[str] = field(default_factory=list)   # 交接的资产 id 列表
    decisions: list[str] = field(default_factory=list)   # 决策/理由
    constraints: list[str] = field(default_factory=list) # 对消费者的约束
    status: str = MSG_STATUS_DELIVERED
    review_id: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "from": self.from_agent,
            "to": self.to_agent,
            "artifacts": list(self.artifacts),
            "decisions": list(self.decisions),
            "constraints": list(self.constraints),
            "status": self.status,
            "review_id": self.review_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "HandoffMessage":
        data = data or {}
        return cls(
            message_id=str(data.get("message_id") or ""),
            from_agent=str(data.get("from") or ""),
            to_agent=str(data.get("to") or ""),
            artifacts=[str(a) for a in (data.get("artifacts") or [])],
            decisions=[str(d) for d in (data.get("decisions") or [])],
            constraints=[str(c) for c in (data.get("constraints") or [])],
            status=str(data.get("status") or MSG_STATUS_DELIVERED),
            review_id=str(data.get("review_id") or ""),
            created_at=str(data.get("created_at") or ""),
        )


@dataclass
class HandoffResult:
    """交接结果: 项目 + 资产链 + 消息链 (供 PipelineResult/Summary 消费)。"""

    project: str
    records: list[ArtifactRecord] = field(default_factory=list)
    messages: list[HandoffMessage] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.records:
            return f"产品管线未产出资产 ({self.project})"
        lines = [f"产品管线完成: {len(self.records)} 个资产 ({self.project}):"]
        for r in self.records:
            parent = (r.metadata or {}).get("parent_artifact") or ""
            lines.append(
                f"  v{r.version} {r.type} [{r.created_by}] parent={parent or '(根)'}"
            )
        lines.append("可输入 '项目列表' 或 /project 查看; 确认后 '准备开发' 进入工程。")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "records": [r.to_dict() for r in self.records],
            "messages": [m.to_dict() for m in self.messages],
            "count": len(self.records),
        }


class HandoffError(Exception):
    """交接失败 (消息/资产非法等 — 明确报错, 不静默)。"""


class HandoffBlocked(HandoffError):
    """交接链被阻断: 冲突 → ReviewGate 挂起等审批 (status=pending_review)。"""

    def __init__(self, message: HandoffMessage, detail: str = ""):
        self.message = message
        self.detail = detail
        super().__init__(
            f"交接阻断: from={message.from_agent} to={message.to_agent} "
            f"review_id={message.review_id or '(无)'} {detail}".strip()
        )


class HandoffBus:
    """多 Agent 交接总线: send(单步) + route(整链), 血缘/冲突/审批一体化。"""

    def __init__(
        self,
        workspace: Any,
        slug: str,
        *,
        registry: Optional[ArtifactRegistry] = None,
        review_gate: Optional[ReviewGate] = None,
        conflict_resolver: Optional[ConflictResolver] = None,
        messages_file: Optional[Path] = None,
    ) -> None:
        self.workspace = workspace
        self.slug = str(slug)
        self.registry = registry or ArtifactRegistry(workspace, self.slug)
        self.review_gate = review_gate or ReviewGate.for_project(
            Path(workspace) / "projects" / self.slug
        )
        self.conflict_resolver = conflict_resolver or ConflictResolver(
            resolution_file=(
                Path(workspace) / "projects" / self.slug / "conflict_resolution.json"
            )
        )
        self._messages_file = Path(messages_file) if messages_file is not None else (
            Path(workspace) / "projects" / self.slug / HANDOFF_MESSAGES_FILE_NAME
        )

    # ------------------------------------------------------------ 单步交接

    def send(
        self,
        producer: AgentEntity,
        consumer: AgentEntity,
        *,
        artifact_type: str,
        content: str,
        source: str = "",
        decisions: Optional[list[str]] = None,
        constraints: Optional[list[str]] = None,
        parent_artifact_id: str = "",
        parent_event_id: str = "",
        conflicts: Optional[list[dict[str, Any]]] = None,
        review_required: bool = False,
        model: str = "",
        token_usage: int = 0,
        cost: str = "",
    ) -> tuple[HandoffMessage, Optional[ArtifactRecord]]:
        """生产者 → 消费者交接: 冲突先判 (→ReviewGate 挂起), 否则写资产 + 落盘消息。

        血缘契约: created_by=producer.id (agt- 前缀), parent_event_id=<上一资产
        event_id>, metadata={"parent_artifact": <上一资产 id>}。
        返回 (消息, 资产记录|None): 冲突 → 不写资产, 消息 status=pending_review
        + review_id (挂起等审批), 资产为 None。
        """
        if not isinstance(producer, AgentEntity) or not isinstance(consumer, AgentEntity):
            raise HandoffError("send 需要 producer/consumer 为 AgentEntity")
        message_id = f"ho-{uuid.uuid4().hex[:12]}"
        message = HandoffMessage(
            message_id=message_id,
            from_agent=producer.id,
            to_agent=consumer.id,
            decisions=list(decisions or []),
            constraints=list(constraints or []),
            status=MSG_STATUS_DELIVERED,
            created_at=_now_iso(),
        )

        decision = self._resolve_conflict(conflicts or [], review_required=review_required)
        if decision in (DECISION_REQUEST_REVIEW, "SERIALIZE"):
            review = self.review_gate.request(
                reason=(
                    "多 Agent 交接冲突, 需人工审批: "
                    f"{producer.id} → {consumer.id} 资产 {artifact_type}"
                ),
                trigger="handoff_bus.send",
                context={"project_id": self.slug, "from": producer.id, "to": consumer.id},
                affected_tasks=[producer.id, consumer.id],
                project_id=self.slug,
            )
            message.status = MSG_STATUS_PENDING_REVIEW
            message.review_id = str(getattr(review, "review_id", "") or "")
            self._append_message(message)
            return message, None

        record = self.registry.write(
            artifact_type,
            str(content or ""),
            created_by=producer.id,
            source=source,
            status="draft",
            parent_event_id=parent_event_id,
            model=model,
            token_usage=token_usage,
            cost=cost,
            metadata={"parent_artifact": str(parent_artifact_id or "")},
        )
        # 审计血缘: ARTIFACT_CREATED (失败安全, 不中断业务) — event_id 供下一环
        record.event_id = self._emit(record, parent_event_id)
        message.artifacts = [record.id]
        self._append_message(message)
        return message, record

    # ------------------------------------------------------------ 整链交接

    def route(
        self,
        agents: list[AgentEntity],
        *,
        produce: Callable[[AgentEntity, str, ProductIntent, str], str],
        product: ProductIntent,
        source: str = "",
        conflicts_for: Optional[Callable[[int, AgentEntity], list[dict[str, Any]]]] = None,
        decisions_for: Optional[Callable[[int, AgentEntity], list[str]]] = None,
        constraints_for: Optional[Callable[[int, AgentEntity], list[str]]] = None,
    ) -> HandoffResult:
        """跑完整角色链: 每步消费上一资产 → 产出 → 交接 (parent_artifact 互引)。

        S10-088 T2: 交接消费上一产出正文 — 每步从 ArtifactRegistry.read 读
        上一资产 content, 作为第 4 参传给 produce (prompt 嵌 '上一资产内容'),
        而非仅传 asset id (血缘双字段仍保留)。

        任一交接 pending_review → HandoffBlocked (链停止, 等审批 — 不静默跳过)。
        """
        if not agents:
            raise HandoffError("route 需要非空 Agent 链")
        result = HandoffResult(project=self.slug)
        prev_artifact_id = ""
        prev_event_id = ""
        prev_content = ""  # S10-088 T2: 上一资产正文 (交接消费, 首环为空=根)
        for index, agent in enumerate(agents):
            content = produce(agent, prev_artifact_id, product, prev_content)
            artifact_type = self._artifact_type_for(agent)
            consumer = agents[index + 1] if index + 1 < len(agents) else agent
            message, record = self.send(
                agent,
                consumer,
                artifact_type=artifact_type,
                content=content,
                source=source or (product.raw or product.name or ""),
                decisions=(
                    (decisions_for(index, agent) if decisions_for else None)
                    or [f"{agent.id} 产出 {artifact_type}"]
                ),
                constraints=(
                    (constraints_for(index, agent) if constraints_for else None)
                    or ["消费上一资产产出, 保持血缘"]
                ),
                parent_artifact_id=prev_artifact_id,
                parent_event_id=prev_event_id,
                conflicts=(conflicts_for(index, agent) if conflicts_for else None),
            )
            if message.status == MSG_STATUS_PENDING_REVIEW:
                raise HandoffBlocked(message)
            if record is None:
                raise HandoffError(
                    f"交接后未找到资产 {artifact_type} (from={agent.id})"
                )
            result.records.append(record)
            result.messages.append(message)
            prev_artifact_id = record.id
            prev_event_id = record.event_id
            prev_content = self.registry.read(record)  # S10-088 T2: 交接消费正文
        return result

    # ------------------------------------------------------------ 内部

    def _emit(self, record: ArtifactRecord, parent_event_id: str) -> str:
        """ARTIFACT_CREATED 审计事件 (失败安全 → ""). 返回 audit_id 供血缘链。"""
        try:
            from ..audit.audit_emitter import AuditEmitter
            ev = AuditEmitter(workspace=self.workspace).emit(
                "ARTIFACT_CREATED",
                project_id=self.slug,
                agent_id=record.created_by,
                actor_type="agent",
                actor_id=record.created_by,
                artifact_reference=record.content_ref,
                parent_event_id=parent_event_id,
                artifact_type=record.type,
                artifact_version=record.version,
            )
            return str(getattr(ev, "audit_id", "") or "") if ev is not None else ""
        except Exception:  # noqa: BLE001 — 审计故障不中断
            return ""

    def _resolve_conflict(
        self, conflicts: list[dict[str, Any]], *, review_required: bool
    ) -> str:
        """冲突 → 执行决策 (S10-057 ConflictResolver.resolve/classify)。

        有冲突 → resolve (落盘 conflict_resolution.json); 无冲突但
        review_required → classify(REQUEST_REVIEW); 其余 → NO_CONFLICT。
        """
        if conflicts:
            outcome = self.conflict_resolver.resolve(list(conflicts), plan_tasks=[])
            return str(outcome.get("decision") or DECISION_NO_CONFLICT)
        if review_required:
            return ConflictResolver.classify(
                [], review_required=True
            )
        return DECISION_NO_CONFLICT

    @staticmethod
    def _artifact_type_for(agent: AgentEntity) -> str:
        """角色 → 资产类型 (ROLE_DEFINITIONS; 未知角色 → <role>_artifact)。"""
        spec = ROLE_DEFINITIONS.get(str(agent.role or "").lower())
        if spec is not None:
            return str(spec.get("artifact_type") or f"{agent.role}_artifact")
        return f"{agent.role}_artifact"

    # ------------------------------------------------------------ 消息持久化

    def _append_message(self, message: HandoffMessage) -> None:
        """消息 append 落盘 m2_handoffs.json (失败安全: 不中断业务)。"""
        try:
            messages = self.load_messages()
            messages.append(message.to_dict())
            self._messages_file.parent.mkdir(parents=True, exist_ok=True)
            self._messages_file.write_text(
                json.dumps(messages, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — 失败安全: 消息审计故障不中断
            pass

    def load_messages(self) -> list[dict[str, Any]]:
        """读回交接消息列表 (缺失/损坏 → [], 失败安全)。"""
        try:
            data = json.loads(self._messages_file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:  # noqa: BLE001 — 失败安全
            return []


__all__ = [
    "MSG_STATUS_DELIVERED",
    "MSG_STATUS_PENDING_REVIEW",
    "HANDOFF_MESSAGES_FILE_NAME",
    "HandoffMessage",
    "HandoffResult",
    "HandoffError",
    "HandoffBlocked",
    "HandoffBus",
]
