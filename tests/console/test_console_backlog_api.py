"""tests/console/test_console_backlog_api.py — S10-010 Task 003: Backlog API (TDD)。

覆盖 (factory-console/api/backlog.py + service.py backlog_* 方法 +
web/backend/fastapi_adapter.py 端点 + org/management.py 实体/状态机复用):
- POST /api/projects/{id}/backlog/epic {name, description} → 创建 Epic
  (id/created_at; 空 name → 400; 项目不存在 → 404)
- POST /api/projects/{id}/backlog/feature {name, description, epic_id?} →
  Feature (可选绑定 Epic: epic.children 追加; epic_id 不存在 → 404)
- POST /api/projects/{id}/backlog/story {name, description, feature_id?} →
  Story (绑定 Feature: feature.children 追加; feature_id 不存在 → 404)
- POST /api/projects/{id}/backlog/task {title, description?, priority?,
  dependency?, story_id?} → Task (绑定 Story: story.children 追加;
  priority 非法 → 400; dependency 环/自引用 → 400)
- GET /api/projects/{id}/backlog → 全量分组 {epics, features, stories, tasks}
- GET /api/projects/{id}/backlog/task/{task_id} → 详情 (不存在 → 404)
- PATCH /api/projects/{id}/backlog/task/{task_id} {title?/description?/
  priority?/status?/assignee?/dependency?}:
  - 字段更新落库; priority 非法 → 400; dependency 环/自引用 → 400
  - status 转换走状态机 (非法转换 → 409; 依赖未满足 → 400;
    依赖满足后同转换 → 200)
- DELETE /api/projects/{id}/backlog/task/{task_id} → 200 (sprint 引用可留;
  不存在 → 404; 删除后 GET 详情 → 404)
- 持久化: 目录信源 management/backlog/*.json (重建 service → 数据仍在)

basename 全仓库唯一 (test_console_* 前缀); fastapi/httpx 未安装 → HTTP 类
跳过; 测试真实装配 (build_console_service → org ProjectStore +
ProjectSpaceStore + ManagementStore 落盘 factory_root)。
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_FACTORY_ORG = _ROOT / "factory-org"
if str(_FACTORY_ORG) not in sys.path:
    sys.path.insert(0, str(_FACTORY_ORG))

#: factory-console 包名含连字符 → importlib 加载 (同 tests/console 其余测试模式)
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")
_api = importlib.import_module("factory-console.api")
_service = importlib.import_module("factory-console.service")

try:  # fastapi/httpx 未安装 (仅 console 侧 venv) → HTTP 类跳过, 路由函数测试仍运行
    from fastapi.testclient import TestClient  # noqa: E402

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装 (console 侧 venv 需安装)"
)


def _create_project(client: Any) -> str:
    """真实装配创建正式项目 (有 name → 旧兼容路径), 返回 project_id。"""
    resp = client.post(
        "/api/projects", json={"idea": "开发一个记账 App", "name": "Backlog Demo"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["project_id"]


def _backlog_dir(factory_root: Path, project_id: str) -> Path:
    """项目 management/backlog 目录 (目录信源断言)。"""
    from org.space import ProjectSpaceStore

    space = ProjectSpaceStore(factory_root)
    slug = space.get_slug(project_id)
    assert slug is not None, f"no space slug for project {project_id}"
    return space.space_dir(slug) / "management" / "backlog"


def _create_epic(client: Any, project_id: str, name: str = "Epic One") -> dict:
    resp = client.post(
        f"/api/projects/{project_id}/backlog/epic",
        json={"name": name, "description": "首个 Epic"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_feature(
    client: Any, project_id: str, name: str = "Feature One", epic_id: str | None = None
) -> dict:
    body: dict = {"name": name, "description": "首个 Feature"}
    if epic_id is not None:
        body["epic_id"] = epic_id
    resp = client.post(f"/api/projects/{project_id}/backlog/feature", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_story(
    client: Any, project_id: str, name: str = "Story One", feature_id: str | None = None
) -> dict:
    body: dict = {"name": name, "description": "首个 Story"}
    if feature_id is not None:
        body["feature_id"] = feature_id
    resp = client.post(f"/api/projects/{project_id}/backlog/story", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_task(
    client: Any,
    project_id: str,
    title: str = "Task One",
    *,
    priority: str | None = None,
    dependency: list[str] | None = None,
    story_id: str | None = None,
) -> dict:
    body: dict = {"title": title, "description": "首个 Task"}
    if priority is not None:
        body["priority"] = priority
    if dependency is not None:
        body["dependency"] = dependency
    if story_id is not None:
        body["story_id"] = story_id
    resp = client.post(f"/api/projects/{project_id}/backlog/task", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ------------------------------------------------------------------ HTTP fixtures


@pytest.fixture
def project(factory_root: Path, event_logger):
    """真实装配: build_console_service + build_app → (TestClient, project_id)。

    每测试独立 factory_root (tmp_path/factory) — 目录信源隔离, 零串扰。
    """
    service = _adapter.build_console_service(factory_root, event_logger=event_logger)
    app = _adapter.build_app(service, event_logger=event_logger)
    with TestClient(app) as c:
        project_id = _create_project(c)
        yield c, project_id


# ------------------------------------------------------------------ Epic


@requires_fastapi
class TestEpicCreateHttp:
    def test_create_epic_201_shape(self, project):
        client, project_id = project
        resp = client.post(
            f"/api/projects/{project_id}/backlog/epic",
            json={"name": "支付系统", "description": "月级能力"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"].startswith("EPIC-")
        assert body["name"] == "支付系统"
        assert body["description"] == "月级能力"
        assert body["created_at"]
        assert body["children"] == []

    def test_create_epic_empty_name_400(self, project):
        client, project_id = project
        resp = client.post(
            f"/api/projects/{project_id}/backlog/epic",
            json={"name": "   ", "description": ""},
        )
        assert resp.status_code == 400
        assert "name" in resp.json()["error"]["message"]

    def test_create_epic_project_missing_404(self, factory_root, event_logger):
        """项目不存在 → 404 (项目 id 不存在)。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            resp = c.post(
                "/api/projects/P-nope/backlog/epic",
                json={"name": "Epic", "description": ""},
            )
        assert resp.status_code == 404


