#!/usr/bin/env python3
"""旧代码台账生成器 + 基线校验（只读扫描，不修改仓库代码）。

用法：
    python scripts/legacy_inventory.py            # 打印报告
    python scripts/legacy_inventory.py --write    # 写台账 md + 基线 json
    python scripts/legacy_inventory.py --check    # 对照基线，超基线则退出码 1

台账含两栏：
    规模（文件/行）        结构是否在增长
    可达性（活/测试/死）    哪些真死、哪些还连着线 —— 由 scripts/legacy_reach.py 提供

不计入围栏：scripts/（工具）、docs/、bin/、apps/、tests/、src/（新地基）。
"""
from __future__ import annotations

import ast
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from legacy_reach import LEGACY_ROOTS, ROOT, analyze as reach_analyze

SKIP = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
        "node_modules", "build", "dist", "target", ".mypy_cache"}
NEW = ROOT / "src" / "ai_factory_os"

# 人工判定（判据来源见 docs/cleanup/2026-09-11-* ；机器只负责复述）
VERDICTS: dict[str, tuple[str, str, str]] = {
    "factory-console": ("混合：新 OS 内核 + 旧会话链 + Web + API", "拆分 → services / core / api / apps", "待绞杀"),
    "factory-core": ("L4 旧数据层，24 包互引", "逐包复核后归档", "已判 132/138 可归档（实测待复核）"),
    "factory-exec": ("旧执行域（roles/skill/tool/provider/approval）", "同左，逐项判定", "已判 51/52 可归档（实测待复核）"),
    "factory-org": ("组织领域模型（最完整）", "services/organization", "待绞杀"),
    "factory-runtime": ("旧 runtime bundle", "core/node 或 infrastructure", "待判定"),
    "factory_console": ("打包胶水（连字符目录名的转发层）", "保留", "合法，非冗余"),
    "kernel": ("v0.2 遗留契约（大部分已删，剩 governance/patch_filter）", "删除 / 迁入新地基", "绞杀中"),
    "services": ("绞杀示范 approval_runtime", "src/…/services", "示范保留"),
    "demo": ("演示代码", "archive", "待处理"),
}

BASELINE = ROOT / "tests" / "architecture" / "legacy_baseline.json"
LEDGER = ROOT / "docs" / "cleanup" / "LEGACY-LEDGER.md"


def legacy_files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*.py"):
        if any(s in p.parts for s in SKIP) or "tests" in p.parts or NEW in p.parents:
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
        for mod in imports_of(f):
            for target in by_root:
                if mod in (target, target.replace("-", "_")) and src != target:
                    edges[(src, target)] += 1
    return {
        "files": sorted(str(f.relative_to(ROOT)) for f in files),
        "lines": sum(line_counts.values()),
        "by_root": {r: (len(fs), sum(line_counts[f] for f in fs)) for r, fs in sorted(by_root.items())},
        "edges": {f"{a}->{b}": n for (a, b), n in sorted(edges.items())},
    }


def report(data: dict, reach: dict) -> str:
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
        "| 分区 | 文件 | 行数 | 活 | 仅测试 | 未证实 | 定性 | 目标 | 状态 |",
        "|---|---:|---:|---:|---:|---:|---|---|---|",
    ]
    by_root_reach = reach["by_root"]
    for name, (count, line_count) in data["by_root"].items():
        verdict, target, status = VERDICTS.get(name, ("—", "—", "—"))
        r = by_root_reach.get(name, {"live": 0, "test_only": 0, "unverified": 0})
        out.append(f"| `{name}` | {count} | {line_count} | {r['live']} | {r['test_only']} | "
                   f"{r['unverified']} | {verdict} | {target} | {status} |")
    t = reach["totals"]
    out += [
        f"| **合计** | **{len(data['files'])}** | **{data['lines']}** | "
        f"**{reach['live']['files']}** | **{reach['test_only']['files']}** | "
        f"**{reach['unverified']['files']}** | | | |",
        "",
        "## 二、可达性（从活入口 BFS import 图）",
        "",
        "> ⚠️ **本栏不产出「可删」结论。** 静态可达性无法证明代码是死的 ——",
        "> 项目存在多种静态解析不到的加载方式（字符串动态加载、拼接式加载、经本地辅助函数转发）。",
        "> 第三类一律标「未证实」，需人工确认后才可考虑处置。",
        "",
        f"入口：{', '.join('`' + e + '`' for e in reach['entries'])}",
        "",
        "| 类别 | 文件 | 行数 | 含义 |",
        "|---|---:|---:|---|",
        f"| 可达 | {reach['live']['files']} | {reach['live']['lines']} | 生产入口能走到（主链） |",
        f"| 仅测试可达 | {reach['test_only']['files']} | {reach['test_only']['lines']} | 只有测试能走到 |",
        f"| 未证实使用 | {reach['unverified']['files']} | {reach['unverified']['lines']} | 静态走不到 —— **不得当作可删** |",
        f"| **合计** | **{t['files']}** | **{t['lines']}** | |",
        "",
        f"> 其中 **{reach['unverified_shadowed']['files']} 文件 / "
        f"{reach['unverified_shadowed']['lines']} 行**受已知动态加载前缀影响"
        f"（前缀 {', '.join('`' + p + '`' for p in reach['dynamic_prefixes']) or '无'}），"
        "**尤其不可当作可删**。",
        f"> 动态调用 {reach['dynamic_calls']} 处；未解析字面量 {len(reach['unresolved_dynamic'])} 条。",
        "",
        "## 三、跨分区依赖边（只减不增）",
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
        "## 四、说明",
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

    reach = reach_analyze()
    if "--write" in args:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                            encoding="utf-8")
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(report(data, reach), encoding="utf-8")
        print(f"已写 {BASELINE.relative_to(ROOT)}")
        print(f"已写 {LEDGER.relative_to(ROOT)}")
        print(f"基线: {len(data['files'])} 文件 / {data['lines']} 行 / {len(data['edges'])} 条边")
        print(f"可达性: 活 {reach['live']['files']} / 仅测试 {reach['test_only']['files']} / "
              f"未证实 {reach['unverified']['files']}")
        return 0
    print(report(data, reach))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
