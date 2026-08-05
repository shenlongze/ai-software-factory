"""tests/agents/agent_helpers.py — Agent/Skill 构造 helper (测试共享, 平铺模块同 task_helpers 模式)。"""

from __future__ import annotations

from agents.models import Agent, Skill


def make_agent(agent_id: str = "A-001", **overrides) -> Agent:
    """默认 Agent; overrides 覆盖任意字段。"""
    defaults = {
        "id": agent_id,
        "name": f"agent {agent_id}",
        "role": "backend-developer",
        "description": "默认测试 Agent",
        "skills": ["backend"],
    }
    defaults.update(overrides)
    return Agent(**defaults)


def make_skill(skill_id: str = "backend", **overrides) -> Skill:
    """默认 Skill; overrides 覆盖任意字段。"""
    defaults = {
        "id": skill_id,
        "name": f"skill {skill_id}",
        "category": "backend",
        "description": "默认测试 Skill",
        "capabilities": ["java", "spring boot"],
        "version": "1.0.0",
    }
    defaults.update(overrides)
    return Skill(**defaults)
