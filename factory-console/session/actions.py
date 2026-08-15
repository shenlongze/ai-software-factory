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
from .intent import INTENT_CREATE_PROJECT, IntentObject
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
    team_id = _slugify(name) or "team"
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


def team(context: ExecutionContext) -> ActionResult:
    """Agent Team 协作视图 (S10-056, 验收 E/F): \"创建团队\" → TeamRegistry.create;
    其余 (\"查看团队/团队状态/团队协作\") → 默认团队协作视图 (team_snapshot)。

    只读查询 (非敏感, 无确认门); 失败安全: 数据缺失 → 默认团队/占位, 不抛。
    workforce action 保持独立 (兼容既有 \"查看团队\" → 团队状态路径)。
    """
    context.require("user")
    raw = context.intent.raw if context.intent else ""
    if "创建团队" in raw:
        return _team_create(context, raw)
    return _team_view(context)


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
            name="team",
            description=(
                "团队协作视图 (查看团队 → 成员角色/负载/绩效; "
                "创建团队 → TeamRegistry.create)"
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
    return registry
