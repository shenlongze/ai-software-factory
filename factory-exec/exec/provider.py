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
# Adapter 实现: anthropic.py / openai.py / local.py (Phase A 实现 2 个真实)
```

要求:
- Agent 只调 generate(), 不知 Provider 细节 (模型/API/格式)
- usage → 成本记录 (8B-3 语义)
- error → 失败处理 (Runtime 转 ExecutionResult failed + org.execution.failed)

ProviderRegistry: 注册/按 id 取, 支持未来多 Provider (不绑模型);
注册表只做 id → Adapter 映射, 无业务逻辑。

Provider 可替换铁律 (Phase A+++ Benchmark 设计): Anthropic ↔ OpenAI 同接口
切换零修改 (CLI --provider); 禁 mock 当能力证明 — 真实 HTTP 调用, 无 key
→ ProviderError 响亮暴露。

ProviderConfigChecker: 配置检查工具 — 枚举内置 Provider 的 key 环境变量,
检测缺失 → 明确提示 (哪个 key 未设置 + 如何设置), 供 CLI providers 命令
与 Benchmark 预检使用 (key 缺失 → BLOCKED 标注, 诚实不假装)。
"""

from __future__ import annotations

import os
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
    """默认注册表: 内置真实 Adapter (Anthropic + OpenAI; 无 key 时 generate 抛清晰
    ProviderError — 配置缺口响亮暴露, 不静默降级)。

    Adapter 懒加载 (延迟 import → httpx 依赖只在需要时加载;
    无 httpx 环境删除 providers 目录即等同未注册该 Provider)。
    """
    registry = ProviderRegistry()
    try:
        from .providers.anthropic import AnthropicProvider

        registry.register(AnthropicProvider())
    except ImportError:  # pragma: no cover — httpx 缺失 (声明依赖, 理论不可达)
        pass
    try:
        from .providers.openai import OpenAIProvider

        registry.register(OpenAIProvider())
    except ImportError:  # pragma: no cover — httpx 缺失 (声明依赖, 理论不可达)
        pass
    return registry


# ------------------------------------------------------------------ 配置检查

#: Provider id → (显示名, key 环境变量, 设置指引) — 单一事实源 (与 Adapter
#: 构造缺省一致; Adapter 的 key 解析在 generate 时读 env, 此处预检同源)。
PROVIDER_KEY_SPECS: dict[str, tuple[str, str, str]] = {
    "anthropic": (
        "Anthropic",
        "ANTHROPIC_API_KEY",
        "export ANTHROPIC_API_KEY=sk-ant-...  (https://console.anthropic.com)",
    ),
    "openai": (
        "OpenAI",
        "OPENAI_API_KEY",
        "export OPENAI_API_KEY=sk-...  (https://platform.openai.com/api-keys)",
    ),
}


class ProviderConfigStatus:
    """单个 Provider 配置状态 (provider_id/display/key_var/configured)。

    configured=True 仅表示 key 已设置, 不代表调用成功 (真实调用仍需
    Benchmark/run 验证 — 配置检查不假装能力)。
    """

    def __init__(
        self,
        *,
        provider_id: str,
        display: str,
        key_var: str,
        configured: bool,
    ) -> None:
        self.provider_id = provider_id
        self.display = display
        self.key_var = key_var
        self.configured = configured

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "display": self.display,
            "key_var": self.key_var,
            "configured": self.configured,
        }

    @property
    def ok(self) -> bool:
        return self.configured

    @property
    def message(self) -> str:
        """人类可读状态 (缺失 → 明确提示 + 指引, 响亮不静默)。"""
        if self.configured:
            return f"{self.display} (key={self.key_var}) 已配置 ✓"
        _, _, guide = PROVIDER_KEY_SPECS[self.provider_id]
        return f"{self.display} (key={self.key_var}) 未配置 ✗ — {guide}"


class ProviderConfigChecker:
    """Provider 配置预检 (key 缺失 → 明确提示 + 指引; Benchmark/CLI 预检用)。

    设计: 检查 key 是否设置 (os.environ), 不做网络调用 — 配置检查是能力
    前置门槛, 不是能力证明 (真实调用由 Benchmark 做, 无 key → BLOCKED 标注)。
    env: 可注入 dict (测试 monkeypatch os.environ 或传 env 覆盖)。
    """

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self._env = os.environ if env is None else env

    def check(self, provider_id: str | None = None) -> list[ProviderConfigStatus]:
        """检查全部内置 Provider (缺省) 或单个; 返回状态列表 (按 id 排序)。"""
        ids = [provider_id] if provider_id else list(PROVIDER_KEY_SPECS)
        statuses = []
        for pid in ids:
            if pid not in PROVIDER_KEY_SPECS:
                continue
            display, key_var, _ = PROVIDER_KEY_SPECS[pid]
            statuses.append(
                ProviderConfigStatus(
                    provider_id=pid,
                    display=display,
                    key_var=key_var,
                    configured=bool(self._env.get(key_var, "")),
                )
            )
        return statuses

    def any_configured(self) -> bool:
        """是否存在至少一个已配置 Provider (Benchmark 预检: False → 全部 BLOCKED)。"""
        return any(s.configured for s in self.check())

    def configured_ids(self) -> list[str]:
        """已配置 Provider id 列表 (按 id 排序; 空 = 无 key)。"""
        return [s.provider_id for s in self.check() if s.configured]

    def summary(self) -> dict[str, Any]:
        """结构化摘要 (CLI providers / Benchmark 预检 / 报告引用)。"""
        statuses = self.check()
        return {
            "providers": [s.to_dict() for s in statuses],
            "any_configured": any(s.configured for s in statuses),
            "configured_ids": [s.provider_id for s in statuses if s.configured],
            "blocked": [s.provider_id for s in statuses if not s.configured],
            "message": (
                "所有 Provider 已配置 (真实调用可用)"
                if all(s.configured for s in statuses)
                else "存在未配置 Provider (key 缺失 → 真实调用 BLOCKED, "
                "见各 provider 的 key_var 指引)"
            ),
        }
