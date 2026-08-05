"""runtimes/definitions.py — 默认 Runtime 定义 (hermes/echo/mock, 只描述不执行)。

设计依据:
- phase5a1-status.md: 默认定义 hermes (type=agent, capabilities: code-generation/
  tool-use/reasoning) / echo (mock) / mock — 只描述不执行。
- 边界 (ADR-0014 决策 3): 默认定义常驻代码层, 是 Catalog 的内建基线 (builtin
  baseline) — 读路径 (get/list/find_by_capability) 由 RuntimeCatalog 合并,
  永不自动写入 catalog.json; 持久化层只存用户注册/覆盖的定义。

与内置 Adapter 的关系 (ADR-0014): 定义 id 与 BUILTIN_ADAPTERS 键不必一致 —
echo 的 Adapter id 即 "echo", hermes 的 Adapter id 为 "hermes-runtime", 而
Catalog 默认定义 id 为 "hermes" (能力描述命名空间独立于实现注册命名空间)。
"""

from __future__ import annotations

from .models import CatalogStatus, RuntimeDefinition

DEFAULT_DEFINITIONS: list[RuntimeDefinition] = [
    RuntimeDefinition(
        id="hermes",
        name="Hermes Agent",
        type="agent",
        description="Hermes Agent — Nous Research 的通用 AI Agent Runtime "
                    "(经 hermes CLI one-shot 调用执行, 真实执行出口)",
        capabilities=["code-generation", "tool-use", "reasoning"],
        supported_tasks=["feature-implementation", "bugfix", "refactoring", "verification"],
        version="1.0.0",
        status=CatalogStatus.ACTIVE,
        metadata={
            "vendor": "Nous Research",
            "execution": "hermes -z (one-shot subprocess)",
            "builtin": True,
        },
    ),
    RuntimeDefinition(
        id="echo",
        name="Echo Runtime",
        type="mock",
        description="Echo mock Runtime — 输入原样回显到 output, 供派发/执行链路验证",
        capabilities=["echo", "testing"],
        supported_tasks=["smoke-test"],
        version="1.0.0",
        status=CatalogStatus.ACTIVE,
        metadata={
            "execution": "in-process (no subprocess)",
            "builtin": True,
        },
    ),
    RuntimeDefinition(
        id="mock",
        name="Mock Runtime",
        type="mock",
        description="通用 mock Runtime — 模拟执行结果, 供编排/恢复/测试场景",
        capabilities=["simulation", "testing"],
        supported_tasks=["smoke-test", "orchestration-test"],
        version="1.0.0",
        status=CatalogStatus.ACTIVE,
        metadata={
            "execution": "in-process (no subprocess)",
            "builtin": True,
        },
    ),
]

DEFAULT_DEFINITION_IDS: tuple[str, ...] = tuple(d.id for d in DEFAULT_DEFINITIONS)


def default_definitions() -> list[RuntimeDefinition]:
    """默认定义深拷贝列表 (调用方可安全修改, 不影响模块常量)。"""
    return [d.model_copy(deep=True) for d in DEFAULT_DEFINITIONS]


def default_definition(definition_id: str) -> RuntimeDefinition | None:
    """按 id 取默认定义 (未命中返回 None)。"""
    for d in DEFAULT_DEFINITIONS:
        if d.id == definition_id:
            return d.model_copy(deep=True)
    return None
