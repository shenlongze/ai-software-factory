"""动态工具面接入 (S10-127 M2.2) — 首轮核心+预检索+元工具, tool_search 累积展开。

不触发真实 API。覆盖:
- 首轮工具数 < 全量, 含核心 + 预检索命中 + tool_search
- dispatch("tool_search") 返回 matches
- tool_search 调用后 visible 工具累积 (expand_matches)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from factory_console.session import agent_loop as _al
from factory_console.session import tool_search as _ts


@pytest.fixture(scope="module")
def all_tools():
    return _al.tool_schemas(None)


def test_initial_tools_smaller_and_contains_core(all_tools):
    first = _al._initial_tools("扫描项目", all_tools, top_k=5)
    names = [str((t["function"] or {}).get("name")) for t in first]
    assert len(first) < len(all_tools), "首轮工具面必须小于全量"
    for c in _al.CORE_TOOL_IDS:
        assert c in names, f"核心工具 {c} 缺失"
    assert _ts.TOOL_SEARCH_ID in names
    # 预检索命中: "扫描项目" → project_scan 首轮可见 (核心已含, 检查去重无重复)
    assert len(names) == len(set(names)), "工具面不允许重复"


def test_initial_tools_presearch_hit(all_tools):
    # 问"查看文档" → project_docs 应被预检索加入首轮
    first = _al._initial_tools("帮我查看项目文档", all_tools, top_k=5)
    names = [str((t["function"] or {}).get("name")) for t in first]
    assert "project_docs" in names, names


def test_dispatch_tool_search_matches(all_tools):
    ctx = {"all_tools": all_tools}
    r = _al.dispatch("tool_search", {"query": "扫描项目"}, root="/tmp", project_id="p", service=None, ctx=ctx)
    assert r.get("ok") is True
    assert "project_scan" in (r.get("matches") or []), r


def test_dispatch_tool_search_no_hit(all_tools):
    ctx = {"all_tools": all_tools}
    r = _al.dispatch("tool_search", {"query": "zzz不存在的工具zzz"}, root="/tmp", project_id="p", service=None, ctx=ctx)
    assert r.get("ok") is True
    assert not (r.get("matches") or [])


def test_expand_after_tool_search(all_tools):
    first = _al._initial_tools("你好", all_tools, top_k=2)
    # 模拟 tool_search("查看文档") 命中 project_docs
    ctx = {"all_tools": all_tools}
    r = _al.dispatch("tool_search", {"query": "查看文档"}, root="/tmp", project_id="p", service=None, ctx=ctx)
    expanded = _ts.expand_matches(all_tools, first, r.get("matches") or [])
    expanded_names = [str((t["function"] or {}).get("name")) for t in expanded]
    assert "project_docs" in expanded_names
    assert len(expanded) >= len(first)
    # 累积不重复
    expanded2 = _ts.expand_matches(all_tools, expanded, r.get("matches") or [])
    assert len(expanded2) == len(expanded)
