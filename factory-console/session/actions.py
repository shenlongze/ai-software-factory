"""factory-console/session/actions.py — 真实 Action 集 (S10-048 P0 + S10-049 P0/P2/P3): 调 Service Layer, 不复制业务。

create_project → 薄调 org.cli.cmd_project_register (同 cli_factory._proxy_org_cli 代理方式)
list_projects  → 只读 projects.json (复用 commands.read_projects — 同一数据口径)
show_status    → workspace/session/项目数 (会话内状态展示, 不复制 cli_factory.status 业务)
agent.execute_task (S10-049) → 薄调 exec.cli.cmd_exec_run (真实 Agent Runtime:
   LLM → 沙箱 → patch → 产物), 经 Agent Selector 选 agent, 产出 AgentExecutionResult
   (统一结构: success/agent/artifact/cost/duration/result_id/error) + 审计记录。

设计: docs/sprint10/S10-048-intent-kernel-design.md §2.3 / §2.7
     + docs/sprint10/S10-049-agent-execution-design.md §2.2-§2.6
边界:
- Action 只做薄调用 + 结果组装; 业务全在既有 Service Layer
- 失败安全: 底层异常 → ActionResult(error) 明确返回, 不吞不裸抛
- 渲染视图: data 含 header/rows (表格) 或键值字段, 经 ActionResult.to_dict 提升
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

from .action import (
    STATUS_ERROR,
    STATUS_OK,
    Action,
    ActionRegistry,
    ActionResult,
    ExecutionContext,
)
from .audit import record_execution
from .commands import read_projects
from .intent import IntentObject

#: 会话工作区缺省 (与 commands.DEFAULT_PROJECTS_FILE 同口径: ~/.factory)
DEFAULT_WORKSPACE = Path.home() / ".factory"

#: 前端任务特征关键词 (Agent Selector — 设计 §2.4)
_FRONTEND_KEYWORDS = ("前端", "flutter", "ui", "界面")

#: 默认 Agent (无特征/未显式指定 → backend-1)
DEFAULT_AGENT = "backend-1"

#: 前端 Agent
FRONTEND_AGENT = "flutter-dev"

#: 审计记录字段 (设计 §2.6): intent/action/agent/task/result/result_id/timestamp
_RECORD_KEYS = ("intent", "action", "agent", "task", "result", "result_id", "timestamp", "error")


@dataclass
class AgentExecutionResult:
    """Agent 执行统一结果结构 (设计 §2.5) — success/agent/artifact/cost/duration。

    artifact: patch/产物路径摘要; cost: usage 摘要; duration: 耗时字符串。
    result_id: 底层 Runtime 执行结果 id (审计/回放); error: 失败详情 (None = 成功)。
    """

    success: bool
    agent: str
    artifact: str = ""
    cost: str = ""
    duration: str = ""
    result_id: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """渲染/审计视图 (顶层契约字段 + 摘要键)。"""
        return {
            "success": self.success,
            "agent": self.agent,
            "artifact": self.artifact,
            "cost": self.cost,
            "duration": self.duration,
            "result_id": self.result_id,
            "error": self.error,
        }


@dataclass
class AgentExecutionContext(ExecutionContext):
    """Agent 执行上下文 (设计 §2.2) — 扩展 ExecutionContext + task_id/agent_id/project_id。

    继承: workspace/session/user/project/intent/metadata (S10-048);
    未来: permission/audit/cost_tracking。
    """

    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    project_id: Optional[str] = None


def _load_org_cli() -> Any:
    """延迟加载 org.cli (sys.path 挂 factory-org — 同 cli_factory._proxy_org_cli 薄代理)。

    返回模块对象 (测试可 monkeypatch 其 cmd_project_register 验证调用链)。
    """
    root = Path(__file__).resolve().parents[2]  # session/ → factory-console/ → 仓库根
    path = str(root / "factory-org")
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module("org.cli")


def _load_exec_cli() -> Any:
    """延迟加载 exec.cli (sys.path 挂 factory-exec — 同 _load_org_cli 薄代理)。

    cmd_exec_run(root, args) — 真实 Agent Runtime 链 (LLM → 沙箱 → patch → 产物)。
    args: project(目录, 必填)/task/objective/agent/employee/provider/test_cmd/json。
    """
    root = Path(__file__).resolve().parents[2]  # session/ → factory-console/ → 仓库根
    path = str(root / "factory-exec")
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module("exec.cli")


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


def select_agent(intent: Optional[IntentObject], context: Optional[ExecutionContext] = None) -> str:
    """Agent Selector 最小版 (设计 §2.4): params.agent_id 优先; 否则按 objective 关键词:
    前端/flutter/ui/界面 → flutter-dev; 其余 → backend-1。

    intent/context 均可为 None (失败安全 → 默认 backend-1)。
    """
    params = intent.parameters if intent is not None else {}
    agent = params.get("agent_id")
    if agent:
        return str(agent)
    objective = str(params.get("objective") or "").lower()
    if any(keyword in objective for keyword in _FRONTEND_KEYWORDS):
        return FRONTEND_AGENT
    return DEFAULT_AGENT


def _artifact_summary(artifacts: Any) -> str:
    """产物摘要: artifacts[0] 的 path/id (Runtime 产物 to_dict), 非 dict → str。"""
    if not artifacts:
        return ""
    first = artifacts[0]
    if isinstance(first, dict):
        return str(first.get("path") or first.get("id") or "")
    return str(first)


def _usage_summary(usage: Any) -> str:
    """usage 摘要 (cost/tokens), dict 取已知键; 非 dict/未知 → str (失败安全)。"""
    if not usage:
        return ""
    if isinstance(usage, dict):
        parts: list[str] = []
        for key in ("cost_usd", "cost", "total_cost"):
            if usage.get(key) is not None:
                parts.append(str(usage[key]))
        if usage.get("total_tokens"):
            parts.append(f"{usage['total_tokens']} tokens")
        return " · ".join(parts) or str(usage)
    return str(usage)


def _record_execution(
    context: AgentExecutionContext,
    execution: AgentExecutionResult,
    params: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """审计记录 (设计 §2.6): 写入 workspace/exec/execution_records.json (失败安全)。

    context 为 AgentExecutionContext (task_id/agent_id/project_id 扩展字段入审计);
    测试隔离: records 文件位于 context.workspace 下 (workspace 缺省 ~/.factory),
    审计失败不阻断执行 (record_execution 内部失败安全)。
    """
    try:
        record = {
            "intent": context.intent.intent_type if context.intent else "unknown",
            "action": "agent.execute_task",
            "agent": execution.agent,
            "task": str(params.get("objective") or context.task_id or ""),
            "result": "success" if execution.success else "failed",
            "result_id": execution.result_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": execution.error,
        }
        record_execution(
            record,
            records_file=Path(context.workspace) / "exec" / "execution_records.json",
        )
    except Exception:  # noqa: BLE001 — 失败安全: 审计失败不影响执行结果
        return


def execute_task(context: ExecutionContext) -> ActionResult:
    """执行开发任务 — 薄调 exec.cli.cmd_exec_run (真实 Agent Runtime, 设计 §2.1)。

    参数 (来自 context.intent.parameters): objective 任务描述; task_id/task;
    agent_id 显式指定 Agent; project 项目目录 (缺省 context.project → workspace)。

    流程: 参数提取 → Agent Selector → AgentExecutionContext 组装 → 薄调
    cmd_exec_run(root=workspace, args) → AgentExecutionResult 统一结构 →
    审计记录 → ActionResult (失败安全: 底层异常 → 明确错误)。
    """
    context.require("user")  # 基线权限 (action.permission="project" 由 RBAC 后续 Task 强制)
    params = context.intent.parameters if context.intent else {}
    objective = str(params.get("objective") or "")
    task_id = params.get("task_id") or params.get("task") or ""
    project_ref = str(params.get("project") or context.project or context.workspace)
    agent = select_agent(context.intent, context)
    exec_ctx = AgentExecutionContext(
        workspace=context.workspace,
        session=context.session,
        user=context.user,
        project=context.project,
        intent=context.intent,
        task_id=task_id or None,
        agent_id=params.get("agent_id"),
        project_id=params.get("project") or context.project,
    )
    if not objective and not task_id:
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message="任务执行失败: 缺少任务描述 (objective/task)",
            error="缺少任务描述 (objective/task)",
        )
    args = SimpleNamespace(
        project=project_ref,
        task=task_id,
        objective=objective,
        agent=agent,
        employee=params.get("employee"),
        provider=params.get("provider"),
        test_cmd=params.get("test_cmd"),
        json=True,
    )
    try:
        # root = workspace (缺省 ~/.factory = data_dir); 项目目录经 args.project 传入
        result = _load_exec_cli().cmd_exec_run(root=context.workspace, args=args)
    except Exception as exc:  # noqa: BLE001 — 失败安全: 底层异常 → 明确错误, 不裸抛
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"任务执行失败: {exc}",
            error=str(exc),
        )
    ok = bool(result.get("ok")) and result.get("exit_code", 1) == 0
    error = str(result.get("error") or "") if not ok else None
    usage = result.get("usage") or {}
    execution = AgentExecutionResult(
        success=ok,
        agent=agent,
        artifact=_artifact_summary(result.get("artifacts") or []),
        cost=_usage_summary(usage),
        duration=str(usage.get("duration") or result.get("duration") or ""),
        result_id=result.get("result_id"),
        error=error,
    )
    _record_execution(exec_ctx, execution, params, result)
    if ok:
        message = f"任务执行完成: {agent}"
        if execution.artifact:
            message += f" · 产物 {execution.artifact}"
        return ActionResult(
            ok=True,
            status=STATUS_OK,
            message=message,
            data={"execution": execution.to_dict()},
            error=None,
        )
    return ActionResult(
        ok=False,
        status=STATUS_ERROR,
        message=f"任务执行失败: {result.get('error', '未知原因')}",
        data={"execution": execution.to_dict()},
        error=error or "任务执行失败",
    )


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
    registry.register(
        Action(
            name="agent.execute_task",
            description="执行开发任务 → Agent Runtime (真实 LLM + 产物)",
            handler=execute_task,
            permission="project",
            metadata={
                "service": "exec.cli.cmd_exec_run (Agent Runtime)",
                "phase": "S10-049 P0",
                "sensitive": True,
                "category": "execution",
            },
        )
    )
    return registry
