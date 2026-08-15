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

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from .intent import (
    INTENT_CREATE_PRODUCT,
    INTENT_RUN_TASK,
    IntentObject,
    IntentParser,
    KeywordIntentParser,
)
from .product import (
    FIELD_QUESTIONS,
    ProductIntent,
    generate_temp_product_name,
    parse_core_features,
)

#: run_task 执行所需的定位参数 (project/task/task_id — 任一缺失 → 澄清)
_TASK_TARGET_KEYS = ("project", "task", "task_id")

#: 产品发现必填字段追问顺序 (设计 §2.3: problem → user → core_features)
_PRODUCT_FIELD_ORDER: tuple[str, ...] = ("problem", "user", "core_features")

#: 确认回答集合 (y/yes 不区分大小写; 其余 → 拒绝, 默认 No — 同 ConfirmationGate 口径)
_APPROVE_ANSWERS: frozenset[str] = frozenset({"y", "yes"})

#: 产品确认提示 (y/N 约定: 回车/其他 → 拒绝)
_PRODUCT_CONFIRM_PROMPT = "确认创建这个产品? (y/N)"


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
    """ConversationManager.handle() 的产出: 当前状态 + 给用户的消息 + 是否等待输入。"""

    state: ConversationState
    message: str = ""
    needs_input: bool = False


