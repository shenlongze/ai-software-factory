"""factory-console/session/discovery_intelligence.py — 发现阶段 LLM 深度介入 (S10-099 + S10-102)。

产品发现 = LLM 理解主路径 + 规则状态机兜底:
- DiscoveryIntentAnalyzer: 意图理解 (优先级: 控制指令 > 查询 > 求助 >
  字段回答 > 产品描述) + 结构化提取 {problem, user, core_features, name, platform,
  usage_scenarios, mvp_scope, non_functional_requirements} + 缺失原因
  (为什么缺) + 智能追问 (≤3, 优先 1 条) + 主动分析
  (platform/competitors/scope/notes) + 理解摘要 ("我理解你要做 X, 给 Y 用...").
- 默认装配: 复用 ReasoningProvider()._default_llm_fn() (exec.cli provider 链,
  同 naming 修复 bcc1b14 模式); llm_fn=None 且无 provider/key → 抛
  DiscoveryLLMUnavailable (上层规则兜底, 诚实降级, 不伪造 LLM 理解)。
- JSON 解析宽容链: 剥 markdown code fence → json.loads → {..} 子串回退 →
  schema 校验 (category ∈ 合法面; extraction/proactive 缺字段补空;
  smart_questions 截断 ≤3); 任何失败 → DiscoveryLLMError。
- S10-102: analyze_confirmation — 确认阶段输入分类 (确认/确认+下一步/改名/
  澄清/取消/委托/其它, 附产品摘要), 失败 → ConfirmationLLMError (上层确定性表
  兜底 — 无 LLM 规则兜底真实生效, 不伪造 LLM 分类)。

边界:
- 纯标准库 + 只读引用 session/product.parse_core_features; 零新依赖
- 不改 reasoning.py / naming.py / product.py / intent.py (复用不重造)
- 不落盘、不执行; analyze 只输出结构化分析 (conversation.py 状态机消费)

设计: docs/sprint10/S10-099-discovery-llm-plan.md §2/§4
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .product import parse_core_features

#: 合法意图类别 (优先级: 控制指令 > 查询 > 求助 > 字段回答 > 产品描述 — prompt 内写明)
VALID_CATEGORIES: tuple[str, ...] = (
    "control",
    "query",
    "help_request",
    "field_answer",
    "product_description",
)

#: 合法确认分类 (S10-102 §1.2 — 确认阶段输入分类面)
VALID_CONFIRMATION_CATEGORIES: tuple[str, ...] = (
    "approve",
    "approve_next",
    "rename",
    "clarify",
    "cancel",
    "delegate",
    "other",
)

#: extraction 契约字段 (缺失补空; S10-100: 加 usage_scenarios/mvp_scope/
#: non_functional_requirements — DiscoverySession 7 字段对齐, 可选键)
EXTRACTION_FIELDS: tuple[str, ...] = (
    "problem", "user", "core_features", "name", "platform",
    "usage_scenarios", "mvp_scope", "non_functional_requirements",
)

#: proactive 契约字段
PROACTIVE_FIELDS: tuple[str, ...] = ("platform", "competitors", "scope", "notes")

#: 对话历史轮次上限 (prompt 上下文预算 — 最近 3 轮)
MAX_HISTORY_ROUNDS: int = 3

#: smart_questions 上限 (≤3, 追问时只取最重要 1 条)
MAX_SMART_QUESTIONS: int = 3

#: JSON 提取正则 (markdown code fence 内 JSON / 裸 JSON 对象 — 宽容链回退)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

#: 发现分析 prompt (计划 §2.3 核心交付 — 意图优先级 + 结构化输出契约)
_DISCOVERY_PROMPT = """你是 AI Factory 的产品经理。用户正在描述一个产品想法, 可能是完整描述、
字段回答、控制指令、查询或求助。判断意图（优先级: 控制指令 > 查询 > 求助 >
字段回答 > 产品描述）, 并尽可能结构化提取产品定义。

【对话历史】(最近 3 轮, 无则空)
{history}

【系统上一轮问题】(若有 — 用户本轮输入可能是对它的回答)
{system_question}

【用户最新输入】
{text}

