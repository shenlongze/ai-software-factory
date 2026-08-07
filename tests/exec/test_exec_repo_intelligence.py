"""tests/exec/test_exec_repo_intelligence.py — Repository Intelligence v1。

覆盖 (Phase A++++++-2a, 设计依据 ai-developer-capability-engine-model.md
§1 Repository Intelligence 7 层):
- L1 File Structure: 文件重要性评分 (入口/核心 > 工具/配置 > 文档/资源) +
  依赖数增强 (recompute_importance) + format_context 重要性列;
- L2 Module: 模块归属 (module_of) + 模块聚合 (module_map/files_of_module);
- L4 Symbol Enhancement: 跨文件「谁定义」查询 (symbols_by_name) + 符号所属模块;
- L3 Dependency: import/require/include 静态解析 (多语言) + FileDependency 图
  + 影响面 (修改 A → 依赖 A 的文件);
- L5 Call Graph MVP: 符号级调用关系 (同文件 + 跨文件, 正则级) + callers_of
  影响面;
- L6 Test Map: 测试文件 ↔ 源文件映射 (命名约定 + import 引用);
- L7 Architecture Summary: 入口/核心模块/技术栈/风险区域 (大文件/复杂模块/
  无测试映射);
- RepositoryIntelligence 门面 + format_context 文本 + 失败样本定位能力
  (symbol 真实行号 / 超长文件风险标注 — Benchmark 失败归因工具)。

实现文件: factory-exec/exec/repo_index.py (增强) + factory-exec/exec/
repo_intelligence.py (新建)。

"""
from __future__ import annotations

from pathlib import Path

from exec.repo_index import (
    FileEntry,
    RepositoryIndex,
    RepositoryIndexer,
    SymbolKind,
    importance_of,
    module_of,
)
from exec_helpers import write_files

PY_SRC = (
    "def top_level():\n"
    "    return helper()\n"
    "\n"
    "def helper():\n"
    "    return 1\n"
    "\n"
    "class MyClass:\n"
    "    def method_a(self):\n"
    "        return top_level()\n"
)


def _indexed(tmp_path: Path, files: dict[str, str]) -> RepositoryIndex:
    write_files(tmp_path, files)
    return RepositoryIndexer(tmp_path).index()


# ================================================================ L1 File Importance

class TestFileImportance:
    def test_importance_of_entry_files_high(self):
        for name in ("main.py", "app.dart", "run.js", "index.ts", "cli.py", "__main__.py"):
            assert importance_of(f"lib/{name}") == "high", name

    def test_importance_of_docs_resources_low(self):
        for name in ("README.md", "docs/guide.txt", "assets/icon.png",
                     "pubspec.lock", "favicon.svg", "style.css"):
            assert importance_of(name) == "low", name

    def test_importance_of_config_medium(self):
        for name in ("pubspec.yaml", "package.json", "config/app.toml",
                     "settings.json", "pom.xml"):
            assert importance_of(name) == "medium", name

    def test_importance_of_tool_dirs_medium(self):
        for name in ("lib/utils/string_util.dart", "src/helpers/format.py",
                     "lib/tools/debug.dart"):
            assert importance_of(name) == "medium", name

    def test_importance_of_test_files_medium(self):
        for name in ("test_foo.py", "foo_test.dart", "tests/foo_test.py",
                     "test/bar_test.dart"):
            assert importance_of(name) == "medium", name

    def test_importance_of_plain_source_medium(self):
        assert importance_of("lib/editor/services/search_service.dart") == "medium"
        assert importance_of("lib/core/document/block.dart") == "medium"

    def test_importance_dependent_boost(self):
        # dependents ≥ 3 → high (核心文件, 依赖数增强)
        assert importance_of("lib/core/document/block.dart", dependents=3) == "high"
        assert importance_of("lib/core/document/block.dart", dependents=2) == "medium"
        # 入口文件恒 high; 文档即使被依赖也保持 low (不误升)
        assert importance_of("main.py", dependents=0) == "high"
        assert importance_of("README.md", dependents=5) == "low"

    def test_file_entry_importance_filled_by_indexer(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {
                "main.py": "x = 1\n",
                "lib/util.py": "def u():\n    return 1\n",
                "README.md": "# r\n",
                "test_main.py": "def test_x():\n    pass\n",
            },
        )
        by_path = {f.path: f for f in idx.files}
        assert by_path["main.py"].importance == "high"
        assert by_path["lib/util.py"].importance == "medium"
        assert by_path["README.md"].importance == "low"
        assert by_path["test_main.py"].importance == "medium"

    def test_importance_counts(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"main.py": "x\n", "a.py": "x\n", "README.md": "x\n"},
        )
        assert idx.importance_counts == {"high": 1, "medium": 1, "low": 1}

    def test_recompute_importance_boosts_dependents(self, tmp_path: Path):
        idx = _indexed(tmp_path, {"core.py": "x = 1\n", "a.py": "x\n", "b.py": "x\n", "c.py": "x\n"})
        # core.py 被 3 个文件依赖 → high; a.py 被 1 个依赖 → 保持 medium
        upgraded = idx.recompute_importance({"core.py": 3, "a.py": 1})
        by_path = {f.path: f for f in upgraded.files}
        assert by_path["core.py"].importance == "high"
        assert by_path["a.py"].importance == "medium"

    def test_recompute_importance_is_copy_not_mutation(self, tmp_path: Path):
        idx = _indexed(tmp_path, {"core.py": "x\n", "a.py": "x\n", "b.py": "x\n", "c.py": "x\n"})
        upgraded = idx.recompute_importance({"core.py": 3})
        assert idx.find("core.py").importance == "medium"  # 原实例不变
        assert upgraded.find("core.py").importance == "high"

    def test_format_context_importance_column_optional(self, tmp_path: Path):
        idx = _indexed(tmp_path, {"main.py": "x = 1\n", "a.py": "x\n"})
        plain = idx.format_context()
        assert " [high]" not in plain  # 默认关 — Stage 1 输出逐位不变
        tagged = idx.format_context(include_importance=True)
        assert "- main.py (1 lines, python," in tagged
        assert " [high]" in tagged
        assert " [medium]" in tagged


