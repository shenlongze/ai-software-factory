#!/usr/bin/env python3
"""分类守卫（R18–R22）—— Founder: "代码必须严格分类，严格管理，不能东一个西一个"。

为什么需要它：
    R1–R17 原由 tests/architecture/*.py 强制，但 tests/ 已不存在（刀29 清理）
    ⇒ 铁律实为"目标态"，现役零强制。本脚本是分类铁律（R18–R22）的第一台
    机器强制，建在 scripts/（与现役载体 check_imports / migration_check 一致）。

    Founder 原话的落点:
      · R18–R21 = "严格分类"      · R22 = "不放在一起，乱"

规则：
    R18 一能力一域    同一能力文件名出现在 >1 个服务域 → 红
    R19 一物一名      API 路径第一段按词根/同义词聚类，一族 >1 组 → 红
    R20 清单单一      SSoT §二 域清单 vs contracts/ services/ api/domains/ 实际目录
    R21 一域一落点    services/<域>/ 与 api/domains/<域>/ 同名同存
    R22 一层一目录    同目录 >30 个 .py 且前缀 ≥20 种 → 红（平铺）

用法：
    python scripts/check_classification.py              # 五条全查
    python scripts/check_classification.py --rule R22   # 只查一条
    python scripts/check_classification.py -q           # 只报汇总
    python scripts/check_classification.py -v           # 明细不截断

退出码: 0 = 全绿；1 = 有红（CI 可直接用）；2 = 用法错误
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OS = SRC / "ai_factory_os"
SSOT = ROOT / "docs" / "ssot" / "architecture.md"
LEGACY_ADAPTER = (OS / "_pending_migration" / "factory_console" / "web"
                  / "backend" / "fastapi_adapter.py")

SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
             "build", "dist", "node_modules", ".mypy_cache", "htmlcov"}

#: R18 排除的"按域同名"通用名 —— 每域一套是【结构统一】该有的样子, 不算重复
GENERIC_NAMES = {
    "__init__", "service", "store", "rules", "events", "contracts",
    "types", "router", "schemas", "models", "repositories", "ports",
}

#: R22 平铺阈值
FLAT_MIN_FILES = 30
FLAT_MIN_PREFIXES = 20

#: R19 形态变体后缀（去后缀后同名 = 同一实体）
VARIANT_SUFFIX = re.compile(
    r"-(os|truth|sessions|requests|gates|runs|profiles|incidents|feedback|"
    r"conflicts|samples|trees|detail|details|list)$"
)

#: R19 语义同义组（名字完全不同, 词根法抓不到 —— 显式登记, 可维护）
SYNONYM_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"conversations", "sessions"}),        # 会话
    frozenset({"workflows", "board"}),               # 编排
    frozenset({"production-runs", "runs"}),          # 运行
    frozenset({"learning", "intelligence"}),         # 学习
    frozenset({"incidents", "health-incidents"}),    # 事件
    frozenset({"ops", "operations"}),                # 运维
)


def _py_files(d: Path) -> list[Path]:
    return [f for f in d.rglob("*.py") if not any(p in SKIP_DIRS for p in f.parts)]


def _subdirs(d: Path) -> list[str]:
    if not d.is_dir():
        return []
    return sorted(x.name for x in d.iterdir()
                  if x.is_dir() and x.name not in SKIP_DIRS)


def _domain_dirs(d: Path) -> list[str]:
    """只取"域"目录（含 __init__.py 的包）。"""
    return [x.name for x in sorted(d.iterdir())
            if x.is_dir() and x.name not in SKIP_DIRS and (x / "__init__.py").is_file()]


def ssot_domain_lists() -> dict[str, list[str]]:
    """解析 SSoT §二 的三份域清单（单一事实源）。

    三份必须都从 SSoT 读 —— 不许在脚本里另抄一份（抄了就会漂移，刀22 踩过）。
    """
    if not SSOT.is_file():
        return {}
    text = SSOT.read_text(encoding="utf-8")
    out: dict[str, list[str]] = {}
    for label, marker in (("contracts", "**契约域（"),
                          ("services", "**服务域（"),
                          ("api/domains", "**API 分组（")):
        i = text.find(marker)
        if i < 0:
            continue
        seg = text[i:]
        ends = [x for x in (seg.find("\n**", 5), seg.find("\n##", 5)) if x > 0]
        body = seg[: min(ends)] if ends else seg
        # 去掉引用块（> 开头）—— 里面常举例提到别的域名，会污染清单
        body = "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith(">"))
        out[label] = re.findall(r"`([a-z_]+)`", body)
    return out


# ---------------------------------------------------------------- 规则实现

def rule_r18() -> list[str]:
    """一能力一域: 同一能力文件名出现在 >1 个服务域。"""
    services = OS / "services"
    by_name: dict[str, list[str]] = defaultdict(list)
    for f in _py_files(services):
        stem = f.stem
        if stem in GENERIC_NAMES:
            continue
        rel = f.relative_to(services)
        if len(rel.parts) < 2:
            continue
        by_name[stem].append(str(rel))
    return [f"{n}: " + " · ".join(sorted(v)) for n, v in sorted(by_name.items())
            if len({p.split("/")[0] for p in v}) > 1]


def _endpoint_groups() -> dict[str, int]:
    """扫全仓端点, 按 /api/<第一段> 归类计数。"""
    cnt: dict[str, int] = defaultdict(int)
    pat = re.compile(r"""@(?:app|router)\.(?:get|post|put|delete|patch)\(\s*["'](/api|/)([^"']*)""")
    for f in _py_files(SRC):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "@app." not in text and "@router." not in text:
            continue
        for m in pat.finditer(text):
            if m.group(1) != "/api":
                continue
            seg = m.group(2).lstrip("/").split("/")
            if seg and seg[0]:
                cnt[seg[0]] += 1
    # APIRouter(prefix="/api/<seg>")
    pre = re.compile(r"""APIRouter\([^)]*prefix\s*=\s*["']/api/([^"']+)["']""")
    for f in _py_files(OS / "api"):
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in pre.finditer(text):
            seg = m.group(1).split("/")[0]
            if seg and seg not in cnt:
                cnt[seg] = 0
    return dict(cnt)


def _root_of(g: str) -> str:
    r = VARIANT_SUFFIX.sub("", g)
    return re.sub(r"s$", "", r)


def rule_r19() -> list[str]:
    """一物一名: 同一实体两个名字。

    数据源两类，输出里区分:
      · 老区在跑的端点（有计数）
      · 新地基空壳 router 的 prefix（无端点，标"空壳"）—— 只用于暴露"目标名 vs 现名"不一致
    """
    cnt = _endpoint_groups()
    fam: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for g, n in cnt.items():
        fam[_root_of(g)].append((g, n))

    def show(g: str, n: int) -> str:
        return f"{g} {n}" if n else f"{g}(空壳)"

    out: list[str] = []
    for k, v in sorted(fam.items(), key=lambda x: -sum(n for _, n in x[1])):
        if len(v) > 1:
            out.append(f"{k}: " + " · ".join(show(g, n) for g, n in sorted(v, key=lambda x: -x[1])))
    for group in SYNONYM_FAMILIES:
        present = sorted(g for g in group if g in cnt)
        if len(present) > 1:
            out.append("同义: " + " · ".join(show(g, cnt[g]) for g in present))
    return out


def rule_r20() -> list[str]:
    """清单单一: SSoT 三份清单 vs 代码实际目录（各层各比各的）。"""
    want = ssot_domain_lists()
    if not want:
        return ["SSoT §二 三份域清单解析失败（文件或格式变了）"]
    out: list[str] = []
    dirs = {"contracts": OS / "contracts",
            "services": OS / "services",
            "api/domains": OS / "api" / "domains"}
    for label, d in dirs.items():
        wl = want.get(label)
        if wl is None:
            out.append(f"{label}: SSoT 未定义该层清单")
            continue
        have = set(_domain_dirs(d))
        missing = sorted(set(wl) - have)
        extra = sorted(have - set(wl))
        if missing:
            out.append(f"{label}: 清单有但目录无 {missing}")
        if extra:
            out.append(f"{label}: 目录有但清单无 {extra}")
    return out


def rule_r21() -> list[str]:
    """一域一落点: services/<域>/ 与 api/domains/<域>/ 同名同存。"""
    svc = set(_domain_dirs(OS / "services"))
    api = set(_domain_dirs(OS / "api" / "domains"))
    out: list[str] = []
    if svc - api:
        out.append(f"有服务域无 API 分组 {sorted(svc - api)}")
    if api - svc:
        out.append(f"有 API 分组无服务域 {sorted(api - svc)}")
    return out


def rule_r22() -> list[str]:
    """一层一目录（禁平铺）。"""
    out: list[str] = []
    for d in [OS, *(x for x in OS.rglob("*") if x.is_dir())]:
        if any(p in SKIP_DIRS for p in d.parts):
            continue
        pys = [f for f in d.glob("*.py") if f.name != "__init__.py"]
        if len(pys) <= FLAT_MIN_FILES:
            continue
        prefixes = {f.stem.split("_")[0] for f in pys}
        if len(prefixes) >= FLAT_MIN_PREFIXES:
            out.append(f"{d.relative_to(ROOT)}: {len(pys)} 个 .py 平铺, {len(prefixes)} 种前缀")
    return sorted(out, key=lambda s: -int(re.search(r": (\d+)", s).group(1)))  # type: ignore[union-attr]


RULES = {
    "R18": ("一能力一域　同一能力出现在 >1 个服务域", rule_r18),
    "R19": ("一物一名　同一实体两个名字", rule_r19),
    "R20": ("清单单一　SSoT 域清单 vs 实际目录", rule_r20),
    "R21": ("一域一落点　services 与 api/domains 同名同存", rule_r21),
    "R22": ("一层一目录　禁平铺", rule_r22),
}


def main() -> int:
    ap = argparse.ArgumentParser(description="分类守卫 R18–R22")
    ap.add_argument("--rule", choices=sorted(RULES), action="append",
                    help="只查指定规则（可重复）")
    ap.add_argument("-q", "--quiet", action="store_true", help="只报汇总")
    ap.add_argument("-v", "--verbose", action="store_true", help="明细不截断")
    ap.add_argument("--max", type=int, default=12, help="每条规则明细上限（default 12）")
    args = ap.parse_args()

    todo = args.rule or sorted(RULES)
    red = 0
    for r in todo:
        label, fn = RULES[r]
        items = fn()
        mark = "红" if items else "绿"
        if items:
            red += 1
        if not args.quiet:
            print(f"[{mark}] {r} {label}　({len(items)} 项)")
            shown = items if args.verbose else items[: args.max]
            for it in shown:
                print(f"       · {it}")
            if len(items) > len(shown):
                print(f"       … 另有 {len(items) - len(shown)} 项（-v 看全部）")
    passed = len(todo) - red
    verdict = "全绿" if not red else "有红"
    print(f"\n汇总: {passed}/{len(todo)} 条规则通过（{verdict}）—— "
          f"Founder: \"代码必须严格分类，严格管理，不能东一个西一个\"")
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
