"""factory-console/conversation_app.py — Conversation Application Layer (S49/Phase 5)。

CLI / API / WebUI 的**唯一**业务入口 (S49 §十三/§十四):
```
CLI ───┐
       │
WebUI ─┼──→ ConversationApplicationService / ProductUnderstandingService
       │
API ───┘
```

组件:
- ConversationApplicationService — conversation 生命周期 (create/get/messages/close)
- ProductUnderstandingService — 自然语言 → Understanding 更新 (唯一解释入口):
    process_user_message(text) = 追加消息 → interpreter 抽取 facts → upsert → 回复
- InterpretationResult / Interpreter — 解释协议 (测试注入确定性 interpreter;
  生产接 LLM 适配器, 见 real-llm-execution-validation 经验: 解释失败必须显式降级)
- default_interpreter — 无 LLM 兜底: 确定性中文规则抽取 (Internal Structured,
  External Natural — 不要求用户 keyword; 规则只是内部实现)
- sufficiency / adaptive clarification — 从 snapshot 发现真正缺失, 自然提问
  (替代固定 problem→user→core_features 问卷; S49 §五)

边界:
- 本模块只 import factory_console.product_understanding (domain); 不触碰
  conversation_os/session/legacy (S49 §十禁令)。
- 无 LLM 依赖: interpreter 注入; None → default_interpreter (确定性, 可测试)。
- 回复文本由 interpreter 提供 (reply) — 规则兜底时给出基于 Understanding 的诚实回复。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from factory_console import product_understanding as pu
from factory_console.semantic_proposal import (
    ProposalValidationError, apply_operations, validate_proposal,
)

# 延迟 import (避免顶层循环): llm_semantic_interpreter / build_llm_prompt 供默认语义解释


# ------------------------------------------------------------------ 解释协议

@dataclass
class InterpretationResult:
    """一轮自然语言输入的解释结果 (facts 增量 + 回复)。"""

    facts: list[dict[str, Any]] = field(default_factory=list)
    reply: str = ""
    question: str = ""  # 若需要用户澄清, 非空
    summary: str = ""


#: Interpreter 协议: (root, conversation_id, text, snapshot) -> InterpretationResult
Interpreter = Callable[[str, str, str, dict[str, Any]], InterpretationResult]

#: 关键维度缺失标签 (sufficiency) — 中文, 供提问直接使用
DIMENSION_LABELS: dict[str, str] = {
    "name": "产品叫什么",
    "platform": "运行平台 (手机/PC/网页?)",
    "operation": "操作方式",
    "core_flow": "核心玩法或主流程",
    "no_login": "是否需要登录",
}


# ------------------------------------------------------------------ 确定性规则解释器 (兜底)

#: 想法触发 (Idea — 首次描述产品)
_IDEA_PATTERNS = [
    (r"(?:我想|我要|想做|打算做|准备做|希望做|想开发|想写|做一个|做一款|开发一个|开发一款|写一个|搞一个)(.{2,60})", "想法"),
]
#: 平台 → Requirement/Constraint
_PLATFORM_PATTERNS = [
    (r"手机|移动端|安卓|android|ios", "手机端"),
    (r"网页?|web|浏览器|h5", "网页端"),
    (r"桌面|电脑|pc|mac|windows|linux", "桌面端"),
]
#: 登录约束
_NO_LOGIN_PATTERNS = [
    (r"不要登录|不用登录|无需登录|免登录|不用注册|不需要登录|不登录", "无需登录, 打开即可使用"),
]
#: 一般否定约束 (不要/禁止/不能 X — 登录已由 _NO_LOGIN 覆盖)
_BAN_PATTERNS = [
    (r"不要([^,。;；，]{2,30})", "禁止{0}"),
    (r"禁止([^,。;；，]{2,30})", "禁止{0}"),
    (r"不能(?:做|加|有)?([^,。;；，]{2,30})", "禁止{0}"),
    (r"不做(?:付费|内购|广告)?", "禁止付费内购"),
]
#: 未来想法 (FUTURE_IDEA)
_FUTURE_PATTERNS = [
    (r"以后(?:可以|再加|再|想)?(?:加|做|上|支持|要)?(?:一个|个|的)?([^,。;；]{2,40})", None),
    (r"未来(?:可以|再)?(?:加|做|上|支持|要)?([^,。;；]{2,40})", None),
    (r"(先不做|暂时不做|暂不考虑)([^,。;；]{2,40})", None),
]
#: 决策触发 (DECISION — 用户拍板"就用 X")
_DECISION_PATTERNS = [
    (r"(?:操作|操控)(?:方式|上)?(?:就|用|采用|选择|用)?([^,。;；]{1,20})?(?:虚拟摇杆|摇杆|按键|点按|点击|拖动|滑屏|触屏)", None),
    (r"(?:就|决定|采用|选择|用|改成|改为)([^,。;；]{2,30})(?:吧|好了|就行|即可)?$", None),
]


def _extract_first(text: str, patterns: list[tuple[str, Any]]) -> str:
    for pat, _ in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return ""


def _norm_fact_type(fact_type: str) -> str:
    t = str(fact_type or "").strip().upper()
    return t if t in pu.FACT_TYPES else "REQUIREMENT"


def default_interpreter(root: str, conversation_id: str, text: str,
                        snapshot: dict[str, Any]) -> InterpretationResult:
    """确定性中文规则解释 (无 LLM 兜底; 规则内部实现, 不要求用户 keyword)。

    语义 (对应 S49 §四 场景):
    - 想法描述 → IDEA
    - 平台/登录 → CONSTRAINT/REQUIREMENT
    - "以后可以加 X" → FUTURE_IDEA
    - "就用 X / 虚拟摇杆吧" → DECISION
    同内容重复 → 不新增 (domain supersession, Test D)。
    """
    raw = str(text or "").strip()
    result = InterpretationResult()
    if not raw:
        result.reply = "请告诉我你的想法。"
        return result
    existing = {f"{f.get('type')}:{pu.normalize_content(f.get('content'))}"
                for f in snapshot.get("facts", [])}

    def _add(fact_type: str, content: str, confidence: float = 1.0) -> None:
        key = f"{fact_type}:{pu.normalize_content(content)}"
        if key in existing:
            return
        existing.add(key)
        result.facts.append({"type": fact_type, "content": content,
                             "confidence": confidence, "provenance": "rule"})

    # 1. 平台 (最具体词 → content 中文标签)
    plat_content = ""
    for pat, label in _PLATFORM_PATTERNS:
        if re.search(pat, raw, re.IGNORECASE):
            plat_content = label
            break
    if plat_content:
        _add("REQUIREMENT", f"运行平台: {plat_content}")

    # 2. 无需登录 (命中即不再走一般否定 2b — 重申场景 2b 会误抽"登录")
    no_login_hit = False
    for pat, label in _NO_LOGIN_PATTERNS:
        if re.search(pat, raw):
            no_login_hit = True
            _add("CONSTRAINT", label)
            break
    # 2b. 一般否定约束 (不要内购/不要广告…) — 仅当本句未命中登录约束
    if not no_login_hit:
        for pat, label_tpl in _BAN_PATTERNS:
            m = re.search(pat, raw)
            if m:
                word = m.group(1).strip() if m.lastindex else ""
                content = label_tpl.format(word) if word else label_tpl
                _add("CONSTRAINT", content)
                break

    # 3. 未来想法 (含"以后/未来/先不做" → FUTURE_IDEA)
    future = _extract_future(raw)
    if future:
        _add("FUTURE_IDEA", future, confidence=0.8)

    # 4. 操作/交互决策
    op = _extract_operation(raw)
    if op:
        _add("DECISION", f"操作方式: {op}")

    # 5. 其它明确决策 (就用/决定/采用 X)
    dec = _extract_decision(raw)
    if dec and not op:
        _add("DECISION", dec, confidence=0.9)

    # 6. 想法 (无任何已抽事实且像初次描述 → IDEA; 或显式"做X"整句)
    has_any = bool(result.facts)
    idea = _extract_idea(raw)
    if idea and not _has_idea(snapshot):
        _add("IDEA", idea, confidence=0.9)
    elif idea and not has_any:
        _add("IDEA", idea, confidence=0.6)

    # 回复: 基于 Understanding 增量
    if result.facts:
        parts = []
        for f in result.facts:
            label = {"IDEA": "我记下了想法", "REQUIREMENT": "好的, 平台",
                     "CONSTRAINT": "明白, 约束", "DECISION": "好的, 决定",
                     "FUTURE_IDEA": "记下, 未来可以考虑"}.get(
                f["type"], f["type"])
            parts.append(f"{label}: {f['content']}")
        result.reply = "；".join(parts) + "。"
        result.summary = "已更新产品理解。"
    else:
        result.reply = _continuity_reply(snapshot, raw)
    return result


def _has_idea(snapshot: dict[str, Any]) -> bool:
    return any(f.get("type") == "IDEA" for f in snapshot.get("facts", []))


def _extract_idea(text: str) -> str:
    for pat, _ in _IDEA_PATTERNS:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip(" ，,。.;；:：")
    return ""


def _extract_future(text: str) -> str:
    m = re.search(r"(?:以后|未来|将来|之后再|先不做|暂时不做)(?:可以|想|要|再)?"
                  r"(?:加|做|上|支持|要|考虑)?(?:一个|个|的)?([^,。;；，]{2,40})", text)
    if m:
        return m.group(1).strip()
    return ""


def _extract_operation(text: str) -> str:
    m = re.search(r"(?:操作|操控)(?:方式|上)?(?:就|用|采用|选择)?"
                  r"(虚拟摇杆|摇杆|按键|点按|点击|拖动|滑屏|触屏|重力感应|键盘|鼠标)", text)
    if m:
        return m.group(1)
    # "操作就用虚拟摇杆吧"
    m = re.search(r"操作.{0,4}(?:就|用)(.{2,12})", text)
    if m:
        return m.group(1).strip("吧。.,， ")
    return ""


def _extract_decision(text: str) -> str:
    # 排除已当作 idea 的"做X"句 (决策常含 用/采用/决定)
    m = re.search(r"(?:用|采用|就用|决定|选择|改成|改为|定位为|面向)([^,。;；，]{2,40})"
                  r"(?:吧|好了|就行|即可|为目标|用户)?$", text)
    if m:
        return m.group(1).strip()
    return ""


def _legacy_to_proposal(legacy_interp: Callable[..., Any]) -> Callable[..., dict[str, Any]]:
    """把旧 Interpreter (返回 InterpretationResult) 适配为 semantic proposal 协议。

    供无 LLM 环境的确定性兜底/旧测试兼容: 旧规则抽取的 facts → ADD operations,
    经与生产完全相同的 validate_proposal/apply_operations 管道落 Truth (Golden Path
    §8: 测试可注入 deterministic, 但必须经过同一 Domain Validation / Mutation)。
    本适配**不扩张规则**: 只转译旧规则已有输出; 语义理解主路径是 LLM。
    """

    def _adapter(root: str, conversation_id: str, text: str,
                 snapshot: dict[str, Any]) -> dict[str, Any]:
        interp = legacy_interp(root, conversation_id, text, snapshot)
        ops = []
        for f in interp.facts:
            ops.append({"op": "ADD", "fact_type": f["type"],
                        "content": f["content"],
                        "confidence": float(f.get("confidence") or 1.0)})
        return {
            "operations": ops,
            "reply": interp.reply or "",
            "question": interp.question or "",
            "summary": interp.summary or "",
            "show_understanding": False,
        }

    return _adapter


def _continuity_reply(snapshot: dict[str, Any], text: str) -> str:
    """无新 fact 时的连续性回复: 引用已有 Understanding, 不假装知道。

    S49 §七: Session 2 继续对话必须基于持久化 Understanding 回答, 不能
    "不知道你说的是什么项目"。
    """
    facts = snapshot.get("facts", [])
    if not facts:
        return "我还没记录到具体的产品想法 —— 你可以直接说想做什么, 例如「我想做一个飞机大战小游戏」。"
    idea = next((f for f in facts if f.get("type") == "IDEA"), None)
    head = f"我们聊的是「{idea['content']}」。" if idea else "基于之前聊的: "
    lines = [head]
    for f in facts:
        if f.get("type") != "IDEA":
            lines.append(f"- {f.get('type').lower()}: {f.get('content')}")
    lines.append("你可以继续补充或修改。")
    return "\n".join(lines)


# ------------------------------------------------------------------ 服务

class ConversationApplicationService:
    """Conversation 生命周期 (Application Layer 入口之一; 无业务状态机)。"""

    def __init__(self, root: str | Any) -> None:
        self.root = str(root)

    def create(self, *, title: str = "新会话", created_by: str = "human") -> dict[str, Any]:
        return pu.create_conversation(self.root, title=title, created_by=created_by)

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        return pu.get_conversation(self.root, conversation_id)

    def list(self) -> list[dict[str, Any]]:
        return pu.conversations(self.root)

    def messages(self, conversation_id: str) -> list[dict[str, Any]]:
        return pu.messages(self.root, conversation_id)

    def close(self, conversation_id: str) -> dict[str, Any]:
        return pu.close_conversation(self.root, conversation_id)


class ProductUnderstandingService:
    """Product Understanding 应用服务 (唯一解释入口 + sufficiency/adaptive)。"""

    def __init__(self, root: str | Any, *,
                 interpreter: Callable[..., Any] | None = None,
                 semantic: bool = False) -> None:
        """root: workspace root; semantic=True → 默认 LLM Semantic Interpreter。

        interpreter 注入 (协议: (root, conv_id, text, snapshot) -> proposal dict,
        其中 proposal 含 operations 列表 — 见 semantic_proposal.validate_proposal):
        - None + semantic=True  → llm_semantic_interpreter (生产; LLM 不可用自动降级)
        - None + semantic=False → deterministic default_interpreter (测试/无 LLM,
          输出自动转 proposal 经同一 validate/apply 管道)
        - 显式注入          → 测试注入 (deterministic semantic interpreter)
        """
        self.root = str(root)
        if interpreter is not None:
            self._interpreter = interpreter
        elif semantic:
            try:
                from factory_console.llm_semantic_interpreter import (
                    llm_semantic_interpreter as _llm)
                self._interpreter = _llm
            except Exception:  # noqa: BLE001 — import 失败 → 确定性兜底
                self._interpreter = _legacy_to_proposal(default_interpreter)
        else:
            self._interpreter = _legacy_to_proposal(default_interpreter)

    # ---- 自然语言增量更新 (Golden Path: Semantic Proposal 管道) ----
    def process_user_message(self, conversation_id: str, text: str) -> dict[str, Any]:
        """用户自然语言 → message 落盘 → Semantic Proposal → Domain Validation → Truth。

        管道 (Golden Path §7):
          User Message → Context Assembly (persistent Understanding)
          → interpreter (LLM 或 deterministic) → Semantic Proposal
          → validate_proposal (Domain Validation) → apply_operations (唯一写路径)
          → reply/question

        返回 {message, reply, question, proposal, operations_applied,
              understanding_version, show_understanding}
        """
        if pu.get_conversation(self.root, conversation_id) is None:
            raise ValueError(f"conversation 不存在: {conversation_id}")
        msg = pu.append_message(self.root, conversation_id,
                                role="human", content=text)
        snap = pu.understanding_snapshot(self.root, conversation_id)
        # 1) interpreter → proposal (LLM 语义理解, 或注入 deterministic)
        proposal = self._interpreter(self.root, conversation_id, text, snap)
        # 2) Domain Validation (proposal 未通过 → 拒绝, 不写 Truth)
        validated = validate_proposal(proposal)
        ops = validated["operations"]
        # 3) 唯一 Truth 写路径
        applied = apply_operations(
            self.root, conversation_id, ops,
            source_message_id=msg["id"], fallback_actor="human")
        # 4) 落 assistant 消息 + 回复
        reply = validated.get("reply") or self._fallback_reply(snap, text, applied)
        if reply:
            pu.append_message(self.root, conversation_id,
                              role="assistant", content=reply)
        return {
            "message": msg,
            "reply": reply,
            "question": validated.get("question", ""),
            "summary": validated.get("summary", ""),
            "proposal": validated,
            "operations_applied": applied,
            "show_understanding": bool(validated.get("show_understanding")),
            "understanding_version": pu.understanding_version(self.root, conversation_id),
        }

    @staticmethod
    def _fallback_reply(snapshot: dict[str, Any], text: str,
                        applied: list[dict[str, Any]]) -> str:
        if applied:
            parts = []
            for r in applied:
                f = r.get("fact") or {}
                label = {"IDEA": "记下想法", "REQUIREMENT": "平台/需求",
                         "CONSTRAINT": "约束", "DECISION": "决定",
                         "FUTURE_IDEA": "未来考虑", "QUESTION": "问题"}.get(
                    f.get("type", ""), f.get("type", ""))
                parts.append(f"{label}: {f.get('content')}")
            return "；".join(parts) + "。" if parts else "已更新产品理解。"
        return _continuity_reply(snapshot, text)

    # ---- 只读 (context/PRD 输入) ----
    def snapshot(self, conversation_id: str) -> dict[str, Any]:
        return pu.understanding_snapshot(self.root, conversation_id)

    def context(self, conversation_id: str, *, recent_messages: int = 8) -> dict[str, Any]:
        return pu.build_context(self.root, conversation_id,
                                recent_messages=recent_messages)

    def facts(self, conversation_id: str, *, fact_type: str = "",
              include_inactive: bool = False) -> list[dict[str, Any]]:
        return pu.list_facts(self.root, conversation_id, fact_type=fact_type,
                             include_inactive=include_inactive)

    # ---- Sufficiency / Adaptive Clarification (S49 §五) ----
    def sufficiency_gaps(self, conversation_id: str) -> list[str]:
        """当前产品定义下真正缺失且影响决策的维度 (非固定问卷)。"""
        snap = self.snapshot(conversation_id)
        facts = snap.get("facts", [])
        types = {f.get("type") for f in facts}
        contents = " ".join(str(f.get("content", "")) for f in facts)
        if not types:
            return ["想做一个什么样的产品? 可以先说说你的想法。"]
        gaps = []
        if "IDEA" not in types:
            gaps.append("先确定核心想法: 你想做什么?")
        if "REQUIREMENT" not in types and not re.search(r"平台|手机|网页|桌面", contents):
            gaps.append("运行平台还没定 (手机 / 网页 / 桌面?)。")
        if "DECISION" not in types and not re.search(r"操作|摇杆|点击|拖动", contents):
            gaps.append("交互方式还没定 (例如操作方式会影响后续设计)。")
        return gaps

    def adaptive_question(self, conversation_id: str,
                          asked: list[str] | None = None) -> str:
        """基于具体产品判断的下一个问题 (只问影响决策的; 不问已答)。"""
        asked = [str(x).strip() for x in (asked or [])]
        for gap in self.sufficiency_gaps(conversation_id):
            if gap not in asked:
                return gap
        return ""


__all__ = [
    "ConversationApplicationService", "ProductUnderstandingService",
    "InterpretationResult", "Interpreter", "default_interpreter",
    "_legacy_to_proposal",
]
