"""tests/providers/providers_helpers.py — Provider 测试数据构造 (唯一 basename)。

与 tests/dashboard/dashboard_helpers.py 同模式: 纯数据工厂, 被测试文件与
conftest 共用; basename 全仓库唯一 (providers_helpers) — backend-developer
skill 陷阱: 多非包目录共存时同名模块互相遮蔽。
"""

from __future__ import annotations

from providers.adapters import BUILTIN_PROVIDER_ADAPTERS
from providers.definitions import DEFAULT_PROVIDER_DEFINITIONS
from providers.models import ProviderDefinition, ProviderStatus


def make_definition(
    provider_id: str = "openai",
    *,
    name: str | None = None,
    type: str = "cloud",
    capabilities: list[str] | None = None,
    models: list[str] | None = None,
    status: ProviderStatus | str = ProviderStatus.ACTIVE,
    version: str = "1.0.0",
) -> ProviderDefinition:
    """构造 ProviderDefinition (字段可覆盖, 默认 openai cloud provider)。"""
    return ProviderDefinition(
        id=provider_id,
        name=name or f"Provider {provider_id}",
        type=type,
        capabilities=capabilities or ["chat", "generation"],
        models=models or [f"{provider_id}-model"],
        version=version,
        status=status,
    )


def default_hermes_definition() -> ProviderDefinition:
    """默认定义基线 hermes (内建, 只读)。"""
    return DEFAULT_PROVIDER_DEFINITIONS[0]


def builtin_adapter_ids() -> list[str]:
    """内置 Provider Adapter 实现 id 列表 (BUILTIN_PROVIDER_ADAPTERS 键)。"""
    return sorted(BUILTIN_PROVIDER_ADAPTERS)
