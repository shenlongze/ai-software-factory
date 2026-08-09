"""tests/console/test_console_web_adapter.py — Phase 11B FastAPI Adapter 测试 (ADR-0035)。

覆盖 (factory-console/web/backend/fastapi_adapter.py):
- build_console_service: 按工厂根装配 (镜像 CLI, 失败安全; 无需 fastapi)
- build_app / create_app: 8 个只读端点冒烟 (TestClient)
  - /api/dashboard → 200 七域 JSON (空工厂 → 全空域)
  - /api/projects, /api/approvals, /api/recommendations, /api/experience,
    /api/providers → 200 列表
  - /api/projects/{id}/lifecycle + /api/decisions/{id} → 存在 200 / 缺失 404
- Permission Boundary: 只读路由 (GET/HEAD) + S9-002 审批决定两 POST
  (approve/reject; 无 PUT/PATCH/DELETE 写路径)
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
    """最薄只读桩: dashboard 七域 + 8 个读接口 (与 11A ConsoleService 同签名)。"""

    def dashboard(self):
        return _models.ConsoleDashboard()

    def list_projects(self):
        return [_models.ProjectSummary(id="demo", name="Demo Project", status="active")]

    def project_lifecycle(self, project_id):
        if project_id != "demo":
            return None
        return _models.LifecycleSummary(project_id=project_id, status="running", next_actions=["do x"])

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
        assert resp.json()[0]["id"] == "demo"

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
        assert resp.json()[0]["artifact_id"] == "art-1"

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
        assert resp.json()[0]["score"] == 0.92

    def test_experience(self, client):
        resp = client.get("/api/experience")
        assert resp.status_code == 200
        assert resp.json()[0]["id"] == "exp-1"

    def test_providers(self, client):
        resp = client.get("/api/providers")
        assert resp.status_code == 200
        assert resp.json()[0]["id"] == "hermes"

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
class TestPermissionBoundary:
    def test_write_routes_limited_to_approval_decisions(self, client):
        """Permission Boundary (S9-002): 写路由仅审批决定两 POST。

        用户解除 Console 冻结后, 唯一写路径 = POST /api/approvals/{id}/
        approve|reject (走 org Approval 状态机, source=console 审计);
        其余一切路由只读 (GET/HEAD), 无 PUT/PATCH/DELETE。
        """
        app = _adapter.build_app(_StubService())
        for route in app.routes:
            if not hasattr(route, "methods"):
                continue
            for route_method in route.methods:
                if route_method in {"GET", "HEAD"}:
                    continue
                assert route_method == "POST", (
                    f"非 POST 写路由泄漏: {route_method} {getattr(route, 'path', '?')}"
                )
                path = getattr(route, "path", "")
                assert path.endswith("/approve") or path.endswith("/reject"), (
                    f"POST 路由超出审批决定范围: {path}"
                )

    def test_client_write_surface_limited_to_approval_decisions(self):
        """前端 api client 写面仅审批决定 (POST approve/reject; 无 put/patch/delete)。"""
        src = (Path(__file__).parents[2] / "factory-console" / "web" / "frontend"
               / "src" / "api" / "client.ts").read_text(encoding="utf-8")
        # 写 helper 存在但唯一 (sendJson → POST approve/reject)
        assert "sendJson" in src
        assert "approveApproval" in src
        assert "rejectApproval" in src
        # 无 put/patch/delete 写方法
        assert "function put" not in src
        assert "function patch" not in src
        assert "function del" not in src
        assert "method: 'PUT'" not in src
        assert "method: 'PATCH'" not in src
        assert "method: 'DELETE'" not in src


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
