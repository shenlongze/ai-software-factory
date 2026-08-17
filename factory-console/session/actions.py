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
import json
import re
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
from .agents import AgentMatcher, AgentMetrics, AgentRegistry, workforce_snapshot
from .audit import record_execution
from .commands import read_projects
from .conflicts import ConflictDetector
from .dependencies import TaskDependencyGraph
from .intent import (
    INTENT_CREATE_PROJECT,
    INTENT_TEAM_CONFLICTS,
    INTENT_TEAM_DEPENDENCIES,
    INTENT_TEAM_EXECUTE,
    IntentObject,
)
from .orchestrator import ExecutionOrchestrator
from .pipeline import (
    AgentAssignment,
    EngineeringPlan,
    FeatureTaskGenerator,
    Lifecycle,
    ProductDocument,
    TaskTree,
)
from .product import (
    ProductIntent,
    generate_temp_product_name,
    parse_core_features,
)
from .progress import ProductProgressTracker
from .quality import RepairManager
from .teams import DEFAULT_TEAM_MEMBERS, TeamRegistry, TeamService
from .workspace import WorkspaceContext

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
    reason (S10-055 Task 004): AgentMatcher 可解释选择理由 (执行计划/对话消费)。
    """

    success: bool
    agent: str
    artifact: str = ""
    cost: str = ""
    duration: str = ""
    result_id: Optional[str] = None
    error: Optional[str] = None
    reason: str = ""

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
            "reason": self.reason,
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
        goal=params.get("goal"),  # S10-050: create_product 桥接传 product.problem 作 goal (org Project 必填)
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


def _slugify(text: str) -> str:
    """宽松 slug 化 (产品名 → 项目目录名; 同 org.space._slugify 口径)。

    非字母数字 → '-', 小写, 去首尾 '-' (路径目录推导, 非业务复制)。
    """
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").strip().lower()).strip("-")
    return slug


def _product_from_context(context: ExecutionContext) -> ProductIntent:
    """从上下文构建 ProductIntent: 会话 product_intent 优先; 否则 intent 参数。

    S10-050 P2 (设计 §2.5): create_product 直接执行入口 (确认流外/测试直调)
    也可用 — context.session.product_intent 存在 → 原样复用; 否则从
    context.intent.parameters 提取 (name/problem/user/platform/core_features)。
    """
    session = getattr(context, "session", None)
    product = getattr(session, "product_intent", None) if session is not None else None
    if product is not None:
        return product
    params = context.intent.parameters if context.intent else {}
    features = params.get("core_features") or []
    return ProductIntent(
        name=params.get("name"),
        problem=params.get("problem"),
        user=params.get("user"),
        platform=params.get("platform"),
        core_features=(
            list(features) if isinstance(features, list) else parse_core_features(features)
        ),
        raw=context.intent.raw if context.intent else "",
        session_id=getattr(session, "session_id", None),
    )


def create_product(context: ExecutionContext) -> ActionResult:
    """创建产品 (ProductIntent → 桥接 Project, S10-050 P2/P3)。

    1. 从 context.session.product_intent (或 intent.parameters) 构建 ProductIntent
    2. 完整性校验 — 缺失必填字段 → 明确错误 (列出缺失字段, 不静默)
    3. 桥接: 复用 create_project (薄调 org.cli.cmd_project_register) — 不复制业务
    4. product.json 落盘: projects/<name>/product.json (ProductIntent.to_dict)
    5. 返回 "Product Created: <name> — Ready for Engineering." + 产品摘要

    设计: docs/sprint10/S10-050-product-manager-design.md §2.5 / §2.6
    """
    context.require("user")  # 基线权限 (permission="project" 由 RBAC 后续 Task 强制)
    product = _product_from_context(context)
    missing = product.missing_fields()
    if missing:
        # 验收 F: 缺失字段 → 明确错误 (不静默)
        detail = ", ".join(missing)
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"产品创建失败: 产品信息不完整, 缺失: {detail}",
            error=f"产品信息不完整, 缺失: {detail}",
        )
    if not product.name:
        product.name = generate_temp_product_name()  # name 缺省 → 临时名
    # 桥接: 复用 create_project (薄调 org.cli.cmd_project_register, 不复制业务)
    bridge_intent = IntentObject(
        intent_type=INTENT_CREATE_PROJECT,
        params={"name": product.name, "goal": product.problem or ""},
        raw=product.raw,
        source="product",
    )
    bridge_ctx = ExecutionContext(
        workspace=context.workspace,
        session=context.session,
        user=context.user,
        project=context.project,
        intent=bridge_intent,
    )
    created = create_project(bridge_ctx)
    if not created.ok:
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"产品创建失败: {created.message}",
            error=created.error or created.message,
        )
    project = created.data.get("project") or {} if isinstance(created.data, dict) else {}
    # product.json 落盘: projects/<slug>/product.json (与 org project.json 同空间)
    slug = str(project.get("slug") or _slugify(product.name) or project.get("id") or "unnamed")
    product_dir = Path(context.workspace) / "projects" / slug
    product.status = "project_created"
    product_path = product_dir / "product.json"
    try:
        product_path.parent.mkdir(parents=True, exist_ok=True)
        product_path.write_text(product.to_json(), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 — 失败安全: 落盘异常 → 明确错误
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"产品创建失败: product.json 落盘失败: {exc}",
            error=str(exc),
        )
    return ActionResult(
        ok=True,
        status=STATUS_OK,
        message=f"Product Created: {product.name} — Ready for Engineering.",
        data={
            "product": product.to_dict(),
            "project": project,
            "product_file": str(product_path),
            "project_file": str(product_dir / "project.json"),
            "summary": product.to_summary(),
        },
        error=None,
    )


def _write_text_file(path: Path, content: str) -> None:
    """落盘文本资产 (父目录自动创建)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json_file(path: Path, data: dict[str, Any]) -> None:
    """落盘 JSON 资产 (ensure_ascii=False — 中文可读; 确定性无时间戳)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _read_json_file(path: Path) -> dict[str, Any]:
    """读取 JSON 资产 (失败 → 抛, 由调用方失败安全处理)。"""
    return json.loads(path.read_text(encoding="utf-8"))


def _find_product_dir(projects_root: Path, product: ProductIntent) -> Optional[str]:
    """扫描 projects/*/product.json 按 name 定位产品目录 (slug 推导失败的兜底)。"""
    for pfile in sorted(projects_root.glob("*/product.json")):
        try:
            data = _read_json_file(pfile)
        except Exception:  # noqa: BLE001 — 失败安全: 损坏文件跳过
            continue
        if data.get("name") == product.name:
            return pfile.parent.name
    return None


def _locate_product(
    context: ExecutionContext,
) -> tuple[Optional[ProductIntent], Optional[str], Path]:
    """定位当前产品与项目目录 (S10-051 资产读写共用)。

    优先级:
    ① context.session.current_project / context.project 显式指向 → projects/<slug>/product.json
    ② context.session.product_intent (会话产品流程产物) → name slug 或同名扫描
    ③ 扫描兜底: projects/*/product.json 最新一个

    返回 (ProductIntent | None, slug | None, projects_root) — 未找到 → (None, None, root)。
    """
    session = getattr(context, "session", None)
    product = getattr(session, "product_intent", None) if session is not None else None
    current_project = (
        getattr(session, "current_project", None) if session is not None else None
    )
    if not current_project:
        current_project = getattr(context, "project", None)
    projects_root = Path(context.workspace) / "projects"
    # ① 显式 current_project → 读 product.json
    if current_project:
        # S10-053 修正: current_project 可能是完整路径 → 取 basename 作 slug
        pslug = Path(str(current_project)).name or str(current_project)
        pdir = projects_root / pslug
        pfile = pdir / "product.json"
        if pfile.is_file():
            try:
                return (
                    ProductIntent.from_dict(_read_json_file(pfile)),
                    pslug,
                    projects_root,
                )
            except Exception:  # noqa: BLE001 — 失败安全: 损坏 → 继续其它路径
                pass
    # ② 会话 product_intent → name slug (或同名扫描兜底, 兼容中文产品名)
    if product is not None:
        slug = _slugify(product.name) if product.name else ""
        if not slug or not (projects_root / slug).is_dir():
            matched = _find_product_dir(projects_root, product)
            if matched is not None:
                slug = matched
        if not slug:
            return None, None, projects_root
        return product, slug, projects_root
    # ③ 扫描兜底: 最新 product.json
    matches = sorted(projects_root.glob("*/product.json"))
    if matches:
        latest = max(matches, key=lambda p: p.stat().st_mtime)
        try:
            return (
                ProductIntent.from_dict(_read_json_file(latest)),
                latest.parent.name,
                projects_root,
            )
        except Exception:  # noqa: BLE001 — 失败安全: 损坏 → 视为未找到
            return None, None, projects_root
    return None, None, projects_root


def generate_prd(context: ExecutionContext) -> ActionResult:
    """生成产品需求文档 (S10-051 P2): ProductIntent → PRD.md + product.json status=prd_ready。

    产品来源: session.product_intent / current_project / 扫描 (见 _locate_product)。
    纯规则生成 (pipeline.ProductDocument, 不调 LLM); 资产落盘 projects/<slug>/PRD.md。
    """
    context.require("user")
    product, slug, projects_root = _locate_product(context)
    if product is None or slug is None:
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message="PRD 生成失败: 未找到产品定义 (请先创建产品)",
            error="未找到产品定义 (请先创建产品)",
        )
    missing = product.missing_fields()
    if missing:
        detail = ", ".join(missing)
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"PRD 生成失败: 产品信息不完整, 缺失: {detail}",
            error=f"产品信息不完整, 缺失: {detail}",
        )
    prd_text = ProductDocument.from_product_intent(product)
    product_dir = projects_root / slug
    prd_path = product_dir / "PRD.md"
    product_file = product_dir / "product.json"
    product.status = "prd_ready"
    try:
        _write_text_file(prd_path, prd_text)
        existing = _read_json_file(product_file) if product_file.is_file() else {}
        _write_json_file(product_file, {**existing, **product.to_dict()})
    except Exception as exc:  # noqa: BLE001 — 失败安全: 落盘异常 → 明确错误
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"PRD 生成失败: 落盘失败: {exc}",
            error=str(exc),
        )
    return ActionResult(
        ok=True,
        status=STATUS_OK,
        message=f"PRD 已生成: {prd_path}",
        data={
            "prd_file": str(prd_path),
            "product_file": str(product_file),
            "sections": list(ProductDocument.SECTIONS),
            "status": product.status,
        },
        error=None,
    )


