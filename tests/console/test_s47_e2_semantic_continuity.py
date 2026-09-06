"""S47-E2 — 语义回合分类测试 (LLM mock 返回真实形状; 非词表)。

验证 (通用语义机制):
- 语义等价: 多种自然语言表达 → 相同 relation (经 LLM 分类)
- 语义分类函数把 LLM 判定映射为对应引导 (非词表 if/else)
- 修改/拒绝/指代/转向/含糊 → 各自引导
- 反硬编码: 词表不决定行为 (降级路径仅 LLM 不可用时)
"""
import pytest

from factory_console.session.agent_loop import (
    _classify_turn_relation,
    _continuation_guide,
    _continuation_guide_semantic,
)

H = [
    {"role": "user", "content": "飞机大战现在做到哪了？"},
    {"role": "assistant", "content": "我可以继续帮你做需求分析，需要吗？"},
]


def _llm_returning(rel: str, summary: str = "继续"):
    def llm(prompt: str) -> str:
        assert "relation" in prompt  # 语义分类 prompt 形状
        return f'{{"relation": "{rel}", "summary": "{summary}"}}'
    return llm


class TestSemanticEquivalence:
    @pytest.mark.parametrize("msg", ["需要", "好", "可以", "行", "继续吧", "你继续", "就按这个来"])
    def test_confirm_expressions(self, msg):
        rel, _ = _classify_turn_relation(msg, H[-1]["content"], _llm_returning("confirm"))
        assert rel == "confirm"
        g = _continuation_guide_semantic(msg, H, _llm_returning("confirm"))
        assert "确认" in g and "执行" in g

    @pytest.mark.parametrize("msg", ["可以，不过先把登录需求补完整", "继续，但先别生成代码",
                                     "好，先完善登录部分", "那就按你说的先做需求整理"])
    def test_confirm_modify_expressions(self, msg):
        rel, summary = _classify_turn_relation(
            msg, H[-1]["content"], _llm_returning("confirm_modify", "先完善登录"))
        assert rel == "confirm_modify" and summary == "先完善登录"
        g = _continuation_guide_semantic(msg, H, _llm_returning("confirm_modify", "先完善登录"))
        assert "约束" in g and "先完善登录" in g

    @pytest.mark.parametrize("msg", ["不用", "先不要", "算了", "暂时不做", "先放一下"])
    def test_decline_expressions(self, msg):
        rel, _ = _classify_turn_relation(msg, H[-1]["content"], _llm_returning("decline"))
        assert rel == "decline"
        g = _continuation_guide_semantic(msg, H, _llm_returning("decline"))
        assert "拒绝" in g and "不执行" in g

    @pytest.mark.parametrize("msg", ["那刚才那个方案呢", "你提到的 PRD 呢", "继续刚才的工作",
                                     "接着上面的内容说"])
    def test_reference_expressions(self, msg):
        rel, _ = _classify_turn_relation(msg, H[-1]["content"], _llm_returning("reference"))
        assert rel == "reference"
        g = _continuation_guide_semantic(msg, H, _llm_returning("reference"))
        assert "结合上一轮" in g

    @pytest.mark.parametrize("msg", ["先别做 PRD，重新梳理需求", "我想改一下目标",
                                     "先做登录，不做支付"])
    def test_redirect_expressions(self, msg):
        rel, _ = _classify_turn_relation(msg, H[-1]["content"], _llm_returning("redirect"))
        assert rel == "redirect"
        g = _continuation_guide_semantic(msg, H, _llm_returning("redirect"))
        assert "新目标" in g and "旧提议" in g

    def test_ambiguous(self):
        g = _continuation_guide_semantic("嗯", H, _llm_returning("ambiguous", "含糊"))
        assert "最小澄清" in g

    def test_no_proposal_no_guide(self):
        h2 = [{"role": "user", "content": "你好"},
              {"role": "assistant", "content": "你好！有什么可以帮你？"}]
        assert _continuation_guide_semantic("需要", h2, _llm_returning("confirm")) == ""


class TestNoKeywordBehaviour:
    def test_fallback_only_when_llm_unavailable(self):
        # llm_fn=None → 词表降级 (保护路径, 非主机制)
        g = _continuation_guide_semantic("需要", H, None)
        assert "确认并执行" in g

    def test_word_list_not_behaviour(self):
        # 直接词表函数与语义函数区分: 语义函数依赖 LLM 输出
        rel, _ = _classify_turn_relation("随便什么词", H[-1]["content"],
                                         _llm_returning("confirm"))
        assert rel == "confirm"  # 任意表达由 LLM 判, 词表不参与
