"""tests/console/test_s10_103_command_routing.py — 发现/确认流程命令分流 (S10-103)。

计划: docs/sprint10/S10-103-command-routing-plan.md §2 契约测试要点 1-9
覆盖:
1. 发现中 "/status" → passthrough=True + problem 不被填 (handle_product_answer 与 handle() 两入口)
2. 发现中 "exit"/"quit" → exit_requested=True + problem 不被填
3. 确认中 slash/exit → 同样分流 (handle_product_confirm)
4. "退出" → 仍取消发现 (向后兼容, 非退出会话)
5. 普通字段答案 → 不受影响 (字段收集正常)
6. 宿主级: InteractiveSession 产品流中 "/status" → registry 执行 (/status 输出);
   "exit" → running=False + 退出提示
7. handle() slash → passthrough (不再死胡同消息)
8. CLI: factory project (无子命令) 提示含 status; factory create project (无 --name) → rc 2
9. 版本 v1.1.79 (单源断言见 test_s10_074_deployment)

命令分流纯确定性 — 全部测试禁用 LLM 分析器 (analyzer=None), 不依赖/不伪造 LLM。

basename 全仓库唯一 (test_s10_103_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 的父目录 (含连字符包名)
    sys.path.insert(0, str(_ROOT))

CF = importlib.import_module("factory-console.cli_factory")
CONV = importlib.import_module("factory-console.session.conversation")
CTX = importlib.import_module("factory-console.session.context")
SESS = importlib.import_module("factory-console.session.session")

STATES = CONV.ConversationState


def _manager(**kw):
    """ConversationManager — 命令分流纯确定性, 显式禁用 LLM 分析器。"""
    kw.setdefault("analyzer", None)
    return CONV.ConversationManager(**kw)


def _start_discovery(mgr) -> None:
    mgr.start_product_discovery("我想开发一个台球计分APP")


def _fill_to_confirmation(mgr) -> None:
    """走完 3 个必填字段 → PRODUCT_CONFIRMATION (确认路径测试前置)。"""
    mgr.start_product_discovery("我想开发一个台球计分APP")
    mgr.handle_product_answer("解决台球比赛计分麻烦")
    mgr.handle_product_answer("台球爱好者")
    mgr.handle_product_answer("计分、比赛记录")
    assert mgr.state == STATES.PRODUCT_CONFIRMATION


def _session(tmp_path):
    """宿主级 InteractiveSession (临时 workspace, 零真实环境依赖)。"""
    return SESS.InteractiveSession(
        context_manager=CTX.ContextManager(workspace=str(tmp_path / "ws")),
    )


# ------------------------------------------------------------------ 1-2: 发现路径命令分流 (契约 1-2)


def test_discovery_slash_passthrough_answer_entry():
    """契约 1: 发现中 /status (handle_product_answer) → passthrough + problem 不被填。"""
    mgr = _manager()
    _start_discovery(mgr)
    resp = mgr.handle_product_answer("/status")
    assert resp.passthrough is True
    assert resp.needs_input is True
    assert resp.exit_requested is False
    assert resp.message == ""
    assert mgr.product_intent.problem is None  # 未被当字段


def test_discovery_slash_passthrough_handle_entry():
    """契约 1: 发现中 /status (handle) → passthrough + problem 不被填。"""
    mgr = _manager()
    _start_discovery(mgr)
    resp = mgr.handle("/status")
    assert resp.passthrough is True
    assert resp.needs_input is True
    assert resp.exit_requested is False
    assert mgr.product_intent.problem is None  # 未被当字段


def test_discovery_exit_exit_requested():
    """契约 2: 发现中 exit → exit_requested + problem 不被填。"""
    mgr = _manager()
    _start_discovery(mgr)
    resp = mgr.handle_product_answer("exit")
    assert resp.exit_requested is True
    assert resp.needs_input is False
    assert resp.passthrough is False
    assert resp.message == ""
    assert mgr.product_intent.problem is None  # 未被当字段


def test_discovery_quit_exit_requested():
    """契约 2: 发现中 quit → exit_requested + problem 不被填。"""
    mgr = _manager()
    _start_discovery(mgr)
    resp = mgr.handle_product_answer("quit")
    assert resp.exit_requested is True
    assert mgr.product_intent.problem is None


def test_discovery_chinese_exit_variants_exit_requested():
    """契约 2: 再见/退出会话/拜拜/结束 → exit_requested (不当字段)。"""
    for word in ("再见", "退出会话", "拜拜", "结束"):
        mgr = _manager()
        _start_discovery(mgr)
        resp = mgr.handle_product_answer(word)
        assert resp.exit_requested is True, word
        assert mgr.product_intent.problem is None, word


# ------------------------------------------------------------------ 3: 确认路径命令分流 (契约 3)


def test_confirm_slash_passthrough():
    """契约 3: 确认中 /status → passthrough (不改名不确认, 状态不变)。"""
    mgr = _manager()
    _fill_to_confirmation(mgr)
    name_before = mgr.product_intent.name
    resp = mgr.handle_product_confirm("/status")
    assert resp.passthrough is True
    assert resp.exit_requested is False
    assert resp.needs_input is True
    assert mgr.state == STATES.PRODUCT_CONFIRMATION
    assert mgr.product_intent.name == name_before  # 名称未被覆盖


def test_confirm_exit_exit_requested():
    """契约 3: 确认中 exit → exit_requested (不当名称/不当确认)。"""
    mgr = _manager()
    _fill_to_confirmation(mgr)
    name_before = mgr.product_intent.name
    resp = mgr.handle_product_confirm("exit")
    assert resp.exit_requested is True
    assert resp.passthrough is False
    assert resp.needs_input is False
    assert mgr.state == STATES.PRODUCT_CONFIRMATION
    assert mgr.product_intent.name == name_before  # 名称未被覆盖


def test_confirm_quit_exit_requested():
    """契约 3: 确认中 quit → exit_requested。"""
    mgr = _manager()
    _fill_to_confirmation(mgr)
    resp = mgr.handle_product_confirm("quit")
    assert resp.exit_requested is True


def test_confirm_chinese_exit_variants_exit_requested():
    """契约 3: 确认中 再见/退出会话/拜拜/结束 → exit_requested。"""
    for word in ("再见", "退出会话", "拜拜", "结束"):
        mgr = _manager()
        _fill_to_confirmation(mgr)
        resp = mgr.handle_product_confirm(word)
        assert resp.exit_requested is True, word


# ------------------------------------------------------------------ 4: "退出" 向后兼容 (契约 4)


def test_exit_chinese_word_still_cancels_discovery():
    """契约 4: 发现中 "退出" → 仍取消发现 (非退出会话, 向后兼容)。"""
    mgr = _manager()
    _start_discovery(mgr)
    resp = mgr.handle_product_answer("退出")
    assert resp.exit_requested is False
    assert resp.passthrough is False
    assert "已取消" in resp.message
    assert mgr.product_intent is None  # 产品流程已重置


def test_exit_chinese_word_still_cancels_confirm():
    """契约 4: 确认中 "退出" → 仍取消发现 (非退出会话, 向后兼容)。"""
    mgr = _manager()
    _fill_to_confirmation(mgr)
    resp = mgr.handle_product_confirm("退出")
    assert resp.exit_requested is False
    assert resp.passthrough is False
    assert "已取消" in resp.message
    assert mgr.product_intent is None


# ------------------------------------------------------------------ 5: 普通字段答案不受影响 (契约 5)


def test_normal_field_answer_unchanged():
    """契约 5: 普通答案仍填充字段 (命令分流不误伤字段收集)。"""
    mgr = _manager()
    _start_discovery(mgr)
    resp = mgr.handle_product_answer("现有工具太繁琐")
    assert resp.passthrough is False
    assert resp.exit_requested is False
    assert mgr.product_intent.problem == "现有工具太繁琐"
    assert mgr.product_intent.user is None  # 只填当前缺失字段


# ------------------------------------------------------------------ 6: 宿主级 (契约 6)


def test_host_slash_in_product_flow_executes_registry(capsys, tmp_path):
    """契约 6: 宿主产品流中 /status → registry 执行 (会话状态输出, 不当字段)。"""
    sess = _session(tmp_path)
    sess._dispatch("我想开发一个台球计分APP")
    sess._dispatch("/status")
    out = capsys.readouterr().out
    assert "会话状态" in out
    assert sess.conversation.product_intent.problem is None


def test_host_exit_in_product_flow_stops_session(capsys, tmp_path):
    """契约 6: 宿主产品流中 exit → 退出提示 + running=False + 不当字段。"""
    sess = _session(tmp_path)
    sess._dispatch("我想开发一个台球计分APP")
    sess._dispatch("exit")
    out = capsys.readouterr().out
    assert "已退出会话 — 再见!" in out
    assert sess.running is False
    assert sess.conversation.product_intent.problem is None


# ------------------------------------------------------------------ 7: handle() slash → passthrough (契约 7)


def test_handle_slash_passthrough_not_dead_end():
    """契约 7: handle() slash → passthrough (不再死胡同消息, 状态不变)。"""
    mgr = _manager()
    resp = mgr.handle("/status")
    assert resp.passthrough is True
    assert resp.needs_input is True
    assert resp.message == ""
    assert resp.state == STATES.DISCOVERY
    assert mgr.pending_intent is None


def test_handle_exit_requested_without_product_flow():
    """契约 7 补充: 无产品流程时 handle("exit") → exit_requested。"""
    mgr = _manager()
    resp = mgr.handle("exit")
    assert resp.exit_requested is True
    assert resp.passthrough is False


# ------------------------------------------------------------------ 8: CLI (契约 8)


def _make_cli(tmp_path):
    """hermetic FactoryCLI: DATA_DIR 指向 tmp, root 默认仓库根 (factory-org 可代理)。"""
    cfg = CF.ConfigProvider(
        environ={"DATA_DIR": str(tmp_path / "data")},
        env_file=tmp_path / "env",
        user_config_file=tmp_path / "cfg.json",
    )
    return CF.FactoryCLI(cfg)


def _create_args(**kw):
    """create_cmd 完整 Namespace (对齐 p_create argparse 实际字段集)。"""
    base = dict(
        command="create", create_type="project", name="", template="solo",
        company="", departments="", goal="", id=None, language="", framework="",
        build_command="", test_command="", project_type="", repo_path=None,
        json=False,
    )
    base.update(kw)
    return argparse.Namespace(**base)


def test_cli_project_hint_includes_status(tmp_path, capsys):
    """契约 8: factory project (无子命令) → 提示含 status, rc 2。"""
    cli = _make_cli(tmp_path)
    args = argparse.Namespace(command="project", project_command=None, json=False)
    rc = cli.project_cmd(args)
    err = capsys.readouterr().err
    assert rc == 2
    assert "status" in err
    assert "create / list / rename / status" in err


def test_cli_create_project_requires_name(tmp_path, capsys):
    """契约 8: factory create project (无 --name) → rc 2 明确错误。"""
    cli = _make_cli(tmp_path)
    args = _create_args(create_type="project", name="")
    rc = cli.create_cmd(args)
    err = capsys.readouterr().err
    assert rc == 2
    assert "create project 需要 --name" in err


def test_cli_create_project_with_name_succeeds(tmp_path):
    """契约 8 补充: create project 带 --name → 正常创建 (rc 0, 项目落盘)。"""
    cli = _make_cli(tmp_path)
    args = _create_args(create_type="project", name="记账助手")
    rc = cli.create_cmd(args)
    assert rc == 0
    pf = cli.data_dir / "org" / "projects.json"
    assert pf.is_file()
    data = __import__("json").loads(pf.read_text(encoding="utf-8"))
    assert any(
        p.get("name") == "记账助手" for p in data.get("projects", {}).values()
    )


# ------------------------------------------------------------------ 9: 版本 (契约 9)


def test_pyproject_version_bumped():
    """契约 9: pyproject 版本 v1.1.79 (单源断言见 test_s10_074_deployment)。"""
    import tomllib

    ver = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    assert ver == "1.1.130"
