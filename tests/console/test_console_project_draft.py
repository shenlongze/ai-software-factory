"""tests/console/test_console_project_draft.py — Draft Project + Discovery 持久化 (S10-009 Task 004)。

覆盖 (factory-console/api/projects.py + service.py + web/backend/fastapi_adapter.py
+ org/space.py ProjectSpaceStore 原语):
- POST /api/projects {idea} (无 name) → 创建 DRAFT:
  - 201 {project_id, name: "unnamed-project-{ts}", lifecycle: discovery, draft: true}
  - 目录骨架: idea/ discovery/ 存在 + project.json 信源可读 (lifecycle/draft 落库)
  - idea/conversation.json + idea.md 写入 (含原始想法)
  - discovery/conversation.json 初始化
- 旧兼容: POST {idea, name} → 正式项目 (旧形状 {project_id, name, idea, status},
  status=idea — 不破坏前端确认创建)
- POST /api/projects/{id}/discovery/answer {question, answer}:
  - 追加 discovery/conversation.json (可多次, 顺序保留)
  - 项目不存在 → 404; 空 answer/question → 400
- POST /api/projects/{id}/discovery/complete:
  - 生成 discovery/product-definition.md (基于 idea + 沟通记录)
  - lifecycle discovery → product_defined (org store + space 信源)
  - 未在 discovery 状态 → 409; 项目不存在 → 404
- 事件: org.project.created 落库 (draft 创建); 新事件 (org.project.discovery.*)
  失败安全 (不拖垮端点)
- 路由函数 (无 HTTP): 空 idea → ValueError; store 缺失 → None

basename 全仓库唯一 (test_console_* 前缀); fastapi/httpx 未安装 → HTTP 类
跳过 (与 test_console_project_create.py 同模式)。测试真实装配 (build_console_service
→ org ProjectStore + ProjectSpaceStore 落盘 factory_root)。
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

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

from console_helpers import event_types_of  # noqa: E402

#: factory-console 包名含连字符 → importlib 加载 (同 tests/console 其余测试模式)
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")
_api = importlib.import_module("factory-console.api")
_projects_api = importlib.import_module("factory-console.api.projects")


def _space_dir(factory_root: Path, project_id: str) -> Path:
    """项目空间目录 (workspace/projects/{slug} — 经 index 自愈查询)。"""
    from org.space import ProjectSpaceStore

    space = ProjectSpaceStore(factory_root)
    slug = space.get_slug(project_id)
    assert slug is not None, f"no space slug for project {project_id}"
    return space.space_dir(slug)


def _conversation(factory_root: Path, project_id: str, subdir: str) -> dict:
    """读取 {subdir}/conversation.json (断言持久化内容)。"""
    path = _space_dir(factory_root, project_id) / subdir / "conversation.json"
    assert path.is_file(), f"missing {path}"
    return json.loads(path.read_text(encoding="utf-8"))


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


class _NoStoreService:
    """缺 org/space store 的桩 (503 语义: 三个新 service 方法 → None)。"""

    def create_draft_project(self, idea, **kwargs):
        return None

    def save_discovery_answer(self, project_id, question, answer):
        return None

    def complete_discovery(self, project_id):
        return None


@requires_fastapi
class TestDraftCreateHttp:
    @pytest.fixture
    def client(self, factory_root: Path, event_logger):
        """真实装配 (build_console_service → org ProjectStore + ProjectSpaceStore)。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            yield c

    def test_create_draft_201_shape(self, client):
        """POST {idea} 无 name → 201 {project_id, name: unnamed-project-*, lifecycle,
        draft}。"""
        resp = client.post("/api/projects", json={"idea": "开发一个记账 App"})
        assert resp.status_code == 201
        body = resp.json()
        assert set(body.keys()) == {
            "project_id", "name", "idea", "status", "lifecycle", "draft",
        }
        assert body["project_id"].startswith("P")
        assert body["name"].startswith("unnamed-project-")
        assert body["idea"] == "开发一个记账 App"
        assert body["lifecycle"] == "discovery"
        assert body["status"] == "discovery"
        assert body["draft"] is True

    def test_draft_space_dirs_and_project_json(self, client, factory_root):
        """目录骨架: idea/ discovery/ 存在; project.json 信源可读 (lifecycle/draft)。"""
        created = client.post("/api/projects", json={"idea": "开发一个记账 App"}).json()
        space_dir = _space_dir(factory_root, created["project_id"])
        assert (space_dir / "idea").is_dir()
        assert (space_dir / "discovery").is_dir()
        project_json = space_dir / "project.json"
        assert project_json.is_file()
        data = json.loads(project_json.read_text(encoding="utf-8"))
        assert data["id"] == created["project_id"]
        assert data["lifecycle"] == "discovery"
        assert data["draft"] is True

    def test_draft_idea_files_written(self, client, factory_root):
        """idea/conversation.json + idea.md 写入 (含原始想法)。"""
        created = client.post("/api/projects", json={"idea": "开发一个记账 App"}).json()
        space_dir = _space_dir(factory_root, created["project_id"])
        idea_json = _conversation(factory_root, created["project_id"], "idea")
        assert idea_json["idea"] == "开发一个记账 App"
        assert idea_json["project_id"] == created["project_id"]
        idea_md = (space_dir / "idea" / "idea.md").read_text(encoding="utf-8")
        assert "开发一个记账 App" in idea_md

    def test_draft_discovery_conversation_initialized(self, client, factory_root):
        """discovery/conversation.json 初始化 (空会话, 元数据齐全)。"""
        created = client.post("/api/projects", json={"idea": "开发一个记账 App"}).json()
        disc = _conversation(factory_root, created["project_id"], "discovery")
        assert disc["project_id"] == created["project_id"]
        assert disc["conversation"] == []
        assert disc["status"] == "active"

    def test_draft_listed_in_projects(self, client):
        """持久化闭环: 创建后 GET /api/projects 出现该项目。"""
        created = client.post("/api/projects", json={"idea": "开发一个记账 App"}).json()
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()["items"]]
        assert created["project_id"] in ids

    def test_draft_emits_org_project_created(self, client, event_store):
        """事件: org.project.created 落库 (复用既有事件, 不扩 Core 枚举)。"""
        client.post("/api/projects", json={"idea": "开发一个记账 App"})
        assert "org.project.created" in event_types_of(event_store)


