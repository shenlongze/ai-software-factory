"""架构层依赖测试（SSoT v0.2 冻结）。

用 ast 解析 src/ai_factory_os/ 下所有 .py 的 import，断言 8 条依赖铁律。
当前 src 是空骨架（无实现）→ 全部 PASS 属预期。
"""
from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "ai_factory_os"
LAYERS = ("contracts", "core", "services", "plugins", "infrastructure", "api", "bootstrap")


def _layer_of(path: Path) -> str:
    """文件所属顶层层（contracts / core / services / …）。"""
    rel = path.relative_to(SRC)
    return rel.parts[0] if rel.parts else ""


def _sub_of(path: Path) -> str:
    """层的第二级（如 services/identity → identity）。"""
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
    """import 的模块名 → 其顶层层（非 ai_factory_os 内部返回 ''）。"""
    parts = mod.split(".")
    if parts[0] != "ai_factory_os" or len(parts) < 2:
        return ""
    return parts[1]


def _target_sub(mod: str) -> str:
    parts = mod.split(".")
    return parts[2] if len(parts) > 2 else ""


def test_r1_contracts_no_cross_import() -> None:
    """R1: contracts/* 不许 import 其他顶层包。"""
    for f in _all_py():
        if _layer_of(f) != "contracts":
            continue
        for mod in _abs_imports(f):
            tgt = _target_layer(mod)
            assert not (tgt and tgt != "contracts"), f"[R1] {f}: {mod}"


def test_r2_core_only_contracts() -> None:
    """R2: core/* 只许 import contracts（+ 标准库）。"""
    for f in _all_py():
        if _layer_of(f) != "core":
            continue
        for mod in _abs_imports(f):
            tgt = _target_layer(mod)
            assert tgt in ("", "contracts"), f"[R2] {f}: {mod}"


def test_r3_services_no_cross_impl() -> None:
    """R3: services/A 不许 import services/B 的实现。"""
    for f in _all_py():
        if _layer_of(f) != "services":
            continue
        own = _sub_of(f)
        for mod in _abs_imports(f):
            tgt, sub = _target_layer(mod), _target_sub(mod)
            assert not (tgt == "services" and sub and sub != own), f"[R3] {f}: {mod}"


def test_r4_plugins_only_contracts() -> None:
    """R4: plugins/* 只许 import contracts。"""
    for f in _all_py():
        if _layer_of(f) != "plugins":
            continue
        for mod in _abs_imports(f):
            tgt = _target_layer(mod)
            assert tgt in ("", "contracts"), f"[R4] {f}: {mod}"


def test_r5_infrastructure_only_contracts() -> None:
    """R5: infrastructure/* 只许 import contracts。"""
    for f in _all_py():
        if _layer_of(f) != "infrastructure":
            continue
        for mod in _abs_imports(f):
            tgt = _target_layer(mod)
            assert tgt in ("", "contracts"), f"[R5] {f}: {mod}"


def test_r6_api_no_storage_impl() -> None:
    """R6: api/* 不许 import infrastructure.storage 的具体实现。"""
    for f in _all_py():
        if _layer_of(f) != "api":
            continue
        for mod in _abs_imports(f):
            assert not mod.startswith("ai_factory_os.infrastructure.storage"), f"[R6] {f}: {mod}"


def test_r7_apps_not_in_src() -> None:
    """R7: apps/* 不许出现在 src/ 内。"""
    for f in _all_py():
        parts = f.relative_to(SRC).parts
        assert "apps" not in parts, f"[R7] {f}"
        for mod in _abs_imports(f):
            assert "apps" not in mod.split("."), f"[R7] {f}: {mod}"


def test_r8_bootstrap_may_import_all() -> None:
    """R8: bootstrap/* 例外（可 import 全部）—— 仅验证该层可被识别。"""
    for f in _all_py():
        if _layer_of(f) == "bootstrap":
            assert True  # 无约束
