#!/usr/bin/env python3
"""旧代码可达性分析（只读）。

从活入口 BFS 真实 import 图，把旧代码分为三类：
    可达         生产入口能走到
    仅测试可达    只有测试能走到
    未证实使用    静态分析走不到 —— **不得当作可删**（可能被动态/未知方式使用）

⚠️ 本工具**不产出「可删」结论**。静态可达性无法证明代码是死的：
   项目里存在多种静态解析不到的加载方式，已确认的三类：
     ① 字符串动态加载     importlib.import_module("factory_console.api")
     ② 拼接式动态加载     __import__(f"factory_console.{mod}")
     ③ 经本地辅助函数转发  _console_import("api")  →  __import__(f"factory_console.{mod}")
   ①②③ 已覆盖；未覆盖的方式仍可能有，故第三类一律标「未证实」。

解析覆盖：
    · 绝对 import · 相对 import · 目录 → 包名映射（factory-console → factory_console）
    · 字符串动态加载 · 拼接式动态加载（前缀）· 本地辅助函数调用点

用法：
    python scripts/legacy_reach.py            # 摘要
    python scripts/legacy_reach.py --json     # 机器可读
"""
from __future__ import annotations

import ast
import json
import re
import sys
from collections import deque
from pathlib import Path

from legacy_roots import EXTERNAL_ONLY_NAMES, LEGACY_PARTS, PARTITIONS  # 单一来源

ROOT = Path(__file__).resolve().parents[1]
NEW = ROOT / "src" / "ai_factory_os"
SKIP = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
        "node_modules", "build", "dist", "target", ".mypy_cache"}

# (根目录, 该根下文件的模块名前缀) —— 顺序即优先级
LEGACY_DIR = ROOT.joinpath(*LEGACY_PARTS)

ROOTS: tuple[tuple[Path, str], ...] = (
    (LEGACY_DIR / "factory-console", "factory_console"),
    (LEGACY_DIR / "factory-core", ""),
    (LEGACY_DIR / "factory-exec", ""),
    (LEGACY_DIR / "factory-org", ""),
    (LEGACY_DIR / "factory-runtime", ""),
    (LEGACY_DIR, ""),
)

PROD_ENTRIES = (
    "bin/factory",
    "src/legacy/factory-console/cli_factory.py",
    "src/legacy/factory-console/web/backend/fastapi_adapter.py",
)

# ⚠️ 已知盲区 —— 本工具**只扫 Python 的加载行为**，下列消费方式它看不见：
#   ① 子进程调用 CLI：Rust/JS/Shell 把它当命令跑（如 desktop 调 factory-runtime CLI）
#   ② 路径引用：测试夹具 / 打包配置按文件系统路径引用目录
#   ③ 非 Python 消费者：Rust / TypeScript / JSON 配置里写死名字
#   ④ 未覆盖的动态加载：非字面量拼接（如 f"{prefix}{name}" 的形式）
# 为降低 ①③ 的漏判，本文件额外做一次**名称引用扫描**（见 external_references）。
KNOWN_BLIND_SPOTS = (
    "subprocess-cli",       # 被当命令跑，不被 import
    "path-reference",       # 按文件系统路径引用
    "non-python-consumer",  # Rust / TS / JSON 里写死名字
    "computed-dynamic",     # 非字面量拼接的动态加载
)

# 名称引用扫描范围（非 Python 载体）
SCAN_SUFFIXES = (".rs", ".ts", ".tsx", ".js", ".jsx", ".json", ".toml",
                 ".yaml", ".yml", ".sh", ".cfg", ".ini", ".spec", ".nix", ".dockerfile")
SKIP_DIR_FOR_SCAN = {"node_modules", "docs", "build", "dist", "target"}
# 自引用：本工具自己的产物不算「被消费」
SKIP_SELF_PREFIXES = ("tests/architecture/", "scripts/")
# 强信号载体（清单/打包/桥接）优先作为示例 —— 文档性提及会排在后面
STRONG_SUFFIXES = (".toml", ".json", ".rs", ".spec", ".yaml", ".yml", ".cfg", ".ini")

_DYN_LITERAL = re.compile(r"""(?:import_module|__import__)\(\s*["']([\w.\-]+)["']""")
_DYN_ANY = re.compile(r"(?:import_module|__import__)\(")
_IMPORT_FUNCS = ("__import__", "import_module")


def all_py() -> list[Path]:
    return sorted(p for p in ROOT.rglob("*.py")
                  if not any(s in p.parts for s in SKIP) and NEW not in p.parents)


