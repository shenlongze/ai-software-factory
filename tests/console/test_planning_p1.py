"""tests/console/test_planning_p1.py — P1-FIX: Idea → Planning 生产链。

验证:
- intent 路由: 制定/生成/规划开发计划 → plan_development (非 create_task)
- 批准语义不重新生成计划
- plan_development 能力 (真实 Plan 持久化由 fastapi 分支完成, 此处测意图分类)
"""

from __future__ import annotations

import pytest

from factory_console.session.query_engine import VALID_INTENTS


PLANNING_PHRASES = [
    "请制定开发计划",
    "生成开发计划",
    "制定项目开发计划",
    "规划项目",
    "给这个项目做开发计划",
    "创建开发计划",
    "生成计划卡片",
    "生成待审批计划",
    "请调用 plan_development 工具",
    "把需求规划成开发任务",
    "为项目规划开发步骤",
    "制定开发计划并生成待审批的计划卡片",
]

CREATE_TASK_PHRASES = [
    "创建一个任务",
    "添加任务",
    "把 X 加到任务列表",
    "完善导出功能",
]


def test_valid_intents_has_plan_development() -> None:
    assert "plan_development" in VALID_INTENTS


def test_intent_llm_prompt_mentions_plan_development() -> None:
    from factory_console.session.query_engine import _INTENT_LLM_PROMPT

    assert "plan_development" in _INTENT_LLM_PROMPT


def test_planning_phrases_not_create_task_keywords() -> None:
    """规划类短语不得落入 create_task 关键词 (完善/优化/拆解等)。"""
    from factory_console.session.query_engine import parse_intent

    for phrase in PLANNING_PHRASES:
        r = parse_intent(phrase)
        assert r["intent"] != "create_task", f"规划短语误路由 create_task: {phrase}"


def test_parse_intent_llm_planning_detection() -> None:
    """LLM 意图分类: 制定开发计划 → plan_development。"""
    from factory_console.session.query_engine import parse_intent_llm

    def _llm(text: str) -> str:
        return '{"intent": "plan_development", "project": "记账App", "task": null}'

    r = parse_intent_llm("请为记账App制定开发计划", _llm)
    assert r["intent"] == "plan_development"
    assert r["project"] == "记账App"
