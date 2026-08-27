"""factory-console/session/intent_core.py — 会话意图理解层 (IntentCore v1, v1.1.208).

Founder 2026-08-27: 不能一味用关键词, 一定要真正 get 到用户的意图; 不行就 loop,
3 次 loop 后还不清醒就追问。

设计 (docs/sprint10/会话系统-整体设计-v2.md §2):
- understand_intent: LLM 结构化意图理解 — intent × target × need × emotion × summary × followup
- 确定性兜底: LLM 不可用/输出坏 → 规则快路径 (不赌 LLM, 不编造)
- route_for: 意图 → 专业能力线 (Router 表) — "专业的人干专业的事"
- 铁律: 质疑/不满/纠错必须识别 (challenge) → 自查, 不是继续瞎答
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

#: 意图枚举 (设计文档 §2.1)
INTENTS = ("question", "challenge", "chat", "delegate", "develop", "operate", "clarify")
#: 对象类型
TARGET_TYPES = ("project", "task", "doc", "system", "external", "general")
#: 用户需要
NEEDS = ("info", "action", "verification", "correction", "creation", "execution")
#: 情绪
EMOTIONS = ("neutral", "satisfied", "dissatisfied", "urgent", "skeptical")

_INTENT_PROMPT = """你是 AI Factory 的意图理解器。用户消息千变万化（提问/质疑/聊天/派活/开发/操作/不满），
你的唯一任务：真正听懂用户在做什么，输出结构化意图 JSON（不要多余文字）。

只输出 JSON:
{{
  "intent": "question|challenge|chat|delegate|develop|operate|clarify",
  "target": {{"type": "project|task|doc|system|external|general", "id": null}},
  "need": "info|action|verification|correction|creation|execution",
  "emotion": "neutral|satisfied|dissatisfied|urgent|skeptical",
  "summary": "一句话: 用户到底要什么",
  "followup": null
}}

判定规则:
- question: 要信息/查询 (进度/状态/这是什么/扫描/分析利弊)
- challenge: 质疑/不满/纠错 (这回答不负责/上次不对吧/你瞎猜/太敷衍/数据不对) → 用户要的是验证+修正
- chat: 打招呼/闲聊/讨论 (你好/聊聊/你觉得呢)
- delegate/develop: 派活/开发 (把XX做完/开发XX/写个XX/帮我做XX/继续做XX)
- operate: 操作现有东西 (开始/标记/删除/改名/推送/创建任务/执行计划)
- external: 要外部专业能力 (审查架构/安全评估/竞品分析)
- clarify: 信息不足, 无法判断用户要什么 → 需要追问

