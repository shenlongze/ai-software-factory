"""Cognitive Golden Path — Phase 1: LLM Semantic Interpreter 测试。

验证 Golden Path §7/§8:
- LLM 输出 → parse_semantic_json → validate_proposal → apply_operations (生产管道)
- LLM 不可用/输出非法 → 显式降级 (不猜事实, 不部分写 Truth)
- Context Assembly (prompt 含持久化 Understanding, 不猜)
- ProductUnderstandingService(semantic=True) → LLM 语义理解真正改 Truth

用注入 fake_llm 模拟 DeepSeek 输出 (测试不依赖真实 LLM; 生产路径同一代码)。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from factory_console import conversation_app as ca  # noqa: E402
from factory_console import product_understanding as pu  # noqa: E402
from factory_console.llm_semantic_interpreter import (  # noqa: E402
    build_llm_prompt, llm_semantic_interpreter, parse_semantic_json,
)
from factory_console.semantic_proposal import ProposalValidationError  # noqa: E402


@pytest.fixture()
def root(tmp_path: Path) -> str:
    return str(tmp_path / "factory")


@pytest.fixture()
def conv(root: str) -> dict:
    return ca.ConversationApplicationService(root).create(title="飞机大战")


def _json_llm(payload: str):
    """fake LLM: 返回预设 JSON 文本。"""
    def _fn(prompt: str) -> str | None:
        return payload
    return _fn


class TestParseSemanticJson:
    def test_parses_clean_json(self) -> None:
        p = parse_semantic_json(
            '{"operations":[{"op":"ADD","fact_type":"REQUIREMENT",'
            '"content":"运行平台: 手机端"}],"reply":"好的"}')
        assert p["operations"][0]["op"] == "ADD"
        assert p["reply"] == "好的"

    def test_parses_fenced_json(self) -> None:
        p = parse_semantic_json(
            '```json\n{"operations":[{"op":"ADD","fact_type":"IDEA",'
            '"content":"飞机大战"}],"reply":"明白"}\n```')
        assert p["operations"][0]["content"] == "飞机大战"

    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(ProposalValidationError):
            parse_semantic_json("我不是 JSON")

    def test_rejects_invalid_op_inside(self) -> None:
        with pytest.raises(ProposalValidationError):
            parse_semantic_json(
                '{"operations":[{"op":"MAGIC","fact_type":"IDEA","content":"x"}]}')


class TestLlmInterpreterDegrade:
    def test_no_llm_fn_returns_clarify(self, root: str, conv: dict,
                                       monkeypatch: pytest.MonkeyPatch) -> None:
        """LLM 不可用 (llm_raw=None) → 不猜, 返回 CLARIFY proposal。

        R0 A2 (2026-09-08): 真实 LLM 环境 (DEEPSEEK_API_KEY 在场) 下,
        fn=None 会走默认 llm_raw 并真实调用 — 本测试显式把 llm_raw 置 None,
        与真实环境解耦, 恢复"LLM 不可用 → 降级"的本意。
        """
        import factory_console.console_sessions as _cs

        monkeypatch.setattr(_cs, "llm_raw", lambda prompt: None)
        snap = pu.understanding_snapshot(root, conv["id"])
        # 强制走"产品语义但无 LLM"分支: 用会命中 hint 的文本 + fn=None
        p = llm_semantic_interpreter(root, conv["id"], "我们要做手机端应用",
                                     snap, llm_fn=None)
        assert p["operations"] == []  # 不猜事实
        assert p["reply"]  # 诚实引导

    def test_llm_returns_none_degrades(self, root: str, conv: dict) -> None:
        snap = pu.understanding_snapshot(root, conv["id"])
        p = llm_semantic_interpreter(
            root, conv["id"], "我们要做手机端应用", snap,
            llm_fn=lambda prompt: None)
        assert p["operations"] == []

    def test_invalid_llm_output_degrades(self, root: str, conv: dict) -> None:
        snap = pu.understanding_snapshot(root, conv["id"])
        p = llm_semantic_interpreter(
            root, conv["id"], "我们要做手机端应用", snap,
            llm_fn=_json_llm("不是JSON"))
        assert p["operations"] == []


class TestLlmInterpreterPipeline:
    def test_llm_proposal_applies_to_truth(self, root: str,
                                           conv: dict) -> None:
        """LLM 说 ADD 手机端 → 真正写入 Truth (经 validate+apply)。"""
        llm = _json_llm(
            '{"operations":[{"op":"ADD","fact_type":"REQUIREMENT",'
            '"content":"运行平台: 手机端","confidence":0.95}],"reply":"好的"}')
        # interpreter 直接产出 proposal (带 LLM)
        snap = pu.understanding_snapshot(root, conv["id"])
        p = llm_semantic_interpreter(root, conv["id"], "手机端", snap, llm_fn=llm)
        assert p["operations"][0]["fact_type"] == "REQUIREMENT"
        # 经 service 管道 (validate + apply) 落盘
        svc = ca.ProductUnderstandingService(
            root, interpreter=_interp_with_llm(llm))
        res = svc.process_user_message(conv["id"], "手机端。")
        facts = pu.list_facts(root, conv["id"])
        assert any("手机端" in f["content"] for f in facts), res


def _interp_with_llm(llm):
    """包一层: interpreter 协议 (root, conv, text, snapshot) → proposal (带 LLM)。"""
    def _i(root: str, conversation_id: str, text: str,
           snapshot: dict) -> dict:
        from factory_console.llm_semantic_interpreter import llm_semantic_interpreter
        return llm_semantic_interpreter(root, conversation_id, text, snapshot,
                                        llm_fn=llm)
    return _i


class TestLlmPromptContext:
    def test_prompt_contains_understanding(self, root: str, conv: dict) -> None:
        """Context Assembly: prompt 必须含持久化 Understanding (不猜)。"""
        pu.upsert_fact(root, conv["id"], fact_type="IDEA", content="飞机大战")
        pu.upsert_fact(root, conv["id"], fact_type="REQUIREMENT",
                       content="运行平台: 手机端")
        snap = pu.understanding_snapshot(root, conv["id"])
        prompt = build_llm_prompt(snap, "那操作方式呢?")
        assert "飞机大战" in prompt
        assert "运行平台: 手机端" in prompt
        assert "那操作方式呢?" in prompt


class TestServiceSemanticMode:
    def test_service_semantic_mode_nl_update(self, root: str,
                                             conv: dict) -> None:
        """ProductUnderstandingService(semantic=True) 默认 LLM 解释 (无 LLM 环境
        自动降级 — 不抛错, 不写假事实)。"""
        svc = ca.ProductUnderstandingService(root, semantic=True)
        res = svc.process_user_message(conv["id"], "你好, 我想做个产品")
        assert "reply" in res
        assert "understanding_version" in res
        # "你好, 我想做个产品" 若 LLM 不可用 → CLARIFY/空 ops (降级, 不写假事实)
        assert isinstance(res["proposal"]["operations"], list)


class TestDeterministicGoesThroughPipeline:
    def test_legacy_interp_ops_are_add(self, root: str, conv: dict) -> None:
        """确定性 interpreter 输出 → ADD operations (经同一 validate/apply 管道)。"""
        svc = ca.ProductUnderstandingService(root)  # 默认 deterministic
        res = svc.process_user_message(conv["id"], "我想做一个飞机大战小游戏。")
        for op in res["proposal"]["operations"]:
            assert op["op"] in ("ADD", "CLARIFY", "QUESTION")
        facts = pu.list_facts(root, conv["id"])
        assert any(f["type"] == "IDEA" for f in facts)


class TestProductHintRegex:
    """S1-6: 委婉业务需求不被预筛误判为寒暄 (llm 预筛漏词修复)。"""

    def _interp_with(self, llm_out: str):
        from factory_console.llm_semantic_interpreter import (
            llm_semantic_interpreter)
        calls = []

        def fake_llm(prompt: str) -> str:
            calls.append(prompt)
            return llm_out
        return llm_semantic_interpreter, fake_llm, calls

    def test_business_wording_reaches_llm(self, root: str, conv: dict) -> None:
        """'给电商系统加会员积分: 下单得积分抵现' → 应触达 LLM (非'嗯我在'降级)。"""
        llm_semantic_interpreter, fake_llm, calls = self._interp_with(
            '{"operations":[],"reply":"已记录","show_understanding":false}')
        from factory_console import product_understanding as pu
        snap = pu.understanding_snapshot(root, conv["id"])
        res = llm_semantic_interpreter(
            root, conv["id"],
            "给电商系统加会员积分：下单得积分，积分可抵现金。", snap,
            llm_fn=fake_llm)
        assert calls, "业务需求未触达 LLM (被预筛误判寒暄)"
        assert res["reply"] == "已记录"

    def test_greeting_still_skips_llm(self, root: str, conv: dict) -> None:
        """寒暄 '你好' → 不触达 LLM (预筛仍挡纯闲聊)。"""
        llm_semantic_interpreter, fake_llm, calls = self._interp_with(
            '{"operations":[],"reply":"x","show_understanding":false}')
        from factory_console import product_understanding as pu
        snap = pu.understanding_snapshot(root, conv["id"])
        llm_semantic_interpreter(root, conv["id"], "你好", snap,
                                 llm_fn=fake_llm)
        assert not calls, "寒暄不应调 LLM"
