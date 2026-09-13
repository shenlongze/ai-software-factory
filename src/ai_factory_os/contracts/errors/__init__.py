"""errors — 统一错误码。零依赖。"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorCode(str, Enum):
    """全平台统一错误码（新增须在此登记）。"""

    # 通用
    NOT_FOUND = "not_found"
    INVALID_STATE = "invalid_state"
    INVALID_INPUT = "invalid_input"
    CONFLICT = "conflict"
    # 组织
    SUBJECT_UNKNOWN = "subject_unknown"
    AUTHORITY_DENIED = "authority_denied"
    # 工作
    DEPENDENCY_MISSING = "dependency_missing"
    DEPENDENCY_CYCLE = "dependency_cycle"
    CAPABILITY_REF_MISSING = "capability_ref_missing"
    # 资源
    CAPABILITY_UNKNOWN = "capability_unknown"
    NO_BINDING = "no_binding"
    RESOLUTION_UNRESOLVED = "resolution_unresolved"
    CAPACITY_EXHAUSTED = "capacity_exhausted"
    # 执行
    ACTIVE_EXECUTION_EXISTS = "active_execution_exists"
    EXECUTION_FAILED = "execution_failed"
    # 治理
    GATE_NOT_APPROVED = "gate_not_approved"
    BUDGET_EXCEEDED = "budget_exceeded"
    POLICY_DENIED = "policy_denied"
    # 事实
    EVENT_APPEND_ONLY = "event_append_only"
    EVENT_CHAIN_BROKEN = "event_chain_broken"


@dataclass(frozen=True)
class ErrorPayload:
    """结构化错误载荷（可跨进程传递）。"""

    code: ErrorCode
    message: str
    subject_ref: str = ""
    details: tuple[str, ...] = ()


class OsError(Exception):
    """平台统一异常；必须携带 ErrorCode。"""

    def __init__(self, code: ErrorCode, message: str, subject_ref: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.subject_ref = subject_ref

    def payload(self) -> ErrorPayload:
        return ErrorPayload(code=self.code, message=self.message, subject_ref=self.subject_ref)
