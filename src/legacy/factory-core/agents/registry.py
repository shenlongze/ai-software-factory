"""agents/registry.py — AgentRegistry / SkillRegistry: register/get/list/remove/find_by_skill。

设计依据:
- phase3b-status.md: AgentRegistry + SkillRegistry (register/get/list/remove/find_by_skill)
- event-model.md §4.3 事件先落库再行动 — 落地口径与 tasks CLI 一致: 存储先落地,
  事件后发 (events 独立 SQLite, 事件失败不应回滚已落盘状态, 由上层重试/补发)。
- Event 集成一律经 EventLogger (不直接写 EventStore); logger 可缺省 (纯存储操作,
  库/测试场景)。

写方法返回 `(对象, Event | None)`: Event 含存储层回填的 seq, 供 CLI 输出审计锚点。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from events.logger import EventLogger
from events.models import Event, EventType

from .models import Agent, AgentStatus, Skill
from .store import AgentStore, SkillStore


class AgentRegistryError(Exception):
    """AgentRegistry 基础异常。"""


class AgentExistsError(AgentRegistryError):
    """Agent 已存在 (register 冲突)。"""


class AgentNotFoundError(AgentRegistryError):
    """Agent 不存在。"""


class AgentRegistry:
    """Agent 注册表: AgentStore 持久化 + 事件 (agent.registered/updated/removed/viewed)。"""

    SOURCE = "agent_registry"  # event-model §2.1 source 取值

    def __init__(self, store: AgentStore, logger: EventLogger | None = None):
        self._store = store
        self._logger = logger

    @property
    def store(self) -> AgentStore:
        return self._store

    # ------------------------------------------------------------------ 写

    def register(self, agent: Agent) -> tuple[Agent, Event | None]:
        """注册新 Agent; id 冲突抛 AgentExistsError; 发 agent.registered。"""
        if self.get(agent.id) is not None:
            raise AgentExistsError(f"agent already exists: {agent.id}")
        self._store.save(agent)
        ev = self._emit(
            EventType.AGENT_REGISTERED, agent, "register agent",
            {"name": agent.name, "role": agent.role, "skills": agent.skills,
             "description": agent.description},
        )
        return agent, ev

    def update(self, agent: Agent) -> tuple[Agent, Event | None]:
        """更新已有 Agent (刷新 updated_at); 不存在抛 AgentNotFoundError; 发 agent.updated。"""
        old = self.get(agent.id)
        if old is None:
            raise AgentNotFoundError(f"agent not found: {agent.id}")
        agent.updated_at = datetime.now(timezone.utc)
        self._store.save(agent)
        ev = self._emit(
            EventType.AGENT_UPDATED, agent, "update agent",
            {"name": agent.name, "role": agent.role, "status": agent.status.value,
             "skills": agent.skills, "from_status": old.status.value},
        )
        return agent, ev

    def remove(self, agent_id: str) -> tuple[Agent, Event | None]:
        """移除 Agent; 不存在抛 AgentNotFoundError; 发 agent.removed。"""
        agent = self.get(agent_id)
        if agent is None:
            raise AgentNotFoundError(f"agent not found: {agent_id}")
        self._store.remove(agent_id)
        ev = self._emit(
            EventType.AGENT_REMOVED, agent, "remove agent",
            {"name": agent.name, "role": agent.role, "status": agent.status.value,
             "skills": agent.skills},
        )
        return agent, ev

    # ------------------------------------------------------------------ 状态更新 (Phase 4B-3)

    # 以下三个方法为分配层的状态原语 (AgentAllocator 独占使用): 只改 Agent 自身状态,
    # 不发事件 — 状态变更的审计由 assignment 域事件承载 (agent.assignment.* / agent.released,
    # ADR-0008 决策 3)。任务关联经 Agent.current_task 记录 (引用, 不复制任务数据)。

    def set_status(self, agent_id: str, status: AgentStatus | str) -> Agent:
        """设置 Agent 状态 (低层原语, 任意合法状态); 不存在抛 AgentNotFoundError。"""
        want = AgentStatus.parse(status) if isinstance(status, str) else status
        agent = self.get(agent_id)
        if agent is None:
            raise AgentNotFoundError(f"agent not found: {agent_id}")
        agent.status = want
        agent.updated_at = datetime.now(timezone.utc)
        self._store.save(agent)
        return agent

    def mark_working(self, agent_id: str, task_id: str | None = None) -> Agent:
        """标记工作中: AVAILABLE → WORKING, 记录当前任务 id (引用); 不发事件。"""
        agent = self.set_status(agent_id, AgentStatus.WORKING)
        agent.current_task = task_id
        self._store.save(agent)
        return agent

    def mark_available(self, agent_id: str) -> Agent:
        """标记空闲: → AVAILABLE, 清空当前任务引用; 不发事件。"""
        agent = self.set_status(agent_id, AgentStatus.AVAILABLE)
        agent.current_task = None
        self._store.save(agent)
        return agent

    def _emit(self, type_: EventType, agent: Agent, action: str, payload: dict[str, Any]) -> Event | None:
        if self._logger is None:
            return None
        return self._logger.record(
            type_, source=self.SOURCE, agent_id=agent.id,
            stage=agent.status.value.lower(), action=action, result="OK", payload=payload,
        )

    # ------------------------------------------------------------------ 读

    def get(self, agent_id: str) -> Agent | None:
        """按 id 取 Agent; 不存在返回 None。"""
        return self._store.load(agent_id)

    def list(
        self,
        *,
        status: AgentStatus | str | None = None,
        role: str | None = None,
        skill: str | None = None,
    ) -> list[Agent]:
        """全部 Agent (按 id 排序), 可选按状态/角色/技能过滤。"""
        want = AgentStatus.parse(status) if isinstance(status, str) else status
        agents = []
        for a in self._store.load_all().values():
            if want is not None and a.status is not want:
                continue
            if role is not None and a.role != role:
                continue
            if skill is not None and skill not in a.skills:
                continue
            agents.append(a)
        return sorted(agents, key=lambda a: a.id)

    def find_by_skill(self, skill: str) -> list[Agent]:
        """按技能找 Agent: 精确匹配 Agent.skills 中的元素 (Skill.id 或自由标签)。"""
        return self.list(skill=skill)

    def count(self) -> int:
        return len(self._store.load_all())

    def ids(self) -> list[str]:
        """现有 Agent id 列表 (排序, CLI 自动编号用)。"""
        return sorted(self._store.load_all())

    def next_id(self, prefix: str = "A-") -> str:
        """自动编号: 取现有最大数字后缀 +1 (如 A-001 → A-002)。"""
        max_n = 0
        for agent_id in self.ids():
            rest = agent_id[len(prefix):] if agent_id.startswith(prefix) else ""
            if rest.isdigit():
                max_n = max(max_n, int(rest))
        return f"{prefix}{max_n + 1:03d}"


class SkillRegistryError(Exception):
    """SkillRegistry 基础异常。"""


class SkillExistsError(SkillRegistryError):
    """Skill 已存在 (register 冲突)。"""


class SkillNotFoundError(SkillRegistryError):
    """Skill 不存在。"""


class SkillRegistry:
    """Skill 注册表 (能力目录): SkillStore 持久化 + 事件 (skill.registered/removed/viewed)。"""

    SOURCE = "skill_registry"

    def __init__(self, store: SkillStore, logger: EventLogger | None = None):
        self._store = store
        self._logger = logger

    @property
    def store(self) -> SkillStore:
        return self._store

    # ------------------------------------------------------------------ 写

    def register(self, skill: Skill) -> tuple[Skill, Event | None]:
        """注册新 Skill; id 冲突抛 SkillExistsError; 发 skill.registered。"""
        if self.get(skill.id) is not None:
            raise SkillExistsError(f"skill already exists: {skill.id}")
        self._store.save(skill)
        ev = self._emit(
            EventType.SKILL_REGISTERED, skill, "register skill",
            {"name": skill.name, "category": skill.category, "version": skill.version,
             "capabilities": skill.capabilities},
        )
        return skill, ev

    def remove(self, skill_id: str) -> tuple[Skill, Event | None]:
        """移除 Skill; 不存在抛 SkillNotFoundError; 发 skill.removed。"""
        skill = self.get(skill_id)
        if skill is None:
            raise SkillNotFoundError(f"skill not found: {skill_id}")
        self._store.remove(skill_id)
        ev = self._emit(
            EventType.SKILL_REMOVED, skill, "remove skill",
            {"name": skill.name, "category": skill.category, "version": skill.version},
        )
        return skill, ev

    def _emit(self, type_: EventType, skill: Skill, action: str, payload: dict[str, Any]) -> Event | None:
        if self._logger is None:
            return None
        return self._logger.record(
            type_, source=self.SOURCE, stage=skill.category, action=action,
            result="OK", payload=payload,
        )

    # ------------------------------------------------------------------ 读

    def get(self, skill_id: str) -> Skill | None:
        """按 id 取 Skill; 不存在返回 None。"""
        return self._store.load(skill_id)

    def list(self, *, category: str | None = None) -> list[Skill]:
        """全部 Skill (按 id 排序), 可选按类别过滤。"""
        skills = [
            s for s in self._store.load_all().values()
            if category is None or s.category == category
        ]
        return sorted(skills, key=lambda s: s.id)

    def count(self) -> int:
        return len(self._store.load_all())

    def ids(self) -> list[str]:
        return sorted(self._store.load_all())

    def next_id(self, prefix: str = "S-") -> str:
        """自动编号: 取现有最大数字后缀 +1 (如 S-001 → S-002)。"""
        max_n = 0
        for skill_id in self.ids():
            rest = skill_id[len(prefix):] if skill_id.startswith(prefix) else ""
            if rest.isdigit():
                max_n = max(max_n, int(rest))
        return f"{prefix}{max_n + 1:03d}"
