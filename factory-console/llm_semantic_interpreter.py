"""factory-console/llm_semantic_interpreter.py — LLM Semantic Understanding (Golden Path)。

RED-1 修复: regex keyword interpreter → LLM Semantic Understanding。

管道 (Golden Path §7):
  User Message
    → Context Assembly (persistent Understanding + recent messages, 非猜)
    → LLM (console_sessions.llm_raw / DeepSeek)
    → Structured Semantic Proposal (JSON)
    → Domain Validation (semantic_proposal.validate_proposal)
    → apply (唯一 Truth 写路径)

边界:
- LLM 只理解语言、产出 proposal; 不得直接写 Product Understanding。
- LLM 不可用/解析失败/validation 失败 → 显式降级 (确定性兜底或诚实引导),
  绝不部分写 Truth。
- 禁止把 regex 扩张成更大 keyword 系统: 本模块无产品事实规则; 兜底只做
  "无法可靠理解时诚实澄清", 不猜事实。
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from factory_console.semantic_proposal import (
    ProposalValidationError, build_proposal, validate_proposal,
)

#: LLM 函数签名: fn(prompt: str, mode: str) -> str — 与 console_sessions.llm_raw 同构
LLMFn = Callable[[str], str | None]

SYSTEM_PROMPT = """你是 AI Factory OS 的 Product Understanding 语义解释器。
你的职责: 把用户的自然语言消息, 对照"当前产品理解", 转成一组结构化语义操作。

你绝不能直接写入产品真相。你只产出提案 (Semantic Proposal)。

支持操作:
- ADD: 新增事实 (新信息)
- UPDATE: 修改已有事实 (用户改变主意/补充细节, 内容写新值)
- NEGATE: 否定已有事实 (用户说不要 X, 而 X 已被记录)
- DEFER: 延后 (用户说以后再做, 非拒绝)
- REPLACE: 替换同维度决定 (用户换成另一种方案)
- CONFIRM: 确认 AI 当前理解/某条事实 (用户说"对/没错/可以")
- REJECT: 明确拒绝 (用户否决某提案/事实)
- CLARIFY: 信息不足需要反问 (附 content = 要问的问题, 不要猜)
- QUESTION: 用户在提问 (fact_type=QUESTION, content=问题)

fact_type 只能是: IDEA, REQUIREMENT, CONSTRAINT, DECISION, QUESTION, FUTURE_IDEA。

规则:
1. 用户新增产品事实 → ADD。
2. 用户改主意 (如 "还是做成网页吧" 而当前理解是手机端) → UPDATE/REPLACE。
3. 用户否定已记录项 → NEGATE/REJECT。
4. "以后/先不做/暂缓" → DEFER (不能静默忽略, 也不能当拒绝)。
5. 用户确认 (对/是的/就这么定) → CONFIRM (若可确定对象)。
6. 用户提问/表达不确定 → QUESTION 或 CLARIFY。
7. 信息不足无法判断 → CLARIFY (宁可不改, 不要猜)。
8. 问候语/寒暄/无产品语义 → operations: [] (空), reply 正常回应。
9. reply: 给用户的简短自然语言回复 (中文)。
10. question: 如果你需要主动追问一个最关键缺口, 填这里 (只填一个)。