class ConversationManager:
    """会话状态机 (基础 flow) — 跟踪对话状态与待确认意图, 历史可审计。

    - state: 当前状态 (初始 DISCOVERY)
    - pending_intent: 识别成功后挂起的 Intent (等待确认/澄清)
    - history: 事件记录 ({"event": "input"|"transition", ...}) — 可审计
    - transition(new_state): 状态迁移 (非法枚举 → ValueError, 不静默)
    - handle(text, parser): 基础 flow — 识别 → CONFIRMATION; 未识别 → CLARIFICATION
    - reset(): 回到初始 DISCOVERY (清空 pending_intent / history)
    """

    def __init__(self, parser: Optional[IntentParser] = None) -> None:
        self.state = ConversationState.DISCOVERY
        self.pending_intent: Optional[IntentObject] = None
        self.history: list[dict[str, Any]] = []
        #: 默认解析器 (handle 未显式传 parser 时使用; 可注入定制/LLM 版)
        self._parser = parser if parser is not None else KeywordIntentParser()
        #: S10-050: 当前产品意图 (DISCOVERY 多轮追问产物; None = 无进行中的产品流程)
        self.product_intent: Optional[ProductIntent] = None
        #: 产品发现待追问字段队列 (按 _PRODUCT_FIELD_ORDER; 空 = 必填齐全)
        self._product_pending: list[str] = []

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
            # slash 命令由 SlashCommandRegistry 处理, 状态机不接管 (状态不变)
            return ConversationResponse(
                state=self.state,
                message="slash 命令由命令注册表处理, 不走会话状态机",
                needs_input=False,
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
        - 返回当前缺失字段的明确问题 (不静默)
        """
        self.product_intent = ProductIntent(
            name=generate_temp_product_name(),
            raw=(text or "").strip(),
            session_id=None,
        )
        self._product_pending = list(_PRODUCT_FIELD_ORDER)
        self.pending_intent = None  # 产品流程接管, 不挂起普通 intent
        if self.state != ConversationState.DISCOVERY:
            self.transition(ConversationState.DISCOVERY)
        return ConversationResponse(
            state=self.state,
            message=self._next_product_question(),
            needs_input=True,
        )

    def _next_product_question(self) -> str:
        """当前缺失字段的追问问题 (验收 F: 明确追问, 不静默)。"""
        if not self._product_pending:
            return ""
        field = self._product_pending[0]
        question = FIELD_QUESTIONS.get(field, f"请补充: {field}")
        return f"{question} (缺失字段: {field})"

    def _set_product_field(self, field: str, value: str) -> None:
        """填充产品字段: core_features 解析为列表; 其余原样赋值。"""
        if field == "core_features":
            self.product_intent.core_features = parse_core_features(value)  # type: ignore[union-attr]
        else:
            setattr(self.product_intent, field, value)  # type: ignore[union-attr]

    def _enter_product_confirmation(self) -> ConversationResponse:
        """必填齐全 → PRODUCT_CONFIRMATION: 产品摘要 + 确认询问 (验收 C [4])。"""
        self.transition(ConversationState.PRODUCT_CONFIRMATION)
        summary = self.product_intent.to_summary()  # type: ignore[union-attr]
        return ConversationResponse(
            state=self.state,
            message=f"{summary}\n{_PRODUCT_CONFIRM_PROMPT}",
            needs_input=True,
        )

    def handle_product_answer(self, text: str) -> ConversationResponse:
        """产品发现多轮回答: 填充当前缺失字段 → 还有缺失 → 追问下一个;
        全部补齐 → PRODUCT_CONFIRMATION + 摘要 + 确认询问。

        空回答 → 明确要求补充 (不静默跳过, 验收 F)。
        """
        if self.product_intent is None:
            return self._clarify("请先描述你的产品想法 (例如: '我想开发一个台球计分APP')")
        raw = (text or "").strip()
        if not raw:
            return ConversationResponse(
                state=self.state,
                message="回答不能为空 — 请补充当前缺失字段",
                needs_input=True,
            )
        if not self._product_pending:
            # 防御: 必填已齐全 (状态异常) → 回到确认
            return self._enter_product_confirmation()
        field = self._product_pending[0]
        self._set_product_field(field, raw)
        self._product_pending = self._product_pending[1:]
        if self._product_pending:
            # 还有缺失 → 追问下一个 (验收 C: 缺 problem → 追问; 补齐 → 追问 user)
            return ConversationResponse(
                state=self.state,
                message=self._next_product_question(),
                needs_input=True,
            )
        return self._enter_product_confirmation()

    def handle_product_confirm(
        self,
        answer: str,
        confirm_fn: Optional[Callable[[ProductIntent], str]] = None,
    ) -> ConversationResponse:
        """产品确认: y/yes → PROJECT_CREATION (+ 执行 create_product via confirm_fn)
        → DONE + "Product Created: X — Ready for Engineering." (验收 D);
        n/其它 → 重置 DISCOVERY (product_intent 清空, 验收 E)。

        confirm_fn: 宿主注入的执行回调 (接收 ProductIntent → 返回展示消息;
        conversation 零依赖, 不直接调 Action)。缺省 → 停留在 PROJECT_CREATION
        (返回信号, 由宿主执行创建)。
        """
        if self.product_intent is None:
            return self._clarify("当前没有进行中的产品流程 — 请描述你的产品想法")
        approved = (answer or "").strip().lower() in _APPROVE_ANSWERS
        if not approved:
            # 验收 E: 确认 n → 重置 DISCOVERY (product_intent / pending 清空)
            cancelled = self.product_intent.name or "(未命名产品)"
            self.product_intent = None
            self._product_pending = []
            self.pending_intent = None
            self.transition(ConversationState.DISCOVERY)
            return ConversationResponse(
                state=self.state,
                message=f"已取消产品 {cancelled} — 重新开始产品发现, 请描述你的产品想法",
                needs_input=True,
            )
        # 验收 D: y → PROJECT_CREATION → 创建 → DONE
        self.transition(ConversationState.PROJECT_CREATION)
        if confirm_fn is None:
            return ConversationResponse(
                state=self.state,
                message="产品已确认 — 等待执行创建 (create_product: ProductIntent → Project)",
                needs_input=False,
            )
        try:
            message = confirm_fn(self.product_intent)
        except Exception as exc:  # noqa: BLE001 — 失败安全: 创建失败 → 重置, 明确错误
            product_name = self.product_intent.name or "(未命名产品)"
            self.product_intent = None
            self._product_pending = []
            self.transition(ConversationState.DISCOVERY)
            return ConversationResponse(
                state=self.state,
                message=f"产品创建失败 ({product_name}): {exc} — 已重置, 请重新描述产品想法",
                needs_input=True,
            )
        self.transition(ConversationState.DONE)
        return ConversationResponse(
            state=self.state,
            message=message or f"Product Created: {self.product_intent.name} — Ready for Engineering.",
            needs_input=False,
        )

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
        self.history = []
