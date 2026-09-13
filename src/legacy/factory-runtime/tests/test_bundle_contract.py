"""factory-runtime/tests/test_bundle_contract.py — Phase 15A-3c-3 dmg 契约测试 (少量)。

验证**真实打包产物** (dist/factory-runtime-bundle, PyInstaller onedir) 的契约:
  1. bundle init → 7 子目录 + runtime_state.json + runtime_token (600)
  2. data_root 权限 0700 (fresh machine 隐私契约)
  3. 内嵌解释器独立性 (_internal/ 内含 Python.framework/python3.12 — 不依赖系统 python)

与 tests/factory_runtime/ (源码级 CLI 契约) 互补: 本文件走子进程调用 bundle 可执行
文件本身 — 即 dmg 内嵌的那个 artifact。dist/ 被 gitignore, 未构建时 pytest.skip
(等价 @skipif)。

注意: root pytest.ini testpaths=["tests"] 不含本目录 — 运行方式:
    .venv/bin/pytest -q tests/ factory-runtime/tests/
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest

_BUNDLE = (
    Path(__file__).resolve().parents[2]
    / "dist"
    / "factory-runtime-bundle"
    / "factory-runtime-bundle"
)

SUBDIRS = ["config", "providers", "agents", "skills", "mcp", "logs", "data"]


def _bundle() -> Path:
    if not _BUNDLE.is_file():
        pytest.skip("dist/factory-runtime-bundle 未构建 (scripts/build-runtime-bundle.sh)")
    return _BUNDLE


def _init_root(bundle: Path, root: Path) -> None:
    subprocess.run(
        [str(bundle), "--root", str(root), "init"],
        check=True,
        capture_output=True,
        text=True,
    )


def test_bundle_init_creates_seven_subdirs_and_state() -> None:
    bundle = _bundle()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "root"
        _init_root(bundle, root)
        for name in SUBDIRS:
            assert (root / name).is_dir(), f"init 缺子目录: {name}"
        assert (root / "config" / "runtime_state.json").is_file()
        assert (root / "config" / "runtime_token").is_file()


def test_bundle_init_data_root_perms_700_token_600() -> None:
    if os.name != "posix":
        pytest.skip("POSIX only")
    bundle = _bundle()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "root"
        _init_root(bundle, root)
        assert stat.S_IMODE(root.stat().st_mode) == 0o700, (
            f"data_root 权限应 700, got {oct(stat.S_IMODE(root.stat().st_mode))}"
        )
        assert stat.S_IMODE((root / "config" / "runtime_token").stat().st_mode) == 0o600


def test_bundle_embeds_own_interpreter() -> None:
    """App 内嵌 runtime 不依赖系统 python: _internal/ 含 PyInstaller 内嵌解释器。"""
    bundle = _bundle()
    internal = bundle.parent / "_internal"
    assert internal.is_dir(), "PyInstaller onedir _internal 缺失"
    embedded = (
        (internal / "Python.framework").exists()
        or (internal / "python3.12").exists()
        or (internal / "Python").exists()
    )
    assert embedded, "内嵌解释器缺失 (Python.framework / python3.12 / Python)"
