"""factory-exec/exec/project_adoption.py — Existing Project Adoption (S9-004)。

已有项目接入三件套 (复用 repo_intelligence L2-L7, 零 LLM / 零数据库 /
零第三方静态分析库, 全部确定性启发式):

- detect_language / detect_framework: 语言/框架检测 (清单文件强信号 +
  扩展名统计; 与 repo_index 语言判定同源启发式);
- analyze_project: Repository Analyzer → Project Analysis 载荷
  (language/framework/structure/dependencies/build_method/test_method —
  与 factory-org CONTRACTS project_analysis 同源);
- run_baseline: Baseline Validation → {build, test} 结果 (失败安全:
  build/test 命令缺失 → status "unavailable" 不崩溃; 命令失败 → "failed"
  记录 output_head; Python 无 build_command 时 ast.parse 语法检查兜底 —
  零副作用, 不写 __pycache__);
- build_context_snapshot: Context Snapshot → 浅层目录树 + 重要文件
  (repo_intelligence File Importance) + 架构摘要 (供后续 Agent 上下文输入,
  标注为输入而非事实证据)。

KISS 边界 (同 repo_intelligence): 正则/清单启发式, 允许误报漏报; 命令
执行限时 (timeout 默认 120s), output_head 截断 (默认 500 字符) 控上下文。

设计依据: docs/sprint9/sprint9-architecture.md §3 (Existing Project Adoption
— Project 注册器 + 沙箱快照 + 基线测试运行确认环境可用)。
"""

from __future__ import annotations

import ast
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from .repo_intelligence import analyze_repository

#: 遍历跳过的噪声目录 (树/语言统计 — 构建产物与版本库不参与分析)
_NOISE_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", "__pycache__", ".dart_tool", "node_modules",
        "build", "dist", ".venv", "venv", ".factory", ".idea", ".vscode",
        ".pytest_cache", ".mypy_cache", ".ruff_cache", ".DS_Store",
    }
)

#: 扩展名 → 语言 (语言检测; 与 repo_index 支持语言对齐)
_LANGUAGE_SUFFIXES: dict[str, str] = {
    ".py": "python",
    ".dart": "dart",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
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
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "shell",
    ".swift": "swift",
    ".cs": "csharp",
}

#: 清单文件强信号 (存在 → 语言候选; 排序 = 优先级, 先命中先得)
_MANIFEST_LANGUAGE: list[tuple[str, str]] = [
    ("pubspec.yaml", "dart"),
    ("go.mod", "go"),
    ("Cargo.toml", "rust"),
    ("pyproject.toml", "python"),
    ("setup.py", "python"),
    ("requirements.txt", "python"),
    ("package.json", "javascript"),
    ("pom.xml", "java"),
    ("build.gradle", "java"),
    ("build.gradle.kts", "kotlin"),
    ("composer.json", "php"),
    ("Gemfile", "ruby"),
    ("Makefile", "unknown"),  # Makefile 存在但语言不定 (不抢占强信号)
]

#: 框架检测: (候选文件, 内含关键字 → 框架) 按语言分组
_FRAMEWORK_HINTS: dict[str, list[tuple[str, str, str]]] = {
    "dart": [
        ("pubspec.yaml", "flutter:", "flutter"),
        ("pubspec.yaml", "", "dart"),
    ],
    "python": [
        ("manage.py", "", "django"),
        ("pyproject.toml", "django", "django"),
        ("pyproject.toml", "fastapi", "fastapi"),
        ("pyproject.toml", "flask", "flask"),
        ("pyproject.toml", "", "pyproject"),
        ("setup.py", "", "setuptools"),
    ],
    "javascript": [
        ("package.json", '"next"', "nextjs"),
        ("package.json", '"react"', "react"),
        ("package.json", '"vue"', "vue"),
        ("package.json", '"express"', "express"),
        ("package.json", "", "node"),
    ],
    "typescript": [
        ("package.json", '"next"', "nextjs"),
        ("package.json", '"react"', "react"),
        ("package.json", '"vue"', "vue"),
        ("package.json", '"express"', "express"),
        ("package.json", "", "node"),
        ("tsconfig.json", "", "typescript"),
    ],
    "java": [
        ("pom.xml", "", "maven"),
        ("build.gradle", "", "gradle"),
    ],
    "kotlin": [
        ("build.gradle.kts", "", "gradle-kotlin"),
        ("pom.xml", "", "maven"),
    ],
    "go": [("go.mod", "", "go-modules")],
    "rust": [("Cargo.toml", "", "cargo")],
}

