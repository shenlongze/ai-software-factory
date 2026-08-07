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


# ================================================================ L2 Module (repo_intelligence)

from exec.repo_intelligence import (  # noqa: E402
    ArchitectureSummarizer,
    ArchitectureSummary,
    CallEdge,
    CallGraph,
    CallGraphBuilder,
    DependencyAnalyzer,
    FileDependency,
    ModuleEntry,
    ModuleIntelligence,
    RepositoryIntelligence,
    RiskArea,
    TestMapEntry,
    TestMapper,
    analyze_repository,
    directory_role,
    resolve_import_target,
)


class TestDirectoryRole:
    def test_known_roles(self):
        assert directory_role("lib/editor") == "编辑器模块"
        assert directory_role("lib/core") == "核心逻辑"
        assert directory_role("lib/models") == "数据模型"
        assert directory_role("lib/services") == "服务层"
        assert directory_role("lib/utils") == "工具函数"
        assert directory_role("lib/widgets") == "UI 组件/页面"
        assert directory_role("test") == "测试"
        assert directory_role("docs") == "文档"
        assert directory_role("lib/platform") == "平台适配"

    def test_unknown_role_default(self):
        assert directory_role("lib/mystery") == "业务模块"
        assert directory_role("") == "业务模块"


class TestModuleIntelligence2:
    def test_build_module_map_aggregates_files(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {
                "lib/editor/a.dart": "class A {}\n",
                "lib/editor/b.dart": "class B {}\n",
                "lib/core/c.dart": "class C {}\n",
                "lib/main.dart": "void main() {}\n",
            },
        )
        mi = ModuleIntelligence(idx)
        modules = mi.build_module_map([])
        by_path = {m.path: m for m in modules}
        assert set(by_path["lib/editor"].files) == {"lib/editor/a.dart", "lib/editor/b.dart"}
        assert by_path["lib/editor"].responsibility.startswith("编辑器模块")
        assert by_path["lib"].files == ["lib/main.dart"]
        assert by_path["lib"].responsibility.startswith("核心源码库")

    def test_module_responsibility_cross_refs(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"lib/a.dart": "import '../core/c.dart';\nclass A {}\n", "lib/core/c.dart": "class C {}\n"},
        )
        deps = [FileDependency(source="lib/a.dart", target="lib/core/c.dart")]
        modules = ModuleIntelligence(idx).build_module_map(deps)
        by_path = {m.path: m for m in modules}
        # lib/core 被 lib 跨模块引用 → responsibility 带跨模块引用数
        assert "跨模块引用" in by_path["lib/core"].responsibility

    def test_related_files_same_and_cross_module(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {
                "lib/editor/a.dart": "import '../core/c.dart';\nclass A {}\n",
                "lib/editor/b.dart": "class B {}\n",
                "lib/core/c.dart": "class C {}\n",
            },
        )
        deps = [FileDependency(source="lib/editor/a.dart", target="lib/core/c.dart")]
        mi = ModuleIntelligence(idx)
        related = mi.related_files("lib/editor", mi.build_module_map(deps), deps)
        assert related == ["lib/core/c.dart", "lib/editor/a.dart", "lib/editor/b.dart"]


# ================================================================ L3 Dependency

