"""tests/console/test_tools_executor.py — U-2 统一工具执行链 (v1.1.169)。

Founder: 工具要和 CLI/WebUI 连接正确调用 — Registry→Permission→Schema→Execute。
覆盖 (factory_console.tools.executor):
- 未注册工具 → 诚实错误
- 规划中工具 → 诚实"未实现"
- 敏感工具无 confirm → 拒绝
- 参数校验 (required)
- code_search / monitor 真实执行 (tmp 仓库)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_P) if (_P := _p) else _p)  # noqa: F841

_ex = importlib.import_module("factory_console.tools.executor")


class TestExecutor:
    def test_unregistered(self):
        r = _ex.execute_tool("nope", {})
        assert not r["ok"] and "未注册" in r["error"]

    def test_planned(self):
        r = _ex.execute_tool("code_review", {})
        assert not r["ok"] and "规划中" in r["error"]

    def test_sensitive_requires_confirm(self):
        r = _ex.execute_tool("git_ops", {}, context={})
        assert not r["ok"] and "确认" in r["error"]

    def test_missing_required_param(self):
        # code_search 需要 keyword (adapter 校验)
        r = _ex.execute_tool("code_search", {}, context={"root": _ROOT, "project_id": "p"})
        assert not r["ok"]

    def test_code_search_real(self, tmp_path):
        # repo 定位: project.json workspace_dir 指向带 .git 的仓库
        repo = tmp_path / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "mod.py").write_text("def scan_project():\n    pass\n", encoding="utf-8")
        import subprocess
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        pdir = tmp_path / "workspace" / "projects" / "p"
        pdir.mkdir(parents=True)
        (pdir / "project.json").write_text(
            '{"workspace_dir": "' + str(repo) + '"}', encoding="utf-8")
        r = _ex.execute_tool("code_search", {"keyword": "scan_project"},
                             context={"root": tmp_path, "project_id": "p"})
        assert r["ok"]
        assert any("mod.py" in h.get("file", "") for h in r["output"].get("hits", []))

    def test_monitor_returns_version(self):
        r = _ex.execute_tool("monitor", {}, context={"root": _ROOT, "project_id": "p"})
        assert r["ok"]
        assert "version" in r["output"].get("system", {})
