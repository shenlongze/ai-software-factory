"""agents — Agent + Skill Registry (Phase 3B: 身份管理 + 能力目录 + JSON 持久化 + Event 集成)。

对外出口 (phase3b-status.md): Agent / AgentStatus / Skill / AgentRegistry / SkillRegistry /
AgentStore / SkillStore + 内置技能目录 (BUILTIN_SKILLS)。
"""

from .models import Agent, AgentStatus, Skill
from .registry import (
    AgentExistsError,
    AgentNotFoundError,
    AgentRegistry,
    AgentRegistryError,
    SkillExistsError,
    SkillNotFoundError,
    SkillRegistry,
    SkillRegistryError,
)
from .skills import BUILTIN_SKILLS, builtin_skill, builtin_skill_ids
from .store import AgentStore, CorruptStoreError, RegistryStoreError, SkillStore

__all__ = [
    "Agent",
    "AgentStatus",
    "Skill",
    "AgentStore",
    "SkillStore",
    "AgentRegistry",
    "SkillRegistry",
    "AgentRegistryError",
    "AgentExistsError",
    "AgentNotFoundError",
    "SkillRegistryError",
    "SkillExistsError",
    "SkillNotFoundError",
    "RegistryStoreError",
    "CorruptStoreError",
    "BUILTIN_SKILLS",
    "builtin_skill",
    "builtin_skill_ids",
]
