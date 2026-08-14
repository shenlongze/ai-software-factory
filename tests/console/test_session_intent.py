"""tests/console/test_session_intent.py — Intent Layer 基础 (S10-047 Task 005)。

设计: docs/sprint10/S10-046-intent-layer-design.md (§2 Intent Object / §3 Q1 / §4 注册表 / §6 边界)
覆盖:
- KeywordIntentParser 关键词识别: 创建/做一个/开发一个 → create_project;
  加/修复/写 → run_task; 花了多少/成本/费用 → show_cost; 状态/看看 → show_status
- 未识别 → None (含空输入/纯空白)
- IntentObject 结构化: intent_type/params/constraints/confidence/raw
  (+ 验收口径别名 type/parameters)
- 接口: IntentParser ABC (abstractmethod, 不可直接实例化);
  KeywordIntentParser 为子类; 未来 LLMIntentParser 扩展点可用 (桩实现)

basename 全仓库唯一 (test_session_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib
import inspect

import pytest

INTENT_MOD = importlib.import_module("factory-console.session.intent")

P = INTENT_MOD.KeywordIntentParser


# ------------------------------------------------------------------ 关键词识别 (验收 A)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("创建一个APP", INTENT_MOD.INTENT_CREATE_PROJECT),
        ("帮我做一个电商 APP", INTENT_MOD.INTENT_CREATE_PROJECT),
        ("开发一个工具", INTENT_MOD.INTENT_CREATE_PROJECT),
        ("加测试", INTENT_MOD.INTENT_RUN_TASK),
        ("修复 main.py 的 bug", INTENT_MOD.INTENT_RUN_TASK),
        ("写单元测试", INTENT_MOD.INTENT_RUN_TASK),
        ("花了多少", INTENT_MOD.INTENT_SHOW_COST),
        ("用了多少成本", INTENT_MOD.INTENT_SHOW_COST),
        ("这个月的费用", INTENT_MOD.INTENT_SHOW_COST),
        ("状态", INTENT_MOD.INTENT_SHOW_STATUS),
        ("看看", INTENT_MOD.INTENT_SHOW_STATUS),
    ],
)
def test_keyword_recognized(text, expected):
    intent = P().parse(text)
    assert intent is not None
    assert intent.intent_type == expected
    assert intent.raw == text  # 原始输入保留 (审计)


@pytest.mark.parametrize("text", ["hello world", "随便聊聊", "1+1=?", "", "   "])
def test_keyword_unrecognized_none(text):
    assert P().parse(text) is None


def test_parse_none_input():
    assert P().parse(None) is None  # 类型宽容: None → 未识别


# ------------------------------------------------------------------ IntentObject 结构化 (验收 B)


def test_intent_object_structured():
    intent = P().parse("创建一个APP")
    assert intent.intent_type == INTENT_MOD.INTENT_CREATE_PROJECT
    assert isinstance(intent.params, dict)
    assert isinstance(intent.constraints, dict)
    assert intent.confidence == 1.0  # 规则确定性匹配
    assert intent.raw == "创建一个APP"
    # 验收口径别名: type / parameters
    assert intent.type == intent.intent_type
    assert intent.parameters is intent.params


def test_intent_object_params_extraction():
    # 关键词后剩余文本作为参数 hint (设计 §2 示例口径)
    intent = P().parse("加测试")
    assert intent.parameters == {"objective": "测试"}
    intent = P().parse("创建一个APP")
    assert intent.parameters["name"] == "一个APP"
    # show_cost 固定口径: period=session (设计 §2 示例)
    intent = P().parse("花了多少")
    assert intent.parameters == {"period": "session"}
    # 无 hint → 空 params (不伪造参数)
    assert P().parse("创建").parameters == {}


def test_intent_object_defaults():
    obj = INTENT_MOD.IntentObject(intent_type="show_status")
    assert obj.params == {} and obj.constraints == {}
    assert obj.confidence == 1.0 and obj.raw == ""


# ------------------------------------------------------------------ 接口 (验收 C: 未来 LLM 扩展)


def test_intent_parser_is_abstract():
    assert inspect.isabstract(INTENT_MOD.IntentParser)
    with pytest.raises(TypeError):
        INTENT_MOD.IntentParser()  # ABC 不可直接实例化


def test_keyword_parser_subclasses_interface():
    assert issubclass(INTENT_MOD.KeywordIntentParser, INTENT_MOD.IntentParser)
    assert isinstance(P(), INTENT_MOD.IntentParser)


def test_llm_parser_extension_point():
    """未来 LLMIntentParser 扩展点: 同接口实现 parse 即可替换 (S10-046 §3 Q1)。"""

    class LLMIntentParser(INTENT_MOD.IntentParser):  # 桩: 模拟 LLM 结构化输出
        def parse(self, text):
            return INTENT_MOD.IntentObject(
                intent_type="create_project",
                params={"name": "ecommerce", "goal": text},
                constraints={"provider": "deepseek"},
                confidence=0.95,
                raw=text,
            )

    llm = LLMIntentParser()
    intent = llm.parse("帮我创建一个电商 APP")
    assert intent.intent_type == "create_project"
    assert intent.params["name"] == "ecommerce"
    assert intent.confidence == 0.95  # LLM 置信度 (<1.0, 触发确认门条件)
    assert llm.parse("x").raw == "x"


def test_parse_signature_contract():
    """接口契约: parse(text: str) -> IntentObject | None (设计 §2)。"""
    sig = inspect.signature(INTENT_MOD.IntentParser.parse)
    assert "text" in sig.parameters
    assert sig.return_annotation is not inspect.Signature.empty