def prepare_project(context: ExecutionContext) -> ActionResult:
    """准备工程 (S10-051 P3 高级组合 Action): 一次生成全部管线资产。

    依次: generate_prd (PRD.md) → EngineeringPlan (engineering.json) →
    TaskTree (tasks.json) → AgentAssignment (execution_plan.json, 复用
    select_agent) → Lifecycle (project.json status=execution_ready)。

    返回 "Project Ready For Engineering." + 4 资产路径 (验收 F)。
    """
    context.require("user")
    product, slug, projects_root = _locate_product(context)
    if product is None or slug is None:
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message="工程准备失败: 未找到产品定义 (请先创建产品)",
            error="未找到产品定义 (请先创建产品)",
        )
    missing = product.missing_fields()
    if missing:
        detail = ", ".join(missing)
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"工程准备失败: 产品信息不完整, 缺失: {detail}",
            error=f"产品信息不完整, 缺失: {detail}",
        )
    product_dir = projects_root / slug
    # 1) PRD (ProductDocument — 规则生成)
    prd_text = ProductDocument.from_product_intent(product)
    prd_path = product_dir / "PRD.md"
    # 2) EngineeringPlan → engineering.json
    plan = EngineeringPlan.from_prd(product, prd_text)
    engineering_path = product_dir / "engineering.json"
    # 3) FeatureTaskGenerator → tasks.json (S10-055 Task 002: 功能级 Epic/Task,
    #    非模板化 db/api/frontend/test — 用户可感知功能; TaskTree 旧路径仍可用, 验收 H)
    tree = FeatureTaskGenerator.from_product(product)
    tasks_path = product_dir / "tasks.json"
    # 4) AgentAssignment → execution_plan.json (复用 select_agent: frontend→flutter-dev;
    #    feature/epic 归属透传 — Feature Level Execution 消费)
    execution = AgentAssignment.from_tasks(
        tree, select_agent_fn=select_agent, context=context
    )
    execution_path = product_dir / "execution_plan.json"
    # 5) Lifecycle: project.json status → execution_ready (保留既有 org 字段)
    project_path = product_dir / "project.json"
    product.status = Lifecycle.EXECUTION_READY
    try:
        _write_text_file(prd_path, prd_text)
        _write_json_file(engineering_path, plan)
        _write_json_file(tasks_path, tree)
        _write_json_file(execution_path, execution)
        existing_project = (
            _read_json_file(project_path) if project_path.is_file() else {}
        )
        _write_json_file(
            project_path,
            {
                **existing_project,
                "name": product.name,
                "status": Lifecycle.EXECUTION_READY,
            },
        )
        product_file = product_dir / "product.json"
        existing_product = _read_json_file(product_file) if product_file.is_file() else {}
        _write_json_file(product_file, {**existing_product, **product.to_dict()})
    except Exception as exc:  # noqa: BLE001 — 失败安全: 落盘异常 → 明确错误
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"工程准备失败: 资产落盘失败: {exc}",
            error=str(exc),
        )
    return ActionResult(
        ok=True,
        status=STATUS_OK,
        message="Project Ready For Engineering.",
        data={
            "prd_file": str(prd_path),
            "engineering_file": str(engineering_path),
            "tasks_file": str(tasks_path),
            "execution_file": str(execution_path),
            "project_file": str(project_path),
            "status": Lifecycle.EXECUTION_READY,
        },
        error=None,
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


def _agent_reason_for(agent: str, objective: str) -> str:
    """AgentMatcher 可解释选择理由 (S10-055 Task 004) — 失败安全: 计算失败 → ""。

    以 objective 为任务输入 (agent 已由 select_agent 决定, 本函数只产 reason,
    不改变决策); 供 execute_task 结果 / 审计 / 对话消费。
    """
    try:
        match = AgentMatcher().reason_for(
            agent, {"name": objective, "objective": objective}
        )
        return str(match.get("reason") or "")
    except Exception:  # noqa: BLE001 — 失败安全: reason 缺失不阻断执行
        return ""


def _workspace_agents_file(workspace: Any) -> Optional[Path]:
    """工作区 Agent 注册表 (workspace/agents/agents.json); 不存在 → None (默认注册表)。

    Workforce Dashboard / Matcher 优先读工作区数据 (测试隔离), 无则回落
    ~/.factory/agents/agents.json (真实数据空间, 同 commands.DEFAULT_PROJECTS_FILE 口径)。
    """
    path = Path(workspace) / "agents" / "agents.json"
    return path if path.is_file() else None


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
    # S10-055 Task 004: AgentMatcher 可解释理由 (失败安全 → "", 不改变决策)
    reason = _agent_reason_for(agent, objective)
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
        reason=reason,
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


def execute_project(context: ExecutionContext) -> ActionResult:
    """执行项目 (S10-052 P2): execution_plan.json → 任务队列 → Lifecycle 推进。

    \"开始开发/开始执行/执行项目\" → 确认门 (sensitive) → 本项目:
    1. 定位产品 (复用 _locate_product) + Lifecycle 检查 (需 EXECUTION_READY
       或 DEVELOPMENT — 可恢复; 已交付/测试中 → 明确拒绝)
    2. ExecutionOrchestrator: 有未完成任务 (execution_state.json 存在 pending/
       failed) → resume 恢复; 否则 → execute_project 全新执行
    3. ExecutionResult → ActionResult (失败安全: 底层异常 → 明确错误)

    任务执行复用 execute_task (orchestrator._default_execute_fn 薄调, 验收 H)。
    """
    context.require("user")  # 基线权限 (action.permission="project" 由 RBAC 后续 Task 强制)
    product, slug, projects_root = _locate_product(context)
    if product is None or slug is None:
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message="执行项目失败: 未找到产品定义 (请先创建产品)",
            error="未找到产品定义 (请先创建产品)",
        )
    # Lifecycle 检查 (设计 §8): 需 EXECUTION_READY 或 DEVELOPMENT (可恢复)
    project_dir = projects_root / slug
    project_file = project_dir / "project.json"
    status: Optional[str] = None
    if project_file.is_file():
        try:
            status = str(_read_json_file(project_file).get("status") or "")
        except Exception:  # noqa: BLE001 — 损坏 → 不阻塞 (orchestrator 为准)
            status = None
    allowed = (Lifecycle.EXECUTION_READY, Lifecycle.DEVELOPMENT)
    if status and status not in allowed:
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=(
                f"执行项目失败: 项目当前状态 {status!r}, "
                f"需 {Lifecycle.EXECUTION_READY!r} 或 {Lifecycle.DEVELOPMENT!r}"
            ),
            error=f"项目状态 {status!r} 不允许执行",
        )
    orchestrator = ExecutionOrchestrator(context.workspace)
    try:
        if orchestrator.needs_resume(slug):
            result = orchestrator.resume(slug)
        else:
            result = orchestrator.execute_project(slug)
    except Exception as exc:  # noqa: BLE001 — 失败安全: 底层异常 → 明确错误
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"执行项目失败: {exc}",
            error=str(exc),
        )
    ok = result.failed_tasks == 0
    message = (
        f"项目执行完成: {result.project} — {result.completed_tasks} 任务完成"
        if ok
        else f"项目执行未完成: {result.failed_tasks} 任务失败 (可再次开始开发恢复)"
    )
    return ActionResult(
        ok=ok,
        status=STATUS_OK if ok else STATUS_ERROR,
        message=message,
        data=result.to_dict(),
        error=None if ok else ("; ".join(result.errors) or "任务执行失败"),
    )


def repair_task(context: ExecutionContext) -> ActionResult:
    """修复失败任务 (S10-053 P3): \"修复失败任务/修复任务\" → 确认门 → RepairManager。

    流程:
    1. 定位产品 (复用 _locate_product) → project_dir
    2. 读 repair_task.json → 无 pending → 明确提示 (幂等, 不报错)
    3. RepairManager.repair — execute_fn 缺省薄调 execute_task
       (orchestrator._default_execute_fn 复用 Agent Runtime, 验收 H)
    4. 返回修复结果 {repair_id, status: completed/failed/none, retry_count}

    Retry Policy (设计 §5): max_retry=1 — 修复重试 1 次仍失败 → failed (不无限循环)。
    """
    context.require("user")
    product, slug, projects_root = _locate_product(context)
    if product is None or slug is None:
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message="修复任务失败: 未找到产品定义 (请先创建产品)",
            error="未找到产品定义 (请先创建产品)",
        )
    project_dir = projects_root / slug
    repairs = RepairManager.load_repairs(project_dir)
    if not any(r.get("status") == "pending" for r in repairs):
        return ActionResult(
            ok=True,
            status=STATUS_OK,
            message=f"修复任务: 无待修复任务 (已处理 {len(repairs)} 条)",
            data={
                "project": slug,
                "repair_id": None,
                "status": "none",
                "repairs_total": len(repairs),
            },
            error=None,
        )
    try:
        result = RepairManager().repair(project_dir)
    except Exception as exc:  # noqa: BLE001 — 失败安全: 底层异常 → 明确错误
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"修复任务失败: {exc}",
            error=str(exc),
        )
    ok = result.get("status") == "completed"
    status_label = {
        "completed": "修复完成",
        "failed": "修复失败 (已达最大重试次数)",
        "retrying": "修复重试中",
    }.get(result.get("status"), "无待修复任务")
    retries = int(result.get("retry_count") or 0)
    message = (
        f"修复任务: {status_label} — 重试 {retries} 次"
        if ok
        else f"修复任务: {status_label} (重试 {retries} 次)"
    )
    validation = result.get("validation")
    validation_errors = (
        validation.get("errors") if isinstance(validation, dict) else None
    )
    return ActionResult(
        ok=ok,
        status=STATUS_OK if ok else STATUS_ERROR,
        message=message,
        data={
            "project": slug,
            "repair_id": result.get("repair_id"),
            "status": result.get("status"),
            "retry_count": retries,
            "validation": validation,
        },
        error=None if ok else validation_errors,
    )


def project_progress(context: ExecutionContext) -> ActionResult:
    """查询项目执行进度 (S10-052 P4 + S10-053 P6 + S10-055 Task 003/004): 只读。

    "项目进度/进度如何/执行到哪了" → 非敏感查询 → 汇总
    {project, status, lifecycle, tasks_total, completed, running, pending,
    failed, agents} + S10-053 增强 (验收 H): validation {passed, failed,
    not_run} + repair {pending, done, failed} + S10-055 增强 (验收 D):
    features (功能级完成度) + product_progress (product_progress.json 内容,
    同步落盘 — 回答 "做到哪里")。
    """
    context.require("user")
    product, slug, projects_root = _locate_product(context)
    if product is None or slug is None:
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message="进度查询失败: 未找到产品定义 (请先创建产品)",
            error="未找到产品定义 (请先创建产品)",
        )
    orchestrator = ExecutionOrchestrator(context.workspace)
    try:
        progress = orchestrator.get_progress(slug)
    except Exception as exc:  # noqa: BLE001 — 失败安全: 底层异常 → 明确错误
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"进度查询失败: {exc}",
            error=str(exc),
        )
    # S10-055 Task 003: 功能级进度文档 (product_progress.json 落盘 — 失败安全:
    # 进度查询不因落盘失败阻断)
    project_dir = projects_root / slug
    progress_doc: dict[str, Any] = {
        "product": product.name or slug,
        "status": "pending",
        "tasks_total": 0,
        "tasks_completed": 0,
        "features": [],
    }
    state_file = project_dir / "execution_state.json"
    try:
        if state_file.is_file():
            state_doc = _read_json_file(state_file)
            progress_doc = ProductProgressTracker.update_from_execution(
                state_doc, product_name=product.name or slug
            )
        else:
            tasks_file = project_dir / "tasks.json"
            tasks = (
                _read_json_file(tasks_file).get("tasks") or []
                if tasks_file.is_file()
                else []
            )
            progress_doc = ProductProgressTracker.init(product, tasks)
        ProductProgressTracker.save(project_dir, progress_doc)
    except Exception:  # noqa: BLE001 — 失败安全: 功能进度计算/落盘失败不影响查询
        pass
    data: dict[str, Any] = {
        **progress,
        "features": progress_doc.get("features") or [],
        "product_progress": progress_doc,
    }
    total = progress.get("tasks_total") or 0
    completed = progress.get("completed") or 0
    if progress.get("status") == "not_started":
        message = f"项目进度: 尚未开始执行 (共 {total} 个任务)"
    else:
        message = f"项目进度: {completed}/{total} 完成"
    return ActionResult(
        ok=True,
        status=STATUS_OK,
        message=message,
        data=data,
        error=None,
    )


def accept_project(context: ExecutionContext) -> ActionResult:
    """项目验收 (S10-055 Task 005, 验收 G): "通过验收/验收通过" → 确认门 → DELIVERED。

    流程:
    1. 定位产品 (复用 _locate_product)
    2. ExecutionOrchestrator.accept_project — 仅 lifecycle=user_acceptance
       (执行完成 + 验证通过后停在待验收) 可验收 → DELIVERED;
       其它状态 → 明确拒绝 (不静默推进)
    3. 成功 → "项目已验收交付: <slug>" + {project, status: delivered}
    """
    context.require("user")
    product, slug, projects_root = _locate_product(context)
    if product is None or slug is None:
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message="项目验收失败: 未找到产品定义 (请先创建产品)",
            error="未找到产品定义 (请先创建产品)",
        )
    orchestrator = ExecutionOrchestrator(context.workspace)
    try:
        accepted = orchestrator.accept_project(slug)
    except Exception as exc:  # noqa: BLE001 — 失败安全: 底层异常 → 明确错误
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"项目验收失败: {exc}",
            error=str(exc),
        )
    if not accepted:
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message="项目验收失败: 项目尚未到达待验收状态 (需执行完成且验证通过)",
            error="项目未处于 user_acceptance 状态 (无法验收)",
        )
    return ActionResult(
        ok=True,
        status=STATUS_OK,
        message=f"项目已验收交付: {slug}",
        data={
            "project": slug,
            "status": Lifecycle.DELIVERED,
            "lifecycle": Lifecycle.DELIVERED,
        },
        error=None,
    )



def governance_status(context: ExecutionContext) -> ActionResult:
    """factory status — 项目生产状态总览 (S10-063): status/plan_version/
    completed/running/pending/token_usage/estimated_cost/budget/review。
    只读查询 (非敏感, 无确认门)。失败安全: 无项目 → 友好空态。
    """
    context.require("user")
    workspace = Path(context.workspace or ".")
    try:
        rows = []
        projects_dir = workspace / "projects"
        if projects_dir.is_dir():
            for pd in sorted(projects_dir.iterdir()):
                if not pd.is_dir():
                    continue
                state_file = pd / "execution_state.json"
                if not state_file.is_file():
                    continue
                import json as _json
                try:
                    state = _json.loads(state_file.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                rows.append([
                    pd.name,
                    state.get("status") or state.get("lifecycle") or "-",
                    str(state.get("plan_version") or 1),
                    str(state.get("governance_status") or "-"),
                ])
        if not rows:
            return ActionResult(ok=True, status=STATUS_OK, message="暂无生产项目。")
        lines = ["项目 | 状态 | 计划版本 | 治理状态"] + [" | ".join(r) for r in rows]
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines))
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR, message=f"状态查询失败: {exc}", error=str(exc))


def governance_budget(context: ExecutionContext) -> ActionResult:
    """factory budget — 预算查询 (S10-063): cost_records.json 聚合 →
    spent/remaining/ratio/level。只读查询。失败安全: 无记录 → 空态。
    """
    context.require("user")
    workspace = Path(context.workspace or ".")
    try:
        from .cost_ledger import CostLedger
        from .budget import ProjectBudget, BudgetUsage, BudgetEnforcer
        ledger = CostLedger(file=workspace / "cost" / "cost_records.json")
        records = ledger.records()
        budget = ProjectBudget()
        usage = BudgetUsage.from_records(records, budget=budget)
        level = BudgetEnforcer.check(budget, usage)["level"]
        lines = [
            f"总消耗: {usage.total_cost:.4f} USD / {usage.total_tokens} tokens",
            f"LLM 调用: {usage.llm_calls} | 重规划: {usage.replans} | 重试: {usage.retries}",
            f"预算等级: {level}",
        ]
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(ok=False, status=STATUS_ERROR, message=f"预算查询失败: {exc}", error=str(exc))


