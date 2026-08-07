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
(Phase A++++++-2a 增强: 文件重要性评分 + 符号归属模块 — 供 Repository
Intelligence 上下文组装; 完整依赖/调用链见 exec/repo_intelligence.py。)

实现 (KISS, 确定性, 零 LLM):
- RepositoryIndexer.index(root): 递归文件树 (忽略隐藏目录/构建产物) →
  FileEntry (path/size/language/line_count/symbols/importance/module)。
- 语言识别: 扩展名映射 (LANGUAGE_BY_EXT); 未知扩展 → "text"。
- symbol 扫描: 正则级多语言 (def/class/interface/enum/struct/类型化方法),
  与 operations.OperationEngine 的锚点启发式同源 (共享 _looks_like_def
  语义 — 此处为独立实现避免循环依赖, 行为一致)。
- File Structure Intelligence: importance_of() 静态启发式 (入口/核心逻辑 >
  工具/配置 > 文档/资源) + FileEntry.importance + 依赖数增强
  (recompute_importance — 被多文件依赖的核心文件升 high)。
- Symbol Intelligence Enhancement: SymbolEntry.module (所属模块) +
  RepositoryIndex.symbols_by_name (跨文件查「谁定义」— 调用关系定位)。
- format_context(): 文本上下文 (文件树 + 每文件符号索引) — 供 prompt
  组装 (Repository Explore 步骤产物); include_importance 可选列。
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

#: 入口文件基名 (无扩展名匹配 — 静态启发式, 文件重要性 high)
_ENTRY_FILE_NAMES = {
    "main", "app", "run", "index", "server", "cli", "__main__",
    "entry", "bootstrap",
}

#: 文档/资源扩展名 (重要性 low)
_DOC_RESOURCE_SUFFIXES = {
    ".md", ".rst", ".txt", ".html", ".htm", ".css", ".scss",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".lock", ".pdf", ".woff", ".woff2", ".ttf", ".otf", ".mp4",
    ".mp3", ".wav", ".zip", ".tar", ".gz",
}

#: 配置/数据扩展名 (重要性 medium)
_CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml"}

#: 工具/辅助目录名 (重要性 medium)
_TOOL_DIR_NAMES = {"util", "utils", "helper", "helpers", "tools", "tool"}

#: 依赖数增强阈值: 被 ≥ 该数文件依赖 → 核心文件 (importance high)
_DEPENDENT_CORE_THRESHOLD = 3

#: 常见源码根目录 (module_of 取前两段; 其余取首段)
_SOURCE_ROOTS = {"lib", "src", "app", "pkg", "packages", "core"}


#: 代码后缀 (入口文件判定仅对代码/无后缀生效 — app.toml 是配置不是入口)
_CODE_SUFFIXES = {
    ".py", ".dart", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go",
    ".rs", ".c", ".h", ".cpp", ".cc", ".cs", ".swift", ".rb", ".php",
}


def importance_of(rel_path: str, *, line_count: int = 0, dependents: int = 0) -> str:
    """文件重要性启发式 → high|medium|low (确定性, 零 LLM)。

    分层 (设计依据 ai-developer-capability-engine-model.md §1 L1):
      high   — 入口文件 (main/app/run/index/...) + 核心文件 (被 ≥3 文件依赖);
      medium — 源码 (默认) / 测试 / 工具 / 配置;
      low    — 文档 / 资源 (md/txt/图片/字体/锁文件等)。

    dependents: 依赖分析后的被依赖文件数 (0 = 未分析, 静态启发式);
    依赖数增强由 RepositoryIndex.recompute_importance() 统一应用。
    """
    p = Path(rel_path)
    lower_name = p.name.lower()
    stem = p.stem.lower()
    suffix = p.suffix.lower()
    # 文档/资源 (先于入口 — 锁文件/样式不算入口)
    if suffix in _DOC_RESOURCE_SUFFIXES:
        return "low"
    # 入口文件 (仅代码/无后缀 — app.toml 是配置, app.dart 是入口)
    if stem in _ENTRY_FILE_NAMES and (suffix in _CODE_SUFFIXES or suffix == ""):
        return "high"
    # 测试文件
    rel_lower = rel_path.lower()
    if (
        lower_name.startswith("test_")
        or lower_name.endswith("_test")
        or ".test." in lower_name
        or "/test/" in "/" + rel_lower
        or rel_lower.startswith("test/")
        or "/tests/" in "/" + rel_lower
        or rel_lower.startswith("tests/")
    ):
        return "medium"
    # 配置
    if suffix in _CONFIG_SUFFIXES or "config" in rel_lower:
        return "medium"
    # 工具/辅助目录
    if any(part.lower() in _TOOL_DIR_NAMES for part in p.parts):
        return "medium"
    # 核心文件 (依赖数增强 — 被多文件依赖 = 核心模块)
    if dependents >= _DEPENDENT_CORE_THRESHOLD:
        return "high"
    return "medium"


