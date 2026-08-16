"""factory-console/session/llm_gap.py — LLMGapAnalyzer (S10-062 批次 B)。

LLM Gap 分析器 (GAP G1, 设计 §4): LLM 优先 — 上下文 + 任务上下文证据 →
ReasoningProvider.analyze_gap → 结构化 GapAnalysis; 失败 (API error /
timeout / invalid JSON / schema error / deterministic 校验失败 /
confidence 低于阈值 / 重复缺口) → fallback deterministic GapAnalyzer
(S10-061 信号词规则) → 再失败 → REQUEST_REVIEW (unknown gap — 安全兜底,
设计 §8 fallback 链)。LLM 挂不影响系统。

LLMGapResult — 分析结果包装 {analysis: GapAnalysis, fallback_used, source,
reason, provider, model, raw_output, validation_result, confidence,
latency}: fallback_used 标记供 PlanningTrace (设计 §9)。

deterministic gate (LLM 输出过门 — 设计 §7/§8):
- schema 面: detected/gap_type/severity/confidence/recommended_action 存在
- 合法面: gap_type ∈ GapAnalyzer.GAP_TYPES; severity ∈ SEVERITIES;
  recommended_action ∈ ACTIONS; confidence ∈ [0.0, 1.0]
- 阈值面: detected=true 时 confidence ≥ 阈值 (缺省 0.5) → 否则 fallback
- 防重面: 相同 (source_task_id, gap_type) 已在历史分析/prev_decisions
  INSERT_TASK → duplicate_of 标记 (GAP G6); LLM 自报重复 → 采用

输入:
- context: AutonomousPlanningContext (或任意项目上下文 dict — prompt 面)
- task_context: 执行上下文 {task, result, validation, artifacts,
  agent_output, failures, existing_tasks, dag, prev_decisions, workspace}
  (evidence 提取 + deterministic fallback 输入面)

边界 (批次 B):
- 纯标准库 + 只读引用 session/gap_analyzer (GapAnalysis/GapAnalyzer) +
  session/reasoning (ReasoningProvider/ReasoningError); 零新依赖,
  不修改任何现有模块; 不落盘 (trace 由调用方注入 PlanningTrace)
- 禁真实网络/LLM (测试用 llm_fn deterministic fixture; 真实 LLM 留 Pilot)

设计: docs/sprint10/S10-062-llm-planning-design.md §4/§7/§8/§9
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .gap_analyzer import GapAnalysis, GapAnalyzer
from .reasoning import (
    OPERATION_ANALYZE_GAP,
    ReasoningError,
    ReasoningProvider,
    ReasoningUnavailable,
)

#: confidence 阈值 (detected=true 的 LLM gap 低于此值 → fallback — 设计 §12)
DEFAULT_CONFIDENCE_THRESHOLD = 0.5


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式。"""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LLMGapResult:
    """LLM Gap 分析结果 (fallback_used 标记供 trace — 设计 §9)。

    analysis:       最终 GapAnalysis (LLM 或 deterministic 或 REQUEST_REVIEW)
    fallback_used:  是否走了 fallback (LLM 失败/校验不过/低 confidence)
    source:         "llm" | "deterministic" | "request_review" (决策来源)
    reason:         来源原因 (LLM 失败原因 / 校验失败原因 / 兜底说明)
    provider:       provider id (LLM 路径; fallback → deterministic 名)
    model:          model id (LLM 路径)
    raw_output:     LLM 原始输出 (供 trace/审计)
    validation_result: deterministic gate 结果 {valid, reasons}
    confidence:     analysis.confidence (便捷访问)
    token_usage:    LLM 调用 token 用量 (未统计 → 空)
    latency:        分析耗时 (秒)
    """

    analysis: GapAnalysis = field(default_factory=GapAnalysis)
    fallback_used: bool = False
    source: str = "llm"
    reason: str = ""
    provider: str = ""
    model: str = ""
    raw_output: Any = None
    validation_result: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    token_usage: dict[str, int] = field(default_factory=dict)
    latency: float = 0.0


