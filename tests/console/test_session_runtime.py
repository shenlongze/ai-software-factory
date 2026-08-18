
"""tests/console/test_session_runtime.py — InteractiveSession 运行时 (S10-047 Task 001)。

设计: docs/sprint10/S10-047-session-design.md §2 Session Loop / §5 测试
覆盖:
- session 启动 (banner 含 "AI Factory")
- exit / quit → 优雅退出 rc 0
- 空输入 → 继续 (不退出, 不 dispatch)
- 未知输入 → 友好提示 (不崩溃)
- Ctrl+C / EOF → 优雅退出 rc 0
- cli_factory main 集成: 无参数 / --interactive → session; 有命令 → 原逻辑

basename 全仓库唯一 (test_console_* 前缀)。
"""

from __future__ import annotations

import importlib
import sys

import pytest

class _FakeChat075:
    """测试 ChatService (固定回答, 不依赖真实 LLM)。"""

    def answer(self, question, **kw):
        return f"AI: 测试回答 {question}"

    def is_fallback(self, a):
        return False

SESSION_MOD = importlib.import_module("factory-console.session.session")
CLI_MOD = importlib.import_module("factory-console.cli_factory")


def _feed_inputs(monkeypatch, inputs):
    """把 input() 替换为按序列吐出的迭代器 (耗尽 → StopIteration 证明仍在等待)。"""
    it = iter(inputs)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it))
    return it


def test_banner_contains_ai_factory(monkeypatch, capsys):
    _feed_inputs(monkeypatch, ["exit"])
    rc = SESSION_MOD.InteractiveSession().run()
    out = capsys.readouterr().out
    assert rc == 0
    assert "AI Factory" in out


def test_exit_command(monkeypatch, capsys):
    _feed_inputs(monkeypatch, ["exit"])
    rc = SESSION_MOD.InteractiveSession().run()
    assert rc == 0
    assert "未知命令" not in capsys.readouterr().out  # exit 不触发 dispatch


def test_quit_command(monkeypatch, capsys):
    _feed_inputs(monkeypatch, ["quit"])
    rc = SESSION_MOD.InteractiveSession().run()
    assert rc == 0
    assert "未知命令" not in capsys.readouterr().out


def test_empty_input_continues(monkeypatch, capsys):
    _feed_inputs(monkeypatch, ["", "exit"])
    rc = SESSION_MOD.InteractiveSession().run()
    assert rc == 0
    assert "未知命令" not in capsys.readouterr().out  # 空输入不 dispatch


def test_empty_input_does_not_exit(monkeypatch):
    # 只喂空输入: 若空输入退出则 run 返回; 否则继续等待 → 迭代器耗尽抛 StopIteration
    _feed_inputs(monkeypatch, [""])
    with pytest.raises(StopIteration):
        SESSION_MOD.InteractiveSession().run()


def test_unknown_command_friendly_hint(monkeypatch, capsys):
    """S10-075: 未知输入 → AI 问答 (不再 '未知命令')。"""
    _feed_inputs(monkeypatch, ["foobar", "exit"])
    rc = SESSION_MOD.InteractiveSession(chat_service=_FakeChat075()).run()
    out = capsys.readouterr().out
    assert rc == 0
    assert "未知命令" not in out


def test_keyboard_interrupt_exits(monkeypatch, capsys):
    def raiser(prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", raiser)
    rc = SESSION_MOD.InteractiveSession().run()
    assert rc == 0


def test_eof_exits(monkeypatch, capsys):
    def raiser(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", raiser)
    rc = SESSION_MOD.InteractiveSession().run()
    assert rc == 0


# ---------------------------------------------------------------- main 集成


def test_main_no_args_enters_session(monkeypatch, capsys):
    _feed_inputs(monkeypatch, ["exit"])
    rc = CLI_MOD.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "AI Factory" in out  # banner 显示 → 无参数进入 session


def test_main_interactive_flag_enters_session(monkeypatch, capsys):
    _feed_inputs(monkeypatch, ["exit"])
    rc = CLI_MOD.main(["--interactive"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "AI Factory" in out


def test_main_with_args_unchanged_help(monkeypatch, capsys):
    # 有参数 → 原逻辑: --help 由 argparse 处理 (SystemExit 0, 非 session)
    with pytest.raises(SystemExit) as exc:
        CLI_MOD.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "输入 exit 或 quit 退出会话" not in out  # session banner 未出现 → 未进入 session


def test_main_unknown_command_still_rc2(monkeypatch, capsys):
    # 未知子命令 → argparse 错误 rc 2 (不被无参数分支吞掉)
    with pytest.raises(SystemExit) as exc:
        CLI_MOD.main(["bogus-cmd-xyz"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "bogus-cmd-xyz" in err


def test_main_run_help_still_argparse(monkeypatch, capsys):
    # run 子命令 → 原逻辑 (argparse help, SystemExit 0)
    with pytest.raises(SystemExit) as exc:
        CLI_MOD.main(["run", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--project" in out  # run 子命令自己的选项帮助
    assert "输入 exit 或 quit 退出会话" not in out  # 未进入 session