def governance_review(context: ExecutionContext) -> ActionResult:
    """factory review — 待审列表 + approve/reject (S10-063 ReviewGate)。
    context.params: review_id (可选) + decision ("approve"/"reject") + reviewer。
    敏感确认门: approve/reject 需确认。
    """
    context.require("user")
    workspace = Path(context.workspace or ".")
    params = context.params or {}
    review_id = str(params.get("review_id") or "")
    decision = str(params.get("decision") or "")
    try:
        from .review_gate import ReviewGate
        gate = ReviewGate(file=workspace / "cost" / "review_records.json")
        if review_id and decision in ("approve", "reject"):
            reviewer = str(params.get("reviewer") or "user")
            rec = gate.approve(review_id, reviewer) if decision == "approve" else gate.reject(review_id, reviewer)
            return ActionResult(ok=True, status=STATUS_OK, message=f"评审 {review_id} → {rec.status}")
        pending = gate.pending()
        if not pending:
            return ActionResult(ok=True, status=STATUS_OK, message="无待审评审。")
        lines = ["review_id | reason | trigger | risk"] + [
            f"{r.review_id} | {r.reason[:30]} | {r.trigger} | {r.risk}" for r in pending
        ]
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(ok=False, status=STATUS_ERROR, message=f"评审查询失败: {exc}", error=str(exc))


def workforce(context: ExecutionContext) -> ActionResult:
    """Workforce Dashboard (S10-055 Task 005, 验收 E): "查看团队/团队状态" → 团队状态。

    只读查询 (非敏感, 无确认门): AgentRegistry (工作区 agents.json 优先, 无 →
    默认注册表) + AgentMetrics (工作区 agent_metrics.json / execution_records.json
    优先, 无 → 真实记录聚合) 合并 → agents [{id, name, role, status, success_rate,
    total_tasks, avg_cost}] (按 id 排序) + 渲染视图 (header/rows)。
    失败安全: 数据缺失 → 默认注册表/空绩效, 不抛。
    """
    context.require("user")
    agents_file = _workspace_agents_file(context.workspace)
    records_file = Path(context.workspace) / "exec" / "execution_records.json"
    metrics_file = Path(context.workspace) / "exec" / "agent_metrics.json"
    try:
        rows = workforce_snapshot(
            agents_file=agents_file,
            records_file=records_file if records_file.is_file() else None,
            metrics_file=metrics_file if metrics_file.is_file() else None,
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全: 聚合异常 → 明确错误
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"团队状态查询失败: {exc}",
            error=str(exc),
        )
    table_rows = [
        [
            row["id"],
            row["role"],
            row["status"],
            (
                f"{row['success_rate'] * 100:.0f}%"
                if row["success_rate"] is not None
                else "-"
            ),
            row["total_tasks"],
        ]
        for row in rows
    ]
    return ActionResult(
        ok=True,
        status=STATUS_OK,
        message=f"团队共 {len(rows)} 名 Agent",
        data={
            "count": len(rows),
            "agents": rows,
            "header": ["id", "role", "status", "success_rate", "total_tasks"],
            "rows": table_rows,
        },
        error=None,
    )


def task_owner(context: ExecutionContext) -> ActionResult:
    """任务负责人 (S10-055 Task 006, 验收 F): "谁负责这个任务" → 最近任务 Agent。

    只读查询: ① 当前项目 execution_state.json 最近任务 (有 agent 的最后一个) →
    agent; ② 兜底: 工作区 execution_records.json 最近执行记录 → agent;
    ③ 仍无 → agent=None + 明确提示 (查询成功, 数据为空, 不报错)。
    返回 {agent, task, project} + 消息 "最近任务「X」由 Y 负责"。
    """
    context.require("user")
    agent: Optional[str] = None
    task_name: Optional[str] = None
    project: Optional[str] = None
    product, slug, projects_root = _locate_product(context)
    if slug:
        state_file = projects_root / slug / "execution_state.json"
        try:
            if state_file.is_file():
                state = _read_json_file(state_file)
                for task in reversed(state.get("tasks") or []):
                    if task.get("agent") and str(task.get("agent")) != "None":
                        agent = str(task["agent"])
                        task_name = str(task.get("name") or task.get("id") or "")
                        project = slug
                        break
        except Exception:  # noqa: BLE001 — 失败安全: 状态损坏 → 回落执行记录
            pass
    if agent is None:
        try:
            from .audit import load_records as _load_records

            records = _load_records(
                Path(context.workspace) / "exec" / "execution_records.json"
            )
            for record in reversed(records):
                if record.get("agent") and str(record.get("agent")) != "None":
                    agent = str(record["agent"])
                    task_name = str(record.get("task") or "")
                    project = str(record.get("project") or "")
                    break
        except Exception:  # noqa: BLE001 — 失败安全: 记录损坏 → agent=None
            pass
    if agent is None:
        return ActionResult(
            ok=True,
            status=STATUS_OK,
            message="未找到任务负责人 (尚无执行记录)",
            data={"agent": None, "task": None, "project": None},
            error=None,
        )
    message = f"最近任务「{task_name or '未知任务'}」由 {agent} 负责"
    if project:
        message += f" (项目 {project})"
    return ActionResult(
        ok=True,
        status=STATUS_OK,
        message=message,
        data={"agent": agent, "task": task_name, "project": project},
        error=None,
    )


def agent_reason(context: ExecutionContext) -> ActionResult:
    """Agent 选择理由 (S10-055 Task 006, 验收 G): "为什么选择" → execution_plan reason。

    只读查询: 当前项目 execution_plan.json 中第一个带 reason 的任务 →
    {agent, task, reason} + 消息 "选择 X 的理由: <reason>"。
    无 plan / 无 reason → agent=None + 明确提示 (查询成功, 数据为空, 不报错)。
    """
    context.require("user")
    product, slug, projects_root = _locate_product(context)
    if slug is None:
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message="查询失败: 未找到产品定义 (请先创建产品)",
            error="未找到产品定义 (请先创建产品)",
        )
    reason: Optional[str] = None
    agent: Optional[str] = None
    task_name: Optional[str] = None
    plan_file = projects_root / slug / "execution_plan.json"
    try:
        if plan_file.is_file():
            plan = _read_json_file(plan_file)
            for task in plan.get("tasks") or []:
                if task.get("reason"):
                    reason = str(task["reason"])
                    agent = str(task.get("agent") or "")
                    task_name = str(task.get("name") or task.get("id") or "")
                    break
    except Exception:  # noqa: BLE001 — 失败安全: plan 损坏 → 无 reason
        reason = None
    if not reason:
        return ActionResult(
            ok=True,
            status=STATUS_OK,
            message="未找到 Agent 选择理由 (execution_plan.json 无 reason)",
            data={"agent": None, "task": None, "reason": None},
            error=None,
        )
    return ActionResult(
        ok=True,
        status=STATUS_OK,
        message=f"选择 {agent} 的理由: {reason}",
        data={"agent": agent, "task": task_name, "reason": reason},
        error=None,
    )


def _team_metrics(context: ExecutionContext) -> dict[str, Any]:
    """团队协作视图绩效源: 工作区 agent_metrics.json 优先, 无 → records 聚合。

    同 workforce 口径 (metrics_file → records_file → 真实记录聚合), 失败安全。
    """
    records_file = Path(context.workspace) / "exec" / "execution_records.json"
    metrics_file = Path(context.workspace) / "exec" / "agent_metrics.json"
    if metrics_file.is_file():
        return AgentMetrics.load(metrics_file)
    if records_file.is_file():
        return AgentMetrics.load_from_records(records_file)
    return AgentMetrics.load_from_records()


def _pct(value: Any) -> str:
    """success_rate 渲染: 数字 → 百分比; 缺省/非数字 → 占位 \"-\"。"""
    if isinstance(value, (int, float)):
        return f"{value * 100:.0f}%"
    return "-"


def _team_view(context: ExecutionContext) -> ActionResult:
    """团队协作视图 (验收 E): 默认团队 software-team → team_snapshot 渲染。

    TeamRegistry (工作区 teams.json 优先, 无 → 默认团队) + AgentRegistry
    (工作区 agents.json) + AgentMetrics (工作区绩效) 合并 → members [{agent,
    role, status, success_rate, total_tasks, current_task}] + 渲染 (header/rows)。
    失败安全: 数据缺失 → 默认团队/占位 \"-\", 不抛。
    """
    context.require("user")
    agents_file = _workspace_agents_file(context.workspace)
    teams_file = Path(context.workspace) / "teams" / "teams.json"
    try:
        registry = AgentRegistry.load(agents_file)
        team = TeamRegistry.get("software-team", teams_file=teams_file)
        if team is None:
            team = TeamRegistry.build_default_team(agents_file=agents_file)
        snapshot = TeamService.team_snapshot(team, registry, _team_metrics(context))
    except Exception as exc:  # noqa: BLE001 — 失败安全: 聚合异常 → 明确错误
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"团队视图查询失败: {exc}",
            error=str(exc),
        )
    members = snapshot["members"]
    table_rows = [
        [
            m["agent"],
            m["role"],
            m["status"],
            _pct(m["success_rate"]),
            m["total_tasks"],
            m["current_task"],
        ]
        for m in members
    ]
    return ActionResult(
        ok=True,
        status=STATUS_OK,
        message=f"团队「{snapshot['name']}」共 {len(members)} 名成员",
        data={
            "team": snapshot,
            "count": len(members),
            "members": members,
            "header": ["agent", "role", "status", "success_rate", "total_tasks", "current_task"],
            "rows": table_rows,
        },
        error=None,
    )


def _team_create(context: ExecutionContext, raw: str) -> ActionResult:
    """创建团队 (验收 F): \"创建团队 <name>\" → TeamRegistry.create + add。

    名称来源: ① intent.raw 关键词后剩余文本; ② intent.parameters[\"name\"] 兜底;
    缺名称 → 明确引导 (不静默)。新团队默认采用标准 5 角色编制
    (DEFAULT_TEAM_MEMBERS — 同默认团队, 可后续按需调整)。
    """
    context.require("user")
    name = raw.split("创建团队", 1)[1].strip() if "创建团队" in raw else ""
    if not name:
        params = context.intent.parameters if context.intent else {}
        name = str(params.get("name") or "").strip()
    if not name:
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message="团队创建失败: 请提供团队名称 (例如: 创建团队 电商后端团队)",
            error="缺少团队名称",
        )
    team_id = _slugify(name) or name or "team"
    teams_file = Path(context.workspace) / "teams" / "teams.json"
    try:
        created = TeamRegistry.create(
            team_id,
            name,
            members=[dict(m) for m in DEFAULT_TEAM_MEMBERS],
            teams_file=teams_file,
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全: 创建异常 → 明确错误
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"团队创建失败: {exc}",
            error=str(exc),
        )
    return ActionResult(
        ok=True,
        status=STATUS_OK,
        message=f"团队已创建: {name} ({team_id})",
        data={"team": created, "team_id": team_id, "name": name},
        error=None,
    )