class LLMGapAnalyzer:
    """LLM 优先 Gap 分析器 (设计 §4): analyze → LLMGapResult。

    analyze(context, task_context, provider) — ① prompt (context + 证据);
    ② provider.analyze_gap → 结构化输出; ③ schema + deterministic 校验
    (gap_type/confidence/action 合法面 + 阈值 + 防重); ④ 成功 → GapAnalysis
    (source="llm"); 失败 → fallback deterministic GapAnalyzer.analyze
    (source="deterministic", fallback_used=True); 再失败 → REQUEST_REVIEW
    unknown gap (source="request_review")。永不抛 (失败安全 — LLM 挂不
    影响系统)。

    构造 (全部可注入):
    - provider: ReasoningProvider (缺省自建 — llm_fn=None 时默认装配,
      无真实 provider 时 analyze 直接走 fallback)
    - deterministic: GapAnalyzer (fallback 基础; file 可注入落盘面)
    - confidence_threshold: LLM gap confidence 阈值 (缺省 0.5)
    - trace: PlanningTrace 实例 (可选 — 每次分析落盘 trace)
    - prompt_builder: 可调用 (context, task_context) -> str — 自定义 prompt
      (缺省默认模板)
    """

    #: gap 类型合法面 (与 GapAnalyzer 对齐 — 设计 §7 同一 Gate)
    GAP_TYPES: tuple[str, ...] = GapAnalyzer.GAP_TYPES
    ACTIONS: tuple[str, ...] = GapAnalyzer.ACTIONS
    SEVERITIES: tuple[str, ...] = GapAnalyzer.SEVERITIES

    def __init__(
        self,
        *,
        provider: Optional[ReasoningProvider] = None,
        deterministic: Optional[GapAnalyzer] = None,
        file: Any = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        trace: Any = None,
        prompt_builder: Optional[Any] = None,
    ) -> None:
        self._provider = provider if provider is not None else ReasoningProvider()
        self._deterministic = (
            deterministic if deterministic is not None
            else GapAnalyzer(file=file)
        )
        self._threshold = float(confidence_threshold)
        self._trace = trace
        self._prompt_builder = prompt_builder

    # ------------------------------------------------------------ 分析

    def analyze(
        self,
        context: Any = None,
        task_context: Any = None,
        provider: Optional[ReasoningProvider] = None,
        *,
        prev_decisions: Optional[list[dict[str, Any]]] = None,
        trace: Any = None,
    ) -> LLMGapResult:
        """LLM 优先 Gap 分析 (设计 §4) → LLMGapResult (永不抛)。

        context:      项目/规划上下文 (prompt 面);
        task_context: 执行上下文 dict {task, result, validation, artifacts,
                      agent_output, failures, existing_tasks, dag,
                      prev_decisions, workspace} — evidence + fallback 面;
        provider:     单次调用覆盖 provider (缺省构造注入);
        prev_decisions: 历史重规划决策 (防重面; 缺省取 task_context);
        trace:        单次调用覆盖 trace 实例。
        """
        start = time.monotonic()
        tc = task_context if isinstance(task_context, dict) else {}
        decisions = prev_decisions if prev_decisions is not None else tc.get(
            "prev_decisions"
        )
        decisions = [d for d in (decisions or []) if isinstance(d, dict)]
        prov = provider if provider is not None else self._provider
        llm_ctx = self._llm_context(context, tc, "")
        prompt = self._build_prompt(llm_ctx, tc)
        llm_ctx["prompt"] = prompt  # 最终 LLM 输入 = 上下文 + 证据 + prompt
        pid, model = self._identity(prov)
        fallback_reason = ""

        # ---- 1. LLM 优先
        try:
            raw = prov.analyze_gap(llm_ctx)
            result = self._gate(raw, tc, decisions)
            if result["valid"]:
                analysis = self._to_analysis(raw, result["duplicate_of"])
                latency = round(time.monotonic() - start, 4)
                self._record_trace(
                    trace, prompt, raw, analysis, fallback_used=False,
                    provider=pid, model=model, latency=latency,
                    validation=result,
                )
                return LLMGapResult(
                    analysis=analysis,
                    fallback_used=False,
                    source="llm",
                    reason="LLM 结构化输出通过 deterministic gate",
                    provider=pid,
                    model=model,
                    raw_output=raw,
                    validation_result=result,
                    confidence=analysis.confidence,
                    latency=latency,
                )
            fallback_reason = "LLM 输出未过 deterministic gate: " + "; ".join(
                result["reasons"]
            )
        except ReasoningUnavailable as exc:
            fallback_reason = f"LLM 不可用: {exc}"
        except ReasoningError as exc:
            fallback_reason = f"LLM 失败: {exc}"
        except Exception as exc:  # noqa: BLE001 — 未知异常 → fallback
            fallback_reason = f"LLM 异常: {exc}"

        # ---- 2. fallback deterministic (LLM 挂不影响系统 — 设计 §8)
        return self._fallback(tc, decisions, fallback_reason, start,
                              trace=trace, provider=pid, model=model)

    # ------------------------------------------------------------ gate

    def _gate(
        self,
        raw: Any,
        tc: dict[str, Any],
        prev_decisions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """LLM 输出 deterministic gate (设计 §7/§8): {valid, reasons, ...}。

        检查: ① dict; ② detected bool; ③ gap_type/severity/action 合法面;
        ④ confidence ∈ [0,1] 且 detected 时 ≥ 阈值; ⑤ description 非空
        (detected); ⑥ 防重 (相同 source_task_id+gap_type 已分析 /
        prev_decisions INSERT_TASK → duplicate_of)。失败 → valid=False。
        """
        reasons: list[str] = []
        if not isinstance(raw, dict):
            return {"valid": False,
                    "reasons": [f"输出非 dict: {type(raw).__name__}"]}
        detected = raw.get("detected")
        if not isinstance(detected, bool):
            reasons.append(f"detected 必须为 bool (got {detected!r})")
        gtype = str(raw.get("gap_type") or "")
        if gtype and gtype not in self.GAP_TYPES:
            reasons.append(f"gap_type {gtype!r} 不合法")
        sev = str(raw.get("severity") or "")
        if sev and sev not in self.SEVERITIES:
            reasons.append(f"severity {sev!r} 不合法")
        action = str(raw.get("recommended_action") or "")
        if action and action not in self.ACTIONS:
            reasons.append(f"recommended_action {action!r} 不合法")
        conf = self._conf(raw.get("confidence"))
        if conf is None:
            reasons.append("confidence 必须为 0.0-1.0 数字")
        elif detected and conf < self._threshold:
            reasons.append(
                f"confidence={conf} < 阈值 {self._threshold} (低 confidence → "
                "fallback/REQUEST_REVIEW)"
            )
        if detected and not str(raw.get("description") or "").strip():
            reasons.append("detected=true 时 description 不能为空")

        dup = self._find_duplicate(gtype, str(raw.get("source_task_id") or ""),
                                   prev_decisions)
        if not reasons and detected and dup:
            # LLM 输出本身重复 → 标记 duplicate_of (不拒绝 — 防重语义合并)
            return {
                "valid": True,
                "reasons": [],
                "duplicate_of": dup,
                "note": f"该缺口已由 {dup} 处理过 (duplicate_of)",
            }
        return {
            "valid": not reasons,
            "reasons": reasons,
            "duplicate_of": None,
        }

    def _find_duplicate(
        self,
        gtype: str,
        sid: str,
        prev_decisions: list[dict[str, Any]],
    ) -> Optional[str]:
        """防重 (GAP G6, 同 GapAnalyzer._find_duplicate 语义): 相同
        (source_task_id, gap_type) 已在历史分析或 prev_decisions 已对该
        source INSERT_TASK → 返回重复归属 id; 无 → None。"""
        if not sid or not gtype:
            return None
        for p in self._deterministic.previous_analyses():
            if (
                p.get("source_task_id") == sid
                and p.get("gap_type") == gtype
                and p.get("detected")
            ):
                return str(p.get("source_task_id") or sid)
        for d in prev_decisions:
            if (
                d.get("decision") == "INSERT_TASK"
                and sid in (d.get("affected_tasks") or [])
            ):
                return sid
        return None

    # ------------------------------------------------------------ fallback

    def _fallback(
        self,
        tc: dict[str, Any],
        prev_decisions: list[dict[str, Any]],
        reason: str,
        start: float,
        *,
        trace: Any,
        provider: str,
        model: str,
    ) -> LLMGapResult:
        """deterministic fallback (设计 §8): GapAnalyzer.analyze →
        REQUEST_REVIEW (再失败 — 安全兜底)。永不抛。"""
        try:
            gap = self._deterministic.analyze(
                project=self._project_value(tc),
                workspace=tc.get("workspace"),
                task=tc.get("task"),
                result=tc.get("result"),
                validation=tc.get("validation"),
                artifacts=tc.get("artifacts"),
                agent_output=tc.get("agent_output"),
                failures=tc.get("failures"),
                existing_tasks=tc.get("existing_tasks"),
                dag=tc.get("dag"),
                prev_decisions=prev_decisions,
            )
        except Exception as exc:  # noqa: BLE001 — deterministic 异常 → REVIEW
            gap = GapAnalysis(
                detected=True,
                gap_type="unknown",
                description="缺口分析失败: deterministic fallback 异常, "
                            "需人工评审",
                evidence=["deterministic GapAnalyzer 异常: "
                          f"{str(exc)[:120]}"],
                severity="medium",
                confidence=0.4,
                recommended_action="REQUEST_REVIEW",
                reason="LLM 与 deterministic 均失败 — 安全兜底, 需人工评审 "
                       "(REQUEST_REVIEW)",
                timestamp=_now_iso(),
            )
            fallback_reason = f"{reason}; deterministic 异常: {exc}"
        else:
            fallback_reason = reason or "LLM 未产生有效输出"
            # 兜底确认: 无缺口且无信号 → 保持 NO_ACTION (deterministic 语义)
        latency = round(time.monotonic() - start, 4)
        self._record_trace(
            trace, "", None, gap, fallback_used=True, provider=provider,
            model=model, latency=latency,
            validation={"valid": False, "reasons": [fallback_reason]},
        )
        source = "deterministic" if gap.recommended_action != "REQUEST_REVIEW" \
            else "request_review"
        return LLMGapResult(
            analysis=gap,
            fallback_used=True,
            source=source,
            reason=fallback_reason,
            provider=provider,
            model=model,
            validation_result={"valid": False, "reasons": [fallback_reason]},
            confidence=gap.confidence,
            latency=latency,
        )

    # ------------------------------------------------------------ 内部

    def _build_prompt(self, context: Any, tc: dict[str, Any]) -> str:
        """prompt 组装: 自定义 prompt_builder 优先; 默认 (context + evidence)。

        context 为已增强上下文 (含 evidence 证据列表 — 与 LLM 实际输入一致)。"""
        if self._prompt_builder is not None:
            return str(self._prompt_builder(context, tc))
        lines: list[str] = [
            "你是 AI Software Factory 的规划推理引擎。分析执行上下文中的 "
            "缺口, 只输出严格 JSON。",
        ]
        lines.append("上下文 (JSON):")
        lines.append(_compact_json(self._llm_context(context, tc, "")))
        return "\n".join(lines)

    def _llm_context(
        self, context: Any, tc: dict[str, Any], prompt: str
    ) -> dict[str, Any]:
        """LLM 输入上下文: 项目上下文 + 执行证据 (evidence 列表)。"""
        ctx = dict(context) if isinstance(context, dict) else {}
        ctx["evidence"] = self._extract_evidence(tc)
        if prompt and "prompt" not in ctx:
            ctx["prompt"] = prompt
        return ctx

    @classmethod
    def _extract_evidence(cls, tc: dict[str, Any]) -> list[str]:
        """任务上下文 → evidence 字符串列表 (prompt 证据面 — 设计 §4
        Evidence First)。失败安全 (非预期结构 → 空)。"""
        out: list[str] = []
        validation = tc.get("validation")
        if isinstance(validation, dict) and "success" in validation:
            out.append(f"validation.success={bool(validation.get('success'))}")
            errors = validation.get("errors")
            if isinstance(errors, list):
                for e in errors[:3]:
                    out.append(f"validation.error: {str(e)[:200]}")
        result = tc.get("result")
        if isinstance(result, dict):
            for key in ("agent_output", "output", "error"):
                val = result.get(key)
                if val is not None and str(val).strip():
                    out.append(f"{key}: {str(val)[:200]}")
                    break
        agent_output = tc.get("agent_output")
        if agent_output is not None and str(agent_output).strip():
            out.append(f"agent_output: {str(agent_output)[:200]}")
        failures = tc.get("failures")
        if isinstance(failures, list):
            for f in failures[:3]:
                if isinstance(f, dict):
                    out.append(
                        f"failures: {f.get('task_id')} ({f.get('name')}) — "
                        f"{str(f.get('error') or '')[:120]}"
                    )
        task = tc.get("task")
        if isinstance(task, dict):
            out.append(f"task: {task.get('id')} ({task.get('name')})")
        if not out:
            out.append("无额外执行证据")
        return out

    @staticmethod
    def _project_value(tc: dict[str, Any]) -> Any:
        """task_context 内 project (AutonomousPlanningContext 包装兼容)。"""
        project = tc.get("project")
        if isinstance(project, dict) and "value" in project and "source" in project:
            return project["value"]
        return project

    @staticmethod
    def _conf(value: Any) -> Optional[float]:
        """confidence 校验: 数字且 ∈ [0,1] → float; 否则 None。"""
        if isinstance(value, bool):
            return None
        try:
            conf = float(value)
        except (TypeError, ValueError):
            return None
        return conf if 0.0 <= conf <= 1.0 else None

    @classmethod
    def _to_analysis(
        cls, raw: dict[str, Any], duplicate_of: Optional[str]
    ) -> GapAnalysis:
        """LLM 输出 dict → GapAnalysis (字段归一, 与 GapAnalyzer 同结构)。"""
        dup = duplicate_of
        if dup is None and raw.get("duplicate_of") is not None:
            dup = str(raw["duplicate_of"])
        return GapAnalysis(
            detected=bool(raw.get("detected")),
            gap_type=str(raw.get("gap_type") or ""),
            description=str(raw.get("description") or ""),
            evidence=[
                str(e) for e in (raw.get("evidence") or [])
                if not isinstance(e, dict)
            ],
            severity=str(raw.get("severity") or "low"),
            source_task_id=str(raw.get("source_task_id") or ""),
            confidence=round(float(raw.get("confidence") or 0.0), 2),
            duplicate_of=dup,
            recommended_action=str(raw.get("recommended_action")
                                   or "NO_ACTION"),
            reason=str(raw.get("reason") or ""),
            timestamp=_now_iso(),
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
        analysis: GapAnalysis,
        *,
        fallback_used: bool,
        provider: str,
        model: str,
        latency: float,
        validation: dict[str, Any],
    ) -> None:
        """可选 trace 落盘 (设计 §9 — 白名单 + 脱敏, 失败安全)。"""
        t = trace if trace is not None else self._trace
        if t is None:
            return
        try:
            t.record(
                operation=OPERATION_ANALYZE_GAP,
                provider=provider or ("deterministic" if fallback_used else ""),
                model=model,
                input=prompt if prompt else analysis.to_dict(),
                output=raw,
                parsed_result=analysis.to_dict(),
                confidence=analysis.confidence,
                latency=latency,
                fallback_used=fallback_used,
                validation_result=validation,
                final_decision=analysis.recommended_action,
            )
        except Exception:  # noqa: BLE001 — trace 失败不影响分析 (失败安全)
            pass


def _compact_json(obj: Any) -> str:
    """紧凑 JSON 序列化 (prompt; 失败安全 → str)。"""
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                          default=str)
    except Exception:  # noqa: BLE001
        return str(obj)
