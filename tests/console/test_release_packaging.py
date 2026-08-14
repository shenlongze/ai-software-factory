"""tests/console/test_release_packaging.py — S10-031 Task 2: release packaging。

轻量验证 (不构建 wheel、不真跑 pip install):
- 验收 A: pyproject [project.scripts].factory 指向统一入口的可导入路径
  (factory_console.cli_factory:main — 非 org CLI cli.main)
- 验收 B: 前端 dist 打包配置 (package-data 含 dist) + dist 产物在磁盘存在
- 验收 C: 导入路径可验证 — factory_console.cli_factory 可 import, 且 main()
  与 factory-console.cli_factory.main 是同一函数对象 (统一入口, 非旧 stub)

装配: 同 tests/console 既有模式 — sys.path 挂仓库根 (factory-console 包名
含连字符, 唯一导入方式 importlib; factory_console 别名包亦从仓库根解析)。
basename 全仓库唯一 (preflight uniq -d 通过)。

只读保证: 只读 pyproject.toml / dist 文件存在性; 不触碰 ~/.factory。
"""

from __future__ import annotations

import importlib
import sys
import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 与 factory_console/ 的父目录
    sys.path.insert(0, str(_ROOT))

PYPROJECT = _ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def pyproject() -> dict:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)


# ------------------------------------------------------------------ 验收 A: console script 指向统一入口


class TestConsoleScript:
    def test_factory_script_points_to_unified_entry(self, pyproject):
        """[project.scripts].factory 指向 cli_factory 统一入口, 不再是 org CLI。"""
        scripts = pyproject["project"]["scripts"]
        assert "factory" in scripts, "缺少 factory console script"
        target = scripts["factory"]
        assert target.endswith(":main")
        module_path = target.rsplit(":", 1)[0]
        assert module_path.endswith("cli_factory"), (
            f"factory 应指向 cli_factory 统一入口, 实际: {target!r}"
        )
        assert "cli.main" not in target, "仍指向 org CLI (cli.main) — 需改"

    def test_script_module_is_valid_identifier_path(self, pyproject):
        """模块路径必须是合法标识符 (生成式 console script 用 import 语句)。"""
        target = pyproject["project"]["scripts"]["factory"]
        module_path = target.rsplit(":", 1)[0]
        for part in module_path.split("."):
            assert part.isidentifier(), (
                f"模块路径含非标识符段 {part!r} — pip 生成的 script 将语法错误"
            )


# ------------------------------------------------------------------ 验收 C: 导入路径可验证 (统一入口)


class TestImportableUnifiedEntry:
    def test_factory_console_cli_factory_imports(self):
        """factory_console.cli_factory 可导入且暴露 callable main。"""
        mod = importlib.import_module("factory_console.cli_factory")
        assert callable(mod.main)

    def test_alias_is_same_function_as_real_unified_entry(self):
        """别名 main 与 factory-console.cli_factory.main 是同一函数对象。"""
        alias = importlib.import_module("factory_console.cli_factory").main
        real = importlib.import_module("factory-console.cli_factory").main
        assert alias is real, "别名未指向统一入口同一函数"

    def test_unified_entry_has_unified_commands(self):
        """统一入口的 parser 含 init/doctor/config/start/project/run (17+ 命令)。"""
        cli_factory = importlib.import_module("factory-console.cli_factory")
        parser = cli_factory.build_parser()
        sub_actions = [a for a in parser._actions if getattr(a, "choices", None)]
        assert sub_actions, "parser 无子命令"
        choices = set()
        for action in sub_actions:
            choices |= set(action.choices)
        for cmd in ("init", "doctor", "config", "start", "project", "run"):
            assert cmd in choices, f"统一入口缺子命令 {cmd}"


# ------------------------------------------------------------------ 验收 B: 前端 dist 打包


class TestFrontendDistPackaging:
    def test_package_data_contains_dist(self, pyproject):
        """[tool.setuptools.package-data] 含 factory-console 前端 dist。"""
        package_data = pyproject["tool"]["setuptools"]["package-data"]
        assert "factory-console" in package_data
        patterns = package_data["factory-console"]
        assert any("web/frontend/dist" in p for p in patterns), (
            f"package-data 缺 web/frontend/dist, 实际: {patterns!r}"
        )

    def test_dist_artifact_exists_on_disk(self):
        """dist 构建产物存在 (index.html + assets/*), 打包时才能读磁盘。"""
        dist = _ROOT / "factory-console" / "web" / "frontend" / "dist"
        assert (dist / "index.html").is_file(), "dist/index.html 缺失"
        assets = dist / "assets"
        assert assets.is_dir() and any(assets.iterdir()), "dist/assets/ 为空"

    def test_packages_find_includes_console_layers(self, pyproject):
        """packages.find 覆盖 factory-console (业务包) 与 factory_console (别名)。"""
        where = pyproject["tool"]["setuptools"]["packages"]["find"]["where"]
        assert "factory-console" in where, "wheel 未包含 factory-console 包"
        assert "factory_console" in where, "wheel 未包含 factory_console 别名包"