def _team_execute(context: ExecutionContext) -> ActionResult:
    """团队模式执行项目 (S10-056 批次 B): \"团队执行 <项目>\" → execute_project(mode=\"team\")。

    定位: raw 中 \"团队执行\" 后文本为项目名 (product.json name 扫描); 缺名称 →
    _locate_product 兜底 (会话 current_project / 最新产品)。Lifecycle 检查同
    execute_project (需 EXECUTION_READY/DEVELOPMENT)。

    执行: ExecutionOrchestrator.execute_project(mode=\"team\", 注入工作区
    teams/agents/task_dependencies/conflicts 资产路径) — 团队成员角色匹配
    (required_role → RoleSystem.role_matches + AgentMatcher) + 依赖拓扑排序
    (TaskDependencyGraph) + 冲突检测记录 (ConflictDetector, 不阻塞)。

    结果: ExecutionResult + mode/team_id + conflicts (conflicts.json 读取)
    + assignments (execution_state.json 任务 → agent) 汇总 (失败安全读取)。
    """
    context.require("user")
    raw = context.intent.raw if context.intent else ""
    name = raw.split("团队执行", 1)[1].strip() if "团队执行" in raw else ""
    projects_root = Path(context.workspace) / "projects"
    slug: Optional[str] = None
    if name:
        matched = _find_product_dir(projects_root, ProductIntent(name=name))
        if matched is not None:
            slug = matched
    if slug is None:
        product, slug, _ = _locate_product(context)
        if product is None or slug is None:
            return ActionResult(
                ok=False,
                status=STATUS_ERROR,
                message="团队执行失败: 未找到产品定义 (请先创建产品)",
                error="未找到产品定义 (请先创建产品)",
            )
    # Lifecycle 检查 (同 execute_project — 需 EXECUTION_READY 或 DEVELOPMENT)
    project_dir = projects_root / slug
    project_file = project_dir / "project.json"
    status: Optional[str] = None
    if project_file.is_file():
        try:
            status = str(_read_json_file(project_file).get("status") or "")
        except Exception:  # noqa: BLE001 — 损坏 → 不阻塞 (orchestrator 为准)
            status = None
    allowed = (Lifecycle.EXECUTION_READY, Lifecycle.DEVELOPMENT)
    if status and status not in allowed:
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=(
                f"团队执行失败: 项目当前状态 {status!r}, "
                f"需 {Lifecycle.EXECUTION_READY!r} 或 {Lifecycle.DEVELOPMENT!r}"
            ),
            error=f"项目状态 {status!r} 不允许执行",
        )
    orchestrator = ExecutionOrchestrator(context.workspace)
    teams_file = Path(context.workspace) / "teams" / "teams.json"
    dependencies_file = Path(context.workspace) / "teams" / "task_dependencies.json"
    conflicts_file = Path(context.workspace) / "teams" / "conflicts.json"
    try:
        result = orchestrator.execute_project(
            slug,
            mode="team",
            teams_file=teams_file,
            agents_file=_workspace_agents_file(context.workspace),
            dependencies_file=dependencies_file,
            conflicts_file=conflicts_file,
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全: 底层异常 → 明确错误
        return ActionResult(
            ok=False,
            status=STATUS_ERROR,
            message=f"团队执行失败: {exc}",
            error=str(exc),
        )
    ok = result.failed_tasks == 0
    team_id, conflicts, assignments = _team_run_summary(
        context.workspace, slug, teams_file, conflicts_file
    )
    message = (
        f"团队执行完成: {result.project} — {result.completed_tasks} 任务完成 ({team_id})"
        if ok
        else f"团队执行未完成: {result.failed_tasks} 任务失败 (可再次团队执行恢复)"
    )
    return ActionResult(
        ok=ok,
        status=STATUS_OK if ok else STATUS_ERROR,
        message=message,
        data={
            **result.to_dict(),
            "mode": "team",
            "team_id": team_id,
            "conflicts": conflicts,
            "assignments": assignments,
        },
        error=None if ok else ("; ".join(result.errors) or "任务执行失败"),
    )


def _team_run_summary(
    workspace: Any,
    slug: str,
    teams_file: Path,
    conflicts_file: Path,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """团队执行汇总 (失败安全): team_id + conflicts + assignments 资产读取。"""
    team_id = "software-team"
    try:
        team = TeamRegistry.load(teams_file).get("software-team")
        if team:
            team_id = str(team.get("team_id") or team_id)
    except Exception:  # noqa: BLE001 — 失败安全: 团队读取失败 → 默认 id
        pass
    conflicts: list[dict[str, Any]] = []
    try:
        conflicts = ConflictDetector(conflicts_file=conflicts_file).list()
    except Exception:  # noqa: BLE001 — 失败安全: 冲突读取失败 → 空列表
        conflicts = []
    assignments: list[dict[str, Any]] = []
    try:
        state_file = Path(workspace) / "projects" / slug / "execution_state.json"
        if state_file.is_file():
            state = _read_json_file(state_file)
            assignments = [
                {
                    "id": str(t.get("id") or ""),
                    "agent": str(t.get("agent") or ""),
                    "status": str(t.get("status") or ""),
                }
                for t in (state.get("tasks") or [])
                if isinstance(t, dict)
            ]
    except Exception:  # noqa: BLE001 — 失败安全: 状态读取失败 → 空列表
        assignments = []
    return team_id, conflicts, assignments


def _team_dependencies(context: ExecutionContext) -> ActionResult:
    """团队依赖视图 (S10-056 批次 B): \"团队依赖/依赖关系\" → TaskDependencyGraph 只读。

    task_dependencies.json (工作区 teams/ 优先, 缺失 → 空图) → {dependencies,
    tasks, topological_order} + 渲染 (task/depends_on 表格)。失败安全: 缺失/损坏
    → 空依赖图, 不抛。
    """
    context.require("user")
    file = Path(context.workspace) / "teams" / "task_dependencies.json"
    graph = TaskDependencyGraph.load(file) if file.is_file() else TaskDependencyGraph()
    deps = graph.to_dict()
    ordered = graph.topological_order(list(deps.keys()))
    rows = [[t, ", ".join(deps[t]) or "-"] for t in sorted(deps)]
    return ActionResult(
        ok=True,
        status=STATUS_OK,
        message=f"任务依赖图: {len(deps)} 个节点 (拓扑顺序 {len(ordered)})",
        data={
            "dependencies": deps,
            "tasks": list(deps.keys()),
            "topological_order": ordered,
            "header": ["task", "depends_on"],
            "rows": rows,
        },
        error=None,
    )


def _team_conflicts(context: ExecutionContext) -> ActionResult:
    """团队冲突视图 (S10-056 批次 B): \"团队冲突/文件冲突\" → ConflictDetector 只读。

    conflicts.json (工作区 teams/) → {conflicts, count} + 渲染 (task_a/task_b/
    file/status 表格)。只检测不解决 — status 恒 open (设计 §2.7 / 边界 §7)。
    失败安全: 缺失/损坏 → 空记录, 不抛。
    """
    context.require("user")
    file = Path(context.workspace) / "teams" / "conflicts.json"
    detector = ConflictDetector(conflicts_file=file)
    records = detector.list()
    rows = [[r["task_a"], r["task_b"], r["file"], r["status"]] for r in records]
    return ActionResult(
        ok=True,
        status=STATUS_OK,
        message=f"文件冲突: {len(records)} 条记录 (检测不解决)",
        data={
            "conflicts": records,
            "count": len(records),
            "header": ["task_a", "task_b", "file", "status"],
            "rows": rows,
        },
        error=None,
    )


def team(context: ExecutionContext) -> ActionResult:
    """Agent Team 协作视图 (S10-056 验收 E/F + 批次 B 集成):
    "团队执行" → 团队模式执行 (mode=team); "团队依赖" → 依赖图视图;
    "团队冲突" → 冲突记录视图; "创建团队" → TeamRegistry.create;
    其余 ("查看团队/团队状态/团队协作") → 默认团队协作视图 (team_snapshot)。

    raw 关键词优先分派; intent_type 兜底 (程序化 Intent 无 raw 关键词也可达)。
    只读查询 (非敏感, 无确认门); 团队执行为确认门 Action (独立注册 team_execute)。
    失败安全: 数据缺失 → 默认团队/占位, 不抛。
    workforce action 保持独立 (兼容既有 "查看团队" → 团队状态路径)。
    """
    context.require("user")
    raw = context.intent.raw if context.intent else ""
    intent_type = context.intent.intent_type if context.intent else ""
    if "团队执行" in raw or intent_type == INTENT_TEAM_EXECUTE:
        return _team_execute(context)
    if "团队依赖" in raw or intent_type == INTENT_TEAM_DEPENDENCIES:
        return _team_dependencies(context)
    if "团队冲突" in raw or intent_type == INTENT_TEAM_CONFLICTS:
        return _team_conflicts(context)
    if "创建团队" in raw:
        return _team_create(context, raw)
    return _team_view(context)




# ================================================================== S10-065 引导式 UX actions

def discovery_start(context: ExecutionContext) -> ActionResult:
    """引导式产品发现入口 (S10-065): "我想做X/开始做X" → DiscoverySession。

    有新 discovery session (workspace 级) → 继续; 无 → start(idea) → 第一问。
    非敏感 (自然对话)。失败安全。
    """
    context.require("user")
    workspace = Path(context.workspace or ".")
    params = context.params or {}
    idea = str(params.get("idea") or "")
    try:
        from .discovery import DiscoverySession
        # 找最近未完成 session (resume) — 有则继续
        existing = None
        try:
            sessions = DiscoverySession.list_sessions(workspace)
            for s in reversed(sessions or []):
                if s.get("current_state") in ("discovering", "clarifying", "ready_for_confirmation"):
                    existing = DiscoverySession.load(workspace, s["session_id"])
                    break
        except Exception:  # noqa: BLE001
            existing = None
        if existing is not None:
            question = existing._next_question()
            q = question.question if question else "信息已收集, 是否确认需求?"
            return ActionResult(
                ok=True, status=STATUS_OK,
                message="继续之前的产品需求确认:\n" + q,
            )
        session = DiscoverySession.start(idea)
        session.save(workspace)
        question = session._next_question()
        q = question.question if question else "这个产品解决什么问题?"
        return ActionResult(
            ok=True, status=STATUS_OK,
            message="我先帮你梳理需求。\n" + q,
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"产品发现启动失败: {exc}", error=str(exc))


def production_session_view(context: ExecutionContext) -> ActionResult:
    """生产会话视图 (S10-065): "查看进度/现在做到哪了" → ProductionSession.to_markdown。

    只读查询。失败安全: 无项目 → 友好空态。
    """
    context.require("user")
    workspace = Path(context.workspace or ".")
    params = context.params or {}
    slug = str(params.get("project") or context.project or "")
    try:
        from .production_session import ProductionSession
        # 无指定项目 → 找最近项目
        if not slug:
            projects_dir = workspace / "projects"
            if projects_dir.is_dir():
                slugs = sorted([p.name for p in projects_dir.iterdir()
                                if p.is_dir() and (p / "execution_state.json").is_file()])
                slug = slugs[-1] if slugs else ""
        if not slug:
            return ActionResult(ok=True, status=STATUS_OK, message="暂无生产中的项目。")
        pd = workspace / "projects" / slug
        if not (pd / "execution_state.json").is_file():
            return ActionResult(ok=True, status=STATUS_OK,
                                message=f"项目 {slug} 尚未开始生产。")
        session = ProductionSession.from_project(pd, slug)
        return ActionResult(ok=True, status=STATUS_OK, message=session.to_markdown())
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"生产状态查询失败: {exc}", error=str(exc))


def resume_project(context: ExecutionContext) -> ActionResult:
    """恢复执行 (S10-065): "继续/继续执行" → orchestrator.resume 薄调。

    复用现有 resume 逻辑 (不复制业务)。失败安全。
    """
    context.require("user")
    workspace = Path(context.workspace or ".")
    params = context.params or {}
    slug = str(params.get("project") or context.project or "")
    try:
        if not slug:
            projects_dir = workspace / "projects"
            if projects_dir.is_dir():
                slugs = sorted([p.name for p in projects_dir.iterdir()
                                if p.is_dir() and (p / "execution_state.json").is_file()])
                slug = slugs[-1] if slugs else ""
        if not slug:
            return ActionResult(ok=True, status=STATUS_OK, message="暂无可恢复的项目。")
        from .orchestrator import ExecutionOrchestrator
        orch = ExecutionOrchestrator(workspace)
        result = orch.resume(slug)
        return ActionResult(
            ok=True, status=STATUS_OK,
            message=f"项目 {slug} 已恢复执行: {result.status} "
                    f"(完成 {result.completed_tasks}/{result.completed_tasks + result.failed_tasks})",
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"恢复执行失败: {exc}", error=str(exc))


def review_view(context: ExecutionContext) -> ActionResult:
    """人工评审视图 (S10-065): "为什么停了" → ReviewView markdown。

    无 review_id → 列出 pending; 有 review_id → 详情。只读查询。
    """
    context.require("user")
    workspace = Path(context.workspace or ".")
    params = context.params or {}
    review_id = str(params.get("review_id") or "")
    try:
        from .review_gate import ReviewGate
        from .review_view import ReviewView
        gate = ReviewGate(file=workspace / "cost" / "review_records.json")
        pending = gate.pending()
        if review_id:
            rec = next((r for r in pending if str(r.review_id) == review_id), None)
            if rec is None:
                return ActionResult(ok=True, status=STATUS_OK,
                                    message=f"未找到待审评审 {review_id}。")
            view = ReviewView.from_review(rec, context={"workspace": str(workspace)})
            return ActionResult(ok=True, status=STATUS_OK, message=view.to_markdown())
        if not pending:
            return ActionResult(ok=True, status=STATUS_OK, message="当前无需人工评审。")
        lines = ["AI Factory 当前有待确认事项:", ""]
        for r in pending:
            lines.append(f"• {r.review_id} — {str(r.reason)[:40]} (风险: {r.risk})")
        lines.append("")
        lines.append("输入 '批准' 或 '拒绝' 处理。")
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines))
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"评审视图失败: {exc}", error=str(exc))


def review_approve(context: ExecutionContext) -> ActionResult:
    """批准评审 (S10-065): "接受/批准/同意" → ReviewGate.approve。"""
    context.require("user")
    workspace = Path(context.workspace or ".")
    params = context.params or {}
    review_id = str(params.get("review_id") or "")
    reviewer = str(params.get("reviewer") or "user")
    try:
        from .review_gate import ReviewGate
        gate = ReviewGate(file=workspace / "cost" / "review_records.json")
        pending = gate.pending()
        if not review_id and pending:
            review_id = str(pending[0].review_id)  # 单待审 → 直接批准
        if not review_id:
            return ActionResult(ok=True, status=STATUS_OK, message="没有待批准的评审。")
        rec = gate.approve(review_id, reviewer)
        return ActionResult(ok=True, status=STATUS_OK,
                            message=f"评审 {review_id} 已批准 ({rec.status}) — 可继续执行。")
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"批准失败: {exc}", error=str(exc))


def review_reject(context: ExecutionContext) -> ActionResult:
    """拒绝评审 (S10-065): "拒绝" → ReviewGate.reject。"""
    context.require("user")
    workspace = Path(context.workspace or ".")
    params = context.params or {}
    review_id = str(params.get("review_id") or "")
    reviewer = str(params.get("reviewer") or "user")
    try:
        from .review_gate import ReviewGate
        gate = ReviewGate(file=workspace / "cost" / "review_records.json")
        pending = gate.pending()
        if not review_id and pending:
            review_id = str(pending[0].review_id)
        if not review_id:
            return ActionResult(ok=True, status=STATUS_OK, message="没有待拒绝的评审。")
        rec = gate.reject(review_id, reviewer)
        return ActionResult(ok=True, status=STATUS_OK,
                            message=f"评审 {review_id} 已拒绝 ({rec.status}) — 生产停止。")
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"拒绝失败: {exc}", error=str(exc))


