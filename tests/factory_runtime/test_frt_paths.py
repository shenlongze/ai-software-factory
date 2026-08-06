"""tests/factory_runtime/test_frt_paths.py — paths 模块 (平台目录映射/7 子目录/权限)。

重点: 平台目录映射 (platformdirs + stdlib 降级) / 7 子目录 / POSIX 700。
"""

from __future__ import annotations

import os
import stat
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """隔离 XDG/APPDATA 环境变量。"""
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)


def test_subdirs_constant(rt_pkg):
    assert rt_pkg.paths.SUBDIRS == (
        "config",
        "providers",
        "agents",
        "skills",
        "mcp",
        "logs",
        "data",
    )


def test_default_data_dir_matches_platformdirs(rt_pkg):
    import platformdirs

    expected = Path(platformdirs.user_data_dir("ai-software-factory"))
    assert rt_pkg.paths.default_data_dir() == expected


def test_default_config_dir_matches_platformdirs(rt_pkg):
    import platformdirs

    expected = Path(platformdirs.user_config_dir("ai-software-factory"))
    assert rt_pkg.paths.default_config_dir() == expected


def test_fallback_data_dir_darwin(rt_pkg, monkeypatch):
    monkeypatch.setitem(sys.modules, "platformdirs", None)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(os, "name", "posix")
    expected = Path.home() / "Library" / "Application Support" / "ai-software-factory"
    assert rt_pkg.paths.default_data_dir() == expected


def test_fallback_data_dir_linux(rt_pkg, monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "platformdirs", None)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    expected = tmp_path / "xdg-data" / "ai-software-factory"
    assert rt_pkg.paths.default_data_dir() == expected


def test_fallback_data_dir_linux_default_share(rt_pkg, monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "platformdirs", None)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    expected = tmp_path / ".local" / "share" / "ai-software-factory"
    assert rt_pkg.paths.default_data_dir() == expected


def test_fallback_data_dir_windows(rt_pkg, monkeypatch, tmp_path):
    # os.name 直接 patch 会让 pathlib 在 macOS 上实例化 WindowsPath 崩溃 —
    # 用 fake os 模块替换 rt_pkg.paths.os (真实 pathlib 不受影响)
    monkeypatch.setitem(sys.modules, "platformdirs", None)
    monkeypatch.setattr(sys, "platform", "linux")
    fake_os = types.SimpleNamespace(name="nt", environ={"APPDATA": str(tmp_path / "appdata")})
    monkeypatch.setattr(rt_pkg.paths, "os", fake_os)
    expected = tmp_path / "appdata" / "ai-software-factory"
    assert rt_pkg.paths.default_data_dir() == expected


def test_fallback_config_dir_linux(rt_pkg, monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "platformdirs", None)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    expected = tmp_path / "xdg-config" / "ai-software-factory"
    assert rt_pkg.paths.default_config_dir() == expected


def test_ensure_data_root_creates_seven_subdirs(rt_pkg, tmp_path):
    root = tmp_path / "data"
    result = rt_pkg.paths.ensure_data_root(root)
    assert result == root.resolve()
    for name in rt_pkg.paths.SUBDIRS:
        assert (result / name).is_dir()


def test_ensure_data_root_idempotent(rt_pkg, tmp_path):
    root = tmp_path / "data"
    rt_pkg.paths.ensure_data_root(root)
    rt_pkg.paths.ensure_data_root(root)  # 二次调用零异常
    assert (root / "logs").is_dir()


def test_ensure_data_root_perm_700(rt_pkg, tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX only")
    root = tmp_path / "data"
    rt_pkg.paths.ensure_data_root(root)
    assert stat.S_IMODE(root.stat().st_mode) == 0o700


def test_ensure_data_root_expands_user(rt_pkg, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    result = rt_pkg.paths.ensure_data_root("~/rt-data")
    assert result == (tmp_path / "rt-data").resolve()