def module_of(rel_path: str) -> str:
    """文件 → 所属模块 (顶层目录段; 源码根下取前两段; 根目录文件 → '(root)')。

    示例 (markpad):
      lib/main.dart               → "lib"
      lib/editor/block_editor.dart → "lib/editor"
      lib/core/document/block.dart → "lib/core"
      test/foo_test.dart           → "test"
      pubspec.yaml                 → "(root)"

    模块边界约定 (Module Intelligence): 模块 = 路径首段目录; 首段是常见
    源码根 (lib/src/app/pkg/packages/core) 且路径 ≥3 段时模块取前两段
    (lib/editor/block_editor.dart → lib/editor; lib/main.dart → lib —
    文件在源码根下仍是根模块, 而非自身成模块)。
    """
    parts = Path(rel_path).parts
    if len(parts) <= 1:
        return "(root)"
    if len(parts) >= 3 and parts[0] in _SOURCE_ROOTS:
        return "/".join(parts[:2])
    return parts[0]


class SymbolKind(str, Enum):
    """符号类型 (正则级判定: function / class / method)。"""

    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"


class SymbolEntry(BaseModel):
    """符号条目: 名称 + 类型 + 定义行 + 块结束行 (启发式) + 所属模块。"""

    name: str
    kind: SymbolKind
    line: int      # 定义行 (1-based)
    end_line: int  # 块结束行 (1-based, 启发式 — 供 replace_block 锚点)
    module: str = ""  # 所属模块 (module_of 文件模块; 调用关系定位用)

    @field_validator("name", mode="before")
    @classmethod
    def _name_none(cls, v: Any) -> Any:
        return v if v is not None else ""

    @field_validator("module", mode="before")
    @classmethod
    def _module_none(cls, v: Any) -> Any:
        return v if v is not None else ""


