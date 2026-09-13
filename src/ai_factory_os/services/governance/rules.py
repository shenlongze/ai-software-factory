"""services.governance.rules — 分级审批规则（纯规则，无 IO，可单测）。

逐条复现 factory-exec/exec/approval.py 的 classify_risk（不改规则）。
"""
from __future__ import annotations

import re

#: 高风险信号（爆炸半径大）
HIGH_RISK_PATTERNS: tuple[str, ...] = (
    r"^--- a/.*(?:delete|删除)",
    r"^\+\+\+ /dev/null",
    r"^[-+]\s*(?:rm\s|os\.remove|shutil\.rmtree)",
    r"requirements\.txt|pyproject\.toml|package\.json",
    r"^diff --git a/(?:db/|migrations/|infra/|deploy)",
)

#: CLI 动词 → 语义终态
_DECISION_MAP: dict[str, str] = {
    "approve": "approved", "approved": "approved",
    "reject": "rejected", "rejected": "rejected", "deny": "rejected",
}


def classify_risk(patch_text: str, *, changed_files: int = 1) -> tuple[str, list[str]]:
    """分级审批：按爆炸半径判定 risk_level 与 required_roles（确定性规则）。

    high   → 删除 / 依赖升级 / 基础设施 → tech_lead + compliance
    medium → 跨文件 / 核心配置         → tech_lead
    low    → 单文件常规修改            → developer
    """
    text = str(patch_text or "")
    if any(re.search(pat, text, re.M) for pat in HIGH_RISK_PATTERNS):
        return "high", ["tech_lead", "compliance"]
    if changed_files >= 3:
        return "medium", ["tech_lead"]
    if changed_files >= 2 or "config" in text[:2000].lower():
        return "medium", ["tech_lead"]
    return "low", ["developer"]


def normalize_decision(decision: str) -> str | None:
    """CLI 动词 → 终态；非法返回 None。"""
    return _DECISION_MAP.get(str(decision).lower())
