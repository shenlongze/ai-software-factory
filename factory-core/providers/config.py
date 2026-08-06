"""providers/config.py — runtime_preferences.provider 字段语义 (Phase 8A 只定义, 8C 实现选择)。

设计依据:
- phase8-plan.md §5 配置模型: project.yaml runtime_preferences (Phase 6A 已有字段)
  在 Phase 8 生效 — 每任务类型的偏好条目可携带 provider:
  ```yaml
  runtime_preferences:
    development:   { runtime: hermes,   provider: openai }
    documentation: { runtime: claude-runtime, provider: claude }
    local:         { provider: ollama }
  ```
- 语义: runtime_preferences 为 dict[str, Any]; 键 = 任务类型 (development/
  documentation/...); 值 = dict (runtime/provider 等偏好键); provider 值 =
  Provider 目录中的定义 id (ProviderRegistry.get 可解析, 未注册时由选择逻辑
  降级 — Phase 8c)。
- 本阶段只定义解析辅助 (纯函数, 无选择逻辑): preferred_provider 从偏好 dict
  提取 task_type 的 provider id; 选择优先级 (显式项目配置 > Agent 要求 >
  Runtime 能力 > Registry 默认) 与注入逻辑 (ExecutionRunner 可选注入) 属
  Phase 8c 范围, 本模块不实现。
"""

from __future__ import annotations

from typing import Any


def preferred_provider(preferences: dict[str, Any] | None, task_type: str) -> str | None:
    """从 runtime_preferences 解析 task_type 的 provider 偏好 id (未配置 → None)。

    Args:
        preferences: project.yaml runtime_preferences (dict 或 None)。
        task_type: 任务类型键 (如 "development" / "local")。

    Returns:
        provider 定义 id (偏好条目缺失 / 非 dict / provider 键缺失或为空 → None)。
    """
    if not preferences:
        return None
    entry = preferences.get(task_type)
    if not isinstance(entry, dict):
        return None
    provider_id = entry.get("provider")
    if not provider_id:
        return None
    return str(provider_id).strip() or None
