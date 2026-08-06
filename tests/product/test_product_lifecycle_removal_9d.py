"""tests/product/test_product_lifecycle_removal_9d.py — Phase 9d Removal Isolation + 唯一 basename (ADR-0029)。

覆盖: lifecycle.py 零顶层 tasks/workflows imports (Core 零修改, 任务集成只经
延迟导入 TaskStore.create), dashboard collector 含生命周期聚合后仍零顶层
product imports (Removal Isolation 源码级断言), cli commands lifecycle 装配
辅助为延迟导入, 删除 product 包后 dashboard --view lifecycle → 响亮 rc 1
(配置缺口不静默), 其余命令零影响, 渲染器/collector 模块可无 product 加载。
"""

from __future__ import annotations

import inspect

import pytest


class TestSourceDecoupling:
    def test_lifecycle_module_no_top_level_core_imports(self):
        """Core 零修改铁律: lifecycle.py 顶层不得 import tasks/workflows。"""
        from product import lifecycle

        src = inspect.getsource(lifecycle)
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import tasks", "from tasks", "import workflows", "from workflows")):
                assert line.startswith((" ", "\t")), f"top-level core import: {line}"

    def test_lifecycle_module_imports_are_delayed(self):
        from product import lifecycle

        src = inspect.getsource(lifecycle)
        # TaskStore 只在函数体内引用 (任务集成经既有 API 调用, 禁修改 Core)
        assert "from tasks.store import TaskStore" in src
        for line in src.splitlines():
            if line.strip().startswith(("from tasks", "import tasks", "from workflows", "import workflows")):
                assert line.startswith((" ", "\t")), f"top-level core import: {line}"

    def test_dashboard_collector_still_no_product_import(self):
        """collector 新增生命周期聚合后仍零顶层 product imports (源码级断言)。"""
        from dashboard import collector

        src = inspect.getsource(collector)
        assert "import product" not in src
        assert "from product" not in src
        assert "def _collect_lifecycle" in src  # 生命周期聚合存在但不跨包引用

    def test_dashboard_views_no_product_import(self):
        from dashboard import views

        src = inspect.getsource(views)
        assert "import product" not in src
        assert "from product" not in src

    def test_renderer_no_product_import(self):
        from dashboard import renderer

        src = inspect.getsource(renderer)
        assert "import product" not in src
        assert "from product" not in src

    def test_commands_lifecycle_helpers_delayed_imports(self):
        from cli import commands

        src = inspect.getsource(commands)
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("import product") or stripped.startswith("from product"):
                assert line.startswith((" ", "\t")), f"top-level product import: {line}"

    def test_lifecycle_test_basenames_unique(self):
        """唯一 basename 陷阱: 本阶段新增测试文件 basename 全仓库唯一 (非包目录
        共存时同名模块互相遮蔽 — test_product_lifecycle_* 前缀约定)。"""
        from pathlib import Path

        repo = Path(__file__).resolve().parents[2]
        new_files = [
            "test_product_lifecycle_registry_9d.py",
            "test_product_lifecycle_engine_9d.py",
            "test_product_lifecycle_decision_chain_9d.py",
            "test_product_lifecycle_cli_9d.py",
            "test_product_lifecycle_dashboard_9d.py",
            "test_product_lifecycle_removal_9d.py",
        ]
        for name in new_files:
            hits = list((repo / "tests").rglob(name))
            assert len(hits) == 1, f"{name} 唯一性被破坏: {hits}"


class TestRemovalViaImportGuard:
    @pytest.fixture
    def block_product(self, monkeypatch):
        """拦截 product.* 导入 (模拟删除 product 包; 先捕获原始 __import__)。"""
        import builtins

        orig_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "product" or name.startswith("product."):
                raise ImportError(f"No module named {name!r} (removal isolation)")
            return orig_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr("builtins.__import__", fake_import)

    def test_commands_module_loads_without_product(self, block_product):
        import cli.commands as commands_mod

        src = inspect.getsource(commands_mod)
        assert commands_mod._open_lifecycle_engine  # 可引用但不触发导入

    def test_dashboard_view_lifecycle_without_package_rc1(self, block_product, capsys, cli_root):
        """product 包被删 → 显式 --view lifecycle → 装配点响亮 rc 1 (同 product
        视图模式: 不静默降级; Removal Isolation 契约 = 模块加载 + 其余零影响)。"""
        from cli.main import main

        rc = main(["--root", str(cli_root), "dashboard", "--view", "lifecycle"])
        out, _ = capsys.readouterr()
        assert rc == 1

    def test_other_commands_unaffected(self, block_product, capsys, cli_root):
        from cli.main import main

        rc = main(["--root", str(cli_root), "task", "list"])
        out, _ = capsys.readouterr()
        assert rc == 0

    def test_dashboard_all_without_product(self, block_product, capsys, cli_root):
        from cli.main import main

        rc = main(["--root", str(cli_root), "dashboard"])
        out, _ = capsys.readouterr()
        assert rc == 0

    def test_lifecycle_command_without_package_rc1(self, block_product, capsys, cli_root):
        from cli.main import main

        rc = main(["--root", str(cli_root), "product", "lifecycle", "templates"])
        out, _ = capsys.readouterr()
        assert rc == 1
