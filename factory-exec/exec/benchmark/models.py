"""factory-exec/exec/benchmark/models.py — Benchmark 样本/结果/报告模型 (Pydantic v2)。

Phase A+++++ Real Product Proof: 样本集 (5 Bug / 3 Feature / 1 Greenfield) +
执行记录 (success/token/cost/latency/patch_quality/human_intervention) +
五维评分 (Understanding/Analysis/Implementation/Validation/Communication,
Level 1-3)。verifier 不依赖 LLM (纯 Python 静态/行为检查, 正反例可独立验证)。

模型分层:
- BenchmarkSample: 样本定义 (id/kind/objective/requirement/files/verifier_id) —
  声明意图, 不含人工答案 (自然语言任务描述)。
- BenchmarkResult: 单样本执行结果 (真实调用数据: usage/cost/latency +
  verifier 判定 + 五维评分 + human_intervention)。
- BenchmarkReport: 全样本集报告 (按 kind 聚合 + 汇总统计 + BLOCKED 标注)。

诚实原则: 无 API key → 真实调用抛 ProviderError → 记录 status=BLOCKED,
reason=ProviderError 消息; 不 mock 当能力证明, 不假装成功。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models import new_id, utcnow


class SampleKind(str, Enum):
    """样本类型: Bug 修复 / Feature 开发 / Greenfield 小项目。"""

    BUG = "bug"
    FEATURE = "feature"
    GREENFIELD = "greenfield"


class SampleStatus(str, Enum):
    """样本执行状态: BLOCKED (无 key, 真实调用未执行) / SUCCESS / FAILED。"""

    BLOCKED = "blocked"
    SUCCESS = "success"
    FAILED = "failed"


class FiveDimScore(BaseModel):
    """五维评分 (Level 1-3): Understanding/Analysis/Implementation/Validation/Communication。

    Level 语义 (ai-employee-benchmark-design.md):
      1 = 未达 (定位错误/方案错误/未实现/未验证/报告缺失)
      2 = 达标 (定位正确/方案合理/实现有效/验证通过/报告清晰)
      3 = 优秀 (根因精准/方案最优/实现最小/验证充分/报告可交付)
    score 归一 1..3, 均值 = 综合分 (level 1-3, 保留 1 位小数)。
    """

    understanding: int = 1
    analysis: int = 1
    implementation: int = 1
    validation: int = 1
    communication: int = 1

    @field_validator("*")
    @classmethod
    def _clamp_level(cls, v: Any) -> int:
        return max(1, min(3, int(v)))

    @property
    def average(self) -> float:
        return round(
            (self.understanding + self.analysis + self.implementation
             + self.validation + self.communication) / 5.0,
            1,
        )

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump()
        d["average"] = self.average
        return d


class BenchmarkResult(BaseModel):
    """单样本执行结果 (真实调用数据 + verifier 判定 + 评分)。"""

    id: str = Field(default_factory=lambda: new_id("BMR"))
    sample_id: str
    kind: SampleKind
    status: SampleStatus = SampleStatus.BLOCKED
    provider_id: str = ""
    model: str = ""
    # 真实调用数据 (8B-3 语义: usage → cost; latency 秒)
    usage: dict[str, Any] = Field(default_factory=dict)
    cost_usd: float | None = None
    latency_s: float | None = None
    # verifier 判定 (不依赖 LLM 的静态/行为检查)
    verifier_id: str = ""
    verifier_passed: bool | None = None
    verifier_detail: str = ""
    # patch 质量 (0-100 启发式: 可应用 40 + verifier 通过 40 + 最小性 10 + 有产物 10;
    # None = 未产出 patch / 未执行)
    patch_quality: int | None = None
    # 评分 (无真实执行 → None)
    score: FiveDimScore | None = None
    # 人工介入 (0 = 零介入; >0 = 次数; None = 未记录)
    human_intervention: int | None = None
    # BLOCKED 原因 (无 key → ProviderError 消息; 诚实标注)
    blocked_reason: str = ""
    error: str = ""
    created_at: Any = Field(default_factory=utcnow)

    @field_validator("kind", mode="before")
    @classmethod
    def _coerce_kind(cls, v: Any) -> SampleKind:
        return SampleKind(v) if isinstance(v, str) else v

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> SampleStatus:
        return SampleStatus(v) if isinstance(v, str) else v

    @field_validator("usage", mode="before")
    @classmethod
    def _usage_none(cls, v: Any) -> Any:
        return v if v is not None else {}

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        d["kind"] = self.kind.value
        d["status"] = self.status.value
        if self.score is not None:
            d["score"] = self.score.to_dict()
        return d


class BenchmarkReport(BaseModel):
    """全样本集 Benchmark 报告 (汇总 + 按 kind 聚合 + BLOCKED 标注)。"""

    id: str = Field(default_factory=lambda: new_id("BMRPT"))
    provider_id: str = ""
    model: str = ""
    results: list[BenchmarkResult] = Field(default_factory=list)
    blocked: bool = False
    blocked_reason: str = ""
    created_at: Any = Field(default_factory=utcnow)

    @field_validator("results", mode="before")
    @classmethod
    def _results_none(cls, v: Any) -> Any:
        if v is None:
            return []
        return [r if isinstance(r, BenchmarkResult) else BenchmarkResult.model_validate(r) for r in v]

    # ------------------------------------------------------------ 汇总统计

    @property
    def counts(self) -> dict[str, int]:
        """按状态统计 (bug/feature/greenfield 全样本)。"""
        from collections import Counter

        return dict(Counter(r.status.value for r in self.results))

    @property
    def success_rate(self) -> float | None:
        """成功率 = success / (success + failed); BLOCKED 不进分母; 无执行 → None。"""
        done = [r for r in self.results if r.status is not SampleStatus.BLOCKED]
        if not done:
            return None
        ok = sum(1 for r in done if r.status is SampleStatus.SUCCESS)
        return round(ok / len(done), 3)

    @property
    def total_cost_usd(self) -> float | None:
        costs = [r.cost_usd for r in self.results if r.cost_usd is not None]
        if not costs:
            return None
        return round(sum(costs), 6)

    @property
    def avg_latency_s(self) -> float | None:
        lats = [r.latency_s for r in self.results if r.latency_s is not None]
        if not lats:
            return None
        return round(sum(lats) / len(lats), 3)

    @property
    def avg_score(self) -> float | None:
        scores = [r.score.average for r in self.results if r.score is not None]
        if not scores:
            return None
        return round(sum(scores) / len(scores), 1)

    def by_kind(self, kind: SampleKind) -> list[BenchmarkResult]:
        return [r for r in self.results if r.kind is kind]

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump(mode="json", exclude={"results"})
        d["results"] = [r.to_dict() for r in self.results]
        d["counts"] = self.counts
        d["success_rate"] = self.success_rate
        d["total_cost_usd"] = self.total_cost_usd
        d["avg_latency_s"] = self.avg_latency_s
        d["avg_score"] = self.avg_score
        return d


class BenchmarkSample(BaseModel):
    """Benchmark 样本 (自然语言任务 + 验收 verifier, 不含人工答案)。

    id: 样本唯一 id (BUG-MKP-001 / FEAT-MKP-001 / GREENFIELD-001)。
    kind: bug | feature | greenfield。
    objective: 自然语言任务描述 (禁人工答案 — 只描述现象/需求, 不给修复方案)。
    requirement: 验收标准 (可验证约束, 供 verifier 判定)。
    project_files: 需要复制到沙箱的项目文件 (相对 markpad lib/ 根)。
    verifier_id: 注册的 verifier 名 (exec.benchmark.verifiers 注册表)。
    fix_hint: 隐藏字段 — 仅供测试/人工核验 verifier 正反例, 绝不进 Agent prompt。
    """

    id: str
    kind: SampleKind
    title: str = ""
    objective: str
    requirement: str = ""
    project_files: list[str] = Field(default_factory=list)
    verifier_id: str = ""
    fix_hint: str = ""  # 只读测试用, 不进 prompt

    @field_validator("kind", mode="before")
    @classmethod
    def _coerce_kind(cls, v: Any) -> SampleKind:
        return SampleKind(v) if isinstance(v, str) else v

    @field_validator("project_files", mode="before")
    @classmethod
    def _files_none(cls, v: Any) -> Any:
        return v if v is not None else []

    def prompt_text(self) -> str:
        """Agent 任务描述 (只含 objective + requirement, 不含 fix_hint)。"""
        parts = [self.objective]
        if self.requirement:
            parts.append(f"验收标准:\n{self.requirement}")
        return "\n\n".join(parts)

    @property
    def task_id(self) -> str:
        """Developer 执行报告契约兼容: benchmark 样本的 task_id 即样本 id。

        (DeveloperAgent.build_report 读取 request.task_id; 样本即任务。)
        """
        return self.id


#: verifier 签名: (sandbox_dir: Path, sample: BenchmarkSample) -> (passed, detail)
VerifierFn = Callable[[Any, "BenchmarkSample"], tuple[bool, str]]
