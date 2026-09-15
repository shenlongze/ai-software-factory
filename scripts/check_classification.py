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


def _rel(p: Path) -> str:
    """相对仓库根的显示路径（不在仓库下时退回绝对路径 —— 不许崩）。"""
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


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
            out.append(f"{_rel(d)}: {len(pys)} 个 .py 平铺, {len(prefixes)} 种前缀")
    return sorted(out, key=lambda s: -int(re.search(r": (\d+)", s).group(1)))  # type: ignore[union-attr]


def rule_r23() -> list[str]:
    """命令登记: CLI 的命令必须全部登记在 api/cli/registry.py（★ 单一事实源）。

    为什么（Founder 2026-09-15 追问「cli 有分类么」）:
        现有 factory 入口 91 个命令**全部平铺在一个 10,155 行的文件里**, help 里
        那 4 个"域"只是 8600-8603 行的 dict（只为打印）—— 代码层零分类。
        新 CLI 的 handler 有命名前缀, 但物理上也是单文件、且前缀 ≠ 架构域。
        ⇒ 命令 → 域 的归属先落成注册表（api/cli/registry.py）, 本规则守住它:
        命令面一旦离开表（新增命令没登记 / 表里写了不存在的命令）→ 红。

    判据: 静态解析两套 CLI 的命令面, 与注册表比对。
      · 现有 factory 入口: cli_factory.py 的 `add_parser("xxx")`
      · 新 CLI: main.py 里**只挂在主 subparser** 上的 `add_parser`（子命令不参与）
    """
    sys.path.insert(0, str(SRC))
    try:
        from ai_factory_os.api.cli.registry import API_CLI, FACTORY_CLI
    except Exception as exc:  # noqa: BLE001 — 表本身坏了 = 最该报的一种红
        return [f"api/cli/registry.py 导入失败: {type(exc).__name__}: {exc}"]

    out: list[str] = []

    # ① 现有 factory 入口（只算真顶层 —— 接收者 = 主 subparser 容器的那些）
    #    注: 全文件 94 个 add_parser, 3 个是子命令（rag 的 query/index/sources,
    #    接收者 p_rag_sub）。★ 顶层有两种写法都要吃:
    #      p_x = sub.add_parser("x", ...)   /   sub.add_parser("x", ...)（无赋值）
    #      以及多行写法 sub.add_parser(\n  "x", ...)
    #    ⇒ 判据只能是**接收者名**, 不能要求有赋值/同一行。
    f_path = OS / "_pending_migration" / "factory_console" / "cli_factory.py"
    if f_path.is_file():
        t = f_path.read_text(encoding="utf-8", errors="replace")
        mf = re.search(r"(\w+)\s*=\s*p(?:arser)?\.add_subparsers\(", t)
        f_main = mf.group(1) if mf else "sub"
        real = set(re.findall(
            rf'(?<![\w.]){re.escape(f_main)}\.add_parser\(\s*["\']([a-z][a-z0-9-]*)["\']', t))
        reg = {c for v in FACTORY_CLI.values() for c in v}
        if real - reg:
            out.append(f"factory 入口: 未登记命令 {sorted(real - reg)}")
        if reg - real:
            out.append(f"factory 入口: 表里有但实际无 {sorted(reg - real)}")

    # ② 新 CLI（同上判据; ★ 扫描范围 = main.py + domains/*.py ——
    #    按域拆分后命令定义会逐步搬进 domains/, 守卫必须跟着走, 否则会误报"表里有但实际无"）
    a_dir = OS / "api" / "cli"
    dom_dir = a_dir / "domains"
    sources = [a_dir / "main.py"]
    if dom_dir.is_dir():
        sources += sorted(p for p in dom_dir.glob("*.py") if p.name != "__init__.py")
    real = set()
    for sp in sources:
        if not sp.is_file():
            continue
        t = sp.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"(\w+)\s*=\s*p\.add_subparsers\(", t)
        main_v = m.group(1) if m else "sub"
        real |= set(re.findall(
            rf'(?<![\w.]){re.escape(main_v)}\.add_parser\(\s*["\']([a-z][a-z0-9-]*)["\']', t))
    if sources and any(sp.is_file() for sp in sources):
        reg = {c for v in API_CLI.values() for c in v}
        if real - reg:
            out.append(f"新 CLI: 未登记顶层命令 {sorted(real - reg)}")
        if reg - real:
            out.append(f"新 CLI: 表里有但实际无 {sorted(reg - real)}")

    return out