# ------------------------------------------------------------------ Feature


@requires_fastapi
class TestFeatureCreateHttp:
    def test_create_feature_201_shape(self, project):
        client, project_id = project
        body = _create_feature(client, project_id)
        assert body["id"].startswith("FEAT-")
        assert body["name"] == "Feature One"
        assert body["created_at"]

    def test_create_feature_binds_epic(self, project, factory_root):
        """epic_id 提供 → Feature 创建 + epic.children 追加 (层级绑定)。"""
        client, project_id = project
        epic = _create_epic(client, project_id)
        feature = _create_feature(client, project_id, epic_id=epic["id"])
        assert feature["epic_id"] == epic["id"]
        backlog_dir = _backlog_dir(factory_root, project_id)
        epic_data = json.loads(
            (backlog_dir / "epic.json").read_text(encoding="utf-8")
        )["epics"]
        assert feature["id"] in epic_data[epic["id"]]["children"]

    def test_create_feature_without_epic_ok(self, project):
        """可选绑定: 无 epic_id → 宽松创建 (不强制层级)。"""
        client, project_id = project
        body = _create_feature(client, project_id)
        assert body["id"].startswith("FEAT-")
        assert body.get("epic_id", "") == ""

    def test_create_feature_missing_epic_404(self, project):
        """绑定不存在的 Epic → 404 (子级绑定不存在)。"""
        client, project_id = project
        resp = client.post(
            f"/api/projects/{project_id}/backlog/feature",
            json={"name": "F", "description": "", "epic_id": "EPIC-nope"},
        )
        assert resp.status_code == 404
        assert "epic" in resp.json()["error"]["message"]

    def test_create_feature_empty_name_400(self, project):
        client, project_id = project
        resp = client.post(
            f"/api/projects/{project_id}/backlog/feature",
            json={"name": "", "description": ""},
        )
        assert resp.status_code == 400


# ------------------------------------------------------------------ Story


@requires_fastapi
class TestStoryCreateHttp:
    def test_create_story_201_shape(self, project):
        client, project_id = project
        body = _create_story(client, project_id)
        assert body["id"].startswith("STORY-")
        assert body["name"] == "Story One"

    def test_create_story_binds_feature(self, project, factory_root):
        """feature_id 提供 → Story 创建 + feature.children 追加。"""
        client, project_id = project
        feature = _create_feature(client, project_id)
        story = _create_story(client, project_id, feature_id=feature["id"])
        assert story["feature_id"] == feature["id"]
        backlog_dir = _backlog_dir(factory_root, project_id)
        feature_data = json.loads(
            (backlog_dir / "feature.json").read_text(encoding="utf-8")
        )["features"]
        assert story["id"] in feature_data[feature["id"]]["children"]

    def test_create_story_missing_feature_404(self, project):
        client, project_id = project
        resp = client.post(
            f"/api/projects/{project_id}/backlog/story",
            json={"name": "S", "description": "", "feature_id": "FEAT-nope"},
        )
        assert resp.status_code == 404
        assert "feature" in resp.json()["error"]["message"]


