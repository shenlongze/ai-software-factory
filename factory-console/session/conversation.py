"""factory-console/session/conversation.py — Conversation State + Manager (S10-048 P3 + S10-050 P4)。

会话状态模型 (基础 flow + S10-050 产品发现, 不过度开发 — 设计 §2.6 + §2.4):
- ConversationState(Enum) — DISCOVERY/CLARIFICATION/PRODUCT_CONFIRMATION/
  CONFIRMATION/PROJECT_CREATION/EXECUTION/DONE
- ConversationResponse — handle() 产出: state + message + needs_input
- ConversationManager — 状态机: state / pending_intent / product_intent /
  history / transition / handle / reset

基础 flow (handle):
  非 slash 文本 → IntentParser.parse →
    - create_product intent → start_product_discovery (S10-050: DISCOVERY 多轮)
    - 识别 intent → pending_intent + CONFIRMATION (返回计划确认消息)
    - 未识别     → CLARIFICATION (提示澄清)
  slash 文本 → 交命令注册表 (状态机不处理, 状态不变)

S10-050 产品发现流程 (P4):
  start_product_discovery → DISCOVERY 多轮追问 (problem → user → core_features,
  缺什么问什么) → 必填齐全 → PRODUCT_CONFIRMATION (摘要 + y/N)
  → handle_product_confirm: y → PROJECT_CREATION (confirm_fn 执行创建) → DONE;
    n → 重置 DISCOVERY (product_intent 清空)

边界 (设计 §2.7):
- 只实现 state model + interface + 基础 flow + 产品发现; EXECUTION 由后续 Task 驱动
- 零依赖 (纯标准库 + session.product), 不复制业务逻辑 (创建执行经 confirm_fn 由宿主注入)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from .discovery_guide import (
    APPROVE_WORDS,
    DEFAULT_SUGGESTIONS,
    EXIT_COMMANDS,
    HELP_KEYWORDS,
    format_progress,
    lifecycle_line,
    match_approve,
    match_approve_next,
    match_clarify,
    match_direct_action,
    match_delegate,
    match_rename,
    normalize_help_text,
)
from .intent import (
    INTENT_CREATE_PRODUCT,
    INTENT_RUN_TASK,
    IntentObject,
    IntentParser,
    KeywordIntentParser,
)
from .product import (
    FIELD_LABELS,
    FIELD_QUESTIONS,
    ProductIntent,
    generate_temp_product_name,
    parse_core_features,
)

#: run_task 执行所需的定位参数 (project/task/task_id — 任一缺失 → 澄清)
_TASK_TARGET_KEYS = ("project", "task", "task_id")

#: 产品发现必填字段追问顺序 (设计 §2.3: problem → user → core_features)
_PRODUCT_FIELD_ORDER: tuple[str, ...] = ("problem", "user", "core_features")

#: S10-109: 字段内容模式 (确定性归类 — 答非所问智能填匹配字段; 模块级常量, 不依赖 LLM)
_FIELD_PATTERNS: dict[str, tuple[str, ...]] = {
    "user":          (r"给.{1,12}用", r"面向.{1,12}", r".{1,12}用户", r".{1,12}人群",
                      r".{1,12}学生", r".{1,12}白领", r".{1,12}开发者", r".{1,12}团队", r".{1,12}企业"),
    "core_features": (r"支持.{1,20}", r"可以.{1,20}", r"能.{1,20}", r".{1,12}功能",
                      r".{1,12}报表", r".{1,12}记录", r".{1,12}统计", r".{1,12}导出", r".{1,12}提醒"),
    "problem":       (r"解决.{1,20}", r".{1,12}麻烦", r".{1,12}痛点", r".{1,12}痛苦",
                      r".{1,12}难", r".{1,12}不便", r".{1,12}费时", r".{1,12}低效"),
}

#: S10-109: 字段归属优先级 (多命中 — 规格: user > core_features > problem)
_FIELD_MATCH_PRIORITY: tuple[str, ...] = ("user", "core_features", "problem")


def _resolve_answer_field(text: str, pending: list[str]) -> Optional[str]:
    """字段归属判定 (S10-109, 确定性, 不依赖 LLM): 确认词整句 → None (不当字段值,
    调用方提示缺字段); 命中非当前字段模式且该字段未填 → 匹配字段; 未命中 → 当前字段
    (正常回答零变化, 逐字节不变)。"""
    norm = str(text or "").strip()
    if not norm or not pending:
        return pending[0] if pending else None
    # 1. 确认词整句匹配 (复用 discovery_guide.APPROVE_WORDS; 整句才触发 —
    #    "做报表" 不误判; y/yes 已在 APPROVE_WORDS, 显式列出与规格逐字对齐)
    if norm.lower() in APPROVE_WORDS or norm.lower() in ("y", "yes"):
        return None
    # 2. 模式匹配 (优先级 user > core_features > problem; 只填未填字段)
    for field in _FIELD_MATCH_PRIORITY:
        if field not in pending:
            continue
        if any(re.search(p, norm) for p in _FIELD_PATTERNS.get(field, ())):
            return field
    # 3. 未命中 → 当前字段 (兼容正常回答, 逐字节不变)
    return pending[0]

#: S10-102: 确认词已上收 discovery_guide.APPROVE_WORDS (确定性表唯一来源)
#: S10-081: 确认阶段取消词 (其余非确认/改名/澄清/委托输入 → 按新分流处理)
_CANCEL_ANSWERS: frozenset[str] = frozenset({"n", "no", "取消", "算了", "不要"})

#: 产品流程控制短语 — 取消/退出当前产品发现 (非答案; 精确匹配, 不误吞正常字段回答)
_PRODUCT_CANCEL_PHRASES: frozenset[str] = frozenset({
    "取消", "算了", "不做了", "不要了", "不想做了", "停止",
    "放弃", "退出", "重新开始", "重新描述", "重来",
})

#: 需求整理短语 — 只整理需求, 不创建项目 (前缀匹配 — 显式命令口径,
#: 回应 "先帮我整理需求, 不要创建项目" 类输入, 不进入创建流程)
_PRODUCT_SUMMARY_PHRASES: tuple[str, ...] = (
    "你先帮我整理", "你帮我整理", "你先整理", "请帮我整理", "请先帮我整理",
    "先帮我整理", "帮我整理", "先整理", "只整理", "只要整理",
    "不要创建", "不创建", "先不要创建", "先不创建",
    "你整理一下", "请整理一下",
)

#: 产品流程逃生短语 — 输入其它意图 (项目列表/创建项目/当前项目) → 产品流程让位,
#: 原输入交回宿主按普通意图链处理 (精确匹配 — 命令式短语, 不误吞字段回答)
_PRODUCT_ESCAPE_PHRASES: frozenset[str] = frozenset({
    "项目列表", "项目清单", "查看项目", "有哪些项目", "现在有哪些项目", "我现在有哪些项目",
    "当前项目", "当前项目是什么", "刚刚创建的项目", "最近创建的项目", "最近创建了什么",
})

#: "现在创建" 短语 — 发现阶段必填未齐 → 引导一次性补齐 (不逃生到空名 create_project);
#: 确认阶段 → 等价 y (直接创建)
_PRODUCT_CREATE_NOW_PHRASES: frozenset[str] = frozenset({
    "创建项目", "现在创建项目", "直接创建项目", "直接创建", "现在创建", "马上创建",
})

#: 修改指令标记 (分隔字段与值 — "把用户改成X" / "功能改为X")
_EDIT_MARKERS: tuple[str, ...] = ("改成", "改为", "修改成", "更改为", "更新为")

#: 修改指令字段别名 (定位要修改的字段)
_EDIT_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "problem": ("问题", "痛点", "要解决的问题"),
    "user": ("用户", "目标用户", "使用者"),
    "core_features": ("功能", "核心功能", "功能点", "特性"),
    "name": ("名称", "名字", "产品名", "产品名称"),
    "platform": ("平台",),
}

#: 修改指令动词前缀 (无字段别名时, 需显式修改意图才识别为编辑指令)
_EDIT_VERB_PREFIXES: tuple[str, ...] = ("修改", "改一下", "帮我改", "请修改", "更新", "调整")

#: 删除/清空指令动词 (S10-104 — "把核心功能删掉"/"清空目标用户"; 复用
#: _EDIT_FIELD_ALIASES 别名; 命中 → 字段清空 → 重新确认/追问, 绝不当改名)
_DELETE_VERBS: tuple[str, ...] = ("删除", "删掉", "清空", "去掉", "移除", "不要")

#: 删除指令动词 (序 2 — 动词前置: "清空目标用户"/"删除核心功能"; 不含 "不要" —
#: "不要用户" 非自然删除表达)
_DELETE_VERBS_PREFIX: tuple[str, ...] = ("清空", "删除", "删掉", "去掉", "移除")

#: 批量模式下 "是否补充?" 的肯定回答 → 重新展示剩余问题
_PRODUCT_SUPPLEMENT_ANSWERS: frozenset[str] = frozenset({
    "是", "好", "行", "要", "补充", "可以", "对", "y", "yes",
})

#: 批量问题短语 — 用户嫌问题多 → 一次性列出剩余必填问题 (前缀匹配)
_PRODUCT_BATCH_PHRASES: tuple[str, ...] = (
    "问题太多", "问题有点多", "问题好多", "问题太多了",
    "一次性问", "一次问完", "一次问", "一起问", "太啰嗦",
)

#: S10-099: LLM category=control 模糊改写的取消类关键词 (确定性硬闸未命中后 —
#: "取消掉这个需求吧" 类改写 → 取消; 精确短语仍走 _PRODUCT_CANCEL_PHRASES)
_LLM_CANCEL_KEYWORDS: tuple[str, ...] = (
    "取消", "算了", "不做了", "不要了", "不想做", "停止",
    "放弃", "退出", "重来", "重新开始",
)

#: S10-099: LLM category=control 模糊改写的整理类关键词 (→ 整理不创建,
#: 覆盖 "整理一下" 类确定性漏网 — 验收 2)
_LLM_SUMMARY_KEYWORDS: tuple[str, ...] = (
    "整理", "汇总", "梳理", "不要创建", "不创建", "只整理", "需求文档",
)

#: 批量问题模式展示用紧凑问题 (编号列表 — 不重复大段引导语)
_BATCH_QUESTIONS: dict[str, str] = {
    "problem": "产品解决什么问题? (用户遇到什么困难? 为什么现在的方法不好?)",
    "user": "目标用户是谁? (主要给谁用, 例如: 个人用户 / 学生 / 中小企业)",
    "core_features": "核心功能有哪些? (用逗号或顿号分隔, 例如: 记账、统计、导出)",
}

#: 批量回答标签别名 (去 "痛点:/用户:/功能:" 前缀 — 批量回答友好)
_FIELD_LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    "problem": ("痛点", "问题", "解决", "要解决的问题", "产品解决"),
    "user": ("用户", "目标用户", "使用者", "给谁用", "面向谁", "面向"),
    "core_features": ("功能", "核心功能", "功能点", "特性"),
}

#: 确认+动作 标签映射 (S10-10x — 发现阶段缺失提示复用)
_NEXT_ACTION_LABELS: dict[str, str] = {
    "prd": "PRD文档",
    "feature_list": "功能清单",
    "html": "HTML页面",
    "docs": "文档",
}

#: 产品确认提示 (y/N 约定: 回车/其他 → 拒绝)
_PRODUCT_CONFIRM_PROMPT = "确认创建这个产品? (y/N)"

#: 产品创建成功后引导 (S10-051 P6): 指向 prepare_project 意图关键词
_ENGINEERING_GUIDE = (
    "产品定义完成 — 是否生成工程计划? 输入 '准备开发' 或 '生成工程计划'"
)


#: S10-099: 未显式注入 analyzer 的哨兵 (区分 "未装配" 与 "显式禁用")
_DISCOVERY_ANALYZER_UNSET = object()


class ConversationState(Enum):
    """会话状态 (设计 §2.6 + S10-050 §2.4): 收集需求 → 澄清 → 确认 → 执行 → 完成。

    S10-050 扩展: PRODUCT_CONFIRMATION (确认 ProductIntent) 与 PROJECT_CREATION
    (创建项目) — 产品发现流程 (DISCOVERY 多轮追问 → 确认 → 创建)。
    """

    DISCOVERY = "discovery"  # 收集需求 (产品发现: 缺什么问什么)
    CLARIFICATION = "clarification"  # 澄清缺失信息
    PRODUCT_CONFIRMATION = "product_confirmation"  # 确认 ProductIntent (S10-050)
    CONFIRMATION = "confirmation"  # 确认执行计划
    PROJECT_CREATION = "project_creation"  # 创建项目 (S10-050)
    EXECUTION = "execution"  # 执行中
    DONE = "done"


@dataclass
class ConversationResponse:
    """ConversationManager.handle() 的产出: 当前状态 + 给用户的消息 + 是否等待输入。

    passthrough: 产品流程逃生标记 (True → 宿主应按普通意图链重新处理原输入,
    不展示 message; 产品流程让位)。
    summary_only: "整理需求不创建" 标记 (True → 宿主应把需求快照落盘为
    discovery.md 资产, 不进入创建流程)。
    product_snapshot: 需求快照 (summary_only 时携带 ProductIntent.to_dict(),
    供宿主落盘 — 产品流程已重置, 快照随响应传递)。
    """

    state: ConversationState
    message: str = ""
    needs_input: bool = False
    passthrough: bool = False
    summary_only: bool = False
    product_snapshot: Optional[dict[str, Any]] = None
    #: S10-099: LLM 理解摘要 / 主动分析 / AI 产出标记 (缺省零影响 — 前端/日志可区分)
    understanding: Optional[str] = None
    proactive: Optional[dict[str, Any]] = None
    ai_generated: bool = False
    #: S10-102/104: 确认+下一步信号 (approved + next_action → 宿主创建成功后执行;
    #: "prd" → generate_prd; feature_list/html/docs → 信号注释 (产出引擎 backlog);
    #: develop/create 只传信号不执行)
    next_action: Optional[str] = None
    #: S10-103: 退出会话信号 (True → 宿主应 print 退出提示并 running=False;
    #: 发现/确认中 exit/quit/再见/退出会话 → 命令分流, 不当字段)
    exit_requested: bool = False


class ConversationManager:
    """会话状态机 (基础 flow) — 跟踪对话状态与待确认意图, 历史可审计。

    - state: 当前状态 (初始 DISCOVERY)
    - pending_intent: 识别成功后挂起的 Intent (等待确认/澄清)
    - history: 事件记录 ({"event": "input"|"transition", ...}) — 可审计
    - transition(new_state): 状态迁移 (非法枚举 → ValueError, 不静默)
    - handle(text, parser): 基础 flow — 识别 → CONFIRMATION; 未识别 → CLARIFICATION
    - reset(): 回到初始 DISCOVERY (清空 pending_intent / history)
    """

    def __init__(
        self,
        parser: Optional[IntentParser] = None,
        *,
        analyzer: Any = _DISCOVERY_ANALYZER_UNSET,
    ) -> None:
        self.state = ConversationState.DISCOVERY
        self.pending_intent: Optional[IntentObject] = None
        self.history: list[dict[str, Any]] = []
        #: 默认解析器 (handle 未显式传 parser 时使用; 可注入定制/LLM 版)
        self._parser = parser if parser is not None else KeywordIntentParser()
        #: S10-050: 当前产品意图 (DISCOVERY 多轮追问产物; None = 无进行中的产品流程)
        self.product_intent: Optional[ProductIntent] = None
        #: 产品发现待追问字段队列 (按 _PRODUCT_FIELD_ORDER; 空 = 必填齐全)
        self._product_pending: list[str] = []
        #: 批量问题模式 (用户嫌问题多 → 一次性列出剩余必填问题)
        self._product_batch_mode: bool = False
        #: S10-099: 发现 LLM 分析器 — 注入/懒装配; None = 规则兜底 (诚实降级)
        #: 显式传 None → 禁用 LLM (确定性测试); 不传 → 首次使用时装配
        self._discovery_analyzer: Any = _DISCOVERY_ANALYZER_UNSET
        self._discovery_analyzer_override: Any = analyzer
        #: S10-099: 最近一次成功 LLM 分析 (确认门理解摘要/主动分析来源; 未用 LLM → None)
        self._discovery_analysis: Optional[Any] = None
        self._last_system_question: str = ""  # 上一轮系统追问 (LLM 多轮字段合并边界)
        #: S10-101: 求助建议挂起 ({"field", "items"}) — 用户 y/1-3/自定义 → 填入字段
        self._suggestion_proposal: Optional[dict[str, Any]] = None

    def transition(self, new_state: ConversationState) -> None:
        """状态迁移: 记录 history (from → to) 后更新 state。

        非法值 (非 ConversationState) → ValueError (明确, 不静默)。
        """
        if not isinstance(new_state, ConversationState):
            raise ValueError(
                f"非法会话状态: {new_state!r} (须为 ConversationState 枚举)"
            )
        self.history.append(
            {"event": "transition", "from": self.state.value, "to": new_state.value}
        )
        self.state = new_state

    def handle(
        self, text: str, parser: Optional[IntentParser] = None
    ) -> ConversationResponse:
        """基础 flow + S10-050 产品流程: 非 slash 文本 → parse → 产品流程 / 确认。

        - 空输入 → CLARIFICATION (提示描述需求)
        - slash 文本 → 状态不变 (命令注册表处理, 不在状态机范围)
        - 产品流程进行中 (product_intent 存在且状态 DISCOVERY/PRODUCT_CONFIRMATION)
          → 输入直接进产品流程 (handle_product_answer / handle_product_confirm)
        - 识别 create_product intent → start_product_discovery (DISCOVERY 多轮追问)
        - 识别成功 (其它 intent) → pending_intent 挂起 + 迁移 CONFIRMATION
        - 未识别 → 迁移 CLARIFICATION, 提示澄清
        """
        self.history.append({"event": "input", "text": text})
        raw = (text or "").strip()
        if not raw:
            return self._clarify("请输入你的需求描述 (例如: '创建一个项目' 或 '项目列表')")
        if raw.startswith("/"):
            # S10-103: slash → passthrough=True — 宿主重分发到命令注册表执行
            # (不再死胡同消息; 状态机不接管, 状态不变)
            return ConversationResponse(
                state=self.state,
                message="",
                needs_input=True,
                passthrough=True,
            )
        # S10-103: EXIT 命令 → exit_requested (产品流程进行中同样先退出 —
        # 命令分流在字段收集之前; "退出" 已在产品流程分支由 _product_control
        # 先处理 → 取消发现, 不走到这里)
        if raw in EXIT_COMMANDS:
            return ConversationResponse(
                state=self.state,
                message="",
                needs_input=False,
                exit_requested=True,
            )
        # S10-050 P4: 产品流程进行中 → 答案直接进产品流程 (多轮追问 / 确认)
        if self.product_intent is not None and self.state in (
            ConversationState.DISCOVERY,
            ConversationState.PRODUCT_CONFIRMATION,
        ):
            if self.state == ConversationState.PRODUCT_CONFIRMATION:
                return self.handle_product_confirm(raw)
            return self.handle_product_answer(raw)
        intent = (parser or self._parser).parse(raw)
        if intent is None:
            return self._clarify(
                "未识别意图 — 请换个说法描述需求 (例如: '创建项目' / '项目列表' / '状态')"
            )
        # S10-050 P1: create_product intent → 产品发现流程 (多轮追问)
        if intent.intent_type == INTENT_CREATE_PRODUCT:
            return self.start_product_discovery(raw)
        # S10-049 P4 (最小): run_task 缺 project/task 定位参数 → 澄清
        # (不挂起 pending_intent — 任务目标未明确, 不进入确认/执行)
        if intent.intent_type == INTENT_RUN_TASK and not any(
            intent.parameters.get(key) for key in _TASK_TARGET_KEYS
        ):
            return self._clarify(
                "需要指定项目或任务: /project <id> 或 描述 '给 X 项目实现 Y'"
            )
        self.pending_intent = intent
        self.transition(ConversationState.CONFIRMATION)
        detail = f"{intent.intent_type} {intent.parameters or ''}".strip()
        return ConversationResponse(
            state=self.state,
            message=f"确认执行计划: {detail}",
            needs_input=True,
        )

    # -------------------------------------------------- S10-050: 产品发现流程 (P4)

    def start_product_discovery(self, text: str) -> ConversationResponse:
        """产品发现入口: 初始化 ProductIntent (临时名) → DISCOVERY → 第一个追问。

        - ProductIntent.name 缺省 → "未命名产品-<ts>" (临时名, 验收 G)
        - 追问顺序 problem → user → core_features (缺什么问什么, 验收 C/F)
        - S10-099: LLM 可用 → 初始描述即解析 (必填齐直入确认 / 缺则智能追问,
          验收 1); LLM 不可用/失败 → 现有逐字段追问不变 (诚实降级)
        - 返回当前缺失字段的明确问题 (不静默)
        """
        self.product_intent = ProductIntent(
            name=generate_temp_product_name(),
            raw=(text or "").strip(),
            session_id=None,
        )
        self._product_pending = list(_PRODUCT_FIELD_ORDER)
        self._last_system_question = ""  # 新发现重置追问上下文
        self._discovery_analysis = None  # S10-099: 新流程清空上次 LLM 理解
        self._suggestion_proposal = None  # S10-101: 新流程清空求助提案
        self.pending_intent = None  # 产品流程接管, 不挂起普通 intent
        if self.state != ConversationState.DISCOVERY:
            self.transition(ConversationState.DISCOVERY)
        # S10-099: LLM 可用 → 初始描述即解析 (历史=[text], 计划 §3.1)
        analysis = self._analyze_discovery(text, history=[text])
        if analysis is not None:
            handled = self._handle_llm_analysis(analysis, text)
            if handled is not None:
                return handled
        return ConversationResponse(
            state=self.state,
            message=self._guide_message(self._next_product_question()),
            needs_input=True,
        )

    def _next_product_question(self) -> str:
        """当前缺失字段的追问问题 (验收 F: 明确追问, 不静默)。"""
        if not self._product_pending:
            return ""
        field = self._product_pending[0]
        question = FIELD_QUESTIONS.get(field, f"请补充: {field}")
        return f"{question} (缺失字段: {field})"

    def _guide_message(self, body: str, *, current: str = "发现") -> str:
        """发现阶段消息前缀: 生命周期行 + 必填进度 (S10-101, 确定性, 无 LLM 也显示)。

        current: 当前生命周期阶段 — 发现/确认 (确认门消息用 "确认")。
        """
        required = _PRODUCT_FIELD_ORDER
        filled = [f for f in required if self._product_field_filled(f)]
        pending = [f for f in required if not self._product_field_filled(f)]
        return (
            lifecycle_line(current) + "\n"
            + format_progress(filled, pending) + "\n"
            + str(body)
        )

    def _set_product_field(self, field: str, value: str) -> None:
        """填充产品字段: core_features 解析为列表; 其余原样赋值。

        批量回答去标签前缀 ("痛点：X" → "X"), 单字段回答不受影响。
        """
        value = _clean_field_answer(field, value)
        if field == "core_features":
            self.product_intent.core_features = parse_core_features(value)  # type: ignore[union-attr]
        else:
            setattr(self.product_intent, field, value)  # type: ignore[union-attr]

    def _enter_product_confirmation(self) -> ConversationResponse:
        """必填齐全 → 命名 → PRODUCT_CONFIRMATION: 产品摘要 + 确认询问 (验收 C [4])。

        S10-081 P0: 确认前生成产品名候选 (LLM 可用 → AI 建议; 否则
        deterministic 提取) — 消除 "未命名产品-<ts>" 作为最终产品名。
        """
        pi = self.product_intent  # type: ignore[union-attr]
        if pi is None:
            return self._clarify("请先描述你的产品想法")
        # 命名: 无名称 / 临时名 → 生成候选 (不覆盖用户已给的名字)
        from .naming import is_temp_name, suggest_names

        candidates: list[str] = []
        if not pi.name or is_temp_name(pi.name):
            # 真实 LLM 命名（S10-081 设计: LLM 可用 → AI 建议; 修复: 之前硬编码
            # llm_fn=None 导致永远走 deterministic 提取 — 模板化根因）
            try:
                from .reasoning import ReasoningProvider

                llm_fn = ReasoningProvider()._default_llm_fn()  # noqa: SLF001
            except Exception:  # noqa: BLE001 — 无 provider/key → 诚实回退 deterministic
                llm_fn = None
            try:
                candidates = suggest_names(
                    getattr(pi, "raw", "") or pi.problem or "",
                    llm_fn=llm_fn,
                    limit=3,
                )
            except Exception:  # noqa: BLE001 — 命名失败 → 保留原逻辑 (极兜底)
                candidates = []
            if candidates:
                pi.name = candidates[0]
        self.transition(ConversationState.PRODUCT_CONFIRMATION)
        summary = pi.to_summary()
        # 展示候选列表 (S10-082: 多候选选择)
        lines = [summary, f"建议名称: {pi.name or '(未命名)'}"]
        if candidates:
            for idx, cand in enumerate(candidates, 1):
                lines.append(f"  {idx}. {cand}")
            lines.append("输入 1-3 选择候选, 或直接输入新名称, 或 y 确认")
        lines.append(_PRODUCT_CONFIRM_PROMPT)
        # S10-099: LLM 理解摘要 + 主动分析 (仅 LLM 真产出时 — ai_generated 诚实
        # 标注; 未用 LLM → 现有消息逐字节不变, 验收 4)
        analysis = self._discovery_analysis
        understanding: Optional[str] = None
        proactive: Optional[dict[str, Any]] = None
        ai_generated = False
        if analysis is not None:
            understanding = (
                str(getattr(analysis, "understanding", "") or "").strip() or None
            )
            proactive = dict(getattr(analysis, "proactive", None) or {}) or None
            ai_generated = True
            if understanding:
                lines.insert(0, understanding)
            proactive_line = self._format_proactive_line(proactive)
            if proactive_line:
                lines.append(proactive_line)
        return ConversationResponse(
            state=self.state,
            message=self._guide_message("\n".join(lines), current="确认"),
            needs_input=True,
            understanding=understanding,
            proactive=proactive,
            ai_generated=ai_generated,
        )

    def handle_product_answer(self, text: str) -> ConversationResponse:
        """产品发现多轮回答: 控制短语优先 (取消/整理需求/逃生/批量问题 — 非答案);
        否则填充当前缺失字段 → 还有缺失 → 追问下一个; 全部补齐 →
        PRODUCT_CONFIRMATION + 摘要 + 确认询问。

        多部分回答 (分号/换行分隔) 且多个字段待填 → 按顺序一次填充多个字段
        (批量友好); 单字段待填 → 原样进入该字段解析 (core_features 顿号分隔不受影响)。

        空回答 → 明确要求补充 (不静默跳过, 验收 F)。
        """
        if self.product_intent is None:
            return self._clarify("请先描述你的产品想法 (例如: '我想开发一个台球计分APP')")
        raw = (text or "").strip()
        if not raw:
            return ConversationResponse(
                state=self.state,
                message=self._guide_message("回答不能为空 — 请补充当前缺失字段"),
                needs_input=True,
            )
        # 控制短语优先 (非答案 — 取消/整理需求/逃生到其它意图/批量问题)
        control = self._product_control(raw)
        if control is not None:
            return control
        # S10-103: 命令分流 (slash → passthrough; exit/quit → exit_requested) —
        # 在字段收集之前 ("退出" 已被 _product_control 处理为取消, 不走到这里)
        cmd = self._command_escape(raw)
        if cmd is not None:
            return cmd
        # S10-104: 删除/清空指令 (字段收集期"清空X" → 重问当前字段; 绝不当字段答案)
        del_field = _parse_delete_command(raw)
        if del_field is not None:
            return self._apply_delete_command(del_field)
        # S10-10x: 发现阶段"确认+动作"短语 ("可以，先出prd文档"/"先出PRD"/"出份功能清单")
        # → 产品定义不完整 → 明确提示缺失 (不当字段回答/不盲目创建;
        #   防 create_product 缺失失败 与 generate_prd 扫描兜底写错项目)
        action_id = match_direct_action(raw) or match_approve_next(raw)
        if action_id:
            pending = list(self._product_pending or [])
            if pending:
                label = _NEXT_ACTION_LABELS.get(action_id, "该产出")
                miss = "、".join(
                    (_BATCH_QUESTIONS.get(f) or f).split("?")[0].split(" (")[0]
                    for f in pending
                )
                return ConversationResponse(
                    state=self.state,
                    message=self._guide_message(
                        f"产品定义还不完整，还缺 {miss} — 补齐后才能生成{label}。"
                        "请先回答当前问题。"
                    ),
                    needs_input=True,
                )
            # 必填已齐 (异常状态) → 回确认
            return self._enter_product_confirmation()
        # S10-101: 求助提案挂起 → 处理选择 (y 全填 / 1-3 单选 / 自定义) —
        # 绝不当字段内容收下 (验收 6)
        if self._suggestion_proposal:
            return self._handle_suggestion_choice(raw)
        # S10-101: 求助关键词确定性硬闸 (LLM 前) — 命中 → 当前缺失字段默认建议
        if self._is_help_request(raw):
            offer = self._offer_suggestions()
            if offer is not None:
                return offer
        # 批量模式下 "是否补充? → 是/好" → 重新展示剩余问题 (逐条回答)
        if self._product_batch_mode and _strip_tail_punct(raw) in _PRODUCT_SUPPLEMENT_ANSWERS:
            return ConversationResponse(
                state=self.state,
                message=self._guide_message(self._batch_questions_message()),
                needs_input=True,
            )
        # S10-099: 确定性硬闸未命中且 LLM 可用 → 意图理解分流
        # (control→既有控制行为 / query→逃生 / help_request→建议展示 /
        #  product_description→提取合并 / field_answer→填当前字段+智能下一问;
        #  LLM 不可用/失败 → 现有逻辑不变)
        analysis = self._analyze_discovery(raw, history=self._discovery_history(raw))
        if analysis is not None:
            handled = self._handle_llm_analysis(analysis, raw)
            if handled is not None:
                return handled
        if not self._product_pending:
            # 防御: 必填已齐全 (状态异常) → 回到确认
            return self._enter_product_confirmation()
        # 多部分回答 → 按顺序填充多个字段 (批量友好; 单字段待填不切分)
        parts = _split_product_answers(raw)
        if len(parts) > 1 and len(self._product_pending) > 1:
            for part in parts:
                if not self._product_pending:
                    break
                field = self._product_pending[0]
                self._set_product_field(field, part)
                self._product_pending = self._product_pending[1:]
            if self._product_pending:
                return ConversationResponse(
                    state=self.state,
                    message=self._guide_message(self._pending_question_message()),
                    needs_input=True,
                )
            return self._enter_product_confirmation()
        field = _resolve_answer_field(raw, self._product_pending)
        if field is None:
            # S10-109: 确认词不当字段值 (机械路径, 无 LLM 同生效) → 不填 + 提示缺字段
            current = self._product_pending[0]
            label = FIELD_LABELS.get(current, current)
            return ConversationResponse(
                state=self.state,
                message=self._guide_message(
                    f"产品定义还不完整, 还缺 {label}, 请先补充"
                ),
                needs_input=True,
            )
        self._set_product_field(field, raw)
        self._product_pending = [f for f in self._product_pending if f != field]
        if self._product_pending:
            # 还有缺失 → 追问下一个 (验收 C: 缺 problem → 追问; 补齐 → 追问 user)
            return ConversationResponse(
                state=self.state,
                message=self._guide_message(self._pending_question_message()),
                needs_input=True,
            )
        return self._enter_product_confirmation()

    # -------------------------------------------------- S10-099: 发现阶段 LLM 分流

    def _analyze_discovery(self, text: str, *, history=None):
        """LLM 可用 → analyze; 不可用/失败 → None (规则兜底, 诚实降级, 不伪造)。"""
        analyzer = self._get_discovery_analyzer()
        if analyzer is None:
            return None
        try:
            return analyzer.analyze(
                text, history=history,
                system_question=self._last_system_question,
            )
        except Exception:  # noqa: BLE001 — LLM 失败 → 规则兜底 (永不 5xx)
            return None

    def _get_discovery_analyzer(self):
        """发现 LLM 分析器 (懒装配 + 缓存; 显式 None → 禁用)。

        装配失败 (无 provider/key) → None → 现有状态机逐字节不变 (验收 3)。
        """
        if self._discovery_analyzer is not _DISCOVERY_ANALYZER_UNSET:
            return self._discovery_analyzer
        if self._discovery_analyzer_override is not _DISCOVERY_ANALYZER_UNSET:
            self._discovery_analyzer = self._discovery_analyzer_override
        else:
            try:
                from .discovery_intelligence import DiscoveryIntentAnalyzer

                self._discovery_analyzer = DiscoveryIntentAnalyzer()
            except Exception:  # noqa: BLE001 — 无 key/provider → 规则兜底
                self._discovery_analyzer = None
        return self._discovery_analyzer

    def _discovery_history(self, current: str) -> list[str]:
        """最近对话轮次 (不含当前输入 — 供 LLM 上下文, prompt 内单独给最新输入)。"""
        lines: list[str] = []
        for entry in reversed(self.history):
            if entry.get("event") != "input":
                continue
            text = str(entry.get("text") or "").strip()
            if text and text != current:
                lines.append(text)
                if len(lines) >= 3:
                    break
        return list(reversed(lines))

    def _handle_llm_analysis(
        self, analysis, text: str
    ) -> Optional[ConversationResponse]:
        """LLM 意图分流 (确定性硬闸未命中后; 计划 §3.1/§3.2)。

        - control → 映射既有控制行为 (取消/整理/逃生 — 模糊改写补充网)
        - query → 逃生 (交回宿主按普通意图链)
        - help_request → 建议展示 + 挂起 proposal (S10-101)
        - product_description → 结构化提取合并 (直入确认 / 智能追问)
        - field_answer → 填当前字段 + 下一问智能/机械 (S10-101 中间字段 LLM 化)
        """
        category = str(getattr(analysis, "category", "") or "")
        if category == "control":
            return self._apply_llm_control(analysis, text)
        if category == "query":
            return self._escape_product_flow(text)
        if category == "help_request":
            return self._apply_help_request(analysis)
        if category == "product_description":
            return self._apply_product_extraction(analysis)
        if category == "field_answer":
            return self._apply_field_answer(analysis, text)
        return None

    def _apply_llm_control(self, analysis, text: str) -> ConversationResponse:
        """LLM category=control → 映射既有控制行为 (验收 2: 模糊改写不被当字段)。

        确定性硬闸已先跑 (未命中) — 这里只处理 "整理一下" 类模糊改写;
        取消类关键词 → 取消; 整理类关键词 → 整理不创建; 其余 → 逃生 (交回宿主)。
        """
        norm = _strip_tail_punct(text)
        if any(keyword in norm for keyword in _LLM_CANCEL_KEYWORDS):
            return self._cancel_product_discovery()
        if any(keyword in norm for keyword in _LLM_SUMMARY_KEYWORDS):
            return self._summarize_product_only()
        return self._escape_product_flow(text)

    def _apply_product_extraction(self, analysis) -> ConversationResponse:
        """LLM 结构化提取合并 (计划 §3.1/§3.2): 只填缺失字段, pending 只留真正缺失。

        - 必填齐 → 直入确认 (LLM 理解摘要 + 主动分析展示, ai_generated 标记)
        - 仍缺 → 智能追问 (最重要 1 条, 带为什么缺)
        """
        self._apply_extraction_to_intent(analysis.extraction or {})
        self._product_pending = [
            field
            for field in _PRODUCT_FIELD_ORDER
            if not self._product_field_filled(field)
        ]
        self._discovery_analysis = analysis
        if not self._product_pending:
            return self._enter_product_confirmation()
        return self._smart_question_response(analysis)

    def _apply_extraction_to_intent(self, extraction: dict) -> None:
        """把 LLM 提取结果并入 ProductIntent (只填非空且未填字段 — 不覆盖用户已给)。"""
        pi = self.product_intent  # type: ignore[union-attr]
        if pi is None:
            return
        from .naming import is_temp_name

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

    def _product_field_filled(self, field: str) -> bool:
        """字段是否有值 (与 ProductIntent._has_value 同口径: core_features 非空列表)。"""
        pi = self.product_intent  # type: ignore[union-attr]
        if pi is None:
            return False
        value = getattr(pi, field, None)
        if field == "core_features":
            return bool(value)
        return value not in (None, "")

    def _smart_question_response(self, analysis) -> ConversationResponse:
        """智能追问: 只问最重要 1 条 (LLM 产出), 带为什么缺 (missing_reasons 话术)。

        无 LLM 追问内容 → 机械追问兜底 (现有 _next_product_question, 逐字节不变)。
        """
        question = ""
        for q in (analysis.smart_questions or []):
            if str(q or "").strip():
                question = str(q).strip()
                break
        if not question:
            q = self._next_product_question()
            self._last_system_question = q  # 记录机械追问 (LLM 多轮合并边界)
            return ConversationResponse(
                state=self.state,
                message=self._guide_message(q),
                needs_input=True,
            )
        missing = self._product_pending[0] if self._product_pending else ""
        reason = str((analysis.missing_reasons or {}).get(missing) or "").strip()
        message = question
        if reason:
            message = f"{question}\n(为什么还问: {reason})"
        self._last_system_question = question  # 记录追问 (LLM 多轮合并边界)
        return ConversationResponse(
            state=self.state,
            message=self._guide_message(message),
            needs_input=True,
            ai_generated=True,
        )

    # -------------------------------------------------- S10-101: 中间字段 LLM 化 + 求助流

    def _smart_question_text(self, analysis) -> Optional[str]:
        """LLM 智能追问文本 (smart_questions[0] 裸问题); 无 → None。

        供 field_answer 之后的下一问 (中间字段 LLM 化契约): 空/失败 → 机械模板。
        理由由调用方按 missing_reasons 拼接 (与 _smart_question_response 同口径)。
        """
        for q in (analysis.smart_questions or []):
            if str(q or "").strip():
                return str(q).strip()
        return None

    def _apply_field_answer(self, analysis, text: str) -> ConversationResponse:
        """field_answer → 填当前字段 → 下一问优先 LLM smart_questions[0] (带理由);
        空/失败 → 机械模板 (诚实降级, 验收 "无 LLM 机械追问保留")。

        S10-109: 字段归属先经 _resolve_answer_field 确定性判定 — 答非所问归类到
        匹配字段 (未填才填) / 确认词不当字段值 (不填+提示缺字段); 不依赖 LLM。

        批量模式 → 剩余问题编号列表 (用户已要求一次看完, 智能单问不打断)。
        """
        if not self._product_pending:
            return self._enter_product_confirmation()  # 防御: 队列空 → 确认
        field = _resolve_answer_field(text, self._product_pending)
        if field is None:
            # S10-109: 确认词不当字段值 → 不填, 提示缺字段 (state 保持 DISCOVERY,
            # pending 不推进; 无 LLM 规则同样生效)
            current = self._product_pending[0]
            label = FIELD_LABELS.get(current, current)
            return ConversationResponse(
                state=self.state,
                message=self._guide_message(
                    f"产品定义还不完整, 还缺 {label}, 请先补充"
                ),
                needs_input=True,
            )
        self._set_product_field(field, text)
        self._product_pending = [f for f in self._product_pending if f != field]
        if not self._product_pending:
            return self._enter_product_confirmation()
        if self._product_batch_mode:
            message = self._pending_question_message()
            self._last_system_question = message
            return ConversationResponse(
                state=self.state,
                message=self._guide_message(message),
                needs_input=True,
            )
        smart = self._smart_question_text(analysis)
        if smart is not None:
            missing = self._product_pending[0] if self._product_pending else ""
            reason = str((analysis.missing_reasons or {}).get(missing) or "").strip()
            message = smart
            if reason:
                message = f"{smart}\n(为什么还问: {reason})"
            self._last_system_question = smart  # 只记裸问题 (LLM 多轮合并边界)
            return ConversationResponse(
                state=self.state,
                message=self._guide_message(message),
                needs_input=True,
                ai_generated=True,
            )
        message = self._pending_question_message()
        self._last_system_question = message
        return ConversationResponse(
            state=self.state,
            message=self._guide_message(message),
            needs_input=True,
        )

    @staticmethod
    def _is_help_request(text: str) -> bool:
        """求助关键词确定性硬闸 (S10-101/102): normalize 后子串匹配。

        normalize_help_text 去全部空白 — "没 想法"→"没想法" 命中 (口语变体
        全覆盖, 两路径同步; 命中 → 触发求助流, LLM 前先查)。
        """
        norm = normalize_help_text(text)
        return any(keyword in norm for keyword in HELP_KEYWORDS)

    def _offer_suggestions(self) -> Optional[ConversationResponse]:
        """求助关键词兜底 (无 LLM): 当前缺失字段 → DEFAULT_SUGGESTIONS → 挂起 proposal。

        无缺失字段 / 无默认建议 → None (交回 LLM/普通逻辑 — 正常输入零影响)。
        """
        if not self._product_pending:
            return None
        field = self._product_pending[0]
        items = list(DEFAULT_SUGGESTIONS.get(field, []))
        if not items:
            return None
        return self._suggestions_response(field, items, note="")

    def _apply_help_request(self, analysis) -> Optional[ConversationResponse]:
        """LLM category=help_request → suggestions 展示 + 挂起 proposal。

        LLM 没给 suggestions/items → DEFAULT_SUGGESTIONS 兜底 (诚实降级);
        仍无 → None (交回普通逻辑)。
        """
        if not self._product_pending:
            return None
        suggestions = dict(getattr(analysis, "suggestions", None) or {})
        field = str(suggestions.get("field") or "").strip()
        if field not in self._product_pending:
            field = self._product_pending[0]
        items = [
            str(item).strip()
            for item in (suggestions.get("items") or [])
            if str(item or "").strip()
        ]
        note = str(suggestions.get("note") or "").strip()
        if not items:
            items = list(DEFAULT_SUGGESTIONS.get(field, []))
        if not items:
            return None
        return self._suggestions_response(field, items, note=note)

    def _suggestions_response(
        self, field: str, items: list[str], *, note: str = ""
    ) -> ConversationResponse:
        """展示建议 + 挂起 proposal: 用户 y 全填 / 1-3 单选 / 自定义填入。

        求助输入绝不当字段内容收下 (验收 6) — 展示后等用户确认。
        """
        label = FIELD_LABELS.get(field, field)
        self._suggestion_proposal = {"field": field, "items": list(items)}
        lines = [f"当前缺{label} — 建议方向:"]
        for idx, item in enumerate(items, 1):
            lines.append(f"  {idx}. {item}")
        if note:
            lines.append(f"({note})")
        lines.append("(输入 y 用全部建议 / 1-3 选择 / 直接输入自定义)")
        return ConversationResponse(
            state=self.state,
            message=self._guide_message("\n".join(lines)),
            needs_input=True,
        )

    def _handle_suggestion_choice(self, text: str) -> ConversationResponse:
        """处理建议选择: y/yes → 全部填入; 1-3 → 单选; 其它 → 自定义填入。

        填入后: 更新进度 → 继续追问/确认 (S10-101 求助确认填入契约)。
        """
        proposal = self._suggestion_proposal or {}
        field = str(proposal.get("field") or "")
        items = [str(i) for i in (proposal.get("items") or [])]
        self._suggestion_proposal = None
        norm = _strip_tail_punct(text)
        if norm in ("y", "yes"):
            value = "、".join(items) if items else text
        elif items and norm in tuple(str(i) for i in range(1, len(items) + 1)):
            value = items[int(norm) - 1]
        else:
            value = text  # 自定义 (原样填入, 非空已由上层保证)
        self._set_product_field(field, value)
        if field in self._product_pending:
            self._product_pending.remove(field)
        if self._product_pending:
            return ConversationResponse(
                state=self.state,
                message=self._guide_message(self._pending_question_message()),
                needs_input=True,
            )
        return self._enter_product_confirmation()

    def _format_proactive_line(self, proactive: Optional[dict]) -> str:
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

    # -------------------------------------------------- 产品流程控制短语 (非答案)

    def _command_escape(self, text: str) -> Optional[ConversationResponse]:
        """命令分流 (S10-103): slash → passthrough; exit/quit → exit_requested。

        确定性 (不依赖 LLM); 与控制指令并列, 在字段收集之前:
        - "/status" → passthrough=True (宿主重分发到命令注册表, 不当字段)
        - exit/quit/退出会话/再见/拜拜/结束 → exit_requested=True (宿主优雅退出)
        - 其余 → None (正常字段/控制短语处理)
        注意: "退出" 在 _PRODUCT_CANCEL_PHRASES (取消发现) 与 EXIT_COMMANDS 交集 —
        调用方须先走 _product_control → "退出" 仍 = 取消发现 (向后兼容)。
        """
        norm = str(text or "").strip()
        if norm.startswith("/"):
            return ConversationResponse(
                state=self.state, message="", needs_input=True, passthrough=True
            )
        if norm in EXIT_COMMANDS:
            return ConversationResponse(
                state=self.state, message="", needs_input=False, exit_requested=True
            )
        return None

    def _product_control(self, text: str) -> Optional[ConversationResponse]:
        """产品流程中的控制短语检测 (非字段答案 — 回答阶段/确认阶段共用)。

        优先级: 取消 → 需求整理 (不创建) → 逃生 (其它意图交回宿主) → 批量问题。
        仅匹配显式命令短语 (精确/前缀), 不误吞正常字段回答。
        """
        norm = _strip_tail_punct(text)
        if norm in _PRODUCT_CANCEL_PHRASES:
            return self._cancel_product_discovery()
        if any(norm.startswith(phrase) for phrase in _sorted_by_len_desc(_PRODUCT_SUMMARY_PHRASES)):
            return self._summarize_product_only()
        # 修改指令 ("把用户改成X" / "修改一下，功能改成X") — 更新已有信息
        edit = _parse_edit_command(text)
        if edit is not None:
            return self._apply_edit_command(*edit)
        # "现在创建" 家族: 精确 (无名称) → 引导补齐; 带名称 → 逃生到 create_project
        # (最长短语优先匹配, 避免 "现在创建" 抢 "现在创建项目")
        for phrase in _sorted_by_len_desc(_PRODUCT_CREATE_NOW_PHRASES):
            if norm.startswith(phrase):
                if len(norm) > len(phrase):
                    return self._escape_product_flow(text)
                return self._create_now_with_incomplete()
        if norm in _PRODUCT_ESCAPE_PHRASES:
            return self._escape_product_flow(text)
        if any(norm.startswith(phrase) for phrase in _sorted_by_len_desc(_PRODUCT_BATCH_PHRASES)):
            return self._enter_product_batch_mode()
        return None

    def _reset_product_flow(self) -> None:
        """清空产品流程 (product_intent / pending / 批量模式) → 回 DISCOVERY。"""
        self.product_intent = None
        self._product_pending = []
        self._product_batch_mode = False
        self._discovery_analysis = None  # S10-099: LLM 理解随流程一并清空
        self._suggestion_proposal = None  # S10-101: 求助提案随流程一并清空
        self.pending_intent = None
        if self.state != ConversationState.DISCOVERY:
            self.transition(ConversationState.DISCOVERY)

    def _cancel_product_discovery(self) -> ConversationResponse:
        """取消当前产品发现 (回答阶段/确认阶段共用) → 重置 DISCOVERY。"""
        if self.product_intent is None:
            return self._clarify("当前没有进行中的产品流程 — 请描述你的产品想法")
        cancelled = self.product_intent.name or "(未命名产品)"  # type: ignore[union-attr]
        self._reset_product_flow()
        return ConversationResponse(
            state=self.state,
            message=(
                f"已取消产品发现 ({cancelled}) — 请描述你的产品想法, "
                "或使用其它命令 (如 '项目列表' / '创建项目')"
            ),
            needs_input=True,
        )

    def _summarize_product_only(self) -> ConversationResponse:
        """只整理需求, 不创建项目: 输出已收集字段摘要 → 重置产品流程。

        直接回应 "先帮我整理需求, 不要创建项目" 类输入 — 不再把命令当字段答案,
        也绝不进入创建流程。
        """
        if self.product_intent is None:
            return self._clarify("请先描述你的产品想法 (例如: '我想开发一个台球计分APP')")
        summary = self.product_intent.to_summary()  # type: ignore[union-attr]
        snapshot = self.product_intent.to_dict()  # type: ignore[union-attr]
        self._reset_product_flow()
        return ConversationResponse(
            state=self.state,
            message=(
                "已按你的要求整理需求 — 未创建任何项目。\n"
                f"{summary}\n"
                "以上为需求整理结果 (已生成 discovery 需求资产); 需要继续补充或创建项目时告诉我 (例如: '创建项目')。"
            ),
            needs_input=True,
            summary_only=True,
            product_snapshot=snapshot,
        )

    def _apply_edit_command(self, field: str, value: str) -> ConversationResponse:
        """应用修改指令: 更新指定字段 → 还有追问则继续, 否则回确认。

        field 为空 → 默认当前待填字段; 已全部填齐但未指明字段 → 引导指明修改项。
        """
        if self.product_intent is None:
            return self._clarify("请先描述你的产品想法 (例如: '我想开发一个台球计分APP')")
        pi = self.product_intent  # type: ignore[union-attr]
        if not field:
            if self._product_pending:
                field = self._product_pending[0]
            else:
                return ConversationResponse(
                    state=self.state,
                    message=(
                        "想修改哪一项? 例如:\n"
                        "  '把目标用户改成创业公司'\n"
                        "  '把核心功能改成客户档案、跟进'\n"
                        f"当前需求:\n{pi.to_summary()}"
                    ),
                    needs_input=True,
                )
        self._set_product_field(field, value)
        self._suggestion_proposal = None  # 编辑已应用 → 求助提案作废 (不残留)
        if field in self._product_pending:
            self._product_pending.remove(field)
        if self._product_pending:
            label = FIELD_LABELS.get(field, field)
            return ConversationResponse(
                state=self.state,
                message=self._guide_message(
                    f"已更新{label}。\n{self._pending_question_message()}"
                ),
                needs_input=True,
            )
        return self._enter_product_confirmation()

    def _apply_delete_command(self, field: str) -> ConversationResponse:
        """应用删除/清空指令 (S10-104): 字段有值 → 清空 (core_features → []; 其余 → "")。

        必填字段 → 迁移 DISCOVERY + pending 首置该字段 + 追问该字段;
        可选字段/必填已齐 → 重进确认 (_enter_product_confirmation, 摘要更新)。
        绝不当改名 — 删除只清字段, 不碰名称语义。
        """
        if self.product_intent is None:
            return self._clarify("请先描述你的产品想法 (例如: '我想开发一个台球计分APP')")
        pi = self.product_intent  # type: ignore[union-attr]
        if self._product_field_filled(field):
            if field == "core_features":
                pi.core_features = []
            else:
                setattr(pi, field, "")
        self._suggestion_proposal = None  # 删除已应用 → 求助提案作废 (不残留)
        label = FIELD_LABELS.get(field, field)
        if field in _PRODUCT_FIELD_ORDER:
            # 必填字段 → 迁移 DISCOVERY + 追问该字段 (其余已填字段保留)
            self._product_batch_mode = False
            self._product_pending = [field] + [
                f
                for f in _PRODUCT_FIELD_ORDER
                if f != field and not self._product_field_filled(f)
            ]
            if self.state != ConversationState.DISCOVERY:
                self.transition(ConversationState.DISCOVERY)
            return ConversationResponse(
                state=self.state,
                message=self._guide_message(
                    f"已清空{label}。\n{self._next_product_question()}"
                ),
                needs_input=True,
            )
        # 可选字段 (name/platform): 必填已齐 → 重进确认; 字段收集期 → 重问当前缺失
        if not self._product_pending:
            return self._enter_product_confirmation()
        return ConversationResponse(
            state=self.state,
            message=self._guide_message(
                f"已清空{label}。\n{self._pending_question_message()}"
            ),
            needs_input=True,
        )

    def _escape_product_flow(self, text: str) -> ConversationResponse:
        """逃生: 用户输入其它意图 (项目列表/创建项目/当前项目) → 产品流程让位,
        原输入交回宿主按普通意图链处理 (passthrough=True, 不再当字段答案)。"""
        self._reset_product_flow()
        return ConversationResponse(
            state=self.state,
            message="",
            needs_input=True,
            passthrough=True,
        )

    def _enter_product_batch_mode(self) -> ConversationResponse:
        """批量问题模式: 用户嫌问题多 → 一次性列出剩余必填问题 (编号), 可逐条
        回答或分号一次写完 (multi-part 填充由 handle_product_answer 支持)。"""
        if self.product_intent is None:
            return self._clarify("请先描述你的产品想法 (例如: '我想开发一个台球计分APP')")
        if not self._product_pending:
            return self._enter_product_confirmation()
        self._product_batch_mode = True
        return ConversationResponse(
            state=self.state,
            message=self._guide_message(self._batch_questions_message()),
            needs_input=True,
        )

    def _create_now_with_incomplete(self) -> ConversationResponse:
        """'创建项目/现在创建' 但必填未齐 → 不能直接创建: 列出还缺字段并询问是否补充
        (批量模式), 避免把裸 '创建项目' 解析成名为 '项目' 的空项目。"""
        if self.product_intent is None:
            return self._clarify("请先描述你的产品想法 (例如: '我想开发一个台球计分APP')")
        if not self._product_pending:
            return self._enter_product_confirmation()
        self._product_batch_mode = True
        missing_lines = "\n".join(
            f"  - {FIELD_LABELS.get(field, field)}" for field in self._product_pending
        )
        return ConversationResponse(
            state=self.state,
            message=self._guide_message(
                f"可以创建，不过还缺少:\n{missing_lines}\n\n"
                "是否补充? 直接回答即可 (可一次写完: 用户:...; 功能:...)"
            ),
            needs_input=True,
        )

    def _pending_question_message(self) -> str:
        """下一个追问: 批量模式 → 剩余问题编号列表; 否则单字段问题 (验收 C/F)。"""
        if self._product_batch_mode:
            return self._batch_questions_message()
        return self._next_product_question()

    def _batch_questions_message(self) -> str:
        """剩余必填问题编号列表 (批量模式提示/推进共用)。"""
        lines = ["剩余需求 (可逐条回答, 或用分号一次写完):"]
        for idx, field in enumerate(self._product_pending, 1):
            question = _BATCH_QUESTIONS.get(field) or FIELD_QUESTIONS.get(field, field)
            lines.append(f"  {idx}. {question}")
        return "\n".join(lines)

    def handle_product_confirm(
        self,
        answer: str,
        confirm_fn: Optional[Callable[[ProductIntent], str]] = None,
    ) -> ConversationResponse:
        """S10-102 + S10-104 确认阶段智能分流 (确定性表 → LLM → 改名兜底)。

        顺序 (计划 §1.3 + S10-104 §1.1/§1.3):
        1. 控制短语 (_product_control — 取消/整理/逃生/修改指令) — 最前, 不变
        2. "创建项目/现在创建" → 等价 y — 不变
        3. 确定性分流 (无 LLM 全覆盖):
           a. 明确改名 (RENAME_RE) → 设名 → 重新确认 (S10-081 行为不变,
              最优先防 "改名叫prd" 被动作规则抢)
           a'. 直接动作请求 (DIRECT_ACTION — "产出份prd文档"/"生成PRD"/
              "出个html"/"出份功能清单") → approved + next_action
              (无确认前缀 = 隐含确认; 名称不被覆盖)
           b. 确认+下一步 ("可以，先出prd文档") → approved + next_action (名称不被覆盖!)
           c. 纯确认 (可以/好/行/y/yes…) → approved (不再当名称)
           d. 澄清 (？/为什么/什么意思/能改吗…) → _clarify_confirmation (不改名不确认)
           d'. 删除/清空指令 ("把核心功能删掉"/"清空目标用户") → 字段清空 →
              重确认/追问 (绝不当改名)
           e. 取消 (n/no/取消/算了/不要/空) → 重置 DISCOVERY (验收 E)
           f. 委托 (随便/你定/你看吧…) → approved (保持当前名称)
        4. 确定性未决 且 LLM 可用 → analyze_confirmation → 按 category 路由
           (other → 改名兜底)
        5. 兜底 (无 LLM/失败): 裸文本 → 改名 (S10-081 兼容: "墨笺" 行为不变)

        confirm_fn: 宿主注入的执行回调 (接收 ProductIntent → 返回展示消息;
        conversation 零依赖, 不直接调 Action)。缺省 → 停留在 PROJECT_CREATION
        (返回信号, 由宿主执行创建)。
        """
        if self.product_intent is None:
            return self._clarify("当前没有进行中的产品流程 — 请描述你的产品想法")
        # 确认阶段 "创建项目/现在创建" → 等价 y (用户已确认, 直接创建)
        if _strip_tail_punct(answer) in _PRODUCT_CREATE_NOW_PHRASES:
            answer = "y"
        # 控制短语优先 (取消/需求整理/逃生/修改指令 — 非改名, 非字段答案)
        control = self._product_control(answer)
        if control is not None:
            return control
        # S10-103: 命令分流 (slash → passthrough; exit/quit → exit_requested) —
        # 在改名/确认分流之前 ("退出" 已被 _product_control 处理为取消, 不走到这里)
        cmd = self._command_escape(answer)
        if cmd is not None:
            return cmd
        raw = (answer or "").strip()
        # 3a. 明确改名命令 ("改名叫墨笺" → rename, S10-081 行为不变;
        # 最优先防 "改名叫prd" 被动作规则抢)
        rename_to = match_rename(raw)
        if rename_to:
            self.product_intent.name = rename_to  # type: ignore[union-attr]
            return self._enter_product_confirmation()
        # 3a'. S10-104: 直接动作请求 ("产出份prd文档"/"生成PRD"/"出个html"/
        # "出份功能清单") → approved + next_action (无确认前缀 = 隐含确认+下一步;
        # 名称不被覆盖)
        action_id = match_direct_action(raw)
        if action_id:
            return self._approve_product_confirm(
                next_action=action_id, confirm_fn=confirm_fn
            )
        # 3b. 确认+下一步 ("可以，先出prd文档" → approved + next_action, 名称不被覆盖)
        next_action = match_approve_next(raw)
        if next_action:
            return self._approve_product_confirm(
                next_action=next_action, confirm_fn=confirm_fn
            )
        # 3c. 纯确认 ("可以"/"好"/"行"/y/yes → approved, 不再当名称)
        if match_approve(raw):
            return self._approve_product_confirm(confirm_fn=confirm_fn)
        # 3d. 澄清/问号请求 ("？"/"为什么"/"能改吗" → 重展示摘要, 不改名不确认)
        if match_clarify(raw):
            return self._clarify_confirmation()
        # 3d'. S10-104: 删除/清空指令 ("把核心功能删掉"/"清空目标用户") —
        # 字段清空 → 重确认/追问, 绝不当改名
        del_field = _parse_delete_command(raw)
        if del_field is not None:
            return self._apply_delete_command(del_field)
        # 3e. 取消 (n/no/取消/算了/不要/空 — 验收 E, 行为不变)
        if not raw or raw.lower() in _CANCEL_ANSWERS:
            cancelled = self.product_intent.name or "(未命名产品)"  # type: ignore[union-attr]
            self._reset_product_flow()
            return ConversationResponse(
                state=self.state,
                message=f"已取消产品 {cancelled} — 重新开始产品发现, 请描述你的产品想法",
                needs_input=True,
            )
        # 3f. 委托 ("随便"/"你定" → approved, 保持当前名称)
        if match_delegate(raw):
            return self._approve_product_confirm(confirm_fn=confirm_fn)
        # 4. LLM 分类 (确定性未决 且 LLM 可用 → analyze_confirmation → 按 category 路由)
        llm = self._analyze_confirmation(raw)
        if llm is not None:
            if llm.category in ("approve", "approve_next"):
                return self._approve_product_confirm(
                    next_action=llm.next_action or None, confirm_fn=confirm_fn
                )
            if llm.category == "rename":
                if llm.rename_to:
                    self.product_intent.name = llm.rename_to  # type: ignore[union-attr]
                return self._enter_product_confirmation()
            if llm.category == "clarify":
                return self._clarify_confirmation()
            if llm.category == "cancel":
                cancelled = self.product_intent.name or "(未命名产品)"  # type: ignore[union-attr]
                self._reset_product_flow()
                return ConversationResponse(
                    state=self.state,
                    message=f"已取消产品 {cancelled} — 重新开始产品发现, 请描述你的产品想法",
                    needs_input=True,
                )
            if llm.category == "delegate":
                return self._approve_product_confirm(confirm_fn=confirm_fn)
            # other → 改名兜底 (S10-081 兼容)
        # 5. 兜底 (无 LLM/失败): 裸文本 → 改名 (S10-081: "墨笺" 行为不变)
        self.product_intent.name = raw  # type: ignore[union-attr]
        return self._enter_product_confirmation()

    def _approve_product_confirm(
        self,
        *,
        next_action: Optional[str] = None,
        confirm_fn: Optional[Callable[[ProductIntent], str]] = None,
    ) -> ConversationResponse:
        """确认创建 (y/确认词/委托 — S10-102): 走 confirm_fn 创建 → DONE。

        approved + next_action → 响应携带 next_action (宿主创建成功后执行,
        如 next_action="prd" → generate_prd; feature_list/html/docs → 信号注释;
        develop/create 只传信号)。
        """
        self.transition(ConversationState.PROJECT_CREATION)
        if confirm_fn is None:
            return ConversationResponse(
                state=self.state,
                message="产品已确认 — 等待执行创建 (create_product: ProductIntent → Project)",
                needs_input=False,
                next_action=next_action,
            )
        try:
            message = confirm_fn(self.product_intent)
        except Exception as exc:  # noqa: BLE001 — 失败安全: 创建失败 → 重置, 明确错误
            product_name = self.product_intent.name or "(未命名产品)"
            self._reset_product_flow()
            return ConversationResponse(
                state=self.state,
                message=f"产品创建失败 ({product_name}): {exc} — 已重置, 请重新描述产品想法",
                needs_input=True,
            )
        self.transition(ConversationState.DONE)
        base = message or f"Product Created: {self.product_intent.name} — Ready for Engineering."
        # S10-051 P6 (验收 H): 产品创建成功后引导 "是否生成工程计划?" —
        # 指向 prepare_project 意图关键词 ('准备开发' / '生成工程计划')
        return ConversationResponse(
            state=self.state,
            message=f"{base}\n{_ENGINEERING_GUIDE}",
            needs_input=False,
            next_action=next_action,
        )

    def _clarify_confirmation(self) -> ConversationResponse:
        """确认阶段澄清 (S10-102): 问号/疑问 → 重展示摘要 + 解释选项。

        不改名不确认 — 用户输入 "？"/"为什么"/"能改吗" 等时说明当前状态与
        可选操作 (确认创建 / 改名 / 修改需求 / 取消), 等待明确选择。
        """
        pi = self.product_intent  # type: ignore[union-attr]
        summary = pi.to_summary() if pi is not None else ""
        lines = [
            summary,
            "你可以:",
            "  • 直接输入 y / 可以 / 好 确认创建",
            "  • 输入新名称改名 (例如: 改名叫墨笺)",
            "  • 输入修改指令调整需求 (例如: 把目标用户改成学生)",
            "  • 输入 取消 放弃本次创建",
        ]
        return ConversationResponse(
            state=self.state,
            message=self._guide_message("\n".join(lines), current="确认"),
            needs_input=True,
        )

    def _analyze_confirmation(self, text: str):
        """确认阶段 LLM 分类 (复用发现分析器; 不可用/失败 → None → 改名兜底)。

        产品摘要 = product_intent.to_summary() (当前名称候选随附);
        诚实降级: 无 LLM / 调用失败 → 返回 None, 不伪造分类。
        """
        analyzer = self._get_discovery_analyzer()
        if analyzer is None:
            return None
        try:
            summary = self.product_intent.to_summary() if self.product_intent else ""
            return analyzer.analyze_confirmation(text, product_summary=summary)
        except Exception:  # noqa: BLE001 — LLM 失败 → 改名兜底 (永不 5xx)
            return None

    def _clarify(self, message: str) -> ConversationResponse:
        """未识别/信息不足 → CLARIFICATION (等待用户输入)。"""
        self.transition(ConversationState.CLARIFICATION)
        return ConversationResponse(
            state=self.state, message=message, needs_input=True
        )

    def reset(self) -> None:
        """回到初始状态: DISCOVERY, 清空 pending_intent / product_intent 与 history (全新会话)。"""
        self.state = ConversationState.DISCOVERY
        self.pending_intent = None
        self.product_intent = None
        self._product_pending = []
        self._product_batch_mode = False
        self._discovery_analysis = None  # S10-099: 清空 LLM 理解 (全新会话)
        self._suggestion_proposal = None  # S10-101: 清空求助提案 (全新会话)
        self.history = []


# ---------------------------------------------------------------- 模块级工具 (控制短语)

def _sorted_by_len_desc(phrases) -> list[str]:
    """短语按长度降序 (最长优先匹配 — 避免短前缀抢长短语)。"""
    return sorted(phrases, key=len, reverse=True)


def _parse_edit_command(text: str) -> Optional[tuple[str, str]]:
    """解析修改指令 → (field, new_value); 非修改指令 → None。

    匹配: "把{field}改成{value}" / "{field}改为{value}" / "修改一下，{field}改成{value}"。
    无字段别名时必须带显式修改动词前缀 ("修改/改一下/更新..."), 避免误吞正常回答
    (如 "把客户管理从混乱改成有序" 作为痛点回答不会被当成编辑指令)。
    """
    norm = (text or "").strip()
    if not norm:
        return None
    pos, marker = _find_edit_marker(norm)
    if pos == -1:
        return None
    head = norm[:pos].strip()
    value = norm[pos + len(marker):].strip()
    if not value:
        return None
    field = _match_edit_field(head)
    if field is None and not norm.startswith(_EDIT_VERB_PREFIXES):
        return None
    return (field or "", value)


def _parse_delete_command(text: str) -> Optional[str]:
    """解析删除/清空指令 → 字段名 (problem/user/core_features/name/platform); 非删除指令 → None。

    匹配 (两序, 复用 _EDIT_FIELD_ALIASES 别名):
      (把|将)?(别名)(删除|删掉|清空|去掉|移除|不要)  — "把核心功能删掉" / "核心功能不要"
      (清空|删除|删掉|去掉|移除)(别名)             — "清空目标用户" / "删除核心功能"
    别名按 _EDIT_FIELD_ALIASES 顺序 (problem→user→core_features→name→platform);
    未命中 → None (正常字段回答/改名/确认 不受影响)。
    """
    norm = (text or "").strip()
    if not norm:
        return None
    for field, aliases in _EDIT_FIELD_ALIASES.items():
        for alias in aliases:
            for verb in _DELETE_VERBS:
                if f"{alias}{verb}" in norm:
                    return field
            for verb in _DELETE_VERBS_PREFIX:
                if f"{verb}{alias}" in norm:
                    return field
    return None


def _find_edit_marker(text: str) -> tuple[int, str]:
    """最早出现的修改标记位置 (("改成", "改为", ...) 中首个)。未找到 → (-1, "")。"""
    pos, marker = -1, ""
    for m in _EDIT_MARKERS:
        idx = text.find(m)
        if idx != -1 and (pos == -1 or idx < pos):
            pos, marker = idx, m
    return pos, marker


def _match_edit_field(head: str) -> Optional[str]:
    """在分隔符前文本中定位字段 (按别名包含匹配, 顺序: problem→user→features→name→platform)。"""
    for field, aliases in _EDIT_FIELD_ALIASES.items():
        for alias in aliases:
            if alias in head:
                return field
    return None


def _clean_field_answer(field: str, value: str) -> str:
    """批量回答清洗: 去 "痛点:/用户:/功能:" 等标签前缀 (仅当冒号前是字段别名)。"""
    text = (value or "").strip()
    if "：" not in text and ":" not in text:
        return text
    for sep in ("：", ":"):
        if sep in text:
            label, _, rest = text.partition(sep)
            label = label.strip()
            aliases = _FIELD_LABEL_ALIASES.get(field, ())
            if any(alias in label for alias in aliases):
                text = rest.strip()
            break
    return text


def _strip_tail_punct(text: str) -> str:
    """控制短语归一化: 去首尾空白 + 去尾部标点 (。！？!?；;，,、)."""
    return (text or "").strip().rstrip("。！？!?；;，,、 \t\n")


def _split_product_answers(text: str) -> list[str]:
    """多部分回答切分: 分号 (；;) 或换行 → 多段 (去空)。单段 → [原样]。"""
    parts = re.split(r"[；;]+|\n+", text)
    return [part.strip() for part in parts if part.strip()]