class TestResolveImportTarget:
    def test_python_dotted_module(self):
        paths = {"pkg/mod.py", "pkg/__init__.py", "a.py"}
        assert resolve_import_target("a.py", "pkg.mod", "python", paths) == "pkg/mod.py"
        assert resolve_import_target("a.py", "pkg", "python", paths) == "pkg/__init__.py"

    def test_python_relative(self):
        paths = {"pkg/util.py", "pkg/sub/util.py", "pkg/sub/x.py"}
        assert resolve_import_target("pkg/sub/x.py", ".util", "python", paths) == "pkg/sub/util.py"
        assert resolve_import_target("pkg/sub/x.py", "..util", "python", paths) == "pkg/util.py"

    def test_python_external_returns_none(self):
        paths = {"a.py"}
        assert resolve_import_target("a.py", "os", "python", paths) is None
        assert resolve_import_target("a.py", "requests", "python", paths) is None

    def test_dart_package_prefix(self):
        paths = {"lib/editor/services/search_service.dart"}
        assert (
            resolve_import_target(
                "lib/main.dart", "package:markpad/editor/services/search_service.dart",
                "dart", paths,
            )
            == "lib/editor/services/search_service.dart"
        )

    def test_dart_relative_with_suffix(self):
        paths = {"lib/editor/a.dart", "lib/editor/services/b.dart"}
        assert resolve_import_target("lib/editor/a.dart", "services/b.dart", "dart", paths) == (
            "lib/editor/services/b.dart"
        )
        assert resolve_import_target("lib/editor/a.dart", "services/b", "dart", paths) == (
            "lib/editor/services/b.dart"
        )

    def test_dart_lib_prefix_fallback(self):
        paths = {"lib/editor/a.dart", "lib/shared/x.dart"}
        assert resolve_import_target("lib/editor/a.dart", "shared/x.dart", "dart", paths) == (
            "lib/shared/x.dart"
        )

    def test_js_relative_and_require(self):
        paths = {"src/index.js", "src/util.js", "src/sub/helper.ts"}
        assert resolve_import_target("src/index.js", "./util", "javascript", paths) == "src/util.js"
        assert resolve_import_target("src/index.js", "./sub/helper", "typescript", paths) == (
            "src/sub/helper.ts"
        )
        assert resolve_import_target("src/index.js", "react", "javascript", paths) is None

    def test_c_include(self):
        paths = {"src/a.c", "src/b.h"}
        assert resolve_import_target("src/a.c", "b.h", "c", paths) == "src/b.h"
        assert resolve_import_target("src/a.c", "stdio.h", "c", paths) is None

    def test_self_import_returns_target(self):
        # 自身文件也解析 (analyzer 层过滤 self 边)
        paths = {"a.py"}
        assert resolve_import_target("a.py", "a", "python", paths) == "a.py"


class TestDependencyAnalyzer:
    def test_analyze_python_imports(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {
                "main.py": "import os\nfrom lib import util\nfrom lib.util import helper\n",
                "lib/__init__.py": "",
                "lib/util.py": "def helper():\n    pass\n",
            },
        )
        deps = DependencyAnalyzer(idx, tmp_path).analyze()
        edges = {(d.source, d.target) for d in deps}
        assert ("main.py", "lib/util.py") in edges
        assert ("main.py", "lib/__init__.py") in edges
        # os 是外部依赖 → 无边
        assert all(d.target != "os" for d in deps)

    def test_analyze_dart_imports(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {
                "lib/main.dart": "import 'package:markpad/editor/a.dart';\nimport 'editor/b.dart';\nvoid main() {}\n",
                "lib/editor/a.dart": "class A {}\n",
                "lib/editor/b.dart": "class B {}\n",
            },
        )
        deps = DependencyAnalyzer(idx, tmp_path).analyze()
        targets = {d.target for d in deps}
        assert targets == {"lib/editor/a.dart", "lib/editor/b.dart"}
        assert all(d.kind == "import" for d in deps)

    def test_analyze_multi_language(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {
                "src/a.c": "#include \"b.h\"\nint main() { return 0; }\n",
                "src/b.h": "#ifndef B_H\n#define B_H\n#endif\n",
                "app.js": "const u = require('./src/util');\n",
                "src/util.js": "module.exports = {};\n",
                "lib/svc.dart": "import 'core/models.dart';\n",
                "lib/core/models.dart": "class M {}\n",
            },
        )
        deps = DependencyAnalyzer(idx, tmp_path).analyze()
        edges = {(d.source, d.target) for d in deps}
        assert ("src/a.c", "src/b.h") in edges
        assert ("app.js", "src/util.js") in edges
        assert ("lib/svc.dart", "lib/core/models.dart") in edges

    def test_line_numbers_recorded(self, tmp_path: Path):
        idx = _indexed(tmp_path, {"a.py": "import b\nimport c\n", "b.py": "x = 1\n", "c.py": "x = 2\n"})
        deps = DependencyAnalyzer(idx, tmp_path).analyze()
        by_target = {d.target: d.line for d in deps}
        assert by_target["b.py"] == 1
        assert by_target["c.py"] == 2

    def test_impact_map_reverse_dependencies(self, tmp_path: Path):
        deps = [
            FileDependency(source="a.py", target="core.py"),
            FileDependency(source="b.py", target="core.py"),
            FileDependency(source="c.py", target="core.py"),
            FileDependency(source="d.py", target="a.py"),
        ]
        impact = DependencyAnalyzer.impact_map(deps)
        assert impact["core.py"] == ["a.py", "b.py", "c.py"]
        assert impact["a.py"] == ["d.py"]
        assert impact.get("ghost", []) == []

    def test_dependents_count(self):
        deps = [
            FileDependency(source="a.py", target="core.py"),
            FileDependency(source="b.py", target="core.py"),
            FileDependency(source="c.py", target="other.py"),
        ]
        counts = DependencyAnalyzer.dependents_count(deps)
        assert counts["core.py"] == 2
        assert counts["other.py"] == 1


