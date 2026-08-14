"""factory-console/session/actions.py — 3 个真实 Action (S10-048 P0): 调 Service Layer, 不复制业务。

create_project → 薄调 org.cli.cmd_project_register (同 cli_factory._proxy_org_cli 代理方式)
list_projects  → 只读 projects.json (复用 commands.read_projects — 同一数据口径)
show_status    → workspace/session/项目数 (会话内状态展示, 不复制 cli_factory.status 业务)

设计: docs/sprint10/S10-048-intent-kernel-design.md §2.3 / §2.7
边界:
- Action 只做薄调用 + 结果组装; 业务全在既有 Service Layer
- 失败安全: 底层异常 → ActionResult(error) 明确返回, 不吞不裸抛
- 渲染视图: data 含 header/rows (表格) 或键值字段, 经 ActionResult.to_dict 提升
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .action import (
    STATUS_ERROR,
    STATUS_OK,
    Action,
    ActionRegistry,
    ActionResult,
    ExecutionContext,
)
from .commands import read_projects

#: 会话工作区缺省 (与 commands.DEFAULT_PROJECTS_FILE 同口径: ~/.factory)
DEFAULT_WORKSPACE = Path.home() / ".factory"


def _load_org_cli() -> Any:
    """延迟加载 org.cli (sys.path 挂 factory-org — 同 cli_factory._proxy_org_cli 薄代理)。

    返回模块对象 (测试可 monkeypatch 其 cmd_project_register 验证调用链)。
    """
    root = Path(__file__).resolve().parents[2]  # session/ → factory-console/ → 仓库根
    path = str(root / "factory-org")
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module("org.cli")


def create_project(context: ExecutionContext) -> ActionResult:
    """创建/注册项目 — 薄调 org.cli.cmd_project_register (Service Layer, 不复制业务)。

    参数 (来自 context.intent.parameters): name 项目名; repo_path 默认
    ExecutionContext.workspace (设计 §2.3: workspace 作为 --repo-path 默认)。
    """
    context.require("user")  # 基线权限; action.permission="project" 由 RBAC 后续 Task 强制
    params = context.intent.parameters if context.intent else {}
    repo_path = str(params.get("repo_path") or context.workspace)
    args = SimpleNamespace(
        repo_path=repo_path,
        name=params.get("name"),
        language=None,
        framework=None,
        build_command=None,
        test_command=None,
        project_type=None,
        goal=None,
        id=None,
    )
    try:
        result = _load_org_cli().cmd_project_register(root=context.workspace, args=args)
    except Exception as exc:  # noqa: BLE001 — 失败安全: 底层异常 → 明确错误
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"项目创建失败: {exc}",
            error=str(exc),
        )
    ok = bool(result.get("ok"))
    project = result.get("project") or {}
    return ActionResult(
        ok=ok,
        status=STATUS_OK if ok else STATUS_ERROR,
        message=(
            f"项目已注册: {project.get('name') or project.get('id') or '(未命名)'}"
            if ok
            else f"项目创建失败: {result.get('error', '未知原因')}"
        ),
        data={
            "project": project,
            "analysis_ref": result.get("analysis_ref"),
            "baseline_ref": result.get("baseline_ref"),
            "snapshot_ref": result.get("snapshot_ref"),
        },
        error=None if ok else str(result.get("error", "注册失败")),
    )


def list_projects(context: ExecutionContext) -> ActionResult:
    """项目清单 — 只读 projects.json (org 数据空间, 同 cli_factory._project_list 口径)。

    复用 commands.read_projects 解析 (失败安全: 缺失/损坏 → 空列表, 永不抛)。
    """
    context.require("user")
    projects_file = Path(context.workspace) / "org" / "projects.json"
    projects = read_projects(projects_file)
    rows = [[p["id"], p["name"]] for p in projects]
    return ActionResult(
        ok=True,
        status=STATUS_OK,
        message=f"共 {len(projects)} 个项目",
        data={
            "count": len(projects),
            "projects": projects,
            "header": ["id", "name"],  # 渲染视图 (HumanRenderer 表格)
            "rows": rows,
        },
    )


def show_status(context: ExecutionContext) -> ActionResult:
    """显示 Factory 状态 — workspace/session/项目数 (会话内状态, 薄读)。"""
    context.require("user")
    snap = context.session.to_dict()
    projects_file = Path(context.workspace) / "org" / "projects.json"
    projects = read_projects(projects_file)
    data: dict[str, Any] = {
        "workspace": str(context.workspace),
        "session_id": snap["session_id"],
        "current_project": snap["current_project"] or "(未选择)",
        "current_agent": snap["current_agent"] or "(未选择)",
        "history_count": len(snap["history"]),
        "project_count": len(projects),
        "user": context.user,
    }
    data["header"] = ["key", "value"]  # 渲染视图 (表格)
    data["rows"] = [[k, str(v)] for k, v in data.items() if k not in ("header", "rows")]
    return ActionResult(ok=True, status=STATUS_OK, message="Factory 状态", data=data)


def build_default_actions() -> ActionRegistry:
    """装配默认 Action 注册表 (注册式 — 新增 Action 只需 register 一行)。"""
    registry = ActionRegistry()
    registry.register(
        Action(
            name="create_project",
            description="创建/注册项目 (调 Service Layer: org project register)",
            handler=create_project,
            permission="project",
            metadata={"service": "org.cli.cmd_project_register", "phase": "S10-048 P0"},
        )
    )
    registry.register(
        Action(
            name="list_projects",
            description="列出项目 (只读 projects.json)",
            handler=list_projects,
            permission="user",
            metadata={"service": "projects.json (org 数据空间)", "phase": "S10-048 P0"},
        )
    )
    registry.register(
        Action(
            name="show_status",
            description="显示 Factory 状态 (workspace/session/项目数)",
            handler=show_status,
            permission="user",
            metadata={"service": "SessionContext + projects.json", "phase": "S10-048 P0"},
        )
    )
    return registry
