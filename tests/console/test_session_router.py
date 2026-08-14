"""tests/console/test_session_router.py — IntentRouter 声明式路由 (S10-048 P0)。

设计: docs/sprint10/S10-048-intent-kernel-design.md §2.4
覆盖 (验收 D 注册式 / E 未路由明确):
- 默认映射: create_project / list_projects / show_status → 同名 Action (经 registry.get)
- register_route 注册/覆盖 (声明式映射, 无 if/else 分派); 空值校验
- 可扩展性: 新意图 register_route + register Action 各一行, 路由逻辑零改动
- 未路由 (类型无映射 / 映射 Action 未注册) → UnknownIntentError (明确, 不静默)

basename 全仓库唯一 (test_session_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib

import pytest

ROUTER_MOD = importlib.import_module("factory-console.session.router")
ACT_MOD = importlib.import_module("factory-console.session.action")
INTENT_MOD = importlib.import_module("factory-console.session.intent")


def _registry_with(names):
    """注册表: 每个 name 一个最小 Action (handler 返回固定结果)。"""
    registry = ACT_MOD.ActionRegistry()
    for name in names:
        registry.register(
            ACT_MOD.Action(
                name=name,
                description=name,
                handler=lambda ctx, n=name: ACT_MOD.ActionResult(message=n),
            )
        )
    return registry


def _intent(intent_type):
    return INTENT_MOD.IntentObject(intent_type=intent_type, raw="x")


def test_default_routes_resolve():
    router = ROUTER_MOD.IntentRouter()
    registry = _registry_with(["create_project", "list_projects", "show_status"])
    for intent_type in ("create_project", "list_projects", "show_status"):
        action = router.route(_intent(intent_type), registry)
        assert action.name == intent_type  # 声明式映射解析到 Action 实例


def test_register_route_adds_and_overrides():
    router = ROUTER_MOD.IntentRouter(mapping={})
    router.register_route("create_project", "create_project")
    assert router.routes() == {"create_project": "create_project"}
    router.register_route("create_project", "other_action")  # 覆盖
    assert router.routes()["create_project"] == "other_action"
    with pytest.raises(ValueError):
        router.register_route("", "x")
    with pytest.raises(ValueError):
        router.register_route("x", "")


def test_router_extension_without_code_change():
    """可扩展性验收: 新意图只需 register_route + register Action, 路由逻辑零改动。"""
    router = ROUTER_MOD.IntentRouter()
    router.register_route("show_cost", "show_cost")
    registry = _registry_with(["create_project", "show_cost"])
    action = router.route(_intent("show_cost"), registry)
    assert action.name == "show_cost"


def test_route_unmapped_intent_raises():
    """E: 类型无映射 → UnknownIntentError, 错误信息明确 (不静默)。

    S10-049: run_task 已纳入默认路由 (→ agent.execute_task), 未映射示例改用 show_cost。
    """
    router = ROUTER_MOD.IntentRouter()
    registry = _registry_with(["create_project"])
    with pytest.raises(ROUTER_MOD.UnknownIntentError) as exc:
        router.route(_intent("show_cost"), registry)
    assert "show_cost" in str(exc.value)
    assert "未配置路由" in str(exc.value)


def test_route_mapped_but_unregistered_raises():
    """E: 映射存在但 Action 未注册 → UnknownIntentError (路由悬空, 明确报错)。"""
    router = ROUTER_MOD.IntentRouter()
    registry = _registry_with([])  # 空注册表
    with pytest.raises(ROUTER_MOD.UnknownIntentError) as exc:
        router.route(_intent("create_project"), registry)
    assert "create_project" in str(exc.value)
    assert "未注册" in str(exc.value)
