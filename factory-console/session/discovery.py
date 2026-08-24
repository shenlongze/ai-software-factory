"""factory-console/session/discovery.py — DiscoverySession (S10-065 P0-1)。

Interactive Discovery 模型层: idea → 多轮澄清 → summary → confirm → create_product,
独立可持久化 (discovery_sessions.json), 进程退出不丢失 (resume)。

组件:
- DiscoveryState — 会话状态常量 (DISCOVERING / CLARIFYING / READY_FOR_CONFIRMATION /
  CONFIRMED / PRODUCT_CREATED / CANCELLED)
- DiscoveryQuestion — 单轮追问 {field, question, required, hint}
- DiscoverySummary — 结构化需求摘要 (name/problem/user/platform/core_features/
  usage_scenarios/mvp_scope/non_functional_requirements)
- DiscoverySession — 会话: start / process_user_input / detect_missing_fields /
  generate_question / apply_answer / build_summary / confirm / create_product /
  cancel / save / load / list_sessions / resume
- DiscoveryStateError / SessionNotFoundError — 非法状态流转/会话缺失明确报错

S10-100 (同步 LLM 化, 与 conversation 发现路径对齐):
- 复用 DiscoveryIntentAnalyzer (discovery_intelligence.py) — 一次产出/智能追问/
  理解摘要/主动分析; analyzer 注入 (测试用) + 懒装配; None/失败 → 规则兜底
  (现有逐字段行为逐字节不变, 诚实降级不伪造)
- LLM 路径标记 _ai_generated; 确认门消息 = 理解摘要首行 + to_text() + 建议名称
  候选 + 主动建议 + 确认提示; 命名 LLM-gated (临时名 + analyzer 可用 → 候选设名)

字段追问顺序 (S10-065 增强): problem → user → core_features → usage_scenarios →
mvp_scope → non_functional_requirements (在 S10-050 的 problem/user/core_features
基础上增加 usage_scenarios/mvp_scope/non_functional_requirements — 可选但建议)。

设计: docs/sprint10/S10-065-interactive-discovery-design.md §2
GAP: docs/sprint10/S10-065-gap-analysis.md G1
边界:
- 包装 ProductIntent (不修改 ProductIntent 核心语义/API); 只建模, 不复制业务
  (create_product 薄调现有 actions.create_product — 惰性 import, 循环依赖护栏)
- 纯标准库零依赖 (json/uuid/dataclasses/datetime/pathlib); 持久化失败安全 (永不抛)
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .product import ProductIntent, generate_temp_product_name, parse_core_features

# ---------------------------------------------------------------- 状态常量

#: 必填字段 (缺失 → 追问; 与 ProductIntent.REQUIRED_FIELDS 同口径)
REQUIRED_FIELDS: tuple[str, ...] = ("problem", "user", "core_features")

#: 增强字段 (可选但建议 — S10-065: 使用场景/MVP 范围/非功能需求)
ENHANCED_FIELDS: tuple[str, ...] = (
    "usage_scenarios",
    "mvp_scope",
    "non_functional_requirements",
)

#: 完整字段追问顺序 (必填 → 增强, 设计 §2 口径)
FIELD_ORDER: tuple[str, ...] = REQUIRED_FIELDS + ENHANCED_FIELDS

#: 字段 → 问题模板 (generate_question 口径 — 追问消息直接可用)
QUESTION_TEMPLATES: dict[str, str] = {
    "problem": "这个产品解决什么问题?",
    "user": "主要给谁使用?",
    "core_features": "核心功能有哪些? (用逗号或顿号分隔)",
    "usage_scenarios": "主要在哪些场景使用?",
    "mvp_scope": "第一版范围是什么? (可不填, 默认全量)",
    "non_functional_requirements": "有什么性能/安全/兼容性要求? (可不填)",
}

#: 字段 → 提示语 (DiscoveryQuestion.hint)
FIELD_HINTS: dict[str, str] = {
    "problem": "描述用户痛点或待解决的问题",
    "user": "目标用户群体",
    "core_features": "逗号/顿号分隔的核心功能列表",
    "usage_scenarios": "典型使用场景 (如: 球房计分/练习记录)",
    "mvp_scope": "第一版交付范围 (可不填)",
    "non_functional_requirements": "性能/安全/兼容性要求 (可不填)",
}

#: 会话存储文件名 (workspace 级: <workspace>/discovery_sessions.json)
SESSIONS_FILE_NAME = "discovery_sessions.json"

#: 确认提示 (READY_FOR_CONFIRMATION 后输入引导)
_CONFIRM_PROMPT = "请确认产品需求 — 输入 y 确认创建 / n 重新描述 (或 /cancel 取消)"

#: S10-100: 发现 LLM 分析器懒装配哨兵 (区分 "未装配" 与 "显式 None=规则兜底")
_ANALYZER_UNSET = object()

#: S10-100: LLM category=control 取消类关键词 (模糊改写 → cancel; 其余控制 → 重问)
_CANCEL_KEYWORDS: tuple[str, ...] = (
    "取消", "算了", "不做了", "不要了", "不想做了", "停止",
    "放弃", "退出", "重新开始", "重新描述", "重来",
)


class DiscoveryState:
    """DiscoverySession 状态常量 (设计 §2 — 值小写落盘口径)。"""

    DISCOVERING = "discovering"  # 初始化, 收集需求
    CLARIFYING = "clarifying"  # 多轮澄清中
    READY_FOR_CONFIRMATION = "ready_for_confirmation"  # 必填齐全, 等确认
    CONFIRMED = "confirmed"  # 用户已确认 (唯一允许 create_product 的状态)
    PRODUCT_CREATED = "product_created"  # 产品已创建
    CANCELLED = "cancelled"  # 已取消

    #: 全部合法状态
    STATUSES: tuple[str, ...] = (
        DISCOVERING,
        CLARIFYING,
        READY_FOR_CONFIRMATION,
        CONFIRMED,
        PRODUCT_CREATED,
        CANCELLED,
    )


class DiscoveryStateError(Exception):
    """非法状态流转 (如未确认就 create_product) — 明确报错, 不静默。"""


class SessionNotFoundError(DiscoveryStateError):
    """resume/load 会话不存在 — 明确报错, 不静默。"""


# ---------------------------------------------------------------- 数据类

@dataclass
class DiscoveryQuestion:
    """单轮澄清追问: field/question/required/hint。"""

    field: str
    question: str
    required: bool = True
    hint: str = ""


@dataclass
class DiscoverySummary:
    """结构化需求摘要 (设计 §2 — confirm 展示口径)。"""

    name: str = ""
    problem: str = ""
    user: str = ""
    platform: str = ""
    core_features: list[str] = field(default_factory=list)
    usage_scenarios: str = ""
    mvp_scope: str = ""
    non_functional_requirements: str = ""

    def to_dict(self) -> dict[str, Any]:
        """→ dict (摘要视图)。"""
        return {
            "name": self.name,
            "problem": self.problem,
            "user": self.user,
            "platform": self.platform,
            "core_features": list(self.core_features),
            "usage_scenarios": self.usage_scenarios,
            "mvp_scope": self.mvp_scope,
            "non_functional_requirements": self.non_functional_requirements,
        }

    def to_text(self) -> str:
        """用户可读摘要文本 (确认消息)。"""
        lines = [
            f"产品: {self.name or '(未命名)'}",
            f"问题: {self.problem or '(未填写)'}",
            f"目标用户: {self.user or '(未填写)'}",
            f"核心功能: {', '.join(self.core_features) if self.core_features else '(未填写)'}",
        ]
        if self.platform:
            lines.append(f"运行平台: {self.platform}")
        if self.usage_scenarios:
            lines.append(f"使用场景: {self.usage_scenarios}")
        if self.mvp_scope:
            lines.append(f"MVP 范围: {self.mvp_scope}")
        if self.non_functional_requirements:
            lines.append(f"非功能要求: {self.non_functional_requirements}")
        return "\n".join(lines)


# ---------------------------------------------------------------- 内部工具

def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (created_at/updated_at)。"""
    return datetime.now(timezone.utc).isoformat()


