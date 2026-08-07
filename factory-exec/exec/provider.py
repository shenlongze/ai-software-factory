"""factory-exec/exec/provider.py — Provider 接口 + 注册表 (Agent 不知道 Provider 细节)。

设计依据 (docs/architecture/phase-a-execution-mvp-design.md §3):
```python
class ProviderRequest:    # 最小输入
    task_context: str     # 任务 + 上下文
    sandbox_path: str     # 工作副本路径
    max_tokens: int

class ProviderResponse:   # 最小输出
    content: str          # 模型回复 (代码/说明)
    usage: dict           # token/成本
    error: str | None

# 接口: generate(request) → response
# Adapter 实现: anthropic.py / openai.py / local.py (Phase A 实现 1 个真实)
```

要求:
- Agent 只调 generate(), 不知 Provider 细节 (模型/API/格式)
- usage → 成本记录 (8B-3 语义)
- error → 失败处理 (Runtime 转 ExecutionResult failed + org.execution.failed)

ProviderRegistry: 注册/按 id 取, 支持未来多 Provider (不绑模型);
注册表只做 id → Adapter 映射, 无业务逻辑。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator


class ProviderError(Exception):
    """Provider 调用失败 (无 key / HTTP 错误 / 网络错误 / 解析失败)。

    消息以稳定前缀开头 (如 \"anthropic api key missing: ...\") 供测试/审计断言;
    Runtime 捕获后转 ExecutionResult failed (error=消息) + org.execution.failed。
    """


class ProviderRequest(BaseModel):
    """Provider 最小输入 (设计 §3): 任务上下文 + 沙箱路径 + token 预算。"""

    task_context: str
    sandbox_path: str = ""
    max_tokens: int = 4096

    @field_validator("sandbox_path", mode="before")
    @classmethod
    def _path_none(cls, v: Any) -> Any:
        return v if v is not None else ""


class ProviderResponse(BaseModel):
    """Provider 最小输出 (设计 §3): content + usage + error。"""

    content: str = ""
    usage: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @field_validator("usage", mode="before")
    @classmethod
    def _usage_none(cls, v: Any) -> Any:
        return v if v is not None else {}

    @property
    def ok(self) -> bool:
        """调用成功判定 (error 为空即成功)。"""
        return not self.error


@runtime_checkable
class ProviderInterface(Protocol):
    """统一 Provider 接口 (Agent/Registry 只依赖此 Protocol)。

    provider_id: 注册表键 (如 \"anthropic\" / \"mock\"); generate(request) →
    ProviderResponse (失败也返回 response, error 承载原因 — 不抛裸异常,
    除 ProviderError 配置缺口外)。
    """

    provider_id: str

    def generate(self, request: ProviderRequest) -> ProviderResponse: ...


class ProviderRegistry:
    """Provider 注册表 (id → Adapter; 支持未来多 Provider, 不绑模型)。

    register: 注册 Adapter (id 冲突覆盖 — 同 id 后注册优先, 测试注入 mock
    便捷); get: 按 id 取 (未注册 → None); list/ids: 枚举已注册。
    """

    def __init__(self) -> None:
        self._providers: dict[str, ProviderInterface] = {}

    def register(self, provider: ProviderInterface) -> None:
        """注册 Adapter (provider_id 冲突 → 覆盖, 后注册优先)。"""
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> ProviderInterface | None:
        """按 id 取 Adapter; 未注册 → None (调用方报配置缺口)。"""
        return self._providers.get(provider_id)

    def list(self) -> list[ProviderInterface]:
        """全部已注册 Adapter (按 id 排序, 审计友好)。"""
        return [self._providers[k] for k in sorted(self._providers)]

    def ids(self) -> list[str]:
        """已注册 id 列表 (按 id 排序)。"""
        return sorted(self._providers)

    def count(self) -> int:
        return len(self._providers)


def default_registry() -> ProviderRegistry:
    """默认注册表: 内置真实 Anthropic Adapter (无 key 时 generate 抛清晰
    ProviderError — 配置缺口响亮暴露, 不静默降级)。

    Adapter 懒加载 (延迟 import anthropic → httpx 依赖只在需要时加载;
    无 httpx 环境删除 providers 目录即等同未注册该 Provider)。
    """
    registry = ProviderRegistry()
    try:
        from .providers.anthropic import AnthropicProvider

        registry.register(AnthropicProvider())
    except ImportError:  # pragma: no cover — httpx 缺失 (声明依赖, 理论不可达)
        pass
    return registry
