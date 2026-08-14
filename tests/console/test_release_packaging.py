"""tests/console/test_release_packaging.py — S10-031 Task 2 修复: release packaging。

轻量验证 (不构建 wheel、不真跑 pip install — 只读 pyproject.toml / 源码 / dist):
- 验收 A (wheel 含代码包): [tool.setuptools] package-dir 把 factory_console 映射到
  factory-console 目录 + packages 显式列出映射包及其子包 (api/web/web.backend),
  并覆盖全部 factory-core 子包 — 配置级回归护栏 (旧缺陷: packages.find where 把
  factory_console 当"搜索根" → wheel 空壳, 安装后 ModuleNotFoundError)
- 验收 B (安装可运行): console script 指向 factory_console.cli_factory:main (合法
  标识符路径); 映射源 factory-console/cli_factory.py 存在且 main() 可导入;
  统一入口 parser 含 init/doctor/config/start/project/run
- 验收 C (重命名安全): factory-console 全部模块对兄弟模块用相对导入, 无绝对
  import 引用兄弟模块 — package_dir 映射重命名后不留断链 (importlib 字符串导入
  属业务代码既有模式, 不在断言范围)
- 验收 D (前端 dist): package-data 键为映射包名 factory_console, 含
  web/frontend/dist 模式; dist 产物在磁盘

装配: 同 tests/console 既有模式 — sys.path 挂仓库根 (factory-console 包名
含连字符, 唯一导入方式 importlib)。basename 全仓库唯一 (preflight uniq -d 通过)。

只读保证: 只读 pyproject.toml / factory-console 源码 / dist 文件存在性;
不触碰 ~/.factory; 不构建 wheel (构建/安装验证由发布流程执行)。
"""

from __future__ import annotations

import ast
import importlib
import sys
import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 与 factory_console/ 的父目录
    sys.path.insert(0, str(_ROOT))

PYPROJECT = _ROOT / "pyproject.toml"
CONSOLE_DIR = _ROOT / "factory-console"


@pytest.fixture(scope="module")
def pyproject() -> dict:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)


@pytest.fixture(scope="module")
def setuptools_cfg(pyproject) -> dict:
    return pyproject["tool"]["setuptools"]


def _console_sibling_names() -> set[str]:
    """factory-console 顶层兄弟模块/子包名 (映射重命名后即 factory_console.*)。"""
    names = {p.stem for p in CONSOLE_DIR.glob("*.py")}
    names |= {d.name for d in CONSOLE_DIR.iterdir() if (d / "__init__.py").is_file()}
    return names


def _factory_core_top_packages() -> set[str]:
    """factory-core 顶层包名 (wheel 中作为独立顶层包存在, 可被绝对导入)。"""
    core_root = _ROOT / "factory-core"
    return {d.name for d in core_root.iterdir() if (d / "__init__.py").is_file()}


# ------------------------------------------------------------------ 验收 A: wheel 含代码包