def review_cancel(context: ExecutionContext) -> ActionResult:
    """取消评审 (S10-065): "取消" → ReviewGate.cancel。"""
    context.require("user")
    workspace = Path(context.workspace or ".")
    params = context.params or {}
    review_id = str(params.get("review_id") or "")
    try:
        from .review_gate import ReviewGate
        gate = ReviewGate(file=workspace / "cost" / "review_records.json")
        pending = gate.pending()
        if not review_id and pending:
            review_id = str(pending[0].review_id)
        if not review_id:
            return ActionResult(ok=True, status=STATUS_OK, message="没有可取消的评审。")
        rec = gate.cancel(review_id)
        return ActionResult(ok=True, status=STATUS_OK,
                            message=f"评审 {review_id} 已取消 ({rec.status})。")
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"取消失败: {exc}", error=str(exc))



# ================================================================== S10-066 Product Intelligence CLI

def _product_intent_from_context(context) -> dict:
    """从 context 取 ProductIntent (project 的 product.json 或 params.product_intent)。"""
    params = context.params or {}
    intent = params.get("product_intent")
    if isinstance(intent, dict) and intent:
        return intent
    workspace = Path(context.workspace or ".")
    slug = str(params.get("project") or context.project or "")
    if not slug:
        projects_dir = workspace / "projects"
        if projects_dir.is_dir():
            slugs = sorted([p.name for p in projects_dir.iterdir()
                            if p.is_dir() and (p / "product.json").is_file()])
            slug = slugs[-1] if slugs else ""
    if slug:
        pf = workspace / "projects" / slug / "product.json"
        if pf.is_file():
            try:
                import json as _json
                return _json.loads(pf.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return {}
    return {}


def product_intelligence(context: ExecutionContext) -> ActionResult:
    """产品智能分析 (S10-066): "分析产品/产品智能" → 完整 8 模块报告。"""
    context.require("user")
    intent = _product_intent_from_context(context)
    try:
        from .product_intelligence import ProductIntelligenceEngine
        engine = ProductIntelligenceEngine()
        report = engine.analyze(intent)
        return ActionResult(ok=True, status=STATUS_OK, message=engine.to_markdown(report))
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"产品智能分析失败: {exc}", error=str(exc))


def product_market(context: ExecutionContext) -> ActionResult:
    """市场分析 (S10-066): "产品市场/市场分析" → MarketAnalysis。"""
    context.require("user")
    intent = _product_intent_from_context(context)
    try:
        from .product_intelligence import ProductIntelligenceEngine
        engine = ProductIntelligenceEngine()
        report = engine.analyze(intent)
        m = report.market_analysis
        lines = [
            f"市场规模: {m.market_size}",
            f"用户趋势: {m.user_trends}",
            f"机会窗口: {m.opportunity_window}",
        ]
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"市场分析失败: {exc}", error=str(exc))


def product_persona(context: ExecutionContext) -> ActionResult:
    """用户画像 (S10-066): "产品画像/用户画像" → UserPersonas。"""
    context.require("user")
    intent = _product_intent_from_context(context)
    try:
        from .product_intelligence import ProductIntelligenceEngine
        engine = ProductIntelligenceEngine()
        report = engine.analyze(intent)
        lines = ["用户画像:"]
        for p in report.user_personas:
            lines.append(f"• {p.name} — {p.description}")
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"用户画像失败: {exc}", error=str(exc))


def product_mvp(context: ExecutionContext) -> ActionResult:
    """MVP 规划 (S10-066): "MVP规划/MVP拆分" → MvpPlan。"""
    context.require("user")
    intent = _product_intent_from_context(context)
    try:
        from .product_intelligence import ProductIntelligenceEngine
        engine = ProductIntelligenceEngine()
        report = engine.analyze(intent)
        m = report.mvp_plan
        lines = [
            f"MVP: {', '.join(m.mvp)}",
            f"V2: {', '.join(m.v2) if m.v2 else '-'}",
            f"Future: {', '.join(m.future) if m.future else '-'}",
        ]
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"MVP 规划失败: {exc}", error=str(exc))


def product_value(context: ExecutionContext) -> ActionResult:
    """产品价值评分 (S10-066): "产品价值/价值评分" → ProductValueScore。"""
    context.require("user")
    intent = _product_intent_from_context(context)
    try:
        from .product_intelligence import ProductIntelligenceEngine
        engine = ProductIntelligenceEngine()
        report = engine.analyze(intent)
        v = report.product_value_score
        return ActionResult(
            ok=True, status=STATUS_OK,
            message=f"产品价值评分: {v.score}/100\n用户价值: {v.user_value}\n"
                    f"技术价值: {v.technical_value}\n理由: {v.justification}",
        )
    except Exception as exc:  # noqa: BLE001
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"价值评分失败: {exc}", error=str(exc))

# ================================================================== S10-067 Memory Learning CLI

def _memory_params(context) -> dict:
    """取 memory action 参数 (intent.params 优先; 兼容测试 FakeContext.params)。"""
    intent = getattr(context, "intent", None)
    if intent is not None and getattr(intent, "params", None):
        return intent.params
    return getattr(context, "params", None) or {}


def _memory_workspace(context) -> Path:
    """memory action 工作区 (context.workspace 缺省 → ~/.factory)。"""
    return Path(getattr(context, "workspace", None) or DEFAULT_WORKSPACE)


def _memory_lines(records: list, header: str, limit: int = 20) -> list[str]:
    """经验记录 → 展示行 (类型/问题/结果/置信)。"""
    lines = [f"{header} ({len(records)} 条):"]
    for r in records[:limit]:
        subject = r.problem or r.task or "(无问题)"
        outcome = r.result or r.action or "-"
        lines.append(f"• [{r.type}] {subject} → {outcome} (conf {r.confidence})")
    if not records:
        lines.append("无记录。")
    return lines


def memory_search(context: ExecutionContext) -> ActionResult:
    """经验检索 (S10-067): "搜索经验/查找经验" → 关键词检索 (query/type 参数)。"""
    context.require("user")
    params = _memory_params(context)
    query = str(params.get("query") or "")
    record_type = params.get("type") or None
    try:
        from ..memory.experience_store import ExperienceStore
        from ..memory.retrieval import ExperienceRetriever
        ws = _memory_workspace(context)
        retriever = ExperienceRetriever(ExperienceStore.from_workspace(ws))
        hits = retriever.search(query=query, type=str(record_type) if record_type else None)
        lines = _memory_lines(hits, f"经验检索「{query}」" if query else "全部经验")
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines))
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"经验检索失败: {exc}", error=str(exc))


def memory_learn(context: ExecutionContext) -> ActionResult:
    """触发学习 (S10-067): "学习经验/经验学习" → 提取 → 模式/Agent 画像 → 审计。"""
    context.require("user")
    try:
        from ..memory.learning_engine import LearningEngine
        ws = _memory_workspace(context)
        result = LearningEngine(workspace=ws).run(ws)
        lines = [
            f"学习完成: 提取 {result.extracted_count} 条经验"
            f" → {len(result.patterns)} 个模式 + {len(result.agent_profiles)} 个 Agent 画像",
        ]
        for p in result.patterns[:10]:
            lines.append(f"• 模式 {p['pattern_id']}: {p['description']} (conf {p['confidence']})")
        for a in result.agent_profiles[:10]:
            lines.append(
                f"• Agent {a['agent_id']}: {a['total_tasks']} 任务, "
                f"成功率 {a['success_rate']:.0%}"
            )
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines))
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"经验学习失败: {exc}", error=str(exc))


def memory_stats(context: ExecutionContext) -> ActionResult:
    """经验统计 (S10-067): "经验统计" → 按类型/成功/Agent 统计。"""
    context.require("user")
    try:
        from ..memory.experience_store import ExperienceStore
        ws = _memory_workspace(context)
        stats = ExperienceStore.from_workspace(ws).stats()
        lines = [f"经验统计 (共 {stats['total']} 条):"]
        by_type = stats["by_type"] or {}
        if by_type:
            lines.append("按类型: " + ", ".join(f"{k}={v}" for k, v in by_type.items()))
        else:
            lines.append("按类型: 无")
        lines.append(f"按结果: 成功 {stats['by_success']['success']}, "
                     f"失败 {stats['by_success']['failed']}")
        by_agent = stats["by_agent"] or {}
        if by_agent:
            lines.append("按Agent: " + ", ".join(f"{k}={v}" for k, v in by_agent.items()))
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines))
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"经验统计失败: {exc}", error=str(exc))


def memory_analyze_agent(context: ExecutionContext) -> ActionResult:
    """Agent 画像 (S10-067): "分析Agent/Agent成长" → 能力画像 (agent_id 参数)。"""
    context.require("user")
    params = _memory_params(context)
    agent_id = str(params.get("agent_id") or "").strip()
    try:
        from ..memory.experience_store import ExperienceStore
        from ..memory.extraction import ExperienceExtractor
        from ..memory.learning_engine import PatternLearner
        ws = _memory_workspace(context)
        records = ExperienceExtractor.extract_all(ws)
        profiles = PatternLearner().learn_agent(records)
        if not agent_id and profiles:
            agent_id = profiles[0].agent_id
        profile = next((p for p in profiles if p.agent_id == agent_id), None)
        if profile is None:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message=f"未找到 Agent {agent_id!r} 的经验画像 (共 {len(profiles)} 个画像)",
                error="agent profile not found",
            )
        lines = [
            f"Agent 画像: {profile.agent_id} ({profile.role or '角色未知'})",
            f"任务数: {profile.total_tasks} | 成功: {profile.success_count} "
            f"| 成功率: {profile.success_rate:.0%}",
        ]
        if profile.common_problems:
            lines.append("常见问题: " + "; ".join(profile.common_problems[:3]))
        if profile.best_domains:
            lines.append("最佳领域: " + ", ".join(profile.best_domains[:5]))
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines))
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"Agent 画像失败: {exc}", error=str(exc))


def memory_export(context: ExecutionContext) -> ActionResult:
    """导出经验 (S10-067): "导出经验" → 全量经验 → workspace/memory/experience_export.json。"""
    context.require("user")
    try:
        from ..memory.experience_store import ExperienceStore
        import json as _json
        ws = _memory_workspace(context)
        store = ExperienceStore.from_workspace(ws)
        export_path = store.path.parent / "experience_export.json"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(
            _json.dumps([r.to_dict() for r in store.records()],
                        ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return ActionResult(
            ok=True, status=STATUS_OK,
            message=f"已导出 {len(store.records())} 条经验 → {export_path}",
            data={"count": len(store.records()), "path": str(export_path)},
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"经验导出失败: {exc}", error=str(exc))


# ================================================================== S10-068 Debug Intelligence CLI

def _debug_params(context) -> dict:
    """取 debug action 参数 (intent.params 优先; 兼容测试 FakeContext.params)。"""
    intent = getattr(context, "intent", None)
    if intent is not None and getattr(intent, "params", None):
        return intent.params
    return getattr(context, "params", None) or {}


def _debug_workspace(context) -> Path:
    """debug action 工作区 (context.workspace 缺省 → ~/.factory)。"""
    return Path(getattr(context, "workspace", None) or DEFAULT_WORKSPACE)


def _debug_latest_failure(ws: Path) -> Optional[dict]:
    """最近失败任务 (缺省参数面): workspace/exec/execution_records.json 最新
    result=failed 记录 → {error_message, task_id, context}; 无 → None (失败安全)。"""
    try:
        records_file = ws / "exec" / "execution_records.json"
        data = json.loads(records_file.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → None
        return None
    if not isinstance(data, list):
        return None
    failed = [
        r for r in data
        if isinstance(r, dict) and str(r.get("result") or "").lower()
        in ("failed", "fail", "error")
    ]
    if not failed:
        return None
    failed.sort(key=lambda r: str(r.get("timestamp") or ""), reverse=True)
    record = failed[0]
    task = str(record.get("task") or "")
    return {
        "error_message": str(record.get("error") or "") or f"任务失败: {task}",
        "task_id": task,
        "context": str(record.get("intent") or ""),
    }


def debug_analyze(context: ExecutionContext) -> ActionResult:
    """调试分析 (S10-068): \"分析错误/为什么失败/debug\" → DebugDecision
    (错误类型 → 根因 → 历史经验 → 修复策略)。error_message 缺省 → 最近失败任务。"""
    context.require("user")
    params = _debug_params(context)
    error_message = str(params.get("error_message") or "").strip()
    try:
        from .debug import DebugEngine
        from .debug.error_analysis import ErrorAnalyzer

        ws = _debug_workspace(context)
        engine = DebugEngine(ws)
        case_kw: dict = {
            "task_id": str(params.get("task_id") or ""),
            "agent_id": str(params.get("agent_id") or ""),
            "context": str(params.get("context") or ""),
            "project": str(params.get("project") or ""),
        }
        if not error_message:
            latest = _debug_latest_failure(ws)
            if latest is None:
                return ActionResult(
                    ok=False, status=STATUS_ERROR,
                    message="缺少 error_message 参数, 且工作区无失败任务记录",
                    error="no error_message",
                )
            error_message = latest["error_message"]
            case_kw["task_id"] = case_kw["task_id"] or latest["task_id"]
            case_kw["context"] = case_kw["context"] or latest["context"]
        case = ErrorAnalyzer().extract(error_message, **case_kw)
        decision = engine.analyze(case)
        lines = [
            "调试分析:",
            f"• 错误类型: {case.error_type}",
            f"• 错误信息: {case.error_message[:200]}",
        ]
        for evidence in decision.evidence[:5]:
            lines.append(f"• 证据: {evidence}")
        strategy = decision.strategy.value if hasattr(decision.strategy, "value") else str(decision.strategy)
        lines.append(f"• 策略: {strategy} — {decision.reason} (conf {decision.confidence})")
        lines.append(f"• 相关经验: {len(decision.related_experiences)} 条")
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data=decision.to_dict(),
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"调试分析失败: {exc}", error=str(exc))


def debug_history(context: ExecutionContext) -> ActionResult:
    """调试历史 (S10-068): \"查看调试经验/debug历史\" → debug_cases.json 历史。"""
    context.require("user")
    params = _debug_params(context)
    try:
        from .debug import DebugEngine

        ws = _debug_workspace(context)
        engine = DebugEngine(ws)
        limit = int(params.get("limit") or 20)
        entries = engine.history(ws, limit=limit)
        lines = [f"调试历史 (共 {len(entries)} 条):"]
        for entry in entries:
            case = entry.get("case") or {}
            decision = entry.get("decision") or {}
            outcome = str(entry.get("outcome") or "pending")
            lines.append(
                f"• [{case.get('error_type') or 'UNKNOWN'}] "
                f"{(case.get('error_message') or '')[:60]} "
                f"→ {decision.get('strategy')} "
                f"(conf {decision.get('confidence')}, outcome: {outcome})"
            )
        if not entries:
            lines.append("无调试记录。")
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines),
                            data={"count": len(entries)})
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"调试历史查询失败: {exc}", error=str(exc))


