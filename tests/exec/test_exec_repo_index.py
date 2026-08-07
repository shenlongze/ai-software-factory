"""tests/exec/test_exec_repo_index.py — Repository Index MVP (文件树/语言/symbol)。

覆盖 (Phase A++++++-1): 文件树索引 / 语言识别 / symbol 扫描 (函数/类/方法 +
1-based 行号 + 块结束启发式) / 过滤 (隐藏目录/构建产物忽略, index_sandbox
project_files) / 查询 (find/symbol/by_language/languages) / format_context
(文件树 + 符号索引 + max_files 截断)。

设计依据: docs/architecture/developer-agent-reliability-model.md §3 —
Repository Index (文件清单 + 大小 + 语言) + symbol_scan (锚点定位用,
与 OperationEngine 同源启发式)。
"""

from __future__ import annotations

from pathlib import Path

from exec.repo_index import (
    RepositoryIndex,
    RepositoryIndexer,
    SymbolKind,
    index_sandbox,
)
from exec_helpers import write_files

PY_SRC = (
    "def top_level():\n"
    "    return 1\n"
    "\n"
    "class MyClass:\n"
    "    def method_a(self):\n"
    "        return 2\n"
)


def _indexed(tmp_path: Path, files: dict[str, str]) -> RepositoryIndex:
    write_files(tmp_path, files)
    return RepositoryIndexer(tmp_path).index()


class TestIndexFileTree:
    def test_index_basic_file_tree(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"main.py": "x = 1\n", "lib/util.py": "def u():\n    return 1\n", "README.md": "# r\n"},
        )
        paths = {f.path for f in idx.files}
        assert paths == {"main.py", "lib/util.py", "README.md"}
        assert idx.root == str(tmp_path)

    def test_line_count_and_size(self, tmp_path: Path):
        idx = _indexed(tmp_path, {"a.py": "x = 1\ny = 2\n"})
        entry = idx.find("a.py")
        assert entry is not None
        assert entry.line_count == 2
        assert entry.size == len("x = 1\ny = 2\n")

    def test_empty_project(self, tmp_path: Path):
        idx = RepositoryIndexer(tmp_path).index()
        assert idx.files == []
        assert "(empty project)" in idx.format_context()

    def test_ignores_hidden_dirs_and_build_artifacts(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {
                ".git/config": "x",
                "__pycache__/mod.cpython-312.pyc": "x",
                "node_modules/pkg/index.js": "x",
                "src/real.py": "x = 1\n",
                "build/out.o": "x",
                "keep.py": "ok\n",
            },
        )
        paths = {f.path for f in idx.files}
        assert paths == {"src/real.py", "keep.py"}


class TestLanguageDetection:
    def test_language_by_extension(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {
                "a.py": "x\n",
                "b.dart": "x\n",
                "c.js": "x\n",
                "d.ts": "x\n",
                "e.md": "# x\n",
                "f.unknown_ext": "x\n",
            },
        )
        langs = {f.path: f.language for f in idx.files}
        assert langs["a.py"] == "python"
        assert langs["b.dart"] == "dart"
        assert langs["c.js"] == "javascript"
        assert langs["d.ts"] == "typescript"
        assert langs["e.md"] == "markdown"
        assert langs["f.unknown_ext"] == "text"

    def test_language_of_unknown_suffix(self):
        assert RepositoryIndexer.language_of(Path("noext")) == "text"
        assert RepositoryIndexer.language_of(Path("x.PY")) == "python"  # 大小写不敏感