【输出要求】只输出一个 JSON 对象, 禁止 markdown 围栏/注释/多余文字:
{{
  "category": "control|query|help_request|field_answer|product_description",
  "reason": "分类理由（一句）",
  "extraction": {{"problem": "", "user": "", "core_features": [], "name": "", "platform": "", "usage_scenarios": "", "mvp_scope": "", "non_functional_requirements": ""}},
  "missing_reasons": {{"problem": "该字段缺失的原因, 只在输入确实没给时列出"}},
  "smart_questions": ["针对最重要缺失字段的一个具体问题"],
  "proactive": {{"platform": "", "competitors": "", "scope": "", "notes": ""}},
  "understanding": "一句话理解摘要, 形如: 我理解你要做X, 给Y用, 核心是A/B/C",
  "suggestions": {{"field": "", "items": [], "note": ""}}
}}

规则:
- 控制指令（取消/算了/整理/重新开始/查询项目/修改字段）→ category=control, 不提取字段
- 查询（项目列表/当前项目/进度）→ category=query
- 求助（给些建议/没有想法/你看着办/帮我出主意 — 用户不是给信息而是求建议）→
  category=help_request, 不提取字段; suggestions.items 给当前最该补的缺失字段的
  3-5 条方向性建议, suggestions.field 填该字段, suggestions.note 一句话说明;
  若无缺失字段则 suggestions.items 留空
- 产品描述（哪怕不完整）→ category=product_description, 尽力提取; 提取不到的必填字段
  在 missing_reasons 说明为什么缺, smart_questions 只问最重要的一条
- 纯字段回答（"给程序员用"）→ category=field_answer, 只填对应字段; 若还有必填字段
  缺失, smart_questions 给出下一个最重要缺失字段的追问 (带 missing_reasons 理由),
  缺失已齐则 smart_questions 留空
- 若【系统上一轮问题】非空且用户本轮输入明显是对它的回答 → category=field_answer,
  extraction 只填该问题对应的字段, 不当作新产品描述 (不覆盖已填字段)
- extraction 字段只填输入中明确出现的信息, 不猜测、不编造
- 使用场景(usage_scenarios)/MVP范围(mvp_scope)/非功能要求(non_functional_requirements)
  只在描述中明确提到才填, 否则留空"""



#: 确认分析 prompt (S10-102 §1.2 — 确认阶段输入分类契约)
_CONFIRMATION_PROMPT = """你是 AI Factory 的会话助手。用户正在产品确认阶段回应
"确认创建这个产品? (y/N)" — 输入可能是确认、确认+下一步、改名、澄清提问、取消或委托。

【当前产品摘要】(用户确认的对象)
{product_summary}

【用户输入】
{text}

【输出要求】只输出一个 JSON 对象, 禁止 markdown 围栏/注释/多余文字:
{{
  "category": "approve|approve_next|rename|clarify|cancel|delegate|other",
  "next_action": "prd|develop|create|",
  "rename_to": "",
  "reason": "分类理由（一句）"
}}

规则 (优先级: 确认(含确认+下一步) > 明确改名 > 澄清提问 > 取消 > 委托 > 其它):
- 确认: 用户同意创建 (可以/好/行/确认/OK/没问题/y 等) → category=approve, 不改名
- 确认+下一步: 确认同时说出下一步意图 ("可以,先出prd"/"好,开始开发"/"行,创建项目")
  → category=approve_next, next_action 取 prd|develop|create (无则留空)
- 明确改名: 用户给出新名称 ("改名叫X"/"名字改成X"/"产品名X") → category=rename,
  rename_to 填新名称 (不含 "改名叫" 等前缀)
- 澄清提问: 问号/疑问 (？/为什么/什么意思/能改吗/这是什么/然后呢) → category=clarify,
  不改名不确认
- 取消: 拒绝创建 (n/no/取消/算了/不要) → category=cancel
- 委托: 用户没想法交给你定 (随便/你定/你看吧/都行/无所谓/听你的) → category=delegate,
  视为确认, 不改名
- 其它: 无法归入以上 (可能是新的产品名称或自定义指令) → category=other
  (上层按改名兜底处理, 不伪造分类)