# ------------------------------------------------------------------ Task


@requires_fastapi
class TestTaskCreateHttp:
    def test_create_task_201_shape(self, project):
        client, project_id = project
        body = _create_task(client, project_id)
        assert body["id"].startswith("TASK-")
        assert body["title"] == "Task One"
        assert body["status"] == "todo"
        assert body["priority"] == "P2"  # 默认 P2 Normal
        assert body["dependency"] == []
        assert body["created_at"]

    def test_create_task_with_priority_and_dependency(self, project):
        client, project_id = project
        dep = _create_task(client, project_id, title="前置任务")
        body = _create_task(
            client, project_id, title="依赖任务", priority="P1", dependency=[dep["id"]]
        )
        assert body["priority"] == "P1"
        assert body["dependency"] == [dep["id"]]

    def test_create_task_binds_story(self, project, factory_root):
        """story_id 提供 → Task 创建 + story.children 追加 (Task→Story)。"""
        client, project_id = project
        story = _create_story(client, project_id)
        task = _create_task(client, project_id, story_id=story["id"])
        assert task["story_id"] == story["id"]
        backlog_dir = _backlog_dir(factory_root, project_id)
        story_data = json.loads(
            (backlog_dir / "story.json").read_text(encoding="utf-8")
        )["stories"]
        assert task["id"] in story_data[story["id"]]["children"]

    def test_create_task_missing_story_404(self, project):
        client, project_id = project
        resp = client.post(
            f"/api/projects/{project_id}/backlog/task",
            json={"title": "T", "description": "", "story_id": "STORY-nope"},
        )
        assert resp.status_code == 404
        assert "story" in resp.json()["error"]["message"]

    def test_create_task_empty_title_400(self, project):
        client, project_id = project
        resp = client.post(
            f"/api/projects/{project_id}/backlog/task",
            json={"title": "  ", "description": ""},
        )
        assert resp.status_code == 400

    def test_create_task_invalid_priority_400(self, project):
        client, project_id = project
        resp = client.post(
            f"/api/projects/{project_id}/backlog/task",
            json={"title": "T", "description": "", "priority": "P9"},
        )
        assert resp.status_code == 400
        assert "priority" in resp.json()["error"]["message"]

    def test_create_task_dependency_valid_reference_ok(self, project):
        """dependency 引用已存在任务 → 宽松接受 (自引用/环由 PATCH 场景覆盖 —
        POST 时新 task id 未生成, 自引用不可构造; 跨任务环只能经更新构造)。"""
        client, project_id = project
        dep = _create_task(client, project_id, title="前置")
        resp = client.post(
            f"/api/projects/{project_id}/backlog/task",
            json={"title": "T2", "description": "", "dependency": [dep["id"]]},
        )
        assert resp.status_code == 201
        assert resp.json()["dependency"] == [dep["id"]]


# ------------------------------------------------------------------ Backlog 全量


