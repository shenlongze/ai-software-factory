"""Cognitive Golden Path — Phase 3: User-visible Understanding Confirmation Loop。

验证 Golden Path §12/§13/§14:
- understanding_statement: 用户可见"我目前理解的是……" (含已确认/待确认/暂缓/否决/缺口)
- 自然语言修正: "不是, 改成……" / "排行榜还是保留" → 同一 Understanding 被修改 (非表单)
- 主动缺口分析: "你觉得还有什么问题?" → 基于当前理解动态判断 (非固定模板)
- Adaptive Clarification: 缺失影响决策才问, 已回答不重复

用 deterministic semantic interpreter 注入 (fake LLM 语义), 经与生产完全相同的
validate/apply 管道 — 测试验证语义能力而非关键词覆盖率。
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
from factory_console.llm_semantic_interpreter import llm_semantic_interpreter  # noqa: E402
from factory_console.testing_semantic_interp import nlp_semantic_interp  # noqa: E402


@pytest.fixture()
def root(tmp_path: Path) -> str:
    return str(tmp_path / "factory")


@pytest.fixture()
def conv(root: str) -> dict:
    return ca.ConversationApplicationService(root).create(title="飞机大战")


@pytest.fixture()
def svc(root: str):
    return ca.ProductUnderstandingService(root, interpreter=nlp_semantic_interp)


class TestUnderstandingStatement:
    def test_empty_conv_statement(self, root: str, conv: dict,
                                  svc) -> None:
        s = svc.understanding_statement(conv["id"])
        assert "还没有形成产品理解" in s

    def test_statement_includes_facts_and_gap(self, root: str, conv: dict,
                                              svc) -> None:
        svc.process_user_message(conv["id"], "我想做一个飞机大战小游戏。")
        svc.process_user_message(conv["id"], "手机端。")
        s = svc.understanding_statement(conv["id"])
        assert "我目前理解的是" in s
        assert "飞机大战" in s
        assert "手机端" in s
        assert "还有一个问题" in s  # 缺口被主动展示

    def test_statement_includes_deferred_and_rejected(self, root: str,
                                                      conv: dict,
                                                      svc) -> None:
        svc.process_user_message(conv["id"], "我想做一个飞机大战小游戏。")
        svc.process_user_message(conv["id"], "排行榜以后再做。")
        s = svc.understanding_statement(conv["id"])
        assert "暂缓" in s
        assert "排行榜" in s


class TestConfirmationLoop:
    def test_user_sees_and_corrects_naturally(self, root: str, conv: dict,
                                              svc) -> None:
        """用户看到理解 → 自然修正 (不是, 改成网页) → 同一理解被修改。"""
        svc.process_user_message(conv["id"], "我想做一个飞机大战小游戏。")
        svc.process_user_message(conv["id"], "手机端。")
        # 用户看理解 (展示请求 → show_understanding)
        r1 = svc.process_user_message(conv["id"], "你目前理解了什么?")
        assert "我目前理解的是" in r1["reply"]
        # 自然修正: 不是手机端, 改成网页
        svc.process_user_message(conv["id"], "还是做成网页吧。")
        facts = pu.list_facts(root, conv["id"], fact_type="REQUIREMENT")
        assert len(facts) == 1
        assert "网页端" in facts[0]["content"]
        old = [f for f in pu.list_facts(root, conv["id"], include_inactive=True)
               if f["status"] == "SUPERSEDED"]
        assert len(old) == 1 and "手机端" in old[0]["content"]

    def test_user_confirm_after_statement(self, root: str, conv: dict,
                                          svc) -> None:
        """用户说"对/确认" → PROPOSED → CONFIRMED。"""
        svc.process_user_message(conv["id"], "我想做一个飞机大战小游戏。")
        svc.process_user_message(conv["id"], "手机端。")
        # "对" 确认所有 PROPOSED
        svc.process_user_message(conv["id"], "对, 就是这样。")
        snap = svc.snapshot(conv["id"])
        assert all(f["status"] == "CONFIRMED"
                   for f in snap["facts"] if f["type"] != "IDEA")

    def test_leaderboard_kept_local_only(self, root: str, conv: dict,
                                         svc) -> None:
        """排行榜还是保留, 但只做本地最高分 → 修改已有理解 (非静默/非重启)。"""
        svc.process_user_message(conv["id"], "我想做一个飞机大战小游戏。")
        svc.process_user_message(conv["id"], "排行榜以后再做。")
        # 恢复并精化
        svc.process_user_message(conv["id"], "排行榜还是保留, 但只记录本地最高分。")
        snap = svc.snapshot(conv["id"])
        assert len(snap["deferred"]) == 0  # 不再延后
        # 排行榜重新生效 (以本地最高分形式)
        assert any("排行榜" in f["content"] or "最高分" in f["content"]
                   for f in snap["facts"])


class TestAdaptiveGaps:
    def test_analysis_gaps_dynamic(self, root: str, conv: dict,
                                   svc) -> None:
        """飞机大战+手机端+摇杆 → 问的是玩法/结束/难度等缺口, 非固定模板。"""
        svc.process_user_message(conv["id"], "我想做一个飞机大战小游戏。")
        svc.process_user_message(conv["id"], "手机端。")
        svc.process_user_message(conv["id"], "操作就用虚拟摇杆吧。")
        gaps = svc.analysis_gaps(conv["id"])
        assert gaps  # 有主动缺口
        assert all("核心" not in g and "想做什么" not in g for g in gaps)
        joined = " ".join(gaps)
        assert ("结束" in joined or "单局" in joined or "难度" in joined
                or "暂停" in joined or "横屏" in joined)

    def test_analysis_no_facts(self, root: str, conv: dict, svc) -> None:
        gaps = svc.analysis_gaps(conv["id"])
        assert "先说说你想做什么" in gaps[0] or "核心想法" in gaps[0]

    def test_gap_shrinks_after_answers(self, root: str, conv: dict,
                                       svc) -> None:
        svc.process_user_message(conv["id"], "我想做一个飞机大战小游戏。")
        svc.process_user_message(conv["id"], "手机端。")
        g0 = set(svc.sufficiency_gaps(conv["id"]))
        # 回答平台缺口 (补充交互)
        svc.process_user_message(conv["id"], "操作就用虚拟摇杆吧。")
        g1 = set(svc.sufficiency_gaps(conv["id"]))
        assert g1 <= g0  # 缺口单调不增 (回答后不再问同一维度)


class TestSimplificationSemantics:
    @pytest.mark.parametrize("phrase", [
        "简单一点",
        "先做个最小版本",
        "第一版别搞那么复杂",
        "功能先收一收",
        "MVP 控制一下",
    ])
    def test_simplify_variants(self, root: str, conv: dict, svc,
                               phrase: str) -> None:
        """Golden Path §14/§24: 语义等价表达 → 范围收窄 (非关键词特例)。"""
        svc.process_user_message(conv["id"], "我想做一个飞机大战小游戏。")
        svc.process_user_message(conv["id"], "排行榜以后可以做。")
        r = svc.process_user_message(conv["id"], phrase)
        snap = svc.snapshot(conv["id"])
        # 范围收窄被记录
        assert any("MVP" in f["content"] or "收窄" in f["content"]
                   for f in snap["facts"]), r
        # 上下文没丢 (还是同一产品)
        assert any(f["type"] == "IDEA" and "飞机大战" in f["content"]
                   for f in snap["facts"])


class TestDeferSemanticsVariants:
    @pytest.mark.parametrize("phrase", [
        "排行榜以后再说",
        "排行榜先不做",
        "这个功能放到后面",
        "第一版不用排行榜",
        "先把排行榜搁着",
    ])
    def test_defer_variants(self, root: str, conv: dict, svc,
                            phrase: str) -> None:
        """Golden Path §24: 延后语义等价表达 → 作用于已有理解 (非静默/非重启)。"""
        svc.process_user_message(conv["id"], "我想做一个飞机大战小游戏。")
        svc.process_user_message(conv["id"], "以后可以加排行榜。")
        svc.process_user_message(conv["id"], phrase)
        snap = svc.snapshot(conv["id"])
        # 排行榜被延后 (deferred), 不是静默忽略
        assert any("排行榜" in f["content"] for f in snap["deferred"]), snap
        # IDEA 仍在 (没有重启成新产品)
        assert any(f["type"] == "IDEA" for f in snap["facts"])


class TestLlmSemanticNlg:
    def test_actual_llm_path_show_understanding(self, root: str,
                                                conv: dict) -> None:
        """生产 LLM interpreter (fake LLM) 支持展示理解请求。"""
        pu.upsert_fact(root, conv["id"], fact_type="IDEA", content="飞机大战小游戏")

        def _llm(prompt: str) -> str | None:
            return ('{"operations":[],"reply":"","question":"",'
                    '"show_understanding":true}')
        svc = ca.ProductUnderstandingService(
            root, interpreter=_llm_wrapper(_llm))
        r = svc.process_user_message(conv["id"], "你理解了什么?")
        assert "我目前理解的是" in r["reply"]


def _llm_wrapper(llm):
    def _i(root: str, conversation_id: str, text: str,
           snapshot: dict) -> dict:
        return llm_semantic_interpreter(root, conversation_id, text, snapshot,
                                        llm_fn=llm)
    return _i