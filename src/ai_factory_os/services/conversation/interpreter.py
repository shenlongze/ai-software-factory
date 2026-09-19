"""conversation · LLM 语义解释器（外沿 → 提案）—— 搬迁自 factory_console.llm_semantic_interpreter。

管道（Golden Path §7）:
    User Message
      → Context Assembly（持久化 Understanding + 近期消息, **非猜** + 可选相关历史）
      → LLM
      → Structured Semantic Proposal (JSON)
      → Domain Validation (`proposal.validate_proposal`)
      → apply（唯一 Truth 写路径）

边界（不变）:
  · LLM 只理解语言、产出 proposal —— **不得直接写 Product Understanding**。
  · LLM 不可用 / 解析失败 / validation 失败 → **显式降级**（诚实澄清），绝不部分写 Truth。
  · 禁止把 regex 扩张成更大 keyword 系统: 本模块**无产品事实规则**; 兜底只做
    "无法可靠理解时诚实澄清", 不猜事实。（`_PRODUCT_HINT_RE` 只用于"这条消息有没有
    产品语义"的分流判断, 不是事实抽取规则。）

跨域处理（按 SSoT R3/R5 —— 本域不直连别的域）:
  · 调 LLM          → 经 `bind_lookups(llm_fn=...)` 注入; 未接线 → 诚实降级（同"无 LLM 环境"）
  · 历史检索        → 经 `bind_lookups(history_index=...)` 注入; 未接线 → 不带历史段
                      （与原来"检索不可用 → 无历史段落"同一降级路径 ✓）
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

from .proposal import (
    ProposalValidationError, build_proposal, validate_proposal,
)

#: LLM 函数签名: fn(prompt: str) -> str | None
LLMFn = Callable[[str], "str | None"]

_hooks: dict[str, Any] = {}


def bind_lookups(*, llm_fn: LLMFn | None = None,
                 history_index: Any = None) -> None:
    """注入跨域能力（bootstrap 装配时调用；None 项保持不变）。

    llm_fn        — 调 LLM 的函数（缺失 → 降级为诚实澄清）
    history_index — 历史检索工厂: callable(root) -> idx（缺失 → 不带历史段）
    """
    if llm_fn is not None:
        _hooks["llm_fn"] = llm_fn
    if history_index is not None:
        _hooks["history_index"] = history_index


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
#: 确认类短消息（"对/是/好的/就是这样"）—— 多轮澄清时用户最常说的
_CONFIRM_RE = re.compile(
    r"^(对|是|是的|对的|嗯|嗯嗯|好的|好|可以|行|没错|就是这样|就这样|ok|OK|OK的)[。.!！~、 ]*$",
    re.IGNORECASE,
)
#: 寒暄
_GREETING_RE = re.compile(r"^(你好|您好|hi|hello|嗨|在吗|早上好|下午好|晚上好)[。.!！~ ]*$", re.IGNORECASE)
#: 与产品无关的闲聊
_CHITCHAT_RE = re.compile(r"天气|吃饭|累了|休息|周末|心情|无聊|睡觉")


def _has_understanding(snapshot: dict[str, Any]) -> bool:
    """当前会话是否已有产品理解（有 fact）—— 决定兜底回应是"推进"还是"引导"。"""
    return bool(snapshot.get("facts"))


#: 纯展示请求（"你理解了什么"/"总结一下"）—— 不含新信息, 无需调 LLM
_DISPLAY_RE = re.compile(r"^(请)?(你)?(现在|目前)?(理解|觉得|认为|怎么看|总结|复述)[^。！？]{0,12}[?？]?$")
#: 纯确认（"对"/"就是这样"/"没错"）—— 必须整句匹配, 避免误伤"对, 但还要加导出"
_CONFIRM_ONLY_RE = re.compile(r"^(对|对的|是|是的|没错|可以|行|好的|好|就这样|就按这个|ok|okay|ok了)[。.!！~～\s]*$")
#: 纯寒暄 —— 必须【整句】匹配（"你好"✓ / "今天要做个天气应用"✗ 不能被误伤）
_GREETING_ONLY_RE = re.compile(r"^(你好|hi|hello|嗨|在吗|早上好|下午好|晚上好)[。.!！~～\s]*$", re.I)
_CHITCHAT_ONLY_RE = re.compile(
    r"^(你叫什么名字?|你是谁|你(能|会)做什么|谢谢(你)?|多谢|再见|拜拜|今天天气[^。！？]{0,8})[。.!！~～\s]*$",
    re.I,
)


def _is_pure_display_request(text: str) -> bool:
    """只要"展示当前理解", 不含新信息。"""
    return bool(_DISPLAY_RE.match(text))


def _is_pure_confirmation(text: str) -> bool:
    """纯确认（整句就是"对/好的"）—— 带后续要求的（"对, 但…"）不算。"""
    return bool(_CONFIRM_ONLY_RE.match(text))


def _is_pure_chitchat(text: str) -> bool:
    """纯寒暄/闲聊。"""
    return bool(_GREETING_ONLY_RE.match(text) or _CHITCHAT_ONLY_RE.match(text))


_PRODUCT_HINT_RE = re.compile(
    r"做|开发|产品|app|应用|端|平台|登录|排行|摇杆|按键|操作|游戏|界面|用户|"
    r"功能|需求|版本|设计|横屏|竖屏|声音|广告|内购|账号|同步|离线|"
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


def _history_section(root: Any, user_message: str, *, limit: int = 3) -> list[str]:
    """相关历史 → prompt 段落（失败安全: 任何异常 → 空，不影响主链）。

    ★ 标注为【参考非事实】: 历史是"过去发生过什么"，不是当前产品事实，
      不能进 truth 模型（否则历史会污染 Product Understanding）。
    ★ 控制 token: 默认 3 条、每条截断 —— 历史是提示不是正文。
    """
    factory = _hooks.get("history_index")
    if not root or factory is None:
        return []
    try:
        idx = factory(Path(str(root)) / "search.db")
        try:
            # 只取 event/trace/experience —— 排除 message 源:
            # 当前会话自身的消息（我的提问 + AI 上轮的回答）会以字面完全匹配
            # 排在最前，既占位又误导（上轮回答可能正是"没找到" ✗）。
            # 而"做过哪些项目"这类事实记录本就在 event 源里 ✓
            hits = idx.search(user_message, limit=max(limit * 4, 12),
                              sources=("event", "trace", "experience"))
        finally:
            idx.close()
        if not hits:
            return []
        # ★ 排除"提问回声": 用户刚打的那句话字面存在于历史里（就是当前这轮对话），
        #   它会以完全匹配排在最前，把真正的相关记录（如"记账项目"）挤出 3 条窗口 ✗
        probe = " ".join(user_message.split())
        kept = []
        for h in hits:
            body = " ".join((h.title + " " + h.snippet).split())
            if len(probe) >= 8 and (probe[:40] in body or body[:40] in probe):
                continue
            kept.append(h)
        hits = (kept or hits)[:limit]
        out = [
            "",
            "# 相关历史 (可供参考的真实记录)",
            "以下是系统历史里与用户这句话相关的记录，可用于回答"
            "「以前做过什么」「之前那个怎么样了」这类问题；",
            "但它们是【历史发生的事】，不要当作当前产品事实写进产品理解。",
        ]
        for h in hits:
            when = (h.ts[:10] if h.ts else "—")
            out.append(f"- [{h.source} {when}] {h.title[:60]}: {h.snippet[:120]}")
        return out
    except Exception as exc:  # noqa: BLE001 — 检索不可用 → 无历史段落（不禁用主链）
        print(f"[history] 相关历史段落跳过: {type(exc).__name__}: {exc}", file=sys.stderr)
        return []


#: ★ Founder 拍板的「facts 三层结构」（2026-09-19 实现第三层）:
#:   第一层 全量 = 存储（所有事实完整落盘, 不丢）—— 已实现（scoped_facts/understanding）
#:   第二层 索引 = 检索（多了之后找得回）—— 见 knowledge/history 检索层
#:   第三层 最近 = 注入（送 LLM 的【不全量】, 只取"最近 + 相关"）—— 本函数
#: 为什么: 全量送会随事实增长而稀释/挤爆上下文; 而"最近 + 相关"才是 LLM 真正需要的。
#: 保守规则（防漏关键事实）:
#:   · IDEA（产品本体）与 CONSTRAINT（硬约束）**永远保留** —— 它们绝不能因"不最近"被筛掉
#:   · 其余按「最近 N 条 + 与用户消息相关的前 M 条」并集, 保持原时间序
FACTS_RECENT = 8
FACTS_RELEVANT = 5
_ALWAYS_KEEP = ("IDEA", "CONSTRAINT")


def select_facts(facts: list[dict[str, Any]], user_message: str, *,
                 recent: int = FACTS_RECENT, relevant: int = FACTS_RELEVANT) -> tuple[list[dict], int]:
    """第三层「最近的」: 从全量事实里选出要注入 LLM 的那部分。

    返回 (选中事实, 被省略条数)。**纯函数, 确定性**。
    规则: 永久保留 IDEA/CONSTRAINT → 加"最近 N 条" → 加"与消息相关的前 M 条"（按词重叠）。
    """
    if not facts:
        return [], 0
    total = len(facts)
    if total <= recent + relevant:                      # 量少 ⇒ 全给（避免无谓筛选）
        return list(facts), 0
    keep_idx: set[int] = set()
    for i, f in enumerate(facts):
        if str(f.get("type") or "").upper() in _ALWAYS_KEEP:
            keep_idx.add(i)                             # ★ 产品本体/硬约束永不筛掉
    for i in range(max(0, total - recent), total):
        keep_idx.add(i)                                 # 最近 N
    terms = [t for t in re.split(r"[^\w\u4e00-\u9fff]+", str(user_message or "").lower()) if len(t) > 1]
    if terms:
        scored = []
        for i, f in enumerate(facts):
            if i in keep_idx:
                continue
            text = str(f.get("content") or "").lower()
            sc = sum(text.count(t) for t in terms)
            if sc:
                scored.append((sc, i))
        scored.sort(key=lambda x: (-x[0], x[1]))
        for _sc, i in scored[:relevant]:
            keep_idx.add(i)                             # 相关 M
    picked = [f for i, f in enumerate(facts) if i in keep_idx]
    return picked, total - len(picked)


def build_llm_prompt(snapshot: dict[str, Any], user_message: str, *,
                     history_root: Any = None) -> str:
    """Context Assembly → LLM prompt (只读, 不猜)。

    history_root 提供且已接线时附上【相关历史】(检索自历史库) —— 让会话能
    "想起过去"，但明确标注为参考非事实（不污染产品理解）。
    缺省 None = 不带历史（行为与之前完全一致 ✓ 向后兼容）。
    """
    # ★ 2026-09-19（Founder 拍板三层结构 · 第三层「最近的」）: 不再全量送 facts。
    #   实测此前是 `for f in facts:` 全量 ⇒ 事实一多就稀释/挤爆; 现在只送「最近 + 相关」
    #   （IDEA/CONSTRAINT 永久保留, 防筛掉关键事实）。量少时等于全送（行为不变）。
    _all_facts = snapshot.get("facts", [])
    facts, _omitted = select_facts(_all_facts, user_message)
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
    if _omitted:
        # 可解释: 让 LLM 知道自己看到的是"最近+相关", 需要更多时可要求
        lines.append(
            f"(另有 {_omitted} 条较早/不相关的事实未列出 —— 这是「最近+相关」注入;"
            f" 若需要完整理解请说明, 或用 factory conversation facts 查全量)")
    lines += _history_section(history_root, user_message)
    # ★ 2026-09-19（记忆主线 · 知识记忆接通）: 附上【项目文档知识】检索结果。
    #   来源 = RAG 索引（已按分档加权 + 单文件限流排序）; 每条带文件名与档位 ⇒ 可引用可审计。
    #   ★ 明确标注"供引用, 非既有事实" —— 不让检索内容污染"产品理解"。
    knowledge = snapshot.get("knowledge") or []
    if knowledge:
        lines += [
            "",
            "# 项目文档知识 (检索自项目文档 · 供引用 · **非**既有事实)",
            "引用时须给出文件名; 与用户说法冲突时以用户为准, 并把冲突说出来。",
        ]
        for k in knowledge:
            lines.append(f"- [{k.get('tier')}] {k.get('file')} (score={k.get('score')})")
            lines.append(f"  {str(k.get('excerpt') or '')[:240]}")
    mem = snapshot.get("memory_from") or {}
    if mem.get("count"):
        lines.append("")
        lines.append(f"# 跨会话记忆 (来自分层 · {mem.get('count')} 条 · {mem.get('layers')})")
    # ★ 2026-09-19（mem-8）: 项目历史记忆（project_memory 的类型化记忆 —— 已有机制, 本轮只接线）。
    #   它自带权威等级标注（user_intent > verified_state > repo_evidence > agent_claim > summary）,
    #   低等级仅作参考 ⇒ 原样透传, 不改写它的语义。
    pm_block = snapshot.get("project_memory_block") or ""
    if pm_block:
        lines += ["", pm_block]
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

    返回与 `proposal.build_proposal` 同构的 dict; LLM 不可用/解析失败 →
    确定性降级: 返回 CLARIFY (诚实引导) — 不猜产品事实, 不部分写 Truth。
    """
    # 1) 明显无产品语义 (寒暄/确认/纯展示请求) — 不调 LLM (省成本 + 防幻觉)
    #
    # ★ 2026-09-19 修（Founder 实测「说着说着就忘了」的根因）:
    #   原实现用 `_PRODUCT_HINT_RE` 做**关键词预筛** —— 不命中就完全不调 LLM;
    #   且"已有理解"时直接返回 operations=[]（**静默丢弃**）。
    #   实测漏掉的真实需求: 「支持借书和还书」「数据要能导出 Excel」「只给内部员工用」
    #   「我们公司叫星辰图书」（加个"需求:"前缀就命中 —— 说明是纯关键词匹配）。
    #   ⇒ 关键词永远列不全, 而失败模式是"静默丢事实"（最坏的一种）。
    #   ⇒ 改为: **只对"明确无产品语义"的三类短路**（纯展示请求 / 纯确认 / 寒暄闲聊）,
    #     其余一律交给 LLM 判断; 若 LLM 判无新事实, 它自己会返回空 operations（那是它的判断, 而非我们的关键词猜）。
    stripped = text.strip()
    if _is_pure_display_request(stripped):
        return build_proposal(
            operations=[], reply="", summary="", show_understanding=True)
    if _is_pure_confirmation(stripped):
        if _has_understanding(snapshot):
            return build_proposal(
                operations=[], summary="", show_understanding=True,
                reply="收到，就按这个理解继续。需要我「整理成 PRD」吗？")
        return build_proposal(operations=[], reply="好的。你想做什么？直接说一句就行。")
    if _is_pure_chitchat(stripped):
        if _has_understanding(snapshot):
            return build_proposal(operations=[], summary="", show_understanding=True, reply="")
        return build_proposal(
            operations=[], reply="我在。说说你想做什么产品，或者问我要怎么开始。")

    # 2) LLM 调用 (显式注入 → 本域不直连别的域)
    fn = llm_fn or _hooks.get("llm_fn")
    if fn is None:
        return _degrade_clarify(text)

    prompt = build_llm_prompt(snapshot, stripped, history_root=root)
    try:
        raw = fn(prompt)
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
