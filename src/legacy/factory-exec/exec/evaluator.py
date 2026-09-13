"""factory-exec/exec/evaluator.py — CandidateEvaluator 结果评估引擎 (Sprint 5 T5.3)。

设计依据: docs/validation/sprint5-t51-execution-strategy-design.md §3/§4 (T5.1 冻结)
+ 用户确认的 5 层评分模型 (确定性规则 — 禁 LLM 决定 / 禁人工选择 / 禁随机):

    ① Validation Pass        (+100; 硬条件 — 未通过直接降级, 不选除非全失败)
    ② Patch Apply            (±50;  git apply/check 成功 +50 / 失败 -50)
    ③ 修改范围 (Scope)        (越小越优: 基准 +30 缩放, 大修改减分, 下限 -30)
    ④ 回归风险 (Risk)         (核心文件/删码/测试减少降分; 影响面小保分 +10 内)
    ⑤ 需求覆盖 (Coverage)     (Task Analysis 验收标准逐条覆盖 +10, 封顶 +40)

输出 EvaluationResult (可解释, 可审计):
- selected_candidate_id: 选中候选 (验证通过者中总分最高; 无合格 → None);
- ranking: 选择优先级序 (合格在前 → 总分降序 → 逐层优先 → Run 序; 含失败候选
  — 诚实全排序, 全失败时排名首位即\"最不差\");
- score_breakdown: 每候选 5 层分数明细 + 理由 (为什么选 A 不选 B);
- rejection_reason: 无候选 / 全失败 (无合格) → 诚实拒绝理由, 不静默。

确定性铁律:
- 纯函数: 评分只读候选字段, 无 LLM / 无随机 / 无 IO / 无网络;
- 硬门槛: 验证未通过 (failure_reason 非空 / validation_result.passed 非真 /
  无验证证据) → qualified=False, 不可被选中 (除非全部失败 → 诚实拒绝);
- 平局决胜: 层优先级 (Validation→Patch→Scope→Risk→Coverage), 再输入序
  (Run 序 — 先 Run 者胜; 全部确定性可复现)。

KISS 边界: 只依赖 stdlib + pydantic + candidate.ExecutionCandidate;
不跑真实 Benchmark / 不调 LLM / 不落数据库; 各层证据 dict 由产线 (Runtime/
测试) 提供, 缺证据层按 0 分中性处理 — 诚实不臆造。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field

from .candidate import ExecutionCandidate

# ---------------------------------------------------------------- 5 层分数常量

#: ① 验证通过 (最高权重 — 硬条件, 未通过直接降级不可选)。
VALIDATION_PASS_SCORE = 100.0
#: ② patch 可应用 / 应用失败。
PATCH_APPLY_PASS_SCORE = 50.0
PATCH_APPLY_FAIL_SCORE = -50.0
#: ③ 修改范围: 最小改动基准分 / 每多改 1 文件 / 每多改 10 行 / 下限。
SCOPE_BASE_BONUS = 30.0
SCOPE_EXTRA_FILE_PENALTY = 5.0
SCOPE_EXTRA_LINES_PENALTY = 10.0
SCOPE_FLOOR = -30.0
#: ④ 回归风险: 核心文件改动 / 删除大量代码(>50 行) / 测试减少 / 影响面小(≤3 符号)。
RISK_CORE_FILE_PENALTY = -20.0
RISK_DELETION_PENALTY = -10.0
RISK_TESTS_REDUCED_PENALTY = -15.0
RISK_SMALL_IMPACT_BONUS = 10.0
RISK_FLOOR = -30.0
#: ⑤ 需求覆盖: 每条验收标准覆盖 / 封顶。
COVERAGE_PER_CRITERION = 10.0
COVERAGE_CAP = 40.0

#: 层优先级 (T5.1 §4: 验证 > 应用 > 范围 > 风险 > 覆盖; 平局决胜顺序)。
_LAYER_PRIORITY = (
    "validation",
    "patch_apply",
    "scope",
    "regression_risk",
    "requirement_coverage",
)


class EvaluationLayer(str, Enum):
    """5 层评分维度 (T5.1 §4 优先级顺序: 验证 > 应用 > 范围 > 风险 > 覆盖)。"""

    VALIDATION = "validation"
    PATCH_APPLY = "patch_apply"
    SCOPE = "scope"
    REGRESSION_RISK = "regression_risk"
    REQUIREMENT_COVERAGE = "requirement_coverage"


class LayerScore(BaseModel):
    """单层得分明细 (可解释: 分数 + 理由 + 证据细节)。

    qualified 语义: 仅 validation 层有意义 (硬条件) — CandidateScore.qualified
    由 validation 层得分 == VALIDATION_PASS_SCORE 推导, 不单独存层标记。
    """

    layer: EvaluationLayer
    score: float
    reason: str
    detail: dict[str, Any] = Field(default_factory=dict)


class CandidateScore(BaseModel):
    """单候选 5 层总分 + 明细 (为什么选/不选它, 可审计)。"""

    candidate_id: str
    run_id: str = ""
    total: float
    qualified: bool
    layers: list[LayerScore]
    verdict: str


class EvaluationResult(BaseModel):
    """评估输出: 选中候选 / 排序 / 5 层明细 / 诚实拒绝理由 (T5.3)。

    - selected_candidate_id: None = 无合格候选 (rejection_reason 必非空);
    - ranking: 全候选选择优先级序 (含失败候选 — 诚实, 不静默丢弃);
    - score_breakdown: 与 ranking 同序的每候选 5 层明细。
    """

    selected_candidate_id: str | None = None
    ranking: list[str] = Field(default_factory=list)
    score_breakdown: list[CandidateScore] = Field(default_factory=list)
    rejection_reason: str | None = None
    total_candidates: int = 0
    qualified_count: int = 0
    evaluator_version: str = "1.0"


# ---------------------------------------------------------------- 纯函数工具

def _clamp(value: float, low: float, high: float) -> float:
    """数值钳制到 [low, high] (确定性)。"""
    return max(low, min(high, value))


def _int_ev(evidence: dict[str, Any], key: str, default: int = 0) -> int:
    """证据 dict 整数读取 (None/非数值 → default; 确定性, 不抛)。"""
    try:
        return int(evidence.get(key, default) or default)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- 5 层评分 (纯函数)

def _score_validation(candidate: ExecutionCandidate) -> LayerScore:
    """① 验证层 (硬条件): 测试/verifier 通过 +100; 失败/无证据 → 0 + 不合格。

    判定顺序 (确定性):
    1. failure_reason 非空 → 候选已失败, 不可选 (失败证据优先 — 诚实);
    2. validation_result.passed → True +100 / False 0;
    3. 无 passed 键 → 测试计数推断 (tests_passed == tests_total);
       或 syntax_ok/verifier_passed 单信号 → 通过;
    4. 无任何验证证据 → 保守按未验证处理 (0 分, 不可选 — 不臆造通过)。
    """
    if candidate.failure_reason:
        return LayerScore(
            layer=EvaluationLayer.VALIDATION,
            score=0.0,
            reason=(
                f"候选已失败 (failure_reason={candidate.failure_reason})"
                " — 验证层直接降级, 不可选"
            ),
            detail={"failure_reason": candidate.failure_reason},
        )
    v = candidate.validation_result or {}
    passed = v.get("passed")
    if passed is None:
        total = _int_ev(v, "tests_total")
        passed_tests = _int_ev(v, "tests_passed")
        if total > 0:
            passed = passed_tests >= total
        elif v.get("syntax_ok") is True or v.get("verifier_passed") is True:
            passed = True
        else:
            return LayerScore(
                layer=EvaluationLayer.VALIDATION,
                score=0.0,
                reason="无验证证据 (validation_result 空) — 保守按未验证, 不可选",
                detail={"validation_result": v},
            )
    if bool(passed):
        detail = {
            key: v[key]
            for key in ("tests_total", "tests_passed", "syntax_ok", "verifier_passed")
            if key in v
        }
        return LayerScore(
            layer=EvaluationLayer.VALIDATION,
            score=VALIDATION_PASS_SCORE,
            reason="验证通过 (测试/verifier 全绿) — 硬条件满足",
            detail=detail,
        )
    errors = v.get("errors") or v.get("error") or ""
    suffix = f": {errors}" if errors else ""
    return LayerScore(
        layer=EvaluationLayer.VALIDATION,
        score=0.0,
        reason=f"验证失败 — 直接降级不可选{suffix}",
        detail={"errors": errors},
    )


def _score_patch_apply(candidate: ExecutionCandidate) -> LayerScore:
    """② patch 应用层: git apply/check 成功 +50 / 失败 -50 / 无证据 0。"""
    ev = candidate.patch_apply_result or {}
    applied = ev.get("applied")
    if applied is True:
        files = ev.get("files") or []
        return LayerScore(
            layer=EvaluationLayer.PATCH_APPLY,
            score=PATCH_APPLY_PASS_SCORE,
            reason=f"patch 可应用 ({len(files)} 文件)",
            detail={"method": ev.get("method", "git apply --check"), "files": files},
        )
    if applied is False:
        error = ev.get("error") or "git apply 报错"
        return LayerScore(
            layer=EvaluationLayer.PATCH_APPLY,
            score=PATCH_APPLY_FAIL_SCORE,
            reason=f"patch 应用失败: {error}",
            detail={"method": ev.get("method", "git apply --check"), "error": error},
        )
    return LayerScore(
        layer=EvaluationLayer.PATCH_APPLY,
        score=0.0,
        reason="无 patch 应用证据 — 中性 0 分 (不臆造)",
        detail={},
    )


def _score_scope(candidate: ExecutionCandidate) -> LayerScore:
    """③ 修改范围层 (避免大面积): 越小越优。

    公式 (确定性): 基准 +30; 每多改 1 文件 -5; 每多改 10 行 -1; 下限 -30。
    例: 1 文件/10 行 → +30; 4 文件/100 行 → +7; 10 文件/500 行 → -30 (下限)。
    """
    ev = candidate.scope_result or {}
    files = _int_ev(ev, "changed_files")
    lines = _int_ev(ev, "changed_lines")
    if files <= 0 and lines <= 0:
        return LayerScore(
            layer=EvaluationLayer.SCOPE,
            score=0.0,
            reason="无修改范围证据 — 中性 0 分 (不臆造)",
            detail={},
        )
    score = (
        SCOPE_BASE_BONUS
        - max(0, files - 1) * SCOPE_EXTRA_FILE_PENALTY
        - max(0, lines - 20) / SCOPE_EXTRA_LINES_PENALTY
    )
    score = _clamp(score, SCOPE_FLOOR, SCOPE_BASE_BONUS)
    return LayerScore(
        layer=EvaluationLayer.SCOPE,
        score=score,
        reason=(
            f"修改范围 {files} 文件 / {lines} 行"
            " (基准 +30, 每多 1 文件 -5, 每多 10 行 -1, 下限 -30)"
        ),
        detail={"changed_files": files, "changed_lines": lines},
    )


def _score_regression_risk(candidate: ExecutionCandidate) -> LayerScore:
    """④ 回归风险层 (风险降低): 高风险信号降分, 影响面小保分 (+10 内)。

    信号 (确定性): 核心文件改动 -20; 删除代码 >50 行 -10; 测试减少 -15;
    Call Graph 影响面 ≤3 符号 +10; 合计钳制 [-30, +10]; 无证据 → 0 保分。
    """
    ev = candidate.regression_risk_result or {}
    if not ev:
        return LayerScore(
            layer=EvaluationLayer.REGRESSION_RISK,
            score=0.0,
            reason="无回归风险证据 — 中性保分 0 (不臆造)",
            detail={},
        )
    score = 0.0
    notes: list[str] = []
    if ev.get("core_files_changed"):
        score += RISK_CORE_FILE_PENALTY
        notes.append("核心文件改动")
    if _int_ev(ev, "deleted_lines") > 50:
        score += RISK_DELETION_PENALTY
        notes.append("删除代码 >50 行")
    if ev.get("tests_reduced"):
        score += RISK_TESTS_REDUCED_PENALTY
        notes.append("测试减少")
    affected = _int_ev(ev, "affected_symbols", default=-1)
    if 0 <= affected <= 3:
        score += RISK_SMALL_IMPACT_BONUS
        notes.append("影响面小 (Call Graph 波及 ≤3 符号)")
    score = _clamp(score, RISK_FLOOR, RISK_SMALL_IMPACT_BONUS)
    return LayerScore(
        layer=EvaluationLayer.REGRESSION_RISK,
        score=score,
        reason="；".join(notes) if notes else "无风险信号",
        detail=dict(ev),
    )


def _score_requirement_coverage(candidate: ExecutionCandidate) -> LayerScore:
    """⑤ 需求覆盖层: Task Analysis 验收标准逐条覆盖 +10, 封顶 +40。

    evidence: {"covered": n, "total": n} — total 缺省按 covered 自洽。
    """
    ev = candidate.requirement_coverage_result or {}
    covered = _int_ev(ev, "covered")
    total = _int_ev(ev, "total")
    if covered <= 0 and total <= 0:
        return LayerScore(
            layer=EvaluationLayer.REQUIREMENT_COVERAGE,
            score=0.0,
            reason="无需求覆盖证据 — 中性 0 分 (不臆造)",
            detail={},
        )
    total = max(total, covered)
    score = _clamp(covered * COVERAGE_PER_CRITERION, 0.0, COVERAGE_CAP)
    return LayerScore(
        layer=EvaluationLayer.REQUIREMENT_COVERAGE,
        score=score,
        reason=f"验收标准覆盖 {covered}/{total} (逐条 +10, 封顶 +40)",
        detail={"covered": covered, "total": total},
    )


#: 层评分器注册表 (顺序 = T5.1 §4 优先级, 与 EvaluationLayer 枚举一致)。
_LAYER_SCORERS: tuple[Callable[[ExecutionCandidate], LayerScore], ...] = (
    _score_validation,
    _score_patch_apply,
    _score_scope,
    _score_regression_risk,
    _score_requirement_coverage,
)


def score_candidate(candidate: ExecutionCandidate) -> CandidateScore:
    """单候选 5 层评分 → CandidateScore (纯函数, 确定性)。

    total = 5 层得分之和 (保留 2 位小数); qualified = 验证层 == +100
    (硬条件 — 验证未通过者不可被选中); verdict 一句话结论 (可解释)。
    """
    layers = [scorer(candidate) for scorer in _LAYER_SCORERS]
    total = round(sum(layer.score for layer in layers), 2)
    qualified = layers[0].score == VALIDATION_PASS_SCORE
    head = "验证通过, 合格" if qualified else "验证未通过, 不合格"
    breakdown = " | ".join(
        f"{layer.layer.value}:{layer.score:+.0f}" for layer in layers
    )
    extra = "；".join(
        layer.reason
        for layer in layers[1:]
        if layer.score != 0.0
    )
    verdict = f"{head} — 总分 {total:+.0f} [{breakdown}]"
    if extra:
        verdict = f"{verdict} ({extra})"
    return CandidateScore(
        candidate_id=candidate.id,
        run_id=candidate.run_id,
        total=total,
        qualified=qualified,
        layers=layers,
        verdict=verdict,
    )


def _sort_key(item: tuple[int, CandidateScore]) -> tuple[Any, ...]:
    """排序键 (确定性): 合格优先 → 总分降序 → 逐层优先 → 输入序 (Run 序)。

    输入序保证平局时先 Run 者胜 — 与 T5.2 临时选择\"第一个成功\"语义一致。
    """
    index, score = item
    return (
        0 if score.qualified else 1,
        -score.total,
        *(-layer.score for layer in score.layers),
        index,
    )


class CandidateEvaluator:
    """5 层确定性评分评估器 (T5.3; 禁 LLM/随机/人工 — 纯规则, 可解释)。

    用法: CandidateEvaluator().evaluate(candidates) → EvaluationResult。
    无候选 / 全失败: selected=None + rejection_reason (诚实拒绝, 不静默 —
    拒绝理由逐候选列出验证层失败原因, 可审计)。
    """

    version = "1.0"

    def evaluate(self, candidates: list[ExecutionCandidate]) -> EvaluationResult:
        """List[ExecutionCandidate] → EvaluationResult (确定性, 无副作用)。"""
        if not candidates:
            return EvaluationResult(
                selected_candidate_id=None,
                ranking=[],
                score_breakdown=[],
                rejection_reason="no candidates provided to evaluator (无可评估候选)",
                total_candidates=0,
                qualified_count=0,
                evaluator_version=self.version,
            )
        scored = [score_candidate(candidate) for candidate in candidates]
        ordered = [score for _, score in sorted(enumerate(scored), key=_sort_key)]
        ranking = [score.candidate_id for score in ordered]
        qualified = [score for score in ordered if score.qualified]
        if not qualified:
            shown = "；".join(
                f"{score.candidate_id}: {score.layers[0].reason}"
                for score in ordered[:3]
            )
            more = f" 等 {len(ordered) - 3} 个" if len(ordered) > 3 else ""
            return EvaluationResult(
                selected_candidate_id=None,
                ranking=ranking,
                score_breakdown=ordered,
                rejection_reason=(
                    f"no qualified candidate: 全部 {len(candidates)} 个候选"
                    f"验证未通过 — {shown}{more} (最不差 = {ranking[0]})"
                ),
                total_candidates=len(candidates),
                qualified_count=0,
                evaluator_version=self.version,
            )
        return EvaluationResult(
            selected_candidate_id=qualified[0].candidate_id,
            ranking=ranking,
            score_breakdown=ordered,
            rejection_reason=None,
            total_candidates=len(candidates),
            qualified_count=len(qualified),
            evaluator_version=self.version,
        )
