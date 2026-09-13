#!/usr/bin/env python3
"""旧代码台账生成器 + 基线校验（只读扫描，不修改仓库代码）。

用法：
    python scripts/legacy_inventory.py            # 打印报告
    python scripts/legacy_inventory.py --write    # 写台账 md + 基线 json
    python scripts/legacy_inventory.py --check    # 对照基线，超基线则退出码 1

被绞杀对象（旧代码分区）：见 LEGACY_ROOTS。
不计入围栏：scripts/（工具）、docs/、bin/、apps/、tests/、src/（新地基）。
"""
from __future__ import annotations

import ast
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
        "node_modules", "build", "dist", "target", ".mypy_cache"}
NEW = ROOT / "src" / "ai_factory_os"

LEGACY_ROOTS = ("demo", "factory-console", "factory-core", "factory-exec",
                "factory-org", "factory-runtime", "factory_console", "kernel", "services")

# 人工判定（判据来自 docs/cleanup/2026-09-11-*，机器只负责复述）
VERDICTS: dict[str, tuple[str, str, str]] = {
    "factory-console": ("混合：新 OS 内核 + 旧会话链 + Web + API", "拆分 → services / core / api / apps", "待绞杀"),
    "factory-core": ("L4 旧数据层，24 包互引", "逐包复核后归档", "已判 132/138 可归档"),
    "factory-exec": ("旧执行域（roles/skill/tool/provider/approval）", "同左，逐项判定", "已判 51/52 可归档"),
    "factory-org": ("组织领域模型（最完整）", "services/organization", "待绞杀"),
    "factory-runtime": ("旧 runtime bundle", "core/node 或 infrastructure", "待判定"),
    "factory_console": ("打包胶水（连字符目录名的转发层）", "保留", "合法，非冗余"),
    "kernel": ("v0.2 遗留契约（契约已并入 src/…/contracts）", "删除", "待删"),
    "services": ("绞杀示范 approval_runtime", "src/…/services", "示范保留"),
    "demo": ("演示代码", "archive", "待处理"),
}

BASELINE = ROOT / "tests" / "architecture" / "legacy_baseline.json"
LEDGER = ROOT / "docs" / "cleanup" / "LEGACY-LEDGER.md"


def legacy_files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*.py"):
        if any(s in p.parts for s in SKIP) or "tests" in p.parts:
            continue
        if NEW in p.parents:
            continue
        if p.relative_to(ROOT).parts[0] in LEGACY_ROOTS:
            out.append(p)
    return sorted(out)


def imports_of(path: Path) -> set[str]:
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


def scan() -> dict:
    files = legacy_files()
    by_root: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        by_root[f.relative_to(ROOT).parts[0]].append(f)
    line_counts = {f: len(f.read_text(encoding="utf-8", errors="replace").splitlines()) for f in files}
    edges: Counter = Counter()
    for f in files:
        src = f.relative_to(ROOT).parts[0]
        for m in imports_of(f):
            for target in by_root:
                if m in (target, target.replace("-", "_")) and src != target:
                    edges[(src, target)] += 1
    return {
        "files": sorted(str(f.relative_to(ROOT)) for f in files),
        "lines": sum(line_counts.values()),
        "by_root": {r: (len(fs), sum(line_counts[f] for f in fs)) for r, fs in sorted(by_root.items())},
        "edges": {f"{a}->{b}": n for (a, b), n in sorted(edges.items())},
    }


def report(data: dict) -> str:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = [
        "<!-- AUTO-GENERATED: DO NOT EDIT -->",
        "<!-- 由 scripts/legacy_inventory.py --write 生成；派生视图，非事实源 -->",
        "",
        "# 旧代码台账（LEGACY LEDGER）",
        "",
        f"> 生成时间: {stamp} | 生成器: `scripts/legacy_inventory.py`",
        "> 规则：**只减不增** —— 由 `tests/architecture/test_legacy_fence.py` 强制",
        "",
        "## 一、分区总览",
        "",
        "| 分区 | 文件 | 行数 | 定性 | 目标 | 状态 |",
        "|---|---:|---:|---|---|---|",
    ]
    for name, (count, line_count) in data["by_root"].items():
        verdict, target, status = VERDICTS.get(name, ("—", "—", "—"))
        out.append(f"| `{name}` | {count} | {line_count} | {verdict} | {target} | {status} |")
    out += [
        f"| **合计** | **{len(data['files'])}** | **{data['lines']}** | | | |",
        "",
        "## 二、跨分区依赖边（只减不增）",
        "",
    ]
    if data["edges"]:
        out += ["| 从 | 到 | 次数 |", "|---|---|---:|"]
        for key, count in data["edges"].items():
            src, dst = key.split("->")
            out.append(f"| `{src}` | `{dst}` | {count} |")
    else:
        out.append("（无）")
    out += [
        "",
        "## 三、说明",
        "",
        "- 被绞杀对象：`" + "`, `".join(LEGACY_ROOTS) + "`",
        "- 不计入围栏：`scripts/`（工具）、`docs/`、`bin/`、`apps/`、`tests/`、`src/`（新地基）",
        "- 本台账是**派生视图**，不属 SSoT；手写修改将在下次生成时被覆盖。",
        "",
    ]
    return "\n".join(out)


def main() -> int:
    args = sys.argv[1:]
    data = scan()
    if "--write" in args:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                            encoding="utf-8")
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(report(data), encoding="utf-8")
        print(f"已写 {BASELINE.relative_to(ROOT)}")
        print(f"已写 {LEDGER.relative_to(ROOT)}")
        print(f"基线: {len(data['files'])} 文件 / {data['lines']} 行 / {len(data['edges'])} 条边")
        return 0
    if "--check" in args:
        base = json.loads(BASELINE.read_text(encoding="utf-8"))
        added = sorted(set(data["files"]) - set(base["files"]))
        grew = data["lines"] > base["lines"]
        new_edges = {k: v for k, v in data["edges"].items() if v > base["edges"].get(k, 0)}
        print(f"文件: {len(data['files'])} (基线 {len(base['files'])})")
        print(f"行数: {data['lines']} (基线 {base['lines']})")
        for f in added:
            print(f"  新增文件: {f}")
        for k, v in new_edges.items():
            print(f"  边增长: {k} {base['edges'].get(k, 0)} -> {v}")
        print(f"超基线: {'是' if (added or grew or new_edges) else '否'}")
        return 1 if (added or grew or new_edges) else 0
    print(report(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