# ================================================================ L2 Module

class TestModuleIntelligence:
    def test_module_of_source_root_two_levels(self):
        assert module_of("lib/editor/block_editor.dart") == "lib/editor"
        assert module_of("lib/core/document/block.dart") == "lib/core"
        assert module_of("lib/main.dart") == "lib"
        assert module_of("src/main.py") == "src"

    def test_module_of_plain_dirs_and_root(self):
        assert module_of("test/foo_test.dart") == "test"
        assert module_of("docs/guide.md") == "docs"
        assert module_of("pubspec.yaml") == "(root)"
        assert module_of("Makefile") == "(root)"

    def test_module_map_aggregation(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {
                "lib/editor/a.dart": "class A {}\n",
                "lib/editor/b.dart": "class B {}\n",
                "lib/core/c.dart": "class C {}\n",
                "lib/main.dart": "void main() {}\n",
                "README.md": "# r\n",
            },
        )
        mods = idx.module_map
        assert set(mods["lib/editor"]) == {"lib/editor/a.dart", "lib/editor/b.dart"}
        assert mods["lib/core"] == ["lib/core/c.dart"]
        assert mods["lib"] == ["lib/main.dart"]
        assert mods["(root)"] == ["README.md"]

    def test_files_of_module(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"lib/editor/a.dart": "x\n", "lib/editor/b.dart": "x\n", "lib/core/c.dart": "x\n"},
        )
        editor_files = idx.files_of_module("lib/editor")
        assert [f.path for f in editor_files] == ["lib/editor/a.dart", "lib/editor/b.dart"]
        assert idx.files_of_module("ghost") == []

    def test_symbol_module_field(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"lib/editor/service.dart": "class S {\n  void run() {}\n}\n"},
        )
        sym = idx.symbol("lib/editor/service.dart", "run")
        assert sym is not None
        assert sym.module == "lib/editor"
        assert sym.kind is SymbolKind.METHOD


# ================================================================ L4 Symbol Enhancement

class TestSymbolByName:
    def test_symbols_by_name_cross_file(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"a.py": "def render():\n    pass\n", "b.py": "def render():\n    pass\n", "c.py": "x\n"},
        )
        hits = idx.symbols_by_name("render")
        assert sorted(path for path, _ in hits) == ["a.py", "b.py"]
        assert all(s.kind is SymbolKind.FUNCTION for _, s in hits)

    def test_symbols_by_name_no_hit(self, tmp_path: Path):
        idx = _indexed(tmp_path, {"a.py": "x = 1\n"})
        assert idx.symbols_by_name("ghost") == []

    def test_symbols_by_name_includes_line(self, tmp_path: Path):
        idx = _indexed(tmp_path, {"a.py": "x = 1\n\ndef target():\n    pass\n"})
        hits = idx.symbols_by_name("target")
        assert len(hits) == 1
        _, sym = hits[0]
        assert sym.line == 3
        assert sym.module == "(root)"
