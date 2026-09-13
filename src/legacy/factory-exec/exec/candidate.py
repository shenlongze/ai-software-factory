"""factory-exec/exec/candidate.py — Candidate Execution Engine (Sprint 5 T5.2)。

多 Run 执行策略的核心数据结构 + 执行编排 (设计依据:
docs/validation/sprint5-t51-execution-strategy-design.md, T5.1 已冻结):

    Task → Run A ─┐
           Run B ─┼→ Candidate Results → (Evaluator T5.3) → Best Result
           Run C ─┘

本模块四件套 (KISS, 单文件):
- ExecutionCandidate: 单次 Run 的完整可审计记录 (任务/来源/上下文/成本/结果);
  可序列化 (to_dict/from_dict) + 可进 Experience (to_experience_signals)。
- ExecutionRun: Run 生命周期状态机 (pending → running → success|failed),
  非法迁移硬拒绝 (状态机校验)。
- CandidateCollector: 多 Run 候选收集 — 失败候选必须保存 (禁静默丢弃),
  failure_reason 必填 (失败不允许无声无息)。
- SequentialRunner: 默认 N=3 次独立顺序执行 (禁并发 — 单线程 for 循环,
  无 threading/asyncio); 每次 Run 独立 Provider 调用 (同一 Context,
  独立随机性 — 抗单次波动); Run 间状态记录; 异常 → 失败候选 (不中断收集)。

Experience Signal (T5.2 §6, 复用 T4.4 experience_ctx — 不重复建库):
- 成功候选 → ["candidate_success"];
- 失败候选 → 五类失败信号 (experience_ctx FAILURE_TYPES 词汇:
  symbol_miss / context_insufficient / token_overflow / operation_failure /
  validation_failure — 由候选失败原因映射, 同源词汇供未来学习/推荐)。

T5.3 边界: Best 选择由 CandidateEvaluator 承担 (exec/evaluator.py — 5 层
确定性评分, 禁 LLM/随机); 本模块只产候选 + 收集, 并在 T5.3 起把
SequentialRunner.select_result() 升级为经 Evaluator 的正式选择 (评估明细
经 last_evaluation 审计; 全失败 → 最后一个失败结果 + 诚实拒绝理由)。
候选携带 T5.3 各层评分证据 (patch_apply_result / scope_result /
regression_risk_result / requirement_coverage_result — 缺省 {} 中性,
产线不提供则评估层按 0 分处理, 不臆造)。

T5.4 边界 (Model Capability Registry, exec/capability.py):
- ExecutionCandidate.model_capability_snapshot: 候选保存时冻结 registry
  中该模型当前能力评分 ({"provider","model","scores","captured_at"}) —
  历史结果可解释 (模型能力后续变化不影响已保存候选; 无 registry/无该
  模型 → {} 中性, 不臆造);
- SequentialRunner 可选接线: capability_registry (→ 候选快照) +
  experience_stats (→ 每候选成功/失败计数 — 只统计不评分, 禁自动改分;
  复用 experience_ctx 词汇) — 缺省 None, 行为逐位不变 (不改执行流程)。

KISS 边界: 本模块只依赖 stdlib + pydantic + 本层 models/experience_ctx
(零 Core 导入); 不跑真实 Benchmark / 不接 Model Selection / 不改 Benchmark;
不落数据库 (Run 状态在内存, 审计走候选对象 + 既有事件链; Evaluator 评估
结果经 runner.last_evaluation 内存可审计, 不重复建库)。
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field, field_validator

from .capability import capability_snapshot
from .experience_ctx import (
    FAILURE_CONTEXT_INSUFFICIENT,
    FAILURE_OPERATION,
    FAILURE_TOKEN_OVERFLOW,
    FAILURE_VALIDATION,
    FAILURE_TYPES,
)
from .models import _ExecModel, new_id, utcnow

#: 成功/失败候选质量分 (0-100; 保守基线: 验证通过 80 / 失败 0 — 诚实不臆造
#: 精细评分; 精细排名由 T5.3 CandidateEvaluator 5 层确定性评分承担)。
QUALITY_SCORE_PASS = 80.0

# ---------------------------------------------------------------- 失败原因词汇

#: Candidate 失败原因词汇 (T5.2 §6: empty_output/token_limit/operation_error/
#: validation_failed + other 兜底; 失败候选 failure_reason 必填)。
CANDIDATE_REASON_EMPTY_OUTPUT = "empty_output"
CANDIDATE_REASON_TOKEN_LIMIT = "token_limit"
CANDIDATE_REASON_OPERATION_ERROR = "operation_error"
CANDIDATE_REASON_VALIDATION_FAILED = "validation_failed"
CANDIDATE_REASON_OTHER = "other"
CANDIDATE_FAILURE_REASONS: tuple[str, ...] = (
    CANDIDATE_REASON_EMPTY_OUTPUT,
    CANDIDATE_REASON_TOKEN_LIMIT,
    CANDIDATE_REASON_OPERATION_ERROR,
    CANDIDATE_REASON_VALIDATION_FAILED,
    CANDIDATE_REASON_OTHER,
)

#: Candidate 失败原因 → experience_ctx 五类失败信号 (T4.4 词汇映射)。
#: empty_output 归 token_overflow: T5.1 实测根因 — reasoning 模型单次生成耗尽
#: max_tokens (finish_reason=length) → 空响应, 空输出本质是 token 耗尽自愈缺口。
_CANDIDATE_REASON_TO_FAILURE: dict[str, str] = {
    CANDIDATE_REASON_EMPTY_OUTPUT: FAILURE_TOKEN_OVERFLOW,
    CANDIDATE_REASON_TOKEN_LIMIT: FAILURE_TOKEN_OVERFLOW,
    CANDIDATE_REASON_OPERATION_ERROR: FAILURE_OPERATION,
    CANDIDATE_REASON_VALIDATION_FAILED: FAILURE_VALIDATION,
    CANDIDATE_REASON_OTHER: FAILURE_CONTEXT_INSUFFICIENT,
}


def classify_candidate_failure(error: str) -> str:
    """异常/错误文本 → Candidate 失败原因词汇 (稳定子串匹配, 兜底 other)。

    失败不允许静默: 任何失败路径都必须产出非空 failure_reason — 调用方
    (SequentialRunner 异常路径 / candidate_from_result 失败结果) 用它归类。
    """
    if not error:
        return CANDIDATE_REASON_OTHER
    e = str(error).lower()
    if "empty content" in e or "empty response" in e or "produced no output" in e:
        return CANDIDATE_REASON_EMPTY_OUTPUT
    if (
        "token" in e
        or "max_tokens" in e
        or "finish_reason" in e
        or "context length" in e
        or "length" in e
        or "timed out" in e
    ):
        return CANDIDATE_REASON_TOKEN_LIMIT
    if "operation" in e or "symbol" in e or "location" in e or "no parseable patch" in e:
        return CANDIDATE_REASON_OPERATION_ERROR
    if (
        "validation" in e
        or "verifier failed" in e
        or "syntax" in e
        or "test failed" in e
        or "no parseable operations" in e
    ):
        return CANDIDATE_REASON_VALIDATION_FAILED
    return CANDIDATE_REASON_OTHER


def candidate_failure_signal(reason: str) -> str:
    """Candidate 失败原因 → experience_ctx 五类失败信号 (T4.4 词汇复用)。

    reason 已是 experience_ctx 失败类型 (symbol_miss 等) → 原样透传;
    否则按 _CANDIDATE_REASON_TO_FAILURE 映射; 未知 → context_insufficient 兜底。
    """
    if reason in FAILURE_TYPES:
        return reason
    return _CANDIDATE_REASON_TO_FAILURE.get(reason or "", FAILURE_CONTEXT_INSUFFICIENT)


# ================================================================ ExecutionCandidate

class ExecutionCandidate(_ExecModel):
    """单次 Run 的完整执行候选 (T5.2; 15+ 字段, 可序列化可审计)。

    字段 (任务 §1 全部实现):
    - id: 候选唯一 id (CAND-xxx);
    - task_id / run_id: 任务锚点 + 第几次执行 (run_id 必填, 审计锚点);
    - provider / model: 智能来源标识 (openai|anthropic|mock / 模型名);
    - context_trace / budget_trace: Sprint 4 上下文/预算决策 Trace (可审计
      \"为什么这么选\"; 缺省 {} — 运行时逐 Run 的完整 Trace 由 T4.4
      ContextExperienceRecord 另载, 不重复);
    - generated_output: 模型原始输出 (缺省空 — Runtime 路径不暴露 raw);
    - patch: 生成补丁文本 (成功候选的可应用产出);
    - reference: 参考/锚点 (任务引用或外部标识; 缺省空);
    - token_usage: Provider usage dict (prompt/completion/cost);
    - latency: 单次 Run 耗时 (秒, ≥0);
    - validation_result: 语法/测试/verifier 结果 dict;
    - quality_score: 0-100 (T5.3 Evaluator 前: 验证通过 80 / 失败 0);
    - failure_reason: 失败候选必填 (CANDIDATE_FAILURE_REASONS 词汇;
      空 = 成功候选 — is_success 判定);
    - patch_apply_result / scope_result / regression_risk_result /
      requirement_coverage_result: T5.3 Evaluator 各层评分证据 dict
      (② git apply/check 结果 / ③ 修改范围 / ④ 回归风险 / ⑤ 验收标准覆盖;
      缺省 {} — 产线不提供则评估层按 0 分中性处理, 不臆造);
    - model_capability_snapshot: T5.4 能力快照 dict (保存时冻结 registry
      中该模型当前能力评分 {"provider","model","scores","captured_at"} —
      历史结果可解释; 缺省 {} — 无 registry/无该模型中性, 不臆造);
    - created_at: UTC 时间戳 (序列化 round-trip 保留)。

    校验: id/run_id 必填; 容器字段 None → 默认; quality_score clamp [0,100];
    latency clamp ≥0; 时间戳 UTC (from_dict 兼容 ISO 字符串)。
    """

    id: str
    task_id: str = ""
    run_id: str
    provider: str = ""
    model: str = ""
    context_trace: dict[str, Any] = Field(default_factory=dict)
    budget_trace: dict[str, Any] = Field(default_factory=dict)
    generated_output: str = ""
    patch: str = ""
    reference: str = ""
    token_usage: dict[str, Any] = Field(default_factory=dict)
    latency: float = 0.0
    validation_result: dict[str, Any] = Field(default_factory=dict)
    quality_score: float = 0.0
    failure_reason: str = ""
    patch_apply_result: dict[str, Any] = Field(default_factory=dict)
    scope_result: dict[str, Any] = Field(default_factory=dict)
    regression_risk_result: dict[str, Any] = Field(default_factory=dict)
    requirement_coverage_result: dict[str, Any] = Field(default_factory=dict)
    model_capability_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator(
        "context_trace",
        "budget_trace",
        "token_usage",
        "validation_result",
        "patch_apply_result",
        "scope_result",
        "regression_risk_result",
        "requirement_coverage_result",
        "model_capability_snapshot",
        mode="before",
    )
    @classmethod
    def _dicts_none(cls, v: Any) -> Any:
        return v if v is not None else {}

    @field_validator("task_id", "provider", "model", "generated_output", "patch",
                     "reference", "failure_reason", mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> Any:
        return v if v is not None else ""

    @field_validator("quality_score", mode="before")
    @classmethod
    def _quality_clamp(cls, v: Any) -> float:
        try:
            value = float(v)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(100.0, value))

    @field_validator("latency", mode="before")
    @classmethod
    def _latency_nonneg(cls, v: Any) -> float:
        try:
            value = float(v)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, value)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionCandidate:
        """dict → 模型 (to_dict 的逆操作; created_at ISO 字符串 → datetime)。"""
        return cls.model_validate(data)

    @property
    def is_success(self) -> bool:
        """成功判定: 无失败原因即成功 (失败候选必带 failure_reason — Collector 强制)。"""
        return not self.failure_reason

    def to_experience_signals(self) -> list[str]:
        """经验信号 (T5.2 §6): 成功 → [candidate_success]; 失败 → 五类失败
        (experience_ctx T4.4 FAILURE_TYPES 词汇复用, 不重复建库)。"""
        if self.is_success:
            return ["candidate_success"]
        return [candidate_failure_signal(self.failure_reason)]


def candidate_from_result(
    result: Any,
    *,
    run_id: str,
    request: Any = None,
    provider: str = "",
    model: str = "",
    reference: str = "",
    context_trace: dict[str, Any] | None = None,
    budget_trace: dict[str, Any] | None = None,
    validation_result: dict[str, Any] | None = None,
    quality_score: float | None = None,
    failure_reason: str = "",
    latency: float = 0.0,
    capability_registry: Any = None,
) -> ExecutionCandidate:
    """ExecutionResult → ExecutionCandidate (Run 产出物化)。

    result: ExecutionResult 或 duck-typed (is_success/error/usage/artifacts)。
    - patch: 从 PATCH Artifact 文件读取 (path 存在时; 纯内存 → 空串);
    - token_usage: result.usage;
    - validation_result: 显式传入优先; 缺省 {"passed": result.is_success} —
      T5.2 运行时路径不暴露内部 ValidationResult 的保守代理 (真实验证明细
      在 test_result Artifact 与 T4.4 记录中);
    - quality_score: 显式传入优先; 缺省 80 (成功) / 0 (失败);
    - failure_reason: 显式传入优先; 失败结果缺省按 error 文本归类
      (classify_candidate_failure — 失败必带结构化原因, 禁静默);
    - capability_registry: T5.4 可选 — 保存时冻结该模型能力快照
      (capability_snapshot; 无 registry/无该模型 → {} 中性, 不臆造)。
    """
    success = bool(getattr(result, "is_success", False))
    task_id = getattr(request, "task_id", "") if request is not None else ""
    token_usage = dict(getattr(result, "usage", {}) or {})
    patch = ""
    for artifact in getattr(result, "artifacts", []) or []:
        if getattr(artifact, "type", None) is not None:
            from .models import ArtifactType

            if getattr(artifact, "type", None) == ArtifactType.PATCH:
                path = getattr(artifact, "path", "") or ""
                if path:
                    try:
                        p = Path(str(path))
                        if p.is_file():
                            patch = p.read_text(encoding="utf-8")
                    except OSError:  # pragma: no cover — 产物文件读失败 → 空 patch
                        patch = ""
                break
    vresult = (
        dict(validation_result) if validation_result is not None
        else {"passed": success}
    )
    qscore = (
        float(quality_score) if quality_score is not None
        else (QUALITY_SCORE_PASS if success else 0.0)
    )
    reason = failure_reason or ("" if success else classify_candidate_failure(
        getattr(result, "error", "") or ""
    ))
    return ExecutionCandidate(
        id=new_id("CAND"),
        task_id=task_id,
        run_id=run_id,
        provider=provider,
        model=model,
        context_trace=dict(context_trace or {}),
        budget_trace=dict(budget_trace or {}),
        generated_output=getattr(result, "generated_output", "") or "",
        patch=patch,
        reference=reference,
        token_usage=token_usage,
        latency=latency,
        validation_result=vresult,
        quality_score=qscore,
        failure_reason=reason,
        model_capability_snapshot=capability_snapshot(
            capability_registry, provider, model
        ),
    )


# ================================================================ ExecutionRun 状态机

class RunStatus(str, Enum):
    """Run 生命周期状态 (T5.2 §2): pending → running → success|failed。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


