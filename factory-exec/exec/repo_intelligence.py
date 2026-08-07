"""factory-exec/exec/repo_intelligence.py — Repository Intelligence v1 (Phase A++++++-2a)。

设计依据: docs/architecture/ai-developer-capability-engine-model.md §1
(Repository Intelligence 7 层: L1 文件结构 / L2 模块 / L3 依赖 / L4 符号 /
L5 调用关系 / L6 测试映射 / L7 架构上下文)。

本模块实现 (正则级启发式, 确定性, 零 LLM, 零数据库, 零第三方静态分析库):
- ModuleIntelligence (L2): 目录职责 (directory_role) + 模块聚合 (build_module_map);
- DependencyAnalyzer (L3): import/require/include 静态解析 (多语言) →
  FileDependency 图 + 影响面 (修改 A → 依赖 A 的文件);
- CallGraphBuilder (L5): 符号级调用关系 (同文件 + 跨文件, import 感知) →
  CallGraph + callers_of 影响面 (修改前谁调用了被改函数);
- TestMapper (L6): 测试文件 ↔ 源文件 (命名约定 + import 引用) → TestMap;
- ArchitectureSummarizer (L7): 入口识别 / 核心模块 / 技术栈线索 / 风险区域
  (大文件 >500 行 / 复杂模块多依赖 / 无测试映射) → ArchitectureSummary;
- RepositoryIntelligence 门面: 一次分析产出全部 + format_context 文本
  (Context Assembly Engine -2b 的输入: 影响面 / 验证选择 / 相关文件)。

用途 (失败样本定位 — product-proof-report §4.1):
- operation error (symbol 锚点未命中): 完整 symbol 索引 (真实行号) +
  Call Graph 给出被改符号的定义位置与调用方, 供精确锚点;
- 789 行超长文件 empty content: ArchitectureSummary 风险区域标注 + symbol
  索引替代全文内联 (上下文预算控制)。

KISS 边界: 正则级启发式 (不引静态分析库), 调用关系是「符号名 + import
范围」近似, 允许误报/漏报 — 供上下文组装参考, 非编译器级精确图。
"""

from __future__ import annotations

import json
import posixpath
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .repo_index import RepositoryIndex, RepositoryIndexer, SymbolKind, module_of

# ================================================================ 常量

#: 大文件风险阈值 (行数; Architecture 风险区域)
_LARGE_FILE_LINES = 500
#: 复杂模块阈值: 模块内文件数 ≥ 该值 → 复杂模块风险
_COMPLEX_MODULE_FILES = 12
#: 高依赖文件阈值: 被 ≥ 该数文件依赖 → 核心 (importance 增强同源)
_HIGH_DEPENDENTS = 3

#: 目录名 → 职责 (Module Intelligence; 匹配模块路径最后一段)
_ROLE_KEYWORDS: list[tuple[frozenset[str], str]] = [
    (frozenset({"editor"}), "编辑器模块"),
    (frozenset({"core"}), "核心逻辑"),
    (frozenset({"model", "models"}), "数据模型"),
    (frozenset({"service", "services"}), "服务层"),
    (frozenset({"controller", "controllers"}), "控制器"),
    (frozenset({"widget", "widgets", "view", "views", "page", "pages", "ui", "screen", "screens"}), "UI 组件/页面"),
    (frozenset({"util", "utils", "helper", "helpers", "tool", "tools"}), "工具函数"),
    (frozenset({"config", "conf", "settings"}), "配置"),
    (frozenset({"api"}), "API 层"),
    (frozenset({"test", "tests", "spec"}), "测试"),
    (frozenset({"doc", "docs"}), "文档"),
    (frozenset({"platform", "platforms"}), "平台适配"),
    (frozenset({"shared", "common", "commons"}), "共享代码"),
    (frozenset({"export", "exports"}), "导出"),
    (frozenset({"parser", "parsers"}), "解析器"),
    (frozenset({"undo", "history"}), "撤销/历史"),
    (frozenset({"document", "documents"}), "文档模型"),
    (frozenset({"lib", "src", "app", "pkg", "packages", "kernel"}), "核心源码库"),
]

