"""providers/events.py — provider.* 审计事件辅助 (经 EventLogger, Phase 8A, ADR-0022)。

设计依据:
- phase8-plan.md §Q6 事件: 生命周期 provider.registered / provider.removed /
  provider.viewed; 执行 provider.selected / provider.execution.started /
  provider.execution.completed / provider.execution.failed — 经 EventLogger
  (唯一事实源, ADR-0001 决策 1: 事件类型扩展 = 加 EventType 枚举成员, 不改表结构)。
- 参照 understanding/events.py 模式: 辅助函数封装 payload 契约; logger 可缺省
  (None → 返回 None); 只发审计事件, 不触碰任何业务状态 (只读/写分离)。
- source 约定: 注册表/服务层缺省 "provider_registry"; CLI 读命令经 source="cli"
  直接 logger.record (同 dashboard.viewed 模式, CLI 不依赖本模块 — Removal
  Isolation: 删除 providers 不影响 CLI 其他命令)。

payload 契约 (Dashboard Provider View 事件聚合与 CLI --json 出口一致):
- provider.registered: name/type/version/status/capabilities/models
- provider.removed: name/type/version/status
- provider.viewed: provider_id/action/count/type/status/default
- provider.selected: provider_id/model/default (stage=selected 或 default);
  Phase 8B-1 (ADR-0023) 增量: execution_id (关联执行) + source (选择层来源,
  explicit|project|agent|runtime|default)
- provider.execution.started: provider_id/model/request_id (+ execution_id, 8B-1)
- provider.execution.completed: provider_id/model/usage/result=OK (+ execution_id, 8B-1)
- provider.execution.failed: provider_id/model/error/result=ERROR (+ execution_id, 8B-1)
"""

from __future__ import annotations

from typing import Any

from events.models import Event, EventType


def record_provider_registered(
    logger: Any,
    *,
    definition: Any,
    source: str = "provider_registry",
) -> Event | None:
    """Provider 定义注册入库 (ProviderRegistry.register, 存储先落地、事件后发)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.PROVIDER_REGISTERED,
        source=source,
        stage=definition.status.value.lower(),
        action="register provider",
        result="OK",
        payload={
            "provider_id": definition.id,
            "name": definition.name,
            "type": definition.type,
            "version": definition.version,
            "status": definition.status.value,
            "capabilities": definition.capabilities,
            "models": definition.models,
            "description": definition.description,
        },
    )


def record_provider_removed(
    logger: Any,
    *,
    definition: Any,
    source: str = "provider_registry",
) -> Event | None:
    """Provider 定义移除 (ProviderRegistry.remove, 持久化层已删除后发出)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.PROVIDER_REMOVED,
        source=source,
        stage="removed",
        action="remove provider",
        result="OK",
        payload={
            "provider_id": definition.id,
            "name": definition.name,
            "type": definition.type,
            "version": definition.version,
            "status": definition.status.value,
        },
    )


def record_provider_viewed(
    logger: Any,
    *,
    provider_id: str,
    action: str = "view provider",
    count: int | None = None,
    default: str | None = None,
    source: str = "cli",
) -> Event | None:
    """Provider 目录被查看 (CLI list/show 读命令审计, ADR-0002; source 缺省 cli)。"""
    if logger is None:
        return None
    payload: dict[str, Any] = {"provider_id": provider_id, "action": action}
    if count is not None:
        payload["count"] = count
    if default is not None:
        payload["default"] = default
    return logger.record(
        EventType.PROVIDER_VIEWED,
        source=source,
        stage="viewed",
        action=action,
        result="OK",
        payload=payload,
    )


def record_provider_selected(
    logger: Any,
    *,
    provider_id: str,
    model: str | None = None,
    default: bool | None = None,
    source: str = "provider_registry",
    stage: str = "selected",
    action: str = "select provider",
    execution_id: str | None = None,
    selection_source: str | None = None,
) -> Event | None:
    """Provider 被选中 (执行前选择 / set_default 持久化默认, stage 区分)。

    Phase 8B-1 (ADR-0023) 增强: execution_id 关联具体执行 (payload 键
    execution_id); selection_source 为选择链来源层 (payload 键 source,
    explicit|project|agent|runtime|default, 见 providers/selector.py) — 两个
    键都是可选的增量 payload, 不破坏 Phase 8A 既有载荷契约。
    """
    if logger is None:
        return None
    payload: dict[str, Any] = {"provider_id": provider_id}
    if model is not None:
        payload["model"] = model
    if default is not None:
        payload["default"] = default
    if execution_id is not None:
        payload["execution_id"] = execution_id
    if selection_source is not None:
        payload["source"] = selection_source
    return logger.record(
        EventType.PROVIDER_SELECTED,
        source=source,
        stage=stage,
        action=action,
        result="OK",
        payload=payload,
    )