情绪判定: dissatisfied/skeptical 信号 (不负责/糊弄/敷衍/太差/不对/假的/骗) 必须标出。
{history_block}用户消息: {message}
"""

#: 意图 → 专业能力线 (Router 表, 设计文档 §2.2)
_ROUTE_GUIDE = {
    "question": "查询意图: 必须调用数据工具 (project_status/project_tasks/project_scan/code_scan/search_code/project_docs/git_status/monitor) 拿真实数据, 带证据回答; 不要凭空答。",
    "challenge": "质疑/纠错意图: 用户认为上次回答有问题。先【重新查询真实数据验证】, 再诚实承认错误或给出修正; 绝不对着干/嘴硬/糊弄。若上次回答在上下文中, 逐条核对。",
    "chat": "聊天意图: 自然对话即可。除非用户明确要实时数据, 不需要调用工具。",
    "delegate": "分派/开发意图: 先快速了解现状 (最多 2-3 个了解工具), 然后必须调 plan_development 出计划 (目标/任务/顺序/验收) 请求用户审批; 不要无限探索。",
    "develop": "开发意图: 先快速了解现状 (最多 2-3 个了解工具), 然后必须调 plan_development 出计划 (目标/任务/顺序/验收) 请求用户审批; 不要无限探索。",
    "operate": "操作意图: 调用动作工具执行 (task_action/create_task/execute_plan/task_continue); 敏感动作先确认再执行。",
    "external": "外部专业意图: 先了解任务背景, 再调 external_route 选外部 AI agent, 说明选择理由。",
    "clarify": "意图不明: 不要调用任何工具, 直接向用户提出澄清问题 (追问), 等用户补充。",
}


def understand_intent(
    message: str,
    *,
    llm_fn: Callable[[str], str] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """真实意图理解: LLM 结构化 JSON 优先, 失败/不可用 → 规则兜底。

    返回 {intent, target:{type,id}, need, emotion, summary, followup, source}。
    source: "llm" | "fallback" — 诚实标注理解来源。
    """
    msg = str(message or "").strip()
    if not msg:
        return _fallback_intent(msg, history)
    history_block = _history_block(history)
    if llm_fn is not None:
        try:
            raw = str(llm_fn(_INTENT_PROMPT.format(message=msg, history_block=history_block)) or "").strip()
            parsed = _parse_json(raw)
            if parsed:
                return _normalize(parsed, msg, history)
        except Exception:  # noqa: BLE001 — LLM 异常 → 兜底
            pass
    return _fallback_intent(msg, history)


def route_for(intent: str) -> str:
    """意图 → 专业能力线约束 (喂给 Agent 循环的路由提示)。"""
    return _ROUTE_GUIDE.get(str(intent or "").lower(), _ROUTE_GUIDE["clarify"])


def format_intent(intent: dict[str, Any]) -> str:
    """意图 → 注入消息文本 (让模型带意图执行, 不被词面劫持)。"""
    t = intent.get("target") or {}
    return (
        f"【意图理解 (来源: {intent.get('source', 'llm')})】\n"
        f"- 意图: {intent.get('intent')}\n"
        f"- 对象: {t.get('type') or 'general'}{(' (' + str(t.get('id')) + ')') if t.get('id') else ''}\n"
        f"- 需要: {intent.get('need')}\n"
        f"- 情绪: {intent.get('emotion')}\n"
        f"- 用户要什么: {intent.get('summary') or ''}\n"
        f"请严格按此意图执行对应专业能力; 不要被用户表面的词误导。"
    )


# ---------------------------------------------------------------- 内部

def _history_block(history: list[dict[str, Any]] | None) -> str:
    """最近历史 (供意图理解 + 质疑自查): 最近 4 条 user/assistant。"""
    if not history:
        return ""
    recent = [
        f"{h.get('role')}: {str(h.get('content') or '')[:300]}"
        for h in history[-4:]
        if isinstance(h, dict) and h.get("role") in ("user", "assistant")
    ]
    return ("最近对话:\n" + "\n".join(recent) + "\n\n") if recent else ""


def _parse_json(raw: str) -> dict[str, Any] | None:
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        return d if isinstance(d, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _normalize(d: dict[str, Any], message: str, history: list[dict[str, Any]] | None) -> dict[str, Any]:
    """字段合法性校验 + 归一 (坏字段 → 兜底值, 不崩)。"""
    intent = str(d.get("intent") or "").lower()
    if intent not in INTENTS:
        intent = _fallback_intent(message, history)["intent"]
    t = d.get("target")
    ttype = str((t.get("type") if isinstance(t, dict) else None) or "general").lower()
    if ttype not in TARGET_TYPES:
        ttype = "general"
    need = str(d.get("need") or "").lower()
    if need not in NEEDS:
        need = "info"
    emotion = str(d.get("emotion") or "").lower()
    if emotion not in EMOTIONS:
        emotion = "neutral"
    summary = str(d.get("summary") or "").strip()[:200] or message[:80]
    return {
        "intent": intent,
        "target": {"type": ttype, "id": (t.get("id") if isinstance(t, dict) else None)},
        "need": need,
        "emotion": emotion,
        "summary": summary,
        "followup": d.get("followup") if isinstance(d.get("followup"), (str, type(None))) else None,
        "source": "llm",
    }


def _fallback_intent(message: str, history: list[dict[str, Any]] | None) -> dict[str, Any]:
    """规则快路径 (LLM 不可用/输出坏): 只兜底最常见模式, 不堆关键词。"""
    msg = (message or "").strip()
    low = msg.lower()
    summary = msg[:80] or "（空消息）"
    base = {"target": {"type": "general", "id": None}, "need": "info",
            "emotion": "neutral", "summary": summary, "followup": None, "source": "fallback"}
    # 质疑/不满 (含负面情绪信号 → challenge, 优先)
    if any(k in msg for k in ("不负责", "糊弄", "敷衍", "太差", "不对吧", "错了", "假的",
                               "骗", "瞎猜", "不满意", "垃圾", "无语", "蒙我", "合理吗")):
        return {**base, "intent": "challenge", "need": "verification", "emotion": "dissatisfied"}
    # 打招呼
    if re.match(r"^(你好|您好|hi|hello|hey|在吗|嗨|早上好|下午好|晚上好)[!！。.,，\s]*$", low):
        return {**base, "intent": "chat"}
    # 操作现有东西 (动作) — "把 X 标记完成/删除/改名…" 均 operate
    if re.search(r"(标记|删除|改名|归档|收藏|推送|批准|创建任务|执行计划)", msg) \
            or re.search(r"^(把|将|给|帮我)?\s*(开始|完成)\s", msg):
        return {**base, "intent": "operate", "need": "action"}
    # 开发/派活
    if re.search(r"(把.{0,20}(做完|做好|搞定|实现)|开发|写个|做个|做一个|帮我做|实现|搭建|设计一个|重构|继续做|接着做)", msg):
        return {**base, "intent": "develop", "need": "creation"}
    # 查询
    if "?" in msg or "？" in msg or any(k in msg for k in ("多少", "什么", "怎么", "哪些", "进度",
                                                             "状态", "扫描", "分析", "清单", "列表", "怎么样")):
        return {**base, "intent": "question"}
    # 默认: 信息不足 → 追问 (Founder: 意图不明不瞎猜)
    return {**base, "intent": "clarify", "followup": "请补充你想做什么/要查什么"}
