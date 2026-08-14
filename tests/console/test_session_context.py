"""tests/console/test_session_context.py — SessionContext + ContextManager (S10-047 Task 002)。

设计: docs/sprint10/S10-047-session-design.md §3 (context.py — Task 002)
覆盖:
- create: session_id 自动生成 / workspace 注入 / 默认字段
- update: current_project / current_agent (context.current_project="demo" 风格)
- update: metadata 合并 / history 追加 / 未知字段落入 metadata
- read: get() 返回同一对象 (内存单例)
- to_dict: 只读快照

basename 全仓库唯一 (test_console_* 前缀)。
"""

from __future__ import annotations

import importlib

CONTEXT_MOD = importlib.import_module("factory-console.session.context")


def test_create_defaults():
    ctx = CONTEXT_MOD.SessionContext()
    assert ctx.session_id
    assert ctx.session_id.startswith("session-")
    assert ctx.workspace is None
    assert ctx.current_project is None
    assert ctx.current_agent is None
    assert ctx.metadata == {}
    assert ctx.history == []


def test_create_with_explicit_id_and_workspace():
    ctx = CONTEXT_MOD.SessionContext(session_id="s-1", workspace="/tmp/demo")
    assert ctx.session_id == "s-1"
    assert ctx.workspace == "/tmp/demo"


def test_update_current_project_and_agent():
    cm = CONTEXT_MOD.ContextManager(workspace="/tmp/demo")
    cm.update(current_project="demo")
    assert cm.get().current_project == "demo"
    cm.update(current_agent="developer-1")
    assert cm.get().current_agent == "developer-1"


def test_update_metadata_merge():
    cm = CONTEXT_MOD.ContextManager()
    cm.update(metadata={"goal": "hello"})
    cm.update(metadata={"mode": "fast"})
    assert cm.get().metadata == {"goal": "hello", "mode": "fast"}


def test_update_unknown_field_goes_to_metadata():
    cm = CONTEXT_MOD.ContextManager()
    cm.update(foo="bar")
    assert cm.get().metadata["foo"] == "bar"


def test_record_history():
    cm = CONTEXT_MOD.ContextManager()
    cm.record("help")
    cm.record("run demo")
    assert cm.get().history == ["help", "run demo"]


def test_read_returns_same_context_object():
    cm = CONTEXT_MOD.ContextManager()
    cm.update(current_project="demo")
    assert cm.get() is cm.get()  # 内存单例


def test_to_dict_snapshot():
    cm = CONTEXT_MOD.ContextManager(workspace="/tmp/w")
    cm.update(current_project="demo", metadata={"k": 1})
    cm.record("help")
    snap = cm.get().to_dict()
    assert snap["session_id"] == cm.get().session_id
    assert snap["workspace"] == "/tmp/w"
    assert snap["current_project"] == "demo"
    assert snap["current_agent"] is None
    assert snap["metadata"] == {"k": 1}
    assert snap["history"] == ["help"]
    # 快照不暴露可变内部: 改快照不影响上下文
    snap["metadata"]["k"] = 999
    assert cm.get().metadata["k"] == 1