def debug_recommend(context: ExecutionContext) -> ActionResult:
    """修复建议 (S10-068): \"修复建议/debug推荐\" → 策略推荐 (同 analyze 简版)。"""
    context.require("user")
    params = _debug_params(context)
    error_message = str(params.get("error_message") or "").strip()
    try:
        from .debug import DebugEngine
        from .debug.error_analysis import ErrorAnalyzer

        ws = _debug_workspace(context)
        engine = DebugEngine(ws)
        if not error_message:
            latest = _debug_latest_failure(ws)
            if latest is None:
                return ActionResult(
                    ok=False, status=STATUS_ERROR,
                    message="缺少 error_message 参数, 且工作区无失败任务记录",
                    error="no error_message",
                )
            error_message = latest["error_message"]
        decision = engine.analyze(ErrorAnalyzer().extract(error_message))
        strategy = decision.strategy.value if hasattr(decision.strategy, "value") else str(decision.strategy)
        lines = [
            f"修复建议: {strategy} — {decision.reason} (conf {decision.confidence})",
        ]
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data={"strategy": strategy, "reason": decision.reason,
                  "confidence": decision.confidence},
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"修复建议失败: {exc}", error=str(exc))


def debug_stats(context: ExecutionContext) -> ActionResult:
    """调试统计 (S10-068): \"debug统计/调试统计\" → 按错误类型/策略/结果统计。"""
    context.require("user")
    try:
        from .debug import DebugEngine

        ws = _debug_workspace(context)
        engine = DebugEngine(ws)
        stats = engine.stats(ws)
        lines = [f"调试统计 (共 {stats['total_cases']} 个案件):"]
        by_error_type = stats["by_error_type"] or {}
        if by_error_type:
            lines.append("按错误类型: " + ", ".join(
                f"{k}={v}" for k, v in by_error_type.items()))
        else:
            lines.append("按错误类型: 无")
        by_strategy = stats["by_strategy"] or {}
        if by_strategy:
            lines.append("按策略: " + ", ".join(
                f"{k}={v}" for k, v in by_strategy.items()))
        else:
            lines.append("按策略: 无")
        by_outcome = stats["by_outcome"]
        lines.append(f"按结果: 成功 {by_outcome['success']}, "
                     f"失败 {by_outcome['fail']}, 待定 {by_outcome['pending']}")
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines),
                            data=stats)
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"调试统计失败: {exc}", error=str(exc))


# ================================================================== S10-068 Part 2 Autonomous Debug & Repair CLI

def _debug_pipeline(context) -> Any:
    """DebugPipeline 实例 (工作区同 debug action 口径)。"""
    from .debug import DebugPipeline

    return DebugPipeline(_debug_workspace(context))


def _debug_require_session(context, params) -> tuple[Any, Optional[dict]]:
    """按 debug_id 取会话 (缺省 → 最近会话; 无 → (None, None))。"""
    pipeline = _debug_pipeline(context)
    debug_id = str(params.get("debug_id") or "").strip()
    if debug_id:
        session = pipeline.store.get(debug_id)
        return (pipeline, session.to_dict() if session is not None else None)
    latest = pipeline.store.list(limit=1)
    if not latest:
        return (pipeline, None)
    return (pipeline, latest[0].to_dict())


def debug_session(context: ExecutionContext) -> ActionResult:
    """开始调试 (S10-068 Part 2): \"开始调试/调试会话\" → DebugSession (ANALYZING)。"""
    context.require("user")
    params = _debug_params(context)
    error_message = str(params.get("error_message") or "").strip()
    try:
        ws = _debug_workspace(context)
        pipeline = _debug_pipeline(context)
        if not error_message:
            latest = _debug_latest_failure(ws)
            if latest is None:
                return ActionResult(
                    ok=False, status=STATUS_ERROR,
                    message="缺少 error_message 参数, 且工作区无失败任务记录",
                    error="no error_message",
                )
            error_message = latest["error_message"]
            params.setdefault("task_id", latest.get("task_id") or "")
            params.setdefault("context", latest.get("context") or "")
        session = pipeline.start(
            project_id=str(params.get("project_id") or ""),
            task_id=str(params.get("task_id") or ""),
            agent_id=str(params.get("agent_id") or ""),
            error_message=error_message,
            failure_id=str(params.get("failure_id") or ""),
            context=str(params.get("context") or ""),
        )
        lines = [
            "调试会话已开始:",
            f"• debug_id: {session.debug_id}",
            f"• 状态: {session.status}",
            f"• 错误: {session.error_summary[:200]}",
            "下一步: debug analyze / debug root-cause 分析根因",
        ]
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines),
                            data=session.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"调试会话启动失败: {exc}", error=str(exc))


def debug_root_cause(context: ExecutionContext) -> ActionResult:
    """根因分析 (S10-068 Part 2): \"找一下根因\" → RootCause (9 类根因类型)。"""
    context.require("user")
    params = _debug_params(context)
    error_message = str(params.get("error_message") or "").strip()
    try:
        ws = _debug_workspace(context)
        pipeline = _debug_pipeline(context)
        if not error_message:
            latest = _debug_latest_failure(ws)
            if latest is None:
                return ActionResult(
                    ok=False, status=STATUS_ERROR,
                    message="缺少 error_message 参数, 且工作区无失败任务记录",
                    error="no error_message",
                )
            error_message = latest["error_message"]
        case = pipeline.engine.analyzer.extract(
            error_message, task_id=str(params.get("task_id") or ""))
        root = pipeline.engine.root_cause_analyzer.analyze(case)
        lines = [
            "根因分析:",
            f"• 根因类型: {root.root_cause_type}",
            f"• 根因: {root.cause}",
            f"• 置信度: {root.confidence:.2f}",
            f"• 推理: {root.reasoning_summary}",
        ]
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines),
                            data=root.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"根因分析失败: {exc}", error=str(exc))


def debug_repair(context: ExecutionContext) -> ActionResult:
    """自动修复 (S10-068 Part 2): \"自动修复\" → RepairSafety 治理闸后执行修复。"""
    context.require("user")
    params = _debug_params(context)
    try:
        pipeline, session_dict = _debug_require_session(context, params)
        if session_dict is None:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message="无调试会话 (先执行 debug session / debug analyze)",
                error="no debug session",
            )
        from .debug.debug_session import DebugSession, SESSION_ANALYZING

        session = DebugSession.from_dict(session_dict)
        if session.status == SESSION_ANALYZING:
            session = pipeline.analyze(session)
        session = pipeline.repair(
            session,
            max_attempts=int(params.get("max_attempts") or 3),
        )
        decision = (session.budget_usage or {}).get("decision", "")
        lines = [
            "自动修复:",
            f"• debug_id: {session.debug_id}",
            f"• 状态: {session.status}",
            f"• 决策: {decision} — {(session.budget_usage or {}).get('reason', '')}",
            f"• 策略: {session.selected_strategy} (第 {session.attempt_number} 次尝试)",
        ]
        if session.status == "WAITING_FOR_REVIEW":
            lines.append("• 需人工审批: debug resume (decision=approved) 继续")
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines),
                            data=session.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"自动修复失败: {exc}", error=str(exc))


def debug_validate(context: ExecutionContext) -> ActionResult:
    """验证修复 (S10-068 Part 2): \"验证修复\" → PASS→SUCCESS / FAIL→RETRYING。"""
    context.require("user")
    params = _debug_params(context)
    try:
        pipeline, session_dict = _debug_require_session(context, params)
        if session_dict is None:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message="无调试会话 (先执行 debug session / debug repair)",
                error="no debug session",
            )
        from .debug.debug_session import DebugSession

        result = params.get("result")
        if result is not None and not isinstance(result, bool):
            result = str(result).strip().lower() in (
                "success", "pass", "passed", "true", "1", "ok", "succeeded", "成功")
        session = pipeline.validate(
            DebugSession.from_dict(session_dict),
            result=result,
            validation_command=str(params.get("validation_command") or ""),
        )
        lines = [
            "验证修复:",
            f"• debug_id: {session.debug_id}",
            f"• 状态: {session.status}",
            f"• 验证结果: {session.validation_result}",
        ]
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines),
                            data=session.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"调试验证失败: {exc}", error=str(exc))


def debug_resume(context: ExecutionContext) -> ActionResult:
    """继续调试 (S10-068 Part 2): \"继续调试\" → REVIEW 通过后继续 (approved 默认)。"""
    context.require("user")
    params = _debug_params(context)
    try:
        pipeline, session_dict = _debug_require_session(context, params)
        if session_dict is None:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message="无调试会话 (先执行 debug session / debug repair)",
                error="no debug session",
            )
        from .debug.debug_session import DebugSession

        session = pipeline.resume(
            DebugSession.from_dict(session_dict),
            decision=str(params.get("decision") or "approved"),
        )
        lines = [
            "继续调试:",
            f"• debug_id: {session.debug_id}",
            f"• 状态: {session.status}",
        ]
        return ActionResult(ok=True, status=STATUS_OK, message="\n".join(lines),
                            data=session.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"调试继续失败: {exc}", error=str(exc))


# ================================================================== S10-069 Audit Intelligence CLI

def _audit_params(context) -> dict:
    """取 audit action 参数 (intent.params 优先; 兼容测试 FakeContext.params)。"""
    intent = getattr(context, "intent", None)
    if intent is not None and getattr(intent, "params", None):
        return intent.params
    return getattr(context, "params", None) or {}


def _audit_workspace(context) -> Path:
    """audit action 工作区 (context.workspace 缺省 → ~/.factory)。"""
    return Path(getattr(context, "workspace", None) or DEFAULT_WORKSPACE)


def _audit_store(context) -> Any:
    """AuditStore 实例 (工作区同 audit action 口径)。"""
    from ..audit import AuditStore

    return AuditStore(_audit_workspace(context))


def _audit_events_lines(events, header: str, limit: int = 20) -> list[str]:
    """事件列表 → 展示行 (类型/时间/摘要 — 统一 CLI 视图)。"""
    lines = [header]
    for event in events[:limit]:
        digest = event.decision_reason or event.decision or event.action or ""
        lines.append(
            f"• [{event.event_type}] {event.timestamp[:19]} "
            f"{event.task_id or event.agent_id or event.project_id or ''} "
            f"{digest[:60]}"
        )
    if not events:
        lines.append("无审计事件。")
    return lines


def audit_events(context: ExecutionContext) -> ActionResult:
    """审计记录 (S10-069): \"查看审计记录/审计记录\" → 事件列表 (按时间倒序)。"""
    context.require("user")
    params = _audit_params(context)
    try:
        store = _audit_store(context)
        events = store.events()
        project = str(params.get("project") or "")
        event_type = str(params.get("event_type") or "")
        if project:
            events = [e for e in events if e.project_id == project]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        events.sort(key=lambda e: e.timestamp, reverse=True)
        limit = int(params.get("limit") or 20)
        lines = _audit_events_lines(
            events, f"审计记录 (共 {len(events)} 条, 最新在前):", limit=limit)
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data={"count": len(events)})
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计记录查询失败: {exc}", error=str(exc))


def audit_trace(context: ExecutionContext) -> ActionResult:
    """审计追踪 (S10-069): \"审计追踪/查看审计链路\" (参数 trace_id)。"""
    context.require("user")
    params = _audit_params(context)
    try:
        store = _audit_store(context)
        trace_id = str(params.get("trace_id") or "")
        if not trace_id:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message="缺少 trace_id 参数 (如: 审计追踪 <trace_id>)",
                error="no trace_id")
        events = store.query(trace_id=trace_id)
        events.sort(key=lambda e: e.timestamp)
        lines = _audit_events_lines(
            events, f"审计追踪 {trace_id} (共 {len(events)} 条):")
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data={"trace_id": trace_id, "count": len(events)})
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计追踪失败: {exc}", error=str(exc))


