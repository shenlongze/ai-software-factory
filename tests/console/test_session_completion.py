"""tests/console/test_session_completion.py — Completion Framework (S10-047 Task 007)。

设计: docs/sprint10/S10-046-completion-design.md (§2 数据源分层 / §3 实现架构 / §7 边界)
     + docs/sprint10/S10-047-session-design.md §3 (completion.py — Task 007)
覆盖 (验收口径):
- 验收 A: "/" TAB → 列出全部 slash 命令 (/help /project /status /cost /exit)
- 验收 B: "/pr" → 前缀过滤出 /project
- 验收 C: 无匹配 → 空列表 (不报错); 非 slash 位置 → 无候选
- 验收 D: CompletionProvider (ABC) 接口 — 未来 File/Project/Agent/Skill 扩展点
- CompletionRegistry: 注册式聚合 (多源 / 去重 / 排序, 只读无副作用)
- SlashCompletionProvider 数据源 = SlashCommandRegistry (命令表单一来源, 不硬编码)

basename 全仓库唯一 (test_console_* 前缀)。
"""

from __future__ import annotations

import importlib

import pytest

SLASH_MOD = importlib.import_module("factory-console.session.slash")
CMDS_MOD = importlib.import_module("factory-console.session.commands")
COMP_MOD = importlib.import_module("factory-console.session.completion")
CTX_MOD = importlib.import_module("factory-console.session.context")


# ------------------------------------------------------------------ helpers


class _StubCommand(SLASH_MOD.SlashCommand):
    """极简桩命令 (验证数据源 = 注册表, 不硬编码命令名)。"""

    name = "stub"
    description = "stub 命令"

    def execute(self, args: str, context: object) -> int:
        return 0


def _context(**kw):
    """构造带上下文的 SessionContext (workspace/current_project)。"""
    cm = CTX_MOD.ContextManager(workspace=kw.get("workspace"))
    if kw.get("current_project"):
        cm.update(current_project=kw["current_project"])
    return cm.get()


def _default_names() -> list[str]:
    """默认注册表全部命令名 (带斜杠, 字母序 — 验收 A 口径)。"""
    return [f"/{cmd.name}" for cmd in CMDS_MOD.build_default_registry().list()]


# ------------------------------------------------------------------ 验收 A: "/" → 全部命令


def test_slash_bare_prefix_lists_all_commands():
    """验收 A: "/" TAB → 列出全部 slash 命令 (S10-105: +/preview)。"""
    got = COMP_MOD.SlashCompletionProvider().candidates("/", _context())
    assert got == _default_names()
    # S10-105 新增 /preview; S10-106 新增 /board (均按字母序, 默认注册表口径)
    assert got == ["/board", "/cost", "/exit", "/help", "/preview", "/project", "/status"]
    for name in ("/help", "/project", "/status", "/cost", "/exit", "/preview", "/board"):
        assert name in got


# ------------------------------------------------------------------ 验收 B: 前缀过滤


def test_slash_prefix_filters():
    """验收 B: "/pr" → 前缀过滤 (/preview + /project — S10-105 新增 /preview)。"""
    provider = COMP_MOD.SlashCompletionProvider()
    assert provider.candidates("/pr", _context()) == ["/preview", "/project"]
    assert provider.candidates("/st", _context()) == ["/status"]
    # 大写输入归一 (S10-105: /PR → /preview + /project)
    assert provider.candidates("/PR", _context()) == ["/preview", "/project"]


# ------------------------------------------------------------------ 验收 C: 无匹配 → 空列表


def test_slash_no_match_empty_list():
    """验收 C: 无匹配 → 空列表 (不报错)。"""
    provider = COMP_MOD.SlashCompletionProvider()
    assert provider.candidates("/zz", _context()) == []
    assert provider.candidates("/projectx", _context()) == []


