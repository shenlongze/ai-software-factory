"""factory-console/testing_semantic_interp.py — 测试用 deterministic 语义解释器。

Cognitive Golden Path 测试辅助 (非生产): 注入 deterministic semantic interpreter,
模拟 LLM 产出 Semantic Proposal — 经与生产完全相同的 validate/apply 管道
(Golden Path §8: 测试可注入 deterministic, 但必须经过同一 Domain Validation /
Mutation)。生产理解走 llm_semantic_interpreter (DeepSeek)。

tests/ 不是 Python 包 (无 __init__.py), pytest 全量收集时 `tests.console.*` 无法
解析 — 共享 interpreter 放 factory_console 包内, 测试统一从此导入。
"""
from __future__ import annotations

from typing import Any


def nlp_semantic_interp(root: str, conversation_id: str, text: str,
                        snapshot: dict) -> dict[str, Any]:
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