def audit_chain(context: ExecutionContext) -> ActionResult:
    """审计决策链 (S10-069): \"审计决策链\" (参数 trace_id) → 根→子→相关→最终。"""
    context.require("user")
    params = _audit_params(context)
    try:
        store = _audit_store(context)
        trace_id = str(params.get("trace_id") or "")
        if not trace_id:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message="缺少 trace_id 参数 (如: 审计决策链 <trace_id>)",
                error="no trace_id")
        chain = store.get_chain(trace_id)
        root = chain.get("root_event") or {}
        lines = [f"审计决策链 {trace_id} (共 {chain.get('count')} 个事件):"]
        lines.append(f"• 根事件: [{root.get('event_type')}] "
                     f"{root.get('timestamp', '')[:19]} "
                     f"{(root.get('decision_reason') or root.get('decision') or '')[:60]}")
        for child in chain.get("children") or []:
            lines.append(f"  ├─ [{child.get('event_type')}] "
                         f"{child.get('timestamp', '')[:19]} "
                         f"{(child.get('decision_reason') or child.get('decision') or '')[:50]}")
        outcome = chain.get("final_outcome") or {}
        lines.append(f"• 最终: {outcome.get('event_type')} — "
                     f"状态 {outcome.get('status') or '未知'}")
        if chain.get("related_events"):
            lines.append(f"• 相关事件 (跨 trace): {len(chain['related_events'])} 条")
        if not chain.get("count"):
            lines = [f"审计决策链 {trace_id}: 无事件 (trace 不存在)。"]
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines), data=chain)
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计决策链失败: {exc}", error=str(exc))


def audit_decision(context: ExecutionContext) -> ActionResult:
    """审计决策 (S10-069): \"审计决策\" → 含 decision 字段的事件。"""
    context.require("user")
    params = _audit_params(context)
    try:
        store = _audit_store(context)
        events = [e for e in store.events() if e.decision or e.decision_reason]
        project = str(params.get("project") or "")
        if project:
            events = [e for e in events if e.project_id == project]
        events.sort(key=lambda e: e.timestamp, reverse=True)
        lines = [f"审计决策 (共 {len(events)} 条):"]
        for event in events[:20]:
            lines.append(
                f"• [{event.event_type}] {event.timestamp[:19]} "
                f"决策={event.decision or '—'} 原因={event.decision_reason[:60]}")
        if not events:
            lines.append("无决策事件。")
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data={"count": len(events)})
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计决策查询失败: {exc}", error=str(exc))


def audit_explain(context: ExecutionContext) -> ActionResult:
    """审计解释 (S10-069): \"为什么创建这个任务/为什么选择这个Agent/为什么停了\"
    → 结构化\"为什么\" (AuditExplain, 默认不调 LLM)。"""
    context.require("user")
    params = _audit_params(context)
    try:
        from ..audit import AuditExplain

        store = _audit_store(context)
        intent = getattr(context, "intent", None)
        question = str(params.get("question") or "")
        if not question and intent is not None and getattr(intent, "raw", ""):
            question = intent.raw
        if not question:
            question = "为什么"
        task_id = str(params.get("task_id") or "")
        agent_id = str(params.get("agent_id") or "")
        project = str(params.get("project") or "") or str(
            getattr(context, "project", None) or "")
        debug_id = str(params.get("debug_id") or "")
        explainer = AuditExplain(store)
        result = explainer.explain(
            question,
            task_id=task_id or None,
            agent_id=agent_id or None,
            project=project or None,
            debug_id=debug_id or None,
        )
        lines = [
            f"审计解释 ({result.get('answer_type')}):",
            result.get("summary", ""),
        ]
        if result.get("decision"):
            decision = result["decision"]
            lines.append(f"• 决策: {decision.get('decision') or '—'} — "
                         f"{decision.get('reason') or ''}")
        if result.get("approval"):
            approval = result["approval"]
            reviewer = approval.get("reviewer") or approval.get("actor_id") or "?"
            lines.append(f"• 审批: {reviewer} ({approval.get('decision') or 'approved'})")
        cost = result.get("cost") or {}
        if cost.get("events"):
            lines.append(f"• 成本: ${cost.get('total', 0.0):.4f} "
                         f"({cost.get('events')} 条事件)")
        lines.append(f"• 相关事件: {len(result.get('related_events') or [])} 条")
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines), data=result)
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计解释失败: {exc}", error=str(exc))


def audit_task(context: ExecutionContext) -> ActionResult:
    """审计任务 (S10-069): \"审计任务\" (参数 task_id) → 任务全生命周期事件。"""
    context.require("user")
    params = _audit_params(context)
    try:
        store = _audit_store(context)
        task_id = str(params.get("task_id") or "")
        if not task_id:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message="缺少 task_id 参数 (如: 审计任务 <task_id>)",
                error="no task_id")
        events = store.query(task_id=task_id)
        events.sort(key=lambda e: e.timestamp)
        lines = _audit_events_lines(
            events, f"审计任务 {task_id} (共 {len(events)} 条):")
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data={"task_id": task_id, "count": len(events)})
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计任务失败: {exc}", error=str(exc))


def audit_agent(context: ExecutionContext) -> ActionResult:
    """审计Agent (S10-069): \"审计Agent\" (参数 agent_id) → Agent 全部事件。"""
    context.require("user")
    params = _audit_params(context)
    try:
        store = _audit_store(context)
        agent_id = str(params.get("agent_id") or "")
        if not agent_id:
            return ActionResult(
                ok=False, status=STATUS_ERROR,
                message="缺少 agent_id 参数 (如: 审计Agent <agent_id>)",
                error="no agent_id")
        events = store.query(agent_id=agent_id)
        events.sort(key=lambda e: e.timestamp)
        lines = _audit_events_lines(
            events, f"审计Agent {agent_id} (共 {len(events)} 条):")
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data={"agent_id": agent_id, "count": len(events)})
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计Agent失败: {exc}", error=str(exc))


def audit_cost(context: ExecutionContext) -> ActionResult:
    """成本审计 (S10-069): \"查看项目成本审计/成本审计\" → 项目成本事件聚合。"""
    context.require("user")
    params = _audit_params(context)
    try:
        from ..audit import AuditExplain

        store = _audit_store(context)
        project_id = str(params.get("project_id") or "") or str(
            params.get("project") or "") or str(
            getattr(context, "project", None) or "")
        explainer = AuditExplain(store)
        result = explainer.why_cost(project_id)
        cost = result.get("cost") or {}
        lines = [
            f"成本审计 (项目 {project_id or '(全部)'}):",
            f"• 成本事件: {cost.get('events', 0)} 条, "
            f"合计 ${cost.get('total', 0.0):.4f}",
        ]
        if cost.get("references"):
            lines.append(f"• CostLedger 引用: {', '.join(cost['references'][:5])}")
        if cost.get("ledger_total") is not None:
            lines.append(f"• CostLedger 聚合: ${cost['ledger_total']:.4f}")
        if not cost.get("events"):
            lines.append("无成本事件 (LLM_CALL/TOOL_CALL/AGENT_*)。")
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines), data=cost)
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"成本审计失败: {exc}", error=str(exc))


def audit_export(context: ExecutionContext) -> ActionResult:
    """导出审计 (S10-069): \"导出审计\" → audit_export.json 落盘 (项目过滤可选)。"""
    context.require("user")
    params = _audit_params(context)
    try:
        store = _audit_store(context)
        project = str(params.get("project") or "")
        payload = store.export(project_id=project or None)
        ws = _audit_workspace(context)
        out_file = ws / "audit" / "audit_export.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        lines = [
            f"导出审计完成 (共 {len(payload)} 条):",
            f"• 文件: {out_file}",
            f"• 项目过滤: {project or '(全部)'}",
        ]
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines),
            data={"file": str(out_file), "count": len(payload)})
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"导出审计失败: {exc}", error=str(exc))


