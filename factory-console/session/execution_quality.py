"""factory-console/session/execution_quality.py — K-2 执行质量分 (S10-117 C-2/B-6)。

确定性评分器 (纯规则, 不调 LLM — LLM 可选路径必须标注且规则分始终存在):
- score_execution(record, evidence): 执行结果质量 — 复用 T5.3 五层思路
  (validation 硬条件 + patch/scope/risk/coverage 规则), 0-1 归一;
- score_prd(prd_text, product): PRD 质量 — 复用 M3d 六维思路
  (完整性/可行性/可测性/明确性/用户价值/风险);
- score_engineering(plan, product): 工程计划质量 — 复用 M3d 六维权重
  (完整性/粒度/依赖/可行性/可测性/风险)。

失败安全: 任何评分器异常 → ExecutionQuality(score=None, reason=...) — 不阻断
执行链 (调用方把 None 分数如实落盘/展示, 诚实不臆造)。

与 T5.3/M3d 的差异 (诚实记录, 设计 §6):
- T5.3 是加分制 (validation +100 / patch ±50 / scope +30~-30 / risk -30~+10 /
  coverage 0~+40); 本模块归一 0-1 (每维 0-1 × 权重), 层语义与硬门槛不变 —
  validation 失败 → 总分封顶 0.35 (< LOW_SCORE_THRESHOLD 0.5, B-5 低分触发)。
- T5.3 缺证据层按 0 分中性; 本模块 0-1 尺度下"中性"= 0.5 (不奖不罚,
  同 T5.3 "缺证据 0 分中性"语义的尺度平移)。
- T5.3 coverage 逐条 +10 封顶 +40; 本模块用 covered/total 比例 (归一可比)。
- M3d 六维用于拆解任务; PRD 文档无"任务粒度/依赖", 用"明确性/用户价值"替换
  (权重 0.20/0.10); 工程计划沿用 M3d 六维权重, 评分来源是 engineering.json 字段。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

#: 低分阈值 (B-5: score < 0.5 → 低分策略: 重试有界 → 换资源)
LOW_SCORE_THRESHOLD = 0.5

#: 验证硬条件失败时的总分封顶 (validation=0 → 总分 ≤ 0.35, 必 < 0.5 低分)
FAILURE_SCORE_CAP = 0.35

#: 执行质量五维权重 (T5.3 五层归一 0-1; validation 硬条件权重最高)
EXECUTION_WEIGHTS: dict[str, float] = {
    "validation": 0.30,
    "patch_apply": 0.15,
    "scope": 0.15,
    "regression_risk": 0.15,
    "requirement_coverage": 0.25,
}

#: PRD 六维权重 (M3d 思路, 文档适配: 明确性/用户价值替换粒度/依赖)
PRD_WEIGHTS: dict[str, float] = {
    "完整性": 0.25,
    "可行性": 0.20,
    "可测性": 0.15,
    "明确性": 0.20,
    "用户价值": 0.10,
    "风险": 0.10,
}

#: 工程计划六维权重 (与 M3d §3.4 完全一致 — 复用不重写)
ENGINEERING_WEIGHTS: dict[str, float] = {
    "完整性": 0.25,
    "粒度": 0.20,
    "依赖": 0.20,
    "可行性": 0.15,
    "可测性": 0.10,
    "风险": 0.10,
}

#: PRD 必需章节 (与 ProductDocument.SECTIONS 同源口径 — 完整性维)
PRD_SECTIONS: tuple[str, ...] = (
    "Product Overview",
    "Problem",
    "Target User",
    "Core Features",
    "Usage Scenario",
    "Future Direction",
    "User Stories",
    "Acceptance Criteria",
)

#: 占位符 (未填写 → 明确性/用户价值降分, 诚实不臆造)
PRD_PLACEHOLDERS: tuple[str, ...] = ("(未填写)", "(待补充)", "待补充", "TODO", "TBD", "TBD.")


@dataclass
class ExecutionQuality:
    """质量分结果 (0-1 + 分维度 breakdown + 版本 + 规则说明; 可审计)。

    score: 0-1; 评分器故障/无法判定 → None (诚实标注, 不臆造分数)。
    dimensions: 分维度得分 (0-1, 与权重同键)。
    evaluator_version: 评分器版本 (可追溯)。
    scored_at: 评分时间 (UTC ISO)。
    rules: 规则说明 (为什么是这个分, 逐维可解释)。
    reason: score=None 时的诚实原因 (失败安全标注)。
    """

    score: Optional[float]
    dimensions: dict[str, float] = field(default_factory=dict)
    evaluator_version: str = "1.0"
    scored_at: str = ""
    rules: list[str] = field(default_factory=list)
    reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """落盘/展示视图 (JSON 安全; score=None 保留 reason 诚实标注)。"""
        return {
            "score": self.score,
            "dimensions": {k: round(float(v), 4) for k, v in self.dimensions.items()},
            "evaluator_version": self.evaluator_version,
            "scored_at": self.scored_at,
            "rules": list(self.rules),
            "reason": self.reason,
        }


def _now_iso() -> str:
    """当前 UTC ISO 时间 (确定性落盘时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


def _clamp01(value: float) -> float:
    """钳制 0-1 (确定性)。"""
    return max(0.0, min(1.0, float(value)))


def _evidence(evidence: Optional[dict[str, Any]], key: str) -> dict[str, Any]:
    """证据 dict 提取 (None/非 dict → {}, 确定性不抛)。"""
    if not isinstance(evidence, dict):
        return {}
    value = evidence.get(key)
    return value if isinstance(value, dict) else {}


def _num_ev(evidence: dict[str, Any], key: str, default: float = 0.0) -> float:
    """证据数值读取 (None/非数值/非有限 → default, 确定性不抛)。"""
    try:
        value = evidence.get(key, default)
        if value is None:
            return default
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _text_has(text: Optional[str], needle: str) -> bool:
    """文本包含判断 (None 安全, 大小写不敏感)。"""
    return str(needle).lower() in str(text or "").lower()


def _product_field(product: Any, name: str) -> bool:
    """ProductIntent 字段是否有值 (core_features 非空列表; 其余非空串)。"""
    if product is None:
        return False
    value = getattr(product, name, None)
    if name == "core_features":
        return bool(value)
    return value not in (None, "")


# ================================================================== C-2 执行质量分

def _score_validation(record: dict[str, Any], evidence: dict[str, Any]) -> tuple[float, str]:
    """validation 硬条件: 失败 → 0 (低分, B-5 触发); 成功 → 1.0。

    判定顺序 (确定性): ① 证据 validation.passed=False → 0;
    ② 记录 result=failed 或 error 非空 → 0; ③ 其余 (success/无失败证据) → 1.0。
    """
    v = _evidence(evidence, "validation_result")
    passed = v.get("passed")
    result = str((record or {}).get("result") or "")
    error = (record or {}).get("error")
    if passed is False or result == "failed" or error:
        return 0.0, "验证/执行失败 (validation.passed=False 或 result=failed) — 硬条件不满足"
    if passed is True or result == "success":
        return 1.0, "验证通过 (validation.passed=True / result=success)"
    return 1.0, "无失败证据 — 按成功处理 (不臆造失败)"


def _score_patch_apply(record: dict[str, Any], evidence: dict[str, Any]) -> tuple[float, str]:
    """patch 应用层: 可应用 1.0 / 失败 0.0 / 无证据 0.5 中性。"""
    ev = _evidence(evidence, "patch_apply_result")
    applied = ev.get("applied")
    if applied is True:
        files = ev.get("files") or []
        return 1.0, f"patch 可应用 ({len(files)} 文件)"
    if applied is False:
        return 0.0, "patch 应用失败 (patch_apply_result.applied=False)"
    return 0.5, "无 patch 应用证据 — 中性 0.5 (不臆造)"


def _score_scope(record: dict[str, Any], evidence: dict[str, Any]) -> tuple[float, str]:
    """修改范围: 越小越优 (1 文件/≤20 行 → 1.0; 每多 1 文件 -0.15;
    每多 20 行 -0.01; 下限 0.0; 无证据 → 0.5 中性)。"""
    ev = _evidence(evidence, "scope_result")
    files = _num_ev(ev, "changed_files")
    lines = _num_ev(ev, "changed_lines")
    if files <= 0 and lines <= 0:
        return 0.5, "无修改范围证据 — 中性 0.5 (不臆造)"
    score = 1.0 - max(0, files - 1) * 0.15 - max(0, lines - 20) * 0.01
    return _clamp01(score), f"修改范围 {files:g} 文件 / {lines:g} 行 (越小越优)"


def _score_regression_risk(record: dict[str, Any], evidence: dict[str, Any]) -> tuple[float, str]:
    """回归风险: 核心文件/删码/测试减少降分; 影响面小保分; 无证据 → 0.5 中性。"""
    ev = _evidence(evidence, "regression_risk_result")
    signals = {
        "core_files": _num_ev(ev, "core_files"),
        "deleted_lines": _num_ev(ev, "deleted_lines"),
        "tests_reduced": _num_ev(ev, "tests_reduced"),
        "affected_symbols": _num_ev(ev, "affected_symbols"),
    }
    if not any(signals.values()):
        return 0.5, "无回归风险证据 — 中性 0.5 (不臆造)"
    score = 0.7  # 有证据基线
    notes: list[str] = []
    if signals["core_files"] > 0:
        score -= 0.2
        notes.append(f"核心文件 {signals['core_files']:g} 个 (-0.2)")
    if signals["deleted_lines"] > 50:
        score -= 0.1
        notes.append(f"删除 {signals['deleted_lines']:g} 行 (-0.1)")
    if signals["tests_reduced"] > 0:
        score -= 0.15
        notes.append(f"测试减少 {signals['tests_reduced']:g} 条 (-0.15)")
    if 0 < signals["affected_symbols"] <= 3:
        score += 0.1
        notes.append(f"影响面小 ({signals['affected_symbols']:g} 符号, +0.1)")
    return _clamp01(score), "回归风险信号: " + ("; ".join(notes) if notes else "无显著风险")


def _score_requirement_coverage(record: dict[str, Any], evidence: dict[str, Any]) -> tuple[float, str]:
    """需求覆盖: covered/total 比例; 无证据 → 0.5 中性。"""
    ev = _evidence(evidence, "requirement_coverage_result")
    covered = _num_ev(ev, "covered")
    total = _num_ev(ev, "total")
    if covered <= 0 and total <= 0:
        return 0.5, "无需求覆盖证据 — 中性 0.5 (不臆造)"
    total = max(total, covered)
    return _clamp01(covered / total), f"验收标准覆盖 {covered:g}/{total:g} (比例)"


#: 执行层评分器注册表 (与 EXECUTION_WEIGHTS 同键; 顺序无关 — 按权重循环)
_EXECUTION_SCORERS: dict[str, Any] = {
    "validation": _score_validation,
    "patch_apply": _score_patch_apply,
    "scope": _score_scope,
    "regression_risk": _score_regression_risk,
    "requirement_coverage": _score_requirement_coverage,
}


def score_execution(record: dict[str, Any], evidence: dict[str, Any]) -> ExecutionQuality:
    """执行结果质量分 (确定性, 纯规则; 失败安全 → score=None + reason)。

    record: 审计记录 dict (result/error 等); evidence: 执行证据 dict
    (validation_result/patch_apply_result/scope_result/regression_risk_result/
    requirement_coverage_result — 缺省 {} 中性, 不臆造)。

    总分 = Σ(维分 × 权重); validation=0 (硬条件失败) → 总分封顶 0.35,
    保证失败执行必 < LOW_SCORE_THRESHOLD (B-5 低分策略可触发)。
    """
    try:
        dimensions: dict[str, float] = {}
        rules: list[str] = []
        weighted = 0.0
        for key, weight in EXECUTION_WEIGHTS.items():
            dim, rule = _EXECUTION_SCORERS[key](record or {}, evidence or {})
            dim = _clamp01(float(dim))
            dimensions[key] = round(dim, 4)
            rules.append(f"{key}: {dim:.2f} (权重 {weight:.0%}) — {rule}")
            weighted += dim * weight
        if dimensions.get("validation") == 0.0:
            total = min(weighted, FAILURE_SCORE_CAP)
            rules.append(
                f"硬条件: validation=0 → 总分封顶 {FAILURE_SCORE_CAP:.2f} "
                f"(< LOW_SCORE_THRESHOLD {LOW_SCORE_THRESHOLD:g}, B-5 低分策略触发)"
            )
        else:
            total = weighted
        return ExecutionQuality(
            score=round(_clamp01(total), 4),
            dimensions=dimensions,
            evaluator_version="1.0",
            scored_at=_now_iso(),
            rules=rules,
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全: 评分器异常不阻断执行
        return ExecutionQuality(
            score=None,
            dimensions={},
            evaluator_version="1.0",
            scored_at=_now_iso(),
            rules=[],
            reason=f"quality scorer failed: {exc}",
        )


# ================================================================== B-6 PRD 质量分

def _score_prd_completeness(prd_text: Optional[str], product: Any) -> tuple[float, str]:
    """完整性: PRD 必需章节覆盖率 + 产品必填字段 (0.6/0.4 加权)。"""
    present = sum(1 for s in PRD_SECTIONS if _text_has(prd_text, s))
    section_score = present / len(PRD_SECTIONS)
    if product is not None:
        fields = sum(
            1 for name in ("problem", "user", "core_features")
            if _product_field(product, name)
        )
        field_score = fields / 3
    else:
        field_score = 1.0 if section_score >= 0.5 else 0.5
    return _clamp01(0.6 * section_score + 0.4 * field_score), (
        f"章节 {present}/{len(PRD_SECTIONS)} + 产品字段 (0.6/0.4 加权)"
    )


def _score_prd_feasibility(prd_text: Optional[str], product: Any) -> tuple[float, str]:
    """可行性: 平台已指定 + 功能数合理 (1-12); 确定性。"""
    platform = str(getattr(product, "platform", "") or "").strip() if product is not None else ""
    features = list(getattr(product, "core_features", None) or []) if product is not None else []
    platform_ok = bool(platform)
    scope_ok = 1 <= len(features) <= 12
    score = 0.6 * (1.0 if platform_ok else 0.0) + 0.4 * (1.0 if scope_ok else 0.0)
    reason = (
        f"平台={'已指定' if platform_ok else '未指定'} (0.6) + "
        f"功能数 {len(features)} 在 1-12 合理范围={'是' if scope_ok else '否'} (0.4)"
    )
    return _clamp01(score), reason


def _score_prd_testability(prd_text: Optional[str], product: Any) -> tuple[float, str]:
    """可测性: Acceptance Criteria 章节存在且含验收条目 (非空清单)。"""
    text = str(prd_text or "")
    if not _text_has(text, "Acceptance Criteria"):
        return 0.0, "缺 Acceptance Criteria 章节 — 可测性缺失"
    section = text.split("Acceptance Criteria", 1)[-1]
    bullets = sum(1 for line in section.splitlines() if line.strip().startswith(("- ", "* ")))
    score = _clamp01(bullets / 3.0)
    return score, f"Acceptance Criteria 含 {bullets} 条验收条目 (每 3 条满分)"


def _score_prd_clarity(prd_text: Optional[str], product: Any) -> tuple[float, str]:
    """明确性: 无占位符 + 文本有实质内容 (≥200 字符); 确定性。"""
    text = str(prd_text or "")
    placeholder = any(p in text for p in PRD_PLACEHOLDERS)
    length_ok = len(text.strip()) >= 200
    score = 0.7 * (0.0 if placeholder else 1.0) + 0.3 * (1.0 if length_ok else 0.0)
    reason = (
        f"占位符={'有' if placeholder else '无'} (0.7) + "
        f"正文 {len(text.strip())} 字符≥200={'是' if length_ok else '否'} (0.3)"
    )
    return _clamp01(score), reason


def _score_prd_user_value(prd_text: Optional[str], product: Any) -> tuple[float, str]:
    """用户价值: problem + user 均有实质内容 (非占位); 确定性。"""
    if product is None:
        problem = _text_has(prd_text, "## Problem")
        user = _text_has(prd_text, "## Target User")
        score = (1.0 if problem else 0.0) + (1.0 if user else 0.0)
        return _clamp01(score / 2), "章节 Problem/Target User 存在性 (各 0.5)"
    problem_ok = _product_field(product, "problem") and not _placeholder_of(
        getattr(product, "problem", "")
    )
    user_ok = _product_field(product, "user") and not _placeholder_of(
        getattr(product, "user", "")
    )
    score = (1.0 if problem_ok else 0.0) + (1.0 if user_ok else 0.0)
    return _clamp01(score / 2), "problem/user 实质内容 (各 0.5, 占位符降分)"


def _placeholder_of(text: Any) -> bool:
    """文本是否占位 (None/空/已知占位符)。"""
    value = str(text or "").strip()
    return (not value) or value in PRD_PLACEHOLDERS


def _score_prd_risk(prd_text: Optional[str], product: Any) -> tuple[float, str]:
    """风险: Future Direction 章节存在 (风险意识/边界标注); 确定性。"""
    text = str(prd_text or "")
    future = _text_has(text, "Future Direction")
    risk_note = any(k in text.lower() for k in ("risk", "风险", "约束", "边界", "限制"))
    score = 0.6 * (1.0 if future else 0.0) + 0.4 * (1.0 if risk_note else 0.0)
    reason = (
        f"Future Direction={'有' if future else '无'} (0.6) + "
        f"风险/约束标注={'有' if risk_note else '无'} (0.4)"
    )
    return _clamp01(score), reason


_PRD_SCORERS: dict[str, Any] = {
    "完整性": _score_prd_completeness,
    "可行性": _score_prd_feasibility,
    "可测性": _score_prd_testability,
    "明确性": _score_prd_clarity,
    "用户价值": _score_prd_user_value,
    "风险": _score_prd_risk,
}


def score_prd(prd_text: Optional[str], product: Any = None) -> ExecutionQuality:
    """PRD 质量分 (复用 M3d 六维思路; 确定性; 失败安全 → score=None)。"""
    try:
        dimensions: dict[str, float] = {}
        rules: list[str] = []
        weighted = 0.0
        for key, weight in PRD_WEIGHTS.items():
            dim, rule = _PRD_SCORERS[key](prd_text, product)
            dim = _clamp01(float(dim))
            dimensions[key] = round(dim, 4)
            rules.append(f"{key}: {dim:.2f} (权重 {weight:.0%}) — {rule}")
            weighted += dim * weight
        return ExecutionQuality(
            score=round(_clamp01(weighted), 4),
            dimensions=dimensions,
            evaluator_version="1.0",
            scored_at=_now_iso(),
            rules=rules,
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ExecutionQuality(
            score=None,
            dimensions={},
            evaluator_version="1.0",
            scored_at=_now_iso(),
            rules=[],
            reason=f"prd scorer failed: {exc}",
        )


# ================================================================== B-6 工程计划质量分

def _plan_tasks(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """plan.technical_tasks (非 dict 元素归一为 {name: 值}; 确定性)。"""
    tasks: list[dict[str, Any]] = []
    for item in plan.get("technical_tasks") or []:
        if isinstance(item, dict):
            tasks.append(item)
        else:
            tasks.append({"name": str(item), "type": str(item)})
    return tasks


def _score_eng_completeness(plan: dict[str, Any], product: Any) -> tuple[float, str]:
    """完整性: name/platform/architecture 存在 + modules/technical_tasks 非空。"""
    plan = plan or {}
    checks = {
        "name": bool(str(plan.get("name") or "").strip()),
        "platform": bool(str(plan.get("platform") or "").strip()),
        "architecture": bool(str(plan.get("architecture") or "").strip()),
        "modules": bool(plan.get("modules")),
        "tasks": bool(_plan_tasks(plan)),
    }
    score = sum(1.0 for ok in checks.values() if ok) / len(checks)
    missing = [k for k, ok in checks.items() if not ok]
    return _clamp01(score), f"字段完整 {len(checks) - len(missing)}/{len(checks)}" + (
        f" (缺 {', '.join(missing)})" if missing else ""
    )


def _score_eng_granularity(plan: dict[str, Any], product: Any) -> tuple[float, str]:
    """粒度: 模块数 1-6 满分, 7-12 降分; 任务数 4-16 合理。"""
    plan = plan or {}
    modules = list(plan.get("modules") or [])
    tasks = _plan_tasks(plan)
    if modules:
        module_score = 1.0 if len(modules) <= 6 else _clamp01(1.0 - (len(modules) - 6) * 0.1)
    else:
        module_score = 0.0
    task_score = 1.0 if 4 <= len(tasks) <= 16 else _clamp01(len(tasks) / 16.0)
    score = 0.6 * module_score + 0.4 * task_score
    return _clamp01(score), f"模块 {len(modules)} 个 + 任务 {len(tasks)} 个 (合理粒度)" if modules else "无模块 — 粒度不足"


def _score_eng_dependency(plan: dict[str, Any], product: Any) -> tuple[float, str]:
    """依赖: 技术任务链覆盖 database→backend→frontend→test 顺序 (M3 链完整性)。"""
    types = [str(t.get("type") or "") for t in _plan_tasks(plan or {})]
    chain = ("database", "backend", "frontend", "test")
    seen: list[str] = []
    for t in types:
        if t in chain and t not in seen:
            seen.append(t)
    score = len(seen) / len(chain)
    return _clamp01(score), f"技术任务链覆盖 {len(seen)}/{len(chain)} ({'→'.join(chain)})"


def _score_eng_feasibility(plan: dict[str, Any], product: Any) -> tuple[float, str]:
    """可行性: architecture 非空且与 platform 匹配 (EngineeringPlan 口径)。"""
    plan = plan or {}
    architecture = str(plan.get("architecture") or "").strip()
    platform = str(plan.get("platform") or "").strip().lower()
    if not architecture:
        return 0.0, "architecture 缺失 — 可行性不足"
    from .pipeline import ARCHITECTURE_BY_PLATFORM, DEFAULT_ARCHITECTURE

    expected = ARCHITECTURE_BY_PLATFORM.get(platform, DEFAULT_ARCHITECTURE)
    match = architecture == expected
    score = 1.0 if match else 0.6
    return score, f"architecture={architecture!r} 与 platform={platform!r} 匹配={'是' if match else '否'} (未知平台按默认架构, 0.6)"


def _score_eng_testability(plan: dict[str, Any], product: Any) -> tuple[float, str]:
    """可测性: technical_tasks 含 test 类型任务 (验证命令可接)。"""
    types = [str(t.get("type") or "") for t in _plan_tasks(plan or {})]
    score = 1.0 if "test" in types else 0.0
    return score, "含 test 类型任务 (测试用例编写)" if score else "缺 test 类型任务 — 可测性缺失"


def _score_eng_risk(plan: dict[str, Any], product: Any) -> tuple[float, str]:
    """风险: PRD 来源可追溯 + 模块明确 (无来源/空模块 → 风险高)。"""
    plan = plan or {}
    traceable = bool(plan.get("prd_generated")) or bool(plan.get("modules"))
    score = 1.0 if traceable else 0.0
    return score, "计划来源可追溯 (prd_generated/modules 存在)" if traceable else "无来源/模块 — 风险高"


_ENGINEERING_SCORERS: dict[str, Any] = {
    "完整性": _score_eng_completeness,
    "粒度": _score_eng_granularity,
    "依赖": _score_eng_dependency,
    "可行性": _score_eng_feasibility,
    "可测性": _score_eng_testability,
    "风险": _score_eng_risk,
}


def score_engineering(plan: dict[str, Any], product: Any = None) -> ExecutionQuality:
    """工程计划质量分 (复用 M3d 六维权重; 确定性; 失败安全 → score=None)。"""
    try:
        dimensions: dict[str, float] = {}
        rules: list[str] = []
        weighted = 0.0
        for key, weight in ENGINEERING_WEIGHTS.items():
            dim, rule = _ENGINEERING_SCORERS[key](plan or {}, product)
            dim = _clamp01(float(dim))
            dimensions[key] = round(dim, 4)
            rules.append(f"{key}: {dim:.2f} (权重 {weight:.0%}) — {rule}")
            weighted += dim * weight
        return ExecutionQuality(
            score=round(_clamp01(weighted), 4),
            dimensions=dimensions,
            evaluator_version="1.0",
            scored_at=_now_iso(),
            rules=rules,
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ExecutionQuality(
            score=None,
            dimensions={},
            evaluator_version="1.0",
            scored_at=_now_iso(),
            rules=[],
            reason=f"engineering scorer failed: {exc}",
        )


__all__ = [
    "LOW_SCORE_THRESHOLD",
    "FAILURE_SCORE_CAP",
    "EXECUTION_WEIGHTS",
    "PRD_WEIGHTS",
    "ENGINEERING_WEIGHTS",
    "PRD_SECTIONS",
    "ExecutionQuality",
    "score_execution",
    "score_prd",
    "score_engineering",
]
