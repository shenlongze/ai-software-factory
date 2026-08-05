"""assignment — Agent Assignment Layer (Phase 4B-3: 匹配 + 分配 + 工作关系持久化)。

对外出口 (phase4b3-status.md): AgentAssignment / AssignmentStatus / AgentMatcher /
AgentAllocator / AssignmentStore + 各域异常。Agent 员工信息仍在 AgentRegistry
(不复制数据), Assignment 只存工作关系 (agent_id 引用)。

原则: Agent != Assignment — Registry=员工信息+状态, Assignment=工作关系, 不混写。
"""

from .allocator import (
    AgentAllocator,
    AgentAllocatorError,
    AgentNotAvailableError,
    AssignmentNotFoundError,
    AssignmentStateError,
    NoAvailableAgentError,
)
from .matcher import AgentMatcher
from .models import AgentAssignment, AssignmentStatus
from .store import AssignmentStore, AssignmentStoreError, CorruptAssignmentStoreError

__all__ = [
    "AgentAssignment",
    "AssignmentStatus",
    "AgentMatcher",
    "AgentAllocator",
    "AssignmentStore",
    "AgentAllocatorError",
    "AgentNotAvailableError",
    "AssignmentNotFoundError",
    "AssignmentStateError",
    "NoAvailableAgentError",
    "AssignmentStoreError",
    "CorruptAssignmentStoreError",
]
