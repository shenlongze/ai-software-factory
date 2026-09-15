"""api/registry.py — 域 → router 的注册表（★ 单一事实源）。

为什么（2026-09-15 ✓ Founder: "api 的结构一定要统一"）:
  装配只允许读本表 ✗ 不允许在 app.py 里逐个手写 include_router。
  ⇒ 新增域 = 在 DOMAINS 里加一行 ✓；忘接线 = 守卫检查报红 ✓（不会静默漏掉）
"""
from __future__ import annotations

import importlib
from typing import Any

#: (域, 中文标签, router 模块路径)。顺序 = OpenAPI 分组顺序。
DOMAINS: tuple[tuple[str, str, str], ...] = (
    ("conversation", "会话", "ai_factory_os.api.domains.conversation.router"),
    ("understanding", "需求分析", "ai_factory_os.api.domains.understanding.router"),
    ("architecture", "架构分析", "ai_factory_os.api.domains.architecture.router"),
    ("decomposition", "任务拆解", "ai_factory_os.api.domains.decomposition.router"),
    ("orchestration", "编排", "ai_factory_os.api.domains.orchestration.router"),
    ("execution", "执行", "ai_factory_os.api.domains.execution.router"),
    ("validation", "验收", "ai_factory_os.api.domains.validation.router"),
    ("delivery", "交付", "ai_factory_os.api.domains.delivery.router"),
    ("operations", "运维", "ai_factory_os.api.domains.operations.router"),
    ("metrics", "监控", "ai_factory_os.api.domains.metrics.router"),
    ("audit", "审计", "ai_factory_os.api.domains.audit.router"),
    ("governance", "治理", "ai_factory_os.api.domains.governance.router"),
    ("organization", "组织", "ai_factory_os.api.domains.organization.router"),
    ("platform", "平台", "ai_factory_os.api.domains.platform.router"),
)


def domain_names() -> tuple[str, ...]:
    """全部域名（顺序稳定 ✓）。"""
    return tuple(name for name, _label, _mod in DOMAINS)


def iter_routers() -> list[tuple[str, str, Any]]:
    """按声明顺序 import 并返回 (域, 标签, router)。"""
    out: list[tuple[str, str, Any]] = []
    for name, label, module_path in DOMAINS:
        module = importlib.import_module(module_path)
        out.append((name, label, module.router))
    return out
