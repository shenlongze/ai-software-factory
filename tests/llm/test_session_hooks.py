"""会话级 Hooks 单测 (S10-127 M4.1/M4.2/M4.3)。

覆盖:
- 事件框架: 注册/分发/deny 短路/inject 收集
- SessionStart: 有断点 → inject 续接
- PreCompact: 写 Spine handoff (低权威 agent_claim)
- SessionEnd: 从对话提取 decision/error→learning → 记忆 5 类
- PreToolUse: 危险动作 deny; 敏感动作放行 (不误伤现有审批)
- dispatch 集成: git_push 被拦截; project_scan 正常
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SH = _ROOT / "factory-console" / "session" / "session_hooks.py"

for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


@pytest.fixture(scope="module")
def sh():
    from factory_console.session import session_hooks as _sh
    return _sh


def test_framework_register_fire_deny_inject(sh):
    h = sh.SessionHooks()
    h.register("PreToolUse", lambda ctx: {"action": "deny", "reason": "no"})
    h.register("SessionStart", lambda ctx: {"action": "inject", "content": "hi"})
    denied = h.denied(h.fire("PreToolUse", {}))
    assert denied and denied["reason"] == "no"
    assert h.injected(h.fire("SessionStart", {})) == "hi"
    # 未知事件拒绝
    with pytest.raises(ValueError):
        h.register("BadEvent", lambda ctx: None)


def test_pre_tool_use_danger_deny_sensitive_allow(sh):
    r = sh.pre_tool_use_hook({"tool_id": "git_push"})
    assert r and r["action"] == "deny"
    r2 = sh.pre_tool_use_hook({"tool_id": "delete"})
    assert r2 and r2["action"] == "deny"
    # 敏感动作: 放行 (现有审批流程处理)
    assert sh.pre_tool_use_hook({"tool_id": "create_task"}) is None
    assert sh.pre_tool_use_hook({"tool_id": "project_scan"}) is None


def test_session_start_inject_when_resume(sh, tmp_path):
    from factory_console.session.handoff import ProjectSpine

    sp = ProjectSpine.load(tmp_path, "p1")
    sp.set_resume_point(task_id="T-1", note="做到一半", source="verified_state")
    sp.save(tmp_path)
    r = sh.session_start_hook({"data_dir": str(tmp_path), "project_id": "p1"})
    assert r and r["action"] == "inject"
    assert "T-1" in r["content"]
    # 无断点 → None
    sp2 = ProjectSpine.load(tmp_path, "p2")
    sp2.save(tmp_path)
    assert sh.session_start_hook({"data_dir": str(tmp_path), "project_id": "p2"}) is None


def test_pre_compact_writes_spine(sh, tmp_path):
    from factory_console.session.handoff import ProjectSpine

    sp = ProjectSpine.load(tmp_path, "p1")
    sp.save(tmp_path)
    sh.pre_compact_hook({"data_dir": str(tmp_path), "project_id": "p1",
                         "session_id": "s1", "last_answer": "正在做M4",
                         "current_task": "T-9"})
    sp2 = ProjectSpine.load(tmp_path, "p1")
    hc = sp2.data.get("handoff_card") or {}
    assert "正在做M4" in hc.get("progress", "")
    assert sp2.data["resume_point"]["task_id"] == "T-9"
    assert hc.get("source") == "agent_claim"  # 低权威, 仅参考


def test_session_end_extracts_memory(sh, tmp_path):
    from factory_console.session.project_memory import MemoryStore

    msgs = [
        {"role": "system", "content": "【系统】必须围绕用户问题回答, 不要再调用工具"},  # 噪音, 不应提取
        {"role": "assistant", "content": "我决定采用 Server Actions 方案"},
        {"role": "user", "content": "报错 401 权限失败, 解决方法是换 api key"},
        {"role": "assistant", "content": "记住以后都用 Pydantic 校验"},
    ]
    sh.session_end_hook({"data_dir": str(tmp_path), "project_id": "p1", "messages": msgs})
    mem = MemoryStore.load(tmp_path, "p1")
    kinds = {e["kind"] for e in mem.entries}
    assert "decision" in kinds, [e["text"] for e in mem.entries]
    assert "error" in kinds
    assert "learning" in kinds
    # 权威: agent_claim (AI 自述, 低权威)
    for e in mem.entries:
        assert e["authority"] == "agent_claim"
    # system 提示不提取 (无噪音)
    assert not any("不要再调用工具" in e["text"] for e in mem.entries)


def test_dispatch_integration_deny_and_allow():
    from factory_console.session import agent_loop as _al

    # 危险动作被 PreToolUse 拦截
    r = _al.dispatch("git_push", {}, root="/tmp", project_id="p", service=None, ctx={})
    assert r.get("ok") is False
    assert "拦截" in str(r.get("error") or "")
    # 普通工具放行 (不被 hooks 拦截; /tmp 无真实数据 → 执行层报错, 但非"拦截")
    r2 = _al.dispatch("project_scan", {}, root="/tmp", project_id="p", service=None, ctx={})
    assert "拦截" not in str(r2.get("error") or "")
