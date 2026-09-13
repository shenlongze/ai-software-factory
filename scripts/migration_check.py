#!/usr/bin/env python3
"""搬迁可分离性检查（只读）—— 搬之前先算这批文件有多少条线连在批次外。

刀16 的教训：`factory-console/api` 看着是 24 个文件的自足目录，实际有 68 处相对
import 指向 10 个兄弟包 → 搬进去就断。**判据不是文件数，是"批次外引用数"。**

用法：
    python scripts/migration_check.py                 # 扫描所有候选并按可分离度排序
    python scripts/migration_check.py factory-org/org # 只看某个批次
"""
from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 硬跳过：缓存/依赖/构建产物（这些不是代码）
SKIP_HARD = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
             "build", "dist", "target", "node_modules", "htmlcov", ".mypy_cache"}
# 索引用硬名单：测试/脚本/新地基也可能是消费者，必须算进「入边」
SKIP = SKIP_HARD

# 目录 → 包名前缀（对齐运行时：bin/factory 的 PYTHONPATH + pyproject package-dir）
ROOTS: tuple[tuple[Path, str], ...] = (
    (ROOT / "src" / "legacy" / "factory-console", "factory_console"),
    (ROOT / "src" / "legacy" / "factory-core", ""),
    (ROOT / "src" / "legacy" / "factory-exec", ""),
    (ROOT / "src" / "legacy" / "factory-org", ""),
    (ROOT / "src" / "legacy" / "factory-runtime", ""),
    (ROOT, ""),
)

STDLIB = set(sys.stdlib_module_names)


def _third_party(name: str) -> bool:
    """该顶层名是否第三方/标准库（非仓库内代码）。"""
    if name in STDLIB:
        return True
    for root, prefix in ROOTS:
        for cand in (root / name, root / name.replace("_", "-")):
            if cand.is_dir() and any(cand.glob("*.py")):
                return False
            if (root / f"{name}.py").is_file():
                return False
    return True


def module_of(path: Path) -> str | None:
    """文件 → 模块名（与运行时一致）。"""
    for root, prefix in ROOTS:
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        parts = list(rel.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        if not parts:
            continue
        dotted = ".".join(parts)
        return f"{prefix}.{dotted}" if prefix else dotted
    return None


def build_index() -> dict[str, Path]:
    idx: dict[str, Path] = {}
    for root, prefix in ROOTS:
        if not root.is_dir():
            continue
        for p in root.rglob("*.py"):
            if any(s in p.parts for s in SKIP):
                continue
            m = module_of(p)
            if m:
                idx.setdefault(m, p)
    return idx


INDEX = build_index()


def imports_of(path: Path) -> list[tuple[int, str, str]]:
    """返回 [(level, module, 原文)]，level>0 为相对 import。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            out.append((n.level, n.module or "", f"from {'.' * n.level}{n.module or ''} import ..."))
        elif isinstance(n, ast.Import):
            for a in n.names:
                out.append((0, a.name, f"import {a.name}"))
    return out


def resolve(level: int, module: str, owner: str) -> str | None:
    """把 import 解析成绝对模块名；无法判定返回 None。"""
    if level == 0:
        return module
    parts = owner.split(".")
    # 找到 owner 的包：__init__.py 自身即包，否则退一级
    f = INDEX.get(owner)
    pkg = owner if (f is not None and f.name == "__init__.py") else ".".join(parts[:-1])
    for _ in range(level - 1):
        pkg = pkg.rpartition(".")[0]
    return f"{pkg}.{module}" if module else pkg


def check(unit: Path) -> dict:
    """算两个方向：
      出边 —— 本批文件 import 批次外的模块（搬走会断自己）
      入边 —— 批次外的文件 import 本批模块（搬走会断消费者）
    刀16 教训 + 本工具首跑 bug：只看出边会把 tasks/project 误判为"0 引用可搬"。
    """
    unit_files = [p for p in unit.rglob("*.py") if "__pycache__" not in p.parts]
    lines = sum(len(p.read_text(encoding="utf-8", errors="replace").splitlines()) for p in unit_files)
    unit_mods = {m for m, p in INDEX.items() if unit == p.parent or unit in p.parents}

    outgoing: dict[str, list[str]] = defaultdict(list)
    unresolved = 0
    for p in unit_files:
        owner = module_of(p) or ""
        for level, module, raw in imports_of(p):
            target = resolve(level, module, owner)
            if target is None:
                continue
            top = target.split(".")[0]
            if not top or _third_party(top):
                continue
            tf = INDEX.get(target) or INDEX.get(top)
            if tf is not None and unit in tf.parents:
                continue
            outgoing[".".join(target.split(".")[:2])].append(p.name)
            if tf is None:
                unresolved += 1

    incoming: dict[str, set[str]] = defaultdict(set)
    unit_tops = {m.split(".")[0] for m in unit_mods}
    for m, p in INDEX.items():
        if unit in p.parents:
            continue
        for level, module, _raw in imports_of(p):
            target = resolve(level, module, m)
            if target is None:
                continue
            top = target.split(".")[0]
            if top and top in unit_tops:
                incoming[top].add(str(p.relative_to(ROOT)))

    return {"files": len(unit_files), "lines": lines, "out": dict(outgoing),
            "in": {k: sorted(v) for k, v in incoming.items()}, "unresolved": unresolved}


def candidates() -> list[Path]:
    out: list[Path] = []
    for top in ("factory-console", "factory-core", "factory-exec", "factory-org",
                "factory-runtime", "kernel", "services", "demo"):
        base = ROOT / top
        if not base.is_dir():
            continue
        for d in sorted(p for p in base.iterdir() if p.is_dir() and p.name != "__pycache__"):
            if any(d.rglob("*.py")):
                out.append(d)
    return out


def report(units: list[Path]) -> None:
    rows = []
    for u in units:
        r = check(u)
        if not r["files"]:
            continue
        cost = len(r["out"]) + len(r["in"])
        rows.append((cost, -r["lines"], u, r))
    rows.sort()
    print(f"{'出边':>4s} {'入边':>4s} {'文件':>5s} {'行数':>7s}  批次")
    print("-" * 84)
    for _cost, _nl, u, r in rows:
        nout, nin = len(r["out"]), len(r["in"])
        mark = "✓ 可搬（零改动）" if not (nout or nin) else ""
        print(f"{nout:4d} {nin:4d} {r['files']:5d} {r['lines']:7d}  "
              f"{str(u.relative_to(ROOT)):34s} {mark}")
        if r["out"]:
            print(f"{'':4s} {'':4s} {'':5s} {'':7s}    ├─ 出: "
                  + ", ".join(f"{k}×{len(v)}" for k, v in sorted(r["out"].items())[:4]))
        if r["in"]:
            print(f"{'':4s} {'':4s} {'':5s} {'':7s}    └─ 入: "
                  + ", ".join(f"{k}({len(v)})" for k, v in sorted(r["in"].items())[:4]))


if __name__ == "__main__":
    args = sys.argv[1:]
    units = [ROOT / a for a in args] if args else candidates()
    print("搬迁可分离性检查 —— 判据 = 批次外引用数（不是文件数）\n")
    report([u for u in units if u.is_dir()])