def audit_stats(context: ExecutionContext) -> ActionResult:
    """审计统计 (S10-069): \"审计统计\" → total + by_type/status/actor + 完整性。"""
    context.require("user")
    try:
        store = _audit_store(context)
        stats = store.stats()
        integrity = stats.get("integrity") or {}
        lines = [
            f"审计统计 (共 {stats['total']} 条事件):",
            "按事件类型: " + ", ".join(
                f"{k}={v}" for k, v in (stats.get("by_event_type") or {}).items())
            if stats.get("by_event_type") else "按事件类型: 无",
            "按状态: " + ", ".join(
                f"{k}={v}" for k, v in (stats.get("by_status") or {}).items())
            if stats.get("by_status") else "按状态: 无",
            "按执行者: " + ", ".join(
                f"{k}={v}" for k, v in (stats.get("by_actor_type") or {}).items())
            if stats.get("by_actor_type") else "按执行者: 无",
            f"完整性: {'通过' if integrity.get('ok') else '异常'} "
            f"(校验 {integrity.get('verified')}/{integrity.get('total')})",
            f"存储: {stats['file']}",
        ]
        return ActionResult(
            ok=True, status=STATUS_OK, message="\n".join(lines), data=stats)
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return ActionResult(ok=False, status=STATUS_ERROR,
                            message=f"审计统计失败: {exc}", error=str(exc))


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
            name="create_product",
            description="创建产品 (ProductIntent → 桥接 Project: product.json + project.json)",
            handler=create_product,
            permission="project",
            metadata={
                "service": "create_project (org.cli.cmd_project_register 复用)",
                "phase": "S10-050 P2",
                "sensitive": True,
                "category": "product",
            },
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
    registry.register(
        Action(
            name="generate_prd",
            description="生成产品需求文档 (ProductIntent → PRD.md, 规则生成)",
            handler=generate_prd,
            permission="user",
            metadata={
                "service": "pipeline.ProductDocument (规则生成)",
                "phase": "S10-051 P2",
                "sensitive": False,
                "category": "product",
            },
        )
    )
    registry.register(
        Action(
            name="prepare_project",
            description=(
                "准备工程 (PRD + engineering + tasks + agent assignment + lifecycle)"
            ),
            handler=prepare_project,
            permission="user",
            metadata={
                "service": "pipeline (规则生成, 复用 select_agent)",
                "phase": "S10-051 P3",
                "sensitive": True,
                "category": "product",
            },
        )
    )
    registry.register(
        Action(
            name="execute_project",
            description="执行项目 (execution_plan.json → 任务队列 → Lifecycle 推进)",
            handler=execute_project,
            permission="project",
            metadata={
                "service": "ExecutionOrchestrator (复用 execute_task)",
                "phase": "S10-052 P2",
                "sensitive": True,
                "category": "execution",
            },
        )
    )
    registry.register(
        Action(
            name="project_progress",
            description="查询项目执行进度 (只读 execution_state.json)",
            handler=project_progress,
            permission="user",
            metadata={
                "service": "ExecutionOrchestrator.get_progress",
                "phase": "S10-052 P4",
                "sensitive": False,
                "category": "execution",
            },
        )
    )
    registry.register(
        Action(
            name="repair_task",
            description="修复失败任务 (repair_task.json → Agent 重跑 → 验证重跑)",
            handler=repair_task,
            permission="project",
            metadata={
                "service": "RepairManager (复用 execute_task)",
                "phase": "S10-053 P3",
                "sensitive": True,
                "category": "execution",
            },
        )
    )
    registry.register(
        Action(
            name="accept_project",
            description=(
                "项目验收 (USER_ACCEPTANCE → DELIVERED: 执行完成 + 验证通过后"
                "经用户确认交付)"
            ),
            handler=accept_project,
            permission="project",
            metadata={
                "service": "ExecutionOrchestrator.accept_project",
                "phase": "S10-055 P5",
                "sensitive": True,
                "category": "execution",
            },
        )
    )
    registry.register(
        Action(
            name="workforce",
            description="查看团队 (AgentRegistry + AgentMetrics 合并 → 团队状态)",
            handler=workforce,
            permission="user",
            metadata={
                "service": "AgentRegistry + AgentMetrics (workforce_snapshot)",
                "phase": "S10-055 Task 005",
                "sensitive": False,
                "category": "workforce",
            },
        )
    )
    registry.register(
        Action(
            name="task_owner",
            description="谁负责这个任务 (execution_state 最近任务 → Agent)",
            handler=task_owner,
            permission="user",
            metadata={
                "service": "execution_state.json / execution_records.json",
                "phase": "S10-055 Task 006",
                "sensitive": False,
                "category": "workforce",
            },
        )
    )
    registry.register(
        Action(
            name="agent_reason",
            description="为什么选择该 Agent (execution_plan.json reason → 可解释)",
            handler=agent_reason,
            permission="user",
            metadata={
                "service": "execution_plan.json reason (AgentMatcher)",
                "phase": "S10-055 Task 006",
                "sensitive": False,
                "category": "workforce",
            },
        )
    )
    registry.register(
        Action(
            name="team_execute",
            description=(
                "团队模式执行项目 (execute_project mode=team: 团队成员角色匹配 "
                "+ 依赖拓扑排序 + 冲突检测记录)"
            ),
            handler=_team_execute,
            permission="project",
            metadata={
                "service": "ExecutionOrchestrator.execute_project(mode=team)",
                "phase": "S10-056 批次 B",
                "sensitive": True,
                "category": "team",
            },
        )
    )
    registry.register(
        Action(
            name="team_dependencies",
            description="任务依赖图 (TaskDependencyGraph 只读视图: task_dependencies.json)",
            handler=_team_dependencies,
            permission="user",
            metadata={
                "service": "TaskDependencyGraph (task_dependencies.json)",
                "phase": "S10-056 批次 B",
                "sensitive": False,
                "category": "team",
            },
        )
    )
    registry.register(
        Action(
            name="team_conflicts",
            description="文件冲突记录 (ConflictDetector 只读视图, 检测不解决)",
            handler=_team_conflicts,
            permission="user",
            metadata={
                "service": "ConflictDetector (conflicts.json)",
                "phase": "S10-056 批次 B",
                "sensitive": False,
                "category": "team",
            },
        )
    )
    registry.register(
        Action(
            name="team",
            description=(
                "团队协作视图 (查看团队 → 成员角色/负载/绩效; 创建团队 → "
                "TeamRegistry.create; 团队执行/团队依赖/团队冲突 → 对应视图)"
            ),
            handler=team,
            permission="user",
            metadata={
                "service": "TeamRegistry + TeamService (team_snapshot)",
                "phase": "S10-056",
                "sensitive": False,
                "category": "team",
            },
        )
    )
    # S10-063: 生产治理命令 (factory status/budget/review)
    registry.register(
        Action(
            name="factory_status",
            description="生产状态 (项目/状态/计划版本/治理状态)",
            handler=governance_status,
            permission="user",
            metadata={"service": "orchestrator state", "phase": "S10-063",
                      "sensitive": False, "category": "governance"},
        )
    )
    registry.register(
        Action(
            name="factory_budget",
            description="预算查询 (消耗/剩余/等级)",
            handler=governance_budget,
            permission="user",
            metadata={"service": "CostLedger + BudgetEnforcer", "phase": "S10-063",
                      "sensitive": False, "category": "governance"},
        )
    )
    registry.register(
        Action(
            name="factory_review",
            description="生产评审 (待审列表 / approve / reject)",
            handler=governance_review,
            permission="user",
            metadata={"service": "ReviewGate", "phase": "S10-063",
                      "sensitive": False, "category": "governance"},
        )
    )
    # S10-065: 引导式 UX actions (自然语言入口)
    registry.register(
        Action(
            name="discovery_start",
            description="产品需求发现 (引导式: 我想做X → 澄清 → 确认)",
            handler=discovery_start,
            permission="user",
            metadata={"service": "DiscoverySession", "phase": "S10-065",
                      "sensitive": False, "category": "guided"},
        )
    )
    registry.register(
        Action(
            name="production_session_view",
            description="生产会话视图 (查看进度/现在做到哪了)",
            handler=production_session_view,
            permission="user",
            metadata={"service": "ProductionSession", "phase": "S10-065",
                      "sensitive": False, "category": "guided"},
        )
    )
    registry.register(
        Action(
            name="resume_project",
            description="恢复执行 (继续/继续执行)",
            handler=resume_project,
            permission="user",
            metadata={"service": "orchestrator.resume", "phase": "S10-065",
                      "sensitive": False, "category": "guided"},
        )
    )
    registry.register(
        Action(
            name="review_view",
            description="人工评审视图 (为什么停了)",
            handler=review_view,
            permission="user",
            metadata={"service": "ReviewGate + ReviewView", "phase": "S10-065",
                      "sensitive": False, "category": "guided"},
        )
    )
    registry.register(
        Action(
            name="review_approve",
            description="批准评审 (接受/批准/同意)",
            handler=review_approve,
            permission="user",
            metadata={"service": "ReviewGate.approve", "phase": "S10-065",
                      "sensitive": False, "category": "guided"},
        )
    )
    registry.register(
        Action(
            name="review_reject",
            description="拒绝评审 (拒绝)",
            handler=review_reject,
            permission="user",
            metadata={"service": "ReviewGate.reject", "phase": "S10-065",
                      "sensitive": False, "category": "guided"},
        )
    )
    registry.register(
        Action(
            name="review_cancel",
            description="取消评审 (取消)",
            handler=review_cancel,
            permission="user",
            metadata={"service": "ReviewGate.cancel", "phase": "S10-065",
                      "sensitive": False, "category": "guided"},
        )
    )
    # S10-066: Product Intelligence CLI (factory product *)
    registry.register(
        Action(
            name="product_intelligence",
            description="产品智能分析 (分析产品/产品智能 → 8 模块报告)",
            handler=product_intelligence,
            permission="user",
            metadata={"service": "ProductIntelligenceEngine", "phase": "S10-066",
                      "sensitive": False, "category": "product"},
        )
    )
    registry.register(
        Action(
            name="product_market",
            description="市场分析 (产品市场/市场分析)",
            handler=product_market,
            permission="user",
            metadata={"service": "ProductIntelligenceEngine", "phase": "S10-066",
                      "sensitive": False, "category": "product"},
        )
    )
    registry.register(
        Action(
            name="product_persona",
            description="用户画像 (产品画像/用户画像)",
            handler=product_persona,
            permission="user",
            metadata={"service": "ProductIntelligenceEngine", "phase": "S10-066",
                      "sensitive": False, "category": "product"},
        )
    )
    registry.register(
        Action(
            name="product_mvp",
            description="MVP 规划 (MVP规划/MVP拆分)",
            handler=product_mvp,
            permission="user",
            metadata={"service": "ProductIntelligenceEngine", "phase": "S10-066",
                      "sensitive": False, "category": "product"},
        )
    )
    registry.register(
        Action(
            name="product_value",
            description="产品价值评分 (产品价值/价值评分)",
            handler=product_value,
            permission="user",
            metadata={"service": "ProductIntelligenceEngine", "phase": "S10-066",
                      "sensitive": False, "category": "product"},
        )
    )
    # S10-067: Memory Learning CLI (factory memory * — 经验智能)
    registry.register(
        Action(
            name="memory_search",
            description="经验检索 (搜索经验/查找经验 → 关键词检索)",
            handler=memory_search,
            permission="user",
            metadata={"service": "ExperienceRetriever", "phase": "S10-067",
                      "sensitive": False, "category": "memory"},
        )
    )
    registry.register(
        Action(
            name="memory_learn",
            description="学习经验 (学习经验/经验学习 → 提取 + 模式 + Agent 画像)",
            handler=memory_learn,
            permission="user",
            metadata={"service": "LearningEngine", "phase": "S10-067",
                      "sensitive": False, "category": "memory"},
        )
    )
    registry.register(
        Action(
            name="memory_stats",
            description="经验统计 (经验统计 → 按类型/成功/Agent)",
            handler=memory_stats,
            permission="user",
            metadata={"service": "ExperienceStore.stats", "phase": "S10-067",
                      "sensitive": False, "category": "memory"},
        )
    )
    registry.register(
        Action(
            name="memory_analyze_agent",
            description="Agent 成长分析 (分析Agent/Agent成长 → 能力画像)",
            handler=memory_analyze_agent,
            permission="user",
            metadata={"service": "PatternLearner.learn_agent", "phase": "S10-067",
                      "sensitive": False, "category": "memory"},
        )
    )
    registry.register(
        Action(
            name="memory_export",
            description="导出经验 (导出经验 → experience_export.json)",
            handler=memory_export,
            permission="user",
            metadata={"service": "ExperienceStore", "phase": "S10-067",
                      "sensitive": False, "category": "memory"},
        )
    )
    # S10-068: Debug Intelligence CLI (factory debug * — 调试智能)
    registry.register(
        Action(
            name="debug_analyze",
            description="调试分析 (分析错误/为什么失败/debug → DebugDecision)",
            handler=debug_analyze,
            permission="user",
            metadata={"service": "DebugEngine.analyze", "phase": "S10-068",
                      "sensitive": False, "category": "debug"},
        )
    )
    registry.register(
        Action(
            name="debug_history",
            description="调试历史 (查看调试经验/debug历史 → debug_cases 历史)",
            handler=debug_history,
            permission="user",
            metadata={"service": "DebugEngine.history", "phase": "S10-068",
                      "sensitive": False, "category": "debug"},
        )
    )
    registry.register(
        Action(
            name="debug_recommend",
            description="修复建议 (修复建议/debug推荐 → 策略推荐)",
            handler=debug_recommend,
            permission="user",
            metadata={"service": "DebugEngine.analyze", "phase": "S10-068",
                      "sensitive": False, "category": "debug"},
        )
    )
    registry.register(
        Action(
            name="debug_stats",
            description="调试统计 (debug统计/调试统计 → 按错误类型/策略统计)",
            handler=debug_stats,
            permission="user",
            metadata={"service": "DebugEngine.stats", "phase": "S10-068",
                      "sensitive": False, "category": "debug"},
        )
    )
    # S10-068 Part 2: Autonomous Debug & Repair CLI (factory debug * — 完整闭环)
    registry.register(
        Action(
            name="debug_session",
            description="开始调试 (开始调试/调试会话 → DebugSession 会话启动)",
            handler=debug_session,
            permission="user",
            metadata={"service": "DebugPipeline.start", "phase": "S10-068 Part 2",
                      "sensitive": False, "category": "debug"},
        )
    )
    registry.register(
        Action(
            name="debug_root_cause",
            description="根因分析 (找一下根因/根因分析 → RootCause 9 类根因类型)",
            handler=debug_root_cause,
            permission="user",
            metadata={"service": "RootCauseAnalyzer.analyze", "phase": "S10-068 Part 2",
                      "sensitive": False, "category": "debug"},
        )
    )
    registry.register(
        Action(
            name="debug_repair",
            description="自动修复 (自动修复 → RepairSafety 治理闸后执行修复)",
            handler=debug_repair,
            permission="user",
            metadata={"service": "DebugPipeline.repair", "phase": "S10-068 Part 2",
                      "sensitive": False, "category": "debug"},
        )
    )
    registry.register(
        Action(
            name="debug_validate",
            description="验证修复 (验证修复 → PASS→SUCCESS / FAIL→RETRYING)",
            handler=debug_validate,
            permission="user",
            metadata={"service": "DebugPipeline.validate", "phase": "S10-068 Part 2",
                      "sensitive": False, "category": "debug"},
        )
    )
    registry.register(
        Action(
            name="debug_resume",
            description="继续调试 (继续调试 → REVIEW 通过后继续调试)",
            handler=debug_resume,
            permission="user",
            metadata={"service": "DebugPipeline.resume", "phase": "S10-068 Part 2",
                      "sensitive": False, "category": "debug"},
        )
    )
    # S10-069: Audit Intelligence CLI (factory audit * — 统一审计智能)
    registry.register(
        Action(
            name="audit_events",
            description="审计记录 (查看审计记录/审计记录 → 事件列表)",
            handler=audit_events,
            permission="user",
            metadata={"service": "AuditStore.query", "phase": "S10-069",
                      "sensitive": False, "category": "audit"},
        )
    )
    registry.register(
        Action(
            name="audit_trace",
            description="审计追踪 (审计追踪/查看审计链路 → trace 全链路事件)",
            handler=audit_trace,
            permission="user",
            metadata={"service": "AuditStore.query(trace_id)", "phase": "S10-069",
                      "sensitive": False, "category": "audit"},
        )
    )
    registry.register(
        Action(
            name="audit_chain",
            description="审计决策链 (审计决策链 → 根→子→相关→最终)",
            handler=audit_chain,
            permission="user",
            metadata={"service": "AuditDecisionChain.get_chain", "phase": "S10-069",
                      "sensitive": False, "category": "audit"},
        )
    )
    registry.register(
        Action(
            name="audit_decision",
            description="审计决策 (审计决策 → 含 decision 字段的事件)",
            handler=audit_decision,
            permission="user",
            metadata={"service": "AuditQuery.by_decision", "phase": "S10-069",
                      "sensitive": False, "category": "audit"},
        )
    )
    registry.register(
        Action(
            name="audit_explain",
            description="审计解释 (为什么创建这个任务/为什么选择这个Agent/为什么停了)",
            handler=audit_explain,
            permission="user",
            metadata={"service": "AuditExplain.explain", "phase": "S10-069",
                      "sensitive": False, "category": "audit"},
        )
    )
    registry.register(
        Action(
            name="audit_task",
            description="审计任务 (审计任务 → 任务全生命周期事件)",
            handler=audit_task,
            permission="user",
            metadata={"service": "AuditStore.query(task_id)", "phase": "S10-069",
                      "sensitive": False, "category": "audit"},
        )
    )
    registry.register(
        Action(
            name="audit_agent",
            description="审计Agent (审计Agent → Agent 全部事件)",
            handler=audit_agent,
            permission="user",
            metadata={"service": "AuditStore.query(agent_id)", "phase": "S10-069",
                      "sensitive": False, "category": "audit"},
        )
    )
    registry.register(
        Action(
            name="audit_cost",
            description="成本审计 (查看项目成本审计/成本审计 → 成本事件聚合)",
            handler=audit_cost,
            permission="user",
            metadata={"service": "AuditExplain.why_cost", "phase": "S10-069",
                      "sensitive": False, "category": "audit"},
        )
    )
    registry.register(
        Action(
            name="audit_export",
            description="导出审计 (导出审计 → audit_export.json)",
            handler=audit_export,
            permission="user",
            metadata={"service": "AuditStore.export", "phase": "S10-069",
                      "sensitive": False, "category": "audit"},
        )
    )
    registry.register(
        Action(
            name="audit_stats",
            description="审计统计 (审计统计 → total + by_type/status/actor + 完整性)",
            handler=audit_stats,
            permission="user",
            metadata={"service": "AuditStore.stats", "phase": "S10-069",
                      "sensitive": False, "category": "audit"},
        )
    )
    return registry
