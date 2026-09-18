#!/usr/bin/env python3
"""架构守卫（R1–R17）—— 层级依赖 + 旧代码围栏。

为什么需要它：
    SSoT §三 称 R1–R17"全部机器强制"，但强制载体 `tests/architecture/*.py` 已不存在
    （刀29 清理）⇒ 这些铁律实际是"目标态"，一年没有载体。本脚本把它们重建在
    scripts/（与 R18–R22 的守卫同位），并**实测**当前违规数。

分层（SSoT §一）：
    contracts/  全部跨层契约（无逻辑无 IO）        → 仅标准库
    core/       平台本体（scheduler + events）      → contracts
    services/   业务域用例（唯一业务入口）           → contracts
    plugins/    一切实现绑定                        → contracts
    infrastructure/ 技术底座                        → contracts
    api/        对外接口层                          → contracts + services
    bootstrap/  装配与启动（唯一可 import 全部）      → 全部

规则：
    R1  contracts 不许 import 其他层      R2  core 只许 import contracts
    R3  services 不许跨域 import          R4  plugins 只许 import contracts
    R5  infrastructure 只许 import contracts   R6  api 不许 import infrastructure
    R9  contracts 不许含控制流            R10 禁用文件名
    R11 services/<域>/ 文件 ⊆ 五件套      R12 core 无业务词 + ≤3000 行
    R13 新地基不许 import 旧区            R16 不许新增顶层目录
    R17 core 只允许 scheduler / events
    R7  apps/ 不许出现在 src/ 内           R8  bootstrap 例外（不查）
    R14/R15 旧区只减不增（需基线文件，未建则如实报"无基线"）

用法：
    python scripts/check_architecture.py              # 全部
    python scripts/check_architecture.py --rule R3    # 单条（可重复）
    python scripts/check_architecture.py -v           # 明细不截断
    python scripts/check_architecture.py --selftest   # 只跑解析器自检
退出码: 0 = 全绿；1 = 有红；2 = 用法错误
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
OS = ROOT / "src" / "ai_factory_os"

LAYERS = ("contracts", "core", "services", "plugins", "infrastructure", "api", "bootstrap")
LEGACY = ""  # ★ 2026-09-15: 旧区(_pending_migration)已整体删除 ⇒ 该层不再存在
SKIP = {"__pycache__"}

#: R10 SSoT 只列全了 3 个（"11 个"未列全）→ 如实标注，不装作查全
BANNED_NAMES = {"models.py", "utils.py", "common.py"}

#: R11 services/<域>/ 允许的文件名（五件套 + 契约/类型/入口）
FIVE_PIECE = {"service", "store", "rules", "events", "contracts", "types", "__init__"}

#: R16 允许的顶层目录
ALLOWED_TOP = set(LAYERS) | {"compat_aliases.py"}

#: R12 core 的业务词（"order" 不列 —— rank.py 里是排序顺序, 歧义太大）
BIZ_WORDS = re.compile(
    r"\b(project|product|employee|agent|task|customer|invoice|"
    r"workforce|organization|approval|budget)\b", re.I)

CORE_MAX_LINES = 3000
CORE_SUBMODULES = {"scheduler", "events"}


# ------------------------------------------------------------------ 解析

class Module:
    """一个 .py 文件 → (相对路径, 模块全名, 是否包, 层, 域, AST)。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.rel = str(path.relative_to(OS))
        is_pkg = path.name == "__init__.py"
        stem = self.rel[:-3].replace("/", ".")
        if is_pkg:
            stem = stem[: -len(".__init__")]
        self.mod = "ai_factory_os." + stem
        self.is_pkg = is_pkg
        parts = self.rel.split("/")
        self.layer: str | None = parts[0] if parts[0] in LAYERS else (
            None)
        self.domain: str | None = parts[1] if self.layer == "services" and len(parts) > 1 else None
        try:
            self.tree: ast.Module | None = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            self.tree = None

    def imports(self) -> list[tuple[str, int]]:
        """(目标模块, 行号)。含相对导入与函数内 lazy import（ast.walk 全覆盖）。"""
        if self.tree is None:
            return []
        out: list[tuple[str, int]] = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                out += [(a.name, node.lineno) for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                t = self._resolve(node)
                if t:
                    out.append((t, node.lineno))
        return out

    def _resolve(self, node: ast.ImportFrom) -> str | None:
        """相对导入 → 绝对模块名。

        ★ 关键: 包(__init__.py)的"当前包"是它自己, 普通模块是父级。
           level=1 → 当前包;  第 k 级 = 去掉 (level-1) 段后再去掉文件名段。
           （本函数曾算错, 把 contracts/resource 的 `from ..governance` 解析成
             不存在的顶层 ai_factory_os.governance ⇒ 假红。故 --selftest 覆盖它。）
        """
        if node.level == 0:
            return node.module
        parts = self.mod.split(".")
        drop = node.level - (1 if self.is_pkg else 0)
        base = parts[: len(parts) - drop] if drop > 0 else parts
        if node.module:
            base = base + node.module.split(".")
        return ".".join(base)


def target_layer(mod: str) -> str | None:
    p = mod.split(".")
    if not p or p[0] != "ai_factory_os":
        return None
    if len(p) < 2:
        return "_root"
    return p[1] if p[1] in LAYERS else "_other"


def target_domain(mod: str) -> str | None:
    p = mod.split(".")
    return p[2] if len(p) > 2 and p[1] == "services" else None


def modules() -> list[Module]:
    return [Module(f) for f in sorted(OS.rglob("*.py")) if not any(x in SKIP for x in f.parts)]


# ------------------------------------------------------------------ 规则

def _layer_edges(mods: list[Module]) -> list[tuple[Module, str, str, int]]:
    """(源, 目标层, 目标模块, 行号)，已排除同层自引。"""
    out = []
    for m in mods:
        if m.layer is None or m.layer == "bootstrap":       # R8 例外
            continue
        for tgt, ln in m.imports():
            tl = target_layer(tgt)
            if tl is None or tl == "_root":
                continue
            if tl == m.layer and target_domain(tgt) in (None, m.domain):
                continue                                    # 同层同域 = 合规
            out.append((m, tl, tgt, ln))
    return out


def rule_r1(mods, edges):
    return [f"{m.rel}:{ln} → {t}" for m, tl, t, ln in edges
            if m.layer == "contracts" and tl != "contracts"]


def rule_r2(mods, edges):
    return [f"{m.rel}:{ln} → {t}" for m, tl, t, ln in edges
            if m.layer == "core" and tl != "contracts"]


def rule_r3(mods, edges):
    return [f"{m.rel}:{ln} → {t}" for m, tl, t, ln in edges
            if m.layer == "services" and tl == "services"
            and target_domain(t) not in (None, m.domain)]


def rule_r4(mods, edges):
    return [f"{m.rel}:{ln} → {t}" for m, tl, t, ln in edges
            if m.layer == "plugins" and tl != "contracts"]


def rule_r5(mods, edges):
    return [f"{m.rel}:{ln} → {t}" for m, tl, t, ln in edges
            if m.layer == "infrastructure" and tl != "contracts"]


def rule_r6(mods, edges):
    return [f"{m.rel}:{ln} → {t}" for m, tl, t, ln in edges
            if m.layer == "api" and tl == "infrastructure"]


def rule_r7(mods, edges):
    """apps 类（cli/web/desktop/mobile）必须独立于 src/（SSoT §一）。

    ★ 2026-09-15 修（Founder: "你代码落地位置的问题不是错一次了"）:
      原实现只查 **src/ 的直接子目录** —— 于是 `src/ai_factory_os/api/cli/` 这种
      深层嵌套完全扫不到, CLI 就这样在 src 里住了很久, 直到 Founder 追问"位置对么"
      才查出它违反 SSoT §一。**规矩在, 守卫查的是字面而不是实质。**
      ⇒ 改为**递归**查任意深度的 cli/web/desktop/mobile 目录。
    豁免: `_pending_migration/**` —— 老区整块待绞杀, 其存量由 R14/R15 管,
      不在这里重复报（否则真·消费者和待迁老区混成一片, 报红失去指向性）。
    """
    bad = []
    for p in (ROOT / "src").rglob("*"):
        if not p.is_dir() or p.name not in ("cli", "web", "desktop", "mobile"):
            continue
        if "__pycache__" in p.parts:
            continue
        bad.append(p)
    return [f"{p.relative_to(ROOT)}/ 在 src/ 内（apps 类必须独立于 src/ — SSoT §一）"
            for p in sorted(bad)]


def rule_r9(mods, edges):
    """contracts 不许含控制流。"""
    ctrl = (ast.If, ast.For, ast.While, ast.Try, ast.With)
    out = []
    for m in mods:
        if m.layer != "contracts" or m.tree is None:
            continue
        for node in ast.walk(m.tree):
            if isinstance(node, ctrl):
                out.append(f"{m.rel}:{getattr(node, 'lineno', '?')} 含 {type(node).__name__}")
    return out


def rule_r10(mods, edges):
    extra = ""
    if len(BANNED_NAMES) < 11:
        extra = f"（SSoT 只列全 {len(BANNED_NAMES)}/11 个，未列全部分未查）"
    hits = [f"{m.rel}{extra}" for m in mods if m.path.name in BANNED_NAMES]
    return hits


def rule_r11(mods, edges):
    """R11: services/<域>/ 内文件 ⊆ 五件套。

    按字面判: 只看【域目录下的直接子文件】; 子目录（analyzers/ runtime/ kernel/ …）
    不在 R11 射程内 —— 那是"域内再分包", 归 R18（一能力一域）管。
    """
    out = []
    for m in mods:
        if m.layer != "services" or m.domain is None:
            continue
        parts = m.rel.split("/")
        if len(parts) != 3 or not m.path.is_file():        # 只看直接子文件
            continue
        if m.path.stem not in FIVE_PIECE:
            out.append(f"{m.rel}（非五件套：{m.path.stem}）")
    return out


def rule_r12(mods, edges):
    out = []
    total = 0
    for m in mods:
        if m.layer != "core":
            continue
        total += len(m.path.read_text(encoding="utf-8", errors="replace").splitlines())
        if m.tree is None:
            continue
        for node in ast.walk(m.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if BIZ_WORDS.search(node.name):
                    out.append(f"{m.rel}:{node.lineno} 业务词 {node.name}")
    if total > CORE_MAX_LINES:
        out.append(f"core/ 总行数 {total} > {CORE_MAX_LINES}")
    return out


def rule_r13(mods, edges):
    return [f"{m.rel}:{ln} → {t}" for m, tl, t, ln in edges if tl == LEGACY]


def rule_r14(mods, edges):
    base = ROOT / "scripts" / "legacy_baseline.json"
    if not base.is_file():
        return [f"无基线文件 {base.relative_to(ROOT)}（旧区只减不增无法判定 —— 需先建基线）"]
    return []


def rule_r15(mods, edges):
    return []          # 同 R14：依赖边基线未建


def rule_r16(mods, edges):
    have = {p.name for p in OS.iterdir()
            if not p.name.startswith(".") and p.name not in ("__pycache__", "__init__.py")}
    extra = sorted(have - ALLOWED_TOP)
    return [f"新增顶层目录/文件 {extra}"] if extra else []


def rule_r17(mods, edges):
    core = OS / "core"
    subs = sorted(p.name for p in core.iterdir()
                  if p.is_dir() and not p.name.startswith("__"))
    extra = [s for s in subs if s not in CORE_SUBMODULES]
    return [f"core/ 出现非 scheduler/events 子模块 {extra}"] if extra else []


Rule = Callable[[list["Module"], list[tuple]], list[str]]

RULES: dict[str, tuple[str, Rule]] = {
    "R1": ("contracts 不许 import 其他层", rule_r1),
    "R2": ("core 只许 import contracts", rule_r2),
    "R3": ("services 不许跨域 import", rule_r3),
    "R4": ("plugins 只许 import contracts", rule_r4),
    "R5": ("infrastructure 只许 import contracts", rule_r5),
    "R6": ("api 不许 import infrastructure", rule_r6),
    "R7": ("apps/ 不许出现在 src/ 内", rule_r7),
    "R9": ("contracts 不许含控制流", rule_r9),
    "R10": ("禁用文件名", rule_r10),
    "R11": ("services/<域>/ ⊆ 五件套", rule_r11),
    "R12": ("core 无业务词 + ≤3000 行", rule_r12),
    "R13": ("新地基不许 import 旧区", rule_r13),
    "R14": ("旧区文件只减不增", rule_r14),
    "R16": ("不许新增顶层目录", rule_r16),
    "R17": ("core 只允许 scheduler/events", rule_r17),
}


# ------------------------------------------------------------------ 自检

def _ifrom(src: str) -> ast.ImportFrom:
    """一句话源码 → ImportFrom 节点（自检用）。"""
    node = ast.parse(src).body[0]
    assert isinstance(node, ast.ImportFrom)
    return node


def _selftest() -> int:
    """解析器自检 —— 相对导入是守卫的地基, 它错了全盘皆错（且看起来很安静）。"""
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    pkg = tmp / "pkg"
    (pkg / "sub").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "sub" / "__init__.py").write_text("", encoding="utf-8")
    modf = pkg / "sub" / "mod.py"
    modf.write_text("", encoding="utf-8")

    global OS                              # noqa: PLW0603 — 自检临时改, finally 还原
    saved = OS
    cases: list[tuple[str, bool, str]] = []

    def chk(name: str, got: str | None, want: str) -> None:
        cases.append((name, got == want, f"得到 {got!r}, 期望 {want!r}"))

    try:
        OS = tmp
        # 包(__init__.py）: level=1 → 自己; level=2 → 父包
        m = Module(pkg / "sub" / "__init__.py")
        m.mod = "ai_factory_os.contracts.resource"
        chk("包 level=1 → 当前包", m._resolve(_ifrom("from .x import A")),
            "ai_factory_os.contracts.resource.x")
        chk("包 level=2 → 父包+模块", m._resolve(_ifrom("from ..governance import A")),
            "ai_factory_os.contracts.governance")
        # 普通模块: level=1 → 父包; level=2 → 祖父包
        m2 = Module(modf)
        m2.mod = "ai_factory_os.services.conversation.service"
        chk("模块 level=1 → 父包", m2._resolve(_ifrom("from . import A")),
            "ai_factory_os.services.conversation")
        chk("模块 level=2 → 祖父包", m2._resolve(_ifrom("from ..work import B")),
            "ai_factory_os.services.work")
        chk("绝对导入原样", m2._resolve(_ifrom("from ai_factory_os.contracts.work import C")),
            "ai_factory_os.contracts.work")
    finally:
        OS = saved

    cases.append(("层判定", target_layer("ai_factory_os.services.work.store") == "services", ""))
    cases.append(("域判定", target_domain("ai_factory_os.services.work.store") == "work", ""))
    # ★ 2026-09-15: 「旧区判定」自检随老区删除移除（_pending_migration 已不存在）

    print("── 解析器自检（相对导入 · 层/域判定）")
    ok = sum(1 for _, c, _ in cases if c)
    for n, c, d in cases:
        print(f"   [{'PASS' if c else 'FAIL'}] {n}" + (f"   ← 得到 {d}" if not c else ""))
    print(f"   {ok}/{len(cases)} 通过")
    return 0 if ok == len(cases) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="架构守卫 R1–R17")
    ap.add_argument("--rule", choices=sorted(RULES), action="append")
    ap.add_argument("--selftest", action="store_true", help="只跑解析器自检")
    ap.add_argument("-q", "--quiet", action="store_true", help="只报汇总")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--max", type=int, default=10)
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    mods = modules()
    edges = _layer_edges(mods)
    todo = args.rule or sorted(RULES)
    red = 0
    for r in todo:
        label, fn = RULES[r]
        items = fn(mods, edges)
        red += bool(items)
        if not args.quiet:
            print(f"[{'红' if items else '绿'}] {r} {label}　({len(items)})")
            for it in (items if args.verbose else items[: args.max]):
                print(f"       · {it}")
            if len(items) > args.max and not args.verbose:
                print(f"       … 另 {len(items) - args.max} 项")

    print(f"\n汇总: {len(todo) - red}/{len(todo)} 条规则通过"
          f"（{'有红' if red else '全绿'}）· 跨层/跨域 import 边 {len(edges)} 条")
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
