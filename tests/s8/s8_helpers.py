"""tests/s8/s8_helpers.py — S8-001 PM Agent 测试构造/断言 helper (唯一名)。

- product_payload_ok: 合法 product 契约载荷 (7 节) — 与 org CONTRACTS
  product 同构 (market_analysis/user_persona/user_journey/problem_statement/
  feature_list/mvp_scope/user_stories)
- product_json: 合法 product 的 JSON 串 (mock provider 注入, 围栏/散文变体)
- event_sequence / payload_of: 事件库断言辅助 (org.workflow.* / org.stage.*)
- make_idea_artifact: idea 产物 dict (executor context inputs 契约)
"""

from __future__ import annotations

import json
from typing import Any


def product_payload_ok(*, feature_count: int = 3, story_count: int = 2) -> dict[str, Any]:
    """合法 product 契约载荷 (7 节; feature_list/mvp_scope/user_stories 结构)。"""
    return {
        "market_analysis": "目标市场: 个人记账用户; 竞争: 手工表格/同类 App",
        "user_persona": "25-40 岁上班族, 需要简单记账与月度报表",
        "user_journey": "记录一笔支出 → 查看分类统计 → 月底生成报表",
        "problem_statement": "手工记账繁琐, 现有工具功能过重",
        "feature_list": [f"功能 {i}" for i in range(1, feature_count + 1)],
        "mvp_scope": {
            "in": ["支出记录", "分类统计"],
            "out": ["多人协作", "自动导入账单"],
        },
        "user_stories": [
            {"as-a": "用户", "i-want": "快速记录支出", "so-that": "不遗漏"},
            {"as-a": "用户", "i-want": "查看月度报表", "so-that": "掌握开销"},
        ][:story_count] or ["用户故事占位"],
    }


def product_json(
    *,
    fenced: bool = False,
    prose: bool = False,
    **overrides: Any,
) -> str:
    """合法 product 的 JSON 串 (mock provider 注入; 围栏/散文变体可叠加)。"""
    payload = product_payload_ok()
    payload.update(overrides)
    body = json.dumps(payload, ensure_ascii=False)
    if fenced:
        body = f"```json\n{body}\n```"
    if prose:
        body = f"以下是产品分析结果:\n{body}\n以上为全部内容。"
    return body


def event_sequence(store: Any) -> list[str]:
    return [e.type.value for e in store.query()]


def payload_of(store: Any, event_type: str) -> dict[str, Any]:
    for e in store.query():
        if e.type.value == event_type:
            return dict(e.payload)
    raise AssertionError(f"no event of type {event_type!r} found")


def make_idea_artifact(*, idea: str = "开发一个记账 Web App") -> dict[str, Any]:
    """idea 产物 dict (executor context inputs 契约: type + metadata.idea)。"""
    return {"type": "idea", "ref": "file:///idea.txt", "metadata": {"idea": idea}}