class TestPackageDirMapping:
    def test_package_dir_maps_console_to_underscore_package(self, setuptools_cfg):
        """package-dir 必须把 factory_console 映射到 factory-console 目录 (Design Note)。"""
        pkg_dir = setuptools_cfg["package-dir"]
        assert pkg_dir.get("factory_console") == "factory-console", (
            "缺 package-dir 映射 factory_console → factory-console — wheel 将不含 CLI 代码"
        )

    def test_packages_include_mapped_package_and_subpackages(self, setuptools_cfg):
        """packages 显式包含 factory_console 及其子包 (api/web/web.backend)。"""
        packages = setuptools_cfg["packages"]
        for pkg in (
            "factory_console",
            "factory_console.api",
            "factory_console.web",
            "factory_console.web.backend",
        ):
            assert pkg in packages, f"packages 缺 {pkg} — wheel 将不含该代码"

    def test_packages_have_no_hyphenated_names(self, setuptools_cfg):
        """packages 不得含连字符包名 factory-console (非法导入路径, 空壳根因之一)。"""
        packages = setuptools_cfg["packages"]
        assert not any("factory-console" in p for p in packages), (
            f"packages 含连字符包名: {[p for p in packages if 'factory-console' in p]}"
        )

    def test_packages_cover_all_factory_core_subpackages(self, setuptools_cfg):
        """packages ⊇ factory-core 全部子包 + exec/org 映射包 (S10-031)。"""
        packages = set(setuptools_cfg["packages"])
        core_root = _ROOT / "factory-core"
        discovered = {
            ".".join(init.parent.relative_to(core_root).parts)
            for init in core_root.rglob("__init__.py")
            if "__pycache__" not in init.parts
        }
        # S10-031: exec/org 映射包 (package_dir 指向 factory-exec/exec, factory-org/org)
        for src, prefix in ((_ROOT / "factory-exec" / "exec", "exec"),
                            (_ROOT / "factory-org" / "org", "org")):
            for init in src.rglob("__init__.py"):
                if "__pycache__" in init.parts:
                    continue
                rel = init.parent.relative_to(src).parts
                discovered.add(".".join((prefix, *rel)))
        missing = discovered - packages
        assert not missing, f"factory-core/exec/org 子包未列入 packages: {sorted(missing)}"
        only_mapped = {p for p in packages if p.startswith("factory_console")}
        assert packages - discovered - only_mapped == set(), "packages 含未知包名"

    def test_explicit_packages_replaces_stale_find(self, setuptools_cfg):
        """packages 为显式列表 — 空壳根因 (find 把 factory_console 当搜索根) 已移除。"""
        assert isinstance(setuptools_cfg["packages"], list), (
            "packages 必须是显式列表; packages.find 无法打包映射包的子包 (空壳根因)"
        )


# ------------------------------------------------------------------ 验收 B: 安装可运行


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


class TestMappedPackageSource:
    def test_mapped_dir_has_cli_factory_with_main(self):
        """映射源 factory-console/cli_factory.py 存在且暴露 callable main (安装后
        factory_console.cli_factory 即此文件)。"""
        entry = CONSOLE_DIR / "cli_factory.py"
        assert entry.is_file(), "factory-console/cli_factory.py 缺失"
        mod = importlib.import_module("factory-console.cli_factory")
        assert callable(mod.main)

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


# ------------------------------------------------------------------ 验收 C: 重命名安全


class TestRelativeImportsOnly:
    def test_sibling_imports_are_relative(self):
        """factory-console 模块对兄弟模块只用相对导入 — package_dir 映射重命名后
        不留 `import factory-console.x` 断链。例外: 指向 factory-core 顶层包
        (如 events/) 的绝对导入在 wheel 中作为独立顶层包可解析, 不算断链。
        (importlib 字符串导入属业务代码既有模式, 不在断言范围。)"""
        siblings = _console_sibling_names()
        core_top = _factory_core_top_packages()
        bad: list[str] = []
        seen_relative = False
        for py in CONSOLE_DIR.rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.level > 0:  # 相对导入 (from .x / from ..y) — level 编码前导点
                        seen_relative = True
                        continue
                    top = (node.module or "").split(".")[0]
                    if top in siblings and top not in core_top:
                        bad.append(f"{py.relative_to(CONSOLE_DIR)}: from {node.module} import")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        if top in siblings and top not in core_top:
                            bad.append(f"{py.relative_to(CONSOLE_DIR)}: import {alias.name}")
        assert seen_relative, "未发现相对导入 — 断言落空"
        assert not bad, f"存在绝对兄弟导入 (映射重命名后断链): {bad}"


# ------------------------------------------------------------------ 验收 D: 前端 dist 打包


class TestFrontendDistPackaging:
    def test_package_data_keyed_by_mapped_package(self, setuptools_cfg):
        """package-data 键为映射包名 factory_console (模式相对映射目录)。"""
        package_data = setuptools_cfg["package-data"]
        assert "factory_console" in package_data
        patterns = package_data["factory_console"]
        assert any("web/frontend/dist" in p for p in patterns), (
            f"package-data 缺 web/frontend/dist, 实际: {patterns!r}"
        )
        assert "factory-console" not in package_data, "package-data 仍用连字符旧键"

    def test_dist_artifact_exists_on_disk(self):
        """dist 构建产物存在 (index.html + assets/*), 打包时才能读磁盘。"""
        dist = CONSOLE_DIR / "web" / "frontend" / "dist"
        assert (dist / "index.html").is_file(), "dist/index.html 缺失"
        assets = dist / "assets"
        assert assets.is_dir() and any(assets.iterdir()), "dist/assets/ 为空"
