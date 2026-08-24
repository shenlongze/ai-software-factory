"""factory-console/audit/audit_event.py — AuditEvent 统一审计事件模型 (S10-069)。

统一事件模型 (GAP G1/G3/G4/G11/G12): Product→Plan→Task→Agent→Debug→Memory→
Cost→Review→Delivery 全生命周期事件, 单一结构落盘 audit_events.json。

- EVENT_TYPES: 33 个标准事件类型 (验收: 30+)
- 脱敏: 键名黑名单 (api_key/secret/password/token/credential/authorization)
  递归删除; 原始 Prompt/Context 不落盘 (只存 input_reference/hash/summary)
- hash: sha256(audit_id + canonical_json + previous_event_hash) — 防篡改基础
  (AuditIntegrity 负责链校验)

设计: docs/sprint10/S10-069-audit-design.md §2
边界:
- 纯标准库 (dataclasses/json/hashlib/uuid/datetime), 零新依赖
- from_dict 失败安全: 未知键保留 (前向兼容), 缺失字段缺省
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

#: 标准事件类型注册表 (S10-069 设计 §2 — 54 个, 验收: 30+)
EVENT_TYPES: tuple[str, ...] = (
    "PRODUCT_CREATED",
    "PROJECT_RENAMED",
    "EVIDENCE_BUNDLE_CREATED",
    "APPROVAL_REQUESTED",
    "APPROVAL_DECIDED",
    "DECISION_LEARNED",
    "DISCOVERY_COMPLETED",
    "DISCOVERY_CONFIRMED",
    "PRODUCT_INTELLIGENCE",
    "PLAN_CREATED",
    "PLAN_CHANGED",
    "TASK_CREATED",
    "TASK_ASSIGNED",
    "AGENT_STARTED",
    "AGENT_COMPLETED",
    "LLM_CALL",
    "TOOL_CALL",
    "ARTIFACT_CREATED",
    "TEST_STARTED",
    "TEST_FAILED",
    "TEST_PASSED",
    "DEBUG_STARTED",
    "ROOT_CAUSE_IDENTIFIED",
    "DEBUG_STRATEGY_SELECTED",
    "REPAIR_STARTED",
    "REPAIR_COMPLETED",
    "REPAIR_FAILED",
    "VALIDATION_PASSED",
    "VALIDATION_FAILED",
    "MEMORY_RETRIEVED",
    "MEMORY_LEARNED",
    "GOVERNANCE_CHECK",
    "BUDGET_WARNING",
    "BUDGET_BLOCKED",
    "REVIEW_REQUESTED",
    "REVIEW_APPROVED",
    "REVIEW_REJECTED",
    "TASK_BLOCKED",
    "TASK_COMPLETED",
    "TASK_STARTED",
    "TASK_FAILED",
    "AGENT_ASSIGNED",
    "DELIVERY_CREATED",
    # S10-112 P0-10: 交付链 4 事件此前被 delivery.py 实际发射 (模块 docstring
    # 也宣称 "全程审计事件") 但漏注册 → AuditEmitter 失败安全静默丢弃, 审计
    # 记录与实现漂移; 补入注册表 (不新增业务, 只同步已发射事件)。
    "PATCH_APPLIED",
    "CODE_VALIDATED",
    "DELIVERY_COMPLETED",
    "DELIVERY_FAILED",
    "USER_ACCEPTANCE",
    "PROJECT_DELIVERED",
    "DECOMPOSE_STARTED",
    "DECOMPOSE_ATOMIC",
    "DECOMPOSE_SPLIT",
    "DECOMPOSE_CYCLE_REJECTED",
    "DECOMPOSE_COMPLETED",
    "PLAN_KEYPATH_COMPUTED",
    "PLAN_MERGE_MARKED",
    "EVAL_COMPLETED",
    "EVAL_REJECTED_FALLBACK",
    # M3e (S10-097): M3 全链调度执行事件 (5 事件)
    "EXECUTION_ROUND_STARTED",
    "EXECUTION_TASK_ASSIGNED",
    "EXECUTION_TASK_COMPLETED",
    "EXECUTION_ROUND_COMPLETED",
    "EXECUTION_M3_DEGRADED",
)

#: 敏感键精确名 (脱敏: 键名小写/下划线归一后 ∈ 该集合 → 删除)
SENSITIVE_KEYS_EXACT: frozenset[str] = frozenset({
    "api_key", "apikey", "secret", "password", "token", "credential",
    "authorization", "auth",
})

#: 敏感键子串 (脱敏: 键名小写/下划线归一后含任一子串 → 删除)
SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "api_key", "apikey", "secret", "password", "token", "credential",
    "authorization", "bearer", "private_key", "client_secret",
    "access_token", "refresh_token", "id_token", "auth_token",
)

#: 用量统计安全后缀 (\"token\" 黑名单例外 — token_usage/input_tokens 等是
#: 合法审计用量, 不是密钥; 键名归一后以这些后缀结尾 → 不脱敏)
SAFE_USAGE_SUFFIXES: tuple[str, ...] = (
    "_usage", "_tokens", "_count", "_total", "_input", "_output",
    "_input_tokens", "_output_tokens", "_total_tokens",
)

#: 保留字段后缀 (脱敏仍允许落盘的安全摘要/引用键 — 设计 §2: 只存
#: hash/summary/reference, 原始敏感内容不落盘)
SAFE_SUFFIXES: tuple[str, ...] = (
    "_hash", "hash", "_summary", "summary", "_ref", "_reference",
)

#: actor_type 取值 (统一\"谁\" — GAP G4)
ACTOR_TYPES: tuple[str, ...] = ("user", "system", "agent", "llm", "tool")

#: 默认审计工作区 (~/.factory — 与 session/actions.DEFAULT_WORKSPACE 同口径)
DEFAULT_WORKSPACE = None


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (事件时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


def _is_sensitive_key(key: str) -> bool:
    """键名是否敏感 (精确名或子串命中 — 脱敏判定)。

    例外: 用量统计后缀 (token_usage/input_tokens/total_tokens — 合法审计
    字段, 非密钥) 与安全摘要/引用后缀 (hash/summary/ref — 只存摘要不存
    原文) 不脱敏; 其余命中敏感子串 (api_key/secret/password/token/
    credential/authorization) 一律删除。
    """
    normalized = str(key).lower().replace("-", "_")
    if any(normalized.endswith(sfx) for sfx in SAFE_USAGE_SUFFIXES):
        return False
    if normalized in SENSITIVE_KEYS_EXACT:
        return True
    if any(sub in normalized for sub in SENSITIVE_KEY_SUBSTRINGS):
        # S10-069 修复: 敏感子串优先于 hash/summary 后缀 (password_hash 也脱敏)
        return True
    if any(normalized.endswith(sfx) for sfx in SAFE_SUFFIXES):
        return False
    return False


def redact(payload: Any) -> Any:
    """递归脱敏: 键名命中敏感词 → 删除该键 (dict/list 递归, 其余原样)。

    安全摘要/引用后缀 (hash/summary/id/ref) 保留 — 不丢失审计引用能力
    (设计 §2: 只存 input_reference/hash/summary, 原始 Prompt 不落盘)。
    """
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for k, v in payload.items():
            key = str(k)
            if _is_sensitive_key(key):
                continue
            out[key] = redact(v)
        return out
    if isinstance(payload, list):
        return [redact(v) for v in payload]
    return payload


def canonical_json(payload: Any) -> str:
    """稳定序列化 (sort_keys — hash 确定性基础)。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