@requires_fastapi
class TestBacklogListHttp:
    def test_get_backlog_empty(self, project):
        client, project_id = project
        resp = client.get(f"/api/projects/{project_id}/backlog")
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == project_id
        assert body["epics"] == []
        assert body["features"] == []
        assert body["stories"] == []
        assert body["tasks"] == []

    def test_get_backlog_groups_all(self, project):
        client, project_id = project
        epic = _create_epic(client, project_id)
        feature = _create_feature(client, project_id, epic_id=epic["id"])
        story = _create_story(client, project_id, feature_id=feature["id"])
        _create_task(client, project_id, story_id=story["id"])
        resp = client.get(f"/api/projects/{project_id}/backlog")
        assert resp.status_code == 200
        body = resp.json()
        assert [e["id"] for e in body["epics"]] == [epic["id"]]
        assert [f["id"] for f in body["features"]] == [feature["id"]]
        assert [s["id"] for s in body["stories"]] == [story["id"]]
        assert len(body["tasks"]) == 1
        assert body["tasks"][0]["status"] == "todo"

    def test_get_backlog_project_missing_404(self, factory_root, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            resp = c.get("/api/projects/P-nope/backlog")
        assert resp.status_code == 404


# ------------------------------------------------------------------ Task 详情


@requires_fastapi
class TestTaskDetailHttp:
    def test_get_task_detail_200(self, project):
        client, project_id = project
        task = _create_task(client, project_id, title="详情任务", priority="P0")
        resp = client.get(f"/api/projects/{project_id}/backlog/task/{task['id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == task["id"]
        assert body["title"] == "详情任务"
        assert body["priority"] == "P0"
        assert body["status"] == "todo"
        assert body["assignee"] == ""
        assert body["created_at"] and body["updated_at"]

    def test_get_task_missing_404(self, project):
        client, project_id = project
        resp = client.get(f"/api/projects/{project_id}/backlog/task/TASK-nope")
        assert resp.status_code == 404


# ------------------------------------------------------------------ Task PATCH


@requires_fastapi
class TestTaskPatchHttp:
    def test_patch_task_fields_200(self, project):
        client, project_id = project
        task = _create_task(client, project_id)
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/{task['id']}",
            json={"title": "新标题", "description": "新描述", "assignee": "dev-1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "新标题"
        assert body["description"] == "新描述"
        assert body["assignee"] == "dev-1"

    def test_patch_task_priority_200(self, project):
        client, project_id = project
        task = _create_task(client, project_id)
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/{task['id']}",
            json={"priority": "P1"},
        )
        assert resp.status_code == 200
        assert resp.json()["priority"] == "P1"

    def test_patch_task_invalid_priority_400(self, project):
        client, project_id = project
        task = _create_task(client, project_id)
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/{task['id']}",
            json={"priority": "P9"},
        )
        assert resp.status_code == 400
        assert "priority" in resp.json()["error"]["message"]

    def test_patch_task_empty_title_400(self, project):
        client, project_id = project
        task = _create_task(client, project_id)
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/{task['id']}",
            json={"title": "   "},
        )
        assert resp.status_code == 400

    def test_patch_task_status_legal_transition_200(self, project):
        """状态机合法转换: todo → ready → in_progress。"""
        client, project_id = project
        task = _create_task(client, project_id)
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/{task['id']}",
            json={"status": "ready"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/{task['id']}",
            json={"status": "in_progress"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

    def test_patch_task_status_illegal_transition_409(self, project):
        """非法转换 (跳级: todo → done) → 409 (状态机拒绝, 诚实冲突)。"""
        client, project_id = project
        task = _create_task(client, project_id)
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/{task['id']}",
            json={"status": "done"},
        )
        assert resp.status_code == 409
        assert "transition" in resp.json()["error"]["message"]

    def test_patch_task_status_dependency_gate_400(self, project):
        """依赖未满足: B 依赖 A (A 非 DONE) → B 转 ready → 400。"""
        client, project_id = project
        a = _create_task(client, project_id, title="A")
        b = _create_task(client, project_id, title="B", dependency=[a["id"]])
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/{b['id']}",
            json={"status": "ready"},
        )
        assert resp.status_code == 400
        assert "dependenc" in resp.json()["error"]["message"]

    def test_patch_task_status_dependency_satisfied_200(self, project):
        """依赖满足: A 走完 todo→ready→in_progress→review→done, B → ready → 200。"""
        client, project_id = project
        a = _create_task(client, project_id, title="A")
        b = _create_task(client, project_id, title="B", dependency=[a["id"]])
        for status in ("ready", "in_progress", "review", "done"):
            resp = client.patch(
                f"/api/projects/{project_id}/backlog/task/{a['id']}",
                json={"status": status},
            )
            assert resp.status_code == 200, resp.text
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/{b['id']}",
            json={"status": "ready"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    def test_patch_task_dependency_self_400(self, project):
        """dependency 自引用 → 400。"""
        client, project_id = project
        task = _create_task(client, project_id)
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/{task['id']}",
            json={"dependency": [task["id"]]},
        )
        assert resp.status_code == 400
        assert "self" in resp.json()["error"]["message"]

    def test_patch_task_dependency_cycle_400(self, project):
        """dependency 环: T1 依赖 T2 后, T2 依赖 T1 → 400 (DFS 环检测)。"""
        client, project_id = project
        t1 = _create_task(client, project_id, title="T1")
        t2 = _create_task(client, project_id, title="T2")
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/{t1['id']}",
            json={"dependency": [t2["id"]]},
        )
        assert resp.status_code == 200
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/{t2['id']}",
            json={"dependency": [t1["id"]]},
        )
        assert resp.status_code == 400
        assert "cycle" in resp.json()["error"]["message"]

    def test_patch_task_missing_404(self, project):
        client, project_id = project
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/TASK-nope",
            json={"title": "x"},
        )
        assert resp.status_code == 404


