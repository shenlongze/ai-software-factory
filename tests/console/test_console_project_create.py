"""tests/console/test_console_project_create.py — POST /api/projects 测试 (S10-006.5 P0 Fix)。

覆盖 (factory-console/api/projects.py + web/backend/fastapi_adapter.py):
- extract_project_name: 中文动词前缀去除 / 关键词映射 / slug 化 / 空 (规则式纯函数)
- POST /api/projects 成功 201: {project_id, name, idea, status} 形状
- 400: idea 空 / project_type 非法 / tech 非法 (宽容收窄)
- 503: org store 缺失 (失败安全 — 不拖垮 API)
- 持久化: 创建后 GET /api/projects 出现 (真实 ProjectStore + tmp 工厂根)
- 事件: org.project.created 落库 (复用既有事件, 不扩 Core 枚举)
- project_type/tech 透传落库 (org Project.project_type/framework)

basename 全仓库唯一 (test_console_* 前缀); fastapi/httpx 未安装 → HTTP 类
跳过 (与 test_console_web_adapter.py 同模式)。
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
_api = importlib.import_module("factory-console.api")
_projects_api = importlib.import_module("factory-console.api.projects")
_service = importlib.import_module("factory-console.service")


# ------------------------------------------------------------------ 项目名提取 (纯函数)


class TestExtractProjectName:
    """extract_project_name — 规则式项目名提取 (无 LLM, 覆盖常见 demo 场景)。"""

    def test_ledger_app(self):
        """开发一个记账 App → ledger-app (中文关键词映射 + 尾部噪声去除)。"""
        assert _projects_api.extract_project_name("开发一个记账 App") == "ledger-app"

    def test_todo_list(self):
        """我想开发一个待办清单 → todo (长动词前缀 + 关键词映射)。"""
        assert _projects_api.extract_project_name("我想开发一个待办清单") == "todo"

    def test_blog_site(self):
        """做一个博客网站 → blog (尾部噪声 网站 去除)。"""
        assert _projects_api.extract_project_name("做一个博客网站") == "blog"

    def test_weather_app(self):
        """帮我开发一个天气应用 → weather。"""
        assert _projects_api.extract_project_name("帮我开发一个天气应用") == "weather"

    def test_english_idea(self):
        """英文想法 → slug (hello world → hello-world)。"""
        assert _projects_api.extract_project_name("hello world") == "hello-world"

    def test_empty_and_none(self):
        """空/None → \"\" (调用方 fallback, 不崩溃)。"""
        assert _projects_api.extract_project_name("") == ""
        assert _projects_api.extract_project_name("   ") == ""
        assert _projects_api.extract_project_name(None) == ""

    def test_noise_only(self):
        """纯噪声 (开发一个app) → \"app\" 残留被截断 (长度保护) 或空 — 不崩溃。"""
        result = _projects_api.extract_project_name("开发一个App")
        # "App" 为尾部噪声且长度 >= 主体 → 保留原文 slug (不误删整个词)
        assert isinstance(result, str)


# ------------------------------------------------------------------ HTTP (fastapi + httpx)


try:
    from fastapi.testclient import TestClient  # noqa: E402

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装 (console 侧 venv 需安装)"
)


class _NoProjectStoreService:
    """缺 org project store 的桩 (503 语义: create_project/create_draft_project → None)。"""

    def create_project(self, idea, **kwargs):
        return None

    def create_draft_project(self, idea, **kwargs):
        return None

    def list_projects(self):
        return []