@dataclass
class AuditEvent:
    """统一审计事件 (S10-069 设计 §2 — 全字段)。

    事件字段: 身份 (audit_id/trace_id/correlation_id/project_id/workspace_id/
    task_id/agent_id)、谁 (actor_type/actor_id)、什么 (event_type/action)、
    何时 (timestamp)、生命周期 (lifecycle_state/source)、引用 (input_reference/
    parent_event_id/related_event_ids/artifact_reference/cost_reference/
    memory_reference/debug_reference)、决策 (decision/decision_reason/evidence/
    policy/policy_result/approval)、结果 (result/impact/risk/status)、扩展
    (metadata)、完整性 (event_hash/previous_event_hash)。
    """

    audit_id: str = ""
    trace_id: str = ""
    correlation_id: str = ""
    project_id: str = ""
    workspace_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    actor_type: str = "system"
    actor_id: str = ""
    event_type: str = ""
    action: str = ""
    timestamp: str = ""
    lifecycle_state: str = ""
    source: str = ""
    input_reference: str = ""
    decision: str = ""
    decision_reason: str = ""
    evidence: Any = field(default_factory=list)
    policy: str = ""
    policy_result: str = ""
    approval: Any = field(default_factory=dict)
    parent_event_id: str = ""
    related_event_ids: Any = field(default_factory=list)
    artifact_reference: str = ""
    cost_reference: str = ""
    memory_reference: str = ""
    debug_reference: str = ""
    result: Any = field(default_factory=dict)
    impact: Any = field(default_factory=dict)
    risk: str = ""
    status: str = ""
    metadata: Any = field(default_factory=dict)
    event_hash: str = ""
    previous_event_hash: str = ""

    # ------------------------------------------------------------ 构造

    @classmethod
    def create(
        cls,
        event_type: str,
        *,
        trace_id: str = "",
        correlation_id: str = "",
        project_id: str = "",
        workspace_id: str = "",
        task_id: str = "",
        agent_id: str = "",
        actor_type: str = "system",
        actor_id: str = "",
        action: str = "",
        lifecycle_state: str = "",
        source: str = "",
        input_reference: str = "",
        decision: str = "",
        decision_reason: str = "",
        evidence: Any = None,
        policy: str = "",
        policy_result: str = "",
        approval: Any = None,
        parent_event_id: str = "",
        related_event_ids: Any = None,
        artifact_reference: str = "",
        cost_reference: str = "",
        memory_reference: str = "",
        debug_reference: str = "",
        result: Any = None,
        impact: Any = None,
        risk: str = "",
        status: str = "",
        metadata: Any = None,
        timestamp: str = "",
        previous_event_hash: str = "",
    ) -> "AuditEvent":
        """工厂方法: 自动生成 audit_id (uuid4) + timestamp (UTC ISO)。

        event_type 非法 (不在 EVENT_TYPES) → ValueError (显式, 不静默 —
        事件类型是审计契约; 测试/调用方传标准类型)。
        """
        normalized = str(event_type or "").strip()
        if normalized not in EVENT_TYPES:
            raise ValueError(
                f"非法事件类型: {normalized!r} (可用: {', '.join(EVENT_TYPES)})"
            )
        return cls(
            audit_id=str(uuid.uuid4()),
            trace_id=str(trace_id or ""),
            correlation_id=str(correlation_id or ""),
            project_id=str(project_id or ""),
            workspace_id=str(workspace_id or ""),
            task_id=str(task_id or ""),
            agent_id=str(agent_id or ""),
            actor_type=str(actor_type or "system"),
            actor_id=str(actor_id or ""),
            event_type=normalized,
            action=str(action or ""),
            timestamp=str(timestamp or _now_iso()),
            lifecycle_state=str(lifecycle_state or ""),
            source=str(source or ""),
            input_reference=str(input_reference or ""),
            decision=str(decision or ""),
            decision_reason=str(decision_reason or ""),
            evidence=list(evidence) if isinstance(evidence, list) else [],
            policy=str(policy or ""),
            policy_result=str(policy_result or ""),
            approval=dict(approval) if isinstance(approval, dict) else {},
            parent_event_id=str(parent_event_id or ""),
            related_event_ids=(
                list(related_event_ids) if isinstance(related_event_ids, list) else []
            ),
            artifact_reference=str(artifact_reference or ""),
            cost_reference=str(cost_reference or ""),
            memory_reference=str(memory_reference or ""),
            debug_reference=str(debug_reference or ""),
            result=result if isinstance(result, dict) else {},
            impact=impact if isinstance(impact, dict) else {},
            risk=str(risk or ""),
            status=str(status or ""),
            metadata=metadata if isinstance(metadata, dict) else {},
            event_hash="",
            previous_event_hash=str(previous_event_hash or ""),
        )

    # ------------------------------------------------------------ 序列化

    def to_dict(self, *, redact_sensitive: bool = True) -> dict[str, Any]:
        """→ dict (落盘/传输视图)。redact_sensitive=True (缺省) 时对自由
        dict 字段 (evidence/approval/result/impact/metadata) 递归脱敏 —
        纵深防御: 即使调用方未脱敏, 敏感键也不进入审计存储。"""
        payload: dict[str, Any] = {
            "audit_id": self.audit_id,
            "trace_id": self.trace_id,
            "correlation_id": self.correlation_id,
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "event_type": self.event_type,
            "action": self.action,
            "timestamp": self.timestamp,
            "lifecycle_state": self.lifecycle_state,
            "source": self.source,
            "input_reference": self.input_reference,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "evidence": self.evidence,
            "policy": self.policy,
            "policy_result": self.policy_result,
            "approval": self.approval,
            "parent_event_id": self.parent_event_id,
            "related_event_ids": self.related_event_ids,
            "artifact_reference": self.artifact_reference,
            "cost_reference": self.cost_reference,
            "memory_reference": self.memory_reference,
            "debug_reference": self.debug_reference,
            "result": self.result,
            "impact": self.impact,
            "risk": self.risk,
            "status": self.status,
            "metadata": self.metadata,
            "event_hash": self.event_hash,
            "previous_event_hash": self.previous_event_hash,
        }
        if redact_sensitive:
            for key in ("evidence", "approval", "result", "impact", "metadata"):
                payload[key] = redact(payload[key])
        return payload

    @classmethod
    def from_dict(cls, data: Any) -> "AuditEvent":
        """dict → AuditEvent (失败安全: 非 dict → 空事件; 缺失字段缺省)。"""
        if not isinstance(data, dict):
            return cls()
        return cls(
            audit_id=str(data.get("audit_id") or ""),
            trace_id=str(data.get("trace_id") or ""),
            correlation_id=str(data.get("correlation_id") or ""),
            project_id=str(data.get("project_id") or ""),
            workspace_id=str(data.get("workspace_id") or ""),
            task_id=str(data.get("task_id") or ""),
            agent_id=str(data.get("agent_id") or ""),
            actor_type=str(data.get("actor_type") or "system"),
            actor_id=str(data.get("actor_id") or ""),
            event_type=str(data.get("event_type") or ""),
            action=str(data.get("action") or ""),
            timestamp=str(data.get("timestamp") or ""),
            lifecycle_state=str(data.get("lifecycle_state") or ""),
            source=str(data.get("source") or ""),
            input_reference=str(data.get("input_reference") or ""),
            decision=str(data.get("decision") or ""),
            decision_reason=str(data.get("decision_reason") or ""),
            evidence=data.get("evidence") or [],
            policy=str(data.get("policy") or ""),
            policy_result=str(data.get("policy_result") or ""),
            approval=data.get("approval") or {},
            parent_event_id=str(data.get("parent_event_id") or ""),
            related_event_ids=data.get("related_event_ids") or [],
            artifact_reference=str(data.get("artifact_reference") or ""),
            cost_reference=str(data.get("cost_reference") or ""),
            memory_reference=str(data.get("memory_reference") or ""),
            debug_reference=str(data.get("debug_reference") or ""),
            result=data.get("result") or {},
            impact=data.get("impact") or {},
            risk=str(data.get("risk") or ""),
            status=str(data.get("status") or ""),
            metadata=data.get("metadata") or {},
            event_hash=str(data.get("event_hash") or ""),
            previous_event_hash=str(data.get("previous_event_hash") or ""),
        )

    # ------------------------------------------------------------ hash

    def hash_payload(self) -> dict[str, Any]:
        """hash 输入负载: 全字段除 event_hash 本身 (含 previous_event_hash —
        链式防篡改, 设计 §2: sha256(audit_id + canonical_json +
        previous_event_hash))。"""
        payload = self.to_dict(redact_sensitive=False)
        payload.pop("event_hash", None)
        return payload

    @staticmethod
    def hash_event(
        audit_id: str,
        payload: Any,
        previous_event_hash: str = "",
    ) -> str:
        """sha256(audit_id + canonical_json + previous_event_hash) — 确定性。"""
        digest_input = (
            f"{audit_id}|{canonical_json(payload)}|{previous_event_hash}"
        )
        return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()

    def compute_hash(self) -> str:
        """计算本事件 hash (不含 event_hash 字段 — 自指稳定)。"""
        return self.hash_event(
            self.audit_id, self.hash_payload(), self.previous_event_hash
        )

    def seal(self, previous_event_hash: str = "") -> "AuditEvent":
        """封存: 设置 previous_event_hash + 计算 event_hash → 返回自身。"""
        if not self.audit_id:
            # S10-069 修复: 封存时保证 audit_id 唯一 (append 直收实例时也生成)
            self.audit_id = str(uuid.uuid4())
        self.previous_event_hash = str(previous_event_hash or "")
        self.event_hash = self.compute_hash()
        return self

    def is_sealed(self) -> bool:
        """是否已封存 (event_hash 非空且等于重算值)。"""
        if not self.event_hash:
            return False
        return self.event_hash == self.compute_hash()

    def __repr__(self) -> str:  # pragma: no cover — 调试视图
        return (
            f"AuditEvent({self.event_type or '?'}, "
            f"trace={self.trace_id[:8] or '?'}, hash={self.event_hash[:8] or 'unsealed'})"
        )