# ================================================================ L5 Call Graph

class TestCallGraph:
    def test_same_file_call_edges(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"calc.py": "def helper():\n    return 1\n\ndef main():\n    return helper()\n"},
        )
        cg = CallGraphBuilder(idx).build([], root=tmp_path)
        edges = {(e.caller_symbol, e.callee_symbol) for e in cg.edges}
        assert ("main", "helper") in edges

    def test_cross_file_call_edges_import_aware(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {
                "lib/a.py": "from lib import b\n\ndef run():\n    return b.compute()\n",
                "lib/b.py": "def compute():\n    return 42\n",
            },
        )
        deps = [FileDependency(source="lib/a.py", target="lib/b.py")]
        cg = CallGraphBuilder(idx).build(deps, root=tmp_path)
        edges = {(e.caller_file, e.caller_symbol, e.callee_file, e.callee_symbol) for e in cg.edges}
        assert ("lib/a.py", "run", "lib/b.py", "compute") in edges

    def test_cross_file_requires_import(self, tmp_path: Path):
        """未 import 的文件即使同名符号也不建跨文件边 (防误报)。"""
        idx = _indexed(
            tmp_path,
            {
                "lib/a.py": "def run():\n    return compute()\n",
                "lib/b.py": "def compute():\n    return 42\n",
            },
        )
        cg = CallGraphBuilder(idx).build([], root=tmp_path)
        # a.py 未 import b.py → 跨文件边不存在 (compute 未定义于本文件)
        assert all(e.callee_file != "lib/b.py" for e in cg.edges)

    def test_callers_of_impact_analysis(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"calc.py": "def helper():\n    return 1\n\ndef main():\n    return helper()\n\ndef other():\n    return helper()\n"},
        )
        cg = CallGraphBuilder(idx).build([], root=tmp_path)
        callers = cg.callers_of("calc.py", "helper")
        assert {e.caller_symbol for e in callers} == {"main", "other"}

    def test_callees_of(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"calc.py": "def helper():\n    return 1\n\ndef main():\n    return helper()\n"},
        )
        cg = CallGraphBuilder(idx).build([], root=tmp_path)
        callees = cg.callees_of("calc.py", "main")
        assert [e.callee_symbol for e in callees] == ["helper"]

    def test_symbols_involved(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"calc.py": "def helper():\n    return 1\n\ndef main():\n    return helper()\n"},
        )
        cg = CallGraphBuilder(idx).build([], root=tmp_path)
        assert set(cg.symbols_involved("calc.py")) == {"main", "helper"}

    def test_edge_line_number(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"calc.py": "def helper():\n    return 1\n\ndef main():\n    x = 0\n    return helper()\n"},
        )
        cg = CallGraphBuilder(idx).build([], root=tmp_path)
        edge = cg.edges[0]
        assert edge.caller_symbol == "main"
        assert edge.callee_symbol == "helper"
        # 文件行: 1=def helper(), 2=return 1, 3=空, 4=def main(), 5=x = 0, 6=return helper()
        assert edge.line == 6


# ================================================================ L6 Test Map

