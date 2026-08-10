"""factory-console/web/backend/fastapi_adapter.py — Phase 11B 最薄 FastAPI Adapter (ADR-0035)。

把 Phase 11A 路由函数 (factory-console/api/*) 挂为 HTTP 端点 + 托管前端
build 静态文件 (SPA)。只做 HTTP 绑定 (参数解析 / JSON 序列化 / 静态托管),
**不写任何 UI 逻辑**, 不修改 factory-console/service.py 或 api/* (只读适配)。

设计依据:
- phase11b-status.md: Browser → Web UI (React+TS) → Console API Layer (11A)
  → Factory Data; Web UI 只消费 Console API。
- 只读铁律 (phase11a-status.md + human-console-model.md): 全部端点 GET,
  零写路径 — 审批/决定/创建 等执行权永远在既有引擎 (9c Approval 状态机),
  Console 只读不决定。Permission Boundary: 本模块不注册任何 POST/PUT/DELETE。
- 审计 (ADR-0002 读审计同语义): 端点经 11A 路由函数注入 EventLogger →
  console.viewed / console.dashboard.viewed; logger 缺失 → 静默 (失败安全)。
- 依赖: fastapi + uvicorn 仅装在 console 侧 venv (不污染 factory-core
  pyproject)。Core 零修改。

装配:
- create_app(factory_root=...) — 镜像 cli.commands._open_console_service
  (全部 store 可选, 失败安全); 供 uvicorn 直接启动。
- build_app(service=..., static_dir=...) — 注入已装配 service; 供测试/
  复用方使用。

端点 (只读 GET + S9-002 审批决定 POST + S10-006.5 创建 POST):
  /api/dashboard                        → ConsoleDashboard 七域 (11A service.dashboard)
  /api/projects                         → list_projects (console.viewed)
  POST /api/projects                    → create_project ({idea,project_type,tech}
                                          → org 项目; 400/503 语义)   [S10-006.5]
  /api/projects/{project_id}/lifecycle  → get_project_lifecycle (None → 404)
  /api/approvals                        → list_approvals (?pending_only)
  /api/decisions/{decision_id}          → get_decision (None → 404)
  /api/recommendations                  → list_recommendations (?limit)
  /api/experience                       → list_experience (?limit)
  /api/providers                        → list_providers
  /api/workflows                        → list_workflows (?project_id)      [S9-002]
  /api/workflows/{workflow_id}          → get_workflow (None → 404)         [S9-002]
  /api/artifacts                        → list_artifacts (?project/workflow/type) [S9-002]
  POST /api/approvals/{id}/approve      → 审批放行 (404/409 映射)            [S9-002]
  POST /api/approvals/{id}/reject       → 审批否决 (404/409 映射)            [S9-002]
  GET  /api/review-feedback             → 审核反馈历史 (artifact/gate 过滤)   [S10-006]
  POST /api/review-feedback             → 保存反馈记录 (round 递增; 400/503)  [S10-006]
Permission Boundary (S9-002 收窄 + S10-004/006/006.5 扩展): 写路径仅
① 审批决定两 POST (approve/reject, reviewer="console" 落库 + source="console"
审计) ② Feedback Loop 一 POST (review-feedback — Reject 意见落库, 不触碰
引擎) ③ Runtime 实例生命周期 POST (创建/start/stop/screenshot, S10-004)
④ POST /api/projects (S10-006.5 — org 项目壳创建: org.project.created 审计,
只建壳不启动执行链); 其余端点全部 GET — register_project/成本写入等仍
不在 Console 范围 (S9-005/后续)。
静态: frontend build 产物 (dist/) — SPA html=True; 缺目录 → 纯 API 模式。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel

__all__ = ["DEFAULT_ROOT", "DEFAULT_PORT", "build_app", "build_console_service", "create_app"]

#: 默认后端端口 (uvicorn 启动提示用; vite dev proxy 同源约定)
DEFAULT_PORT = 8011

#: 默认工厂根 (与 cli.context.DEFAULT_ROOT 同口径: ~/.factory)
DEFAULT_ROOT = Path.home() / ".factory"


class _ApprovalDecisionBody(BaseModel):
    """POST 审批决定 body (S9-003: comment 透传落库 — Review 反馈输入)。

    兼容 S9-002 无 body 调用 (reviewer 默认 "console"); comment 默认空串
    (既有调用零破坏 — 决定事件/门落库字段不变)。
    """

    reviewer: str = "console"
    comment: str = ""


class _CreateRuntimeBody(BaseModel):
    """POST /projects/{id}/runtimes body (S10-004: 创建 Runtime Instance)。

    type: browser|terminal (沙箱实例类型); artifact_id: 绑定产物 (browser
    预览 ux_ui/code/release 对应产物, 无 → None — 创建后可从 Timeline 联动
    绑定)。type 合法性在 handler 显式校验 → 400 (语义清晰, 不依赖 pydantic 422)。
    """

    type: str
    artifact_id: str | None = None


class _CreateProjectBody(BaseModel):
    """POST /api/projects body (S10-006.5: 用户第一公里创建闭环)。

    {idea, project_type?, tech?}: idea 为必填想法 (空 → 400); project_type
    (web|mobile|desktop) 与 tech (auto|flutter|react|vue) 可选 — 宽容
    收窄 (非设计值 → 400), 透传 org Project 落库 (project_type/framework),
    不伪造 AI 技术选型。
    """

    idea: str
    project_type: str = ""
    tech: str = ""


class _ReviewFeedbackBody(BaseModel):
    """POST /api/review-feedback body (S10-006: Feedback Loop 反馈记录)。

    {artifact_id, gate_id, reviewer, comment}: Reject 决定后前端同时调用本
    端点保存结构化驳回意见 (round 按产物递增, 下轮 Agent 重生成输入)。
    comment 空 → 400 (无反馈不落库); reviewer 默认 "console" (与审批决定
    同口径); gate_id 记录来源审批门 (空串允许 — 兼容产物级反馈, 不强制)。
    """

    artifact_id: str
    gate_id: str = ""
    reviewer: str = "console"
    comment: str = ""


# ------------------------------------------------------------------ 装配


def build_console_service(factory_root: str | Path, *, event_logger: Any = None) -> Any:
    """按工厂根装配 ConsoleService (镜像 cli.commands._open_console_service)。

    全部 store 依赖可选 (失败安全: 缺任一 store → Console 按空数据处理);
    延迟导入 Core 包保 Removal Isolation (删除任一 Core 包不影响 Console 加载)。
    factory-console 包名含连字符 → importlib 按路径加载 (同 CLI 模式)。

    S9-002: 装配 org 数据空间 (root/org — ProjectStore + WorkflowLifecycle,
    与 factory-org 演示/CLI 同目录口径); event_logger 提供时注入带事件库的
    生命周期 (org.approval.* 决定事件 source="console" 落库审计); org 缺失
    → 跳过注入 (失败安全, 读命令永不因 org 缺失失败)。
    """
    root = Path(factory_root)
    root.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[3]  # .../ai-software-factory/
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        module = importlib.import_module("factory-console")
    except Exception as exc:  # 缺装/损坏 → 装配失败 (调用方决定兜底)
        raise RuntimeError("factory-console 未安装 (缺 factory-console/ 包)") from exc

    from agents.registry import AgentRegistry
    from agents.store import AgentStore

    from intelligence.store import DecisionStore, ExperienceStore, RecommendationStore

    from product.store import ProductStore

    from providers.registry import ProviderRegistry
    from providers.store import ProviderStore
    from providers.usage import UsageStore

    from tasks.store import TaskStore

    from workspace.manager import WorkspaceManager

    # S9-002: org 数据空间 (root/org — 与 factory-org CLI 同目录口径; 失败安全)
    project_store = None
    workflow_lifecycle = None
    try:
        org_dir = repo_root / "factory-org"
        if org_dir.is_dir() and str(org_dir) not in sys.path:
            sys.path.insert(0, str(org_dir))
        from org.projects import ProjectStore
        from org.workflow import WorkflowLifecycle

        project_store = ProjectStore(root / "org")
        workflow_lifecycle = WorkflowLifecycle(project_store, logger=event_logger)
    except Exception:
        project_store = None
        workflow_lifecycle = None

    # S10-004: Runtime 数据空间 (root/runtimes — 独立于 org, 原子写 JSON;
    # 失败安全: 装配失败 → None, runtime 操作按空/不存在处理)
    runtime_store = None
    runtime_screenshot_store = None
    try:
        _runtime_stores = importlib.import_module("factory-console.runtime_store")
        runtime_store = _runtime_stores.RuntimeInstanceStore(root / "runtimes")
        runtime_screenshot_store = _runtime_stores.RuntimeScreenshotStore(root / "runtimes")
    except Exception:
        runtime_store = None
        runtime_screenshot_store = None

    # S10-006: 审核反馈数据空间 (root/review_feedback.json — Feedback Loop
    # Reject 意见落库; 失败安全: 装配失败 → None, 反馈保存/查询按空处理)
    review_feedback_store = None
    try:
        _feedback_module = importlib.import_module("factory-console.review_feedback")
        review_feedback_store = _feedback_module.ReviewFeedbackStore(root)
    except Exception:
        review_feedback_store = None

    return module.ConsoleService(
        workspace_manager=WorkspaceManager(root),
        task_store=TaskStore(root / "tasks"),
        agent_registry=AgentRegistry(AgentStore(root / "agents")),
        product_store=ProductStore(root / "product"),
        decision_store=DecisionStore(root / "intelligence"),
        recommendation_store=RecommendationStore(root / "intelligence"),
        experience_store=ExperienceStore(root / "intelligence"),
        usage_store=UsageStore(root / "providers"),
        provider_registry=ProviderRegistry(ProviderStore(root / "providers")),
        project_store=project_store,
        workflow_lifecycle=workflow_lifecycle,
        # S10-004: Runtime 实例/截图持久化 (root/runtimes; 失败安全)
        runtime_store=runtime_store,
        runtime_screenshot_store=runtime_screenshot_store,
        # S10-006: 审核反馈持久化 (root/review_feedback.json — Feedback Loop
        # Reject 意见落库; 失败安全: 装配失败 → None, 保存/查询按空处理)
        review_feedback_store=review_feedback_store,
    )


def _open_event_logger(factory_root: str | Path) -> Any:
    """按工厂根打开 EventLogger (<root>/factory.db, CLI 同路径; 失败安全 → None)。"""
    from events.logger import EventLogger
    from events.store import EventStore

    try:
        return EventLogger(EventStore(Path(factory_root) / "factory.db"))
    except Exception:
        return None  # 事件库不可用 → 静默 (读审计失败不拖垮 API)


def build_app(
    service: Any,
    *,
    static_dir: str | Path | None = None,
    event_logger: Any = None,
) -> Any:
    """把已装配 ConsoleService 挂为 FastAPI app (最薄 HTTP 绑定)。

    只读铁律: 只注册 GET 端点 — 本函数不产生任何写路由 (Permission Boundary)。
    static_dir 存在 → 挂 SPA 静态托管 (html=True); 否则纯 API 模式。
    """
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.responses import StreamingResponse
    from fastapi.staticfiles import StaticFiles

    # 延迟 import 11A 路由函数 + 事件辅助 (仅依赖 factory-console.api, 无 Web 依赖)
    _api = importlib.import_module("factory-console.api")
    _events = importlib.import_module("factory-console.events")
    # S10-004: Runtime 状态机异常 (service 定义; api/__init__ 不导出 —
    # Adapter 层直接取 service 符号, 避免给 api 包加非路由导出)
    _service = importlib.import_module("factory-console.service")
    RuntimeStateError = _service.RuntimeStateError

    app = FastAPI(title="AI Software Factory — Human Console Web", version="0.1.0")

    @app.get("/api/dashboard")
    def api_dashboard() -> dict[str, Any]:
        """七域汇总 (11A ConsoleDashboard; 发 console.dashboard.viewed 审计)。"""
        dashboard = service.dashboard()
        logger = event_logger
        if logger is not None:
            _events.record_console_dashboard_viewed(
                logger,
                projects=len(dashboard.projects),
                pending_approvals=len(dashboard.pending_approvals),
                running_agents=len(dashboard.running_agents),
                decisions=len(dashboard.decisions),
                total_cost=dashboard.cost.total_cost,
                experiences=dashboard.experience.total,
                events=len(dashboard.activity),
            )
        return dashboard.to_dict()

    @app.get("/api/projects")
    def api_projects() -> list[dict[str, Any]]:
        """项目清单 (11A list_projects, 只读投影)。"""
        return [p.to_dict() for p in _api.list_projects(service, logger=event_logger)]

    @app.post("/api/projects", status_code=201)
    def api_create_project(body: _CreateProjectBody) -> dict[str, Any]:
        """创建项目 (S10-006.5: {idea, project_type?, tech?} → org 项目)。

        错误语义: idea 空 → 400 (空想法不创建); project_type/tech 非法
        → 400 (宽容收窄); org store 缺失/创建失败 → 503 (失败安全, 不
        拖垮 API); 成功 → 201 {project_id, name, idea, status}。写面
        (Permission Boundary): 与审批决定/Runtime/Review 反馈并列的
        Console 写路径 — 只建 org 项目壳 (org.project.created 审计),
        不启动执行链 (Step 4-5 后续 Sprint)。
        """
        idea = body.idea.strip()
        if not idea:
            raise HTTPException(status_code=400, detail="idea is required (空想法不创建)")
        project_type = body.project_type.strip()
        tech = body.tech.strip()
        for field_name, value, allowed in (
            ("project_type", project_type, ("", "web", "mobile", "desktop")),
            ("tech", tech, ("", "auto", "flutter", "react", "vue")),
        ):
            if value not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"{field_name} must be one of: {', '.join(a for a in allowed if a)}",
                )
        summary = _api.create_project(
            service,
            idea,
            project_type=project_type,
            tech=tech,
            logger=event_logger,
        )
        if summary is None:
            raise HTTPException(
                status_code=503, detail="project store unavailable (org 未装配)"
            )
        return summary.to_dict()

    @app.get("/api/projects/{project_id}/lifecycle")
    def api_project_lifecycle(project_id: str) -> dict[str, Any]:
        """生命周期快照; 无 → 404 (11A None 语义由 HTTP 层映射)。"""
        summary = _api.get_project_lifecycle(service, project_id, logger=event_logger)
        if summary is None:
            raise HTTPException(status_code=404, detail="lifecycle not found")
        return summary.to_dict()

    @app.get("/api/approvals")
    def api_approvals(
        pending_only: bool = Query(default=False),
    ) -> list[dict[str, Any]]:
        """审批清单 (11A list_approvals, 只读不决定)。"""
        return [
            a.to_dict()
            for a in _api.list_approvals(service, logger=event_logger, pending_only=pending_only)
        ]

    @app.get("/api/approval-gates")
    def api_approval_gates(
        status: str | None = Query(default=None),
        workflow_id: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        """org 审批门清单 (S9-002 — Approval 页决定操作对象; 只读查询)。"""
        return [
            g.to_dict()
            for g in _api.list_approval_gates(
                service, logger=event_logger, status=status, workflow_id=workflow_id
            )
        ]

    @app.get("/api/decisions/{decision_id}")
    def api_decision(decision_id: str) -> dict[str, Any]:
        """决策详情; 不存在 → 404。"""
        summary = _api.get_decision(service, decision_id, logger=event_logger)
        if summary is None:
            raise HTTPException(status_code=404, detail="decision not found")
        return summary.to_dict()

    @app.get("/api/recommendations")
    def api_recommendations(
        limit: int = Query(default=10, ge=1, le=100),
    ) -> list[dict[str, Any]]:
        """推荐产物 (11A list_recommendations, 只推荐不执行)。"""
        return [
            r.to_dict()
            for r in _api.list_recommendations(service, logger=event_logger, limit=limit)
        ]

    @app.get("/api/experience")
    def api_experience(
        limit: int = Query(default=10, ge=1, le=100),
    ) -> list[dict[str, Any]]:
        """经验记录 (11A list_experience, 六域)。"""
        return [
            e.to_dict() for e in _api.list_experience(service, logger=event_logger, limit=limit)
        ]

    @app.get("/api/providers")
    def api_providers() -> list[dict[str, Any]]:
        """Provider 目录 (11A list_providers)。"""
        return [p.to_dict() for p in _api.list_providers(service, logger=event_logger)]

    @app.get("/api/workflows")
    def api_workflows(
        project_id: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        """组织级 Workflow 运行清单 (S9-002; 阶段链进度聚合, 只读)。"""
        return [
            w.to_dict()
            for w in _api.list_workflows(service, logger=event_logger, project_id=project_id)
        ]

    @app.get("/api/workflows/{workflow_id}")
    def api_workflow_detail(workflow_id: str) -> dict[str, Any]:
        """单 Workflow 8 阶段链全视图; 无 org/不存在 → 404。"""
        detail = _api.get_workflow(service, workflow_id, logger=event_logger)
        if detail is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        return detail.to_dict()

    @app.get("/api/artifacts")
    def api_artifacts(
        project_id: str | None = Query(default=None),
        workflow_id: str | None = Query(default=None),
        type: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        """org Artifact 清单 (S9-002; project/workflow/type 过滤, 只读)。"""
        return [
            a.to_dict()
            for a in _api.list_artifacts(
                service,
                logger=event_logger,
                project_id=project_id,
                workflow_id=workflow_id,
                type=type,
            )
        ]

    @app.get("/api/artifacts/{artifact_id}")
    def api_artifact_detail(artifact_id: str) -> dict[str, Any]:
        """单产物详情 (S9-003: metadata 契约载荷 + review 审批门; 404 映射)。"""
        detail = _api.get_artifact(service, artifact_id, logger=event_logger)
        if detail is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return detail.to_dict()

    @app.get("/api/artifacts/{artifact_id}/content")
    def api_artifact_content(artifact_id: str) -> dict[str, Any]:
        """产物渲染内容 (S10-005 — location 文件文本: Code diff 兜底 / Release
        下载源; 缺失 → content null, 失败安全; 产物不存在 → 404)。"""
        content = _api.get_artifact_content(service, artifact_id, logger=event_logger)
        if content is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return content.to_dict()

    # ------------------------------------------------- S10-002: Runtime API
    # UI 与 CLI 共用 (Adapter 层只读 + SSE; 零 Core 修改, 只消费 org.* 查询)。

    @app.get("/api/projects/{project_id}/workflow")
    def api_project_workflow(project_id: str) -> dict[str, Any]:
        """项目工作流详情 (S10-002 — 8 阶段链 + 统计)。

        项目存在但无运行数据 → mock 工作流 (is_mock=True, 前端可展示);
        项目不存在 → 404 (mock 只兜底数据缺失, 不兜底不存在)。
        """
        detail = _api.get_project_workflow(service, project_id, logger=event_logger)
        if detail is None:
            raise HTTPException(status_code=404, detail="project not found")
        return detail.to_dict()

    @app.get("/api/workflows/{workflow_id}/stages")
    def api_workflow_stages(workflow_id: str) -> list[dict[str, Any]]:
        """Workflow 阶段运行明细 (S10-002 — 状态/agent/artifacts/duration/cost)。

        duration_s 从事件流推导 (stage_started → stage_completed 时间戳差);
        cost_usd 未跟踪 → null (诚实); 无 org/不存在 → 404。
        """
        runs = _api.get_workflow_stages(service, workflow_id, logger=event_logger)
        if runs is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        return [r.to_dict() for r in runs]

    @app.get("/api/projects/{project_id}/timeline")
    def api_project_timeline(
        project_id: str,
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        """Timeline 事件聚合 (S10-002 — user/stage/artifact/review/error)。

        数据源 = events.db org.* 事件 (与 SSE 同源同映射; Timeline 历史
        快照); 项目不存在 → 404; 无事件 → [] (诚实空态)。
        """
        events = _api.get_project_timeline(
            service, project_id, logger=event_logger, limit=limit
        )
        if events is None:
            raise HTTPException(status_code=404, detail="project not found")
        return [e.to_dict() for e in events]

    @app.get("/api/events/stream")
    def api_events_stream(
        project_id: str,
        since_seq: int = Query(default=0, ge=0),
        poll_interval: float = Query(default=1.0, ge=0.05),
        max_polls: int | None = Query(default=None, ge=1),
    ) -> StreamingResponse:
        """SSE 事件流 (S10-002 — Timeline 实时增量驱动; 只读 GET)。

        推送: stage.started / stage.completed / artifact.created /
        approval.required / error (SSE_EVENT_MAP); 从 events 库按
        project_id 轮询 (since_seq 断点续推); 无事件库 → 单条 error
        (mock=True) 后关闭 (失败安全)。max_polls/poll_interval 为
        测试/调试旋钮 (生产缺省: 无限轮询至客户端断开)。
        """
        import json

        def _generate() -> Iterator[str]:
            for name, data in _api.iter_sse_events(
                service,
                project_id,
                logger=event_logger,
                since_seq=since_seq,
                poll_interval=poll_interval,
                max_polls=max_polls,
            ):
                yield f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ------------------------------------------- S10-004: Runtime Workspace API
    # Instance 模式 (workspace-architecture.md §4 调整版): "+" 创建 browser|
    # terminal 实例 + start/stop 生命周期 + screenshot 预留。写路径新增
    # (Permission Boundary S10-004 扩展: 与审批决定并列的 Console 写路径 —
    # 仅 Runtime 实例生命周期, 不触碰 Core 引擎)。
    # 错误映射: 项目/实例不存在 → 404; 非法 type → 400; 状态机非法流转
    # (RuntimeStateError) → 409; 事件 (org.runtime.*) 由路由函数落库。

    @app.post("/api/projects/{project_id}/runtimes")
    def api_create_runtime(project_id: str, body: _CreateRuntimeBody) -> dict[str, Any]:
        """创建 Runtime Instance (starting; browser|terminal + artifact 绑定)。"""
        if body.type not in ("browser", "terminal"):
            raise HTTPException(
                status_code=400, detail="runtime type must be browser|terminal"
            )
        instance = _api.create_runtime(
            service,
            project_id,
            body.type,
            artifact_id=body.artifact_id,
            logger=event_logger,
        )
        if instance is None:
            raise HTTPException(status_code=404, detail="project not found")
        return instance.to_dict()

    @app.get("/api/projects/{project_id}/runtimes")
    def api_project_runtimes(project_id: str) -> list[dict[str, Any]]:
        """项目 Runtime 实例列表 (无 → []; 项目不存在 → 404)。"""
        instances = _api.list_runtimes(service, project_id, logger=event_logger)
        if instances is None:
            raise HTTPException(status_code=404, detail="project not found")
        return [r.to_dict() for r in instances]

    @app.get("/api/runtimes/{runtime_id}")
    def api_runtime_detail(runtime_id: str) -> dict[str, Any]:
        """单实例详情 (url/session/status; 不存在 → 404)。"""
        instance = _api.get_runtime(service, runtime_id, logger=event_logger)
        if instance is None:
            raise HTTPException(status_code=404, detail="runtime not found")
        return instance.to_dict()

    @app.post("/api/runtimes/{runtime_id}/start")
    def api_runtime_start(runtime_id: str) -> dict[str, Any]:
        """启动实例 (starting|stopped → running; 重启允许)。"""
        try:
            instance = _api.start_runtime(service, runtime_id, logger=event_logger)
        except RuntimeStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if instance is None:
            raise HTTPException(status_code=404, detail="runtime not found")
        return instance.to_dict()

    @app.post("/api/runtimes/{runtime_id}/stop")
    def api_runtime_stop(runtime_id: str) -> dict[str, Any]:
        """停止实例 (starting|running → stopped)。"""
        try:
            instance = _api.stop_runtime(service, runtime_id, logger=event_logger)
        except RuntimeStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if instance is None:
            raise HTTPException(status_code=404, detail="runtime not found")
        return instance.to_dict()

    @app.post("/api/runtimes/{runtime_id}/screenshot")
    def api_runtime_screenshot(runtime_id: str) -> dict[str, Any]:
        """截图预留: 保存截图记录 + artifact 引用 (完整 Feedback Loop 后续实现)。"""
        try:
            screenshot = _api.capture_runtime_screenshot(
                service, runtime_id, logger=event_logger
            )
        except RuntimeStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if screenshot is None:
            raise HTTPException(status_code=404, detail="runtime not found")
        return screenshot.to_dict()

    @app.post("/api/approvals/{approval_id}/approve")
    def api_approve_approval(
        approval_id: str,
        body: _ApprovalDecisionBody | None = None,
    ) -> dict[str, Any]:
        """审批放行 (S9-002: 接 org.approval S9-001; source=console 审计)。

        门不存在 → 404; 非 PENDING 门 (终态不可撤销) → 409 Conflict。
        S9-003: body.comment 透传落库 (gate.comment — Review 反馈输入)。
        """
        reviewer = body.reviewer if body is not None else "console"
        comment = body.comment if body is not None else ""
        try:
            summary = _api.approve_approval(
                service, approval_id, reviewer=reviewer, comment=comment
            )
        except Exception as exc:
            if _api.conflict_status(exc):
                raise HTTPException(status_code=409, detail="approval already decided") from exc
            raise
        if summary is None:
            raise HTTPException(status_code=404, detail="approval gate not found")
        return summary.to_dict()

    @app.post("/api/approvals/{approval_id}/reject")
    def api_reject_approval(
        approval_id: str,
        body: _ApprovalDecisionBody | None = None,
    ) -> dict[str, Any]:
        """审批否决 (S9-002: gate → REJECTED 终态 + workflow FAILED 停止)。

        错误语义同 approve (404 / 409); 决定不可撤销 — 审计铁律。
        S9-003: body.comment 透传落库 (否决原因 → 下轮重生成反馈输入)。
        """
        reviewer = body.reviewer if body is not None else "console"
        comment = body.comment if body is not None else ""
        try:
            summary = _api.reject_approval(
                service, approval_id, reviewer=reviewer, comment=comment
            )
        except Exception as exc:
            if _api.conflict_status(exc):
                raise HTTPException(status_code=409, detail="approval already decided") from exc
            raise
        if summary is None:
            raise HTTPException(status_code=404, detail="approval gate not found")
        return summary.to_dict()

    # ------------------------------------------- S10-006: Review Feedback API
    # Feedback Loop (workspace-architecture.md §3 Panel Review): Reject 决定后
    # 前端同时 POST /api/review-feedback 保存结构化驳回意见 — 下轮 Agent
    # 重生成输入的数据源 (gate.comment 由 S9-001 决定端点负责审计落库, 本
    # 端点只补 Loop 数据流, 不重设计审批 API)。
    # 错误语义: 400 空意见/缺 artifact_id (无反馈不落库); 503 缺 store
    # (失败安全 — 审批决定不受反馈保存失败影响, 前端按尽力而为处理)。

    @app.get("/api/review-feedback")
    def api_review_feedback(
        artifact_id: str | None = Query(default=None),
        gate_id: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        """审核反馈历史 (GET — 按 artifact/gate 过滤, round 升序)。

        无过滤 → 全部记录; 无匹配 → [] (诚实空态); 缺 store → [] (失败
        安全, 与 11A 读命令同哲学 — 查询永不因数据缺失失败)。
        """
        records = _api.list_review_feedback(
            service,
            artifact_id,
            gate_id=gate_id,
            logger=event_logger,
        )
        return [r.to_dict() for r in records]

    @app.post("/api/review-feedback")
    def api_save_review_feedback(body: _ReviewFeedbackBody) -> dict[str, Any]:
        """保存审核反馈记录 (POST — Reject 意见落库, round 按产物递增)。"""
        artifact_id = body.artifact_id.strip()
        if not artifact_id:
            raise HTTPException(status_code=400, detail="artifact_id is required")
        comment = body.comment.strip()
        if not comment:
            raise HTTPException(status_code=400, detail="comment is required (空意见不落库)")
        record = _api.save_review_feedback(
            service,
            reviewer=body.reviewer or "console",
            artifact_id=artifact_id,
            gate_id=body.gate_id,
            comment=comment,
        )
        if record is None:
            # 缺 review_feedback store → 503 (失败安全: 决定已成功, 反馈
            # 尽力而为; 前端显示提示不阻断流程)
            raise HTTPException(
                status_code=503, detail="review feedback store unavailable"
            )
        return record.to_dict()

    if static_dir is not None and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="web")

    return app


def create_app(
    factory_root: str | Path | None = None,
    *,
    static_dir: str | Path | None = None,
) -> Any:
    """装配 ConsoleService + EventLogger 并构建 app (uvicorn 入口)。

    factory_root=None → 用户默认工厂根 (~/.factory, 同 CLI FactoryContext)。
    """
    root = Path(factory_root) if factory_root is not None else DEFAULT_ROOT
    logger = _open_event_logger(root)
    service = build_console_service(root, event_logger=logger)
    return build_app(service, static_dir=static_dir, event_logger=logger)


if __name__ == "__main__":  # pragma: no cover — uvicorn 直接启动入口
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=DEFAULT_PORT)
