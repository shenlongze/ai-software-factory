"""架构铁律测试（代码层级设计 v1.0）。

用 ast 解析 src/ai_factory_os/ 下所有 .py 的 import 与语法结构，断言 12 条铁律。
不 import 被测代码 —— 纯静态，零副作用。

铁律清单：
    R1  contracts 不 import 其他顶层包
    R2  core 只 import contracts
    R3  services/A 不 import services/B 的实现
    R4  plugins 只 import contracts
    R5  infrastructure 只 import contracts
    R6  api 不 import infrastructure 的具体实现
    R7  apps 不出现在 src 内
    R8  bootstrap 例外（可 import 全部）
    R9  contracts 内无逻辑（无 if/for/while/try/with）
    R10 新结构内禁用文件名
    R11 services 域内文件 ⊆ 五件套
    R12 core 无业务词 且 总行数 ≤ 上限
"""
from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "ai_factory_os"
LAYERS = ("contracts", "core", "services", "plugins", "infrastructure", "api", "bootstrap")

# R10：禁用文件名（全仓库统一命名，防再次长出 25 个 models.py）
FORBIDDEN_FILENAMES = (
    "models.py", "utils.py", "common.py", "helpers.py", "misc.py",
    "base.py", "core.py", "_v2.py", "_old.py", "_backup.py", "_new.py",
)

# R11：services 域内只允许这五件（+ __init__）
SERVICE_FILES = ("service.py", "store.py", "rules.py", "events.py", "contracts.py")

# R12：core 内不许出现的具体业务词（大小写不敏感）
CORE_FORBIDDEN_WORDS = (
    "prd", "backlog", "sprint", "golden path", "golden_path",
    "software", "软件", "客户", "行业", "招聘", "市场", "财务", "代码生成",
)

CORE_LINE_LIMIT = 3000


# ------------------------------------------------------------------ helpers

def _layer_of(path: Path) -> str:
    rel = path.relative_to(SRC)
    return rel.parts[0] if rel.parts else ""


def _sub_of(path: Path) -> str:
    rel = path.relative_to(SRC)
    return rel.parts[1] if len(rel.parts) > 1 else ""


def _abs_imports(path: Path) -> list[str]:
    """提取绝对 import 的模块名（相对 import 视为同层，跳过）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level:
            if node.module:
                mods.append(node.module)
    return mods


def _all_py() -> list[Path]:
    return sorted(SRC.rglob("*.py")) if SRC.exists() else []


def _target_layer(mod: str) -> str:
    parts = mod.split(".")
    if parts[0] != "ai_factory_os" or len(parts) < 2:
        return ""
    return parts[1]


def _target_sub(mod: str) -> str:
    parts = mod.split(".")
    return parts[2] if len(parts) > 2 else ""


def _files_in_layer(layer: str) -> list[Path]:
    return [f for f in _all_py() if _layer_of(f) == layer]


# ------------------------------------------------------------------ R1-R8

def test_r1_contracts_no_cross_import() -> None:
    """R1: contracts/* 不许 import 其他顶层包。"""
    for f in _files_in_layer("contracts"):
        for mod in _abs_imports(f):
            tgt = _target_layer(mod)
            assert not (tgt and tgt != "contracts"), f"[R1] {f}: {mod}"


def test_r2_core_only_contracts() -> None:
    """R2: core/* 只许 import contracts（+ 标准库）。"""
    for f in _files_in_layer("core"):
        for mod in _abs_imports(f):
            tgt = _target_layer(mod)
            assert tgt in ("", "contracts"), f"[R2] {f}: {mod}"


def test_r3_services_no_cross_impl() -> None:
    """R3: services/A 不许 import services/B 的实现。"""
    for f in _files_in_layer("services"):
        own = _sub_of(f)
        for mod in _abs_imports(f):
            tgt, sub = _target_layer(mod), _target_sub(mod)
            assert not (tgt == "services" and sub and sub != own), f"[R3] {f}: {mod}"


def test_r4_plugins_only_contracts() -> None:
    """R4: plugins/* 只许 import contracts。"""
    for f in _files_in_layer("plugins"):
        for mod in _abs_imports(f):
            tgt = _target_layer(mod)
            assert tgt in ("", "contracts"), f"[R4] {f}: {mod}"


def test_r5_infrastructure_only_contracts() -> None:
    """R5: infrastructure/* 只许 import contracts。"""
    for f in _files_in_layer("infrastructure"):
        for mod in _abs_imports(f):
            tgt = _target_layer(mod)
            assert tgt in ("", "contracts"), f"[R5] {f}: {mod}"


def test_r6_api_no_infrastructure_impl() -> None:
    """R6: api/* 不许 import infrastructure 的具体实现。"""
    for f in _files_in_layer("api"):
        for mod in _abs_imports(f):
            tgt = _target_layer(mod)
            assert tgt != "infrastructure", f"[R6] {f}: {mod}"


def test_r7_apps_not_in_src() -> None:
    """R7: apps/* 不许出现在 src/ 内。"""
    for f in _all_py():
        parts = f.relative_to(SRC).parts
        assert "apps" not in parts, f"[R7] {f}"
        for mod in _abs_imports(f):
            assert "apps" not in mod.split("."), f"[R7] {f}: {mod}"


def test_r8_bootstrap_may_import_all() -> None:
    """R8: bootstrap/* 例外（可 import 全部）—— 仅验证该层可被识别。"""
    for f in _files_in_layer("bootstrap"):
        assert True  # 无约束


# ------------------------------------------------------------------ R9-R12

def test_r9_contracts_have_no_logic() -> None:
    """R9: contracts 内无逻辑 —— 不许 if/for/while/try/with。"""
    banned = (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith,
              ast.AsyncFor, ast.AsyncFunctionDef)
    for f in _files_in_layer("contracts"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            assert not isinstance(node, banned), \
                f"[R9] {f}:{getattr(node, 'lineno', '?')} 出现逻辑语句 {type(node).__name__}"


def test_r10_no_forbidden_filenames() -> None:
    """R10: 新结构内不得出现禁用文件名。"""
    for f in _all_py():
        for bad in FORBIDDEN_FILENAMES:
            hit = f.name == bad or (bad.startswith("_") and f.stem.endswith(bad[:-3]))
            assert not hit, f"[R10] 禁用文件名: {f}"


def test_r11_services_five_piece_only() -> None:
    """R11: 每个 services 域内的文件 ⊆ 五件套 + __init__.py。"""
    for f in _files_in_layer("services"):
        assert f.name == "__init__.py" or f.name in SERVICE_FILES, \
            f"[R11] {f} 不在五件套内（{SERVICE_FILES}）"


def test_r12_core_thin_and_pure() -> None:
    """R12: core 无业务词，且总行数 ≤ 上限。"""
    core_files = _files_in_layer("core")
    texts = {f: f.read_text(encoding="utf-8") for f in core_files}
    for f, txt in texts.items():
        low = txt.lower()
        for word in CORE_FORBIDDEN_WORDS:
            assert word not in low, f"[R12] core 出现业务词 {word!r}: {f}"
    total = sum(len(t.splitlines()) for t in texts.values())
    assert total <= CORE_LINE_LIMIT, f"[R12] core 行数 {total} > {CORE_LINE_LIMIT}"