@requires_fastapi
class TestCreateProjectHttp:
    @pytest.fixture
    def client(self, factory_root: Path, event_logger):
        """真实装配 (build_console_service → org ProjectStore 落盘 factory_root/org)。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            yield c

    def test_create_201_shape(self, client):
        """POST /api/projects {idea} (无 name) → S10-009-004: 创建 DRAFT —
        201 {project_id, name: unnamed-project-*, idea, status, lifecycle, draft}。"""
        resp = client.post("/api/projects", json={"idea": "开发一个记账 App"})
        assert resp.status_code == 201
        body = resp.json()
        assert set(body.keys()) == {
            "project_id", "name", "idea", "status", "lifecycle", "draft",
        }
        assert body["name"].startswith("unnamed-project-")
        assert body["idea"] == "开发一个记账 App"
        assert body["status"] == "discovery"
        assert body["lifecycle"] == "discovery"
        assert body["draft"] is True
        assert body["project_id"].startswith("P")

    def test_create_with_type_and_tech(self, client):
        """project_type/tech 透传 (web/flutter) → 201 且不报错 (draft 创建路径)。"""
        resp = client.post(
            "/api/projects",
            json={"idea": "我想开发一个待办清单", "project_type": "web", "tech": "flutter"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"].startswith("unnamed-project-")
        assert body["lifecycle"] == "discovery"

    def test_empty_idea_400(self, client):
        """idea 空 → 400 (空想法不创建, 语义清晰)。"""
        resp = client.post("/api/projects", json={"idea": "   "})
        assert resp.status_code == 400
        assert "idea is required" in resp.json()["detail"]

    def test_missing_idea_400(self, client):
        """无 idea 键 (pydantic 422 由路由函数缺省校验) — 兼容: 显式空字符串同 400。"""
        resp = client.post("/api/projects", json={})
        assert resp.status_code in (400, 422)

    def test_invalid_project_type_400(self, client):
        """project_type 非法 (非 web|mobile|desktop) → 400 宽容收窄。"""
        resp = client.post(
            "/api/projects", json={"idea": "做一个博客", "project_type": "quantum"}
        )
        assert resp.status_code == 400
        assert "project_type" in resp.json()["detail"]

    def test_invalid_tech_400(self, client):
        """tech 非法 (非 auto|flutter|react|vue) → 400 宽容收窄。"""
        resp = client.post(
            "/api/projects", json={"idea": "做一个博客", "tech": "assembly"}
        )
        assert resp.status_code == 400
        assert "tech" in resp.json()["detail"]

    def test_no_store_503(self):
        """org store 缺失 → 503 (失败安全: 创建不可用, 不拖垮 API)。"""
        app = _adapter.build_app(_NoProjectStoreService())
        with TestClient(app) as c:
            resp = c.post("/api/projects", json={"idea": "开发一个记账 App"})
        assert resp.status_code == 503

    def test_create_then_listed(self, client):
        """持久化闭环: 创建后 GET /api/projects 出现该项目 (真实 ProjectStore)。"""
        created = client.post("/api/projects", json={"idea": "开发一个记账 App"}).json()
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()]
        assert created["project_id"] in ids

    def test_create_emits_org_project_created(self, client, event_store):
        """事件: org.project.created 落库 (复用既有事件, 不扩 Core 枚举)。"""
        client.post("/api/projects", json={"idea": "开发一个记账 App"})
        assert "org.project.created" in event_types_of(event_store)


@requires_fastapi
class TestCreateProjectPersistence:
    def test_type_and_tech_persisted(self, factory_root: Path, event_logger):
        """project_type/tech 落库: org Project.project_type/framework 可读回。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        summary = service.create_project(
            "开发一个记账 App", name="ledger-app", project_type="mobile", tech="flutter"
        )
        assert summary is not None
        store = service._project_store
        # service.create_project 返回 org Project (id 属性, 非 API 投影 project_id)
        project = store.get_project(summary.id)
        assert project is not None
        assert project.project_type == "mobile"
        assert project.framework == "flutter"
        assert project.goal == "开发一个记账 App"

    def test_store_missing_returns_none(self):
        """缺 store → service.create_project None (HTTP 层 503)。"""
        service = _service.ConsoleService()
        assert service.create_project("开发一个记账 App") is None


class TestCreateProjectRouteFunction:
    """api/projects.create_project 路由函数 (无 HTTP 依赖) 语义。"""

    def test_empty_idea_raises_value_error(self):
        """idea 空 → ValueError (HTTP 层映射 400)。"""
        with pytest.raises(ValueError):
            _api.create_project(_NoProjectStoreService(), "   ")

    def test_no_store_returns_none(self):
        """store 缺失 → None (HTTP 层映射 503)。"""
        summary = _api.create_project(_NoProjectStoreService(), "开发一个记账 App")
        assert summary is None