def _field_label(field_name: str) -> str:
    """字段名 → 中文标签 (missing_fields 返回口径, 追问消息直接可用)。"""
    from .product import FIELD_LABELS

    return FIELD_LABELS.get(field_name, field_name)


def _read_json(path: Path) -> Any:
    """读取 JSON (缺失/损坏 → None, 失败安全)。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 失败安全
        return None


def _write_json(path: Path, data: Any) -> bool:
    """落盘 JSON (失败 → False, 永不抛 — 失败安全)。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return True
    except Exception:  # noqa: BLE001 — 失败安全
        return False


# ---------------------------------------------------------------- 会话模型

class DiscoverySession:
    """交互式产品发现会话 (设计 §2): idea → 多轮澄清 → summary → confirm → 创建。

    字段:
    - session_id — 唯一会话 id (uuid4 hex)
    - workspace_id — 归属工作区 (审计)
    - idea — 用户初始想法 (原始输入)
    - product_intent — 包装的 ProductIntent (不重写其语义)
    - current_state — DiscoveryState (DISCOVERING → CLARIFYING → ... )
    - missing_fields — 最近一次 detect_missing_fields 结果 (必填缺失)
    - questions — 已追问问题列表 (审计)
    - answers — 字段 → 回答记录 (覆盖更新)
    - summary — DiscoverySummary (build_summary 产物)
    - created_product_id — create_product 后产品 id (slug)
    - created_at / updated_at — 时间戳

    状态流转 (设计 §2):
      start → DISCOVERING → (process_user_input) → CLARIFYING → ... →
      全字段回答完 → READY_FOR_CONFIRMATION → confirm → CONFIRMED →
      create_product → PRODUCT_CREATED; 任意阶段 cancel → CANCELLED。
    """

    def __init__(
        self,
        *,
        session_id: Optional[str] = None,
        workspace_id: str = "",
        idea: str = "",
        ask_enhanced: bool = True,
        analyzer: Optional[Any] = None,
    ) -> None:
        self.session_id = session_id or str(uuid.uuid4())
        self.workspace_id = str(workspace_id or "")
        self.idea = str(idea or "")
        self.product_intent = ProductIntent(
            name=generate_temp_product_name(),
            raw=str(idea or "").strip(),
            session_id=self.session_id,
        )
        self.current_state = DiscoveryState.DISCOVERING
        self.missing_fields: list[str] = list(REQUIRED_FIELDS)
        self.questions: list[DiscoveryQuestion] = []
        self.answers: dict[str, str] = {}
        self.summary: Optional[DiscoverySummary] = None
        self.created_product_id: str = ""
        self.created_at = _now_iso()
        self.updated_at = self.created_at
        #: 待追问字段队列 (按 FIELD_ORDER; ask_enhanced=False → 仅必填)
        self._pending_fields: list[str] = list(FIELD_ORDER if ask_enhanced else REQUIRED_FIELDS)
        self._ask_enhanced = bool(ask_enhanced)
        #: S10-100: 发现 LLM 分析器 — 注入/懒装配; None/失败 = 规则兜底 (诚实降级)
        self._analyzer_override: Any = analyzer
        self._analyzer: Any = _ANALYZER_UNSET
        #: S10-100: 多轮字段合并边界 (v1.1.19 模式) — 上一轮系统追问
        self._last_system_question: str = ""
        #: S10-100: LLM 真产出标记 / 理解摘要 / 主动分析 (确认门展示)
        self._ai_generated: bool = False
        self._understanding: str = ""
        self._proactive: dict[str, Any] = {}
        #: S10-100: LLM 智能追问消息 (当前待问字段展示文本; 空 = 机械模板)
        self._llm_question_text: str = ""
        #: S10-100: 建议名称候选 (LLM-gated 命名展示; 空 = 无候选)
        self._name_candidates: list[str] = []

    # ------------------------------------------------------------ start

    @classmethod
    def start(
        cls,
        idea: str,
        *,
        workspace_id: str = "",
        ask_enhanced: bool = True,
        session_id: Optional[str] = None,
        analyzer: Optional[Any] = None,
    ) -> "DiscoverySession":
        """开始一个发现会话: 初始化 + 第一个问题 (problem 追问)。

        ask_enhanced=False → 只追问必填 3 字段 (S10-050 兼容口径);
        缺省 True → 必填 + 增强字段 (usage_scenarios/mvp_scope/non_functional)。

        S10-100: analyzer 可用 → analyze(idea) → 必填齐直达 READY (理解摘要+
        建议名称候选+主动建议) / 缺 → 智能追问 1 条带理由; analyzer None/失败 →
        现有第一问 (零变化)。
        """
        session = cls(
            session_id=session_id,
            workspace_id=workspace_id,
            idea=idea,
            ask_enhanced=ask_enhanced,
            analyzer=analyzer,
        )
        handled = session._start_llm(idea)
        if not handled:
            first = session._next_question()
            if first is not None:
                session.questions.append(first)
                session._last_system_question = first.question
        return session

    # ------------------------------------------------------------ 追问

    def _next_question(self) -> Optional[DiscoveryQuestion]:
        """当前应追问的问题 (队列首字段); 队列空 → None。

        S10-100: LLM 智能追问文本优先 (_llm_question_text); 否则机械模板。
        """
        if not self._pending_fields:
            return None
        field_name = self._pending_fields[0]
        question = self._llm_question_text or self.generate_question(field_name)
        return DiscoveryQuestion(
            field=field_name,
            question=question,
            required=field_name in REQUIRED_FIELDS,
            hint=FIELD_HINTS.get(field_name, ""),
        )

    @staticmethod
    def generate_question(field_name: str) -> str:
        """字段 → 追问问题模板 (未知字段 → 兜底, 不抛)。"""
        return QUESTION_TEMPLATES.get(
            field_name, f"请补充: {_field_label(field_name)}"
        )

    # ------------------------------------------------------------ 缺失检测

    def detect_missing_fields(self) -> list[str]:
        """必填缺失字段 (中文字段名 — 追问/错误消息直接可用)。

        仅必填 (problem/user/core_features) 参与; 增强字段可选但建议,
        不阻塞 READY_FOR_CONFIRMATION 判定 (design §2 信息足够口径)。
        """
        missing = self.product_intent.missing_fields()
        self.missing_fields = missing
        return list(missing)

    def required_filled(self) -> bool:
        """必填字段是否齐全 (problem/user/core_features)。"""
        return not self.detect_missing_fields()

    # ------------------------------------------------------------ 回答

    def apply_answer(self, field_name: str, value: Any) -> None:
        """填充字段: 更新 ProductIntent 对应字段 + answers 记录 (覆盖更新)。

        core_features → parse_core_features (列表); problem/user/platform/name
        → ProductIntent 属性; 增强字段 → answers; 未知字段 → 忽略 (不崩溃,
        非法输入失败安全)。
        """
        if field_name not in (FIELD_ORDER + ("platform", "name")):
            return
        text = str(value or "").strip()
        if field_name == "core_features":
            self.product_intent.core_features = parse_core_features(text)
        elif field_name in ("problem", "user", "platform", "name"):
            setattr(self.product_intent, field_name, text)
        self.answers[field_name] = text
        self.updated_at = _now_iso()

    def process_user_input(self, text: str) -> dict[str, Any]:
        """处理用户一轮回答 → {state, question, summary, missing_fields, message}。

        流转 (设计 §2 口径):
        1. 空/纯空白回答 → 拒绝 + 重新问 (不静默跳过, 不推进字段)
        2. S10-100: analyzer 可用 → analyze(text, system_question=最近问题):
           - product_description → 提取合并 (只填缺失不覆盖) → 必填齐 READY /
             仍缺 智能追问 (带理由)
           - field_answer → 并入现有 apply 逻辑 (当前字段, 不覆盖其它)
           - control → 取消类 cancel(); 其余 → 不当作字段, 重问当前问题
           - query → 不当作字段, 重问当前问题 (模型层不逃生)
           analyzer None/失败 → 现有逻辑 (零变化)
        3. 正常回答 → apply_answer 当前字段 → 队列推进:
           - 队列空 → READY_FOR_CONFIRMATION + build_summary + 确认提示
           - 还有字段 → CLARIFYING + 下一问 (必填齐全后仍建议增强字段)
        4. READY_FOR_CONFIRMATION/CONFIRMED 后输入 → 确认引导 (不误食为答案)
        5. PRODUCT_CREATED/CANCELLED 终态 → 提示 (不崩溃)
        """
        if self.current_state in (DiscoveryState.READY_FOR_CONFIRMATION, DiscoveryState.CONFIRMED):
            return self._confirm_prompt_response()
        if self.current_state in (DiscoveryState.PRODUCT_CREATED, DiscoveryState.CANCELLED):
            return {
                "state": self.current_state,
                "question": None,
                "summary": self.summary,
                "missing_fields": self.detect_missing_fields(),
                "message": (
                    f"会话已{'完成' if self.current_state == DiscoveryState.PRODUCT_CREATED else '取消'}"
                    f" (产品: {self.created_product_id or self.product_intent.name or '无'})"
                ),
            }
        raw = (text or "").strip()
        if not raw:
            return self._reject_response("回答不能为空 — 请补充当前问题")
        # S10-100: LLM 意图分流 (失败/None → 规则兜底, 现有逻辑逐字节不变)
        analysis = self._analyze_llm(raw)
        if analysis is not None:
            resp = self._handle_llm_analysis(analysis, raw)
            if resp is not None:
                return resp
        # 现有规则逻辑 (analyzer None/失败 → 逐字段零变化)
        question = self._next_question()
        if question is None:
            # 防御: 队列空但状态未就绪 (状态异常) → 回到确认
            return self._ready_response()
        self.apply_answer(question.field, raw)
        if self._pending_fields:
            self._pending_fields.pop(0)
        self._llm_question_text = ""  # 已回答当前追问 → 下一问回归模板/新智能追问
        self.detect_missing_fields()
        nxt = self._next_question()
        if nxt is None:
            return self._ready_response()
        self.current_state = DiscoveryState.CLARIFYING
        self.questions.append(nxt)
        self._last_system_question = nxt.question
        return {
            "state": self.current_state,
            "question": nxt,
            "summary": self.summary,
            "missing_fields": list(self.missing_fields),
            "message": nxt.question,
        }

    # ------------------------------------------------------------ S10-100: LLM 分流

    def _get_analyzer(self):
        """发现 LLM 分析器 (懒装配 + 缓存; 注入优先)。

        装配失败 (无 provider/key) → None → 现有规则行为逐字节不变 (验收 3)。
        """
        if self._analyzer is not _ANALYZER_UNSET:
            return self._analyzer
        if self._analyzer_override is not None:
            self._analyzer = self._analyzer_override
        else:
            try:
                from .discovery_intelligence import DiscoveryIntentAnalyzer

                self._analyzer = DiscoveryIntentAnalyzer()
            except Exception:  # noqa: BLE001 — 无 key/provider → 规则兜底
                self._analyzer = None
        return self._analyzer

    def _analyze_llm(self, text: str):
        """LLM 可用 → analyze; 不可用/失败 → None (规则兜底, 诚实降级, 不伪造)。"""
        analyzer = self._get_analyzer()
        if analyzer is None:
            return None
        try:
            return analyzer.analyze(
                text, system_question=self._last_system_question
            )
        except Exception:  # noqa: BLE001 — LLM 失败 → 规则兜底 (永不 5xx)
            return None

    def _start_llm(self, idea: str) -> bool:
        """start() 初始描述即解析 (验收 1): product_description/field_answer →
        提取合并 (READY / 智能追问); 其它类别/失败 → False (规则第一问, 零变化)。"""
        analysis = self._analyze_llm(idea)
        if analysis is None:
            return False
        category = str(getattr(analysis, "category", "") or "")
        if category in ("product_description", "field_answer"):
            self._apply_llm_extraction(analysis)
            return True
        return False

    def _handle_llm_analysis(self, analysis, text: str) -> Optional[dict[str, Any]]:
        """LLM 意图分流 (计划 §2.3): control/query 不当字段; product_description
        提取合并; field_answer → None (并入既有规则逻辑, 当前字段不覆盖其它)。"""
        category = str(getattr(analysis, "category", "") or "")
        if category == "control":
            if self._is_cancel_control(text):
                return self._cancel_response()
            return self._requestion_response(
                "这看起来是控制指令, 不是需求信息 — 请继续回答当前问题"
            )
        if category == "query":
            return self._requestion_response(
                "这看起来是查询, 不是需求信息 — 请继续回答当前问题"
            )
        if category == "product_description":
            return self._apply_llm_extraction(analysis)
        return None  # field_answer → 并入既有规则逻辑

    @staticmethod
    def _is_cancel_control(text: str) -> bool:
        """LLM category=control → 取消类关键词命中 (模糊改写 → cancel)。"""
        norm = str(text or "").strip()
        return any(keyword in norm for keyword in _CANCEL_KEYWORDS)

    def _cancel_response(self) -> dict[str, Any]:
        """LLM control(取消) → cancel → CANCELLED 响应。"""
        self.cancel()
        return {
            "state": self.current_state,
            "question": None,
            "summary": self.summary,
            "missing_fields": self.detect_missing_fields(),
            "message": "已取消产品需求确认。",
        }

    def _requestion_response(self, note: str) -> dict[str, Any]:
        """LLM control(非取消)/query → 不当作字段, 重问当前问题 (模型层不逃生)。"""
        question = self._next_question()
        if question is not None:
            self._last_system_question = question.question
        message = f"{note}\n{question.question}" if question else note
        return {
            "state": self.current_state,
            "question": question,
            "summary": self.summary,
            "missing_fields": self.detect_missing_fields(),
            "message": message,
        }

    def _apply_llm_extraction(self, analysis) -> dict[str, Any]:
        """LLM 结构化提取合并 (计划 §2.3): 只填缺失字段, pending 只留真正缺失。

        - 必填齐 → READY (理解摘要+主动建议+命名候选, ai_generated 标记)
        - 仍缺 → 智能追问 (最重要 1 条, 带为什么缺)
        """
        self._apply_extraction(analysis.extraction or {})
        order = FIELD_ORDER if self._ask_enhanced else REQUIRED_FIELDS
        self._pending_fields = [
            field for field in order if not self._field_filled(field)
        ]
        self._ai_generated = True
        self._understanding = str(
            getattr(analysis, "understanding", "") or ""
        ).strip()
        self._proactive = dict(getattr(analysis, "proactive", None) or {})
        if self.required_filled():
            return self._ready_response()
        return self._llm_smart_question_response(analysis)

    def _apply_extraction(self, extraction: dict) -> None:
        """把 LLM 提取结果并入 (只填非空且未填字段 — 不覆盖用户已给, v1.1.19 边界)。

        problem/user/core_features/platform/name → ProductIntent (name 仅临时名
        可换); usage_scenarios/mvp_scope/non_functional_requirements → answers。
        """
        from .naming import is_temp_name

        pi = self.product_intent
        problem = str(extraction.get("problem") or "").strip()
        if problem and not pi.problem:
            pi.problem = problem
        user = str(extraction.get("user") or "").strip()
        if user and not pi.user:
            pi.user = user
        features = extraction.get("core_features") or []
        if features and not pi.core_features:
            pi.core_features = parse_core_features(features)
        name = str(extraction.get("name") or "").strip()
        if name and (not pi.name or is_temp_name(pi.name)):
            pi.name = name
        platform = str(extraction.get("platform") or "").strip()
        if platform and not pi.platform:
            pi.platform = platform
        for key in ("usage_scenarios", "mvp_scope", "non_functional_requirements"):
            value = str(extraction.get(key) or "").strip()
            if value and not self.answers.get(key, ""):
                self.answers[key] = value
        self.updated_at = _now_iso()

    def _field_filled(self, field: str) -> bool:
        """字段是否有值 (core_features 非空列表; 其余非 None/非空串)。"""
        if field == "core_features":
            return bool(self.product_intent.core_features)
        if field in ("problem", "user"):
            return bool(getattr(self.product_intent, field, ""))
        if field in ("usage_scenarios", "mvp_scope", "non_functional_requirements"):
            return bool(self.answers.get(field, ""))
        return False

    def _llm_smart_question_response(self, analysis) -> dict[str, Any]:
        """智能追问: 只问最重要 1 条 (LLM 产出), 带为什么缺 (missing_reasons 话术)。

        无 LLM 追问内容 → 机械模板兜底 (现有第一问, 逐字节不变)。
        """
        question = ""
        for q in (analysis.smart_questions or []):
            if str(q or "").strip():
                question = str(q).strip()
                break
        missing = self._pending_fields[0] if self._pending_fields else ""
        reason = str((analysis.missing_reasons or {}).get(missing) or "").strip()
        if question:
            message = question
            if reason:
                message = f"{question}\n(为什么还问: {reason})"
        else:
            nxt = self._next_question()
            message = nxt.question if nxt else ""
        self.current_state = DiscoveryState.CLARIFYING
        self._last_system_question = question or message
        self._llm_question_text = message
        q_item = DiscoveryQuestion(
            field=missing or "",
            question=message,
            required=(missing in REQUIRED_FIELDS),
            hint=FIELD_HINTS.get(missing or "", ""),
        )
        self.questions.append(q_item)
        return {
            "state": self.current_state,
            "question": q_item,
            "summary": self.summary,
            "missing_fields": self.detect_missing_fields(),
            "message": message,
        }

    @staticmethod
    def _format_proactive_line(proactive: Optional[dict]) -> str:
        """主动分析展示行: "主动建议: 平台=.. · 竞品=.. · 范围=.. · 备注=.."。"""
        if not proactive:
            return ""
        parts = []
        for key, label in (
            ("platform", "平台"),
            ("competitors", "竞品"),
            ("scope", "范围"),
            ("notes", "备注"),
        ):
            value = proactive.get(key)
            if isinstance(value, list):
                value = "、".join(
                    str(v).strip() for v in value if str(v or "").strip()
                )
            value = str(value or "").strip()
            if value:
                parts.append(f"{label}={value}")
        return "主动建议: " + " · ".join(parts) if parts else ""

    # ------------------------------------------------------------ 内部响应

    def _reject_response(self, message: str) -> dict[str, Any]:
        """空回答拒绝: 状态不变, 重新问当前问题。"""
        question = self._next_question()
        if question is not None:
            self._last_system_question = question.question
        return {
            "state": self.current_state,
            "question": question,
            "summary": self.summary,
            "missing_fields": self.detect_missing_fields(),
            "message": message,
        }

    def _ready_response(self) -> dict[str, Any]:
        """必填/全部字段收集完毕 → READY_FOR_CONFIRMATION + 摘要 + 确认提示。

        S10-100: LLM 真产出 (ai_generated) → 命名候选 + 理解摘要/主动建议消息;
        否则现有消息逐字节不变 (验收 3)。
        """
        self.current_state = DiscoveryState.READY_FOR_CONFIRMATION
        self.summary = self.build_summary()
        if self._ai_generated:
            self._maybe_suggest_names()
            self.summary = self.build_summary()  # 名称可能已换为候选1
        return {
            "state": self.current_state,
            "question": None,
            "summary": self.summary,
            "missing_fields": [],
            "message": self._ready_message(),
        }

    def _ready_message(self) -> str:
        """READY 确认消息: LLM 真产出 → 理解摘要首行 + to_text() + 建议名称候选
        + 主动建议 + 确认提示; 否则现有消息逐字节不变。"""
        base = f"{self.summary.to_text()}\n{_CONFIRM_PROMPT}"
        if not self._ai_generated:
            return base
        lines: list[str] = []
        if self._understanding:
            lines.append(self._understanding)
        lines.append(self.summary.to_text())
        if self._name_candidates:
            lines.append(f"建议名称: {self.product_intent.name or '(未命名)'}")
            for idx, cand in enumerate(self._name_candidates, 1):
                lines.append(f"  {idx}. {cand}")
            lines.append("输入 1-3 选择候选, 或直接输入新名称, 或 y 确认")
        proactive_line = self._format_proactive_line(self._proactive)
        if proactive_line:
            lines.append(proactive_line)
        lines.append(_CONFIRM_PROMPT)
        return "\n".join(lines)

    def _maybe_suggest_names(self) -> None:
        """LLM-gated 命名 (计划 §2.4): ai_generated 且 name 是临时名且 analyzer
        可用 → suggest_names (analyzer 同一 llm_fn) → 候选1设名 + 展示候选;
        无 LLM → 临时名保留 (当前行为, 零变化)。"""
        if not self._ai_generated:
            return
        from .naming import is_temp_name, suggest_names

        pi = self.product_intent
        if not pi.name or not is_temp_name(pi.name):
            return
        analyzer = self._get_analyzer()
        if analyzer is None:
            return
        llm_fn = getattr(analyzer, "llm_fn", None)
        desc = pi.raw or pi.problem or ""
        try:
            candidates = suggest_names(desc, llm_fn=llm_fn, limit=3)
        except Exception:  # noqa: BLE001 — 命名失败 → 保留临时名 (极兜底)
            candidates = []
        if candidates:
            pi.name = candidates[0]
            self._name_candidates = list(candidates)

    def _confirm_prompt_response(self) -> dict[str, Any]:
        """确认/已确认后的输入 → 确认引导 (不误食为答案)。"""
        return {
            "state": self.current_state,
            "question": None,
            "summary": self.summary,
            "missing_fields": [],
            "message": _CONFIRM_PROMPT,
        }

    # ------------------------------------------------------------ 摘要/确认

    def build_summary(self) -> DiscoverySummary:
        """结构化需求摘要 (全字段 — 缺失占位, 不静默)。"""
        self.summary = DiscoverySummary(
            name=self.product_intent.name or "",
            problem=self.product_intent.problem or "",
            user=self.product_intent.user or "",
            platform=self.product_intent.platform or "",
            core_features=list(self.product_intent.core_features or []),
            usage_scenarios=self.answers.get("usage_scenarios", ""),
            mvp_scope=self.answers.get("mvp_scope", ""),
            non_functional_requirements=self.answers.get("non_functional_requirements", ""),
        )
        return self.summary

    def confirm(self) -> "DiscoverySession":
        """用户确认 → CONFIRMED (仅 READY_FOR_CONFIRMATION 可进入; 幂等)。

        其它状态 → DiscoveryStateError (明确, 不静默)。
        """
        if self.current_state == DiscoveryState.CONFIRMED:
            return self
        if self.current_state != DiscoveryState.READY_FOR_CONFIRMATION:
            raise DiscoveryStateError(
                f"无法确认: 当前状态 {self.current_state!r} — 须为 "
                f"{DiscoveryState.READY_FOR_CONFIRMATION!r}"
            )
        self.current_state = DiscoveryState.CONFIRMED
        self.updated_at = _now_iso()
        # S10-073 P0-B: 需求确认自动 Audit (DISCOVERY_CONFIRMED, 失败安全)
        try:
            from ..audit.audit_emitter import AuditEmitter
            AuditEmitter(workspace=self.workspace_id or None).emit(
                "DISCOVERY_CONFIRMED",
                project_id=self.created_product_id or "",
                actor_type="user",
                decision_reason=f"需求确认完成: {self.idea or ''}",
            )
        except Exception:  # noqa: BLE001 — 失败安全
            pass
        return self

    def cancel(self) -> "DiscoverySession":
        """取消会话 → CANCELLED (已创建的产品不可取消)。"""
        if self.current_state == DiscoveryState.PRODUCT_CREATED:
            raise DiscoveryStateError(
                "无法取消: 产品已创建 (created_product_id="
                f"{self.created_product_id!r})"
            )
        if self.current_state == DiscoveryState.CANCELLED:
            return self
        self.current_state = DiscoveryState.CANCELLED
        self.updated_at = _now_iso()
        return self

    # ------------------------------------------------------------ 创建产品

    def create_product(
        self,
        workspace: Any = None,
        *,
        creator: Optional[Callable[..., str]] = None,
        **kw: Any,
    ) -> str:
        """创建产品 (薄调现有逻辑 — 不复制业务) → created_product_id。

        仅 CONFIRMED 允许 (验收 B) — 其它状态 → DiscoveryStateError。
        creator 可注入 (测试用); 缺省 _create_product_via_actions 薄调
        actions.create_product (惰性 import, 循环依赖护栏)。
        """
        if self.current_state != DiscoveryState.CONFIRMED:
            raise DiscoveryStateError(
                f"只有 {DiscoveryState.CONFIRMED!r} 状态才允许创建产品 "
                f"(当前: {self.current_state!r})"
            )
        if creator is None:
            creator = _create_product_via_actions
        product_id = creator(workspace, self.product_intent, **kw)
        self.created_product_id = str(product_id or "")
        self.current_state = DiscoveryState.PRODUCT_CREATED
        self.updated_at = _now_iso()
        return self.created_product_id

    # ------------------------------------------------------------ 持久化

    def to_dict(self) -> dict[str, Any]:
        """→ dict (discovery_sessions.json 条目 — 全字段, resume 可恢复)。"""
        return {
            "session_id": self.session_id,
            "workspace_id": self.workspace_id,
            "idea": self.idea,
            "product_intent": self.product_intent.to_dict(),
            "current_state": self.current_state,
            "missing_fields": list(self.missing_fields),
            "questions": [
                {
                    "field": q.field,
                    "question": q.question,
                    "required": q.required,
                    "hint": q.hint,
                }
                for q in self.questions
            ],
            "answers": dict(self.answers),
            "summary": self.summary.to_dict() if self.summary is not None else None,
            "created_product_id": self.created_product_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "_pending_fields": list(self._pending_fields),
            "_ask_enhanced": bool(self._ask_enhanced),
            "_last_system_question": self._last_system_question,
            "_ai_generated": bool(self._ai_generated),
            "_understanding": self._understanding,
            "_proactive": dict(self._proactive),
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["DiscoverySession"]:
        """dict → DiscoverySession (缺失/损坏 → None, 失败安全)。"""
        if not isinstance(data, dict) or not data.get("session_id"):
            return None
        intent_data = data.get("product_intent")
        session = cls(
            session_id=str(data.get("session_id")),
            workspace_id=str(data.get("workspace_id") or ""),
            idea=str(data.get("idea") or ""),
            ask_enhanced=bool(data.get("_ask_enhanced", True)),
        )
        session.product_intent = ProductIntent.from_dict(intent_data or {})
        session.product_intent.session_id = session.session_id
        state = str(data.get("current_state") or DiscoveryState.DISCOVERING)
        if state not in DiscoveryState.STATUSES:
            state = DiscoveryState.DISCOVERING
        session.current_state = state
        session.missing_fields = [
            str(f) for f in (data.get("missing_fields") or [])
        ]
        session.questions = [
            DiscoveryQuestion(
                field=str(q.get("field") or ""),
                question=str(q.get("question") or ""),
                required=bool(q.get("required", True)),
                hint=str(q.get("hint") or ""),
            )
            for q in (data.get("questions") or [])
            if isinstance(q, dict)
        ]
        session.answers = {
            str(k): str(v)
            for k, v in (data.get("answers") or {}).items()
        }
        summary = data.get("summary")
        if isinstance(summary, dict):
            session.summary = DiscoverySummary(
                name=str(summary.get("name") or ""),
                problem=str(summary.get("problem") or ""),
                user=str(summary.get("user") or ""),
                platform=str(summary.get("platform") or ""),
                core_features=[
                    str(f) for f in (summary.get("core_features") or [])
                ],
                usage_scenarios=str(summary.get("usage_scenarios") or ""),
                mvp_scope=str(summary.get("mvp_scope") or ""),
                non_functional_requirements=str(
                    summary.get("non_functional_requirements") or ""
                ),
            )
        session.created_product_id = str(data.get("created_product_id") or "")
        session.created_at = str(data.get("created_at") or "")
        session.updated_at = str(data.get("updated_at") or "")
        pending = data.get("_pending_fields")
        if isinstance(pending, list):
            session._pending_fields = [str(f) for f in pending]
        # S10-100: LLM 状态字段 (旧会话文件缺省 → 默认值, 兼容不崩)
        session._last_system_question = str(data.get("_last_system_question") or "")
        session._ai_generated = bool(data.get("_ai_generated", False))
        session._understanding = str(data.get("_understanding") or "")
        proactive = data.get("_proactive")
        session._proactive = (
            {str(k): str(v) for k, v in proactive.items()}
            if isinstance(proactive, dict)
            else {}
        )
        return session

    @staticmethod
    def _sessions_file(workspace: Any, file: Any = None) -> Path:
        """会话存储文件路径 (显式 file 优先; 否则 <workspace>/discovery_sessions.json)。"""
        if file is not None:
            return Path(file)
        return Path(workspace) / SESSIONS_FILE_NAME

    def save(self, workspace: Any, file: Any = None) -> Optional[Path]:
        """持久化到 discovery_sessions.json (append/覆盖同 session_id; 失败安全)。

        成功 → Path; 失败 → None (不抛)。
        """
        path = self._sessions_file(workspace, file)
        sessions = self.load_all(workspace, file=path) if path.is_file() else []
        entry = self.to_dict()
        for i, existing in enumerate(sessions):
            if existing.get("session_id") == self.session_id:
                sessions[i] = entry
                break
        else:
            sessions.append(entry)
        return path if _write_json(path, sessions) else None

    @classmethod
    def load_all(cls, workspace: Any, file: Any = None) -> list[dict[str, Any]]:
        """读回全部会话条目 (缺失/损坏 → [], 失败安全)。"""
        path = cls._sessions_file(workspace, file)
        data = _read_json(path)
        if not isinstance(data, list):
            return []
        return [d for d in data if isinstance(d, dict)]

    @classmethod
    def load(
        cls, workspace: Any, session_id: str, file: Any = None
    ) -> Optional["DiscoverySession"]:
        """按 session_id 读回会话; 不存在 → None (失败安全)。"""
        for entry in cls.load_all(workspace, file=file):
            if entry.get("session_id") == session_id:
                return cls.from_dict(entry)
        return None

    @classmethod
    def list_sessions(
        cls, workspace: Any, file: Any = None
    ) -> list[dict[str, Any]]:
        """会话列表 (摘要视图 — id/idea/state/updated_at; 失败安全 → [])。"""
        sessions = cls.load_all(workspace, file=file)
        result: list[dict[str, Any]] = []
        for entry in sessions:
            state = str(entry.get("current_state") or "")
            if state not in DiscoveryState.STATUSES:
                state = DiscoveryState.DISCOVERING
            result.append(
                {
                    "session_id": str(entry.get("session_id") or ""),
                    "idea": str(entry.get("idea") or ""),
                    "state": state,
                    "created_at": str(entry.get("created_at") or ""),
                    "updated_at": str(entry.get("updated_at") or ""),
                }
            )
        return result

    @classmethod
    def resume(
        cls, workspace: Any, session_id: str, file: Any = None
    ) -> "DiscoverySession":
        """从磁盘恢复会话 (CLI/进程退出不丢失)。

        会话不存在 → SessionNotFoundError (明确, 不静默)。
        """
        session = cls.load(workspace, session_id, file=file)
        if session is None:
            raise SessionNotFoundError(
                f"发现会话不存在: {session_id!r} "
                f"(文件: {cls._sessions_file(workspace, file)})"
            )
        return session


# ---------------------------------------------------------------- 薄调桥

def _create_product_via_actions(
    workspace: Any, product: ProductIntent, **kw: Any
) -> str:
    """薄调现有 actions.create_product (不复制业务 — GAP 复用口径)。

    构造 ExecutionContext (session.product_intent 复用 — create_product
    优先消费会话产品意图) → actions.create_product → 返回产品 id (slug)。
    失败 → DiscoveryStateError (明确, 不静默)。

    惰性 import .actions (循环依赖护栏: actions.py 顶层 import 本模块)。
    """
    from .action import ExecutionContext
    from .actions import create_product
    from .context import SessionContext
    from .intent import IntentObject

    session = SessionContext(workspace=str(workspace))
    session.product_intent = product  # 复用会话产品意图 (不复制字段映射)
    intent = IntentObject(
        intent_type="create_product",
        params={},
        raw=product.raw or "",
        source="discovery",
    )
    ctx = ExecutionContext(
        workspace=Path(workspace),
        session=session,
        user="user",
        project="",
        intent=intent,
    )
    result = create_product(ctx)
    if not result.ok:
        raise DiscoveryStateError(
            f"产品创建失败: {result.error or result.message}"
        )
    data = result.data or {}
    # product_file 是权威位置 (projects/<slug>/product.json) — 优先取目录名
    product_file = str(data.get("product_file") or "")
    if product_file:
        return Path(product_file).parent.name
    project = data.get("project") or {}
    product_data = data.get("product") or {}
    return str(
        project.get("slug")
        or project.get("id")
        or product_data.get("name")
        or product.name
        or ""
    )


__all__ = [
    "DiscoveryState",
    "DiscoveryStateError",
    "SessionNotFoundError",
    "DiscoveryQuestion",
    "DiscoverySummary",
    "DiscoverySession",
    "REQUIRED_FIELDS",
    "ENHANCED_FIELDS",
    "FIELD_ORDER",
    "QUESTION_TEMPLATES",
    "SESSIONS_FILE_NAME",
    "_create_product_via_actions",
]