只输出 JSON, 不要输出任何其它文本或 markdown 代码块围栏。JSON 结构:
{"operations":[{"op":"ADD","fact_type":"REQUIREMENT","content":"运行平台: 手机端","confidence":0.9}],"reply":"...","question":"","show_understanding":false}
"""

#: 产品相关词 (LLM 判定"这消息有没有产品语义"用 — 非事实抽取规则)
#: S1-6: 补业务域词 (电商/积分/会员/下单/兑换/支付/订单/购物) — 防委婉产品需求
#: 被预筛误判为寒暄 (CT F2 P2: llm 预筛正则漏委婉表达)。
_PRODUCT_HINT_RE = re.compile(
    r"做|开发|产品|app|应用|端|平台|登录|排行|摇杆|按键|操作|游戏|界面|用户|"
    r"功能|需求|版本|设计|横屏|竖屏|声音|广告|内购|账号|同步|离线|"
    r"加|积分|会员|下单|兑换|支付|订单|购物|电商|商城|优惠|折扣|金额|"
    r"实现|支持|需要|可以|想要|希望|"
    r"暂停|难度|分数|关卡|分享|通知|主题|支付|上线|发布",
    re.IGNORECASE,
)


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_semantic_json(raw: str) -> dict[str, Any]:
    """LLM 原始输出 → Semantic Proposal dict (宽容解析; 失败抛 ProposalValidationError)。"""
    text = _strip_json_fence(raw)
    try:
        data = json.loads(text)
    except ValueError as exc:
        # 尝试提取首个 {...} (LLM 偶发夹带解释文本)
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m is None:
            raise ProposalValidationError(
                f"LLM 输出非 JSON: {raw[:200]!r}") from exc
        data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ProposalValidationError(f"LLM 输出非对象: {raw[:200]!r}")
    return validate_proposal(data)


def build_llm_prompt(snapshot: dict[str, Any], user_message: str) -> str:
    """Context Assembly → LLM prompt (只读, 不猜)。"""
    facts = snapshot.get("facts", [])
    deferred = snapshot.get("deferred", [])
    rejected = snapshot.get("rejected", [])
    lines = [
        SYSTEM_PROMPT,
        "",
        "# 当前产品理解 (Product Understanding)",
        f"version={snapshot.get('version')}",
    ]
    if not facts and not deferred and not rejected:
        lines.append("(暂无事实 — 新会话)")
    for f in facts:
        lines.append(
            f"- {f['type']} [{f['status']}] {f['content']}"
            f" (id={f['id']})")
    for f in deferred:
        lines.append(f"- (延后) {f['type']} {f['content']} (id={f['id']})")
    for f in rejected:
        lines.append(f"- (已否决) {f['type']} {f['content']} (id={f['id']})")
    lines += [
        "",
        "# 用户消息",
        user_message,
        "",
        "# 请输出 JSON (如上规则)",
    ]
    return "\n".join(lines)


def llm_semantic_interpreter(root: str, conversation_id: str, text: str,
                             snapshot: dict[str, Any],
                             llm_fn: LLMFn | None = None) -> dict[str, Any]:
    """生产 Semantic Interpreter: LLM → proposal (validated)。

    返回与 semantic_proposal.build_proposal 同构的 dict; LLM 不可用/解析失败 →
    确定性降级: 返回 CLARIFY (诚实引导) — 不猜产品事实, 不部分写 Truth。
    """
    # 1) 明显无产品语义 (寒暄/确认展示请求) — 不调 LLM (省成本 + 防幻觉)
    stripped = text.strip()
    if not _PRODUCT_HINT_RE.search(stripped):
        # "我目前的理解是?" / "你理解了什么" → show_understanding (无 fact 变更)
        if re.search(r"理解|你(现在|目前)?(觉得|认为|怎么看)|总结", stripped):
            return build_proposal(
                operations=[], reply="", summary="", show_understanding=True)
        return build_proposal(operations=[], reply="嗯, 我在。想做什么产品? 说说你的想法。")

    # 2) LLM 调用 (注入或默认)
    if llm_fn is None:
        try:
            from factory_console.console_sessions import llm_raw as _raw
            llm_fn = _raw  # type: ignore[assignment]
        except Exception:  # noqa: BLE001 — 无 LLM 环境 → 降级
            llm_fn = None
    if llm_fn is None:
        return _degrade_clarify(text)

    prompt = build_llm_prompt(snapshot, stripped)
    try:
        raw = llm_fn(prompt)
    except Exception:  # noqa: BLE001 — LLM 挂 → 降级 (不猜)
        return _degrade_clarify(text)
    if not raw or not str(raw).strip():
        return _degrade_clarify(text)

    # 3) 解析 + Domain Validation (失败 → 降级, 不部分写)
    try:
        return parse_semantic_json(str(raw))
    except ProposalValidationError:
        return _degrade_clarify(text)


def _degrade_clarify(text: str) -> dict[str, Any]:
    """确定性降级: 不猜产品事实 — 诚实引导 (而不是静默忽略或错误记录)。"""
    return build_proposal(
        operations=[],
        reply=("我暂时无法可靠理解这句话与产品的关联。"
               "可以换一种说法, 或告诉我它属于哪个方面"
               " (核心想法 / 平台 / 功能 / 约束 / 交互方式 / 以后再说)?"),
        question="这句话想表达的是……?",
    )


__all__ = [
    "LLMFn", "SYSTEM_PROMPT",
    "parse_semantic_json", "build_llm_prompt",
    "llm_semantic_interpreter",
]