"""
class DiscoveryLLMError(Exception):
    """发现阶段 LLM 失败 (调用异常 / 非法 JSON / schema 校验失败)。

    语义: 上层捕获 → 规则状态机兜底 (诚实降级, 永不伪造 LLM 理解)。"""


class DiscoveryLLMUnavailable(DiscoveryLLMError):
    """无可用 LLM (未配置 provider/key / 装配失败)。

    语义: 整个发现 LLM 通道不可用 — 上层直接规则兜底 (现有状态机零变化)。"""


class ConfirmationLLMError(DiscoveryLLMError):
    """确认阶段 LLM 分类失败 (调用异常 / 非法 JSON / schema 校验失败)。

    语义: 上层捕获 → 确定性表 + 改名兜底 (诚实降级, 永不伪造 LLM 分类)。"""


@dataclass
class DiscoveryAnalysis:
    """LLM 对用户输入的意图理解 + 结构化提取 (计划 §2.2 输出契约)。

    category: "control" | "query" | "help_request" | "field_answer" |
      "product_description"
    reason: 一句分类理由 (可审计)
    extraction: {problem, user, core_features:list, name, platform,
      usage_scenarios, mvp_scope, non_functional_requirements} — 可空
    missing_reasons: 必填缺失字段 → 为什么缺 (智能追问依据)
    smart_questions: ≤3 条针对性追问 (追问时只取最重要 1 条; field_answer
      时给出下一个最重要缺失字段的追问 — 中间字段 LLM 化契约来源)
    proactive: {platform, competitors, scope, notes} — 用户没说但该有的
    understanding: 一句理解摘要 ("我理解你要做 X, 给 Y 用, 核心是 A/B/C")
    suggestions: {field, items, note} — help_request 时填充 (当前缺失字段的
      方向性建议 3-5 条 + 一句说明; 缺省空 dict)
    """

    category: str
    reason: str = ""
    extraction: dict[str, Any] = field(default_factory=dict)
    missing_reasons: dict[str, str] = field(default_factory=dict)
    smart_questions: list[str] = field(default_factory=list)
    proactive: dict[str, str] = field(default_factory=dict)
    understanding: str = ""
    suggestions: dict[str, Any] = field(default_factory=dict)



@dataclass
class ConfirmationAnalysis:
    """LLM 对确认阶段输入的分类 (计划 §1.2 输出契约)。

    category: "approve" | "approve_next" | "rename" | "clarify" | "cancel" |
      "delegate" | "other"
    next_action: approve_next 时 "prd"/"develop"/"create" (非法 → 归一为空)
    rename_to: rename 时新名称 (不带 "改名叫" 等前缀)
    reason: 一句分类理由 (可审计)
    """

    category: str
    next_action: str = ""
    rename_to: str = ""
    reason: str = ""

class DiscoveryIntentAnalyzer:
    """发现阶段 LLM 意图理解 / 结构化提取 (计划 §2.1)。

    用法:
        analyzer = DiscoveryIntentAnalyzer()           # 默认装配 _default_llm_fn()
        analyzer = DiscoveryIntentAnalyzer(llm_fn=fn)  # 测试注入 / 真实调用方
        a = analyzer.analyze(text, history=[...])      # → DiscoveryAnalysis

    llm_fn 签名: (prompt: str, operation: str) -> str | dict (同 reasoning 口径;
    dict 视为已解析结果 — fixture 便捷)。默认装配失败 (无 provider/key) →
    DiscoveryLLMUnavailable。
    """

    def __init__(self, llm_fn: Optional[Callable[..., Any]] = None) -> None:
        if llm_fn is None:
            try:
                from .reasoning import ReasoningProvider

                llm_fn = ReasoningProvider()._default_llm_fn()  # noqa: SLF001
            except Exception as exc:  # noqa: BLE001 — 无 provider/key → 不可用
                raise DiscoveryLLMUnavailable(
                    f"无可用 LLM provider (发现阶段规则兜底): {exc}"
                ) from exc
        self._llm_fn = llm_fn

    @property
    def llm_fn(self) -> Optional[Callable[..., Any]]:
        """装配的 LLM 调用函数 (供命名等复用同一 llm_fn — S10-100 命名 LLM-gated)。"""
        return self._llm_fn

    # ------------------------------------------------------------ 主入口

    def analyze(
        self,
        text: str,
        *,
        history: Optional[list[str]] = None,
        system_question: str = "",
    ) -> DiscoveryAnalysis:
        """1 次 LLM 调用 → 结构化 JSON → 宽容解析 → schema 校验 → DiscoveryAnalysis。

        失败 (空输入/调用异常/非法 JSON/schema 缺 category) → DiscoveryLLMError
        (上层规则兜底, 诚实降级, 不伪造理解)。
        """
        text = str(text or "").strip()
        if not text:
            raise DiscoveryLLMError("输入为空, 无法分析")
        prompt = self.build_prompt(text, history=history, system_question=system_question)
        try:
            raw = self._llm_fn(prompt, "discovery_intent")
        except Exception as exc:  # noqa: BLE001 — 调用方异常 → 统一失败面
            raise DiscoveryLLMError(
                f"discovery_intent: LLM 调用异常: {exc}"
            ) from exc
        parsed = self._parse_json(raw)
        if not isinstance(parsed, dict):
            raise DiscoveryLLMError(
                "discovery_intent: LLM 输出非 JSON 对象 "
                f"(类型 {type(parsed).__name__})"
            )
        return self._to_analysis(parsed)

    def extract_once(
        self,
        text: str,
        *,
        history: Optional[list[str]] = None,
    ) -> DiscoveryAnalysis:
        """= analyze 别名 (语义清晰: 一次调用即结构化提取)。"""
        return self.analyze(text, history=history)


    # ------------------------------------------------------------ S10-102: 确认分类

    def analyze_confirmation(
        self,
        text: str,
        *,
        product_summary: str = "",
    ) -> ConfirmationAnalysis:
        """1 次 LLM 调用 → 确认阶段输入分类 → 宽容解析 → schema 校验。

        失败 (空输入/调用异常/非法 JSON/category 不合法) → ConfirmationLLMError
        (上层确定性表兜底 — 确认/改名/澄清/取消/委托 关键词, 诚实降级, 不伪造)。
        """
        text = str(text or "").strip()
        if not text:
            raise ConfirmationLLMError("输入为空, 无法分类")
        prompt = self.build_confirmation_prompt(text, product_summary=product_summary)
        try:
            raw = self._llm_fn(prompt, "confirm_intent")
        except Exception as exc:  # noqa: BLE001 — 调用方异常 → 统一失败面
            raise ConfirmationLLMError(
                f"confirm_intent: LLM 调用异常: {exc}"
            ) from exc
        parsed = self._parse_json(raw)
        if not isinstance(parsed, dict):
            raise ConfirmationLLMError(
                "confirm_intent: LLM 输出非 JSON 对象 "
                f"(类型 {type(parsed).__name__})"
            )
        return self._to_confirmation_analysis(parsed)

    def build_confirmation_prompt(
        self, text: str, *, product_summary: str = ""
    ) -> str:
        """组装确认分析 prompt (产品摘要 + 用户输入)。"""
        return _CONFIRMATION_PROMPT.format(
            product_summary=str(product_summary or "").strip() or "(无)",
            text=str(text or "").strip(),
        )

    @classmethod
    def _to_confirmation_analysis(cls, data: dict[str, Any]) -> ConfirmationAnalysis:
        """确认分类 schema 校验 + 归一化 (计划 §1.2)。

        - category 必须 ∈ 合法面 (非法/缺失 → ConfirmationLLMError → 确定性表兜底)
        - next_action 只认 prd/develop/create (其它 → 归一为空, 宽容)
        - rename_to/reason 去空白; 缺失 → ""
        """
        category = str(data.get("category") or "").strip()
        if category not in VALID_CONFIRMATION_CATEGORIES:
            raise ConfirmationLLMError(
                f"confirm_intent: category {category!r} 不合法 "
                f"(合法: {', '.join(VALID_CONFIRMATION_CATEGORIES)})"
            )
        next_action = str(data.get("next_action") or "").strip().lower()
        if next_action not in ("prd", "develop", "create"):
            next_action = ""
        return ConfirmationAnalysis(
            category=category,
            next_action=next_action,
            rename_to=str(data.get("rename_to") or "").strip(),
            reason=str(data.get("reason") or "").strip(),
        )
    # ------------------------------------------------------------ prompt

    def build_prompt(
        self, text: str, *, history: Optional[list[str]] = None,
        system_question: str = "",
    ) -> str:
        """组装发现分析 prompt (最近 3 轮 + 系统上一轮问题 + 用户最新输入)。"""
        lines: list[str] = []
        if history:
            recent = [
                str(h).strip()
                for h in history
                if str(h or "").strip()
            ][-MAX_HISTORY_ROUNDS:]
            for idx, item in enumerate(recent, 1):
                lines.append(f"{idx}. {item}")
        history_block = "\n".join(lines) if lines else "(无)"
        return _DISCOVERY_PROMPT.format(
            history=history_block,
            system_question=str(system_question or "").strip() or "(无)",
            text=text,
        )

    # ------------------------------------------------------------ 解析/校验

    @classmethod
    def _parse_json(cls, raw: Any) -> Any:
        """结构化输出宽容解析 (计划 §2.4): dict 原样 / bytes 解码 /
        str 剥 code fence → json.loads → {..} 子串回退; 失败 → 返回原值
        (调用方判非 dict → DiscoveryLLMError)。"""
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8")
            except (UnicodeDecodeError, AttributeError):  # noqa: BLE001
                return raw
        if not isinstance(raw, str):
            return raw
        text = raw.strip()
        if not text:
            return raw
        # 剥 markdown code fence (```json ... ``` / ``` ... ```)
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = _JSON_OBJECT_RE.search(text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return raw
        return raw

    @classmethod
    def _to_analysis(cls, data: dict[str, Any]) -> DiscoveryAnalysis:
        """schema 校验 + 归一化 → DiscoveryAnalysis (计划 §2.4)。

        - category 必须 ∈ 合法面 (非法/缺失 → DiscoveryLLMError → 规则兜底)
        - extraction/proactive 缺字段补空 (宽容); core_features 列表化;
          smart_questions 截断 ≤3 (次要字段失败不阻断)
        - reason/understanding 去空白; 缺失 → ""
        """
        category = str(data.get("category") or "").strip()
        if category not in VALID_CATEGORIES:
            raise DiscoveryLLMError(
                f"discovery_intent: category {category!r} 不合法 "
                f"(合法: {', '.join(VALID_CATEGORIES)})"
            )
        return DiscoveryAnalysis(
            category=category,
            reason=str(data.get("reason") or "").strip(),
            extraction=cls._normalize_extraction(data.get("extraction")),
            missing_reasons=cls._normalize_missing_reasons(
                data.get("missing_reasons")
            ),
            smart_questions=cls._normalize_questions(data.get("smart_questions")),
            proactive=cls._normalize_proactive(data.get("proactive")),
            understanding=str(data.get("understanding") or "").strip(),
            suggestions=cls._normalize_suggestions(data.get("suggestions")),
        )

    @classmethod
    def _normalize_extraction(cls, raw: Any) -> dict[str, Any]:
        """extraction 归一化: 非 dict → 空; 缺字段补空; core_features 列表化;
        字符串字段若为 list → 顿号连接 (宽容)。"""
        if not isinstance(raw, dict):
            raw = {}
        out: dict[str, Any] = {}
        for key in EXTRACTION_FIELDS:
            value = raw.get(key)
            if key == "core_features":
                out[key] = parse_core_features(value)
            elif isinstance(value, list):
                out[key] = "、".join(
                    str(v).strip() for v in value if str(v or "").strip()
                )
            else:
                out[key] = str(value or "").strip() if value not in (None, "") else ""
        return out

    @classmethod
    def _normalize_missing_reasons(cls, raw: Any) -> dict[str, str]:
        """missing_reasons 归一化: 非 dict → 空; 键值字符串化。"""
        if not isinstance(raw, dict):
            return {}
        return {
            str(key): str(value or "").strip()
            for key, value in raw.items()
            if str(key or "").strip()
        }

    @classmethod
    def _normalize_questions(cls, raw: Any) -> list[str]:
        """smart_questions 归一化: str → [str]; 去空; 截断 ≤3。"""
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            return []
        questions = [
            str(q).strip() for q in raw if str(q or "").strip()
        ]
        return questions[:MAX_SMART_QUESTIONS]

    @classmethod
    def _normalize_suggestions(cls, raw: Any) -> dict[str, Any]:
        """suggestions 归一化 (S10-101): 非 dict → 空; field/note 字符串化;
        items 列表化 (str → [str]); 缺省补空 — 诚实降级 (缺省空, 上层用默认建议)。"""
        if not isinstance(raw, dict):
            return {}
        field = str(raw.get("field") or "").strip()
        items_raw = raw.get("items")
        if isinstance(items_raw, str):
            items_raw = [items_raw]
        if isinstance(items_raw, list):
            items = [
                str(item).strip()
                for item in items_raw
                if str(item or "").strip()
            ]
        else:
            items = []
        note = str(raw.get("note") or "").strip()
        if not field and not items and not note:
            return {}  # 全空 → 空 dict (上层可统一用默认建议, 诚实降级)
        return {"field": field, "items": items, "note": note}

    @classmethod
    def _normalize_proactive(cls, raw: Any) -> dict[str, str]:
        """proactive 归一化: 非 dict → 空; 缺字段补空; list → 顿号连接。"""
        if not isinstance(raw, dict):
            raw = {}
        out: dict[str, str] = {}
        for key in PROACTIVE_FIELDS:
            value = raw.get(key)
            if isinstance(value, list):
                out[key] = "、".join(
                    str(v).strip() for v in value if str(v or "").strip()
                )
            else:
                out[key] = str(value or "").strip() if value not in (None, "") else ""
        return out
