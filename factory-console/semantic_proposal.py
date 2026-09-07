"""factory-console/semantic_proposal.py — Semantic Proposal Domain (Cognitive Golden Path)。

S49 interpreter 只输出 "抽取的 facts"; Golden Path 需要**完整语义操作**:
LLM 理解用户语言 → 产出 Structured Semantic Proposal (一组 SemanticOperation) →
**Domain Validation** (proposal 不得直接写 Truth) → **apply_proposal** 走冲突/
supersession 解析 → Product Understanding mutation → 持久化。

设计依据 (Golden Path §7/§8):
- LLM 职责 = 理解语言 (产出 proposal); Domain 职责 = 决定 Truth 如何变化。
- LLM 不得直接写 Product Understanding — 唯一写路径经 validate_proposal → apply_proposal。
- 禁止把 regex keyword parser 扩张成更大 keyword parser; 生产理解必须走 LLM
  Semantic Proposal (console_sessions.llm_raw); 测试可注入 deterministic
  interpreter, 但必须经过与本生产完全相同的 validate/apply pipeline。
- 语义操作 (Capability A-G, §9): ADD / UPDATE / NEGATE / DEFER / REPLACE /
  CONFIRM / REJECT / CLARIFY / QUESTION / SUGGEST。

本模块零 LLM 依赖 (纯标准库): interpreter 适配器在 llm_semantic_interpreter.py;
确定性兜底在 deterministic_proposal.py (不扩张 keyword, 只做诚实降级 + 明确
"无法确定时澄清")。
"""
from __future__ import annotations

from typing import Any, Literal

# ------------------------------------------------------------------ 语义操作注册表

#: 支持的语义操作 (Golden Path §9)
OpName = Literal[
    "ADD", "UPDATE", "NEGATE", "DEFER", "REPLACE",
    "CONFIRM", "REJECT", "CLARIFY", "QUESTION", "SUGGEST",
]
SEMANTIC_OPS: tuple[str, ...] = (
    "ADD", "UPDATE", "NEGATE", "DEFER", "REPLACE",
    "CONFIRM", "REJECT", "CLARIFY", "QUESTION", "SUGGEST",
)

#: 操作 → 目标 fact 状态语义 (供 interpreter/validation 参考)
OP_STATUS_SEMANTICS: dict[str, str] = {
    "ADD": "PROPOSED",        # 新增事实 (默认待确认)
    "UPDATE": "PROPOSED",     # 修改 = supersede 旧值 + 新值 (或原地刷新)
    "NEGATE": "REJECTED",     # 否定已有事实
    "DEFER": "DEFERRED",      # 延后 (非拒绝, 可恢复)
    "REPLACE": "PROPOSED",    # 替换 (supersede 同维度旧值)
    "CONFIRM": "CONFIRMED",   # 用户明确确认
    "REJECT": "REJECTED",     # 用户明确拒绝
    "SUGGEST": "PROPOSED",    # AI 建议 (低置信待确认)
    "CLARIFY": "CLARIFY",     # 需澄清 (非 fact 变更)
    "QUESTION": "QUESTION",   # 提问 (记录为 QUESTION fact)
}

#: 会改变 Truth 的操作 (CLARIFY/QUESTION 不直接改 fact, 只加消息/提问)
MUTATING_OPS: tuple[str, ...] = (
    "ADD", "UPDATE", "NEGATE", "DEFER", "REPLACE",
    "CONFIRM", "REJECT", "SUGGEST",
)


class ProposalValidationError(ValueError):
    """Semantic Proposal 未通过 Domain Validation (拒绝写入 Truth)。"""


# ------------------------------------------------------------------ Proposal 结构


def normalize_op(op: str) -> str:
    o = str(op or "").strip().upper()
    if o not in SEMANTIC_OPS:
        raise ProposalValidationError(
            f"非法语义操作: {op!r} (可选: {', '.join(SEMANTIC_OPS)})")
    return o


