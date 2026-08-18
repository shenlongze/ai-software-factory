"""tests/console/test_session_slash.py — Slash Command 框架 + 基础命令 (S10-047 Task 003/004)。

设计: docs/sprint10/S10-046-slash-command-design.md (Slash 定位/路由/边界)
     + docs/sprint10/S10-047-session-design.md §3 (slash.py — Task 003; commands.py — Task 004)
覆盖:
- 注册式框架: register / get / list / execute 解析分发 (无硬编码 if)
- 未知 slash → 明确提示 (含 /help 指引), 不静默
- /help 列出命令 (name + description)
- /status 显示 session/workspace/当前项目/当前 Agent (来自 SessionContext)
- /project 无参=列表 (复用 projects.json 数据口径) / 有参=切换 current_project
- /cost 成本接口占位 (会话近期活动摘要)
- /exit 退出 (宿主 session.running=False)
- session 集成: "/" 开头 → registry; 其它 → 未知提示 (Task 001 行为不回归)

basename 全仓库唯一 (test_console_* 前缀)。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

class _FakeChat075:
    """测试 ChatService (固定回答, 不依赖真实 LLM)。"""

    def answer(self, question, **kw):
        return f"AI: 测试回答 {question}"

    def is_fallback(self, a):
        return False

SLASH_MOD = importlib.import_module("factory-console.session.slash")
CMDS_MOD = importlib.import_module("factory-console.session.commands")
SESS_MOD = importlib.import_module("factory-console.session.session")
CTX_MOD = importlib.import_module("factory-console.session.context")
CFG_MOD = importlib.import_module("factory-console.config")
CLI_MOD = importlib.import_module("factory-console.cli_factory")


# ------------------------------------------------------------------ helpers


class _StubCommand(SLASH_MOD.SlashCommand):
    """极简桩命令: 记录 (args, context) 调用, 验证注册式分发。"""

    name = "stub"
    description = "stub 命令"

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, object]] = []

    def execute(self, args: str, context: object) -> int:
        self.calls.append((args, context))
        return 0


def _context(**kw):
    """构造带上下文的 SessionContext (workspace/current_project/current_agent/history)。"""
    cm = CTX_MOD.ContextManager(workspace=kw.get("workspace"))
    if kw.get("current_project"):
        cm.update(current_project=kw["current_project"])
    if kw.get("current_agent"):
        cm.update(current_agent=kw["current_agent"])
    for line in kw.get("history", []):
        cm.record(line)
    return cm.get()


def _write_projects(path: Path, projects: dict) -> None:
    """按 org 规范格式写 projects.json ({"projects": {id: {name}}} — FactoryCLI 同口径)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"projects": projects}), encoding="utf-8")


def _make_cli(tmp_path: Path):
    """hermetic FactoryCLI (同 test_cli_project_run 模式): config.json 指向 tmp data_dir。"""
    data_dir = tmp_path / ".factory"
    data_dir.mkdir(exist_ok=True)
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"core": {"data_dir": str(data_dir)}}), encoding="utf-8")
    config = CFG_MOD.ConfigProvider(
        user_config_file=cfg_file, env_file=tmp_path / ".env", environ={}
    )
    return CLI_MOD.FactoryCLI(config, root=tmp_path)


def _feed_inputs(monkeypatch, inputs):
    """input() 替换为按序列吐出 (耗尽 → StopIteration 证明仍在等待)。"""
    it = iter(inputs)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it))
    return it


# ------------------------------------------------------------------ 注册式框架 (Task 003)


def test_registry_register_get_list():
    registry = SLASH_MOD.SlashCommandRegistry()
    cmd = _StubCommand()
    registry.register(cmd)
    assert registry.get("stub") is cmd
    assert registry.get("nope") is None
    assert [c.name for c in registry.list()] == ["stub"]
    # 注入反向引用 (命令可访问 registry)
    assert cmd.registry is registry
    # 多命令按 name 排序 (list 稳定性)
    other = _StubCommand()
    other.name = "aaa"
    registry.register(other)
    assert [c.name for c in registry.list()] == ["aaa", "stub"]


def test_registry_duplicate_register_overrides():
    registry = SLASH_MOD.SlashCommandRegistry()
    first, second = _StubCommand(), _StubCommand()
    registry.register(first)
    registry.register(second)
    assert registry.get("stub") is second


