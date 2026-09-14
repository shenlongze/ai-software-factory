#!/usr/bin/env python3
"""全量导入验证 —— 逐模块导入 src/ 下所有模块，报出失败项。

为什么需要它：搬迁/重构后，"能跑"不等于"没搬坏"。抽样验证会漏（刀31 的
providers bug 潜伏了 6 刀才被发现）。本脚本把【逐模块全量导入】固化为可重复动作。

用法:
    python scripts/check_imports.py            # 全部（新地基 + 隔离区）
    python scripts/check_imports.py --new      # 只验新地基 src/ai_factory_os
    python scripts/check_imports.py -q         # 只报汇总

退出码: 0 = 全部可导入；1 = 有失败（CI 可直接用）
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

#: (扫描目录, 模块名前缀) —— 与运行时 PYTHONPATH 一致
TREES = (
    (SRC / "ai_factory_os", "ai_factory_os"),
    (SRC / "legacy" / "factory-core", ""),
    (SRC / "legacy" / "factory-exec", ""),
    (SRC / "legacy" / "factory-console", "factory_console"),
)


def modules(tree: Path, prefix: str) -> list[str]:
    """目录 → 模块名列表（跳过 __init__ / __pycache__ / tests）。"""
    out: list[str] = []
    for p in tree.rglob("*.py"):
        if "__pycache__" in p.parts or p.name == "__init__.py":
            continue
        rel = p.relative_to(tree).with_suffix("")
        parts = rel.parts
        if "tests" in parts or "node_modules" in parts:
            continue
        name = ".".join((prefix, *parts)) if prefix else ".".join(parts)
        out.append(name)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", action="store_true", help="只验新地基")
    ap.add_argument("-q", "--quiet", action="store_true", help="只报汇总")
    args = ap.parse_args()

    # 与 bin/factory 的 PYTHONPATH 等价：src 必须排在最前（逆序插入）
    # ⚠ 注意用 factory-console（连字符目录）而非 src/legacy —— 后者会让转发壳
    #   src/legacy/factory_console/ 遮蔽真包，导致 false negative。
    for p in reversed((SRC, SRC / "legacy" / "factory-core",
                       SRC / "legacy" / "factory-console")):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    trees = TREES[:1] if args.new else TREES
    all_mods: list[str] = []
    for tree, prefix in trees:
        if tree.exists():
            all_mods.extend(modules(tree, prefix))
    uniq = sorted(set(all_mods))

    failed: list[tuple[str, str]] = []
    for name in uniq:
        try:
            importlib.import_module(name)
        except Exception as exc:                     # noqa: BLE001 — 逐个模块，必须全收
            failed.append((name, f"{type(exc).__name__}: {exc}"))

    if not args.quiet or failed:
        for name, err in failed:
            print(f"  ✗ {name}\n      {err}")
    print(f"导入验证: {len(uniq) - len(failed)}/{len(uniq)} 通过"
          f"{f'，{len(failed)} 失败' if failed else '，全绿 ✓'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
