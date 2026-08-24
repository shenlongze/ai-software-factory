"""factory-console/session/discovery_intelligence.py — 发现阶段 LLM 深度介入 (S10-099)。

产品发现 = LLM 理解主路径 + 规则状态机兜底:
- DiscoveryIntentAnalyzer: 意图理解 (优先级: 控制指令 > 查询 > 字段回答 >
  产品描述) + 结构化提取 {problem, user, core_features, name, platform} +
  缺失原因 (为什么缺) + 智能追问 (≤3, 优先 1 条) + 主动分析
  (platform/competitors/scope/notes) + 理解摘要 ("我理解你要做 X, 给 Y 用...").
- 默认装配: 复用 ReasoningProvider()._default_llm_fn() (exec.cli provider 链,
  同 naming 修复 bcc1b14 模式); llm_fn=None 且无 provider/key → 抛
  DiscoveryLLMUnavailable (上层规则兜底, 诚实降级, 不伪造 LLM 理解)。
- JSON 解析宽容链: 剥 markdown code fence → json.loads → {..} 子串回退 →
  schema 校验 (category ∈ 合法面; extraction/proactive 缺字段补空;
  smart_questions 截断 ≤3); 任何失败 → DiscoveryLLMError。

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

#: 合法意图类别 (优先级: 控制指令 > 查询 > 字段回答 > 产品描述 — prompt 内写明)
VALID_CATEGORIES: tuple[str, ...] = (
    "control",
    "query",
    "product_description",
    "field_answer",
)

#: extraction 契约字段 (缺失补空)
EXTRACTION_FIELDS: tuple[str, ...] = (
    "problem", "user", "core_features", "name", "platform",
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
字段回答、控制指令或查询。判断意图（优先级: 控制指令 > 查询 > 字段回答 > 产品描述）,
并尽可能结构化提取产品定义。

【对话历史】(最近 3 轮, 无则空)
{history}

【系统上一轮问题】(若有 — 用户本轮输入可能是对它的回答)
{system_question}

【用户最新输入】
{text}

【输出要求】只输出一个 JSON 对象, 禁止 markdown 围栏/注释/多余文字:
{{
  "category": "control|query|product_description|field_answer",
  "reason": "分类理由（一句）",
  "extraction": {{"problem": "", "user": "", "core_features": [], "name": "", "platform": ""}},
  "missing_reasons": {{"problem": "该字段缺失的原因, 只在输入确实没给时列出"}},
  "smart_questions": ["针对最重要缺失字段的一个具体问题"],
  "proactive": {{"platform": "", "competitors": "", "scope": "", "notes": ""}},
  "understanding": "一句话理解摘要, 形如: 我理解你要做X, 给Y用, 核心是A/B/C"
}}

规则:
- 控制指令（取消/算了/整理/重新开始/查询项目/修改字段）→ category=control, 不提取字段
- 查询（项目列表/当前项目/进度）→ category=query
- 产品描述（哪怕不完整）→ category=product_description, 尽力提取; 提取不到的必填字段
  在 missing_reasons 说明为什么缺, smart_questions 只问最重要的一条
- 纯字段回答（"给程序员用"）→ category=field_answer, 只填对应字段
- 若【系统上一轮问题】非空且用户本轮输入明显是对它的回答 → category=field_answer,
  extraction 只填该问题对应的字段, 不当作新产品描述 (不覆盖已填字段)
- extraction 字段只填输入中明确出现的信息, 不猜测、不编造"""


class DiscoveryLLMError(Exception):
    """发现阶段 LLM 失败 (调用异常 / 非法 JSON / schema 校验失败)。

    语义: 上层捕获 → 规则状态机兜底 (诚实降级, 永不伪造 LLM 理解)。"""


class DiscoveryLLMUnavailable(DiscoveryLLMError):
    """无可用 LLM (未配置 provider/key / 装配失败)。

    语义: 整个发现 LLM 通道不可用 — 上层直接规则兜底 (现有状态机零变化)。"""


@dataclass
class DiscoveryAnalysis:
    """LLM 对用户输入的意图理解 + 结构化提取 (计划 §2.2 输出契约)。

    category: "control" | "query" | "product_description" | "field_answer"
    reason: 一句分类理由 (可审计)
    extraction: {problem, user, core_features:list, name, platform} — 可空
    missing_reasons: 必填缺失字段 → 为什么缺 (智能追问依据)
    smart_questions: ≤3 条针对性追问 (追问时只取最重要 1 条)
    proactive: {platform, competitors, scope, notes} — 用户没说但该有的
    understanding: 一句理解摘要 ("我理解你要做 X, 给 Y 用, 核心是 A/B/C")
    """

    category: str
    reason: str = ""
    extraction: dict[str, Any] = field(default_factory=dict)
    missing_reasons: dict[str, str] = field(default_factory=dict)
    smart_questions: list[str] = field(default_factory=list)
    proactive: dict[str, str] = field(default_factory=dict)
    understanding: str = ""


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
        )

    @classmethod
    def _normalize_extraction(cls, raw: Any) -> dict[str, Any]:
        """extraction 归一化: 非 dict → 空; 缺字段补空; core_features 列表化。"""
        if not isinstance(raw, dict):
            raw = {}
        out: dict[str, Any] = {}
        for key in EXTRACTION_FIELDS:
            value = raw.get(key)
            if key == "core_features":
                out[key] = parse_core_features(value)
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