#: 测试方法检测: (测试文件内关键字 → 方法) 按语言分组 (内容信号, 确定性)
_TEST_METHOD_HINTS: dict[str, list[tuple[str, str]]] = {
    "python": [("import pytest", "pytest"), ("import unittest", "unittest")],
    "dart": [("flutter_test", "flutter_test"), ("package:test", "dart_test")],
    "javascript": [("vitest", "vitest"), ("jest", "jest"), ("mocha", "mocha")],
    "typescript": [("vitest", "vitest"), ("jest", "jest"), ("mocha", "mocha")],
    "java": [("org.junit", "junit"), ("org.testng", "testng")],
    "kotlin": [("kotlin.test", "kotlin_test")],
    "go": [("testing", "go_test")],
    "rust": [("#[test]", "cargo_test")],
}


def _is_test_file(rel_path: str, language: str) -> bool:
    """测试文件命名约定判定 (语言感知; 与 repo_intelligence 测试判定同源启发式)。"""
    name = Path(rel_path).name
    low = rel_path.lower()
    if language == "python":
        return (
            name.startswith("test_")
            or name.endswith("_test.py")
            or low.startswith("tests/")
            or "/tests/" in "/" + low
        )
    if language == "dart":
        return name.endswith("_test.dart")
    if language in ("javascript", "typescript"):
        return ".test." in name or ".spec." in name
    if language == "java":
        return name.endswith("Test.java")
    if language == "kotlin":
        return name.endswith("Test.kt")
    if language == "go":
        return name.endswith("_test.go")
    if language == "rust":
        return low.startswith("tests/")
    return False


def detect_test_method(
    root: str | Path, language: str = "", test_files: list[str] | None = None
) -> str:
    """测试方法提示: 命名约定找测试文件 → 内容关键字定框架; 无测试 → unknown。

    约定存在但无框架关键字时按语言默认惯例推断 (python → pytest, dart →
    dart_test — 事实惯例, 非猜测); 其余语言 → unknown (诚实不猜)。
    """
    root = Path(root)
    language = language or detect_language(root)
    test_files = test_files if test_files is not None else [
        p.relative_to(root).as_posix() for p in _iter_source_files(root)
    ]
    candidates = [f for f in test_files if _is_test_file(f, language)]
    if not candidates:
        return "unknown"
    hints = _TEST_METHOD_HINTS.get(language, [])
    for keyword, method in hints:
        for f in candidates[:20]:
            try:
                text = (root / f).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if keyword in text:
                return method
    if language == "python":
        return "pytest"
    if language == "dart":
        return "dart_test"
    return "unknown"


def _iter_source_files(root: Path) -> list[Path]:
    """遍历根目录下源码文件 (跳过噪声目录; 排序稳定, 确定性)。"""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in _NOISE_DIRS
        )
        for name in sorted(filenames):
            if name in _NOISE_DIRS:
                continue
            out.append(Path(dirpath) / name)
    return out