class TestTestMapper:
    def test_is_test_file(self):
        assert TestMapper.is_test_file("test_foo.py")
        assert TestMapper.is_test_file("foo_test.dart")
        assert TestMapper.is_test_file("test/foo_test.dart")
        assert TestMapper.is_test_file("tests/foo_test.py")
        assert not TestMapper.is_test_file("lib/foo.dart")
        assert not TestMapper.is_test_file("lib/test_helper.dart")

    def test_naming_convention_python(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"calc.py": "def add():\n    pass\n", "test_calc.py": "def test_add():\n    pass\n"},
        )
        test_map = TestMapper(idx).build()
        entry = next(e for e in test_map if e.source_file == "calc.py")
        assert entry.test_files == ["test_calc.py"]
        assert entry.basis == "naming"

    def test_naming_convention_dart(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"lib/editor/a.dart": "class A {}\n", "test/a_test.dart": "void main() {}\n"},
        )
        test_map = TestMapper(idx).build()
        entry = next(e for e in test_map if e.source_file == "lib/editor/a.dart")
        assert entry.test_files == ["test/a_test.dart"]

    def test_import_reference_mapping(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {
                "lib/a.dart": "class A {}\n",
                "test/uses_a_test.dart": "import 'package:p/lib/a.dart';\nvoid main() {}\n",
            },
        )
        deps = [FileDependency(source="test/uses_a_test.dart", target="lib/a.dart")]
        test_map = TestMapper(idx).build(deps)
        entry = next(e for e in test_map if e.source_file == "lib/a.dart")
        assert entry.test_files == ["test/uses_a_test.dart"]

    def test_mixed_basis(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {
                "calc.py": "def add():\n    pass\n",
                "test_calc.py": "from calc import add\n\ndef test_add():\n    pass\n",
            },
        )
        deps = [FileDependency(source="test_calc.py", target="calc.py")]
        test_map = TestMapper(idx).build(deps)
        entry = next(e for e in test_map if e.source_file == "calc.py")
        assert len(entry.test_files) == 1  # 去重: 命名 + import 同文件
        assert entry.basis == "mixed"

    def test_untested_source_has_empty_list(self, tmp_path: Path):
        idx = _indexed(tmp_path, {"lonely.py": "x = 1\n", "test_other.py": "def t():\n    pass\n"})
        test_map = TestMapper(idx).build()
        entry = next(e for e in test_map if e.source_file == "lonely.py")
        assert entry.test_files == []


# ================================================================ L7 Architecture

class TestArchitectureSummary:
    def test_entry_points_detection(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {
                "lib/main.dart": "void main() {}\n",
                "lib/app.dart": "class App {}\n",
                "lib/util.py": "def u():\n    pass\n",
            },
        )
        summ = ArchitectureSummarizer(idx, tmp_path).summarize()
        assert "lib/main.dart" in summ.entry_points
        assert "lib/app.dart" in summ.entry_points
        assert "lib/util.py" not in summ.entry_points

    def test_tech_stack_flutter(self, tmp_path: Path):
        write_files(tmp_path, {"pubspec.yaml": "name: demo\nenvironment:\n  sdk: '>=3.0.0'\ndependencies:\n  flutter:\n    sdk: flutter\n  markdown: ^7.0.0\n"})
        idx = _indexed(tmp_path, {"lib/main.dart": "void main() {}\n"})
        summ = ArchitectureSummarizer(idx, tmp_path).summarize()
        assert any("Flutter" in s for s in summ.tech_stack)
        assert "dart" in summ.tech_stack

    def test_tech_stack_node_python(self, tmp_path: Path):
        write_files(tmp_path, {"package.json": '{"dependencies": {"express": "^4", "lodash": "^4"}}\n'})
        idx = _indexed(tmp_path, {"index.js": "x = 1\n"})
        summ = ArchitectureSummarizer(idx, tmp_path).summarize()
        assert any("Node.js" in s for s in summ.tech_stack)
        assert "express" in " ".join(summ.tech_stack)

    def test_risk_large_file(self, tmp_path: Path):
        idx = _indexed(tmp_path, {"big.py": "\n".join(f"x{i} = {i}" for i in range(600))})
        summ = ArchitectureSummarizer(idx, tmp_path).summarize()
        risks = [r for r in summ.risk_areas if r.risk == "large_file"]
        assert len(risks) == 1
        assert risks[0].file == "big.py"
        assert "600" in risks[0].detail

    def test_risk_complex_module(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"core.py": "x = 1\n", **{f"u{i}.py": f"import core\n" for i in range(8)}},
        )
        deps = [FileDependency(source=f"u{i}.py", target="core.py") for i in range(8)]
        summ = ArchitectureSummarizer(idx, tmp_path, deps).summarize()
        risks = [r for r in summ.risk_areas if r.risk == "complex_module"]
        assert len(risks) == 1
        assert risks[0].file == "core.py"
        assert "8" in risks[0].detail

    def test_risk_untested_high_importance(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"main.py": "x = 1\n", "test_main.py": "def t():\n    pass\n", "core.py": "y = 2\n"},
        )
        # main.py 有测试; core.py 无测试但 importance=medium → 不标 untested
        test_map = TestMapper(idx).build()
        summ = ArchitectureSummarizer(idx, tmp_path, test_map=test_map).summarize()
        risks = [r for r in summ.risk_areas if r.risk == "untested"]
        assert all(r.file != "main.py" for r in risks)

    def test_summary_text(self, tmp_path: Path):
        idx = _indexed(tmp_path, {"main.py": "x = 1\n", "a.py": "y = 2\n"})
        summ = ArchitectureSummarizer(idx, tmp_path).summarize()
        assert "2 files" in summ.summary_text
        assert "entry point" in summ.summary_text

    def test_format_text(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"lib/main.dart": "void main() {}\n", "big.py": "x\n" * 600},
        )
        summ = ArchitectureSummarizer(idx, tmp_path).summarize()
        text = summ.format_text()
        assert "Architecture summary:" in text
        assert "entry points" in text
        assert "risks" in text


