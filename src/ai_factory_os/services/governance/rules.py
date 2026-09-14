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

#: ★ 敏感路径/操作白名单（Founder: 治理要有牙齿 —— 不能让"小改"绕过风险判定 ✗）
#:   为什么（缺口4）: 原规则只按【爆炸半径】(删除/依赖/跨文件) 判风险 ✗ →
#:   一个"只改一行"但落在【密钥/CI/权限/部署】的改动可能被判 low ✗（实际极敏感 ✗）
#:   这些路径一经改动即【至少 medium】，涉及密钥/生产配置的直接 high ✓
SENSITIVE_PATTERNS: tuple[str, ...] = (
    r"\.env(?:\.[\w.]+)?$",                  # 环境变量 / 密钥
    r"(?:^|/)secrets?(?:/|\.)", r"(?:^|/)credentials?(?:/|\.)",
    r"(?:^|/)\.github/workflows/",             # CI/CD
    r"(?:^|/)(?:auth|iam|permission|acl)(?:s|/|\.)",  # 权限与认证
    r"(?:^|/)(?:alembic|migrations?)/",         # 数据库 schema 变更
    r"(?:^|/)(?:Dockerfile|docker-compose\.ya?ml|Chart\.ya?ml|k8s|helm)/?",
    r"(?:^|/)(?:terraform|\.tf|ansible|playbook)",
    r"(?:^|/)nginx\.conf", r"(?:^|/)systemd/.*\.service",
    r"(?:^|/)pyproject\.toml|(?:^|/)setup\.cfg",  # 打包/发布配置
)

#: 敏感项中【最敏感】的（改了直接 high ✓）
CRITICAL_PATTERNS: tuple[str, ...] = (
    r"\.env(?:\.[\w.]+)?$", r"(?:^|/)secrets?(?:/|\.)",
    r"(?:^|/)credentials?(?:/|\.)", r"(?:^|/)\.github/workflows/",
    r"(?:^|/)(?:terraform|\.tf)", r"(?:^|/)systemd/.*\.service",
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
    # ★ 敏感路径: 密钥/生产配置/CI/权限 → 直接 high（不看爆炸半径 ✗）
    if any(re.search(pat, text, re.M | re.I) for pat in CRITICAL_PATTERNS):
        return "high", ["tech_lead", "compliance"]
    # ★ 敏感路径: 其它受关注区域 → 至少 medium（但"小改"不再等于 low ✗）
    if any(re.search(pat, text, re.M | re.I) for pat in SENSITIVE_PATTERNS):
        return "medium", ["tech_lead"]
    if changed_files >= 3:
        return "medium", ["tech_lead"]
    if changed_files >= 2 or "config" in text[:2000].lower():
        return "medium", ["tech_lead"]
    return "low", ["developer"]


def normalize_decision(decision: str) -> str | None:
    """CLI 动词 → 终态；非法返回 None。"""
    return _DECISION_MAP.get(str(decision).lower())