def test_execute_parses_name_and_args():
    registry = SLASH_MOD.SlashCommandRegistry()
    cmd = _StubCommand()
    registry.register(cmd)
    ctx = _context()
    assert registry.execute("/stub hello world", ctx) == 0
    assert cmd.calls == [("hello world", ctx)]  # 同一 context 对象传入
    assert registry.execute("/stub", ctx) == 0
    assert cmd.calls[-1][0] == ""  # 无参 → 空串


def test_execute_unknown_slash_hint(capsys):
    registry = SLASH_MOD.SlashCommandRegistry()
    rc = registry.execute("/bogus", _context())
    out = capsys.readouterr().out
    assert rc == 1
    assert "未知命令" in out
    assert "/bogus" in out
    assert "/help" in out  # 明确指引可用命令 (不静默)


def test_execute_bare_slash_unknown(capsys):
    registry = SLASH_MOD.SlashCommandRegistry()
    rc = registry.execute("/", _context())
    out = capsys.readouterr().out
    assert rc == 1
    assert "未知命令" in out and "/help" in out


def test_execute_non_slash_line_rejected(capsys):
    registry = SLASH_MOD.SlashCommandRegistry()
    rc = registry.execute("hello", _context())
    out = capsys.readouterr().out
    assert rc == 1
    assert "以 / 开头" in out


# ------------------------------------------------------------------ /help


def test_help_lists_commands(capsys):
    registry = CMDS_MOD.build_default_registry()
    rc = registry.execute("/help", _context())
    out = capsys.readouterr().out
    assert rc == 0
    assert "系统命令:" in out
    for name in ("help", "status", "project", "cost", "exit"):
        assert f"/{name}" in out  # name 展示
    assert "退出会话" in out  # description 展示


# ------------------------------------------------------------------ /status


def test_status_shows_context(capsys):
    ctx = _context(workspace="/tmp/ws", current_project="demo", current_agent="backend-1")
    rc = CMDS_MOD.build_default_registry().execute("/status", ctx)
    out = capsys.readouterr().out
    assert rc == 0
    assert "=== 会话状态 ===" in out
    assert ctx.session_id in out  # session
    assert "/tmp/ws" in out  # workspace
    assert "demo" in out  # current project
    assert "backend-1" in out  # current agent


def test_status_unset_fields_placeholder(capsys):
    ctx = _context()
    rc = CMDS_MOD.build_default_registry().execute("/status", ctx)
    out = capsys.readouterr().out
    assert rc == 0
    assert "(未设置)" in out and "(未选择)" in out


# ------------------------------------------------------------------ /project


def test_project_list_shows_projects(tmp_path, capsys):
    projects_file = tmp_path / "org" / "projects.json"
    _write_projects(projects_file, {"demo": {"name": "Demo 项目"}, "alpha": {"name": "Alpha"}})
    ctx = _context(workspace=str(tmp_path), current_project="demo")
    registry = CMDS_MOD.build_default_registry(projects_file=projects_file)
    rc = registry.execute("/project", ctx)
    out = capsys.readouterr().out
    assert rc == 0
    assert "项目清单 (2 个)" in out
    assert "demo" in out and "Demo 项目" in out
    assert "alpha" in out and "Alpha" in out
    assert "当前项目: demo" in out  # current 显示


def test_project_switch_current_project(tmp_path, capsys):
    projects_file = tmp_path / "org" / "projects.json"
    _write_projects(projects_file, {"demo": {"name": "Demo"}, "alpha": {"name": "Alpha"}})
    ctx = _context()
    assert ctx.current_project is None
    registry = CMDS_MOD.build_default_registry(projects_file=projects_file)
    assert registry.execute("/project alpha", ctx) == 0
    out = capsys.readouterr().out
    assert "已切换当前项目: alpha" in out
    assert ctx.current_project == "alpha"  # 切换生效 (ContextManager 同一对象)


def test_project_unknown_id_error(tmp_path, capsys):
    projects_file = tmp_path / "org" / "projects.json"
    _write_projects(projects_file, {"demo": {"name": "Demo"}})
    ctx = _context()
    registry = CMDS_MOD.build_default_registry(projects_file=projects_file)
    assert registry.execute("/project nope", ctx) == 1
    out = capsys.readouterr().out
    assert "未知项目" in out and "nope" in out
    assert ctx.current_project is None  # 未切换


