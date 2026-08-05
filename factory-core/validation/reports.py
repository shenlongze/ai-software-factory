"""validation/reports.py — ValidationReport: 汇总 (层/总判定) + 输出格式。

设计依据:
- phase3a-status.md: ValidationReport (汇总 + 输出格式)
- 父任务 CLI 输出样例:
    Validation Report
    Task: T-001
    L1 Factory    PASS
    L2 Workflow   PASS
    L3 Artifact   SKIP
    Result: PASS

层判定 = 该层规则的最差状态; 总判定 = 全规则的最差状态 (FAIL > ERROR > SKIP > PASS)。
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .models import ValidationResult, ValidationStatus

# 层级别 → 展示名 (报告格式)
LEVEL_NAMES = {"L1": "Factory", "L2": "Workflow", "L3": "Artifact"}

# 规则失败 → 规范 reason (completed/failed 事件载荷与 CLI 输出用)
REASON_BY_RULE: dict[str, str] = {
    "L1.task_exists": "task_not_found",
    "L1.task_data": "task_data_invalid",
    "L1.task_status": "task_status_invalid",
    "L1.task_files": "task_files_incomplete",
    "L2.workflow": "workflow_mismatch",
    "L2.expect_status": "status_mismatch",
    "L3.artifact": "artifact_hook_error",
}

_SEVERITY = {
    ValidationStatus.PASS: 0,
    ValidationStatus.SKIP: 1,
    ValidationStatus.ERROR: 2,
    ValidationStatus.FAIL: 3,
}


def render_checks(results: list[ValidationResult]) -> list[dict]:
    """结果 → checks 载荷 [{id, name, status, detail}] (Phase 2 契约保留)。"""
    from .rules import RULE_NAMES

    return [
        {
            "id": r.id,
            "name": RULE_NAMES.get(r.rule, r.rule),
            "status": r.status.value,
            "detail": r.message,
        }
        for r in results
    ]


class ValidationReport(BaseModel):
    """一次验证的汇总报告: 任务 + 规则结果 + 层/总判定 + 文本输出。"""

    task_id: str
    level: str = "L2"
    results: list[ValidationResult] = Field(default_factory=list)
    task_found: bool = False          # 任务文件是否存在 (CLI 退出码 7 判定)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------ 汇总

    @property
    def by_level(self) -> dict[str, ValidationStatus]:
        """每层状态: 层内非 SKIP 规则的最差状态; 整层全 SKIP 才显示 SKIP。

        如 L1 全 PASS → PASS; L3 仅 Hook SKIP → SKIP。
        """
        out: dict[str, ValidationStatus] = {}
        for level in LEVEL_NAMES:
            active = [r for r in self.results
                      if r.level == level and r.status is not ValidationStatus.SKIP]
            if not active:
                out[level] = ValidationStatus.SKIP
            else:
                out[level] = max((r.status for r in active), key=_SEVERITY.__getitem__)
        return out

    @property
    def result(self) -> ValidationStatus:
        """总判定: 任一 FAIL → FAIL; 否则任一 ERROR → ERROR; 否则 PASS (SKIP 不阻止通过)。"""
        active = [r for r in self.results if r.status is not ValidationStatus.SKIP]
        if not active:
            return ValidationStatus.PASS
        return max((r.status for r in active), key=_SEVERITY.__getitem__)

    @property
    def passed(self) -> bool:
        """是否通过 (PASS 才算; SKIP 不阻止通过)。"""
        return self.result is ValidationStatus.PASS

    @property
    def reason(self) -> str | None:
        """首个 FAIL 规则的规范 reason (如 task_not_found / status_mismatch)。"""
        for r in self.results:
            if r.status is ValidationStatus.FAIL:
                return REASON_BY_RULE.get(r.id, r.id)
        return None

    # ------------------------------------------------------------------ 输出

    def to_text(self) -> str:
        """Validation Report 文本格式 (父任务样例)。"""
        lines = ["Validation Report", f"Task: {self.task_id}"]
        for level, name in LEVEL_NAMES.items():
            lines.append(f"{level} {name:<10} {self.by_level[level].value}")
        lines.append(f"Result: {self.result.value}")
        return "\n".join(lines)