def validate_operation(op: dict[str, Any]) -> dict[str, Any]:
    """单条 SemanticOperation 的 Domain Validation。

    规则 (防止 LLM 幻觉直接污染 Truth):
    - op 必填且 ∈ SEMANTIC_OPS
    - fact_type 必填 ∈ FACT_TYPES (CLARIFY 可省略)
    - content 必填 (非空字符串; 经 strip)
    - confidence ∈ [0, 1]
    - CLARIFY: 不需要 fact (语义 = 反问), content = 澄清问题文本
    - QUESTION: fact_type 强制 QUESTION
    - NEGATE/REJECT/DEFER/CONFIRM 对已有 fact 操作时: target_id 可选
      (无 target_id 时按 content/dimension 解析到已有 fact — 见 resolve 层)

    返回规范化 dict (不落盘)。
    """
    if not isinstance(op, dict):
        raise ProposalValidationError(f"operation 必须是 dict: {op!r}")
    o = normalize_op(op.get("op", ""))
    out: dict[str, Any] = {"op": o}
    if o == "CLARIFY":
        q = str(op.get("content") or "").strip()
        if not q:
            raise ProposalValidationError("CLARIFY 必须带 content (澄清问题文本)")
        out["content"] = q[:300]
        return out
    ftype = str(op.get("fact_type") or "").strip().upper()
    if ftype not in ("IDEA", "REQUIREMENT", "CONSTRAINT", "DECISION",
                     "QUESTION", "FUTURE_IDEA"):
        raise ProposalValidationError(
            f"非法 fact_type: {op.get('fact_type')!r}")
    content = str(op.get("content") or "").strip()
    if not content:
        raise ProposalValidationError(f"{o} 必须带 content")
    out["fact_type"] = ftype
    out["content"] = content[:500]
    conf = op.get("confidence")
    try:
        confidence = float(conf if conf not in (None, "") else 1.0)
    except (TypeError, ValueError):
        raise ProposalValidationError(
            f"非法 confidence: {conf!r} (须为数字)") from None
    if not 0.0 <= confidence <= 1.0:
        raise ProposalValidationError(
            f"confidence 越界: {confidence} (须 ∈ [0,1])")
    out["confidence"] = confidence
    if o == "QUESTION":
        out["fact_type"] = "QUESTION"
    tid = op.get("target_id")
    if tid:
        out["target_id"] = str(tid)
    actor = str(op.get("actor") or "").strip()
    if actor:
        out["actor"] = actor
    return out


def validate_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    """Semantic Proposal 的 Domain Validation (顶层)。

    Proposal 结构:
    {
      "operations": [SemanticOperation...],   # 必填, 可空
      "reply": str,                            # 给用户的自然语言回复
      "summary": str,                          # 对当前理解的更新总结 (可选)
      "question": str,                         # 主动追问 (可选, 仅一个)
      "show_understanding": bool               # 是否展示当前理解 (可选)
    }

    抛 ProposalValidationError → interpreter 层降级 (不得部分写 Truth)。
    """
    if not isinstance(proposal, dict):
        raise ProposalValidationError(f"proposal 必须是 dict: {proposal!r}")
    ops_raw = proposal.get("operations")
    if not isinstance(ops_raw, list):
        raise ProposalValidationError("proposal.operations 必须是 list (可为空)")
    ops = [validate_operation(o) for o in ops_raw]
    out: dict[str, Any] = {"operations": ops}
    for k in ("reply", "summary", "question"):
        v = proposal.get(k)
        if v is not None:
            out[k] = str(v).strip()[:600]
    out["show_understanding"] = bool(proposal.get("show_understanding", False))
    return out


def build_proposal(*, operations: list[dict[str, Any]], reply: str = "",
                   summary: str = "", question: str = "",
                   show_understanding: bool = False) -> dict[str, Any]:
    """构造合法 proposal (interpreter 适配器/测试注入用)。"""
    return validate_proposal({
        "operations": operations, "reply": reply, "summary": summary,
        "question": question, "show_understanding": show_understanding,
    })


# ------------------------------------------------------------------ apply (Truth mutation)


def _find_active_fact(doc: dict[str, Any], *, fact_type: str = "",
                      content: str = "", fact_id: str = "") -> dict[str, Any] | None:
    """在 doc 中找可操作 fact (按 id 优先; 否则 type+content 精确 / 语义槽)。"""
    from . import product_understanding as pu
    facts = (doc.setdefault("understanding", {})
             .setdefault("facts", {}))
    if fact_id:
        f = facts.get(fact_id)
        if f is not None and f.get("status") in pu.MUTABLE_STATUSES:
            return dict(f)
        return None
    # 精确 key 优先 (effective 或 deferred/rejected — 可恢复/否定)
    target_key = (fact_type.upper(), pu.normalize_content(content))
    for f in facts.values():
        if f.get("type") != fact_type.upper():
            continue
        if f.get("status") not in pu.MUTABLE_STATUSES:
            continue
        if pu.identity_key(f) == target_key:
            return dict(f)
    # 语义槽 (同槽不同值 = 修改对象)
    if content:
        dim = pu.dimension_of({"type": fact_type, "content": content})
        for f in facts.values():
            if f.get("type") != fact_type.upper():
                continue
            if f.get("status") not in pu.MUTABLE_STATUSES:
                continue
            if pu.dimension_of(f) == dim:
                return dict(f)
    return None