class FileEntry(BaseModel):
    """文件条目: 路径/大小/语言/行数/符号列表/重要性/所属模块。"""

    path: str
    size: int = 0
    language: str = "text"
    line_count: int = 0
    symbols: list[SymbolEntry] = Field(default_factory=list)
    importance: str = "medium"  # high|medium|low (File Structure Intelligence)
    module: str = ""            # 所属模块 (module_of)

    @field_validator("language", mode="before")
    @classmethod
    def _lang_none(cls, v: Any) -> Any:
        return v if v is not None else "text"

    @field_validator("importance", mode="before")
    @classmethod
    def _importance_none(cls, v: Any) -> Any:
        return v if v is not None else "medium"

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

    def symbols_by_name(self, name: str) -> list[tuple[str, SymbolEntry]]:
        """跨文件按符号名查定义 → [(文件相对路径, SymbolEntry)] (谁定义)。

        Call Graph / 影响面定位: 修改/引用某符号前先查真实定义位置
        (同名符号多文件共存时全部返回 — 调用关系由 Call Graph 裁决)。
        """
        hits: list[tuple[str, SymbolEntry]] = []
        for f in self.files:
            for s in f.symbols:
                if s.name == name:
                    hits.append((f.path, s))
        return hits

    def by_language(self, language: str) -> list[FileEntry]:
        """按语言过滤 (上下文按任务类型选文件)。"""
        return [f for f in self.files if f.language == language]

    @property
    def languages(self) -> list[str]:
        """仓库出现的语言集合 (按出现频率降序)。"""
        from collections import Counter

        counter = Counter(f.language for f in self.files)
        return [lang for lang, _ in counter.most_common()]

    @property
    def importance_counts(self) -> dict[str, int]:
        """重要性分布 {high: N, medium: N, low: N} (Architecture 摘要输入)。"""
        counts = {"high": 0, "medium": 0, "low": 0}
        for f in self.files:
            counts[f.importance] = counts.get(f.importance, 0) + 1
        return counts

    @property
    def module_map(self) -> dict[str, list[str]]:
        """文件 → 所属模块聚合 {模块: [文件相对路径]} (Module Intelligence)。"""
        out: dict[str, list[str]] = {}
        for f in self.files:
            out.setdefault(f.module, []).append(f.path)
        return out

    def files_of_module(self, module: str) -> list[FileEntry]:
        """模块内全部文件 (模块边界; 相关文件聚合输入)。"""
        return [f for f in self.files if f.module == module]

    def recompute_importance(self, dependents: dict[str, int]) -> "RepositoryIndex":
        """依赖数增强: 被 ≥3 文件依赖的核心文件升 high (依赖分析后调用)。

        dependents: {文件相对路径: 被依赖文件数} (Dependency Intelligence
        产出)。只升不降 (入口文件恒 high; 文档/资源保持 low — 即使被
        引用也不代表核心逻辑)。返回 model_copy 新实例 (不原地改)。
        """
        files: list[FileEntry] = []
        for f in self.files:
            new_importance = f.importance
            if f.importance == "medium":
                dep_count = dependents.get(f.path, 0)
                if dep_count >= _DEPENDENT_CORE_THRESHOLD:
                    new_importance = "high"
            files.append(f.model_copy(update={"importance": new_importance}))
        return self.model_copy(update={"files": files})

    # ------------------------------------------------------------ 上下文文本

    def format_context(
        self,
        *,
        max_files: int = 100,
        include_symbols: bool = True,
        include_importance: bool = False,
    ) -> str:
        """文件树 + 符号索引 → 文本 (Repository Explore 步骤产物, prompt 素材)。

        - 文件树: 路径 + 行数 + 语言 + 大小 (按路径排序);
        - 符号索引: 每文件函数/类定义行 (行号可作锚点);
        - include_importance: 附加 [high|medium|low] 重要性列 (File Structure
          Intelligence; 默认关 — 保持 Stage 1 输出逐位不变);
        - max_files 截断 (大仓库上下文预算控制)。
        """
        lines = [f"Repository index ({len(self.files)} files)"]
        for f in self.files[:max_files]:
            size_kb = f.size / 1024.0
            tag = f" [{f.importance}]" if include_importance else ""
            lines.append(
                f"- {f.path} ({f.line_count} lines, {f.language}, {size_kb:.1f}KB){tag}"
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
                rel_str = str(rel)
                files.append(
                    FileEntry(
                        path=rel_str,
                        size=path.stat().st_size,
                        language=self.language_of(path),
                        line_count=line_count,
                        symbols=self.scan_symbols(content, module=module_of(rel_str)),
                        importance=importance_of(rel_str),
                        module=module_of(rel_str),
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
    def scan_symbols(cls, content: str, *, module: str = "") -> list[SymbolEntry]:
        """源码 → 符号列表 (正则级多语言; 行号 1-based)。

        kind 判定: 顶层定义 (无缩进) → function/class; 缩进定义 →
        method (类内方法启发式; 模块级函数缩进为 0 → function)。
        module: 所属模块 (module_of 文件模块; 供「谁定义」调用关系定位)。
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
                    module=module,
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