@requires_fastapi
class TestLegacyCreateCompat:
    """旧兼容: POST {idea, name} → 正式项目 (前端确认创建, 零破坏)。"""

    @pytest.fixture
    def client(self, factory_root: Path, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            yield c

    def test_legacy_name_still_regular_project(self, client):
        """{idea, name} → 201 旧形状 {project_id, name, idea, status}, status=idea。"""
        resp = client.post(
            "/api/projects", json={"idea": "开发一个记账 App", "name": "记账本"}
        )
        assert resp.status_code == 201
        body = resp.json()
        assert set(body.keys()) == {"project_id", "name", "idea", "status"}
        assert body["name"] == "记账本"
        assert body["idea"] == "开发一个记账 App"
        assert body["status"] == "idea"

    def test_legacy_name_not_draft(self, client):
        """{idea, name} → 无 draft 语义 (draft=false 且无 unnamed 名)。"""
        resp = client.post(
            "/api/projects", json={"idea": "开发一个记账 App", "name": "记账本"}
        )
        body = resp.json()
        assert not body["name"].startswith("unnamed-project-")


@requires_fastapi
class TestDiscoveryAnswerHttp:
    @pytest.fixture
    def client(self, factory_root: Path, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            yield c

    def _draft_id(self, client) -> str:
        return client.post("/api/projects", json={"idea": "开发一个记账 App"}).json()[
            "project_id"
        ]

    def test_answer_appends_to_conversation(self, client, factory_root):
        """answer → 200 {project_id, question, answer, count}; conversation.json 追加。"""
        pid = self._draft_id(client)
        resp = client.post(
            f"/api/projects/{pid}/discovery/answer",
            json={"question": "目标平台?", "answer": "手机 App"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == pid
        assert body["question"] == "目标平台?"
        assert body["answer"] == "手机 App"
        assert body["count"] == 1
        disc = _conversation(factory_root, pid, "discovery")
        assert disc["conversation"][0]["question"] == "目标平台?"
        assert disc["conversation"][0]["answer"] == "手机 App"

    def test_answer_multiple_appends_keep_order(self, client, factory_root):
        """可多次 answer → 追加 (顺序保留)。"""
        pid = self._draft_id(client)
        client.post(
            f"/api/projects/{pid}/discovery/answer",
            json={"question": "Q1", "answer": "A1"},
        )
        resp = client.post(
            f"/api/projects/{pid}/discovery/answer",
            json={"question": "Q2", "answer": "A2"},
        )
        assert resp.json()["count"] == 2
        disc = _conversation(factory_root, pid, "discovery")
        assert [e["question"] for e in disc["conversation"]] == ["Q1", "Q2"]
        assert [e["answer"] for e in disc["conversation"]] == ["A1", "A2"]

    def test_answer_missing_project_404(self, client):
        resp = client.post(
            "/api/projects/P-nope/discovery/answer",
            json={"question": "Q", "answer": "A"},
        )
        assert resp.status_code == 404

    def test_answer_empty_400(self, client):
        """空 answer → 400 (空答案不记录)。"""
        pid = self._draft_id(client)
        resp = client.post(
            f"/api/projects/{pid}/discovery/answer",
            json={"question": "Q", "answer": "   "},
        )
        assert resp.status_code == 400
        assert "answer" in resp.json()["error"]["message"]

    def test_answer_empty_question_400(self, client):
        """空 question → 400 (空问题不记录)。"""
        pid = self._draft_id(client)
        resp = client.post(
            f"/api/projects/{pid}/discovery/answer",
            json={"question": "  ", "answer": "A"},
        )
        assert resp.status_code == 400


@requires_fastapi
class TestDiscoveryCompleteHttp:
    @pytest.fixture
    def client(self, factory_root: Path, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            yield c

    def _draft_with_answer(self, client) -> str:
        pid = client.post("/api/projects", json={"idea": "开发一个记账 App"}).json()[
            "project_id"
        ]
        client.post(
            f"/api/projects/{pid}/discovery/answer",
            json={"question": "目标平台?", "answer": "手机 App"},
        )
        return pid

    def test_complete_generates_product_definition(self, client, factory_root):
        """complete → 200 {lifecycle: product_defined}; product-definition.md 生成
        (含 idea + 沟通记录)。"""
        pid = self._draft_with_answer(client)
        resp = client.post(f"/api/projects/{pid}/discovery/complete")
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == pid
        assert body["lifecycle"] == "product_defined"
        pd_path = _space_dir(factory_root, pid) / "discovery" / "product-definition.md"
        assert pd_path.is_file()
        content = pd_path.read_text(encoding="utf-8")
        assert "开发一个记账 App" in content  # idea
        assert "手机 App" in content  # 澄清记录

    def test_complete_updates_org_lifecycle(self, client, factory_root):
        """lifecycle discovery → product_defined (org store + space 信源)。"""
        from org.projects import ProjectStore

        pid = self._draft_with_answer(client)
        client.post(f"/api/projects/{pid}/discovery/complete")
        store = ProjectStore(factory_root / "org")
        project = store.get_project(pid)
        assert project is not None
        assert project.lifecycle.value == "product_defined"
        assert project.draft is True  # 仍未 rename (confirm 前保持草稿标记)
        data = json.loads(
            (_space_dir(factory_root, pid) / "project.json").read_text(encoding="utf-8")
        )
        assert data["lifecycle"] == "product_defined"

    def test_complete_not_in_discovery_409(self, client):
        """未在 discovery 状态 (正式项目) → 409 (状态冲突, 诚实拒绝)。"""
        pid = client.post(
            "/api/projects", json={"idea": "开发一个记账 App", "name": "记账本"}
        ).json()["project_id"]
        resp = client.post(f"/api/projects/{pid}/discovery/complete")
        assert resp.status_code == 409

    def test_complete_missing_project_404(self, client):
        resp = client.post("/api/projects/P-nope/discovery/complete")
        assert resp.status_code == 404

    def test_complete_marks_conversation_completed(self, client, factory_root):
        """complete 后 discovery/conversation.json status → completed。"""
        pid = self._draft_with_answer(client)
        client.post(f"/api/projects/{pid}/discovery/complete")
        disc = _conversation(factory_root, pid, "discovery")
        assert disc["status"] == "completed"


# ------------------------------------------------------------------ service 持久化 (无 HTTP)


class TestDraftService:
    def test_create_draft_project_persists_space(self, factory_root: Path, event_logger):
        """service.create_draft_project: org Project (draft/discovery) + 空间文件。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        project = service.create_draft_project("开发一个记账 App")
        assert project is not None
        assert project.draft is True
        assert project.lifecycle.value == "discovery"
        assert project.name.startswith("unnamed-project-")
        assert project.goal == "开发一个记账 App"
        assert project.slug == ""  # draft 期无正式 slug (rename 时更新)
        space_dir = _space_dir(factory_root, project.id)
        assert (space_dir / "discovery" / "conversation.json").is_file()

    def test_create_draft_project_no_store_none(self):
        """缺 store → None (HTTP 层 503)。"""
        import importlib as _il

        _service_mod = _il.import_module("factory-console.service")
        service = _service_mod.ConsoleService()
        assert service.create_draft_project("开发一个记账 App") is None

    def test_save_discovery_answer_appends(self, factory_root: Path, event_logger):
        """service.save_discovery_answer: 追加 + 返回 count。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        project = service.create_draft_project("开发一个记账 App")
        assert project is not None
        result = service.save_discovery_answer(project.id, "目标平台?", "手机 App")
        assert result is not None
        assert result["count"] == 1
        result2 = service.save_discovery_answer(project.id, "Q2", "A2")
        assert result2["count"] == 2
        disc = _conversation(factory_root, project.id, "discovery")
        assert len(disc["conversation"]) == 2

    def test_save_discovery_answer_empty_raises(self, factory_root: Path, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        project = service.create_draft_project("开发一个记账 App")
        assert project is not None
        with pytest.raises(ValueError):
            service.save_discovery_answer(project.id, "Q", "  ")

    def test_complete_discovery_transitions(self, factory_root: Path, event_logger):
        """service.complete_discovery: lifecycle → product_defined + 产物落库。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        project = service.create_draft_project("开发一个记账 App")
        assert project is not None
        service.save_discovery_answer(project.id, "目标平台?", "手机 App")
        updated = service.complete_discovery(project.id)
        assert updated is not None
        assert updated.lifecycle.value == "product_defined"
        pd_path = _space_dir(factory_root, project.id) / "discovery" / "product-definition.md"
        assert pd_path.is_file()

    def test_complete_discovery_wrong_state_raises(self, factory_root: Path, event_logger):
        """非 discovery 状态 → ValueError (HTTP 层 409)。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        project = service.create_project("开发一个记账 App", name="记账本")
        assert project is not None
        with pytest.raises(ValueError):
            service.complete_discovery(project.id)


# ------------------------------------------------------------------ 路由函数 (无 HTTP 依赖)


class TestDraftRouteFunction:
    """api/projects 新路由函数 (无 HTTP 依赖) 语义。"""

    def test_create_draft_empty_idea_raises_value_error(self):
        with pytest.raises(ValueError):
            _api.create_draft_project(_NoStoreService(), "   ")

    def test_create_draft_no_store_returns_none(self):
        summary = _api.create_draft_project(_NoStoreService(), "开发一个记账 App")
        assert summary is None

    def test_answer_empty_raises_value_error(self):
        with pytest.raises(ValueError):
            _api.save_discovery_answer(_NoStoreService(), "P-1", "Q", "  ")

    def test_answer_no_store_returns_none(self):
        summary = _api.save_discovery_answer(_NoStoreService(), "P-1", "Q", "A")
        assert summary is None

    def test_complete_no_store_returns_none(self):
        summary = _api.complete_discovery(_NoStoreService(), "P-1")
        assert summary is None


class TestProjectStarred:
    """Founder 2026-08-26 #1: 收藏/关注 (PATCH /api/projects/{id} {starred})。"""

    @pytest.fixture
    def client(self, factory_root: Path, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            yield c

    def test_star_unstar_project(self, client):
        """PATCH starred=true → 列表 starred=true; PATCH false → 取消。"""
        created = client.post("/api/projects", json={"idea": "做一个番茄钟 App", "name": "番茄钟"})
        assert created.status_code == 201
        pid = created.json()["project_id"]
        # star
        r = client.patch(f"/api/projects/{pid}", json={"starred": True})
        assert r.status_code == 200
        # 列表含 starred=true
        listed = client.get("/api/projects").json()["items"]
        me = next(p for p in listed if p["id"] == pid)
        assert me["starred"] is True
        # 取消
        r2 = client.patch(f"/api/projects/{pid}", json={"starred": False})
        assert r2.status_code == 200
        listed2 = client.get("/api/projects").json()["items"]
        me2 = next(p for p in listed2 if p["id"] == pid)
        assert me2["starred"] is False

    def test_star_persists_in_org(self, client, factory_root):
        """starred 落库 org/projects.json (方案 A: 项目属性)。"""
        created = client.post("/api/projects", json={"idea": "做一个笔记 App", "name": "笔记"})
        pid = created.json()["project_id"]
        client.patch(f"/api/projects/{pid}", json={"starred": True})
        import json
        org = json.load(open(factory_root / "org" / "projects.json"))
        assert org["projects"][pid]["starred"] is True

    def test_star_requires_action(self, client):
        """无任何更新字段 → 400 (无事可做)。"""
        created = client.post("/api/projects", json={"idea": "做一个博客", "name": "博客"})
        pid = created.json()["project_id"]
        r = client.patch(f"/api/projects/{pid}", json={})
        assert r.status_code == 400


class TestProjectArchive:
    """Founder 2026-08-26: 归档 (软归档, 可恢复; 独立于生命周期)。"""

    @pytest.fixture
    def client(self, factory_root: Path, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            yield c

    def test_archive_unarchive(self, client):
        """PATCH archived=true → 列表 archived=true; false → 恢复。"""
        created = client.post("/api/projects", json={"idea": "做一个归档测试", "name": "归档测试"})
        pid = created.json()["project_id"]
        client.patch(f"/api/projects/{pid}", json={"archived": True})
        listed = client.get("/api/projects").json()["items"]
        me = next(p for p in listed if p["id"] == pid)
        assert me["archived"] is True
        # 恢复
        client.patch(f"/api/projects/{pid}", json={"archived": False})
        listed2 = client.get("/api/projects").json()["items"]
        me2 = next(p for p in listed2 if p["id"] == pid)
        assert me2["archived"] is False

    def test_archive_persists_in_org(self, client, factory_root):
        """archived 落库 org/projects.json (软归档可恢复)。"""
        created = client.post("/api/projects", json={"idea": "归档持久化", "name": "归档持久"})
        pid = created.json()["project_id"]
        client.patch(f"/api/projects/{pid}", json={"archived": True})
        import json
        org = json.load(open(factory_root / "org" / "projects.json"))
        assert org["projects"][pid]["archived"] is True
