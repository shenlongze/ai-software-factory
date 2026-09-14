"""providers/config.py — runtime_preferences.provider 字段语义 (Phase 8A 定义, 8B-1 选择)。

设计依据:
- phase8-plan.md §5 配置模型: project.yaml runtime_preferences (Phase 6A 已有字段)
  在 Phase 8 生效 — 每任务类型的偏好条目可携带 runtime 与 provider:
  ```yaml
  runtime_preferences:
    development:   { runtime: hermes,   provider: openai }
    documentation: { runtime: claude-runtime, provider: claude }
    local:         { provider: ollama }
  ```
- phase8b1-status.md §2 (Phase 8B-1 增强): parse_runtime_preferences(preferences,
  task_type) → {runtime, provider} 完善 Phase 8A 的 preferred_provider; 选择链
  (providers/selector.py) 消费本模块解析结果, 本模块仍是无选择逻辑的纯解析层。
- runtime_default_provider: "Runtime 能力" 层 (优先级第 3) 的数据源 — Runtime
  目录定义 (runtimes/models.py RuntimeDefinition) 声明的默认 provider。模型本身
  无 provider 字段 (Core 零修改, ADR-0014 边界), 声明走 metadata 扩展:
  metadata.default_provider (或兼容旧形态的顶层 provider 属性); 本辅助对任意
  对象宽容读取 (getattr + dict 检查), 未声明 → None (选择链降级)。
- 语义: 偏好条目缺失 / 非 dict / 键缺失或空值 → None ({"runtime": None,
  "provider": None}); provider 值 = Provider 目录中的定义 id (未注册时由选择
  逻辑降级 — providers/selector.py)。
"""

from __future__ import annotations

from typing import Any


def preferred_provider(preferences: dict[str, Any] | None, task_type: str) -> str | None:
    """从 runtime_preferences 解析 task_type 的 provider 偏好 id (未配置 → None)。

    Phase 8A 契约 (保持兼容): 偏好条目缺失 / 非 dict / provider 键缺失或为空
    → None。Phase 8B-1 起委托 parse_runtime_preferences (单一解析事实源, DRY)。
    """
    return parse_runtime_preferences(preferences, task_type)["provider"]


def parse_runtime_preferences(
    preferences: dict[str, Any] | None, task_type: str,
) -> dict[str, str | None]:
    """解析 runtime_preferences.<task_type> 条目 → {"runtime", "provider"} (键恒在)。

    Args:
        preferences: project.yaml runtime_preferences (dict 或 None)。
        task_type: 任务类型键 (如 "development" / "local")。

    Returns:
        {"runtime": 偏好 runtime id | None, "provider": 偏好 provider id | None} —
        条目缺失 / 非 dict / 键缺失或空白 → None (值 strip 后为空同样归 None)。
    """
    if not preferences:
        return {"runtime": None, "provider": None}
    entry = preferences.get(task_type)
    if not isinstance(entry, dict):
        return {"runtime": None, "provider": None}
    return {
        "runtime": _clean(entry.get("runtime")),
        "provider": _clean(entry.get("provider")),
    }


def runtime_default_provider(runtime_definition: Any) -> str | None:
    """Runtime 目录定义声明的默认 provider id (未声明 → None)。

    读取顺序 (宽容, 对任意对象安全):
    1. metadata["default_provider"] (Phase 8B-1 推荐形态 — metadata 是
       RuntimeDefinition 的扩展容器, Core 零修改)。
    2. 顶层 provider 属性 (旧形态兼容, getattr 失败安全)。
    """
    if runtime_definition is None:
        return None
    metadata = getattr(runtime_definition, "metadata", None)
    if isinstance(metadata, dict):
        declared = metadata.get("default_provider")
        if declared:
            return str(declared).strip() or None
    declared = getattr(runtime_definition, "provider", None)
    if declared:
        return str(declared).strip() or None
    return None


def _clean(value: Any) -> str | None:
    """偏好键值清洗: 空/非字符串 → None; 字符串 strip 后为空 → None。"""
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