class TestSymbolScan:
    def test_scan_symbols_line_numbers_1based(self):
        symbols = RepositoryIndexer.scan_symbols(PY_SRC)
        by_name = {s.name: s for s in symbols}
        assert by_name["top_level"].line == 1
        assert by_name["MyClass"].line == 4
        assert by_name["method_a"].line == 5

    def test_symbol_kinds(self):
        symbols = RepositoryIndexer.scan_symbols(PY_SRC)
        by_name = {s.name: s for s in symbols}
        assert by_name["top_level"].kind is SymbolKind.FUNCTION
        assert by_name["MyClass"].kind is SymbolKind.CLASS
        assert by_name["method_a"].kind is SymbolKind.METHOD  # 缩进定义

    def test_symbol_end_line_heuristic(self):
        symbols = RepositoryIndexer.scan_symbols(PY_SRC)
        by_name = {s.name: s for s in symbols}
        # top_level 块延伸到 class 定义前一行 (空行跳过)
        assert by_name["top_level"].end_line == 3
        assert by_name["MyClass"].end_line == len(PY_SRC.splitlines())

    def test_scan_typed_method_signature(self):
        content = "class Service:\n    void handle(String req) {\n    }\n"
        symbols = RepositoryIndexer.scan_symbols(content)
        names = [s.name for s in symbols]
        assert "Service" in names
        assert "handle" in names

    def test_symbols_included_in_index(self, tmp_path: Path):
        idx = _indexed(tmp_path, {"calc.py": PY_SRC})
        entry = idx.find("calc.py")
        assert entry is not None
        assert [s.name for s in entry.symbols] == ["top_level", "MyClass", "method_a"]


class TestQuery:
    def test_find_missing_returns_none(self, tmp_path: Path):
        idx = _indexed(tmp_path, {"a.py": "x\n"})
        assert idx.find("nope.py") is None

    def test_symbol_lookup(self, tmp_path: Path):
        idx = _indexed(tmp_path, {"calc.py": PY_SRC})
        sym = idx.symbol("calc.py", "MyClass")
        assert sym is not None and sym.kind is SymbolKind.CLASS
        assert idx.symbol("calc.py", "ghost") is None
        assert idx.symbol("missing.py", "x") is None

    def test_by_language_filter(self, tmp_path: Path):
        idx = _indexed(
            tmp_path, {"a.py": "x\n", "b.py": "y\n", "c.md": "# z\n"}
        )
        py = idx.by_language("python")
        assert {f.path for f in py} == {"a.py", "b.py"}

    def test_languages_frequency_order(self, tmp_path: Path):
        idx = _indexed(
            tmp_path,
            {"a.py": "x\n", "b.py": "y\n", "c.py": "z\n", "d.md": "# m\n"},
        )
        assert idx.languages[0] == "python"
        assert set(idx.languages) == {"python", "markdown"}


class TestFormatContext:
    def test_format_context_tree_and_symbols(self, tmp_path: Path):
        idx = _indexed(tmp_path, {"calc.py": PY_SRC})
        text = idx.format_context()
        assert "Repository index (1 files)" in text
        assert "- calc.py (6 lines, python," in text
        assert "function top_level @ line 1" in text
        assert "class MyClass @ line 4" in text

    def test_format_context_max_files_truncation(self, tmp_path: Path):
        files = {f"f{i}.py": "x = 1\n" for i in range(5)}
        idx = _indexed(tmp_path, files)
        text = idx.format_context(max_files=2)
        assert "(3 more files)" in text
        assert "f0.py" in text
        assert "f4.py" not in text

    def test_format_context_without_symbols(self, tmp_path: Path):
        idx = _indexed(tmp_path, {"calc.py": PY_SRC})
        text = idx.format_context(include_symbols=False)
        assert "function top_level" not in text


class TestIndexSandbox:
    def test_project_files_filter(self, tmp_path: Path):
        write_files(
            tmp_path,
            {"lib/a.dart": "class A {}\n", "lib/b.dart": "class B {}\n", "web/c.dart": "x\n"},
        )
        idx = index_sandbox(tmp_path, project_files=["lib/a.dart"])
        assert {f.path for f in idx.files} == {"lib/a.dart"}

    def test_project_files_directory_prefix(self, tmp_path: Path):
        write_files(
            tmp_path,
            {"lib/a.dart": "class A {}\n", "lib/sub/b.dart": "class B {}\n", "web/c.dart": "x\n"},
        )
        idx = index_sandbox(tmp_path, project_files=["lib"])
        assert {f.path for f in idx.files} == {"lib/a.dart", "lib/sub/b.dart"}

    def test_index_sandbox_no_filter_all(self, tmp_path: Path):
        write_files(tmp_path, {"a.py": "x\n", "b.py": "y\n"})
        idx = index_sandbox(tmp_path)
        assert len(idx.files) == 2
