"""assignment/matcher.py — AgentMatcher: 按步骤要求 (role/skill) 从 AgentRegistry 挑候选。

设计依据:
- phase4b3-status.md: 输入 workflow step (required_skill/required_role) → 查 AgentRegistry
  → 候选; 规则: ① role 必须匹配 ② skill 必须包含 required_skill ③ status 必须 AVAILABLE;
  多候选排序: skill 匹配数量优先。
- 纯读模块 (无副作用, 不发事件): 候选计算与排序是确定性函数, 便于单测。

排序语义 (skill 匹配数量优先, ADR-0008 决策 2):
  1. 主键: 命中必需技能数降序 — required_skill 支持单个 (str) 或多个 (list) 技能;
     Agent 覆盖的必需技能越多排名越前 (多技能步骤按覆盖度择优; 单技能步骤全部合格者同分)。
  2. 次键: agent id 升序 — 确定性 tie-break (跨测试稳定)。

返回 (agent, matched_count) 元组列表: 调用方 (AgentAllocator) 取首个即最优候选。
"""

from __future__ import annotations

from typing import Iterable

from agents.models import Agent, AgentStatus
from agents.registry import AgentRegistry
from workflows.models import WorkflowStep


class AgentMatcher:
    """按步骤/条件过滤 + 排序 Agent 候选 (只读, 无事件)。"""

    def __init__(self, registry: AgentRegistry):
        self._registry = registry

    @property
    def registry(self) -> AgentRegistry:
        return self._registry

    # ------------------------------------------------------------------ 匹配

    def candidates(
        self,
        step: WorkflowStep,
    ) -> list[tuple[Agent, int]]:
        """按步骤匹配候选: role/skill/AVAILABLE 过滤 + skill 匹配数量排序。"""
        return self.match_criteria(
            required_role=step.required_role,
            required_skill=step.required_skill,
        )

    def match_criteria(
        self,
        *,
        required_role: str | None = None,
        required_skill: str | Iterable[str] | None = None,
    ) -> list[tuple[Agent, int]]:
        """按条件匹配候选 (role/skill/AVAILABLE 过滤 + skill 匹配数量排序)。

        - required_role: Agent.role 必须精确相等 (None 表示不限角色)。
        - required_skill: 单个技能字符串或技能集合; Agent.skills 必须至少命中一个必需技能
          (None/空集表示不限技能)。matched_count = 命中的必需技能数 (排序主键)。
        """
        skills = _to_skill_set(required_skill)
        candidates: list[tuple[Agent, int]] = []
        for agent in self._registry.list(status=AgentStatus.AVAILABLE):
            if required_role is not None and agent.role != required_role:
                continue  # ① role 必须匹配
            matched = len(skills & set(agent.skills))
            if skills and matched == 0:
                continue  # ② skill 必须包含 required_skill (至少命中其一)
            candidates.append((agent, matched))
        # ③ AVAILABLE 已由 registry.list 过滤; 排序: 匹配技能数降序, 再 agent id 升序 (确定性)
        candidates.sort(key=lambda t: (-t[1], t[0].id))
        return candidates

    def best(self, step: WorkflowStep) -> Agent | None:
        """最优候选 (排序首位); 无候选返回 None。"""
        candidates = self.candidates(step)
        return candidates[0][0] if candidates else None


def _to_skill_set(value: str | Iterable[str] | None) -> set[str]:
    """规范化必需技能集: 字符串 → 单元素集; None → 空集。"""
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    return set(v for v in value if v)