def module_of(path: Path) -> str | None:
    for root, prefix in ROOTS:
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        parts = list(rel.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        dotted = ".".join(parts)
        if not dotted:
            continue
        return f"{prefix}.{dotted}" if prefix else dotted
    return None


def _fstring_prefix(node: ast.AST) -> str | None:
    """识别 __import__(f"前缀.{var}") / import_module(f"...") → 返回字面前缀。"""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    name = func.id if isinstance(func, ast.Name) else (
        func.attr if isinstance(func, ast.Attribute) else "")
    if name not in _IMPORT_FUNCS or not node.args:
        return None
    first = node.args[0]
    if not isinstance(first, ast.JoinedStr):
        return None
    for part in first.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            return part.value
        return None  # 以 {var} 开头 → 无从判定
    return None


def dynamic_sources(tree: ast.AST) -> tuple[set[str], set[str]]:
    """返回（拼接前缀集合, 具体目标模块集合）。

    覆盖面：
        · 直接的 __import__(f"prefix.{mod}")
        · 本地辅助函数（体内含上述写法）→ 其字符串字面量调用点
    """
    prefixes: set[str] = set()
    helper_prefix: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                found = _fstring_prefix(sub)
                if found:
                    helper_prefix[node.name] = found
                    prefixes.add(found)
        found = _fstring_prefix(node)
        if found:
            prefixes.add(found)

    targets: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (
            func.attr if isinstance(func, ast.Attribute) else "")
        base = helper_prefix.get(name)
        if base is None or not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            targets.add(base + arg.value)
    return prefixes, targets


def parse(path: Path) -> tuple[set[str], list[tuple[int, str]], set[str], tuple[set[str], set[str]]]:
    """返回（绝对模块名, 相对 import, 字符串动态字面量, 动态前缀/目标）。"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text)
    except (SyntaxError, OSError):
        return set(), [], set(), (set(), set())

    absolute: set[str] = set()
    relative: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            absolute |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative.append((node.level, node.module or ""))
            elif node.module:
                absolute.add(node.module)
    return absolute, relative, set(_DYN_LITERAL.findall(text)), dynamic_sources(tree)


def build_index() -> tuple[dict[str, Path], dict[Path, str]]:
    by_module: dict[str, Path] = {}
    module_by_path: dict[Path, str] = {}
    for f in all_py():
        mod = module_of(f)
        if mod:
            module_by_path[f] = mod
            by_module.setdefault(mod, f)
    return by_module, module_by_path


def _resolve(by_module: dict[str, Path], mod: str) -> Path | None:
    parts = mod.split(".")
    for cut in range(len(parts), 0, -1):
        hit = by_module.get(".".join(parts[:cut]))
        if hit is not None:
            return hit
    return None


def _resolve_literal(by_module: dict[str, Path], literal: str) -> Path | None:
    return _resolve(by_module, literal) or _resolve(by_module, literal.replace("-", "_"))


def _resolve_relative(by_module: dict[str, Path], owner: str, level: int, mod: str) -> Path | None:
    own_file = by_module.get(owner)
    is_package = own_file is not None and own_file.name == "__init__.py"
    package = owner if is_package else owner.rpartition(".")[0]
    for _ in range(level - 1):
        package = package.rpartition(".")[0]
    if not package:
        return None
    return _resolve(by_module, f"{package}.{mod}" if mod else package)


def out_edges(path: Path, by_module: dict[str, Path], module_by_path: dict[Path, str],
              unresolved: list[str]) -> list[Path]:
    absolute, relative, dynamic, _ = parse(path)
    found: list[Path] = []
    for mod in absolute:
        hit = _resolve(by_module, mod)
        if hit:
            found.append(hit)
    owner = module_by_path.get(path)
    if owner:
        for level, mod in relative:
            hit = _resolve_relative(by_module, owner, level, mod)
            if hit:
                found.append(hit)
    for literal in dynamic:
        if literal.split(".")[0] in sys.stdlib_module_names:
            continue
        hit = _resolve_literal(by_module, literal)
        if hit:
            found.append(hit)
        else:
            unresolved.append(f"{path.relative_to(ROOT)} -> {literal}")
    return found


def bfs(entries: list[Path], by_module, module_by_path, unresolved: list[str]) -> set[Path]:
    seen: set[Path] = set()
    queue = deque(p for p in entries if p.exists())
    seen.update(queue)
    while queue:
        for nxt in out_edges(queue.popleft(), by_module, module_by_path, unresolved):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def _is_legacy(path: Path) -> bool:
    """必须与 scripts/legacy_inventory.py 的文件集规则完全一致（排除 tests/）。"""
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return False
    return (rel.parts[:2] == LEGACY_PARTS
            and rel.parts[2] in PARTITIONS      # 排除 legacy_paths（我加的基础设施）
            and "tests" not in rel.parts)


def _lines(files) -> int:
    return sum(len(f.read_text(encoding="utf-8", errors="replace").splitlines()) for f in files)


def external_references() -> dict[str, list[str]]:
    """名称引用扫描：非 Python 载体里写死旧分区名的文件（降低盲区 ①③ 的漏判）。

    能在 desktop/src-tauri/tauri.conf.json 这类打包配置里发现「被当组件消费」的目录 ——
    factory-runtime 就是这样被发现的（它是桌面应用的运行时后端，从不被 Python import）。
    """
    pattern = {name: re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])") for name in (*PARTITIONS, *EXTERNAL_ONLY_NAMES)}
    hits: dict[str, list[str]] = {name: [] for name in (*PARTITIONS, *EXTERNAL_ONLY_NAMES)}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        if any(part in SKIP_DIR_FOR_SCAN or part in SKIP for part in path.parts):
            continue
        rel = str(path.relative_to(ROOT))
        if rel.startswith(SKIP_SELF_PREFIXES):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name, rx in pattern.items():
            if rx.search(text):
                hits[name].append(rel)
    # 强信号（清单/打包/桥接）排前，文档性提及排后
    return {name: sorted(files, key=lambda f: (Path(f).suffix.lower() not in STRONG_SUFFIXES, f))
            for name, files in hits.items() if files}


def analyze() -> dict:
    by_module, module_by_path = build_index()
    unresolved: list[str] = []
    tests = [p for p in ROOT.rglob("tests/**/*.py") if not any(s in p.parts for s in SKIP)]
    entries = [ROOT / e for e in PROD_ENTRIES]

    live_all = bfs(entries, by_module, module_by_path, unresolved)
    with_tests = bfs(entries + tests, by_module, module_by_path, unresolved)

    legacy = {p: module_by_path[p] for p in module_by_path if _is_legacy(p)}
    live = {p for p in live_all if p in legacy}
    test_only = {p for p in with_tests if p in legacy} - live

    # 拼接式动态加载 → 受影响前缀（这些模块绝不可判为"未使用"）
    prefixes: set[str] = set()
    dyn_targets: set[str] = set()
    for p in legacy:
        _, _, _, (pre, tgt) = parse(p)
        prefixes |= pre
        dyn_targets |= tgt

    def covered(mod: str) -> bool:
        return (any(mod.startswith(p) for p in prefixes)
                or any(mod == t or mod.startswith(t + ".") for t in dyn_targets))

    unverified = {p for p in legacy if p not in live and p not in test_only}
    unverified_shadowed = {p for p in unverified if covered(legacy[p])}

    dynamic_calls = sum(len(_DYN_ANY.findall(p.read_text(encoding="utf-8", errors="replace")))
                        for p in legacy)
    return {
        "totals": {"files": len(legacy), "lines": _lines(legacy)},
        "live": {"files": len(live), "lines": _lines(live)},
        "test_only": {"files": len(test_only), "lines": _lines(test_only)},
        "unverified": {"files": len(unverified), "lines": _lines(unverified)},
        "unverified_shadowed": {
            "files": len(unverified_shadowed), "lines": _lines(unverified_shadowed),
            "note": "受已知动态加载前缀影响 —— 尤其不可当作可删",
        },
        "by_root": {
            name: {
                "live": sum(1 for p in live if p.relative_to(ROOT).parts[0] == name),
                "test_only": sum(1 for p in test_only if p.relative_to(ROOT).parts[0] == name),
                "unverified": sum(1 for p in unverified if p.relative_to(ROOT).parts[0] == name),
            }
            for name in (*PARTITIONS, *EXTERNAL_ONLY_NAMES)
        },
        "dynamic_calls": dynamic_calls,
        "dynamic_prefixes": sorted(prefixes),
        "dynamic_targets": sorted(dyn_targets),
        "unresolved_dynamic": sorted(set(unresolved)),
        "blind_spots": list(KNOWN_BLIND_SPOTS),
        "external_references": external_references(),
        "entries": list(PROD_ENTRIES),
        "paths": {
            "live": sorted(str(p.relative_to(ROOT)) for p in live),
            "test_only": sorted(str(p.relative_to(ROOT)) for p in test_only),
            "unverified": sorted(str(p.relative_to(ROOT)) for p in unverified),
        },
    }


def main() -> int:
    data = analyze()
    if "--json" in sys.argv[1:]:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0
    t = data["totals"]
    print("旧代码可达性（从活入口 BFS）—— 本工具不产出「可删」结论")
    print(f"  总计          {t['files']:4d} 文件 / {t['lines']:7d} 行")
    for key, label in (("live", "① 可达"), ("test_only", "② 仅测试可达"),
                       ("unverified", "③ 未证实使用（不得当可删）")):
        d = data[key]
        print(f"  {label:26s} {d['files']:4d} 文件 / {d['lines']:7d} 行")
    s = data["unverified_shadowed"]
    print(f"     其中受动态加载前缀影响       {s['files']:4d} 文件 / {s['lines']:7d} 行")
    print(f"  动态调用 {data['dynamic_calls']} 处 · 拼接前缀 {len(data['dynamic_prefixes'])} 个 "
          f"· 未解析字面量 {len(data['unresolved_dynamic'])} 条")
    ext = data["external_references"]
    if ext:
        print()
        print("  ⚠️ 非 Python 载体引用（子进程 / 打包配置 / 路径）—— 弱信号，可能含文档性提及，")
        print("     但被点名的分区绝不可当作可删：")
        for name, files in sorted(ext.items()):
            strong = [f for f in files if Path(f).suffix.lower() in STRONG_SUFFIXES]
            example = strong[0] if strong else files[0]
            tag = "" if strong else "（仅文档性提及）"
            print(f"     {name:16s} {len(files):2d} 个文件，例: {example} {tag}")
    print()
    print("  已知盲区（工具只扫 Python 加载行为）: " + ", ".join(data["blind_spots"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