def detect_language(root: str | Path) -> str:
    """主语言检测: 清单强信号优先, 其次扩展名计数 (平局按优先级序)。"""
    root = Path(root)
    if not root.is_dir():
        return "unknown"
    for manifest, lang in _MANIFEST_LANGUAGE:
        if (root / manifest).is_file():
            return lang
    counts: dict[str, int] = {}
    for path in _iter_source_files(root):
        lang = _LANGUAGE_SUFFIXES.get(path.suffix.lower())
        if lang is not None:
            counts[lang] = counts.get(lang, 0) + 1
    if not counts:
        return "unknown"
    return max(counts.items(), key=lambda kv: kv[1])[0]


def detect_framework(root: str | Path, language: str = "") -> str:
    """框架检测: 语言候选清单文件 + 关键字匹配 → 框架 (未识别 → "")。"""
    root = Path(root)
    language = language or detect_language(root)
    hints = _FRAMEWORK_HINTS.get(language, [])
    for filename, keyword, framework in hints:
        path = root / filename
        if not path.is_file():
            continue
        if keyword:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if keyword not in text:
                continue
        return framework
    return ""


def detect_build_method(root: str | Path, language: str = "") -> str:
    """构建方法提示: 清单文件 → 已知打包方法; 否则 unknown。"""
    root = Path(root)
    language = language or detect_language(root)
    if language == "dart" and (root / "pubspec.yaml").is_file():
        return "dart_package (pub get + analyze/build)"
    if language == "python":
        if (root / "pyproject.toml").is_file():
            return "python_package (pyproject.toml)"
        if (root / "setup.py").is_file():
            return "python_package (setup.py)"
        return "python_syntax_check"
    if language in ("javascript", "typescript") and (root / "package.json").is_file():
        return "node_package (npm install)"
    if language == "go" and (root / "go.mod").is_file():
        return "go_build (go build)"
    if language == "rust" and (root / "Cargo.toml").is_file():
        return "cargo_build (cargo build)"
    if language == "java":
        if (root / "pom.xml").is_file():
            return "maven_build (mvn package)"
        if (root / "build.gradle").is_file():
            return "gradle_build (gradle build)"
    return "unknown"


def analyze_project(
    root: str | Path, *, project_files: list[str] | None = None
) -> dict[str, Any]:
    """Repository Analyzer → Project Analysis 载荷 (CONTRACTS project_analysis)。

    复用 repo_intelligence (L2 模块 / L3 依赖 / L6 测试映射 / L7 架构):
    - structure: 模块列表 {path, responsibility, file_count}
    - dependencies: {edge_count, file_count, top_dependents, languages}
    - build_method / test_method: 清单/命名约定提示 (unavailable → "unknown")
    空仓库回退单条 "(root)" 占位 (契约 min_items 1, 失败安全)。
    """
    root = Path(root)
    intelligence = analyze_repository(root, project_files=project_files)
    language = detect_language(root)
    framework = detect_framework(root, language)
    modules = [
        {"path": m.path, "responsibility": m.responsibility, "file_count": len(m.files)}
        for m in intelligence.modules
    ]
    dependents = _dependents_count(intelligence.dependencies)
    top_dependents = sorted(
        dependents.items(), key=lambda kv: (-kv[1], kv[0])
    )[:10]
    dependencies = {
        "edge_count": len(intelligence.dependencies),
        "file_count": len(intelligence.index.files),
        "top_dependents": [
            {"file": path, "count": count} for path, count in top_dependents
        ],
        "languages": intelligence.index.languages,
    }
    test_files = [f.path for f in intelligence.index.files]
    return {
        "language": language,
        "framework": framework,
        "structure": modules or [
            {"path": "(root)", "responsibility": "no source files", "file_count": 0}
        ],
        "dependencies": dependencies,
        "build_method": detect_build_method(root, language),
        "test_method": detect_test_method(root, language, test_files),
    }


def _dependents_count(
    dependencies: list[Any],
) -> dict[str, int]:
    """依赖图 → 被依赖文件数 {target: count} (影响面摘要)。"""
    out: dict[str, int] = {}
    for dep in dependencies:
        out[dep.target] = out.get(dep.target, 0) + 1
    return out