#: 多语言 import/require/include 行正则 (行首; 启发式, 允许多匹配组)
_IMPORT_PATTERNS: dict[str, re.Pattern[str]] = {
    "python": re.compile(
        r"^\s*(?:from\s+([\w.]+)\s+import\s+([\w]+)|import\s+([\w.]+(?:\s*,\s*[\w.]+)*))\b"
    ),
    "dart": re.compile(r"^\s*import\s+['\"]([^'\"]+)['\"]"),
    "javascript": re.compile(
        r"^\s*(?:import\s+(?:[^'\"]*?)\s*from\s*['\"]([^'\"]+)['\"]|"
        r"import\s+['\"]([^'\"]+)['\"]|require\s*\(\s*['\"]([^'\"]+)['\"]\s*\))"
    ),
    "typescript": re.compile(
        r"^\s*(?:import\s+(?:[^'\"]*?)\s*from\s*['\"]([^'\"]+)['\"]|"
        r"import\s+['\"]([^'\"]+)['\"]|require\s*\(\s*['\"]([^'\"]+)['\"]\s*\))"
    ),
    "java": re.compile(r"^\s*import\s+([\w.]+)\s*;"),
    "kotlin": re.compile(r"^\s*import\s+([\w.]+)"),
    "c": re.compile(r"^\s*#\s*include\s*[<\"]([^>\"]+)[\">]"),
    "cpp": re.compile(r"^\s*#\s*include\s*[<\"]([^>\"]+)[\">]"),
    "rust": re.compile(r"^\s*(?:use\s+([\w:]+)|mod\s+(\w+))\b"),
    "go": re.compile(r"^\s*\"([\w./-]+)\""),
    "ruby": re.compile(r"^\s*require(?:_relative)?\s*['\"]([^'\"]+)['\"]"),
    "php": re.compile(r"^\s*(?:use\s+([\w\\]+)|require(?:_once)?\s*\(?\s*['\"]([^'\"]+)['\"]\s*\))"),
    "shell": re.compile(r"^\s*source\s+([^\s]+)"),
}

#: 无扩展名时的候选补全 (resolve_import_target 用; 语言 → 候选后缀)
_SUFFIX_CANDIDATES: dict[str, list[str]] = {
    "python": [".py"],
    "dart": [".dart"],
    "javascript": [".js", ".jsx", "/index.js", "/index.jsx"],
    "typescript": [".ts", ".tsx", ".js", ".jsx", ".d.ts", "/index.ts", "/index.tsx"],
    "c": [".h", ".c"],
    "cpp": [".hpp", ".h", ".cpp", ".cc", ".c"],
    "java": [".java"],
    "kotlin": [".kt"],
}

#: 符号调用形式 (name( — 正则级; 排除定义行自身的 def/class 等)
_CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")