def apply_operations(root, conversation_id: str,
                     operations: list[dict[str, Any]],
                     source_message_id: str = "",
                     fallback_actor: str = "") -> list[dict[str, Any]]:
    """按序执行一组已 validated 的 SemanticOperation → Truth mutation。

    这是 Semantic Proposal 管道的**唯一写入口**: LLM/interpreter 产出 proposal,
    validate_proposal 通过后交由此函数落盘。冲突/恢复/supersession 语义:
    - ADD/SUGGEST     → upsert_fact (identity + dimension supersession 由 domain 处理)
    - UPDATE/REPLACE  → 找已有 fact → transition SUPERSEDED + upsert 新值
                        (或直接 upsert — domain 已按 identity/dimension 顶替)
    - NEGATE/REJECT   → 找已有 fact → REJECTED; 找不到 → 新增 CONSTRAINT? 不 —
                        找不到 = 用户否定一个我们尚未记录的东西 → 记录 REJECTED
                        (作为否定历史, 阻止后续误加同 key)
    - DEFER           → 找已有 fact → DEFERRED (可恢复); 找不到 → 新增 FUTURE_IDEA
                        + status DEFERRED (延后的未来想法)
    - CONFIRM         → 找已有 fact → CONFIRMED; 找不到 → 抛错 (无对象可确认,
                        防 LLM 幻觉凭空确认)
    - CLARIFY         → 不落 fact (由上层作为 question 处理)
    - QUESTION        → upsert QUESTION fact (记录用户/系统提问, 可 supersede)

    返回: 每次 mutation 的结果 dict 列表 (按序)。空 op 列表 → []。
    """
    from . import product_understanding as pu

    results: list[dict[str, Any]] = []
    actor = fallback_actor or "human"
    for op in operations:
        o = op["op"]
        # 1) CLARIFY — 不落 fact
        if o == "CLARIFY":
            results.append({"op": o, "content": op["content"]})
            continue
        ftype = op["fact_type"]
        content = op["content"]
        # 2) 目标解析 (NEGATE/REJECT/DEFER/CONFIRM/UPDATE/REPLACE 需要已存在对象)
        target = None
        if o in ("NEGATE", "REJECT", "DEFER", "CONFIRM", "UPDATE", "REPLACE"):
            target = _resolve_target(root, conversation_id, op)
        # 3) 分派
        if o in ("ADD", "SUGGEST"):
            res = pu.upsert_fact(
                root, conversation_id, fact_type=ftype, content=content,
                source_message_id=source_message_id,
                confidence=op.get("confidence", 1.0),
                provenance=f"semantic:{o.lower()}",
                status="PROPOSED")
            results.append({"op": o, "fact": res})
        elif o in ("UPDATE", "REPLACE"):
            if target is not None:
                pu.transition_fact(root, conversation_id, target["id"],
                                   to="SUPERSEDED", actor=actor)
            res = pu.upsert_fact(
                root, conversation_id, fact_type=ftype, content=content,
                source_message_id=source_message_id,
                confidence=op.get("confidence", 1.0),
                provenance=f"semantic:{o.lower()}",
                status="PROPOSED")
            results.append({"op": o, "fact": res,
                            "superseded": target["id"] if target else None})
        elif o in ("NEGATE", "REJECT"):
            if target is not None:
                res = pu.transition_fact(root, conversation_id, target["id"],
                                         to="REJECTED", actor=actor)
            else:
                # 否定一个未记录的东西 → 落一条 REJECTED (否定历史)
                res = pu.upsert_fact(
                    root, conversation_id, fact_type=ftype, content=content,
                    source_message_id=source_message_id,
                    confidence=op.get("confidence", 1.0),
                    provenance=f"semantic:{o.lower()}",
                    status="REJECTED")
            results.append({"op": o, "fact": res,
                            "target_id": target["id"] if target else None})
        elif o == "DEFER":
            if target is not None:
                res = pu.transition_fact(root, conversation_id, target["id"],
                                         to="DEFERRED", actor=actor)
            else:
                # 延后一个未记录的东西 → 记录为延后的 FUTURE_IDEA
                res = pu.upsert_fact(
                    root, conversation_id, fact_type="FUTURE_IDEA",
                    content=content,
                    source_message_id=source_message_id,
                    confidence=op.get("confidence", 1.0),
                    provenance="semantic:defer",
                    status="DEFERRED")
            results.append({"op": o, "fact": res,
                            "target_id": target["id"] if target else None})
        elif o == "CONFIRM":
            if target is None:
                raise ProposalValidationError(
                    f"CONFIRM 无对象可确认: {ftype}:{content} — 拒绝幻觉确认")
            res = pu.transition_fact(root, conversation_id, target["id"],
                                     to="CONFIRMED", actor=actor)
            results.append({"op": o, "fact": res})
        elif o == "QUESTION":
            res = pu.upsert_fact(
                root, conversation_id, fact_type="QUESTION", content=content,
                source_message_id=source_message_id,
                confidence=op.get("confidence", 1.0),
                provenance="semantic:question",
                status="PROPOSED")
            results.append({"op": o, "fact": res})
        else:  # pragma: no cover — validate 已挡
            raise ProposalValidationError(f"未处理 op: {o}")
    return results


def _resolve_target(root, conversation_id: str,
                    op: dict[str, Any]) -> dict[str, Any] | None:
    """按 op 找目标 fact (id → type+content 精确 → 语义槽)。"""
    from . import product_understanding as pu

    doc = pu._ensure_conv_doc(root, conversation_id)  # noqa: SLF001 — 同包复用
    return _find_active_fact(
        doc, fact_type=op.get("fact_type", ""),
        content=op.get("content", ""), fact_id=op.get("target_id", ""))


__all__ = [
    "SEMANTIC_OPS", "OP_STATUS_SEMANTICS", "MUTATING_OPS",
    "ProposalValidationError",
    "normalize_op", "validate_operation", "validate_proposal", "build_proposal",
    "apply_operations",
]