def test_non_slash_position_no_candidates():
    """未知位置 (非 / 开头) → 无候选 (设计 §7: 不报错)。"""
    provider = COMP_MOD.SlashCompletionProvider()
    assert provider.candidates("pr", _context()) == []
    assert provider.candidates("", _context()) == []
    assert provider.candidates(None, _context()) == []  # type: ignore[arg-type]


# ------------------------------------------------------------------ 数据源 = SlashCommandRegistry


def test_slash_provider_uses_registry_source():
    """数据源 = 注入的 SlashCommandRegistry (命令表单一来源, 不硬编码)。"""
    registry = SLASH_MOD.SlashCommandRegistry()
    registry.register(_StubCommand())
    provider = COMP_MOD.SlashCompletionProvider(registry=registry)
    assert provider.candidates("/", _context()) == ["/stub"]
    assert provider.candidates("/st", _context()) == ["/stub"]
    assert provider.candidates("/he", _context()) == []  # 默认命令不在该注册表


# ------------------------------------------------------------------ 验收 D: ABC 接口 (未来扩展)


def test_provider_abc_not_instantiable():
    """验收 D: CompletionProvider 是 ABC — candidates 抽象, 不可直接实例化。"""
    with pytest.raises(TypeError):
        COMP_MOD.CompletionProvider()  # type: ignore[abstract]
    assert COMP_MOD.CompletionProvider.__abstractmethods__ == frozenset({"candidates"})


def test_future_provider_subclass_contract():
    """未来扩展 (File/Project/Agent/Skill) 实现同接口后即可注册聚合。"""
    class FileCompletionProvider(COMP_MOD.CompletionProvider):
        source = "workspace"

        def candidates(self, prefix: str, context: object) -> list[str]:
            return [f"file-{prefix}"] if prefix else []

    provider = FileCompletionProvider()
    assert provider.source == "workspace"
    assert provider.candidates("a", _context()) == ["file-a"]
    # 注册进注册表后单入口聚合
    registry = COMP_MOD.CompletionRegistry()
    registry.register(provider)
    assert registry.candidates("a", _context()) == ["file-a"]


# ------------------------------------------------------------------ CompletionRegistry 聚合


def test_registry_aggregates_slash_and_extra():
    """注册表: 聚合多源候选, 去重 + 字母序 (设计 §6 候选排序)。"""
    registry = COMP_MOD.CompletionRegistry()
    slash = COMP_MOD.SlashCompletionProvider()
    registry.register(slash)
    assert registry.candidates("/", _context()) == slash.candidates("/", _context())

    class ExtraProvider(COMP_MOD.CompletionProvider):
        source = "factory-registry"

        def candidates(self, prefix: str, context: object) -> list[str]:
            return ["/project", "/zzz"] if prefix.startswith("/") else []

    registry.register(ExtraProvider())
    got = registry.candidates("/", _context())
    # /project 双源去重; 全量字母序 (S10-105: +/preview; S10-106: +/board)
    assert got == ["/board", "/cost", "/exit", "/help", "/preview", "/project", "/status", "/zzz"]
    assert got.count("/project") == 1


def test_registry_empty_and_providers_snapshot():
    """空注册表 → 空候选; providers() 返回副本 (防外部篡改)。"""
    registry = COMP_MOD.CompletionRegistry()
    assert registry.candidates("/", _context()) == []
    assert registry.providers() == []
    registry.register(COMP_MOD.SlashCompletionProvider())
    snapshot = registry.providers()
    snapshot.clear()
    assert len(registry.providers()) == 1  # 副本, 内部不受影响


def test_candidates_readonly_no_side_effect():
    """补全只读 (设计 §7): candidates 调用不修改 context。"""
    ctx = _context(workspace="/tmp/ws", current_project="demo")
    before = ctx.to_dict()
    COMP_MOD.SlashCompletionProvider().candidates("/", ctx)
    COMP_MOD.CompletionRegistry().candidates("/pr", ctx)
    assert ctx.to_dict() == before