# ---------------------------------------------------------------- Baseline


def _run_command(
    command: str, cwd: Path, *, timeout: int, max_output: int
) -> dict[str, Any]:
    """执行命令 (cwd 内; 失败安全: 找不到命令/超时 → 记录, 不抛异常)。

    返回: {status: passed|failed|unavailable, command, returncode,
    output_head}。status 语义:
    - passed: returncode 0
    - failed: returncode ≠ 0 或超时
    - unavailable: 命令不可执行 (可执行文件不存在 — 环境问题, 非构建失败)
    """
    result: dict[str, Any] = {
        "command": command,
        "returncode": None,
        "output_head": "",
    }
    try:
        proc = subprocess.run(
            shlex.split(command),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        result.update(
            status="unavailable",
            output_head=f"command not found: {exc.filename or command}",
        )
        return result
    except subprocess.TimeoutExpired as exc:
        output = str(exc.stdout or "") + str(exc.stderr or "")
        result.update(
            status="failed",
            output_head=f"timed out after {timeout}s: {output.strip()[:max_output]}",
        )
        return result
    output = (proc.stdout or "") + (proc.stderr or "")
    result.update(
        status="passed" if proc.returncode == 0 else "failed",
        returncode=proc.returncode,
        output_head=output.strip()[:max_output],
    )
    return result


def syntax_check_python(
    root: str | Path, *, files: list[Path] | None = None, max_files: int = 200
) -> dict[str, Any]:
    """Python 语法检查兜底 (build_command 缺失时): ast.parse 全量 .py。

    零副作用 — 不写 __pycache__ (与 compileall 不同); 跳过噪声目录;
    上限 max_files 防超大仓库失控。失败 → 首 5 个错误摘要。
    """
    root = Path(root)
    targets = files if files is not None else _iter_source_files(root)
    errors: list[str] = []
    checked = 0
    for path in targets:
        if path.suffix.lower() != ".py":
            continue
        rel = path.relative_to(root).as_posix()
        if any(part in _NOISE_DIRS for part in Path(rel).parts):
            continue
        if checked >= max_files:
            break
        try:
            ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            checked += 1
        except SyntaxError as exc:
            errors.append(f"{rel}:{exc.lineno}: {exc.msg}")
    if errors:
        return {
            "status": "failed",
            "command": "syntax_check(python)",
            "returncode": 1,
            "output_head": "; ".join(errors[:5]),
            "error_count": len(errors),
        }
    return {
        "status": "passed",
        "command": "syntax_check(python)",
        "returncode": 0,
        "output_head": f"python syntax OK ({checked} files checked)",
        "error_count": 0,
    }


_PASSED_RE = re.compile(r"(\d+)\s+passed")
_FAILED_RE = re.compile(r"(\d+)\s+failed")


def _parse_test_counts(output: str) -> tuple[int, int]:
    """pytest 风格输出 → (passed, failed); 无匹配 → 0 (宽容解析)。"""
    passed = 0
    failed = 0
    for match in _PASSED_RE.finditer(output):
        passed = int(match.group(1))
    for match in _FAILED_RE.finditer(output):
        failed = int(match.group(1))
    return passed, failed


def run_baseline(
    root: str | Path,
    *,
    build_command: str = "",
    test_command: str = "",
    language: str = "",
    timeout: int = 120,
    max_output: int = 500,
) -> dict[str, Any]:
    """Baseline Validation → {build, test} (失败安全, 不抛异常)。

    - build: build_command 非空 → 执行; 空且 language=python → 语法检查;
      否则 → unavailable (无命令且无兜底, 记录原因不崩溃)
    - test: test_command 非空 → 执行 + pytest 风格 passed/failed 计数;
      空 → unavailable
    analysis_ref 由 org 侧回填 (本函数返回 "" 占位)。
    """
    root = Path(root)
    build: dict[str, Any]
    if build_command.strip():
        build = _run_command(
            build_command, root, timeout=timeout, max_output=max_output
        )
    elif language == "python":
        build = syntax_check_python(root)
    else:
        build = {
            "status": "unavailable",
            "command": "",
            "returncode": None,
            "output_head": (
                f"no build command; no syntax check fallback for "
                f"language {language or 'unknown'}"
            ),
        }
    test: dict[str, Any]
    if test_command.strip():
        test = _run_command(
            test_command, root, timeout=timeout, max_output=max_output
        )
        passed, failed = _parse_test_counts(test["output_head"])
        test["passed"] = passed
        test["failed"] = failed
    else:
        test = {
            "status": "unavailable",
            "command": "",
            "returncode": None,
            "output_head": "no test command",
            "passed": 0,
            "failed": 0,
        }
    return {"build": build, "test": test, "analysis_ref": ""}


# -------------------------------------------------------- Context Snapshot


def build_directory_tree(
    root: str | Path, *, max_depth: int = 3, max_entries: int = 60
) -> list[str]:
    """浅层目录树 (缩进行; 跳过噪声目录; 深度/条目上限, 确定性排序)。

    行格式: 目录 "dir/" / 文件 "file" (相对路径, 与 repo_index 同语义);
    BFS 层序遍历, 同层按名称排序; 条目超上限即截断 (不再深入)。
    """
    root = Path(root)
    lines: list[str] = []
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack and len(lines) < max_entries:
        current, depth = stack.pop(0)
        if depth > max_depth:
            continue
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for entry in entries:
            if entry.name in _NOISE_DIRS:
                continue
            if len(lines) >= max_entries:
                break
            rel = entry.relative_to(root).as_posix()
            prefix = "  " * depth
            if entry.is_dir():
                lines.append(f"{prefix}{rel}/")
                stack.append((entry, depth + 1))
            else:
                lines.append(f"{prefix}{rel}")
    return lines


def build_context_snapshot(
    root: str | Path,
    *,
    intelligence: Any = None,
    max_depth: int = 3,
    max_entries: int = 60,
    max_important: int = 30,
) -> dict[str, Any]:
    """Context Snapshot → {tree, tree_entries, important_files, architecture,
    summary_text} (供后续 Agent 上下文输入, 标注为输入)。

    - important_files: File Importance 排序 (high → medium → low, 行数降序),
      上限 max_important; 每条 {path, importance, language, line_count}
    - architecture: repo_intelligence L7 摘要 (entry_points/core_modules/
      tech_stack/risk_areas/summary_text)
    """
    root = Path(root)
    if intelligence is None:
        intelligence = analyze_repository(root)
    tree = build_directory_tree(root, max_depth=max_depth, max_entries=max_entries)
    ranked = sorted(
        intelligence.index.files,
        key=lambda f: (
            {"high": 0, "medium": 1, "low": 2}.get(f.importance, 3),
            -f.line_count,
            f.path,
        ),
    )
    important = [
        {
            "path": f.path,
            "importance": f.importance,
            "language": f.language,
            "line_count": f.line_count,
        }
        for f in ranked[:max_important]
    ]
    arch = intelligence.architecture
    architecture = {
        "entry_points": list(arch.entry_points),
        "core_modules": list(arch.core_modules),
        "tech_stack": list(arch.tech_stack),
        "risk_areas": [
            {"file": r.file, "risk": r.risk, "detail": r.detail}
            for r in arch.risk_areas
        ],
        "summary_text": arch.summary_text,
    }
    languages = intelligence.index.languages
    summary_text = (
        f"Project context for {root.name}: {len(intelligence.index.files)} "
        f"files, languages: {', '.join(languages[:3]) or 'none'}. "
        f"{arch.summary_text}"
    )
    return {
        "tree": tree,
        "tree_entries": len(tree),
        "important_files": important,
        "important_count": len(important),
        "architecture": architecture,
        "summary_text": summary_text,
    }