def record_provider_usage(
    logger: Any,
    *,
    usage: Any,
    source: str = "provider_registry",
) -> Event | None:
    """使用记录落盘审计 (UsageStore.record / 集成层调用后发出, Phase 8B-2)。

    payload 契约 (phase8b2-plan.md §6): provider_id/execution_id/tokens
    ({prompt, completion})/estimated_cost/latency_ms/success (+ model/version/
    error 可选) — 估算计量 (非真实计费), 只审计不触碰任何业务状态。
    """
    if logger is None:
        return None
    payload: dict[str, Any] = {
        "provider_id": usage.provider_id,
        "tokens": {
            "prompt": usage.prompt_tokens,
            "completion": usage.completion_tokens,
        },
        "estimated_cost": usage.estimated_cost,
        "latency_ms": usage.latency_ms,
        "success": usage.success,
    }
    if usage.execution_id is not None:
        payload["execution_id"] = usage.execution_id
    if usage.model is not None:
        payload["model"] = usage.model
    if usage.version is not None:
        payload["version"] = usage.version
    if usage.error is not None:
        payload["error"] = usage.error
    return logger.record(
        EventType.PROVIDER_USAGE_RECORDED,
        source=source,
        stage="recorded",
        action="record provider usage",
        result="OK",
        payload=payload,
    )


def record_provider_execution_started(
    logger: Any,
    *,
    provider_id: str,
    model: str | None = None,
    request_id: str | None = None,
    source: str = "provider_registry",
    execution_id: str | None = None,
) -> Event | None:
    """Provider 执行开始 (adapter.generate/chat 调用前)。

    Phase 8B-1 (ADR-0023) 增强: execution_id 关联具体执行 (payload 键
    execution_id, 可选增量, 不破坏 Phase 8A 载荷契约)。
    """
    if logger is None:
        return None
    payload: dict[str, Any] = {"provider_id": provider_id}
    if model is not None:
        payload["model"] = model
    if request_id is not None:
        payload["request_id"] = request_id
    if execution_id is not None:
        payload["execution_id"] = execution_id
    return logger.record(
        EventType.PROVIDER_EXECUTION_STARTED,
        source=source,
        stage="running",
        action="execute provider",
        result="OK",
        payload=payload,
    )


def record_provider_execution_completed(
    logger: Any,
    *,
    provider_id: str,
    model: str | None = None,
    usage: dict[str, Any] | None = None,
    source: str = "provider_registry",
    execution_id: str | None = None,
) -> Event | None:
    """Provider 执行成功 (response.ok, 终态)。

    Phase 8B-1 (ADR-0023) 增强: execution_id 关联具体执行 (可选增量 payload)。
    """
    if logger is None:
        return None
    payload: dict[str, Any] = {"provider_id": provider_id}
    if model is not None:
        payload["model"] = model
    if usage:
        payload["usage"] = usage
    if execution_id is not None:
        payload["execution_id"] = execution_id
    return logger.record(
        EventType.PROVIDER_EXECUTION_COMPLETED,
        source=source,
        stage="completed",
        action="execute provider",
        result="OK",
        payload=payload,
    )


def record_provider_execution_failed(
    logger: Any,
    *,
    provider_id: str,
    error: str,
    model: str | None = None,
    source: str = "provider_registry",
    execution_id: str | None = None,
) -> Event | None:
    """Provider 执行失败 (response.error 或意外异常, 终态 result=ERROR)。

    Phase 8B-1 (ADR-0023) 增强: execution_id 关联具体执行 (可选增量 payload)。
    """
    if logger is None:
        return None
    payload: dict[str, Any] = {"provider_id": provider_id, "error": error}
    if model is not None:
        payload["model"] = model
    if execution_id is not None:
        payload["execution_id"] = execution_id
    return logger.record(
        EventType.PROVIDER_EXECUTION_FAILED,
        source=source,
        stage="failed",
        action="execute provider",
        result="ERROR",
        payload=payload,
    )
