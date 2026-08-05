"""tests/runtimes/test_cli_catalog.py — CLI: factory runtime catalog list/show。

覆盖: 默认定义表格 / show 详情 / --json / 未找到 rc 7 / 事件 (runtime.catalog.viewed) /
类型过滤 / 用法错误 rc 2 / 目录独立性 (不产生 runtimes.json)。
"""

from __future__ import annotations

import json

import pytest

from cli.main import main
from cli_helpers import event_types, open_events, run_cli


class TestCatalogList:
    def test_list_shows_defaults(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "runtime", "catalog", "list")
        assert rc == 0
        assert "hermes" in out and "echo" in out and "mock" in out
        assert "code-generation, tool-use, reasoning" in out
        assert "3 definitions" in out

    def test_list_json(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "--json", "runtime", "catalog", "list")
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True and data["count"] == 3
        ids = [d["id"] for d in data["definitions"]]
        assert ids == ["echo", "hermes", "mock"]
        assert data["definitions"][1]["capabilities"] == ["code-generation", "tool-use", "reasoning"]

    def test_list_filter_type(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "--json", "runtime", "catalog", "list", "--type", "mock")
        data = json.loads(out)
        assert data["count"] == 2
        assert all(d["type"] == "mock" for d in data["definitions"])

    def test_list_emits_catalog_viewed(self, capsys, cli_root):
        run_cli(capsys, cli_root, "runtime", "catalog", "list")
        store = open_events(cli_root)
        try:
            assert event_types(store) == ["runtime.catalog.viewed"]
        finally:
            store.close()

    def test_list_readonly_no_catalog_file(self, capsys, cli_root):
        """读命令零写 — 不产生 catalog.json (默认定义走代码基线)。"""
        run_cli(capsys, cli_root, "runtime", "catalog", "list")
        assert not (cli_root / "runtimes" / "catalog.json").exists()

    def test_list_does_not_touch_instance_file(self, capsys, cli_root):
        run_cli(capsys, cli_root, "runtime", "catalog", "list")
        assert not (cli_root / "runtimes" / "runtimes.json").exists()


class TestCatalogShow:
    def test_show_default_detail(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "runtime", "catalog", "show", "hermes")
        assert rc == 0
        assert "hermes" in out and "Hermes Agent" in out
        assert "code-generation, tool-use, reasoning" in out

    def test_show_json(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "--json", "runtime", "catalog", "show", "echo")
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True
        assert data["definition"]["id"] == "echo"
        assert data["definition"]["type"] == "mock"

    def test_show_not_found_rc7(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "runtime", "catalog", "show", "nope")
        assert rc == 7
        assert "not found" in err

    def test_show_emits_catalog_viewed(self, capsys, cli_root):
        run_cli(capsys, cli_root, "runtime", "catalog", "show", "hermes")
        store = open_events(cli_root)
        try:
            assert event_types(store) == ["runtime.catalog.viewed"]
        finally:
            store.close()

    def test_show_missing_arg_usage_error(self, cli_root):
        """argparse 缺必选参数 → SystemExit(2) (发生在 main 返回前)。"""
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "runtime", "catalog", "show"])
        assert exc.value.code == 2

    def test_show_unknown_subcommand_rc2(self, cli_root):
        """未知 catalog 子命令 → CliError rc 2 (与 argparse 用法错误同码)。"""
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "runtime", "catalog", "bogus"])
        assert exc.value.code == 2


class TestCatalogListedAfterRegister:
    def test_registered_definition_appears_in_cli_list(self, capsys, cli_root):
        """经 store 注册的自定义定义并入目录列表 (持久化 + 默认基线)。"""
        from runtimes.catalog import RuntimeCatalog
        from runtimes.store import CatalogStore

        catalog = RuntimeCatalog(CatalogStore(cli_root / "runtimes"))
        from catalog_helpers import make_definition

        catalog.register(make_definition("python-rt", capabilities=["python"]))
        rc, out, err = run_cli(capsys, cli_root, "--json", "runtime", "catalog", "list")
        data = json.loads(out)
        assert data["count"] == 4
        assert any(d["id"] == "python-rt" for d in data["definitions"])
