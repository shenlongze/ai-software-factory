#!/usr/bin/env python3
"""生成项目树（排除缓存 / 依赖 / 构建产物）。

用法：
    python scripts/tree.py                 # 写入 docs/project-tree.md（默认）
    python scripts/tree.py <输出路径>       # 写入指定路径
    python scripts/tree.py -               # 打印到标准输出

为什么放进 scripts/：仓库根上原有一份手生的 project_tree.md（598KB，2026-09-12 生成），
既过期（不含 src/）又不可再生。树是「派生视图」，应当是工具产物，不是躺在根上的死文件。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "docs" / "project-tree.md"

#: 不进入树（缓存 / 依赖 / 构建产物 / VCS）
SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
        ".ruff_cache", ".mypy_cache", "build", "dist", "target", ".next",
        ".turbo", "htmlcov", ".DS_Store"}


def walk(directory: Path, prefix: str = "", out: list[str] | None = None) -> list[str]:
    out = [] if out is None else out
    try:
        entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except (PermissionError, FileNotFoundError):
        return out
    entries = [e for e in entries
               if e.name not in SKIP and not e.name.endswith((".pyc", ".pyo"))]
    for i, entry in enumerate(entries):
        last = i == len(entries) - 1
        out.append(f"{prefix}{'└── ' if last else '├── '}{entry.name}")
        if entry.is_dir():
            walk(entry, prefix + ("    " if last else "│   "), out)
    return out


def render() -> str:
    lines = [".", *walk(ROOT)]
    return "\n".join(lines) + "\n"


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_OUT)
    text = render()
    if arg in ("-", "--stdout"):
        sys.stdout.write(text)
        return 0
    target = Path(arg).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    try:
        shown: object = target.relative_to(ROOT)
    except ValueError:          # 仓库外路径（如 /tmp/x.md）也能写
        shown = target
    print(f"已写入 {shown}（{len(text.splitlines())} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