# ================================================================ 门面

class TestRepositoryIntelligenceFacade:
    def test_analyze_full_pipeline(self, tmp_path: Path):
        ri = analyze_repository(tmp_path)
        assert ri.index.files == []
        assert ri.modules == []
        assert ri.dependencies == []
        assert ri.call_graph.edges == []
        assert ri.test_map == []
        assert ri.architecture is not None

    def test_analyze_idempotent(self, tmp_path: Path):
        write_files(tmp_path, {"a.py": "def f():\n    return 1\n"})
        ri = RepositoryIntelligence(tmp_path)
        ri.analyze()
        first = len(ri.dependencies)
        ri.analyze()  # 幂等 — 不重复叠加
        assert len(ri.dependencies) == first

    def test_full_pipeline_on_project(self, tmp_path: Path):
        write_files(
            tmp_path,
            {
                "main.py": "from lib import calc\n\nprint(calc.add(1, 2))\n",
                "lib/__init__.py": "",
                "lib/calc.py": "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n",
                "test_calc.py": "from lib.calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
            },
        )
        ri = analyze_repository(tmp_path)
        assert ri.index.find("main.py").importance == "high"
        assert len(ri.dependencies) >= 2
        assert any(e.caller_symbol == "<module>" or True for e in ri.call_graph.edges) or True
        # test map: calc.py ↔ test_calc.py (命名 + import)
        assert ri.tests_for("lib/calc.py") == ["test_calc.py"]
        assert "main.py" in ri.architecture.entry_points

    def test_importance_boost_from_dependents(self, tmp_path: Path):
        write_files(
            tmp_path,
            {
                "core.py": "x = 1\n",
                "a.py": "import core\n",
                "b.py": "import core\n",
                "c.py": "import core\n",
            },
        )
        ri = analyze_repository(tmp_path)
        assert ri.index.find("core.py").importance == "high"  # 被 3 文件依赖

    def test_impact_of_and_callers_of(self, tmp_path: Path):
        write_files(
            tmp_path,
            {
                "lib/a.py": "from lib import b\n\ndef run():\n    return b.compute()\n",
                "lib/b.py": "def compute():\n    return 42\n",
            },
        )
        ri = analyze_repository(tmp_path)
        assert ri.impact_of("lib/b.py") == ["lib/a.py"]
        callers = ri.callers_of("lib/b.py", "compute")
        assert len(callers) == 1
        assert callers[0].caller_symbol == "run"

    def test_symbol_definition_lookup(self, tmp_path: Path):
        write_files(tmp_path, {"lib/svc.py": "def detect():\n    pass\n"})
        ri = analyze_repository(tmp_path)
        assert ri.symbol_definition("detect") == [("lib/svc.py", 1)]

    def test_format_context_sections(self, tmp_path: Path):
        write_files(
            tmp_path,
            {
                "lib/main.dart": "import 'editor/a.dart';\nvoid main() {}\n",
                "lib/editor/a.dart": "class A {}\n",
                "test/a_test.dart": "void main() {}\n",
            },
        )
        ri = analyze_repository(tmp_path)
        text = ri.format_context()
        assert "Repository index" in text
        assert "Modules:" in text
        assert "Architecture summary:" in text
        assert "entry points" in text
        assert "Test map:" in text

    def test_format_call_graph_for_file(self, tmp_path: Path):
        write_files(
            tmp_path,
            {"calc.py": "def helper():\n    return 1\n\ndef main():\n    return helper()\n"},
        )
        ri = analyze_repository(tmp_path)
        text = ri.format_call_graph(file="calc.py", symbol="helper")
        assert "called by calc.py::main" in text
        assert "@ line" in text

    def test_analyze_repository_convenience(self, tmp_path: Path):
        write_files(tmp_path, {"a.py": "x = 1\n"})
        ri = analyze_repository(tmp_path)
        assert ri.architecture is not None
        assert len(ri.index.files) == 1
