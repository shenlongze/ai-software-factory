"""权限模式化单测 (S10-127 P1.5)。

覆盖:
- plan 模式: 写操作 (create_task) deny, 只读 (project_scan) 放行
- acceptEdits/normal: 写操作放行 (现有审批流程处理)
- auto: 写操作放行 (审计标记)
- 危险动作: 任何模式都 deny
- load_permission_mode: 从文件读 / 缺省 normal
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from factory_console.session import session_hooks as _sh
from factory_console.session import agent_loop as _al


def test_plan_mode_denies_write():
    r = _sh.pre_tool_use_hook({"tool_id": "create_task", "permission_mode": "plan"})
    assert r and r["action"] == "deny"
    assert "plan" in r["reason"]
    r2 = _sh.pre_tool_use_hook({"tool_id": "task_action", "permission_mode": "plan"})
    assert r2 and r2["action"] == "deny"
    r3 = _sh.pre_tool_use_hook({"tool_id": "chain_start", "permission_mode": "plan"})
    assert r3 and r3["action"] == "deny"


def test_plan_mode_allows_read():
    r = _sh.pre_tool_use_hook({"tool_id": "project_scan", "permission_mode": "plan"})
    assert r is None
    r2 = _sh.pre_tool_use_hook({"tool_id": "read_code", "permission_mode": "plan"})
    assert r2 is None


def test_accept_edits_allows_write():
    assert _sh.pre_tool_use_hook({"tool_id": "create_task", "permission_mode": "acceptEdits"}) is None
    assert _sh.pre_tool_use_hook({"tool_id": "create_task", "permission_mode": "normal"}) is None
    assert _sh.pre_tool_use_hook({"tool_id": "create_task", "permission_mode": "auto"}) is None


def test_dangerous_always_denied():
    for mode in ("normal", "plan", "acceptEdits", "auto"):
        r = _sh.pre_tool_use_hook({"tool_id": "git_push", "permission_mode": mode})
        assert r and r["action"] == "deny", mode


def test_load_permission_mode(tmp_path):
    # 缺省 normal
    assert _sh.load_permission_mode(str(tmp_path)) == "normal"
    # 文件生效
    (tmp_path / "session_permissions.json").write_text(
        json.dumps({"permission_mode": "plan"}), encoding="utf-8")
    assert _sh.load_permission_mode(str(tmp_path)) == "plan"
    # 非法值 → normal
    (tmp_path / "session_permissions.json").write_text(
        json.dumps({"permission_mode": "bogus"}), encoding="utf-8")
    assert _sh.load_permission_mode(str(tmp_path)) == "normal"


def test_dispatch_plan_mode_integration(tmp_path):
    # plan 模式下 dispatch 写工具被拦截
    (tmp_path / "session_permissions.json").write_text(
        json.dumps({"permission_mode": "plan"}), encoding="utf-8")
    r = _al.dispatch("create_task", {"title": "x"}, root=str(tmp_path), project_id="p",
                     service=None, ctx={})
    assert r.get("ok") is False
    assert "plan" in str(r.get("error") or "")