def test_project_missing_file_empty_list(tmp_path, capsys):
    # 失败安全: projects.json 缺失 → 空列表提示, 不抛
    ctx = _context()
    registry = CMDS_MOD.build_default_registry(projects_file=tmp_path / "org" / "projects.json")
    assert registry.execute("/project", ctx) == 0
    out = capsys.readouterr().out
    assert "项目清单 (0 个)" in out
    assert "无项目" in out


def test_project_reuses_factory_cli_data_dir(tmp_path, capsys):
    """验收 H: /project 复用 FactoryCLI.data_dir 数据口径 — 同一 projects.json, 零业务复制。"""
    cli = _make_cli(tmp_path)
    _write_projects(cli.data_dir / "org" / "projects.json", {"demo": {"name": "Demo"}})
    registry = CMDS_MOD.build_default_registry(cli=cli)
    assert registry.execute("/project", _context()) == 0
    out = capsys.readouterr().out
    assert "demo" in out and "Demo" in out
    # 与 FactoryCLI._project_list 展示同一数据文件 (口径一致)
    assert registry.execute("/project demo", _context()) == 0
    capsys.readouterr()


# ------------------------------------------------------------------ /cost


def test_cost_shows_context_summary(capsys):
    cm = CTX_MOD.ContextManager(workspace="/tmp/ws")
    for line in ("/help", "/status", "/project demo"):
        cm.record(line)
    ctx = cm.get()
    rc = CMDS_MOD.build_default_registry().execute("/cost", ctx)
    out = capsys.readouterr().out
    assert rc == 0
    assert "=== 成本/用量 ===" in out
    assert ctx.session_id in out
    assert "会话输入数: 3" in out
    assert "/project demo" in out  # 近期活动摘要
    assert "不复制执行业务" in out  # 占位接口声明


def test_cost_empty_history(capsys):
    rc = CMDS_MOD.build_default_registry().execute("/cost", _context())
    out = capsys.readouterr().out
    assert rc == 0
    assert "会话输入数: 0" in out


# ------------------------------------------------------------------ /exit


def test_exit_sets_running_false(capsys):
    session = SimpleNamespace(running=True)
    rc = CMDS_MOD.build_default_registry(session=session).execute("/exit", _context())
    out = capsys.readouterr().out
    assert rc == 0
    assert session.running is False  # 宿主会话停止
    assert "再见" in out


def test_exit_without_host_is_noop(capsys):
    rc = CMDS_MOD.build_default_registry().execute("/exit", _context())
    assert rc == 0


# ------------------------------------------------------------------ session 集成 (Task 003/004 + 001 不回归)


def test_session_dispatch_slash_status(monkeypatch, capsys):
    _feed_inputs(monkeypatch, ["/status", "exit"])
    rc = SESS_MOD.InteractiveSession().run()
    out = capsys.readouterr().out
    assert rc == 0
    assert "=== 会话状态 ===" in out
    assert "session-" in out  # session_id 显示


def test_session_dispatch_slash_exit(monkeypatch, capsys):
    _feed_inputs(monkeypatch, ["/exit"])
    sess = SESS_MOD.InteractiveSession()
    rc = sess.run()
    out = capsys.readouterr().out
    assert rc == 0
    assert sess.running is False
    assert "再见" in out


def test_session_dispatch_unknown_slash(monkeypatch, capsys):
    _feed_inputs(monkeypatch, ["/bogus", "exit"])
    rc = SESS_MOD.InteractiveSession().run()
    out = capsys.readouterr().out
    assert rc == 0
    assert "未知命令" in out and "/bogus" in out
    assert "/help" in out


def test_session_dispatch_non_slash_unknown(monkeypatch, capsys):
    # S10-075: 非 "/" 输入 → AI 问答 (不再未知命令; 不崩溃)
    _feed_inputs(monkeypatch, ["foobar", "exit"])
    rc = SESS_MOD.InteractiveSession(chat_service=_FakeChat075()).run()
    out = capsys.readouterr().out
    assert rc == 0
    assert "未知命令" not in out


def test_session_records_history(monkeypatch, capsys):
    # 输入写入上下文 history (Task 002 集成 — /cost 数据来源)
    _feed_inputs(monkeypatch, ["/help", "exit"])
    sess = SESS_MOD.InteractiveSession()
    rc = sess.run()
    assert rc == 0
    assert sess.context.history == ["/help"]