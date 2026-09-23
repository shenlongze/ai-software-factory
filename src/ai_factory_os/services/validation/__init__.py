"""validation — Phase 3A Validation Engine (三层验证: L1 Factory / L2 Workflow / L3 Artifact Hook)。

对外出口: ValidationEngine / ValidationReport / ValidationResult / ValidationStatus / 规则集。
"""

from .engine import ValidationEngine
from .types import ValidationResult, ValidationStatus
from .reports import ValidationReport

__all__ = ["verify_pytest", "verify_python_syntax", 
    "ValidationEngine",
    "ValidationReport",
    "ValidationResult",
    "ValidationStatus",
]

# ★ 2026-09-15 归位: 真实验证器（跑 pytest / 语法检查）从 _pending_migration 迁入。
#   注意与 validation.engine/rules 的分工: 后者验的是【元数据规则】(任务在不在、字段全不全),
#   本模块验的是【真实执行】(ast.parse / pytest subprocess) —— 两件事, 互补。
from .verification import verify_pytest, verify_python_syntax
