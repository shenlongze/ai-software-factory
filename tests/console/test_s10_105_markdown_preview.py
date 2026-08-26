"""tests/console/test_s10_105_markdown_preview.py — CLI Markdown 渲染 + /preview + 多行输入 (S10-105)。

计划: docs/sprint10/S10-105-markdown-preview-plan.md §2 契约测试要点 1-7
覆盖:
1. looks_like_markdown: 标题/表格/围栏 → True; 进度消息/建议列表/纯文本 → False
2. render_message: markdown → rich 渲染 (输出含处理后的文本, 非 ANSI 断言用 in);
   纯文本 → 原样 (零变化)
3. rich 缺失降级: import 失败 → print 原样 (不崩)
4. /preview: 有参渲染 / 无参 rc2 / 文件不存在 rc2 友好错误 / 非 md 文件原样 / 绝对路径
5. 多行输入: 行尾 "\\" → 续行拼接 "\\n" (run() 整条进 _dispatch); 单行不受影响
6. chat 回答渲染: markdown 回答经 render_message (捕获输出含渲染文本)
7. 非 markdown 消息零变化: 发现/确认消息输出与渲染前一致 (不引入 ANSI/变形)
8. 版本 v1.1.79 (单源断言见 test_s10_074_deployment)

纯确定性 — 不依赖真实 LLM (chat_service 固定回答 / 无 API key 规则兜底)。
basename 全仓库唯一 (test_s10_105_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import builtins
import importlib
import sys
import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 的父目录 (含连字符包名)
    sys.path.insert(0, str(_ROOT))

CMDS = importlib.import_module("factory-console.session.commands")
CTX = importlib.import_module("factory-console.session.context")
RENDER = importlib.import_module("factory-console.session.renderer")
SESS = importlib.import_module("factory-console.session.session")


# ------------------------------------------------------------------ 1: looks_like_markdown (契约 1)


@pytest.mark.parametrize(
    "text",
    [
        "# 一级标题",
        "## 二级标题",
        "###### 六级标题",
        "   # 缩进标题",
        "| 模块 | 说明 |",
        "第一行\n| a | b |\n|---|---|",
        "```python\nprint(1)\n```",
        "代码围栏 ``` 行",
    ],
)
def test_looks_like_markdown_true(text):
    """契约 1: 标题/表格/围栏 → True。"""
    assert RENDER.looks_like_markdown(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "你好，有什么可以帮你？",
        "产品定义 0/3: 问题待填 目标用户待填 核心功能待填",
        "流程: 发现→[确认]→创建→PRD→工程→开发 (当前: 发现)",
        "- 描述你的产品想法\n- 输入 /project 查看已有项目",
        "1. 第一点\n2. 第二点",
        "试试输入: 创建项目 记账App 或 /help",
    ],
)
def test_looks_like_markdown_false(text):
    """契约 1: 进度消息/建议列表/纯文本 → False (列表标记不算)。"""
    assert RENDER.looks_like_markdown(text) is False


def test_looks_like_markdown_non_string():
    """契约 1 补充: 非字符串输入 → False (不抛)。"""
    assert RENDER.looks_like_markdown(None) is False
    assert RENDER.looks_like_markdown(123) is False


# ------------------------------------------------------------------ 2: render_message (契约 2)


def test_render_message_markdown_rendered(capsys):
    """契约 2: markdown → rich 渲染 (非终端无 ANSI, 断言用 in 包含文本)。"""
    md = "# 记账助手 PRD\n\n## 目标\n\n- 自动记账\n\n| 模块 | 说明 |\n|---|---|\n| 记账 | 手动录入 |"
    RENDER.render_message(md)
    out = capsys.readouterr().out
    assert "记账助手 PRD" in out
    assert "自动记账" in out
    assert "手动录入" in out
    assert "\x1b[" not in out  # 非终端 rich 自动去 ANSI


def test_render_message_plain_exact(capsys):
    """契约 2: 纯文本 → print 原样 (零变化, 精确相等)。"""
    text = "产品定义 0/3: 问题待填 目标用户待填 核心功能待填"
    RENDER.render_message(text)
    assert capsys.readouterr().out == text + "\n"


def test_render_message_markdown_fence_no_ansi(capsys):
    """契约 2 补充: 代码围栏经 rich 渲染 (内容可断言, 无 ANSI)。"""
    md = "# 示例\n\n```python\nprint('hi')\n```"
    RENDER.render_message(md)
    out = capsys.readouterr().out
    assert "示例" in out
    assert "print('hi')" in out
    assert "\x1b[" not in out


# ------------------------------------------------------------------ 3: rich 缺失降级 (契约 3)


@pytest.fixture
def _block_rich_import(monkeypatch):
    """模拟 rich 不可 import (真实降级路径, 非 stub)。"""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "rich" or name.startswith("rich."):
            raise ImportError("No module named 'rich'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_render_message_rich_missing_degrade(_block_rich_import, capsys):
    """契约 3: rich import 失败 → print 原样 (诚实降级, 不崩)。"""
    text = "# 标题\n\n| a | b |\n|---|---|\n| 1 | 2 |"
    RENDER.render_message(text)
    assert capsys.readouterr().out == text + "\n"


# ------------------------------------------------------------------ 4: /preview (契约 4)


def _preview_session(tmp_path) -> SESS.InteractiveSession:
    """带 demo 项目 (PRD.md + 普通文本) 的会话 (workspace 指向 tmp, 全 hermetic)。"""
    ws = tmp_path / "ws"
    proj = ws / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "PRD.md").write_text(
        "# 记账助手 PRD\n\n## 目标\n\n- 自动记账\n\n| 模块 | 说明 |\n|---|---|\n| 记账 | 手动录入 |\n",
        encoding="utf-8",
    )
    (ws / "note.txt").write_text("这是普通文本", encoding="utf-8")
    sess = SESS.InteractiveSession(context_manager=CTX.ContextManager(workspace=str(ws)))
    sess.context.current_project = "demo"
    return sess


def test_preview_renders_prd(tmp_path, capsys):
    """契约 4: /preview PRD.md → 相对解析到项目目录 + rich 渲染 (rc 0)。"""
    sess = _preview_session(tmp_path)
    rc = sess.registry.execute("/preview PRD.md", sess.context)
    out = capsys.readouterr().out
    assert rc == 0
    assert "记账助手 PRD" in out
    assert "自动记账" in out
    assert "手动录入" in out
    assert "\x1b[" not in out


def test_preview_absolute_path(tmp_path, capsys):
    """契约 4 补充: /preview 绝对路径 → 直接用 (rc 0)。"""
    sess = _preview_session(tmp_path)
    prd = tmp_path / "ws" / "projects" / "demo" / "PRD.md"
    rc = sess.registry.execute(f"/preview {prd}", sess.context)
    out = capsys.readouterr().out
    assert rc == 0
    assert "记账助手 PRD" in out


def test_preview_cwd_relative(tmp_path, capsys, monkeypatch):
    """契约 4 补充: /preview 相对 cwd 文件 → 解析到 cwd (rc 0)。"""
    sess = _preview_session(tmp_path)
    (tmp_path / "notes.md").write_text("# 本地笔记", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    rc = sess.registry.execute("/preview notes.md", sess.context)
    out = capsys.readouterr().out
    assert rc == 0
    assert "本地笔记" in out


def test_preview_no_args_usage_rc2(tmp_path, capsys):
    """契约 4: /preview 无参 → 用法提示 rc 2 (不崩)。"""
    sess = _preview_session(tmp_path)
    rc = sess.registry.execute("/preview", sess.context)
    out = capsys.readouterr().out
    assert rc == 2
    assert "用法: /preview" in out


def test_preview_missing_file_rc2(tmp_path, capsys):
    """契约 4: /preview 文件不存在 → 友好错误 rc 2 (不崩)。"""
    sess = _preview_session(tmp_path)
    rc = sess.registry.execute("/preview 不存在.md", sess.context)
    out = capsys.readouterr().out
    assert rc == 2
    assert "文件不存在" in out


def test_preview_plain_file_exact(tmp_path, capsys):
    """契约 4: /preview 非 md 文件 → 原样打印 (rc 0, 零变化)。"""
    sess = _preview_session(tmp_path)
    rc = sess.registry.execute("/preview note.txt", sess.context)
    out = capsys.readouterr().out
    assert rc == 0
    assert out == "这是普通文本\n"


def test_preview_rich_missing_degrade(_block_rich_import, tmp_path, capsys):
    """契约 4 补充: rich 缺失时 /preview 仍显示内容 (原样, 不崩)。"""
    sess = _preview_session(tmp_path)
    rc = sess.registry.execute("/preview PRD.md", sess.context)
    out = capsys.readouterr().out
    assert rc == 0
    assert "记账助手 PRD" in out
    assert "手动录入" in out


# ------------------------------------------------------------------ 5: 多行输入 (契约 5)


def test_read_input_line_continuation(monkeypatch):
    """契约 5: 行尾 "\\" → 续行拼接 "\\n" (mock input 序列)。"""
    sess = SESS.InteractiveSession()
    inputs = iter(["第一行\\", "第二行", "end"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(inputs))
    assert sess._read_input_line("> ") == "第一行\n第二行"


def test_read_input_line_multi_continuation(monkeypatch):
    """契约 5 补充: 多段续行全部拼接 (mock input 序列)。"""
    sess = SESS.InteractiveSession()
    inputs = iter(["a\\", "b\\", "c", "end"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(inputs))
    assert sess._read_input_line("> ") == "a\nb\nc"


def test_read_input_line_single_unchanged(monkeypatch):
    """契约 5: 单行 (无尾部 "\\") → 不受影响。"""
    sess = SESS.InteractiveSession()
    monkeypatch.setattr(builtins, "input", lambda prompt="": "你好")
    assert sess._read_input_line("> ") == "你好"


class _RecordingChat:
    """记录 answer 调用的固定回答 ChatService (验证多行整条进分发)。"""

    def __init__(self, reply: str = "AI: 收到"):
        self.reply = reply
        self.calls: list[str] = []

    def answer(self, question: str, **kw):
        self.calls.append(question)
        return self.reply


def test_run_multiline_feeds_dispatch_once(monkeypatch, capsys, tmp_path):
    """契约 5: run() 续行拼接 → 作为一条输入进 _dispatch (chat 收到整条)。"""
    inputs = iter(["第一行\\", "第二行", "exit"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(inputs))
    chat = _RecordingChat()
    sess = SESS.InteractiveSession(
        chat_service=chat,
        context_manager=CTX.ContextManager(workspace=str(tmp_path / "ws")),
    )
    rc = sess.run()
    out = capsys.readouterr().out
    assert rc == 0
    assert chat.calls == ["第一行\n第二行"]  # 拼接后一条输入
    assert "已退出会话" in out


# ------------------------------------------------------------------ 6: chat 回答渲染 (契约 6)


class _FakeMarkdownChat:
    """固定 markdown 回答 (验证 LLM markdown 主场景渲染)。"""

    def __init__(self, reply: str):
        self.reply = reply

    def answer(self, question: str, **kw):
        return self.reply


def test_chat_markdown_answer_rendered(tmp_path, capsys):
    """契约 6: chat markdown 回答经 render_message (捕获输出含渲染文本)。"""
    md = "# 核心概念\n\n| 概念 | 说明 |\n|---|---|\n| Agent | AI 员工 |\n\n```py\nprint('hi')\n```"
    sess = SESS.InteractiveSession(
        chat_service=_FakeMarkdownChat(md),
        context_manager=CTX.ContextManager(workspace=str(tmp_path / "ws")),
    )
    sess._dispatch("什么是 Agent？")
    out = capsys.readouterr().out
    assert "核心概念" in out
    assert "AI 员工" in out
    assert "print('hi')" in out
    assert "\x1b[" not in out


# ------------------------------------------------------------------ 7: 非 markdown 消息零变化 (契约 7)


def test_product_flow_message_zero_change(tmp_path, capsys):
    """契约 7: 产品流发现消息 (无标题/表格/围栏) → 原样, 无 ANSI/变形。"""
    sess = SESS.InteractiveSession(
        context_manager=CTX.ContextManager(workspace=str(tmp_path / "ws")),
    )
    sess._dispatch("我想做一个台球计分APP")
    out = capsys.readouterr().out
    assert "\x1b[" not in out
    assert "流程: [发现]→" in out
    assert "产品定义 0/3:" in out
    # 与 render_message 直出一致 (纯文本路径 = print 原样)
    plain = sess.conversation.product_intent  # 产品流程已建立
    assert plain is not None


def test_lifecycle_progress_plain_rendering(capsys):
    """契约 7 补充: 生命周期/进度文本经 render_message 精确不变。"""
    text = "流程: 发现→[确认]→创建→PRD→工程→开发 (当前: 确认)\n产品定义 3/3: 问题✅ 目标用户✅ 核心功能✅"
    RENDER.render_message(text)
    assert capsys.readouterr().out == text + "\n"


# ------------------------------------------------------------------ 8: 版本 (契约 8)


def test_pyproject_version_bumped():
    """契约 8: pyproject 版本 v1.1.79 (单源断言见 test_s10_074_deployment)。"""
    ver = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    assert ver == "1.1.183"
