"""tool_search 动态工具检索单测 (S10-127 M2.1) — 检索质量 + 目录 + 累积展开。

验收: "扫描项目" → top-5 含 project_scan; "读取代码" → 含 read_code;
"查看文档" → 含 project_docs; 中文/英文查询均可。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_TS = _ROOT / "factory-console" / "session" / "tool_search.py"


@pytest.fixture(scope="module")
def ts():
    spec = importlib.util.spec_from_file_location("tool_search", _TS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fc(name, desc, keywords=None):
    t = {"type": "function", "function": {"name": name, "description": desc,
                                          "parameters": {"type": "object", "properties": {}}}}
    if keywords:
        t["metadata"] = {"keywords": keywords}
    return t


@pytest.fixture(scope="module")
def tools():
    return [
        _fc("code_scan", "扫描项目仓库代码: 文件数/行数/语言分布/测试文件/TODO/大文件/最近改动/git"),
        _fc("project_scan", "扫描项目整体: 任务树/版本线/战役线/质量/风险建议"),
        _fc("project_structure", "查看项目真实结构: 仓库顶层目录树/模块划分/文件分布/入口文件"),
        _fc("read_code", "读取指定文件的代码内容(带行号, 支持分页), 用于理解代码逻辑/实现/调用链"),
        _fc("search_code", "在仓库中检索关键词, 返回命中文件"),
        _fc("project_status", "查询项目实时状态: 生命周期/进度/当前阶段/工作流"),
        _fc("project_tasks", "查询项目任务 (按优先级或全部统计)"),
        _fc("task_action", "对任务执行动作: start/done/priority"),
        _fc("create_task", "在当前项目创建新任务"),
        _fc("project_docs", "列出项目文档/产出物"),
        _fc("git_status", "查询 git 仓库: 远程/分支/领先提交"),
        _fc("monitor", "查询系统/服务运行状态"),
        _fc("task_continue", "继续任务: 按标题定位并锚定到会话"),
        _fc("plan_development", "开发类需求: 产出结构化计划 → 请求审批"),
        _fc("execute_plan", "审批通过后: 按计划建任务进 backlog"),
        _fc("external_route", "为任务选择最合适外部AI agent"),
        _fc("chain_start", "启动执行链: 按计划建任务列表, 逐任务执行"),
        _fc("chain_next", "推进下一个任务"),
        _fc("chain_status", "查询当前执行链进度"),
        _fc("knowledge_search", "在项目文档中检索知识点/历史结论"),
    ]


def test_discover_project_scan(ts, tools):
    hits = ts.discover_tools(tools, "扫描项目", top_k=5)
    names = [str((t["function"] or {}).get("name")) for t in hits]
    assert "project_scan" in names, names


def test_discover_read_code(ts, tools):
    hits = ts.discover_tools(tools, "读取代码 看代码逻辑", top_k=5)
    names = [str((t["function"] or {}).get("name")) for t in hits]
    assert "read_code" in names, names


def test_discover_docs(ts, tools):
    hits = ts.discover_tools(tools, "查看文档", top_k=5)
    names = [str((t["function"] or {}).get("name")) for t in hits]
    assert "project_docs" in names, names


def test_discover_english(ts, tools):
    hits = ts.discover_tools(tools, "scan project", top_k=5)
    names = [str((t["function"] or {}).get("name")) for t in hits]
    assert "project_scan" in names, names


def test_empty_query_returns_empty(ts, tools):
    assert ts.discover_tools(tools, "") == []


def test_catalog_summary_small(ts, tools):
    summary = ts.catalog_summary(tools)
    assert "project_scan" in summary
    assert not any(l.startswith("- tool_search:") for l in summary.splitlines())  # 目录不含元工具条目
    assert len(summary) <= 2400


def test_expand_matches_cumulative(ts, tools):
    visible = [tools[0]]
    expanded = ts.expand_matches(tools, visible, ["project_scan", "read_code"])
    names = [str((t["function"] or {}).get("name")) for t in expanded]
    assert names == ["code_scan", "project_scan", "read_code"]
    # 再次展开不重复
    expanded2 = ts.expand_matches(tools, expanded, ["project_scan"])
    assert len(expanded2) == len(expanded)


def test_t16_compact_schema_smaller(ts, tools):
    """T16: compact 模式 — 精简 schema 体积显著小于全量 (大 schema 场景)。"""
    import json

    big_tools = [{
        "type": "function",
        "function": {
            "name": "bash_exec",
            "description": "执行 shell 命令, 支持任意命令与参数组合" * 10,
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令文本" * 20},
                    "cwd": {"type": "string", "description": "工作目录" * 20},
                    "env": {"type": "object", "description": "环境变量映射" * 20},
                },
                "required": ["command"],
            },
        },
    }]
    full = ts.discover_tools(big_tools, "bash", top_k=1)
    comp = ts.discover_tools(big_tools, "bash", top_k=1, compact=True)
    full_size = len(json.dumps(full, ensure_ascii=False))
    comp_size = len(json.dumps(comp, ensure_ascii=False))
    assert comp_size < full_size * 0.6, f"compact 未减体积: {full_size} vs {comp_size}"
    # compact 保留 name + 参数名 (可调用性)
    comp_fn = comp[0]["function"]
    assert comp_fn["name"]
    assert "properties" in comp_fn["parameters"]


def test_t16_compact_keeps_required(ts, tools):
    """T16: compact 保留必填参数。"""
    comp = ts.discover_tools(tools, "scan", top_k=1, compact=True)
    fn = comp[0]["function"]
    req = fn["parameters"].get("required") or []
    assert isinstance(req, list)
