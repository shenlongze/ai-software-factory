"""factory-console/audit/audit_emitter.py — AuditEmitter (S10-070 G2 自动接入)。

审计自动接入生产链: 生产决策/事件 → 统一 AuditStore 落盘 (脱敏 + hash 链),
零侵入 — 调用方 (session/actions 薄接 / orchestrator 关键点) 只需一行 emit。

- emit(event_type, *, project_id/task_id/agent_id/actor_type/actor_id/
  workspace, **fields) → AuditEvent | None:
    构造 AuditEvent (字段映射: 已知字段 → 事件字段, 未知字段 → metadata,
    不丢失) + 脱敏 (redact — 纵深防御, AuditStore.append 再兜一层) +
    AuditStore.append (原子落盘 + previous_event_hash 链)
  - 失败安全铁律: Audit 任何故障 (事件类型非法/存储异常/落盘失败) → None,
    绝不向业务流抛异常 (审计不中断生产链)
- emit_production(project_id, workspace, **fields) → AuditEvent | None:
    生产事件便捷入口 (PROJECT_DELIVERED/TASK_COMPLETED 语义 — status 默认
    completed, 生产链完成/失败均可调用)

边界:
- 复用 audit_event.AuditEvent (EVENT_TYPES 校验 + redact) 与
  audit_store.AuditStore (append: 封存/链/原子写) — 不重写现有 audit/
- 纯标准库 + 现有模块, 零新依赖

设计: docs/sprint10/S10-069-audit-design.md §2/§3
     + docs/sprint10/S10-070-gap-design.md §三.2 (G2 Audit 自动接入)
"""

from __future__ import annotations

from typing import Any, Optional

from .audit_event import EVENT_TYPES, AuditEvent, redact
from .audit_store import AuditStore

__all__ = ["AuditEmitter"]

#: 已知事件字段 (AuditEvent.create 关键字) — 传入 fields 中命中者 → 事件字段;
#: 未命中 → metadata (不丢失, 失败安全)
_EVENT_FIELDS: frozenset[str] = frozenset({
    "trace_id", "correlation_id", "workspace_id", "task_id", "agent_id",
    "actor_type", "actor_id", "action", "lifecycle_state", "source",
    "input_reference", "decision", "decision_reason", "evidence", "policy",
    "policy_result", "approval", "parent_event_id", "related_event_ids",
    "artifact_reference", "cost_reference", "memory_reference",
    "debug_reference", "result", "impact", "risk", "status", "metadata",
    "timestamp", "previous_event_hash",
})


class AuditEmitter:
    """审计发射器 (G2): 生产事件 → 统一审计存储 (脱敏 + hash 链, 失败安全)。

    用法 (薄接, 不重写业务):
        AuditEmitter(workspace=ws).emit(
            "PRODUCT_CREATED", project_id=slug,
            result={"name": product.name},
            actor_type="agent", actor_id=agent_id,
        )
    emit_production: 生产链完成/失败便捷入口 (PROJECT_DELIVERED 语义)。
    """

    def __init__(self, workspace: Any = None, store: Optional[AuditStore] = None) -> None:
        """store 显式注入 (测试/隔离); 缺省 → workspace 装配 AuditStore。"""
        self._store = store if store is not None else AuditStore(workspace=workspace)

    # ------------------------------------------------------------ 发射

    def emit(
        self,
        event_type: str,
        *,
        project_id: str = "",
        task_id: str = "",
        agent_id: str = "",
        actor_type: str = "system",
        actor_id: str = "",
        workspace: Any = None,
        **fields: Any,
    ) -> Optional[AuditEvent]:
        """发射审计事件 → AuditStore.append (脱敏 + 封存 + 原子落盘)。

        event_type: 必须 ∈ AuditEvent.EVENT_TYPES (非法 → None, 失败安全);
        fields: 已知字段 → 事件字段, 未知 → metadata (不丢失);
        workspace: 非 None 时覆盖 store (独立工作区审计 — 测试/多工作区)。
        返回封存后 AuditEvent (成功) / None (任何故障 — 审计不中断业务)。
        """
        try:
            if workspace is not None:
                self._store = AuditStore(workspace=workspace)
            if str(event_type or "") not in EVENT_TYPES:
                return None
            event_kwargs, extra = self._split_fields(fields)
            event = AuditEvent.create(
                event_type,
                project_id=project_id,
                task_id=task_id,
                agent_id=agent_id,
                actor_type=actor_type,
                actor_id=actor_id,
                **event_kwargs,
            )
            if extra:
                # 未知字段 → metadata (合并既有, 不覆盖调用方显式 metadata)
                merged = dict(event.metadata or {})
                merged.update(extra)
                event.metadata = redact(merged)
            return self._store.append(event)
        except Exception:  # noqa: BLE001 — 失败安全铁律: 审计故障不抛
            return None

    def emit_production(
        self,
        project_id: str,
        workspace: Any = None,
        *,
        task_id: str = "",
        agent_id: str = "",
        actor_type: str = "system",
        actor_id: str = "",
        **fields: Any,
    ) -> Optional[AuditEvent]:
        """生产事件便捷入口 (G2/验收 B): PROJECT_DELIVERED 语义。

        status 缺省 "completed" (生产链完成); 调用方可传 status="failed"
        表达失败交付。project_id 必填 (生产链上下文), workspace 指定审计
        存储位置 (与 emit 同语义)。
        """
        payload = dict(fields)
        payload.setdefault("status", "completed")
        return self.emit(
            "PROJECT_DELIVERED",
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            actor_type=actor_type,
            actor_id=actor_id,
            workspace=workspace,
            **payload,
        )

    # ------------------------------------------------------------ 工具

    @staticmethod
    def _split_fields(fields: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """fields → (事件字段 kwargs, 未知字段) — 已知字段命中事件契约。"""
        event_kwargs: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        for key, value in (fields or {}).items():
            if key in _EVENT_FIELDS:
                event_kwargs[key] = value
            else:
                extra[key] = value
        return event_kwargs, extra

    def store(self) -> AuditStore:
        """当前 AuditStore (测试/统计视图)。"""
        return self._store
