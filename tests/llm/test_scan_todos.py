"""scan_todos 工具 + 完整工具目录注入单测。

覆盖:
- scan_todos: 列出 TODO 明细 (文件:行:内容), 路径过滤, 截断
- dispatch scan_todos → ok + 明细
- tool_schemas 含 scan_todos
- catalog_summary 注入 (含执行类工具)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "src").mkdir(parents=True)
    (r / "src" / "a.py").write_text(
        "x = 1\n# TODO: 优化这里\ny = 2\n# FIXME: 修 bug\n", encoding="utf-8")
    (r / "src" / "b.ts").write_text("// TODO: 加类型\nconst z = 1;\n", encoding="utf-8")
    (r / "README.md").write_text("# 文档\nTODO: 补说明\n", encoding="utf-8")
    return r


def test_scan_todos_lists(repo, tmp_path):
    import json
    from factory_console.session.code_scan import scan_todos, format_todos

    proj = tmp_path / "workspace" / "projects" / "p1"
    proj.mkdir(parents=True)
    (proj / "project.json").write_text(json.dumps({"workspace_dir": str(repo)}), encoding="utf-8")
    r = scan_todos(str(tmp_path), "p1")
    assert r["ok"] is True
    assert r["total"] == 4  # a.py 2 + b.ts 1 + README 1
    files = {it["file"] for it in r["items"]}
    assert "src/a.py" in files
    assert "src/b.ts" in files
    assert "README.md" in files
    assert all(it["line"] >= 1 for it in r["items"])
    text = format_todos(r)
    assert "src/a.py:2" in text
    assert "优化" in text


def test_scan_todos_path_filter(repo, tmp_path):
    import json
    from factory_console.session.code_scan import scan_todos

    proj = tmp_path / "workspace" / "projects" / "p1"
    proj.mkdir(parents=True)
    (proj / "project.json").write_text(json.dumps({"workspace_dir": str(repo)}), encoding="utf-8")
    r = scan_todos(str(tmp_path), "p1", path_filter="src")
    assert r["total"] == 3  # 排除 README
    assert all("src/" in it["file"] for it in r["items"])


def test_scan_todos_truncate(repo, tmp_path):
    import json
    from factory_console.session.code_scan import scan_todos

    proj = tmp_path / "workspace" / "projects" / "p1"
    proj.mkdir(parents=True)
    (proj / "project.json").write_text(json.dumps({"workspace_dir": str(repo)}), encoding="utf-8")
    r = scan_todos(str(tmp_path), "p1", max_items=2)
    assert r["total"] == 2
    assert r["truncated"] is True


def test_dispatch_scan_todos(repo, tmp_path):
    from factory_console.session import agent_loop as _al

    # 模拟 project.json 定位仓库
    import json
    proj = tmp_path / "projects" / "p1"
    proj.mkdir(parents=True)
    (proj / "project.json").write_text(json.dumps({"workspace_dir": str(repo)}), encoding="utf-8")

    r = _al.dispatch("scan_todos", {}, root=str(tmp_path), project_id="p1", service=None, ctx={})
    assert r.get("ok") is True
    assert "TODO/FIXME 明细" in r["output"]


def test_tool_schemas_contains_scan_todos():
    from factory_console.session import agent_loop as _al

    tools = _al.tool_schemas(None)
    names = [str((t.get("function") or {}).get("name")) for t in tools]
    assert "scan_todos" in names


def test_catalog_summary_includes_exec_tools():
    from factory_console.session.tool_search import catalog_summary

    tools = __import__("factory_console.session.agent_loop", fromlist=["tool_schemas"]).tool_schemas(None)
    summary = catalog_summary(tools)
    assert "create_task" in summary
    assert "chain_start" in summary
    assert "gateway_status" in summary
