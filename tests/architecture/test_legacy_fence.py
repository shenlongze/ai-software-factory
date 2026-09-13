"""旧代码围栏 —— 只减不增（结构可控的机器保证）。

R13  新地基（src/ai_factory_os）不得 import 旧代码
R14  旧代码文件只减不增：文件集 ⊆ 基线，总行数 ≤ 基线
R15  旧代码跨分区依赖边只减不增
R16  不得出现新的顶层代码目录（防新增堆放场）

基线由 scripts/legacy_inventory.py --write 生成。
被绞杀对象 = LEGACY_ROOTS；工具/文档/入口不计入围栏。
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEW = ROOT / "src" / "ai_factory_os"
BASELINE_PATH = Path(__file__).with_name("legacy_baseline.json")

SKIP = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
        "node_modules", "build", "dist", "target", ".mypy_cache"}

LEGACY_ROOTS = ("demo", "factory-console", "factory-core", "factory-exec",
                "factory-org", "factory-runtime", "factory_console", "kernel", "services")
ALLOWED_TOP = set(LEGACY_ROOTS) | {"src", "tests", "scripts", "docs", "bin", "apps"}


def _baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _legacy_files() -> list[Path]:
    found = []
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP for part in path.parts) or "tests" in path.parts:
            continue
        if NEW in path.parents or path.relative_to(ROOT).parts[0] not in LEGACY_ROOTS:
            continue
        found.append(path)
    return sorted(found)


def _imports_of(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            mods.add(node.module.split(".")[0])
    return mods


def _current() -> dict:
    files = _legacy_files()
    lines = {f: len(f.read_text(encoding="utf-8", errors="replace").splitlines()) for f in files}
    edges: dict[str, int] = {}
    for f in files:
        src = f.relative_to(ROOT).parts[0]
        for mod in _imports_of(f):
            for target in LEGACY_ROOTS:
                if mod in (target, target.replace("-", "_")) and src != target:
                    key = f"{src}->{target}"
                    edges[key] = edges.get(key, 0) + 1
    return {"files": [str(f.relative_to(ROOT)) for f in files],
            "lines": sum(lines.values()), "edges": edges}


def test_r13_new_ground_never_imports_legacy() -> None:
    """R13: 新地基不得 import 旧代码。"""
    root_names = {r.replace("-", "_") for r in LEGACY_ROOTS}
    for path in sorted(NEW.rglob("*.py")):
        for mod in _imports_of(path):
            assert mod not in root_names, f"[R13] {path.relative_to(ROOT)} -> {mod}"


def test_r14_legacy_files_only_shrink() -> None:
    """R14: 旧代码文件只减不增（文件集 ⊆ 基线，总行数 ≤ 基线）。"""
    base, cur = _baseline(), _current()
    added = sorted(set(cur["files"]) - set(base["files"]))
    assert not added, f"[R14] 新增旧代码文件: {added[:10]}"
    assert cur["lines"] <= base["lines"], \
        f"[R14] 旧代码行数增长 {base['lines']} -> {cur['lines']}"


def test_r15_legacy_edges_only_shrink() -> None:
    """R15: 旧代码跨分区依赖边只减不增。"""
    base, cur = _baseline(), _current()
    for key, count in sorted(cur["edges"].items()):
        ceiling = base["edges"].get(key, 0)
        assert count <= ceiling, f"[R15] 边增长 {key}: {ceiling} -> {count}"


def test_r16_no_new_top_level_code_dirs() -> None:
    """R16: 不得出现新的顶层代码目录（防新增堆放场）。"""
    tops = {p.relative_to(ROOT).parts[0] for p in ROOT.rglob("*.py")
            if not any(part in SKIP for part in p.parts)}
    unexpected = sorted(tops - ALLOWED_TOP)
    assert not unexpected, f"[R16] 新的顶层代码目录: {unexpected}"
