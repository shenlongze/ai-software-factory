"""tests/console/test_session_action.py — Action + ActionRegistry + ExecutionContext + ActionResult (S10-048 P0)。

设计: docs/sprint10/S10-048-intent-kernel-design.md §2.3
覆盖 (验收 D 注册式 + 权限):
- ActionRegistry: register / get / list (注册式, 无硬编码 if); 同名覆盖; list 排序
- Action: name/description/handler/permission/metadata 字段 + execute 委托 handler
- ExecutionContext: workspace/session/user/project/intent 字段;
  require("user") 基线全通过; require("project"/"admin") RBAC 未实现 → 明确 PermissionError
- ActionResult: ok/status/message/data/error + to_dict 渲染视图 (data 键提升)

basename 全仓库唯一 (test_session_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ACT_MOD = importlib.import_module("factory-console.session.action")
CTX_MOD = importlib.import_module("factory-console.session.context")


def _ctx(workspace="tmp/ws", **kw):
    """构造 ExecutionContext (session 为独立 SessionContext)。"""
    return ACT_MOD.ExecutionContext(
        workspace=Path(workspace),
        session=CTX_MOD.SessionContext(workspace=workspace),
        **kw,
    )


def _ok_action(name="demo"):
    def handler(context):
        return ACT_MOD.ActionResult(ok=True, status="ok", message=f"done {context.workspace}")

    return ACT_MOD.Action(name=name, description="demo action", handler=handler, permission="user")


# ------------------------------------------------------------------ ActionRegistry (验收 D)


def test_registry_register_get_list():
    registry = ACT_MOD.ActionRegistry()
    action = _ok_action()
    registry.register(action)
    assert registry.get("demo") is action
    assert registry.get("nope") is None  # 未注册 → None (调用方决定提示)
    assert [a.name for a in registry.list()] == ["demo"]
    # list 按 name 排序 (稳定性)
    other = _ok_action(name="aaa")
    registry.register(other)
    assert [a.name for a in registry.list()] == ["aaa", "demo"]


def test_registry_duplicate_register_overrides():
    registry = ACT_MOD.ActionRegistry()
    first, second = _ok_action(), _ok_action()
    registry.register(first)
    registry.register(second)
    assert registry.get("demo") is second  # 同名覆盖 (声明式语义)


def test_action_fields_and_execute():
    calls = []

    def handler(context):
        calls.append(context)
        return ACT_MOD.ActionResult(ok=True, status="ok", message="ok")

    action = ACT_MOD.Action(
        name="create_project",
        description="创建项目",
        handler=handler,
        permission="project",
        metadata={"service": "org.cli"},
    )
    assert action.name == "create_project"
    assert action.description == "创建项目"
    assert callable(action.handler)
    assert action.permission == "project"
    assert action.metadata["service"] == "org.cli"
    # execute 委托 handler (设计 §2.1: Action.execute(context))
    ctx = _ctx()
    result = action.execute(ctx)
    assert result.ok is True and calls == [ctx]


# ------------------------------------------------------------------ ExecutionContext


def test_execution_context_fields():
    ctx = _ctx(workspace="/tmp/ws", user="alice", project="p1")
    assert ctx.workspace == Path("/tmp/ws")
    assert ctx.session.workspace == "/tmp/ws"
    assert ctx.user == "alice"
    assert ctx.project == "p1"
    assert ctx.intent is None  # 派发时注入


def test_execution_context_require_baseline_user():
    ctx = _ctx()
    ctx.require("user")  # 基线权限全通过 (不抛)
    # RBAC 未实现 → 明确拒绝 (不静默降级)
    with pytest.raises(PermissionError):
        ctx.require("project")
    with pytest.raises(PermissionError):
        ctx.require("admin")


# ------------------------------------------------------------------ ActionResult


def test_action_result_fields_and_to_dict():
    result = ACT_MOD.ActionResult(
        ok=True,
        status="ok",
        message="已注册",
        data={"project": {"id": "p1", "name": "APP"}, "header": ["id"], "rows": [["p1"]]},
    )
    assert result.ok is True and result.status == "ok"
    assert result.error is None
    view = result.to_dict()
    assert view["ok"] is True and view["status"] == "ok"
    assert view["message"] == "已注册"
    # data 键提升 → 渲染视图直接可用 (表格/键值展示)
    assert view["project"] == {"id": "p1", "name": "APP"}
    assert view["header"] == ["id"] and view["rows"] == [["p1"]]


def test_action_result_error_dict():
    result = ACT_MOD.ActionResult(ok=False, status="error", message="失败", error="boom")
    view = result.to_dict()
    assert view["ok"] is False and view["status"] == "error"
    assert view["error"] == "boom"


def test_action_result_non_dict_data():
    result = ACT_MOD.ActionResult(ok=True, status="ok", message="m", data=[1, 2])
    view = result.to_dict()
    assert view["data"] == [1, 2]  # 非 dict → 保留 data 键