#: js/ts 行内 require 兜底 (const u = require('...') 行首非 require, ^\s* 锚定不命中)
_REQUIRE_INLINE_RE = re.compile(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")


# ================================================================ L2 Module

def directory_role(module_path: str) -> str:
    """模块路径最后一段 → 职责描述 (启发式; 未知 → "业务模块")。"""
    last = Path(module_path).name.lower() if module_path else ""
    for names, role in _ROLE_KEYWORDS:
        if last in names:
            return role
    return "业务模块"


class ModuleEntry(BaseModel):
    """模块条目: 路径 + 文件列表 + 目录职责 (L2 Module Intelligence)。"""

    path: str = "(root)"
    files: list[str] = Field(default_factory=list)
    responsibility: str = ""

    def format_text(self) -> str:
        return f"- {self.path} — {self.responsibility} ({len(self.files)} files)"


class ModuleIntelligence:
    """目录 → 模块 → 职责 (L2)。确定性: 模块 = module_of 文件聚合。"""

    def __init__(self, index: RepositoryIndex) -> None:
        self._index = index

    def build_module_map(self, dependencies: list["FileDependency"]) -> list[ModuleEntry]:
        """文件聚合 → 模块列表 (按模块名排序; 职责启发式 + 跨模块引用文件数)。"""
        by_module: dict[str, list[str]] = {}
        for f in self._index.files:
            by_module.setdefault(f.module, []).append(f.path)
        cross_refs = _module_cross_refs(by_module, dependencies)
        entries: list[ModuleEntry] = []
        for mod in sorted(by_module):
            files = sorted(by_module[mod])
            entries.append(
                ModuleEntry(
                    path=mod,
                    files=files,
                    responsibility=_responsibility_with_refs(
                        directory_role(mod), mod, cross_refs.get(mod, 0)
                    ),
                )
            )
        return entries

    def related_files(
        self, module: str, module_map: list[ModuleEntry], dependencies: list["FileDependency"]
    ) -> list[str]:
        """模块相关文件: 同模块文件 + 跨模块引用文件 (依赖/被依赖)。"""
        same = sorted(self._index.module_map.get(module, []))
        related: list[str] = list(same)
        for d in dependencies:
            if module_of(d.source) == module and d.target not in related:
                related.append(d.target)
            elif module_of(d.target) == module and d.source not in related:
                related.append(d.source)
        return sorted(related)


def _module_cross_refs(
    by_module: dict[str, list[str]], dependencies: list["FileDependency"]
) -> dict[str, int]:
    """模块 → 跨模块依赖文件数 (来自其他模块的依赖边; 模块耦合度)。"""
    counts: dict[str, int] = {}
    for d in dependencies:
        src_mod = module_of(d.source)
        tgt_mod = module_of(d.target)
        if src_mod != tgt_mod:
            counts[tgt_mod] = counts.get(tgt_mod, 0) + 1
            counts[src_mod] = counts.get(src_mod, 0) + 1
    return counts


def _responsibility_with_refs(role: str, mod: str, cross_refs: int) -> str:
    base = role
    if cross_refs:
        base = f"{role} (跨模块引用 {cross_refs})"
    if mod == "(root)":
        return f"{base} (根目录文件)"
    return base


# ================================================================ L3 Dependency

class FileDependency(BaseModel):
    """文件依赖边: source 文件依赖 target 文件 (仓库内; 正则级解析)。"""

    source: str
    target: str
    kind: str = "import"  # import / require / include / use / part / source
    line: int = 0


def resolve_import_target(
    source_rel: str, spec: str, language: str, index_paths: set[str]
) -> str | None:
    """import 说明 → 仓库内相对路径 (解析不到 → None = 外部依赖, 不建边)。

    规则 (正则级启发式):
    - dart `package:xxx/...` → 剥前缀后按仓库内路径解析;
    - python `a.b.c` → a/b/c.py 或 a/b/c/__init__.py; 单段 `a` → a.py 或
      a/__init__.py; 相对导入 `.util` / `..util` → 当前/上级包内;
    - 相对路径 (./ ../) → 相对源文件目录 + 语言后缀候选补全;
    - 裸文件名 (dart/c include) → 相对源文件目录解析, dart 再试 lib/ 前缀;
    - 其余裸包名 (node_modules/外部) → None。
    """
    s = spec.strip()
    if not s or s.startswith(("http:", "https:", "dart:")):
        return None
    if s.startswith("package:"):  # dart
        s = s[len("package:"):]
        if "/" in s:
            s = s.split("/", 1)[1]
    # python 点分/单段模块: a.b.c → a/b/c.py; a → a.py / a/__init__.py
    if language == "python" and not s.startswith((".", "/")):
        rel = s.replace(".", "/")
        for cand in (rel + ".py", rel + "/__init__.py"):
            if cand in index_paths:
                return cand
        return None
    # python 相对导入: .util → 当前包; ..util → 上级包
    if language == "python" and s.startswith(".") and not s.startswith(("./", "../")):
        dots = len(s) - len(s.lstrip("."))
        name = s[dots:]
        base_dir = posixpath.dirname(source_rel)
        for _ in range(dots - 1):
            base_dir = posixpath.dirname(base_dir)
        rel = posixpath.normpath(posixpath.join(base_dir, name))
        for cand in (rel + ".py", rel + "/__init__.py"):
            if cand in index_paths:
                return cand
        return None
    # 相对路径
    if s.startswith(("./", "../")):
        base_dir = posixpath.dirname(source_rel)
        rel = posixpath.normpath(posixpath.join(base_dir, s))
        candidates = [rel]
        candidates += [rel + suf for suf in _SUFFIX_CANDIDATES.get(language, [])]
        for cand in candidates:
            if cand in index_paths:
                return cand
        if language == "python" and (rel + "/__init__.py") in index_paths:
            return rel + "/__init__.py"
        return None
    # 裸文件名: 相对源文件目录解析 (dart / c / cpp)
    if language in ("dart", "c", "cpp"):
        base_dir = posixpath.dirname(source_rel)
        rel = posixpath.normpath(posixpath.join(base_dir, s))
        for cand in (rel, rel + ".dart" if not s.endswith(".dart") else rel):
            if cand in index_paths:
                return cand
        if language == "dart":
            for cand in (s, s if s.startswith("lib/") else "lib/" + s):
                if cand in index_paths:
                    return cand
            if not s.endswith(".dart"):
                for cand in (s + ".dart", "lib/" + s + ".dart"):
                    if cand in index_paths:
                        return cand
        return None
    return None


class DependencyAnalyzer:
    """import/require/include 静态解析 (L3) → FileDependency 列表 (仓库内边)。"""

    def __init__(self, index: RepositoryIndex, root: str | Path) -> None:
        self._index = index
        self._root = Path(root)

    def analyze(self, contents: dict[str, str] | None = None) -> list[FileDependency]:
        """全仓库依赖边 (确定性; 只含仓库内解析命中的边)。"""
        paths = {f.path for f in self._index.files}
        deps: list[FileDependency] = []
        for entry in self._index.files:
            pattern = _IMPORT_PATTERNS.get(entry.language)
            if pattern is None:
                continue
            content = (
                contents.get(entry.path, "")
                if contents is not None
                else _read_text(self._root / entry.path)
            )
            for line_no, line in enumerate(content.splitlines(), start=1):
                m = pattern.search(line)
                if not m and entry.language in ("javascript", "typescript"):
                    m = _REQUIRE_INLINE_RE.search(line)
                if not m:
                    continue
                specs: list[str] = []
                if entry.language == "python" and m.group(1):
                    # from X import Y → X 包 + X.Y 子模块 (双候选, 命中即建边)
                    specs = [m.group(1)]
                    if m.group(2):
                        specs.append(f"{m.group(1)}.{m.group(2)}")
                else:
                    spec = next((g for g in m.groups() if g), None)
                    if spec:
                        specs = [spec]
                for spec in specs:
                    target = resolve_import_target(entry.path, spec, entry.language, paths)
                    if target and target != entry.path:
                        deps.append(
                            FileDependency(
                                source=entry.path,
                                target=target,
                                kind="import",
                                line=line_no,
                            )
                        )
        return deps

    @staticmethod
    def impact_map(dependencies: list[FileDependency]) -> dict[str, list[str]]:
        """影响面: 修改 A → 依赖 A 的文件列表 (反向依赖, 按 source 聚合)。"""
        out: dict[str, list[str]] = {}
        for d in dependencies:
            out.setdefault(d.target, []).append(d.source)
        for k in out:
            out[k] = sorted(set(out[k]))
        return out

    @staticmethod
    def dependents_count(dependencies: list[FileDependency]) -> dict[str, int]:
        """被依赖文件数 {文件: N} (importance 依赖数增强输入)。"""
        counts: dict[str, int] = {}
        for d in dependencies:
            counts[d.target] = counts.get(d.target, 0) + 1
        return counts


# ================================================================ L5 Call Graph

class CallEdge(BaseModel):
    """调用边: caller 调用 callee (符号级; 行号 = 调用点, 正则级近似)。"""

    caller_file: str
    caller_symbol: str
    callee_file: str
    callee_symbol: str
    line: int = 0


class CallGraph(BaseModel):
    """调用图 (L5): 节点 = (文件, 符号); 边 = caller → callee。

    用途 (修改前影响范围): callers_of(file, symbol) → 谁调用了被修改函数。
    """

    edges: list[CallEdge] = Field(default_factory=list)

    def callers_of(self, file: str, symbol: str | None = None) -> list[CallEdge]:
        """谁调用了 (file, symbol) — 修改前影响面分析。"""
        return [
            e
            for e in self.edges
            if e.callee_file == file and (symbol is None or e.callee_symbol == symbol)
        ]

    def callees_of(self, file: str, symbol: str | None = None) -> list[CallEdge]:
        """(file, symbol) 调用了谁 — 上下文组装 (调用链下游)。"""
        return [
            e
            for e in self.edges
            if e.caller_file == file and (symbol is None or e.caller_symbol == symbol)
        ]

    def symbols_involved(self, file: str) -> list[str]:
        """文件内参与调用图的符号 (去重; 上下文选段用)。"""
        names: list[str] = []
        for e in self.edges:
            if e.caller_file == file and e.caller_symbol not in names:
                names.append(e.caller_symbol)
            if e.callee_file == file and e.callee_symbol not in names:
                names.append(e.callee_symbol)
        return names


class CallGraphBuilder:
    """符号级调用关系 (L5; 同文件 + 跨文件, import 感知, 正则级)。"""

    def __init__(self, index: RepositoryIndex) -> None:
        self._index = index

    def build(
        self,
        dependencies: list[FileDependency],
        contents: dict[str, str] | None = None,
        root: str | Path | None = None,
    ) -> CallGraph:
        """全仓库调用图。

        同文件: symbol body 内调用本文件其他 symbol (name( 形式);
        跨文件: 文件 A import 文件 B (deps 边), A 的 symbol body 内出现
        B 定义的 symbol 名 → 边。B 的 symbol 也同时在本文件定义 → 同文件
        边优先 (跨文件仅当本文件无此定义)。
        """
        edges: list[CallEdge] = []
        deps_by_source: dict[str, list[FileDependency]] = {}
        for d in dependencies:
            deps_by_source.setdefault(d.source, []).append(d)
        # 全仓库符号索引: 名称 → [(文件, SymbolEntry)]
        callee_index: dict[str, list[tuple[str, Any]]] = {}
        for f in self._index.files:
            for s in f.symbols:
                callee_index.setdefault(s.name, []).append((f.path, s))
        for entry in self._index.files:
            content = (
                contents.get(entry.path, "")
                if contents is not None
                else _read_text(Path(root) / entry.path) if root is not None else ""
            )
            if not content:
                continue
            lines = content.splitlines()
            local_names = {s.name for s in entry.symbols}
            imported_targets = {d.target for d in deps_by_source.get(entry.path, [])}
            for s in entry.symbols:
                body = lines[s.line - 1 : s.end_line]
                for j, ln in enumerate(body, start=s.line):
                    for m in _CALL_RE.finditer(ln):
                        callee = m.group(1)
                        if callee == s.name or callee not in callee_index:
                            continue
                        # 同文件定义优先
                        if callee in local_names:
                            if _has_local(callee_index, entry.path, callee):
                                edges.append(
                                    CallEdge(
                                        caller_file=entry.path,
                                        caller_symbol=s.name,
                                        callee_file=entry.path,
                                        callee_symbol=callee,
                                        line=j,
                                    )
                                )
                            continue
                        # 跨文件: 仅匹配 import 了的文件 (避免同名误报)
                        for (tfile, _tsym) in callee_index[callee]:
                            if tfile in imported_targets:
                                edges.append(
                                    CallEdge(
                                        caller_file=entry.path,
                                        caller_symbol=s.name,
                                        callee_file=tfile,
                                        callee_symbol=callee,
                                        line=j,
                                    )
                                )
                                break
        return CallGraph(edges=edges)


def _has_local(callee_index: dict[str, list[tuple[str, Any]]], file: str, name: str) -> bool:
    for (f, _s) in callee_index.get(name, []):
        if f == file:
            return True
    return False


# ================================================================ L6 Test Map

class TestMapEntry(BaseModel):
    """测试映射条目: 源文件 → 测试文件列表 (命名约定 / import 引用)。"""

    source_file: str
    test_files: list[str] = Field(default_factory=list)
    basis: str = "naming"  # naming / import / mixed


class TestMapper:
    """测试文件 ↔ 源文件映射 (L6; 命名约定 + import/引用扫描)。"""

    def __init__(self, index: RepositoryIndex) -> None:
        self._index = index
        self._paths = {f.path for f in index.files}

    @staticmethod
    def is_test_file(rel_path: str) -> bool:
        low = rel_path.lower()
        name = Path(low).name
        stem = Path(low).stem  # 去扩展名: test_foo → test_foo; foo_test → foo_test
        if any(kw in name for kw in ("helper", "util", "support", "fixture", "mock")):
            return False  # test_helper.dart 是辅助文件不是测试文件
        return (
            stem.startswith("test_")
            or stem.endswith("_test")
            or ".test." in name
            or "/test/" in "/" + low
            or low.startswith("test/")
            or "/tests/" in "/" + low
        )

    def build(self, dependencies: list[FileDependency] | None = None) -> list[TestMapEntry]:
        """源文件 → [测试文件] (每个源文件一条; 无测试 → 空列表, 供风险标注)。"""
        tests_by_source: dict[str, dict[str, Any]] = {}
        deps = dependencies or []
        deps_by_source: dict[str, list[FileDependency]] = {}
        for d in deps:
            deps_by_source.setdefault(d.source, []).append(d)
        for f in self._index.files:
            if not self.is_test_file(f.path):
                continue
            # 1) 命名约定
            for src in self._naming_candidates(f.path):
                entry = tests_by_source.setdefault(src, {"files": [], "basis": "naming"})
                if f.path not in entry["files"]:
                    entry["files"].append(f.path)
            # 2) import/引用: 测试文件依赖的非测试文件
            for d in deps_by_source.get(f.path, []):
                if not self.is_test_file(d.target):
                    entry = tests_by_source.setdefault(d.target, {"files": [], "basis": "naming"})
                    if f.path not in entry["files"]:
                        entry["files"].append(f.path)
                    # 命名 + import 双命中 → mixed; 仅 import → import
                    entry["basis"] = "mixed" if entry["basis"] == "naming" else "import"
        # 确定性排序 + 全源文件条目
        result: list[TestMapEntry] = []
        for f in sorted(self._index.files, key=lambda e: e.path):
            if self.is_test_file(f.path):
                continue
            info = tests_by_source.get(f.path, {"files": [], "basis": "naming"})
            result.append(
                TestMapEntry(
                    source_file=f.path,
                    test_files=sorted(set(info["files"])),
                    basis=str(info["basis"]),
                )
            )
        return result

    def _naming_candidates(self, test_rel: str) -> list[str]:
        """测试文件 → 候选源文件相对路径 (命名约定; basename 匹配, 跨目录)。"""
        name = Path(test_rel).name
        stem = Path(test_rel).stem
        suffix = Path(test_rel).suffix
        bases: list[str] = []
        if stem.startswith("test_"):
            bases.append(stem[len("test_"):] + suffix)
        if stem.endswith("_test"):
            bases.append(stem[: -len("_test")] + suffix)
        if ".test." in name:
            bases.append(name.split(".test.", 1)[0] + suffix)
        out: list[str] = []
        for base in bases:
            for p in self._paths:
                if Path(p).name == base:
                    out.append(p)
        return out


# ================================================================ L7 Architecture

class RiskArea(BaseModel):
    """风险区域: 文件 + 风险类型 + 详情 (Architecture Summary 输出)。"""

    file: str
    risk: str   # large_file / complex_module / untested
    detail: str = ""


class ArchitectureSummary(BaseModel):
    """架构摘要 (L7): 入口 / 核心模块 / 技术栈 / 风险区域 + 文本摘要。"""

    entry_points: list[str] = Field(default_factory=list)
    core_modules: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    risk_areas: list[RiskArea] = Field(default_factory=list)
    summary_text: str = ""

    def format_text(self) -> str:
        """架构摘要 → 文本 (prompt Architecture Context 素材)。"""
        lines = ["Architecture summary:"]
        if self.entry_points:
            lines.append(f"- entry points: {', '.join(self.entry_points)}")
        if self.tech_stack:
            lines.append(f"- tech stack: {', '.join(self.tech_stack)}")
        if self.core_modules:
            lines.append(f"- core modules: {', '.join(self.core_modules)}")
        if self.risk_areas:
            lines.append("- risks:")
            for r in self.risk_areas:
                lines.append(f"  - {r.file}: {r.risk} ({r.detail})")
        if self.summary_text:
            lines.append(f"- summary: {self.summary_text}")
        return "\n".join(lines)


class ArchitectureSummarizer:
    """架构摘要 (L7): 入口/核心模块/技术栈/风险区域 (确定性启发式)。"""

    def __init__(
        self,
        index: RepositoryIndex,
        root: str | Path,
        dependencies: list[FileDependency] | None = None,
        test_map: list[TestMapEntry] | None = None,
    ) -> None:
        self._index = index
        self._root = Path(root)
        self._deps = dependencies or []
        self._test_map = test_map or []

    def summarize(self) -> ArchitectureSummary:
        entry_points = self._entry_points()
        core_modules = self._core_modules()
        tech_stack = self._tech_stack()
        risk_areas = self._risk_areas()
        summary = (
            f"{len(self._index.files)} files, {len(entry_points)} entry point(s), "
            f"{len(core_modules)} core module(s), {len(risk_areas)} risk area(s); "
            f"languages: {', '.join(self._index.languages)}"
        )
        return ArchitectureSummary(
            entry_points=entry_points,
            core_modules=core_modules,
            tech_stack=tech_stack,
            risk_areas=risk_areas,
            summary_text=summary,
        )

    def _entry_points(self) -> list[str]:
        """入口: 文件名 main/app/run/index/__main__ (importance high 同源) + main() 符号。"""
        out: list[str] = []
        for f in self._index.files:
            stem = Path(f.path).stem.lower()
            if stem in {"main", "app", "run", "index", "server", "cli", "__main__", "entry", "bootstrap"}:
                out.append(f.path)
        return sorted(out)

    def _core_modules(self) -> list[str]:
        """核心模块: 高重要性文件多的模块 + 被依赖文件数 top 的模块。"""
        by_module: dict[str, int] = {}
        for f in self._index.files:
            if f.importance == "high":
                by_module[f.module] = by_module.get(f.module, 0) + 1
        for d in self._deps:
            by_module[module_of(d.target)] = by_module.get(module_of(d.target), 0) + 1
        ranked = sorted(by_module.items(), key=lambda kv: (-kv[1], kv[0]))
        return [mod for mod, _ in ranked[:5] if mod != "(root)"]

    def _tech_stack(self) -> list[str]:
        """技术栈: 语言 + 框架线索文件 (pubspec/package.json/pyproject 等)。"""
        stack = list(self._index.languages)
        for fname in ("pubspec.yaml", "pubspec.yml", "package.json", "pyproject.toml",
                      "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "composer.json",
                      "Gemfile", "requirements.txt"):
            path = self._root / fname
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            hint = _framework_hint(fname, text)
            if hint and hint not in stack:
                stack.append(hint)
        return stack

    def _risk_areas(self) -> list[RiskArea]:
        """风险区域: 大文件 (>500 行) / 复杂模块 (高依赖文件) / 无测试映射。"""
        risks: list[RiskArea] = []
        tested = {e.source_file for e in self._test_map if e.test_files}
        for f in self._index.files:
            if f.language in {"markdown", "json", "yaml", "toml", "text", "html", "css"}:
                continue
            if f.line_count > _LARGE_FILE_LINES:
                risks.append(
                    RiskArea(
                        file=f.path,
                        risk="large_file",
                        detail=f"{f.line_count} lines (>{_LARGE_FILE_LINES}) — 上下文预算/修改风险",
                    )
                )
            dependents = sum(1 for d in self._deps if d.target == f.path)
            if dependents >= 8:
                risks.append(
                    RiskArea(
                        file=f.path,
                        risk="complex_module",
                        detail=f"depended on by {dependents} files — 高耦合, 修改影响面大",
                    )
                )
            if f.path not in tested and f.importance == "high":
                risks.append(
                    RiskArea(
                        file=f.path,
                        risk="untested",
                        detail="no test mapping found — 修改后验证覆盖未知",
                    )
                )
        return risks


def _framework_hint(fname: str, text: str) -> str:
    """框架线索文件 → 技术栈提示 (确定性启发式; 无 → "")。"""
    if fname.startswith("pubspec"):
        if "flutter:" in text:
            deps = _extract_yaml_keys(text, "dependencies", max_keys=3)
            return f"Flutter (Dart{(' + ' + deps) if deps else ''})"
        return "Dart (pubspec)"
    if fname == "package.json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return "Node.js (package.json)"
        deps = list((data.get("dependencies") or {}).keys())[:3]
        return f"Node.js{(' + ' + ', '.join(deps)) if deps else ''}"
    if fname == "pyproject.toml":
        return "Python (pyproject.toml)"
    if fname == "requirements.txt":
        return "Python (requirements.txt)"
    if fname == "go.mod":
        return "Go (go.mod)"
    if fname == "Cargo.toml":
        return "Rust (Cargo.toml)"
    if fname == "pom.xml":
        return "Java Spring Boot (Maven)" if "spring-boot" in text else "Java (Maven)"
    if fname == "build.gradle":
        return "Java/Kotlin (Gradle)"
    if fname == "composer.json":
        return "PHP (Composer)"
    if fname == "Gemfile":
        return "Ruby (Bundler)"
    return ""


def _extract_yaml_keys(text: str, section: str, max_keys: int) -> str:
    """yaml 文本 → 指定 section 下的键名 (前 max_keys; 行级启发式)。"""
    in_section = False
    keys: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not in_section:
            if stripped == f"{section}:" or stripped.startswith(f"{section}:"):
                in_section = True
            continue
        if stripped and not stripped.startswith(("-", "#")) and ":" in stripped:
            key = stripped.split(":", 1)[0].strip().strip("'\"")
            if key and not key.startswith("#"):
                keys.append(key)
                if len(keys) >= max_keys:
                    break
        if stripped and not stripped.startswith((" ", "\t")) and ":" in stripped:
            break  # 下一顶层 section
    return ", ".join(keys)


# ================================================================ 门面

def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


class RepositoryIntelligence:
    """仓库情报门面: 一次分析产出 L1-L7 全部 (Context Assembly 输入)。

    构造: root (项目根) + 可选 project_files 过滤 (沙箱副本场景)。
    analyze() 后: index (含 importance) / modules / dependencies /
    call_graph / test_map / architecture 全部就绪。
    """

    def __init__(
        self, root: str | Path, *, project_files: list[str] | None = None
    ) -> None:
        self._root = Path(root)
        self._index = (
            RepositoryIndexer(self._root).index()
            if not project_files
            else _filtered_index(self._root, project_files)
        )
        self._contents: dict[str, str] = {}
        self._modules: list[ModuleEntry] = []
        self._dependencies: list[FileDependency] = []
        self._call_graph = CallGraph()
        self._test_map: list[TestMapEntry] = []
        self._architecture: ArchitectureSummary | None = None
        self._analyzed = False

    # ------------------------------------------------------------ 分析

    def analyze(self) -> "RepositoryIntelligence":
        """全量分析 (幂等; 重复调用零副作用)。"""
        if self._analyzed:
            return self
        self._contents = self._load_contents()
        self._dependencies = DependencyAnalyzer(self._index, self._root).analyze(self._contents)
        # 依赖数增强 → importance (被多文件依赖 = 核心)
        self._index = self._index.recompute_importance(
            DependencyAnalyzer.dependents_count(self._dependencies)
        )
        self._modules = ModuleIntelligence(self._index).build_module_map(self._dependencies)
        self._call_graph = CallGraphBuilder(self._index).build(
            self._dependencies, contents=self._contents
        )
        self._test_map = TestMapper(self._index).build(self._dependencies)
        self._architecture = ArchitectureSummarizer(
            self._index, self._root, self._dependencies, self._test_map
        ).summarize()
        self._analyzed = True
        return self

    def _load_contents(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for f in self._index.files:
            content = _read_text(self._root / f.path)
            if content:
                out[f.path] = content
        return out

    # ------------------------------------------------------------ 查询

    @property
    def index(self) -> RepositoryIndex:
        return self._index

    @property
    def modules(self) -> list[ModuleEntry]:
        return self._modules

    @property
    def dependencies(self) -> list[FileDependency]:
        return self._dependencies

    @property
    def call_graph(self) -> CallGraph:
        return self._call_graph

    @property
    def test_map(self) -> list[TestMapEntry]:
        return self._test_map

    @property
    def architecture(self) -> ArchitectureSummary:
        if self._architecture is None:
            self.analyze()
        assert self._architecture is not None
        return self._architecture

    def impact_of(self, file: str) -> list[str]:
        """修改 A → 依赖 A 的文件列表 (影响面; 依赖图反向查询)。"""
        self.analyze()
        return DependencyAnalyzer.impact_map(self._dependencies).get(file, [])

    def callers_of(self, file: str, symbol: str | None = None) -> list[CallEdge]:
        """谁调用了 (file, symbol) — 修改前影响范围 (Call Graph)。"""
        self.analyze()
        return self._call_graph.callers_of(file, symbol)

    def tests_for(self, source_file: str) -> list[str]:
        """源文件 → 相关测试文件列表 (验证选择)。"""
        self.analyze()
        for e in self._test_map:
            if e.source_file == source_file:
                return list(e.test_files)
        return []

    def symbol_definition(self, name: str) -> list[tuple[str, int]]:
        """符号名 → [(文件, 定义行)] (谁定义; symbol 锚点定位 — 失败样本定位)。"""
        self.analyze()
        return [(path, s.line) for path, s in self._index.symbols_by_name(name)]

    # ------------------------------------------------------------ 上下文文本

    def format_context(
        self,
        *,
        max_files: int = 100,
        include_modules: bool = True,
        include_architecture: bool = True,
        include_tests: bool = True,
    ) -> str:
        """文件树 + 重要性 + 模块 + 架构 + 测试映射 → 文本 (prompt 素材)。

        Call Graph 段按需单独取 (format_call_graph — 修改目标相关才渲染,
        控制上下文预算)。默认输出 L1+L2+L7+L6 摘要; L5 按目标文件取。
        """
        self.analyze()
        parts = [
            self._index.format_context(
                max_files=max_files, include_symbols=True, include_importance=True
            )
        ]
        if include_modules and self._modules:
            parts.append("Modules:\n" + "\n".join(m.format_text() for m in self._modules))
        if include_architecture and self._architecture is not None:
            parts.append(self._architecture.format_text())
        if include_tests and self._test_map:
            tested = [e for e in self._test_map if e.test_files]
            lines = ["Test map:"]
            for e in tested[:30]:
                lines.append(f"- {e.source_file} → {', '.join(e.test_files)}")
            if len(tested) > 30:
                lines.append(f"... ({len(tested) - 30} more mapped files)")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    def format_call_graph(self, *, file: str | None = None, symbol: str | None = None,
                          max_edges: int = 25) -> str:
        """调用图相关段 (影响面: 谁调用了目标; 上下文预算控制)。"""
        self.analyze()
        if not self._call_graph.edges:
            return "(no call edges detected)"
        if file is not None:
            incoming = self._call_graph.callers_of(file, symbol)
            outgoing = self._call_graph.callees_of(file, symbol)
            lines = [f"Call graph for {file}" + (f"::{symbol}" if symbol else "") + ":"]
            for e in incoming[:max_edges]:
                lines.append(f"- called by {e.caller_file}::{e.caller_symbol} @ line {e.line}")
            for e in outgoing[:max_edges]:
                lines.append(f"- calls {e.callee_file}::{e.callee_symbol} @ line {e.line}")
            if not incoming and not outgoing:
                lines.append("- no call edges involving this file")
            return "\n".join(lines)
        # 全图摘要: 按文件聚合边数 (top)
        counts: dict[str, int] = {}
        for e in self._call_graph.edges:
            counts[e.caller_file] = counts.get(e.caller_file, 0) + 1
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:10]
        lines = [f"Call graph ({len(self._call_graph.edges)} edges):"]
        for path, n in top:
            lines.append(f"- {path}: {n} call edge(s)")
        return "\n".join(lines)


def _filtered_index(root: Path, project_files: list[str]) -> RepositoryIndex:
    """选择性复制场景: 只索引 project_files 覆盖的文件 (沙箱副本同源)。"""
    from .repo_index import index_sandbox

    return index_sandbox(root, project_files)


def analyze_repository(
    root: str | Path, *, project_files: list[str] | None = None
) -> RepositoryIntelligence:
    """便捷入口: index + 全量分析 → RepositoryIntelligence (一次调用)。"""
    return RepositoryIntelligence(root, project_files=project_files).analyze()
