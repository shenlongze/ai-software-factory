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
- challenge: 质疑/不满/纠错 (这回答不负责/上次不对吧/你瞎猜/太敷衍/数据不对)
  + 怀疑/确认式质疑 ("是真的吗/确实吗/能确定吗/靠谱吗/真正影响项目吗/可信吗/保证吗")
  → 用户要的是验证+证据, 不是泛泛肯定; need=verification, emotion=skeptical
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
    "question": "若用户要查询/扫描: 应调用对应数据工具 (project_status/project_tasks/project_scan/code_scan/project_structure/search_code/project_docs/git_status/monitor) 拿真实数据再答, 不凭空答。区分: '扫描代码/代码结构' → code_scan; '扫描项目/整体情况' → project_scan; '项目结构/目录树/有哪些模块' → project_structure。",
    "challenge": "若用户质疑/纠错: 先【重新查询真实数据验证】, 再诚实承认错误或给出修正; 绝不对着干/嘴硬/糊弄。",
    "chat": "若只是聊天/打招呼: 自然对话即可, 除非用户要实时数据否则不必调工具。",
    "delegate": "若用户派活/开发: 先快速了解现状 (最多 2-3 个了解工具), 然后调 plan_development 出计划 (目标/任务/顺序/验收) 请求用户审批; 不要无限探索。",
    "develop": "若用户要开发/实现: 先快速了解现状 (最多 2-3 个了解工具), 然后调 plan_development 出计划 (目标/任务/顺序/验收) 请求用户审批; 不要无限探索。",
    "operate": "若用户要操作: 调用动作工具执行 (task_action/create_task/execute_plan/task_continue); 敏感动作先确认再执行。",
    "external": "若用户要外部专业能力: 先了解任务背景, 再调 external_route / delegate_external 选外部 AI agent。",
    "clarify": "若意图不明: 直接向用户提出澄清问题 (追问), 不要瞎猜。",
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
    """意图 → 软参考提示 (v1.1.216 agentic: 仅供参考, 不硬路由, 以模型语义判断为准)。"""
    t = intent.get("target") or {}
    return (
        f"【用户意图参考 (来源: {intent.get('source', 'llm')}, 仅供参考)】\n"
        f"- 疑似意图: {intent.get('intent')} · 对象: {t.get('type') or 'general'}"
        f"{(' (' + str(t.get('id')) + ')') if t.get('id') else ''} · 需要: {intent.get('need')} · 情绪: {intent.get('emotion')}\n"
        f"- 用户大概要: {intent.get('summary') or ''}\n"
        f"请以对话语义为准自主判断如何回答/行动; 若与实际意图不符, 忽略此参考。"
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
    # 怀疑/确认式质疑 ("是真的吗/确实吗/能确定吗/靠谱吗/真正影响项目吗" → 要验证+证据)
    _skeptical = ("真正", "真的", "确实", "确定", "保证", "靠谱", "可信", "准确", "属实", "当真")
    if any(k in msg for k in _skeptical) and re.search(r"(吗|么|？|\?|不|没有|未必|确定)", msg):
        return {**base, "intent": "challenge", "need": "verification", "emotion": "skeptical"}
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