# ------------------------------------------------------------------ Task DELETE


@requires_fastapi
class TestTaskDeleteHttp:
    def test_delete_task_200(self, project):
        client, project_id = project
        task = _create_task(client, project_id)
        resp = client.delete(f"/api/projects/{project_id}/backlog/task/{task['id']}")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": True, "task_id": task["id"]}
        # 删除后详情 → 404
        resp = client.get(f"/api/projects/{project_id}/backlog/task/{task['id']}")
        assert resp.status_code == 404

    def test_delete_task_missing_404(self, project):
        client, project_id = project
        resp = client.delete(f"/api/projects/{project_id}/backlog/task/TASK-nope")
        assert resp.status_code == 404

    def test_delete_task_keeps_story_children(self, project, factory_root):
        """删除 Task 不破坏 Story 绑定 (story.children 引用保留 — 引用非包含)。"""
        client, project_id = project
        story = _create_story(client, project_id)
        task = _create_task(client, project_id, story_id=story["id"])
        resp = client.delete(f"/api/projects/{project_id}/backlog/task/{task['id']}")
        assert resp.status_code == 200
        backlog_dir = _backlog_dir(factory_root, project_id)
        story_data = json.loads(
            (backlog_dir / "story.json").read_text(encoding="utf-8")
        )["stories"]
        assert task["id"] in story_data[story["id"]]["children"]


# ------------------------------------------------------------------ 持久化 (目录信源)


@requires_fastapi
class TestBacklogPersistence:
    def test_management_backlog_files_written(self, project, factory_root):
        """目录信源: management/backlog/{epic,feature,story,task}.json 落盘。"""
        client, project_id = project
        _create_epic(client, project_id)
        _create_feature(client, project_id)
        _create_story(client, project_id)
        _create_task(client, project_id)
        backlog_dir = _backlog_dir(factory_root, project_id)
        for filename in ("epic.json", "feature.json", "story.json", "task.json"):
            path = backlog_dir / filename
            assert path.is_file(), f"missing {path}"
            data = json.loads(path.read_text(encoding="utf-8"))
            assert len(data[list(data.keys())[0]]) == 1  # {section: {id: dict}}

    def test_persistence_survives_reload(self, project, factory_root, event_logger):
        """重建 service (同 factory_root) → 数据仍在 (目录信源, 非内存)。"""
        client, project_id = project
        epic = _create_epic(client, project_id)
        task = _create_task(client, project_id)
        # 重建 service + app (新实例)
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c2:
            resp = c2.get(f"/api/projects/{project_id}/backlog")
            assert resp.status_code == 200
            body = resp.json()
            assert [e["id"] for e in body["epics"]] == [epic["id"]]
            assert [t["id"] for t in body["tasks"]] == [task["id"]]


# ------------------------------------------------------------------ 路由函数 (无 HTTP)


class TestBacklogRoutes:
    """路由函数层错误语义 (不经 HTTP): ValueError → 400 面 / None → 404 面。"""

    def test_route_create_epic_empty_name_valueerror(self, factory_root, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        # 先建项目 (直接调 service, 不经 HTTP)
        summary = service.create_project("测试想法", name="Route Demo")
        assert summary is not None
        with pytest.raises(ValueError):
            _api.create_epic(service, summary.id, name="   ", description="")

    def test_route_create_task_invalid_priority_valueerror(
        self, factory_root, event_logger
    ):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        summary = service.create_project("测试想法", name="Route Demo 2")
        with pytest.raises(ValueError):
            _api.create_task(
                service, summary.id, title="T", description="", priority="P9"
            )

    def test_route_project_missing_returns_none(self, factory_root, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        assert _api.create_epic(service, "P-nope", name="E", description="") is None
        assert _api.list_backlog(service, "P-nope") is None
        assert _api.get_task(service, "P-nope", "TASK-x") is None
        assert _api.update_task(service, "P-nope", "TASK-x", title="t") is None
        assert _api.delete_task(service, "P-nope", "TASK-x") is None
