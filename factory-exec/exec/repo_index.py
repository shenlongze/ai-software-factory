"""factory-exec/exec/repo_index.py — Repository Index MVP (文件树/语言/symbol)。

设计依据 (docs/architecture/developer-agent-reliability-model.md §3):
```
Repository Index (文件清单 + 大小 + 语言) — MVP 本次实现:
  indexer: 文件树 + 语言识别 + 大小排序 (轻量)
  symbol_scan: 函数/类定义位置 (正则级, 多语言)
用途:
  Context 组装只选相关文件 (非全库)
  锚点定位用 symbol 位置 (非行号猜测) — OperationEngine 锚点解析同源
```

不实现 (后续阶段): 完整依赖图 / 调用链 / 继承关系。

实现 (KISS, 确定性, 零 LLM):
- RepositoryIndexer.index(root): 递归文件树 (忽略隐藏目录/构建产物) →
  FileEntry (path/size/language/line_count/symbols)。
- 语言识别: 扩展名映射 (LANGUAGE_BY_EXT); 未知扩展 → "text"。
- symbol 扫描: 正则级多语言 (def/class/interface/enum/struct/类型化方法),
  与 operations.OperationEngine 的锚点启发式同源 (共享 _looks_like_def
  语义 — 此处为独立实现避免循环依赖, 行为一致)。
- format_context(): 文本上下文 (文件树 + 每文件符号索引) — 供 prompt
  组装 (Repository Explore 步骤产物)。
- index_sandbox(sandbox_root, project_files): 便捷入口 — 选择性复制后的
  沙箱副本 → RepositoryIndex (AgentRuntime/Runner 上下文组装用)。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

#: 语言识别映射 (扩展名 → 语言名; 未知 → "text")
LANGUAGE_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".dart": "dart",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".kt": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "shell",
    ".bash": "shell",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".xml": "xml",
    ".sql": "sql",
    ".txt": "text",
    ".gradle": "groovy",
    ".lock": "text",
}

#: 符号定义行正则 (行首; 多语言启发式 — 与 operations._DEF_START 同语义)
_SYMBOL_DEF = re.compile(
    r"^(?:"
    r"(?:public|private|protected|static|final|abstract|async|sync|export|"
    r"default|const|var|let|function|override)\s+)*"
    r"(?:"
    r"def\s+(\w+)\s*\(|"                          # python def foo(
    r"class\s+(\w+)|"                              # class Foo
    r"interface\s+(\w+)|"                          # interface Foo
    r"enum\s+(\w+)|"                               # enum Foo
    r"struct\s+(\w+)|"                             # struct Foo
    r"trait\s+(\w+)|"                              # trait Foo
    r"function\s+(\w+)\s*\(|"                      # js function foo(
    r"[A-Za-z_]\w*[<>,?\[\] .]*\s+(\w+)\s*\(|"     # 类型化方法: void foo( / String bar(
    r"(\w+)\s*\("                                  # 裸函数名: foo(
    r")"
)

#: 缩进忽略的目录/文件 (副本拷贝忽略项同源; indexer 同样跳过构建产物)
_IGNORE_DIR_NAMES = {
    ".git", ".svn", ".hg", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", "node_modules", ".dart_tool",
    "build", "dist", ".gradle", ".idea", "coverage", "Pods", "DerivedData",
    ".hermes", ".factory",
}
_IGNORE_FILE_SUFFIXES = (".pyc", ".pyo", ".DS_Store")


class SymbolKind(str, Enum):
    """符号类型 (正则级判定: function / class / method)。"""

    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"


class SymbolEntry(BaseModel):
    """符号条目: 名称 + 类型 + 定义行 + 块结束行 (启发式)。"""

    name: str
    kind: SymbolKind
    line: int      # 定义行 (1-based)
    end_line: int  # 块结束行 (1-based, 启发式 — 供 replace_block 锚点)

    @field_validator("name", mode="before")
    @classmethod
    def _name_none(cls, v: Any) -> Any:
        return v if v is not None else ""


class FileEntry(BaseModel):
    """文件条目: 路径/大小/语言/行数/符号列表。"""

    path: str
    size: int = 0
    language: str = "text"
    line_count: int = 0
    symbols: list[SymbolEntry] = Field(default_factory=list)

    @field_validator("language", mode="before")
    @classmethod
    def _lang_none(cls, v: Any) -> Any:
        return v if v is not None else "text"

    @field_validator("symbols", mode="before")
    @classmethod
    def _symbols_none(cls, v: Any) -> Any:
        if v is None:
            return []
        return [s if isinstance(s, SymbolEntry) else SymbolEntry.model_validate(s) for s in v]


class RepositoryIndex(BaseModel):
    """仓库索引 (文件树 + 语言 + symbol 位置; 上下文组装输入)。"""

    root: str = ""
    files: list[FileEntry] = Field(default_factory=list)
    generated_at: str = ""

    @field_validator("files", mode="before")
    @classmethod
    def _files_none(cls, v: Any) -> Any:
        if v is None:
            return []
        return [f if isinstance(f, FileEntry) else FileEntry.model_validate(f) for f in v]

    # ------------------------------------------------------------ 查询

    def find(self, path: str) -> FileEntry | None:
        """按相对路径取文件条目 (未索引 → None)。"""
        for f in self.files:
            if f.path == path:
                return f
        return None

    def symbol(self, path: str, name: str) -> SymbolEntry | None:
        """文件内按符号名取条目 (供 OperationEngine 锚点定位参考)。"""
        entry = self.find(path)
        if entry is None:
            return None
        for s in entry.symbols:
            if s.name == name:
                return s
        return None

    def by_language(self, language: str) -> list[FileEntry]:
        """按语言过滤 (上下文按任务类型选文件)。"""
        return [f for f in self.files if f.language == language]

    @property
    def languages(self) -> list[str]:
        """仓库出现的语言集合 (按出现频率降序)。"""
        from collections import Counter

        counter = Counter(f.language for f in self.files)
        return [lang for lang, _ in counter.most_common()]

    # ------------------------------------------------------------ 上下文文本

    def format_context(self, *, max_files: int = 100, include_symbols: bool = True) -> str:
        """文件树 + 符号索引 → 文本 (Repository Explore 步骤产物, prompt 素材)。

        - 文件树: 路径 + 行数 + 语言 + 大小 (按路径排序);
        - 符号索引: 每文件函数/类定义行 (行号可作锚点);
        - max_files 截断 (大仓库上下文预算控制)。
        """
        lines = [f"Repository index ({len(self.files)} files)"]
        for f in self.files[:max_files]:
            size_kb = f.size / 1024.0
            lines.append(
                f"- {f.path} ({f.line_count} lines, {f.language}, {size_kb:.1f}KB)"
            )
            if include_symbols and f.symbols:
                for s in f.symbols:
                    lines.append(
                        f"    {s.kind.value} {s.name} @ line {s.line}"
                    )
        if len(self.files) > max_files:
            lines.append(f"... ({len(self.files) - max_files} more files)")
        if not self.files:
            lines.append("(empty project)")
        return "\n".join(lines)


# ================================================================ Indexer

class RepositoryIndexer:
    """仓库索引器: 递归文件树 → RepositoryIndex (确定性, 零 LLM)。

    构造: root (项目根); 忽略隐藏目录/构建产物 (与 Sandbox 副本忽略项同源)。
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def index(self) -> RepositoryIndex:
        files: list[FileEntry] = []
        if self._root.is_dir():
            for path in sorted(self._root.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(self._root)
                if any(part.startswith(".") for part in rel.parts):
                    continue  # 隐藏目录/文件 (副本过滤项同源)
                if path.name in _IGNORE_DIR_NAMES or path.suffix in _IGNORE_FILE_SUFFIXES:
                    continue
                if any(part in _IGNORE_DIR_NAMES for part in rel.parts):
                    continue
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                line_count = len(content.splitlines())
                files.append(
                    FileEntry(
                        path=str(rel),
                        size=path.stat().st_size,
                        language=self.language_of(path),
                        line_count=line_count,
                        symbols=self.scan_symbols(content),
                    )
                )
        return RepositoryIndex(
            root=str(self._root),
            files=files,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def language_of(path: Path) -> str:
        """扩展名 → 语言名 (未知 → "text")。"""
        return LANGUAGE_BY_EXT.get(path.suffix.lower(), "text")

    @classmethod
    def scan_symbols(cls, content: str) -> list[SymbolEntry]:
        """源码 → 符号列表 (正则级多语言; 行号 1-based)。

        kind 判定: 顶层定义 (无缩进) → function/class; 缩进定义 →
        method (类内方法启发式; 模块级函数缩进为 0 → function)。
        """
        lines = content.splitlines()
        symbols: list[SymbolEntry] = []
        for i, line in enumerate(lines):
            m = _SYMBOL_DEF.match(line.strip())
            if not m:
                continue
            name = next((g for g in m.groups() if g), None)
            if not name:
                continue
            indent = len(line) - len(line.lstrip())
            if m.group(2):  # class/interface/enum/struct/trait
                kind = SymbolKind.CLASS
            elif indent > 0:
                kind = SymbolKind.METHOD
            else:
                kind = SymbolKind.FUNCTION
            symbols.append(
                SymbolEntry(
                    name=name,
                    kind=kind,
                    line=i + 1,
                    end_line=cls.block_end(lines, i) + 1,
                )
            )
        return symbols

    @staticmethod
    def looks_like_def(line: str) -> bool:
        """行是否像新定义 (块结束启发式; 与 operations 同语义)。"""
        s = line.strip()
        if not s:
            return False
        if s.startswith(("#", "//", "/*", "*", "*/")):
            return False
        return bool(_SYMBOL_DEF.match(s))

    @classmethod
    def block_end(cls, lines: list[str], start: int) -> int:
        """块结束行 (0-based inclusive): 下一同缩进定义行前一行/文件尾。"""
        indent = len(lines[start]) - len(lines[start].lstrip())
        for j in range(start + 1, len(lines)):
            line = lines[j]
            if not line.strip():
                continue
            cur_indent = len(line) - len(line.lstrip())
            if cur_indent <= indent and cls.looks_like_def(line):
                return j - 1
        return len(lines) - 1


def index_sandbox(
    sandbox_root: str | Path, project_files: list[str] | None = None
) -> RepositoryIndex:
    """沙箱副本 → RepositoryIndex (上下文组装便捷入口)。

    sandbox_root: 沙箱副本目录 (Sandbox.create 后的 workspace_copy_path)。
    project_files: 可选过滤 — 只索引这些相对路径 (文件/目录前缀); None → 全量。
    """
    index = RepositoryIndexer(sandbox_root).index()
    if not project_files:
        return index
    wanted = [p.rstrip("/") for p in project_files]
    filtered = [
        f
        for f in index.files
        if any(f.path == w or f.path.startswith(w + "/") for w in wanted)
    ]
    return index.model_copy(update={"files": filtered})
