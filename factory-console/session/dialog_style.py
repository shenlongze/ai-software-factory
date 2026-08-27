"""factory-console/session/dialog_style.py — 对话风格引擎 (S-6, v1.1.217).

Founder 2026-08-27: "能说人话么" — 会话要像人说话:
- 风格分级: 闲聊简短 / 查询清晰带数字 / 分析深入 / 质疑先共情 / 动作确认
- 模板解放: 取消【结论】【数据】【数据来源】硬标签 → 自然段落 (信息不丢)
- 情绪回应: 不满/质疑 → 语气前置 (先承认再行动)
- 详略分级: 默认 ≤3 句, 复杂才展开
"""

from __future__ import annotations


#: 怀疑/不满情绪信号 (用于语气前置)
_SKEPTICAL_SIGNALS = ("不负责", "糊弄", "敷衍", "太差", "不对吧", "错了", "假的", "骗",
                      "瞎猜", "不满意", "垃圾", "无语", "蒙我", "合理吗",
                      "真正", "真的", "确实", "确定", "靠谱", "可信", "属实")
#: 闲聊信号 (简短)
_CHAT_SIGNALS = ("你好", "您好", "hi", "hello", "hey", "在吗", "嗨", "谢谢", "感谢",
                 "辛苦了", "再见", "拜拜", "好的", "可以", "嗯", "哈哈", "哈哈哈")

_STYLES: dict[str, dict[str, str]] = {
    "chat": {
        "name": "闲聊",
        "instruction": (
            "像人聊天: 简短友好, 3 句以内; 不需要调工具就别调; 顺着对方话题回应。"
        ),
    },
    "query": {
        "name": "查询",
        "instruction": (
            "用自然段落回答: 先把关键结论说清楚, 关键数字/来源保留, 但不要用"
            "【结论】【数据】【数据来源】这种标签; 像人报告, 不是报表。"
        ),
    },
    "analyze": {
        "name": "分析",
        "instruction": (
            "先给一句话判断(结论), 再用自然段落展开依据(引用真实数据/工具证据); "
            "可以分点但不要套模板标签; 最后给 1-2 条可执行建议。"
        ),
    },
    "skeptical": {
        "name": "质疑回应",
        "instruction": (
            "先承认/共情(如'你说得对, 我重新查证一下'), 再重新查询真实数据核对; "
            "错了就明确认错并给修正, 不嘴硬不辩解。"
        ),
    },
    "action": {
        "name": "动作",
        "instruction": (
            "先说清你要做什么(简短), 敏感动作(建任务/改任务/委派/推送)先请求用户确认; "
            "执行后报告结果, 用自然语言。"
        ),
    },
}


def style_for(message: str, intent: str | None = None, emotion: str | None = None) -> dict[str, str]:
    """按意图软参考 + 消息/情绪特征选风格 (确定性, 不调 LLM)。"""
    msg = str(message or "")
    low = msg.lower()
    # 质疑/不满优先 (情绪/信号)
    if emotion in ("dissatisfied", "skeptical") or any(k in msg for k in _SKEPTICAL_SIGNALS):
        return _STYLES["skeptical"]
    if intent in ("challenge",):
        return _STYLES["skeptical"]
    if intent in ("chat",) or any(k in low for k in ("你好", "谢谢", "再见", "在吗", "hi", "hello", "哈哈")):
        return _STYLES["chat"]
    if intent in ("develop", "delegate", "operate") or any(k in msg for k in ("把", "帮", "做", "改", "推", "建")):
        return _STYLES["action"]
    if intent in ("analyze", "deep_analyze") or any(k in msg for k in ("分析", "评估", "利弊", "建议", "怎么看")):
        return _STYLES["analyze"]
    return _STYLES["query"]


def style_instruction(message: str, intent: str | None = None, emotion: str | None = None) -> str:
    """生成注入 Agent 循环的风格指令文本。"""
    st = style_for(message, intent, emotion)
    return f"【回答风格 · {st['name']}】{st['instruction']}"
