"""factory-console/session/core_loader.py — 延迟加载 factory-core / factory-exec (M1)。

与 actions._load_org_cli/_load_exec_cli 同模式: 运行时 sys.path 挂载对应仓库
目录后 importlib 导入 (包目录名含连字符, 无法直接 import 语句)。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]  # session/ → factory-console/ → 仓库根


def _ensure(path: str) -> None:
    if path not in sys.path:
        sys.path.insert(0, path)


def load_core(module: str, attr: str = "") -> Any:
    """加载 factory-core 子模块 (如 understanding.service); attr 非空 → 取属性。"""
    _ensure(str(_ROOT / "factory-core"))
    mod = importlib.import_module(module)
    return getattr(mod, attr) if attr else mod


def load_exec(module: str, attr: str = "") -> Any:
    """加载 factory-exec 子模块 (如 exec.sandbox); attr 非空 → 取属性。"""
    _ensure(str(_ROOT / "factory-exec"))
    mod = importlib.import_module(module)
    return getattr(mod, attr) if attr else mod
