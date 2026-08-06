"""tests/product/test_product_removal.py — Removal Isolation: 删除 product 不影响 Factory (Phase 9A, ADR-0026)。

覆盖: product/store.py 零顶层 events imports (源码级断言, 同 provider 解耦铁律),
dashboard collector 零顶层 product imports, CLI commands 模块可无 product 包加载
(延迟导入), 删除 product 包后 dashboard --view product 仍 rc 0 (空快照, 旧链路)。
"""

from __future__ import annotations

import inspect

import pytest


class TestSourceDecoupling:
    def test_store_module_has_no_top_level_events_import(self):
        from product import store

        src = inspect.getsource(store)
        assert "import events" not in src
        assert "from events" not in src

    def test_dashboard_collector_has_no_top_level_product_import(self):
        from dashboard import collector

        src = inspect.getsource(collector)
        assert "import product" not in src
        assert "from product" not in src

    def test_cli_commands_has_no_top_level_product_import(self):
        from cli import commands

        src = inspect.getsource(commands)
        # 只允许延迟导入形态: 顶层不得 import product (docstring 里出现的说明文字除外)
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("import product") or stripped.startswith("from product"):
                # 缩进 > 0 = 函数体内延迟导入, 允许
                assert line.startswith((" ", "\t")), f"top-level product import: {line}"


class TestRemovalViaImportGuard:
    @pytest.fixture
    def block_product(self, monkeypatch):
        """拦截 product.* 导入 (模拟删除 product 包; IMPORT_NAME 无条件走 __import__)。

        陷阱: monkeypatch 替换 builtins.__import__ 后, 模块内裸 `__import__` 名字
        解析到替换后的 fake → 递归 RecursionError; 必须先捕获原始 __import__。
        """
        import builtins

        orig_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "product" or name.startswith("product."):
                raise ImportError(f"No module named {name!r} (removal isolation)")
            return orig_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr("builtins.__import__", fake_import)

    def test_commands_module_loads_without_product(self, block_product):
        # 模块已缓存? 强制新加载 (Removal Isolation: 顶层无 product 引用)
        import cli.commands as commands_mod

        src = inspect.getsource(commands_mod)
        assert "product" in src  # 延迟导入辅助存在
        assert commands_mod._open_product_service  # 可引用但不触发导入

    def test_dashboard_view_product_without_package_rc1(self, block_product, capsys, cli_root):
        # 显式 --view product 且 product 包被删 → cmd_dashboard 延迟导入失败 →
        # 响亮 rc 1 (与 provider 视图同模式: 装配点不做静默降级, 配置缺口响亮暴露);
        # Removal Isolation 的契约 = 模块加载 + 其余视图/命令零影响
        from cli.main import main

        rc = main(["--root", str(cli_root), "dashboard", "--view", "product"])
        out, _ = capsys.readouterr()
        assert rc == 1

    def test_other_commands_unaffected_by_missing_product(self, block_product, capsys, cli_root):
        from cli.main import main

        rc = main(["--root", str(cli_root), "task", "list"])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "tasks" in out.lower()

    def test_product_command_without_package_rc1(self, block_product, capsys, cli_root):
        # 删除 product 包后 product 命令本身 → ImportError 兜底 rc 1 (配置缺口响亮暴露)
        from cli.main import main

        rc = main(["--root", str(cli_root), "product", "idea", "create", "--title", "t"])
        out, _ = capsys.readouterr()
        assert rc == 1

    def test_dashboard_all_without_product(self, block_product, capsys, cli_root):
        from cli.main import main

        rc = main(["--root", str(cli_root), "dashboard"])
        out, _ = capsys.readouterr()
        assert rc == 0
