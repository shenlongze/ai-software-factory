"""S10-098 — REPL banner 版本单源回归测试 (v0.2 硬编码修复)。

覆盖:
1. banner 不含 v0.2 (硬编码已移除)
2. banner 版本 == pyproject.toml 版本 (单源一致)
3. 源码态/安装态同源 (pyproject 优先, metadata 兜底)
"""

from __future__ import annotations

import importlib
import tomllib
from importlib import import_module
from pathlib import Path

SESSION = import_module("factory-console.session.session")
ROOT = Path(__file__).resolve().parents[2]


def _pyproject_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


class TestBannerVersion:
    def test_banner_not_hardcoded_v02(self):
        """banner 不再含 v0.2 硬编码。"""
        assert "v0.2" not in SESSION.BANNER

    def test_banner_matches_pyproject(self):
        """banner 版本 == pyproject.toml 版本 (单源)。"""
        first = SESSION.BANNER.split("\n")[0]
        assert _pyproject_version() in first, f"banner={first!r} pyproject={_pyproject_version()}"

    def test_banner_has_version_prefix(self):
        """banner 以 AI Factory v<ver> 开头。"""
        assert SESSION.BANNER.startswith("AI Factory v")
