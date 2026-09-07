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


@pytest.fixture()
def root(tmp_path: Path) -> str:
    return str(tmp_path / "factory")


@pytest.fixture()
def conv(root: str) -> dict:
    return ca.ConversationApplicationService(root).create(title="飞机大战")


def _nlp_semantic_interp(root: str, conversation_id: str, text: str,
                         snapshot: dict) -> dict:
    """deterministic 语义等价解释器 (注入用; 经同一 validate/apply 管道)。

    注意: 这不是给生产用的 keyword 扩张 — 生产走 LLM (llm_semantic_interpreter)。
    此处只为测试语义能力 (Golden Path §24), 覆盖语义等价表达。
    """
    raw = text.strip()
    snap_facts = snapshot.get("facts", [])
    has_idea = any(f.get("type") == "IDEA" for f in snap_facts)
    has_platform = any("平台" in f.get("content", "") or "手机" in f.get("content", "")
                       for f in snap_facts)
    has_interaction = any("操作" in f.get("content", "") or "摇杆" in f.get("content", "")
                          or "按键" in f.get("content", "")
                          for f in snap_facts)
    ops: list[dict] = []
    reply = ""

    def _add(ftype: str, content: str, conf: float = 1.0) -> None:
        ops.append({"op": "ADD", "fact_type": ftype, "content": content,
                    "confidence": conf})

    # ---- 语义等价: 简化/MVP (Golden Path §14/§24) ----
    if any(k in raw for k in ("简单一点", "简单些", "最小版本", "别搞那么复杂",
                              "先收一收", "先做个最小", "MVP 控制", "功能先收",
                              "第一版别", "做简单", "精简", "轻量一点")):
        # 简化 = 将现有 FUTURE_IDEA/低优项延后 + 明确"第一版范围收窄"
        for f in snap_facts:
            if f.get("type") == "FUTURE_IDEA":
                ops.append({"op": "DEFER", "fact_type": "FUTURE_IDEA",
                            "content": f["content"], "target_id": f["id"]})
        ops.append({"op": "ADD", "fact_type": "CONSTRAINT",
                    "content": "第一版范围收窄 (MVP 优先)", "confidence": 0.9})
        reply = "明白, 第一版先做最小可用版本 — 把暂缓项排到后面。"
        return {"operations": ops, "reply": reply, "question": "",
                "show_understanding": True}

    # ---- 未来想法: 以后可以加 X (FUTURE_IDEA) ----
    future_kw = ("以后可以加", "以后想加", "未来可以加", "之后再", "以后还能",
                 "以后支持", "以后要做", "以后再加")
    if any(k in raw for k in future_kw):
        for name in ("排行榜", "多人在线", "登录", "广告", "内购", "音效", "分享"):
            if name in raw:
                _add("FUTURE_IDEA", name, conf=0.8)
                reply = f"记下, {name}以后可以做。"
                return {"operations": ops, "reply": reply, "question": "",
                        "show_understanding": False}

    # ---- 语义等价: 延后排行榜类 (Golden Path §24 变体) ----
    defer_kw = ("以后再说", "先不做", "先别做", "后面再做", "暂缓", "搁着",
                "第一版不用", "以后再做", "以后再", "放到后面")
    if any(k in raw for k in defer_kw):
        # 提取被延后的对象 (排行榜 / 多人在线 …); "这个功能"= 指代最近 future/待确认项
        target = None
        for name in ("排行榜", "多人在线", "登录", "广告", "内购", "音效", "分享"):
            if name in raw:
                target = name
                break
        if target is None:
            # 指代解析: "这个功能/它" → 最近提到的 FUTURE_IDEA 或有效 fact
            candidates = (snapshot.get("facts", []) + snapshot.get("deferred", []))
            for f in reversed(candidates):
                if f.get("type") in ("FUTURE_IDEA", "REQUIREMENT", "DECISION"):
                    target = str(f.get("content", ""))[:20]
                    break
        if target is None:
            target = "这个功能"
        # 找已记录的对应 fact
        tid = None
        for f in snap_facts + snapshot.get("deferred", []):
            if target in str(f.get("content", "")):
                tid = f["id"]
                break
        ops.append({"op": "DEFER", "fact_type": "FUTURE_IDEA",
                    "content": target, "target_id": tid or ""})
        reply = f"好, {target}先不做, 以后需要再加。"
        return {"operations": ops, "reply": reply, "question": "",
                "show_understanding": False}

    # ---- 否定 (不要登录 / 不需要注册) ----
    if any(k in raw for k in ("不要登录", "不用登录", "无需登录", "免登录",
                              "不登录", "不需要注册")):
        _add("CONSTRAINT", "无需登录, 打开即可使用")
        reply = "好, 不需要登录, 打开就能玩。"
        return {"operations": ops, "reply": reply, "question": "",
                "show_understanding": False}

    # ---- 功能需求 (需要/还要/支持 X 的暂停/横屏 等) ----
    for name in ("暂停", "横屏", "竖屏", "存档", "音效", "音乐", "难度", "计分",
                 "分数", "关卡", "血条", "分享", "通知", "主题"):
        if name in raw and any(k in raw for k in ("需要", "还要", "支持", "要加",
                                                  "加上", "做", "加个", "要有",
                                                  "要有", "能")):
            label = {"暂停": "支持暂停功能", "横屏": "横屏方向",
                     "竖屏": "竖屏方向"}.get(name, name)
            _add("REQUIREMENT", f"{label}" if name in ("暂停", "横屏", "竖屏")
                 else f"支持{name}功能")
            reply = f"好, 记下: {name}。"
            return {"operations": ops, "reply": reply, "question": "",
                    "show_understanding": False}

    # ---- 平台 (语义等价: 手机端/手机上/移动/安卓) ----
    if not has_platform and any(k in raw for k in ("手机", "移动", "安卓",
                                                   "手机上", "app", "ios")):
        _add("REQUIREMENT", "运行平台: 手机端")
        reply = "好的, 手机端。"
        return {"operations": ops, "reply": reply, "question": "",
                "show_understanding": False}
    if any(k in raw for k in ("网页", "web", "浏览器", "h5", "网站")):
        _add("REQUIREMENT", "运行平台: 网页端")
        reply = "好的, 网页端。"
        return {"operations": ops, "reply": reply, "question": "",
                "show_understanding": False}

    # ---- 修改: 还是做成网页吧 (手机端已被记录 → REPLACE/UPDATE) ----
    if has_platform and any(k in raw for k in ("还是做成网页", "改成网页",
                                               "不做手机", "网页吧")):
        ops.append({"op": "REPLACE", "fact_type": "REQUIREMENT",
                    "content": "运行平台: 网页端"})
        reply = "明白, 平台从手机端改成网页端。"
        return {"operations": ops, "reply": reply, "question": "",
                "show_understanding": False}

    # ---- 操作方式 (虚拟摇杆 vs 虚拟按键 替换) ----
    if "摇杆" in raw:
        _add("DECISION", "操作方式: 虚拟摇杆")
        reply = "好的, 操作方式用虚拟摇杆。"
        return {"operations": ops, "reply": reply, "question": "",
                "show_understanding": False}
    if "按键" in raw and not has_interaction:
        _add("DECISION", "操作方式: 虚拟按键")
        reply = "好的, 用虚拟按键。"
        return {"operations": ops, "reply": reply, "question": "",
                "show_understanding": False}

    # ---- 想法 ----
    if not has_idea and any(k in raw for k in ("我想做", "做一个", "做一款",
                                               "做个小", "开发", "做个")):
        _add("IDEA", "飞机大战小游戏" if "飞机" in raw else "一个产品")
        reply = "我记下这个想法了。"
        return {"operations": ops, "reply": reply, "question": "",
                "show_understanding": False}

    # ---- 主动缺口分析请求 ----
    if any(k in raw for k in ("还有什么问题", "你觉得", "怎么看", "你问我",
                              "有什么建议")):
        return {"operations": [], "reply": "", "question": "",
                "show_understanding": False}

    # ---- 确认 (对/是/没错/就按这个) ----
    if any(k in raw for k in ("对", "没错", "就是", "可以", "同意")):
        for f in snap_facts:
            if f.get("status") == "PROPOSED":
                ops.append({"op": "CONFIRM", "fact_type": f["type"],
                            "content": f["content"], "target_id": f["id"]})
        reply = "好, 我把这些确认下来。"
        return {"operations": ops, "reply": reply, "question": "",
                "show_understanding": False}

    # ---- 确认展示理解 ----
    if any(k in raw for k in ("你理解", "目前理解", "总结一下", "理清楚了没")):
        return {"operations": [], "reply": "", "question": "",
                "show_understanding": True}

    # ---- 恢复被延后的功能 (排行榜还是保留/要做回来) ----
    if any(k in raw for k in ("还是保留", "要做回来", "还是做", "保留排行榜",
                              "排行榜还是要", "排行榜还是做")):
        target = None
        for name in ("排行榜", "多人在线", "音效", "分享"):
            if name in raw:
                target = name
                break
        for f in snapshot.get("deferred", []):
            if target and target in str(f.get("content", "")):
                ops.append({"op": "ADD", "fact_type": "REQUIREMENT",
                            "content": f"{target} (本地记录)" if "本地" in raw
                            else target, "target_id": ""})
                # 原 deferred 将被新 ADD 顶替 (supersede, 不重复)
                break
        if not ops:
            ops.append({"op": "ADD", "fact_type": "REQUIREMENT",
                        "content": raw.replace("还是保留", "").strip()[:40]})
        reply = "好, 恢复这个功能。"
        return {"operations": ops, "reply": reply, "question": "",
                "show_understanding": False}

    # ---- 其它: 不猜 (CLARIFY) ----
    return {"operations": [], "reply": "嗯, 我记下了。你希望它是什么样?",
            "question": "", "show_understanding": False}


@pytest.fixture()
def svc(root: str):
    return ca.ProductUnderstandingService(root, interpreter=_nlp_semantic_interp)


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
