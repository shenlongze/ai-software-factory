"""factory-console/session/llm_task_proposal.py — LLMTaskProposalEngine (S10-062 批次 B)。

LLM 任务提案引擎 (GAP G2, 设计 §5): LLM 优先 — GapAnalysis + 项目上下文 →
ReasoningProvider.propose_task → 结构化 TaskProposal; 过 TaskProposalValidator
12 项 deterministic gate (设计 §7: role/dup/cycle/confidence/依赖存在性/
replan limit 等); 失败 (LLM 错误 / schema / gate 拒绝) → fallback
deterministic TaskProposalEngine (S10-061 规则模板) → 同 gate; 再失败 →
REQUEST_REVIEW (无提案 — 安全兜底, 设计 §8)。LLM 挂不影响系统。

WHY/HOW/DEPENDENCY (设计 §5 必须解释):
- WHY:  proposal.rationale 必须解释该任务如何解决 GAP (engine gate 检查非空)
- HOW:  proposal.acceptance_criteria 必须描述如何验证完成 (validator 检查 7
        + engine gate)
- DEPENDENCY: proposal.dependencies 必须说明依赖原因 — 依赖任务必须存在
        (validator 检查 5) 且不形成 cycle (validator 检查 6); 类型必须是
        字符串列表 (engine gate)

task_id 系统侧决定 (Deterministic = Enforcement — 设计 §1): LLM 输出
task_id 为空时由引擎按现有任务递增推导 (T0XX, 冲突检查), LLM 永不决定 id;
LLM 提供的冲突 id → Validator 检查 1 拒绝 → fallback。

LLMTaskProposalResult — 提案结果 {proposal: TaskProposal|None,
fallback_used, source ("llm"|"deterministic"|"request_review"), reason,
validation_result, provider, model, raw_output, confidence, latency}:
fallback_used 标记供 PlanningTrace (设计 §9)。

边界 (批次 B):
- 纯标准库 + 只读引用 session/task_proposal (TaskProposal/Engine/Validator/
  DuplicateDetector) + session/reasoning (ReasoningProvider/ReasoningError);
  零新依赖, 不修改任何现有模块; 不改 DAG/不落盘 (trace 由调用方注入)
- 禁真实网络/LLM (测试用 llm_fn deterministic fixture; 真实 LLM 留 Pilot)

设计: docs/sprint10/S10-062-llm-planning-design.md §5/§7/§8/§9
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .reasoning import (
    OPERATION_PROPOSE_TASK,
    ReasoningError,
    ReasoningProvider,
    ReasoningUnavailable,
)
from .task_proposal import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    TaskProposal,
    TaskProposalEngine,
    TaskProposalValidator,
)

#: LLM 输出最大 task_id 推导尝试次数 (冲突保护)
MAX_TASK_ID_ATTEMPTS = 100


@dataclass
class LLMTaskProposalResult:
    """LLM 任务提案结果 (fallback_used 标记供 trace — 设计 §9)。

    proposal:        最终 TaskProposal (LLM 或 deterministic); None →
                     无提案 (REQUEST_REVIEW 路径)
    fallback_used:   是否走了 fallback (LLM 失败/Validator 拒绝)
    source:          "llm" | "deterministic" | "request_review"
    reason:          来源原因 (LLM 失败 / gate 拒绝 / 兜底说明)
    validation_result: Validator 结果 {valid, reasons, checks} (最后一步)
    provider/model:  LLM 路径身份 (fallback → deterministic 名)
    raw_output:      LLM 原始输出 (供 trace/审计)
    confidence:      proposal.confidence (便捷访问; 无提案 → 0.0)
    token_usage:     LLM 调用 token 用量 (未统计 → 空)
    latency:         提案耗时 (秒)
    """

    proposal: Optional[TaskProposal] = None
    fallback_used: bool = False
    source: str = "llm"
    reason: str = ""
    validation_result: dict[str, Any] = field(default_factory=dict)
    provider: str = ""
    model: str = ""
    raw_output: Any = None
    confidence: float = 0.0
    token_usage: dict[str, int] = field(default_factory=dict)
    latency: float = 0.0


class LLMTaskProposalEngine:
    """LLM 优先任务提案引擎 (设计 §5): propose → LLMTaskProposalResult。

    propose(gap, context, provider, existing_tasks, dag) — ① prompt (gap +
    上下文 + WHY/HOW/DEPENDENCY 要求); ② provider.propose_task → 结构化
    dict; ③ task_id 系统侧推导 + WHY/HOW/DEPENDENCY gate +
    TaskProposalValidator.validate (12 项); ④ 成功 → TaskProposal
    (source="llm"); 失败 → fallback deterministic TaskProposalEngine.propose
    → 同 gate (source="deterministic", fallback_used=True); 再失败 →
    REQUEST_REVIEW (proposal=None)。永不抛 (失败安全)。

    构造 (全部可注入):
    - provider: ReasoningProvider (缺省自建 — llm_fn=None 时默认装配,
      无真实 provider 时 propose 直接走 fallback)
    - deterministic: TaskProposalEngine (fallback 基础)
    - validator: TaskProposalValidator (12 项 gate; 可注入 confidence 阈值/
      DuplicateDetector)
    - confidence_threshold: Validator 阈值 (缺省 0.5, 同 S10-061)
    - trace: PlanningTrace 实例 (可选)
    - prompt_builder: 可调用 (gap, context) -> str — 自定义 prompt
    """

    def __init__(
        self,
        *,
        provider: Optional[ReasoningProvider] = None,
        deterministic: Optional[TaskProposalEngine] = None,
        validator: Optional[TaskProposalValidator] = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        trace: Any = None,
        prompt_builder: Optional[Any] = None,
    ) -> None:
        self._provider = provider if provider is not None else ReasoningProvider()
        self._deterministic = (
            deterministic if deterministic is not None
            else TaskProposalEngine()
        )
        self._validator = (
            validator if validator is not None
            else TaskProposalValidator(
                confidence_threshold=confidence_threshold
            )
        )
        self._threshold = float(confidence_threshold)
        self._trace = trace
        self._prompt_builder = prompt_builder

    # ------------------------------------------------------------ 提案

    def propose(
        self,
        gap: Any,
        context: Any = None,
        provider: Optional[ReasoningProvider] = None,
        existing_tasks: Optional[list[dict[str, Any]]] = None,
        dag: Any = None,
        *,
        replan_count: Optional[int] = None,
        max_replan: int = 5,
        trace: Any = None,
    ) -> LLMTaskProposalResult:
        """LLM 优先任务提案 (设计 §5) → LLMTaskProposalResult (永不抛)。

        gap:            触发缺口 (GapAnalysis/dict — 鸭子类型);
        context:        项目上下文 (prompt 面);
        provider:       单次调用覆盖 provider;
        existing_tasks: 已有计划任务列表 (id 推导 + Validator 面);
        dag:            依赖图 (鸭子类型 cycle_detect — Validator 检查 6);
        replan_count/max_replan: Validator 检查 12 (重规划预算);
        trace:          单次调用覆盖 trace 实例。
        """
        start = time.monotonic()
        prov = provider if provider is not None else self._provider
        prompt = self._build_prompt(gap, context)
        pid, model = self._identity(prov)
        fallback_reason = ""

        # ---- 1. LLM 优先
        try:
            raw = prov.propose_task(gap, self._llm_context(gap, context, prompt))
            outcome = self._gate(raw, gap, existing_tasks, dag, replan_count,
                                 max_replan)
            if outcome["proposal"] is not None:
                proposal = outcome["proposal"]
                latency = round(time.monotonic() - start, 4)
                self._record_trace(
                    trace, prompt, raw, proposal,
                    fallback_used=False, provider=pid, model=model,
                    latency=latency, validation=outcome["validation"],
                    source="llm",
                )
                return LLMTaskProposalResult(
                    proposal=proposal,
                    fallback_used=False,
                    source="llm",
                    reason="LLM 结构化输出通过 Validator gate",
                    validation_result=outcome["validation"],
                    provider=pid,
                    model=model,
                    raw_output=raw,
                    confidence=proposal.confidence,
                    latency=latency,
                )
            fallback_reason = "LLM 提案未过 gate: " + "; ".join(
                outcome["reasons"]
            )
        except ReasoningUnavailable as exc:
            fallback_reason = f"LLM 不可用: {exc}"
        except ReasoningError as exc:
            fallback_reason = f"LLM 失败: {exc}"
        except Exception as exc:  # noqa: BLE001 — 未知异常 → fallback
            fallback_reason = f"LLM 异常: {exc}"

        # ---- 2. fallback deterministic (设计 §8 — LLM 挂不影响系统)
        return self._fallback(gap, existing_tasks, dag, replan_count,
                              max_replan, fallback_reason, start,
                              trace=trace, provider=pid, model=model)

    # ------------------------------------------------------------ gate

    def _gate(
        self,
        raw: Any,
        gap: Any,
        existing_tasks: Optional[list[dict[str, Any]]],
        dag: Any,
        replan_count: Optional[int],
        max_replan: int,
    ) -> dict[str, Any]:
        """LLM 输出 deterministic gate: WHY/HOW/DEPENDENCY + Validator 12 项。

        ① 非 dict → reject; ② task_id 空 → 系统侧推导 (T0XX 递增, 冲突
        检查 — LLM 不决定 id); ③ WHY (rationale 非空) / HOW
        (acceptance_criteria 非空) / DEPENDENCY (dependencies 字符串列表)
        完整性 gate; ④ TaskProposalValidator.validate (12 项 — role/dup/
        cycle/confidence/replan limit)。任一失败 → {proposal: None, reasons}。
        """
        reasons: list[str] = []
        if not isinstance(raw, dict):
            return {
                "proposal": None,
                "reasons": [f"输出非 dict: {type(raw).__name__}"],
                "validation": {"valid": False, "reasons": [
                    f"输出非 dict: {type(raw).__name__}"]},
            }
        try:
            proposal = TaskProposal.from_dict(raw)
        except Exception as exc:  # noqa: BLE001 — 结构异常 → gate 拒绝
            return {
                "proposal": None,
                "reasons": [f"TaskProposal 结构异常: {exc}"],
                "validation": {"valid": False, "reasons": [
                    f"TaskProposal 结构异常: {exc}"]},
            }

        # ---- task_id 系统侧决定 (Enforcement — 设计 §1)
        if not str(proposal.task_id or "").strip():
            sid = self._source_task_id(gap)
            proposal.task_id = self._next_task_id(existing_tasks, sid)

        # ---- WHY/HOW/DEPENDENCY 完整性 gate (设计 §5)
        if not str(proposal.rationale or "").strip():
            reasons.append("rationale 为空 (WHY 缺失 — 必须解释解决 GAP)")
        crits = [
            str(c).strip() for c in (proposal.acceptance_criteria or [])
            if c and not isinstance(c, dict)
        ]
        if not crits:
            reasons.append("acceptance_criteria 为空 (HOW 缺失 — 必须描述"
                           "验证完成)")
        deps = proposal.dependencies or []
        if not isinstance(deps, list) or any(
            not isinstance(d, str) for d in deps
        ):
            reasons.append("dependencies 必须为字符串列表 (DEPENDENCY 缺失)")

        # ---- Validator 12 项 deterministic gate (设计 §7)
        validation = self._validator.validate(
            proposal, existing_tasks, dag, replan_count, int(max_replan)
        )
        reasons.extend(validation["reasons"])
        if reasons:
            return {
                "proposal": None,
                "reasons": reasons,
                "validation": validation,
            }
        return {
            "proposal": proposal,
            "reasons": [],
            "validation": validation,
        }

    # ------------------------------------------------------------ fallback

    def _fallback(
        self,
        gap: Any,
        existing_tasks: Optional[list[dict[str, Any]]],
        dag: Any,
        replan_count: Optional[int],
        max_replan: int,
        reason: str,
        start: float,
        *,
        trace: Any,
        provider: str,
        model: str,
    ) -> LLMTaskProposalResult:
        """deterministic fallback (设计 §8): TaskProposalEngine.propose →
        Validator → 再失败 REQUEST_REVIEW (proposal=None)。永不抛。"""
        latency = round(time.monotonic() - start, 4)
        validation: dict[str, Any] = {"valid": False, "reasons": []}
        try:
            proposal = self._deterministic.propose(gap, existing_tasks, dag)
        except Exception as exc:  # noqa: BLE001 — deterministic 异常 → REVIEW
            reason = f"{reason}; deterministic 异常: {exc}"
            validation = {"valid": False,
                          "reasons": [f"deterministic 异常: {exc}"]}
            self._record_trace(
                trace, "", None, None, fallback_used=True, provider=provider,
                model=model, latency=latency, validation=validation,
                source="request_review",
            )
            return LLMTaskProposalResult(
                proposal=None, fallback_used=True,
                source="request_review", reason=reason,
                validation_result=validation, provider=provider,
                model=model, latency=latency,
            )
        if proposal is None:
            # 无模板 (architecture_gap/unknown/validation_failure) → REVIEW
            reason = (
                (reason or "LLM 未产生有效输出")
                + "; deterministic 无模板 → REQUEST_REVIEW"
            )
            validation = {
                "valid": False,
                "reasons": ["deterministic 无模板 (REQUEST_REVIEW 路径)"],
            }
            self._record_trace(
                trace, "", None, None, fallback_used=True, provider=provider,
                model=model, latency=latency, validation=validation,
                source="request_review",
            )
            return LLMTaskProposalResult(
                proposal=None, fallback_used=True,
                source="request_review", reason=reason,
                validation_result=validation, provider=provider,
                model=model, latency=latency,
            )
        validation = self._validator.validate(
            proposal, existing_tasks, dag, replan_count, int(max_replan)
        )
        if not validation["valid"]:
            reason = (
                (reason or "LLM 未产生有效输出")
                + "; deterministic 提案被 Validator 拒绝: "
                + "; ".join(validation["reasons"])
            )
        else:
            reason = (
                (reason or "LLM 未产生有效输出")
                + "; deterministic 提案通过 Validator"
            )
        self._record_trace(
            trace, "", None, proposal, fallback_used=True, provider=provider,
            model=model, latency=latency, validation=validation,
            source="deterministic" if validation["valid"]
            else "request_review",
        )
        return LLMTaskProposalResult(
            proposal=proposal if validation["valid"] else None,
            fallback_used=True,
            source="deterministic" if validation["valid"]
            else "request_review",
            reason=reason,
            validation_result=validation,
            provider=provider,
            model=model,
            confidence=proposal.confidence,
            latency=latency,
        )

    # ------------------------------------------------------------ 内部

    def _build_prompt(self, gap: Any, context: Any) -> str:
        """prompt 组装: 自定义 prompt_builder 优先; 默认 (gap + 上下文 +
        WHY/HOW/DEPENDENCY 要求 — 设计 §5)。"""
        if self._prompt_builder is not None:
            return str(self._prompt_builder(gap, context))
        lines: list[str] = [
            "你是 AI Software Factory 的规划推理引擎。针对缺口生成任务"
            "提案, 只输出严格 JSON。",
            "必须解释: WHY (rationale 说明该任务如何解决 GAP) / HOW "
            "(acceptance_criteria 说明如何验证完成) / DEPENDENCY "
            "(dependencies 说明依赖原因, 依赖任务必须存在)",
        ]
        lines.append("触发缺口 (JSON):")
        lines.append(_compact_json(gap))
        lines.append("项目上下文 (JSON):")
        lines.append(_compact_json(self._llm_context(gap, context, "")))
        return "\n".join(lines)

    def _llm_context(
        self, gap: Any, context: Any, prompt: str
    ) -> dict[str, Any]:
        """LLM 输入上下文: 项目上下文 + 缺口摘要 (gap 字段)。"""
        ctx = dict(context) if isinstance(context, dict) else {}
        if isinstance(gap, dict):
            ctx["gap"] = dict(gap)
        else:
            ctx["gap"] = self._gap_dict(gap)
        if prompt and "prompt" not in ctx:
            ctx["prompt"] = prompt
        return ctx

    @classmethod
    def _gap_dict(cls, gap: Any) -> dict[str, Any]:
        """GapAnalysis → dict (prompt; 非预期 → 空)。"""
        if isinstance(gap, dict):
            return dict(gap)
        if hasattr(gap, "to_dict"):
            try:
                d = gap.to_dict()
                return dict(d) if isinstance(d, dict) else {}
            except Exception:  # noqa: BLE001
                return {}
        return {}

    @staticmethod
    def _source_task_id(gap: Any) -> str:
        """缺口来源任务 id (task_id 推导冲突面)。"""
        if isinstance(gap, dict):
            return str(gap.get("source_task_id") or "")
        return str(getattr(gap, "source_task_id", "") or "")

    @staticmethod
    def _next_task_id(
        existing_tasks: Optional[list[dict[str, Any]]],
        source_task_id: str,
    ) -> str:
        """T0XX 递增 task_id (系统侧决定 — 复用 deterministic 推导语义)。"""
        return TaskProposalEngine._next_task_id(  # noqa: SLF001 — 同仓复用
            existing_tasks, source_task_id
        )

    @staticmethod
    def _identity(provider: Any) -> tuple[str, str]:
        """provider 身份 (fallback trace 用; 不可用 → 空)。"""
        try:
            if hasattr(provider, "_resolve_identity"):
                return provider._resolve_identity()  # noqa: SLF001 — 同包
            if hasattr(provider, "provider_id"):
                return str(provider.provider_id), ""
        except Exception:  # noqa: BLE001 — 失败安全
            pass
        return "", ""

    def _record_trace(
        self,
        trace: Any,
        prompt: str,
        raw: Any,
        proposal: Optional[TaskProposal],
        *,
        fallback_used: bool,
        provider: str,
        model: str,
        latency: float,
        validation: dict[str, Any],
        source: str,
    ) -> None:
        """可选 trace 落盘 (设计 §9 — 白名单 + 脱敏, 失败安全)。"""
        t = trace if trace is not None else self._trace
        if t is None:
            return
        try:
            t.record(
                operation=OPERATION_PROPOSE_TASK,
                provider=provider or ("deterministic" if fallback_used else ""),
                model=model,
                input=prompt if prompt else (proposal.to_dict() if proposal
                                             else {"gap": ""}),
                output=raw,
                parsed_result=proposal.to_dict() if proposal else None,
                confidence=proposal.confidence if proposal else 0.0,
                latency=latency,
                fallback_used=fallback_used,
                validation_result=validation,
                final_decision=proposal.task_id if proposal
                else "REQUEST_REVIEW",
            )
        except Exception:  # noqa: BLE001 — trace 失败不影响提案 (失败安全)
            pass


def _compact_json(obj: Any) -> str:
    """紧凑 JSON 序列化 (prompt; 失败安全 → str)。"""
    import json

    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                          default=str)
    except Exception:  # noqa: BLE001
        return str(obj)
