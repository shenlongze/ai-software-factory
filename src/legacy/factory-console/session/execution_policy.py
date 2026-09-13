"""factory-console/session/execution_policy.py — ExecutionPolicy (S10-063 批次 A)。

Production Governance (GAP G6, 设计 §6): 统一策略层 — 不在 orchestrator 散落
if/else。4 模式:
- AUTO          — 全部自动 (execute/retry/repair/replan/create_task 全允许)
- SAFE_AUTO     — 自动 + review 触发条件 (高风险/低置信度 → 需评审)
- REVIEW_REQUIRED — 特定操作必须人工 (无批准 → 禁)
- MANUAL        — 全人工 (无批准 → 全禁)

接口: can_execute / can_retry / can_repair / can_replan / can_create_task —
独立判定 (各自返回 (allowed, reason)); 统一规则: 人工批准 (approved=True)
优先级最高 (MANUAL/REVIEW_REQUIRED 下可放行); risk(context) — 风险分档
low/medium/high (destructive/删核心/大规模 DAG → high)。

context 键 (约定): risk|risk_level (显式档位), destructive (bool),
reason/description (危险词扫描), dag_size/task_count (大规模 DAG),
scope ("large"/"大"), confidence (0-1), approved (人工批准)。

设计: docs/sprint10/S10-063-production-governance-design.md §6
边界: 纯标准库, 零依赖, 不修改任何现有模块; 纯判定, 不执行动作。
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

# ---------------------------------------------------------------- 模式常量

MODE_AUTO = "AUTO"
MODE_SAFE_AUTO = "SAFE_AUTO"
MODE_REVIEW = "REVIEW_REQUIRED"
MODE_MANUAL = "MANUAL"

#: 全部合法模式
MODES: tuple[str, ...] = (
    MODE_AUTO,
    MODE_SAFE_AUTO,
    MODE_REVIEW,
    MODE_MANUAL,
)

# ---------------------------------------------------------------- 风险常量

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

#: 危险词 (risk 判定: reason/description 命中任一 → high —
#: destructive/删核心等破坏性操作必须人工评审)
DESTRUCTIVE_KEYWORDS: tuple[str, ...] = (
    "删除", "移除", "删核心", "删库", "破坏", "重写核心",
    "drop", "delete", "remove", "destructive", "rewrite core",
)

#: 大规模 DAG 阈值 (dag_size/task_count >= HIGH_RISK_DAG_SIZE → high;
#: >= MEDIUM_RISK_DAG_SIZE → medium)
HIGH_RISK_DAG_SIZE = 10
MEDIUM_RISK_DAG_SIZE = 5

#: SAFE_AUTO 低置信度阈值 (confidence < 阈值 → 需评审)
DEFAULT_LOW_CONFIDENCE = 0.7


class ExecutionPolicy:
    """统一执行策略 (设计 §6): 4 模式 + can_* 独立判定 + risk 分档。

    __init__(mode=MODE_AUTO, confidence_threshold=0.7) — 模式 + 低置信度阈值。
    """

    MODE_AUTO = MODE_AUTO
    MODE_SAFE_AUTO = MODE_SAFE_AUTO
    MODE_REVIEW = MODE_REVIEW
    MODE_MANUAL = MODE_MANUAL

    RISK_LOW = RISK_LOW
    RISK_MEDIUM = RISK_MEDIUM
    RISK_HIGH = RISK_HIGH

    def __init__(
        self,
        mode: str = MODE_AUTO,
        confidence_threshold: float = DEFAULT_LOW_CONFIDENCE,
    ) -> None:
        self.mode = mode if mode in MODES else MODE_AUTO
        self.confidence_threshold = float(confidence_threshold)

    # ------------------------------------------------------------ risk

    def risk(self, context: Any = None) -> str:
        """风险分档 low/medium/high (设计 §6: destructive/删核心/大规模 DAG → high)。

        优先级: 显式档位 (context["risk"]/"risk_level") > destructive 信号
        (destructive=True 或 reason/description 命中危险词) > 大规模 DAG
        (dag_size/task_count) > scope ("large"/"大") > 缺省 low。
        """
        ctx = context or {}
        explicit = str(ctx.get("risk") or ctx.get("risk_level") or "").lower()
        if explicit in (RISK_LOW, RISK_MEDIUM, RISK_HIGH):
            return explicit
        if ctx.get("destructive") is True:
            return RISK_HIGH
        text = " ".join(
            str(ctx.get(k) or "") for k in ("reason", "description", "action", "task")
        ).lower()
        if any(kw in text for kw in DESTRUCTIVE_KEYWORDS):
            return RISK_HIGH
        dag_size = int(ctx.get("dag_size") or 0)
        task_count = int(ctx.get("task_count") or 0)
        if dag_size >= HIGH_RISK_DAG_SIZE or task_count >= HIGH_RISK_DAG_SIZE:
            return RISK_HIGH
        if dag_size >= MEDIUM_RISK_DAG_SIZE or task_count >= MEDIUM_RISK_DAG_SIZE:
            return RISK_MEDIUM
        if str(ctx.get("scope") or "") in ("large", "大", "大型"):
            return RISK_MEDIUM
        return RISK_LOW

    # ------------------------------------------------------------ can_*

    def can_execute(self, context: Any = None) -> Tuple[bool, str]:
        """执行判定 (独立调用)。"""
        return self._decide("execute", context, gate_confidence=True)

    def can_retry(self, context: Any = None) -> Tuple[bool, str]:
        """重试判定 (独立调用) — 低代价操作: SAFE_AUTO 下仅风险闸。"""
        return self._decide("retry", context, gate_confidence=False)

    def can_repair(self, context: Any = None) -> Tuple[bool, str]:
        """修复判定 (独立调用) — 低代价操作: SAFE_AUTO 下仅风险闸。"""
        return self._decide("repair", context, gate_confidence=False)

    def can_replan(self, context: Any = None) -> Tuple[bool, str]:
        """重规划判定 (独立调用) — 结构性变更: SAFE_AUTO 下风险+置信度闸。"""
        return self._decide("replan", context, gate_confidence=True)

    def can_create_task(self, context: Any = None) -> Tuple[bool, str]:
        """新任务提案判定 (独立调用) — SAFE_AUTO 下风险+置信度闸。"""
        return self._decide("create_task", context, gate_confidence=True)

    # ------------------------------------------------------------ 内部

    def _decide(
        self, op: str, context: Any = None, gate_confidence: bool = True
    ) -> Tuple[bool, str]:
        """统一判定: 人工批准 > 模式规则。

        - approved=True (人工批准) → 任何模式放行;
        - AUTO      → 全允许;
        - MANUAL    → 全禁 (无批准);
        - SAFE_AUTO → 高风险 → 禁 (需评审); gate_confidence 且低置信度 → 禁;
          其余 → 允许;
        - REVIEW_REQUIRED → 禁 (无批准 — 特定操作必须人工)。
        """
        ctx = context or {}
        if ctx.get("approved") is True:
            return True, f"人工批准已确认 — {op} 允许"
        mode = self.mode
        if mode == MODE_AUTO:
            return True, f"AUTO 模式: {op} 自动允许"
        if mode == MODE_MANUAL:
            return False, f"MANUAL 模式: {op} 需要人工批准"
        if mode == MODE_SAFE_AUTO:
            level = self.risk(ctx)
            if level == RISK_HIGH:
                return False, (
                    f"SAFE_AUTO 模式: 高风险 ({level}) — {op} 需评审"
                )
            if gate_confidence:
                confidence = float(ctx.get("confidence") or 1.0)
                if confidence < self.confidence_threshold:
                    return False, (
                        f"SAFE_AUTO 模式: 低置信度 {confidence:.2f} < "
                        f"{self.confidence_threshold} — {op} 需评审"
                    )
            return True, f"SAFE_AUTO 模式: 风险/置信度达标 — {op} 允许"
        # MODE_REVIEW (REVIEW_REQUIRED)
        return False, f"REVIEW_REQUIRED 模式: {op} 需要人工批准"
