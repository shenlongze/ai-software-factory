"""tests/console/test_console_web_adapter.py — Phase 11B FastAPI Adapter 测试 (ADR-0035)。

覆盖 (factory-console/web/backend/fastapi_adapter.py):
- build_console_service: 按工厂根装配 (镜像 CLI, 失败安全; 无需 fastapi)
- build_app / create_app: 8 个只读端点冒烟 (TestClient)
  - /api/dashboard → 200 七域 JSON (空工厂 → 全空域)
  - /api/projects, /api/approvals, /api/recommendations, /api/experience,
    /api/providers → 200 列表
  - /api/projects/{id}/lifecycle + /api/decisions/{id} → 存在 200 / 缺失 404
- Permission Boundary: 只读路由 (GET/HEAD) + S9-002 审批决定两 POST
  (approve/reject) + S10-006.5 创建 POST + 项目管理 PATCH/DELETE
  (/api/projects/{id} — 重命名/改 idea/删除; 无 PUT 写路径)
- 审计集成: 端点命中 → events.db 出现 console.viewed / console.dashboard.viewed
- 静态托管: dist/ 存在 → GET / 返回 index.html (SPA)

fastapi/httpx 未安装 (仅 console 侧 venv) → 模块级 importorskip 跳过
HTTP 部分; build_console_service 装配测试不依赖 fastapi, 始终运行。
basename 全仓库唯一 (test_console_* 前缀)。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

from console_helpers import event_types_of  # noqa: E402

#: factory-console 包名含连字符 → importlib 加载 (同 tests/console 其余测试模式)
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")
_models = importlib.import_module("factory-console.models")


# ------------------------------------------------------------------ 装配 (无 fastapi 依赖)


class TestBuildConsoleService:
    def test_assembles_service_from_factory_root(self, factory_root: Path):
        """build_console_service 按工厂根装配 ConsoleService (七域 dashboard 可读)。

        注: 无 workspace.yaml 时 WorkspaceManager 自动发现示例项目 (与 CLI
        _open_workspace_manager 同行为) — 断言七域结构, 不断言空工厂。
        """
        service = _adapter.build_console_service(factory_root)
        dashboard = service.dashboard()
        assert set(dashboard.SECTIONS) == {
            "projects", "approvals", "agents", "decisions", "cost", "experience", "activity",
        }
        assert dashboard.projects is not None
        assert dashboard.approvals is not None
        assert dashboard.cost.total_cost >= 0.0
        assert dashboard.experience.total >= 0

    def test_default_root_is_dot_factory(self):
        """DEFAULT_ROOT 与 CLI 同口径 (~/.factory)。"""
        assert _adapter.DEFAULT_ROOT == Path.home() / ".factory"


# ------------------------------------------------------------------ HTTP 冒烟 (fastapi + httpx)

try:  # fastapi/httpx 未安装 (仅 console 侧 venv) → HTTP 类跳过, 装配测试仍运行
    from fastapi.testclient import TestClient  # noqa: E402

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装 (console 侧 venv 需安装)"
)


class _StubService:
    """最薄只读桩: dashboard 七域 + 8 个读接口 (与 11A ConsoleService 同签名)。

    S10-006.5 收尾: 新增项目管理接口 (update_project/delete_project) —
    镜像真实 service 错误语义 (空 name/idea → ValueError; 项目不存在 →
    None), 供 HTTP 层 400/404/409 映射断言。
    """

    def dashboard(self):
        return _models.ConsoleDashboard()

    def list_projects(self):
        return [_models.ProjectSummary(id="demo", name="Demo Project", status="active")]

    def project_lifecycle(self, project_id):
        if project_id != "demo":
            return None
        return _models.LifecycleSummary(project_id=project_id, status="running", next_actions=["do x"])

    def update_project(self, project_id, *, name=None, idea=None, starred=None, archived=None):
        """镜像 service.update_project: 空值 ValueError / 不存在 None。"""
        cleaned_name = name.strip() if isinstance(name, str) else ""
        cleaned_idea = idea.strip() if isinstance(idea, str) else ""
        if name is not None and not cleaned_name:
            raise ValueError("name is required (空名字不落库)")
        if idea is not None and not cleaned_idea:
            raise ValueError("idea is required (空想法不落库)")
        if not cleaned_name and not cleaned_idea:
            raise ValueError("nothing to update (name/idea 至少提供一项)")
        if project_id != "demo":
            return None
        from types import SimpleNamespace

        return SimpleNamespace(
            id=project_id,
            name=cleaned_name or "Demo Project",
            goal=cleaned_idea or "记账",
            lifecycle=SimpleNamespace(value="idea"),
        )

    def delete_project(self, project_id):
        if project_id != "demo":
            return None
        return True

    def list_approvals(self):
        return [_models.ApprovalSummary(id="req-1", artifact_id="art-1", status="pending")]

    def get_decision(self, decision_id):
        if decision_id != "dec-1":
            return None
        return _models.DecisionSummary(id=decision_id, recommendation="a", score=0.9)

    def list_recommendations(self, limit=10):
        return [_models.RecommendationSummary(id="rec-1", score=0.92)]

    def list_experience(self, limit=10):
        return [_models.ExperienceSummary(id="exp-1", score=0.8)]

    def list_providers(self):
        return [_models.ProviderSummary(id="hermes")]


@pytest.fixture
def client():
    """注入 stub service 的 TestClient (无真实工厂数据, 断言 HTTP 绑定)。"""
    pytest.importorskip("fastapi")
    app = _adapter.build_app(_StubService())
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded_client(event_logger):
    """带 EventLogger 的 client (审计断言: console.* 事件写入 events.db)。"""
    pytest.importorskip("fastapi")
    app = _adapter.build_app(_StubService(), event_logger=event_logger)
    with TestClient(app) as c:
        yield c


@requires_fastapi
class TestDashboardEndpoint:
    def test_dashboard_200_seven_domains(self, client):
        resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {
            "projects", "approvals", "agents", "decisions", "cost", "experience", "activity",
        }

    def test_dashboard_audit_event(self, seeded_client, event_store):
        seeded_client.get("/api/dashboard")
        assert "console.dashboard.viewed" in event_types_of(event_store)

    def test_dashboard_returns_json_content_type(self, client):
        resp = client.get("/api/dashboard")
        assert resp.headers["content-type"].startswith("application/json")


@requires_fastapi
class TestReadOnlyEndpoints:
    def test_projects(self, client):
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["id"] == "demo"

    def test_lifecycle_exists(self, client):
        resp = client.get("/api/projects/demo/lifecycle")
        assert resp.status_code == 200
        assert resp.json()["project_id"] == "demo"

    def test_lifecycle_missing_404(self, client):
        resp = client.get("/api/projects/nope/lifecycle")
        assert resp.status_code == 404

    def test_approvals(self, client):
        resp = client.get("/api/approvals")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["artifact_id"] == "art-1"

    def test_approvals_pending_only_query(self, client):
        resp = client.get("/api/approvals?pending_only=true")
        assert resp.status_code == 200

    def test_decision_exists(self, client):
        resp = client.get("/api/decisions/dec-1")
        assert resp.status_code == 200
        assert resp.json()["recommendation"] == "a"

    def test_decision_missing_404(self, client):
        resp = client.get("/api/decisions/nope")
        assert resp.status_code == 404

    def test_recommendations(self, client):
        resp = client.get("/api/recommendations")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["score"] == 0.92

    def test_experience(self, client):
        resp = client.get("/api/experience")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["id"] == "exp-1"

    def test_providers(self, client):
        resp = client.get("/api/providers")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["id"] == "hermes"

    def test_unknown_api_path_404(self, client):
        resp = client.get("/api/does-not-exist")
        assert resp.status_code == 404

    def test_views_audited(self, seeded_client, event_store):
        seeded_client.get("/api/projects")
        seeded_client.get("/api/providers")
        types = event_types_of(event_store)
        assert "console.viewed" in types
        assert types.count("console.viewed") == 2


@requires_fastapi
class TestProjectManagementEndpoints:
    """S10-006.5 收尾: PATCH/DELETE /api/projects/{id} 端点语义 (200/400/404/409)。"""

    def test_update_project_200_renames(self, client):
        resp = client.patch("/api/projects/demo", json={"name": "记账本"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == "demo"
        assert body["name"] == "记账本"
        assert body["status"] == "idea"

    def test_update_project_idea_field(self, client):
        resp = client.patch("/api/projects/demo", json={"idea": "记账 + 报表"})
        assert resp.status_code == 200
        assert resp.json()["idea"] == "记账 + 报表"

    def test_update_project_empty_name_400(self, client):
        resp = client.patch("/api/projects/demo", json={"name": "   "})
        assert resp.status_code == 400
        assert "name is required" in resp.json()["error"]["message"]

    def test_update_project_empty_body_400(self, client):
        resp = client.patch("/api/projects/demo", json={})
        assert resp.status_code == 400
        assert "nothing to update" in resp.json()["error"]["message"]

    def test_update_project_missing_404(self, client):
        resp = client.patch("/api/projects/nope", json={"name": "x"})
        assert resp.status_code == 404

    def test_delete_project_200(self, client):
        resp = client.delete("/api/projects/demo")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": True, "project_id": "demo"}

    def test_delete_project_missing_404(self, client):
        resp = client.delete("/api/projects/nope")
        assert resp.status_code == 404

    def test_delete_project_running_409(self, client):
        """运行中项目删除 → 409 (ProjectConflictError 映射, 诚实拒绝)。"""
        import importlib

        _service = importlib.import_module("factory-console.service")

        class _RunningService(_StubService):
            def delete_project(self, project_id):
                raise _service.ProjectConflictError(
                    f"project is running: {project_id} (运行中不可删除, 等待完成后重试)"
                )

        app = _adapter.build_app(_RunningService())
        with TestClient(app) as c:
            resp = c.delete("/api/projects/demo")
        assert resp.status_code == 409
        assert "project is running" in resp.json()["error"]["message"]


@requires_fastapi
class TestPermissionBoundary:
    def test_write_routes_limited_to_approval_decisions(self, client):
        """Permission Boundary (S9-002 + S10-004/006/006.5/010): 写路由白名单。

        用户解除 Console 冻结后, 写路径 = 审批决定 POST (approve|reject,
        走 org Approval 状态机, source=console 审计) + Runtime 实例生命周期
        (POST /projects/{id}/runtimes 创建 + /runtimes/{id}/start|stop|
        screenshot) + Review 反馈 (POST /review-feedback) + 项目创建
        (POST /api/projects — S10-006.5 org 项目壳) + Workflow 启动/对话
        (POST /projects/{id}/start|chat — S10-006.5 P1-A 触发执行链/消息
        落库) + 项目管理 PATCH/DELETE /api/projects/{id} (S10-006.5 收尾
        — 重命名/改 idea + 删除 [运行中 409 保护]) + Backlog 写路径
        (S10-010 Task 3 — POST/PATCH/DELETE /api/projects/{id}/backlog*:
        层级创建 + Task 更新/删除, 只落 management/ 目录信源); 其余一切
        路由只读 (GET/HEAD), 无 PUT。
        """
        app = _adapter.build_app(_StubService())
        for route in app.routes:
            if not hasattr(route, "methods"):
                continue
            for route_method in route.methods:
                if route_method in {"GET", "HEAD"}:
                    continue
                assert route_method in {"POST", "PATCH", "DELETE"}, (
                    f"白名单外写路由泄漏: {route_method} {getattr(route, 'path', '?')}"
                )
                path = getattr(route, "path", "")
                # 审批决定 + Runtime 生命周期 + Review 反馈 + 项目创建 + Workflow 启动/对话
                is_approval = path.endswith("/approve") or path.endswith("/reject")
                is_runtime_lifecycle = (
                    "/runtimes" in path or "/runtime-sessions" in path or "/sessions" in path
                    or path == "/api/runtime/execute"
                )
                # S10-018: Tool 执行写面 (POST /api/tools/{id}/execute)
                is_tool_execute = path.startswith("/api/tools/") and path.endswith("/execute")
                # S10-020: MCP 连接写面 (POST /api/mcp/connections — 注册外部 MCP 服务)
                is_mcp_connect = path == "/api/mcp/connections" and route_method == "POST"
                is_review_feedback = path.endswith("/review-feedback")
                is_project_create = path == "/api/projects"
                # S10-007: AI 想法理解 (POST /api/projects/suggest — 建议不落库,
                # 非关键路径; 与创建同为想法输入写面, 白名单内)
                is_project_suggest = route_method == "POST" and path == "/api/projects/suggest"
                is_discovery_answer = route_method == "POST" and path.endswith("/discovery/answer")
                is_discovery_complete = route_method == "POST" and path.endswith("/discovery/complete")
                # S10-009-005: Confirm+Rename 事务 (POST /api/projects/{id}/confirm — 白名单)
                is_project_confirm = route_method == "POST" and path.endswith("/confirm")
                is_workflow_start = path.endswith("/start") or path.endswith("/chat")
                # S10-006.5 收尾: 项目管理 (PATCH/DELETE /api/projects/{id})
                is_project_update = route_method == "PATCH" and path == "/api/projects/{project_id}"
                is_project_delete = route_method == "DELETE" and path == "/api/projects/{project_id}"
                # S10-010 Task 3: Backlog 写路径 (POST/PATCH/DELETE
                # /api/projects/{id}/backlog* — 层级 CRUD + Task 更新/删除)
                is_backlog_write = "/backlog" in path
                # S10-010 Task 4: Sprint/Milestone/Roadmap 写路径 (POST/PATCH/
                # DELETE /api/projects/{id}/sprints*|milestones*|roadmap* —
                # 执行窗口/路线 CRUD + Planning 预留, 只落 management/ 目录信源)
                is_management_write = (
                    "/sprints" in path or "/milestones" in path or "/roadmap" in path
                )
                # v1.1.45: 系统更新 (POST /api/system/update — git pull+pip, 有审计)
                is_system_update = (
                    route_method == "POST" and path == "/api/system/update"
                )
                # v1.1.61: 默认项目设置 (POST /api/board/default — 写偏好文件, 非敏感)
                is_board_default = (
                    route_method == "POST" and path == "/api/board/default"
                )
                # v1.1.63: 任务细化 (POST /api/board/split — 拆子任务写项目数据)
                is_board_split = (
                    route_method == "POST" and path == "/api/board/split"
                )
                # v1.1.73: 文档配置保存 (POST /api/board/docs/config — 写项目偏好)
                is_docs_config = (
                    route_method == "POST" and path == "/api/board/docs/config"
                )
                # v1.1.96: RAG 检索问答 (POST /api/rag/query — 只读索引检索,
                # 确定性规则零副作用 + E-5 审计)
                is_rag_query = (
                    route_method == "POST" and path == "/api/rag/query"
                )
                # v1.1.102: 设置管理面 — LLM 配置 (POST/PATCH /api/config/llm —
                # 新增/修改 provider, 写 providers.json 配置; api_key_ref 只收
                # env: 引用, 明文 key 400 拒绝)
                is_llm_config = (
                    route_method in {"POST", "PATCH"} and path == "/api/config/llm"
                )
                # v1.1.102: MCP 连接移除 (DELETE /api/mcp/connections/{id} —
                # 与 CLI factory mcp remove 同源)
                is_mcp_remove = (
                    route_method == "DELETE" and "/mcp/connections/" in path
                )
                # v1.1.102: Agent/Skill 管理 (POST /api/agents|skills 注册 +
                # DELETE /api/agents/{id}|/api/skills/{id} 移除 — 写 agents/
                # skills.json, 与 CLI factory agent/skill add|remove 同源)
                is_agent_write = (
                    (route_method == "POST" and path == "/api/agents")
                    or (route_method == "DELETE" and path.startswith("/api/agents/"))
                )
                is_skill_write = (
                    (route_method == "POST" and path == "/api/skills")
                    or (route_method == "DELETE" and path.startswith("/api/skills/"))
                )
                # v1.1.188 U-6: 本机 AI 注册 + 委派执行 (POST /api/local-ai/*)
                is_local_ai_write = (
                    route_method == "POST" and path.startswith("/api/local-ai")
                )
                # v1.1.189 U-4: 外部 skill 扫描加载 (POST /api/skills/scan)
                is_skill_scan = (
                    route_method == "POST" and path == "/api/skills/scan"
                )
                assert (
                    is_approval
                    or is_runtime_lifecycle
                    or is_review_feedback
                    or is_project_create
                    or is_project_suggest
                    or is_discovery_answer
                    or is_discovery_complete
                    or is_project_confirm
                    or is_workflow_start
                    or is_project_update
                    or is_project_delete
                    or is_backlog_write
                    or is_management_write
                    or is_tool_execute
                    or is_mcp_connect
                    or is_system_update
                    or is_board_default
                    or is_board_split
                    or is_docs_config
                    or is_rag_query
                    or is_llm_config
                    or is_mcp_remove
                    or is_agent_write
                    or is_skill_write
                    or is_local_ai_write
                    or is_skill_scan
                ), (
                    f"写路由超出白名单 (审批决定 + Runtime + 反馈 + 创建 + 启动 + "
                    f"项目管理 + Backlog + Sprint/Milestone/Roadmap + Tool + MCP + RAG): "
                    f"{route_method} {path}"
                )

    def test_client_write_surface_limited_to_approval_decisions(self):
        """前端 api client 写面仅审批决定 + Runtime + 创建 + 启动/对话 POST
        + 项目管理 PATCH/DELETE (updateProject/deleteProject; 无 put)。"""
        src = (Path(__file__).parents[2] / "factory-console" / "web" / "frontend"
               / "src" / "api" / "client.ts").read_text(encoding="utf-8")
        # 写 helper 存在但唯一 (sendJson → POST 写面)
        assert "sendJson" in src
        assert "approveApproval" in src
        assert "rejectApproval" in src
        # S10-006.5 P1-A: Workflow 启动/对话/状态 (POST start/chat + GET run-status)
        assert "startWorkflow" in src
        assert "sendChat" in src
        assert "runStatus" in src
        # S10-006.5 收尾: 项目管理写面 (PATCH 重命名/改 idea + DELETE 删除;
        # 均为 /api/projects/{id} 白名单路径, 无 put 语义)
        assert "updateProject" in src
        assert "deleteProject" in src
        assert "method: 'PATCH'" in src
        assert "method: 'DELETE'" in src
        # 无 put 写方法 (Permission Boundary: PUT 不在白名单)
        assert "function put" not in src
        assert "method: 'PUT'" not in src


@requires_fastapi
class TestStaticServing:
    def test_spa_index_served_when_dist_exists(self, client, tmp_path: Path):
        """dist/ 存在 → GET / 返回 index.html (SPA 托管)。"""
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html>console</html>", encoding="utf-8")
        app = _adapter.build_app(_StubService(), static_dir=dist)
        with TestClient(app) as c:
            resp = c.get("/")
            assert resp.status_code == 200
            assert "<html>console</html>" in resp.text

    def test_api_only_mode_when_no_dist(self, client):
        """无 dist/ → 纯 API 模式, / 无静态托管 (404)。"""
        resp = client.get("/")
        assert resp.status_code == 404
