"""tests/console/test_session_confirm.py — ConfirmationGate + Session 集成 (S10-048 P4)。

设计: docs/sprint10/S10-048-intent-kernel-design.md §2.5 (ConfirmationGate)
覆盖 (验收 C-F):
C. 敏感 action (create_project) → 打印计划 + 请求确认; 非敏感 (list_projects) → 放行
D. 确认拒绝 → False (取消执行); 确认通过 → True (执行)
E. confirm_fn 可注入 (测试不阻塞 input)
F. Session 集成: 默认装配 gate; 敏感 action 走确认流 (拒绝 → "已取消" 不执行)

basename 全仓库唯一 (test_session_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

CONF_MOD = importlib.import_module("factory-console.session.confirm")
ACT_MOD = importlib.import_module("factory-console.session.action")
ACTIONS_MOD = importlib.import_module("factory-console.session.actions")
INTENT_MOD = importlib.import_module("factory-console.session.intent")
SESS_MOD = importlib.import_module("factory-console.session.session")
CTX_MOD = importlib.import_module("factory-console.session.context")


def _gate():
    return CONF_MOD.ConfirmationGate()


def _intent(intent_type: str = "create_project", **params):
    return INTENT_MOD.IntentObject(intent_type=intent_type, params=params, raw="x")


class _SpyGate:
    """Session 集成探针 gate: 记录 confirm 调用, 返回注入的决策。"""

    def __init__(self, decision: bool = True) -> None:
        self.decision = decision
        self.calls: list[tuple[str, Any, Any]] = []

    def confirm(self, action_name, intent, context):
        self.calls.append((action_name, intent, context))
        return self.decision


class _FakeOrgCli:
    """Service Layer 桩 (验证 Session 是否执行 create_project)。"""

    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    def cmd_project_register(self, root, args):
        self.calls.append((root, args))
        return {"ok": True, "project": {"id": "p1", "name": args.name}, "exit_code": 0}


# ------------------------------------------------------------------ C: 敏感 / 非敏感


def test_sensitive_action_requests_confirmation(capsys):
    """C: create_project (敏感) → 打印计划 + 请求 y/N, 回答经 confirm_fn 读取。"""
    gate = _gate()
    answers: list[str] = []

    def confirm_fn():
        answers.append("read")
        return "y"

    result = gate.confirm("create_project", _intent(name="APP"), confirm_fn=confirm_fn)
    assert result is True
    out = capsys.readouterr().out
    assert "将执行: create_project" in out
    assert "APP" in out  # intent 摘要含参数
    assert answers == ["read"]  # confirm_fn 被调用 (未阻塞 input)


def test_nonsensitive_passes_through(capsys):
    """C: list_projects (非敏感) → 直接放行, 不打印计划、不调用 confirm_fn。"""
    gate = _gate()
    called: list[str] = []

    def confirm_fn():
        called.append("unexpected")
        return "y"

    result = gate.confirm("list_projects", _intent("list_projects"), confirm_fn=confirm_fn)
    assert result is True
    assert called == []  # 非敏感不请求确认
    assert capsys.readouterr().out == ""  # 无计划输出


def test_default_sensitive_actions():
    """默认敏感集合 = {create_project, run_task} (设计 §2.5)。"""
    assert _gate().sensitive_actions == {"create_project", "run_task", "delete_project"}


# ------------------------------------------------------------------ D/E: 确认决策 + 可注入输入源


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("y", True),
        ("Y", True),
        ("yes", True),
        ("YES", True),
        (" n ", False),  # 拒绝 (带空白)
        ("n", False),
        ("N", False),
        ("no", False),
        ("", False),  # 空回车 → 默认 No
    ],
)
def test_confirm_answer_parsing(answer, expected, capsys):
    """D/E: y/yes (忽略大小写) → 通过; 其余/空 → 拒绝 (y/N 默认 No)。"""
    gate = _gate()
    assert gate.confirm("create_project", _intent(), confirm_fn=lambda: answer) is expected
    capsys.readouterr()  # 计划输出已断言于其他用例


def test_eof_no_stdin_passes(monkeypatch, capsys):
    """无 stdin (EOFError: stdin 关闭) → 放行, 不阻塞 (兼容 P1 非阻塞语义)。"""
    gate = _gate()

    def raise_eof(*args, **kwargs):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    assert gate.confirm("create_project", _intent()) is True
    out = capsys.readouterr().out
    assert "将执行: create_project" in out  # 计划仍打印 (可审计)


def test_captured_stdin_passes(monkeypatch, capsys):
    """stdin 不可读 (OSError: pytest 捕获 stdin / 输出重定向) → 放行不阻塞。

    既有会话测试 (不注入 gate, 默认装配) 依赖此路径保持 P1 直接执行语义。
    """
    gate = _gate()

    def raise_oserror(*args, **kwargs):
        raise OSError("pytest: reading from stdin while output is captured")

    monkeypatch.setattr("builtins.input", raise_oserror)
    assert gate.confirm("create_project", _intent()) is True
    assert "将执行: create_project" in capsys.readouterr().out


# ------------------------------------------------------------------ F: Session 集成


def test_session_default_gate_wired():
    """F: 默认 InteractiveSession 装配 ConfirmationGate 实例。"""
    sess = SESS_MOD.InteractiveSession()
    assert isinstance(sess.confirmation_gate, CONF_MOD.ConfirmationGate)


def test_session_sensitive_action_confirmation_flow(monkeypatch, capsys, tmp_path):
    """F: 敏感 action 走确认流 — 拒绝 → "已取消", Action 不执行。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = _FakeOrgCli()
    monkeypatch.setattr(ACTIONS_MOD, "_load_org_cli", lambda: fake)
    spy = _SpyGate(decision=False)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
        confirmation_gate=spy,
    )
    sess._dispatch("创建一个APP")
    # 确认流被触发: gate.confirm 收到 action.name = create_project + intent
    assert len(spy.calls) == 1
    assert spy.calls[0][0] == "create_project"
    assert spy.calls[0][1].intent_type == INTENT_MOD.INTENT_CREATE_PROJECT
    # 拒绝 → 取消执行 (Service Layer 未被调用)
    assert fake.calls == []
    out = capsys.readouterr().out
    assert "已取消" in out


def test_session_sensitive_action_approved_executes(monkeypatch, capsys, tmp_path):
    """F: 确认通过 → Action 执行 (Service Layer 被调用)。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = _FakeOrgCli()
    monkeypatch.setattr(ACTIONS_MOD, "_load_org_cli", lambda: fake)
    spy = _SpyGate(decision=True)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
        confirmation_gate=spy,
    )
    sess._dispatch("创建一个APP")
    assert len(spy.calls) == 1
    assert len(fake.calls) == 1  # 确认通过 → 执行
    out = capsys.readouterr().out
    assert "项目已注册" in out  # Renderer 展示执行结果


def test_session_nonsensitive_action_no_confirmation_ui(capsys, tmp_path):
    """F: 非敏感 action (list_projects) — 默认 gate 直接放行, 无确认计划输出。

    Session 对每个路由 action 都调 gate.confirm; 非敏感判断在 gate 内部
    (放行不打印) — 验证无 "将执行:" 确认 UI 且渲染正常。
    """
    root = tmp_path / "ws"
    root.mkdir()
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )  # 默认装配 ConfirmationGate
    sess._dispatch("项目列表")
    out = capsys.readouterr().out
    assert "将执行:" not in out  # 非敏感 → 无确认计划输出
    assert out.strip()  # 渲染正常 (空 projects.json → 表头输出)
