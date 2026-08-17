"""factory-console/session/reasoning.py — ReasoningProvider (S10-062 批次 B)。

LLM Planning 抽象层 (GAP G4, 设计 §3): 统一 LLM 接口 — analyze_gap /
propose_task / evaluate_plan 三操作, 每个操作: prompt 组装 (JSON 指令 +
上下文) → llm_fn 调用 → 结构化输出解析 (_parse_json) → schema 校验 →
deterministic 校验 (合法面: gap_type/action/severity/role/command/priority/
decision/confidence) → dict 返回。

不硬编码模型 (设计 §3/§15): provider/model 从 LLMControlPlane 读取
(providers.json 装配 — factory-console/llm_control.py, 只读复用不重建);
llm_fn 可注入 (测试 deterministic fixture / 真实调用方提供)。

默认 llm_fn (llm_fn=None): 轻量复用 exec.cli 的 provider 装配 (_provider_registry
— LLMControlPlane 选中 provider → Adapter), 不重建 provider 系统; 无真实
provider 可用 (未配置/不可 import/调用失败) → 抛 ReasoningUnavailable /
ReasoningError, 由上层 LLMGapAnalyzer / LLMTaskProposalEngine fallback
(LLM 挂不影响系统 — 设计 §8 fallback 链)。

失败面 (设计 §8): API error / timeout / invalid JSON / schema error /
deterministic 校验失败 → 一律 ReasoningError (调用方捕获 → fallback)。

边界 (批次 B):
- 纯标准库 + 只读引用 session/gap_analyzer.GapAnalyzer (合法 gap_type/action/
  severity 面) + session/task_proposal (合法 role/command/priority 面) +
  session/replanning.ReplanningEngine (合法决策面) + session/planning_trace
  (可选 trace 记录); 零新依赖, 不修改任何现有模块
- 本模块不落盘、不改 DAG、不执行 (推理层只输出结构化建议)
- factory-exec 只经延迟 import 复用 (sys.path 挂载 — 同 session/actions.py 模式)

设计: docs/sprint10/S10-062-llm-planning-design.md §3/§8/§9/§15
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from .gap_analyzer import GapAnalyzer
from .replanning import ReplanningEngine
from .task_proposal import (
    VALID_PRIORITIES,
    VALID_ROLES,
    VALID_VALIDATION_COMMANDS,
)

# ---------------------------------------------------------------- 合法面

#: GapAnalysis schema 必需字段 (设计 §3 — 结构化输出契约)
GAP_SCHEMA_REQUIRED: tuple[str, ...] = (
    "detected", "gap_type", "description", "severity", "confidence",
    "recommended_action", "reason",
)

#: TaskProposal schema 必需字段 (设计 §5 — 结构化输出契约)
PROPOSAL_SCHEMA_REQUIRED: tuple[str, ...] = (
    "title", "description", "objective", "required_role", "dependencies",
    "acceptance_criteria", "validation_command", "source_gap", "rationale",
    "confidence", "priority",
)

#: ReplanDecision schema 必需字段 (设计 §3 — PLAN_EVALUATION 结构化输出契约)
REPLAN_SCHEMA_REQUIRED: tuple[str, ...] = ("decision", "reason")

#: 操作名 (trace.operation 口径 — 设计 §9)
OPERATION_ANALYZE_GAP = "analyze_gap"
OPERATION_PROPOSE_TASK = "propose_task"
OPERATION_EVALUATE_PLAN = "evaluate_plan"

#: JSON 提取正则 (markdown code fence 内 JSON / 裸 JSON 对象)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

#: 默认 max_tokens (结构化输出预算 — 推理层输出较短)
DEFAULT_MAX_TOKENS = 2048


class ReasoningError(Exception):
    """推理层失败 (API error / timeout / invalid JSON / schema error /
    deterministic 校验失败 — 设计 §8 fallback 触发面)。"""


class ReasoningUnavailable(ReasoningError):
    """无可用 LLM (未配置 provider / provider 不可 import / 装配失败)。

    语义: 不是单次调用失败, 而是整个推理通道不可用 — 上层直接走
    deterministic fallback (LLM 挂不影响系统)。"""


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式。"""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class ReasoningProvider:
    """统一 LLM 推理抽象 (设计 §3): 三操作 + 结构化输出 + 失败面。

    构造 (均可不传 — 全部可注入):
    - llm_fn: 可调用 (prompt: str, operation: str) -> str | dict — 测试注入
      deterministic fixture / 真实调用方提供; None → 内部默认 (复用
      exec.cli provider 装配, 无真实调用时抛 ReasoningUnavailable)
    - control_plane: LLMControlPlane 实例 (provider/model 身份来源;
      None → 延迟构造默认实例)
    - prompt_builder: 可调用 (operation: str, payload: dict) -> str — 自定义
      prompt 组装 (测试断言 prompt 内容 / 未来版本定制)
    - trace: PlanningTrace 实例 (可选 — 每次调用落盘 planning_trace.json,
      设计 §9)
    - max_tokens: 默认调用 token 预算

    analyze_gap(context) -> dict    — 结构化 GapAnalysis (schema 校验 +
    deterministic 校验: gap_type/severity/action/confidence 合法面)
    propose_task(gap, context) -> dict — 结构化 TaskProposal (schema 校验 +
    deterministic 校验: role/command/priority/confidence/rationale 合法面)
    evaluate_plan(context) -> dict  — 结构化 ReplanDecision (schema 校验 +
    deterministic 校验: decision ∈ 8 决策)

    失败: 一律 ReasoningError (或 ReasoningUnavailable) — 调用方捕获走
    fallback 链, 本层绝不静默降级/伪造输出。
    """

    #: 三操作名 (trace 口径)
    OPERATION_ANALYZE_GAP = OPERATION_ANALYZE_GAP
    OPERATION_PROPOSE_TASK = OPERATION_PROPOSE_TASK
    OPERATION_EVALUATE_PLAN = OPERATION_EVALUATE_PLAN

    def __init__(
        self,
        *,
        llm_fn: Optional[Callable[..., Any]] = None,
        control_plane: Any = None,
        prompt_builder: Optional[Callable[[str, dict[str, Any]], str]] = None,
        trace: Any = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        context_ledger: Any = None,
    ) -> None:
        self._llm_fn = llm_fn
        self._control_plane = control_plane
        self._prompt_builder = prompt_builder
        self._trace = trace
        self._context_ledger = context_ledger
        self._max_tokens = int(max_tokens)
        self._provider_id: str = ""
        self._model: str = ""

    # ------------------------------------------------------------ 三操作

    def analyze_gap(self, context: Any) -> dict[str, Any]:
        """请求 LLM 结构化 GapAnalysis (设计 §3) → dict。

        context: 上下文 dict (AutonomousPlanningContext 或任意项目上下文);
        经 prompt_builder/默认 builder 组装 prompt → llm_fn → 解析 → 校验。
        失败 → ReasoningError (调用方 fallback)。
        """
        payload = self._normalize_payload(context)
        return self._call(OPERATION_ANALYZE_GAP, payload, GAP_SCHEMA_REQUIRED,
                          self._validate_gap)

    def propose_task(self, gap: Any, context: Any) -> dict[str, Any]:
        """请求 LLM 结构化 TaskProposal (设计 §5) → dict。

        gap: 触发缺口 (GapAnalysis/dict — prompt 上下文); context: 项目
        上下文。WHY/HOW/DEPENDENCY 要求内置于 prompt 指令 (rationale 必须
        解释解决 GAP / acceptance_criteria 必须描述验证完成 / dependencies
        必须说明依赖原因)。
        """
        payload = self._normalize_payload(context)
        if isinstance(gap, dict):
            payload = {**payload, "gap": dict(gap)}
        else:
            payload = {**payload, "gap": self._gap_dict(gap)}
        return self._call(OPERATION_PROPOSE_TASK, payload,
                          PROPOSAL_SCHEMA_REQUIRED, self._validate_proposal)

    def evaluate_plan(self, context: Any) -> dict[str, Any]:
        """请求 LLM 结构化 ReplanDecision (设计 §3 — PLAN_EVALUATION) → dict。

        decision ∈ 8 计划级决策 (KEEP_PLAN/REORDER_TASKS/INSERT_TASK/
        MODIFY_TASK/BLOCK_TASK/SKIP_TASK/SPLIT_TASK/REQUEST_REVIEW)。
        """
        payload = self._normalize_payload(context)
        return self._call(OPERATION_EVALUATE_PLAN, payload,
                          REPLAN_SCHEMA_REQUIRED, self._validate_replan)

    # ------------------------------------------------------------ 调用

    def _call(
        self,
        operation: str,
        payload: dict[str, Any],
        schema: tuple[str, ...],
        validate: Callable[[dict[str, Any]], list[str]],
    ) -> dict[str, Any]:
        """操作执行管线: prompt → llm_fn → 解析 → schema → deterministic → 返回。

        llm_fn 返回 str (JSON 文本/含 fence) 或 dict (已解析 — fixture
        便捷); 任何失败 → ReasoningError/ReasoningUnavailable。
        """
        start = time.monotonic()
        prompt = self.build_prompt(operation, payload)
        # S10-071 P0-5: Context Budget 真实 gate — 超预算拒绝调用 (防 Context 无限增长)
        if self._context_ledger is not None:
            try:
                est = max(1, len(prompt) // 2)
                ok, reason = self._context_ledger.check(est)
                if not ok:
                    raise ReasoningError(
                        f"{operation}: Context 预算超限 ({est} tokens, {reason}) — 拒绝 LLM 调用"
                    )
            except ReasoningError:
                raise
            except Exception:  # noqa: BLE001 — 预算检查异常不阻断
                pass
        fn = self._llm_fn if self._llm_fn is not None else self._default_llm_fn()
        try:
            raw = fn(prompt, operation)
        except ReasoningError:
            raise
        except Exception as exc:  # noqa: BLE001 — 调用方异常 → 统一失败面
            raise ReasoningError(f"{operation}: LLM 调用异常: {exc}") from exc

        parsed = self._parse_json(raw)
        if not isinstance(parsed, dict):
            raise ReasoningError(f"{operation}: LLM 输出非 JSON 对象 "
                                 f"(类型 {type(parsed).__name__})")
        missing = [k for k in schema if k not in parsed]
        if missing:
            raise ReasoningError(f"{operation}: schema 缺字段: {missing}")
        problems = validate(parsed)
        if problems:
            raise ReasoningError(
                f"{operation}: deterministic 校验失败: {'; '.join(problems)}"
            )
        latency = round(time.monotonic() - start, 4)
        self._record_trace(operation, prompt, raw, parsed, latency)
        return parsed

    # ------------------------------------------------------------ prompt

    def build_prompt(self, operation: str, payload: dict[str, Any]) -> str:
        """prompt 组装: 自定义 prompt_builder 优先, 否则默认 JSON 指令模板。"""
        if self._prompt_builder is not None:
            return str(self._prompt_builder(operation, payload))
        return self._default_prompt(operation, payload)

    @classmethod
    def _default_prompt(
        cls, operation: str, payload: dict[str, Any]
    ) -> str:
        """默认 prompt: 操作指令 + JSON 契约 + 合法面 + 上下文 (紧凑 JSON)。"""
        lines: list[str] = [
            "你是 AI Software Factory 的规划推理引擎。只输出严格 JSON, "
            "不要输出任何额外文本。",
        ]
        if operation == OPERATION_ANALYZE_GAP:
            lines.append(
                "任务: 分析执行上下文中的缺口 (gap), 输出 GapAnalysis JSON: "
                '{"detected": bool, "gap_type": str, "description": str, '
                '"evidence": [str], "severity": str, "source_task_id": str, '
                '"confidence": float, "duplicate_of": str|null, '
                '"recommended_action": str, "reason": str}'
            )
            lines.append(
                "合法 gap_type: " + ", ".join(GapAnalyzer.GAP_TYPES)
            )
            lines.append(
                "合法 recommended_action: " + ", ".join(GapAnalyzer.ACTIONS)
            )
            lines.append(
                "合法 severity: " + ", ".join(GapAnalyzer.SEVERITIES)
                + "; confidence 必须 ∈ [0.0, 1.0]; 无缺口 → "
                'detected=false + recommended_action="NO_ACTION"'
            )
        elif operation == OPERATION_PROPOSE_TASK:
            lines.append(
                "任务: 针对缺口生成任务提案, 输出 TaskProposal JSON: "
                '{"title": str, "description": str, "objective": str, '
                '"required_role": str, "dependencies": [str], '
                '"acceptance_criteria": [str], "validation_command": str, '
                '"source_gap": str, "rationale": str, "confidence": float, '
                '"priority": str}'
            )
            lines.append(
                "必须解释: WHY (rationale 说明该任务如何解决 GAP) / HOW "
                "(acceptance_criteria 说明如何验证完成) / DEPENDENCY "
                "(dependencies 说明依赖原因, 依赖任务必须存在)"
            )
            lines.append(
                "合法 required_role: " + ", ".join(VALID_ROLES)
            )
            lines.append(
                "合法 validation_command: "
                + ", ".join(VALID_VALIDATION_COMMANDS)
                + "; 合法 priority: " + ", ".join(VALID_PRIORITIES)
                + "; confidence ∈ [0.0, 1.0]"
            )
        else:  # OPERATION_EVALUATE_PLAN
            lines.append(
                "任务: 评估当前计划, 输出 ReplanDecision JSON: "
                '{"decision": str, "reason": str, "affected_tasks": [str], '
                '"new_tasks": [dict], "modified_tasks": [dict], '
                '"dependency_changes": [dict], "execution_order": [str], '
                '"plan_version": int}'
            )
            lines.append(
                "合法 decision: " + ", ".join(ReplanningEngine.DECISIONS)
            )
        lines.append("上下文 (JSON):")
        lines.append(_compact_json(payload))
        return "\n".join(lines)

    # ------------------------------------------------------------ 解析/校验

    @classmethod
    def _parse_json(cls, raw: Any) -> Any:
        """结构化输出解析: str (裸 JSON / markdown fence) / dict / bytes。

        提取首个 JSON 对象 ({...}); 解析失败 → 返回原值 (调用方判定
        非 dict → ReasoningError)。dict 输入原样返回 (fixture 便捷)。
        """
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
    def _validate_gap(cls, d: dict[str, Any]) -> list[str]:
        """GapAnalysis deterministic 校验 (合法面 — 设计 §3/§8)。"""
        problems: list[str] = []
        detected = d.get("detected")
        if not isinstance(detected, bool):
            problems.append(f"detected 必须为 bool (got {detected!r})")
        gtype = str(d.get("gap_type") or "")
        if gtype and gtype not in GapAnalyzer.GAP_TYPES:
            problems.append(f"gap_type {gtype!r} 不合法")
        sev = str(d.get("severity") or "")
        if sev and sev not in GapAnalyzer.SEVERITIES:
            problems.append(f"severity {sev!r} 不合法")
        action = str(d.get("recommended_action") or "")
        if action and action not in GapAnalyzer.ACTIONS:
            problems.append(f"recommended_action {action!r} 不合法")
        conf = cls._confidence(d.get("confidence"))
        if conf is None:
            problems.append("confidence 必须为 0.0-1.0 数字")
        if detected and not str(d.get("description") or "").strip():
            problems.append("detected=true 时 description 不能为空")
        return problems

    @classmethod
    def _validate_proposal(cls, d: dict[str, Any]) -> list[str]:
        """TaskProposal deterministic 校验 (WHY/HOW/DEPENDENCY + 合法面)。"""
        problems: list[str] = []
        role = str(d.get("required_role") or "")
        if role not in VALID_ROLES:
            problems.append(f"required_role {role!r} 不合法")
        cmd = str(d.get("validation_command") or "")
        if cmd not in VALID_VALIDATION_COMMANDS:
            problems.append(f"validation_command {cmd!r} 不合法")
        prio = str(d.get("priority") or "")
        if prio not in VALID_PRIORITIES:
            problems.append(f"priority {prio!r} 不合法")
        conf = cls._confidence(d.get("confidence"))
        if conf is None:
            problems.append("confidence 必须为 0.0-1.0 数字")
        for key, label in (
            ("title", "title"),
            ("description", "description"),
            ("objective", "objective"),
        ):
            if not str(d.get(key) or "").strip():
                problems.append(f"{label} 不能为空")
        # WHY: rationale 必须解释解决 GAP (设计 §5)
        if not str(d.get("rationale") or "").strip():
            problems.append("rationale 为空 (WHY 缺失 — 必须解释解决 GAP)")
        # HOW: acceptance_criteria 必须描述验证完成 (设计 §5)
        crits = d.get("acceptance_criteria")
        if not isinstance(crits, list) or not crits or any(
            not str(c or "").strip() for c in crits
        ):
            problems.append("acceptance_criteria 为空 (HOW 缺失 — 必须描述"
                            "验证完成)")
        deps = d.get("dependencies")
        if not isinstance(deps, list) or any(
            not isinstance(x, str) for x in deps
        ):
            problems.append("dependencies 必须为字符串列表 (DEPENDENCY 缺失)")
        if not str(d.get("source_gap") or "").strip():
            problems.append("source_gap 不能为空 (必须标识触发缺口)")
        return problems

    @classmethod
    def _validate_replan(cls, d: dict[str, Any]) -> list[str]:
        """ReplanDecision deterministic 校验 (decision ∈ 8 决策)。"""
        problems: list[str] = []
        decision = str(d.get("decision") or "")
        if decision not in ReplanningEngine.DECISIONS:
            problems.append(f"decision {decision!r} 不合法")
        if not str(d.get("reason") or "").strip():
            problems.append("reason 不能为空")
        for key in ("affected_tasks", "execution_order"):
            val = d.get(key)
            if val is not None and not isinstance(val, list):
                problems.append(f"{key} 必须为列表")
        return problems

    @staticmethod
    def _confidence(value: Any) -> Optional[float]:
        """confidence 校验: 数字且 ∈ [0.0, 1.0] → float; 否则 None。"""
        if isinstance(value, bool):
            return None
        try:
            conf = float(value)
        except (TypeError, ValueError):
            return None
        if conf < 0.0 or conf > 1.0:
            return None
        return conf

    # ------------------------------------------------------------ 默认 llm_fn

    def _default_llm_fn(self) -> Callable[[str, str], str]:
        """默认 llm_fn: 复用 exec.cli provider 装配 (设计 §15 不重建)。

        装配链: LLMControlPlane.select() (providers.json enabled+key) →
        exec.cli._provider_registry (同一 ControlPlane 装配 → Adapter) →
        provider.generate(ProviderRequest)。无真实 provider → 抛
        ReasoningUnavailable (上层 fallback)。
        """
        try:
            pid, _model = self._resolve_identity()
            provider = self._assemble_provider(pid)
        except ReasoningUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 — 装配失败 → 不可用
            raise ReasoningUnavailable(f"LLM provider 装配失败: {exc}") from exc
        if provider is None:
            raise ReasoningUnavailable(
                "无可用 LLM provider (未配置 enabled provider 或无可用 Adapter)"
            )

        max_tokens = self._max_tokens

        def call(prompt: str, operation: str = "") -> str:
            """单次调用: ProviderRequest → ProviderResponse (error → 抛)。"""
            try:
                from exec.provider import ProviderRequest

                resp = provider.generate(
                    ProviderRequest(
                        task_context=str(prompt), max_tokens=max_tokens
                    )
                )
            except ReasoningError:
                raise
            except Exception as exc:  # noqa: BLE001 — 调用异常 → 失败面
                raise ReasoningError(
                    f"{operation or 'llm'}: 调用失败: {exc}"
                ) from exc
            if getattr(resp, "error", None):
                raise ReasoningError(
                    f"{operation or 'llm'}: provider error: {resp.error}"
                )
            return str(getattr(resp, "content", "") or "")

        return call

    def _resolve_identity(self) -> tuple[str, str]:
        """provider/model 身份 (模型名不硬编码 — 设计 §3/§15)。

        来源: 注入 control_plane → 默认 LLMControlPlane (providers.json) →
        空。缓存至实例 (首次解析)。"""
        if self._provider_id:
            return self._provider_id, self._model
        plane = self._control_plane
        if plane is None:
            try:
                from ..llm_control import LLMControlPlane

                plane = LLMControlPlane()
            except Exception:  # noqa: BLE001 — ControlPlane 不可用 → 空身份
                return "", ""
        try:
            sel = plane.select() if plane is not None else None
        except Exception:  # noqa: BLE001 — 失败安全: 身份解析失败 → 空
            sel = None
        if sel is not None:
            self._provider_id = str(getattr(sel, "provider_id", "") or "")
            self._model = str(getattr(sel, "model_id", "") or "")
        return self._provider_id, self._model

    @staticmethod
    def _assemble_provider(provider_id: str) -> Any:
        """exec.cli._provider_registry 装配 (factory-exec 延迟挂载 + import)。

        返回选中 provider Adapter (registry.get(provider_id)); 选中 id 无
        Adapter → 回退注册表首个; 无注册 → None (调用方判不可用)。"""
        root = Path(__file__).resolve().parents[2]  # 仓库根 (factory-exec 父目录)
        exec_path = root / "factory-exec"
        if str(exec_path) not in sys.path:
            sys.path.insert(0, str(exec_path))
        from exec.cli import _provider_registry  # 延迟 import (同 actions.py)

        registry = _provider_registry()
        provider = registry.get(provider_id) if provider_id else None
        if provider is None:
            providers = registry.list()
            provider = providers[0] if providers else None
        return provider

    # ------------------------------------------------------------ trace

    def _record_trace(
        self,
        operation: str,
        prompt: str,
        raw: Any,
        parsed: dict[str, Any],
        latency: float,
    ) -> None:
        """可选 trace 落盘 (设计 §9): 只经 PlanningTrace 白名单 + 脱敏。"""
        trace = self._trace
        if trace is None:
            return
        pid, model = self._resolve_identity()
        confidence = 0.0
        if operation == OPERATION_ANALYZE_GAP:
            confidence = parsed.get("confidence", 0.0)
        elif operation == OPERATION_PROPOSE_TASK:
            confidence = parsed.get("confidence", 0.0)
        try:
            trace.record(
                operation=operation,
                provider=pid,
                model=model,
                input=prompt,  # 只存 sha256 摘要 (不落原文)
                output=raw,
                parsed_result=parsed,
                confidence=confidence,
                latency=latency,
                fallback_used=False,
                final_decision=parsed.get("decision")
                or parsed.get("recommended_action") or parsed.get("title"),
            )
        except Exception:  # noqa: BLE001 — trace 失败不影响调用 (失败安全)
            pass

    # ------------------------------------------------------------ 内部

    @staticmethod
    def _normalize_payload(context: Any) -> dict[str, Any]:
        """上下文 → dict payload (非 dict → 空, 失败安全)。"""
        if isinstance(context, dict):
            return dict(context)
        if hasattr(context, "to_dict"):
            try:
                d = context.to_dict()
                return dict(d) if isinstance(d, dict) else {}
            except Exception:  # noqa: BLE001
                return {}
        return {}

    @staticmethod
    def _gap_dict(gap: Any) -> dict[str, Any]:
        """GapAnalysis → dict (prompt 上下文; 非预期 → 空)。"""
        if isinstance(gap, dict):
            return dict(gap)
        if hasattr(gap, "to_dict"):
            try:
                d = gap.to_dict()
                return dict(d) if isinstance(d, dict) else {}
            except Exception:  # noqa: BLE001
                return {}
        return {}


def _compact_json(obj: Any) -> str:
    """紧凑 JSON 序列化 (prompt 上下文; 失败安全 → str)。"""
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                          default=str)
    except Exception:  # noqa: BLE001 — 序列化失败 → 原样 str
        return str(obj)
