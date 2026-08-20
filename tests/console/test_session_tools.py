"""test_session_tools.py — 工具发现与注册 (M1 内核切片 · 增强层)。

覆盖: AI CLI PATH 发现 / MCP 配置发现 (codex toml + claude json + .mcp.json)
/ 去重 / 展示 (空与有)。basename 全仓库唯一。
"""

from __future__ import annotations

from pathlib import Path

from importlib import import_module

TOOLS = import_module("factory-console.session.tools")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestDiscoverAiClis:
    def test_path_scan_finds_known_clis(self, monkeypatch):
        def fake_which(name):
            return f"/usr/local/bin/{name}" if name in ("codex", "hermes") else None

        monkeypatch.setattr(TOOLS.shutil, "which", fake_which)
        monkeypatch.setattr(TOOLS, "_probe_version", lambda b: "v1.0")
        tools = TOOLS.discover_ai_clis()
        assert [t.name for t in tools] == ["codex", "hermes"]
        assert all(t.kind == "ai_cli" for t in tools)
        assert tools[0].version == "v1.0"

    def test_none_installed_empty(self, monkeypatch):
        monkeypatch.setattr(TOOLS.shutil, "which", lambda name: None)
        assert TOOLS.discover_ai_clis() == []

    def test_version_probe_failure_safe(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("no such binary")
        monkeypatch.setattr(TOOLS.subprocess, "run", boom)
        assert TOOLS._probe_version("/nope") == ""


class TestDiscoverMcpServers:
    def test_codex_toml_parsed(self, tmp_path):
        _write(
            tmp_path / ".codex" / "config.toml",
            '[mcp_servers.node_repl]\ncommand = "node"\nargs = ["repl.mjs"]\n'
            '[mcp_servers.computer-use]\ncommand = "x"\nargs = ["mcp"]\n',
        )
        tools = TOOLS.discover_mcp_servers(home=tmp_path)
        names = [t.name for t in tools]
        assert names == ["node_repl", "computer-use"]
        assert tools[0].command == "node"
        assert tools[0].args == ["repl.mjs"]

    def test_claude_json_parsed(self, tmp_path):
        _write(
            tmp_path / ".claude.json",
            '{"mcpServers": {"github": {"command": "npx", "args": ["-y", "gh-mcp"]}}}',
        )
        tools = TOOLS.discover_mcp_servers(home=tmp_path)
        assert len(tools) == 1
        assert tools[0].name == "github"
        assert tools[0].kind == "mcp"

    def test_project_mcp_json(self, tmp_path, monkeypatch):
        _write(tmp_path / ".mcp.json", '{"mcpServers": {"fs": {"command": "npx"}}}')
        monkeypatch.chdir(tmp_path)
        tools = TOOLS.discover_mcp_servers(home=tmp_path / "empty_home")
        assert any(t.name == "fs" for t in tools)

    def test_missing_configs_empty(self, tmp_path):
        assert TOOLS.discover_mcp_servers(home=tmp_path) == []

    def test_dedupe_by_name_command(self, tmp_path):
        _write(tmp_path / ".claude.json", '{"mcpServers": {"s": {"command": "x"}}}')
        _write(tmp_path / ".mcp.json", '{"mcpServers": {"s": {"command": "x"}}}')
        monkeypatch = __import__("pytest").MonkeyPatch()
        monkeypatch.chdir(tmp_path)
        try:
            tools = TOOLS.discover_mcp_servers(home=tmp_path)
            assert sum(1 for t in tools if t.name == "s") == 1
        finally:
            monkeypatch.undo()


class TestFormat:
    def test_empty_message(self):
        text = TOOLS.format_tools([])
        assert "未发现外部工具" in text
        assert "仅增强" in text

    def test_with_tools(self):
        text = TOOLS.format_tools([
            TOOLS.ToolInfo(name="codex", kind="ai_cli", binary="/x", version="v1"),
        ])
        assert "codex" in text
        assert "ai_cli" in text
        assert "增强层" in text