RULES = {
    "R18": ("一能力一域　同一能力出现在 >1 个服务域", rule_r18),
    "R19": ("一物一名　同一实体两个名字", rule_r19),
    "R20": ("清单单一　SSoT 域清单 vs 实际目录", rule_r20),
    "R21": ("一域一落点　services 与 api/domains 同名同存", rule_r21),
    "R22": ("一层一目录　禁平铺", rule_r22),
    "R23": ("命令登记　CLI 命令必须在 api/cli/registry.py 有域归属", rule_r23),
}


def _mk_domains(root: Path, names: list[str]) -> None:
    for n in names:
        p = root / n
        p.mkdir(parents=True, exist_ok=True)
        (p / "__init__.py").write_text("", encoding="utf-8")


def _selftest() -> int:
    """守卫自检: 证明它会报红、不误报、不自己崩。

    为什么必须自检: 本脚本上线当天就出过两个【静默】bug ——
      R19 路径切分错 ⇒ 全仓 0 命中却"绿"（最坏的守卫是静默的守卫）;
      R22 硬用 relative_to(ROOT) ⇒ 扫描根一变就崩。
    故负例与正例都固化为可重复动作。
    """
    import tempfile

    global SSOT, OS, SRC  # noqa: PLW0603 — 自检需在假树上跑, finally 还原
    saved = SSOT, OS, SRC
    cases: list[tuple[str, bool]] = []
    try:
        tmp = Path(tempfile.mkdtemp())
        fake_os, fake_src = tmp / "ai_factory_os", tmp / "src"
        fake_os.mkdir()
        fake_src.mkdir()
        _mk_domains(fake_os / "contracts", ["a", "b", "c", "d"])   # d 多出来
        _mk_domains(fake_os / "services", ["a"])
        _mk_domains(fake_os / "api" / "domains", ["a"])
        SSOT = tmp / "architecture.md"
        SSOT.write_text(
            "## 二、域清单\n\n**契约域（`contracts/`，3）**\n\n`a` · `b` · `c`\n\n"
            "**服务域（`services/`，1）**\n\n`a`\n\n"
            "**API 分组（`api/domains/`，1）**\n\n`a`\n\n"
            "> 举例提到 `zzz` 不该被算作域\n", encoding="utf-8")
        OS, SRC = fake_os, fake_src

        r20 = rule_r20()
        cases.append(("R20 检出清单↔目录不一致", any("清单无" in x for x in r20)))
        cases.append(("R20 不受引用块举例污染", not any("zzz" in x for x in r20)))
        cases.append(("R21 一致时不误报", rule_r21() == []))
        _mk_domains(fake_os / "api" / "domains", ["b"])
        cases.append(("R21 检出跨层缺分组", rule_r21() != []))

        flat = fake_os / "flat"
        flat.mkdir()
        for i in range(FLAT_MIN_FILES + 5):
            (flat / f"mod{i}_x.py").write_text("", encoding="utf-8")
        cases.append(("R22 检出平铺且不崩", any("flat" in x for x in rule_r22())))
        small = fake_os / "small"
        small.mkdir()
        for i in range(5):
            (small / f"m{i}_x.py").write_text("", encoding="utf-8")
        cases.append(("R22 不误报小目录", not any("small" in x for x in rule_r22())))

        ad = fake_src / "adapter.py"
        ad.write_text('@app.get("/api/thing")\ndef a(): ...\n'
                      '@app.get("/api/things")\ndef b(): ...\n', encoding="utf-8")
        cases.append(("R19 检出单复数变体", any("thing" in x for x in rule_r19())))
        ad.write_text('@app.get("/api/only")\ndef a(): ...\n', encoding="utf-8")
        cases.append(("R19 不误报单一名", rule_r19() == []))
    finally:
        SSOT, OS, SRC = saved

    print("── 守卫自检（必须报红 · 不误报 · 不自己崩）")
    ok = sum(1 for _, c in cases if c)
    for n, c in cases:
        print(f"   [{'PASS' if c else 'FAIL'}] {n}")
    print(f"   {ok}/{len(cases)} 通过")
    return 0 if ok == len(cases) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="分类守卫 R18–R22")
    ap.add_argument("--rule", choices=sorted(RULES), action="append",
                    help="只查指定规则（可重复）")
    ap.add_argument("--selftest", action="store_true",
                    help="跑守卫自检（负例+正例），不扫仓库")
    ap.add_argument("-q", "--quiet", action="store_true", help="只报汇总")
    ap.add_argument("-v", "--verbose", action="store_true", help="明细不截断")
    ap.add_argument("--max", type=int, default=12, help="每条规则明细上限（default 12）")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

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