#: 合法迁移表 (状态机: 只允许 pending→running→success|failed; 终态不可回头)。
#: 其余迁移一律拒绝 (非法迁移硬报错 — 状态机校验)。
_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PENDING: frozenset({RunStatus.RUNNING}),
    RunStatus.RUNNING: frozenset({RunStatus.SUCCESS, RunStatus.FAILED}),
    RunStatus.SUCCESS: frozenset(),
    RunStatus.FAILED: frozenset(),
}


def _now_iso() -> str:
    """统一 UTC 时间戳 (ISO 8601 字符串; 与 experience_ctx 同格式, 排序==时间序)。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ExecutionRun(_ExecModel):
    """Run 生命周期状态机 (T5.2 §2; 非法迁移拒绝)。

    生命周期: 创建 (pending) → start() (running) → complete(candidate_id)
    (success) | fail() (failed)。start_time/end_time 由状态转换写入 (UTC ISO);
    candidate_id 在 complete() 时回填 (Run → 候选锚点)。
    """

    run_id: str
    candidate_id: str = ""
    start_time: str | None = None
    end_time: str | None = None
    status: RunStatus = RunStatus.PENDING

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> RunStatus:
        return RunStatus(v) if isinstance(v, str) else v

    @field_validator("candidate_id", mode="before")
    @classmethod
    def _cid_none(cls, v: Any) -> Any:
        return v if v is not None else ""

    def start(self) -> None:
        """pending → running (记录 start_time); 非法迁移拒绝。"""
        self._transition(RunStatus.RUNNING)
        self.start_time = _now_iso()

    def complete(self, candidate_id: str) -> None:
        """running → success (回填 candidate_id + end_time); 非法迁移拒绝。"""
        self._transition(RunStatus.SUCCESS)
        self.candidate_id = candidate_id
        self.end_time = _now_iso()

    def fail(self) -> None:
        """running → failed (记录 end_time); 非法迁移拒绝。"""
        self._transition(RunStatus.FAILED)
        self.end_time = _now_iso()

    def _transition(self, target: RunStatus) -> None:
        if target not in _RUN_TRANSITIONS[self.status]:
            raise ValueError(
                f"illegal ExecutionRun transition: "
                f"{self.status.value} -> {target.value}"
            )
        self.status = target


# ================================================================ CandidateCollector

class CandidateCollector:
    """多 Run 候选收集器 (T5.2 §3)。

    输入 Task → (多 Run 执行) → 输出 List[ExecutionCandidate]。
    铁律: 失败候选必须保存 (禁静默丢弃) — add() 强制失败候选带
    failure_reason (失败不允许无声无息, 供 Evaluator/经验复盘)。
    顺序保持: 候选按收集顺序排列 (与 Run 执行序一致, 审计友好)。
    """

    def __init__(self) -> None:
        self._candidates: list[ExecutionCandidate] = []

    def add(self, candidate: ExecutionCandidate) -> None:
        """收集一个候选 (失败候选 failure_reason 必填 — 禁静默丢弃)。"""
        if not isinstance(candidate, ExecutionCandidate):
            raise TypeError(
                f"candidate must be ExecutionCandidate, got {type(candidate).__name__}"
            )
        if not candidate.is_success and not candidate.failure_reason:
            raise ValueError(
                "failed candidate must carry failure_reason (失败必存, 禁静默丢弃)"
            )
        self._candidates.append(candidate)

    def collect(self, candidates: list[ExecutionCandidate]) -> list[ExecutionCandidate]:
        """批量收集 (逐个经 add 校验); 返回已收集列表。"""
        for candidate in candidates:
            self.add(candidate)
        return self._candidates

    @property
    def candidates(self) -> list[ExecutionCandidate]:
        """已收集候选 (副本 — 防外部篡改收集器状态)。"""
        return list(self._candidates)

    @property
    def successes(self) -> list[ExecutionCandidate]:
        """成功候选 (按收集序)。"""
        return [c for c in self._candidates if c.is_success]

    @property
    def failures(self) -> list[ExecutionCandidate]:
        """失败候选 (按收集序; 失败必存 — 供复盘/经验, 不静默)。"""
        return [c for c in self._candidates if not c.is_success]

    def __len__(self) -> int:
        return len(self._candidates)


# ================================================================ SequentialRunner

class SequentialRunner:
    """多 Run 顺序执行器 (T5.2 §5)。

    - 默认 N=3 (可配); **顺序执行禁并发** — 单线程 for 循环, 无
      threading/asyncio (并发违反设计: 抗随机性靠独立重试, 非并行);
    - 每次 Run: 独立 Provider 调用 (executor 每次重新调用 — 同一 Context/
      request, 独立随机性; Runtime 路径 = 新沙箱 + 新 Provider generate);
    - Run 间状态记录: 每 Run 一个 ExecutionRun (pending→running→success|failed),
    经 runs 属性可审计;
    - 失败安全: Run 异常 → 失败候选 (failure_reason 归类) + Run failed —
      不中断收集 (失败必存, 禁静默丢弃);
    - 经验信号: 每候选 to_experience_signals() 汇总到 signals (candidate_success
      / 五类失败 — T4.4 词汇);
    - evaluate(): T5.3 正式评估 — CandidateEvaluator 5 层确定性评分
      (禁 LLM/随机), 返回 EvaluationResult (last_evaluation 可审计);
    - select_result(): 经 Evaluator 的正式选择 — 选中候选对应执行结果;
      全失败/无合格 → 最后一个失败结果 (如实返回, 拒绝理由经
      last_evaluation 审计, 不静默);
    - capability_registry (T5.4 可选): 每候选保存时冻结该模型能力快照
      (model_capability_snapshot — 历史可解释; None → 快照 {} 中性);
    - experience_stats (T5.4 可选): 每候选成功/失败喂入统计 (只统计不
      评分 — 禁自动改分; None → 不记录, 行为逐位不变)。

    executor: Callable[[int], ExecutionResult] — 第 index 次 Run 的独立执行
    (1-based); 返回 ExecutionResult (失败也返回结果对象 — 失败安全契约,
    不抛未处理异常; 抛异常由 runner 兜底转失败候选)。
    """

    def __init__(
        self,
        executor: Callable[[int], Any],
        *,
        runs: int = 3,
        provider: str = "",
        model: str = "",
        capability_registry: Any = None,
        experience_stats: Any = None,
    ) -> None:
        if not callable(executor):
            raise TypeError("executor must be callable")
        self._executor = executor
        self._runs_count = max(1, int(runs))
        self._provider = provider
        self._model = model
        self._capability_registry = capability_registry
        self._experience_stats = experience_stats
        self._run_states: list[ExecutionRun] = []
        self._results: list[Any] = []
        self._candidates: list[ExecutionCandidate] = []
        self._signals: list[tuple[str, str]] = []
        self._last_evaluation: Any = None

    # ------------------------------------------------------------------ 状态

    @property
    def candidates(self) -> list[ExecutionCandidate]:
        """最近一次 run() 的候选列表 (副本; 未 run → 空)。"""
        return list(self._candidates)

    @property
    def runs(self) -> list[ExecutionRun]:
        """Run 状态记录 (执行序; pending→running→success|failed 终态)。"""
        return list(self._run_states)

    @property
    def signals(self) -> list[tuple[str, str]]:
        """经验信号汇总 [(signal, run_id), ...] (每候选 to_experience_signals)。"""
        return list(self._signals)

    # ------------------------------------------------------------------ 执行

    def run(self, request: Any = None) -> list[ExecutionCandidate]:
        """顺序执行 N 次 (禁并发) → CandidateCollector 收集 (失败必存)。

        request: ExecutionRequest (task_id 锚点; None → task_id 空)。
        返回候选列表 (与 Run 执行序一致); 每次调用重置内部状态 (可重入)。
        """
        collector = CandidateCollector()
        self._run_states = []
        self._results = []
        self._candidates = []
        self._signals = []
        base = getattr(request, "id", "") or "run"
        for index in range(1, self._runs_count + 1):
            run = ExecutionRun(run_id=f"{base}-run-{index}")
            run.start()
            started = time.monotonic()
            try:
                result = self._executor(index)
                self._results.append(result)
                candidate = candidate_from_result(
                    result,
                    request=request,
                    run_id=run.run_id,
                    provider=self._provider,
                    model=self._model,
                    latency=time.monotonic() - started,
                    capability_registry=self._capability_registry,
                )
                if candidate.is_success:
                    run.complete(candidate.id)
                else:
                    # 失败 Run 必须保存 (禁静默丢弃): Run 状态镜像候选结果 —
                    # 候选失败 → Run failed (失败候选必带 failure_reason)。
                    run.candidate_id = candidate.id
                    run.fail()
            except Exception as exc:  # noqa: BLE001 — 失败安全: Run 异常 → 失败候选
                candidate = ExecutionCandidate(
                    id=new_id("CAND"),
                    run_id=run.run_id,
                    provider=self._provider,
                    model=self._model,
                    failure_reason=classify_candidate_failure(str(exc)),
                    model_capability_snapshot=capability_snapshot(
                        self._capability_registry, self._provider, self._model
                    ),
                )
                # 结果占位对齐: 候选与结果索引一一对应 (select_result 按索引回取)
                self._results.append(None)
                run.candidate_id = candidate.id
                run.fail()
            self._run_states.append(run)
            collector.add(candidate)
            for signal in candidate.to_experience_signals():
                self._signals.append((signal, run.run_id))
            # T5.4 经验统计: 每候选成功/失败喂入 (只统计不评分, 禁自动改分;
            # 复用 experience_ctx 词汇 — 缺省 None 不记录, 行为逐位不变)。
            if self._experience_stats is not None:
                recorder = getattr(self._experience_stats, "record_candidate", None)
                if callable(recorder):
                    recorder(candidate)
        self._candidates = collector.candidates
        return self._candidates

    def evaluate(self) -> Any:
        """正式评估 (T5.3): CandidateEvaluator 5 层确定性评分 (禁 LLM/随机)。

        返回 EvaluationResult (selected/ranking/score_breakdown/rejection_reason,
        可解释可审计); 未 run() → RuntimeError; 评估明细经 last_evaluation
        属性重复读取 (同一次评估结果, 无副作用)。
        """
        if not self._candidates:
            raise RuntimeError("no candidates: call run() first")
        from .evaluator import CandidateEvaluator  # 延迟导入 — 防循环依赖

        evaluation = CandidateEvaluator().evaluate(self._candidates)
        self._last_evaluation = evaluation
        return evaluation

    @property
    def last_evaluation(self) -> Any:
        """最近一次评估结果 (T5.3; 未评估 → None; 审计用 — 为什么选它)。"""
        return self._last_evaluation

    def select_result(self) -> Any:
        """正式选择 (T5.3): CandidateEvaluator 评估 → 选中候选对应执行结果。

        规则: 验证通过候选按 5 层总分选 Best (评估明细经 last_evaluation
        审计 — 为什么选它可解释); 全失败 / 无合格候选 → 最后一个候选结果
        (失败如实返回, 不静默伪装成功 — 拒绝理由经 last_evaluation 审计);
        未 run() → RuntimeError。
        """
        if not self._candidates:
            raise RuntimeError("no candidates: call run() first")
        evaluation = self.evaluate()
        if evaluation.selected_candidate_id is not None:
            for index, candidate in enumerate(self._candidates):
                if candidate.id == evaluation.selected_candidate_id:
                    if index < len(self._results):
                        return self._results[index]
        return self._results[-1] if self._results else None
