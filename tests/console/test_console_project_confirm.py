"""tests/console/test_console_project_confirm.py — Confirm + Rename 事务 (S10-009 Task 005)。

覆盖 (factory-console/api/projects.py confirm_project_route + service.py confirm_project
+ web/backend/fastapi_adapter.py POST /api/projects/{id}/confirm + org/space.py
rename_space 原语):
- POST /api/projects/{id}/confirm {name} → rename 事务:
  - 成功: 200 {project_id, name, slug, lifecycle: confirmed}
  - 目录 rename: unnamed-project-xxx → {slug}/ (原子 os.replace)
  - 文件不丢失: idea/conversation.json + idea.md + discovery/conversation.json
    (含问答记录) + product-definition.md 在 rename 后内容一致
  - project.json 更新: name/slug/lifecycle=confirmed/draft=false
  - index 更新: workspace/projects.json 指向新 slug
  - 引用更新: org/projects.json 镜像 (id 不变, slug/name 更新)
- 错误/回滚:
  - slug 冲突 (已存在同名目录) → 409, 事务未开始 (目录/索引/引用不变)
  - 非法 name (空/无法 slug 化) → 400
  - 项目不存在 → 404
  - rename 中途失败 (os.replace IO 错误) → 503 + 全量回滚到快照
  - rename 后 org 镜像写失败 → 503 + 目录回滚 + 索引/引用还原
- 状态约束: 非 discovery/product_defined 状态 confirm → 409 (未到确认点)
- 幂等: 已 confirmed 同 name 再次 confirm → 200 (原样返回); 不同 name → 409
- 兼容: 旧项目 (无目录) confirm → 先 ensure_space 再 rename
- 事件: org.project.lifecycle_changed 落库 (confirm 审计)
- 路由函数 (无 HTTP): 空 name → ValueError; store 缺失 → None

basename 全仓库唯一 (test_console_* 前缀); fastapi/httpx 未安装 → HTTP 类
跳过 (与 test_console_project_draft.py 同模式)。测试真实装配 (build_console_service
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
_service_mod = importlib.import_module("factory-console.service")


def _space_dir(factory_root: Path, project_id: str) -> Path:
    """项目空间目录 (workspace/projects/{slug} — 经 index 自愈查询)。"""
    from org.space import ProjectSpaceStore

    space = ProjectSpaceStore(factory_root)
    slug = space.get_slug(project_id)
    assert slug is not None, f"no space slug for project {project_id}"
    return space.space_dir(slug)


def _index_map(factory_root: Path) -> dict:
    """workspace/projects.json 索引 (id→slug)。"""
    from org.space import ProjectSpaceStore

    return ProjectSpaceStore(factory_root).list_index()


def _org_project(factory_root: Path, project_id: str):
    """org/projects.json 镜像记录。"""
    from org.projects import ProjectStore

    return ProjectStore(factory_root / "org").get_project(project_id)


def _file_bytes(path: Path) -> bytes | None:
    """文件原始字节 (不存在 → None); 回滚断言逐字节一致。"""
    return path.read_bytes() if path.is_file() else None


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
    """缺 org/space store 的桩 (404 语义: confirm_project → None)。"""

    def confirm_project(self, project_id, name):
        return None


@requires_fastapi
class TestConfirmHttp:
    """POST /api/projects/{id}/confirm — rename 事务成功路径。"""

    @pytest.fixture
    def client(self, factory_root: Path, event_logger):
        """真实装配 (build_console_service → org ProjectStore + ProjectSpaceStore)。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            yield c

    def _draft_id(self, client) -> str:
        return client.post("/api/projects", json={"idea": "开发一个记账 App"}).json()[
            "project_id"
        ]

    def test_confirm_success_shape(self, client):
        """confirm {name} → 200 {project_id, name, slug, lifecycle: confirmed}。"""
        pid = self._draft_id(client)
        resp = client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        assert resp.status_code == 200
        assert resp.json() == {
            "project_id": pid,
            "name": "AI Note",
            "slug": "ai-note",
            "lifecycle": "confirmed",
        }

    def test_confirm_renames_directory(self, client, factory_root):
        """目录 rename: unnamed-project-xxx → {slug}/ (旧目录消失, 新目录为信源)。"""
        pid = self._draft_id(client)
        old_dir = _space_dir(factory_root, pid)
        assert old_dir.name.startswith("unnamed-project-")
        resp = client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        assert resp.status_code == 200
        assert not old_dir.exists()  # 旧目录已 rename 走
        new_dir = factory_root / "workspace" / "projects" / "ai-note"
        assert new_dir.is_dir()
        data = json.loads((new_dir / "project.json").read_text(encoding="utf-8"))
        assert data["id"] == pid
        assert data["name"] == "AI Note"
        assert data["slug"] == "ai-note"
        assert data["lifecycle"] == "confirmed"
        assert data["draft"] is False

    def test_confirm_keeps_conversation_and_discovery_files(self, client, factory_root):
        """文件不丢失: idea/conversation.json + idea.md + discovery/conversation.json
        (含问答记录) rename 后内容一致。"""
        pid = self._draft_id(client)
        client.post(
            f"/api/projects/{pid}/discovery/answer",
            json={"question": "目标平台?", "answer": "手机 App"},
        )
        old_dir = _space_dir(factory_root, pid)
        before = {
            "idea_conversation": (old_dir / "idea" / "conversation.json").read_bytes(),
            "idea_md": (old_dir / "idea" / "idea.md").read_bytes(),
            "discovery_conversation": (old_dir / "discovery" / "conversation.json").read_bytes(),
        }
        resp = client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        assert resp.status_code == 200
        new_dir = factory_root / "workspace" / "projects" / "ai-note"
        assert (new_dir / "idea" / "conversation.json").read_bytes() == before["idea_conversation"]
        assert (new_dir / "idea" / "idea.md").read_bytes() == before["idea_md"]
        disc = json.loads(
            (new_dir / "discovery" / "conversation.json").read_text(encoding="utf-8")
        )
        assert disc["conversation"][0]["answer"] == "手机 App"

    def test_confirm_updates_workspace_index(self, client, factory_root):
        """index 更新: workspace/projects.json 指向新 slug (无残留 unnamed)。"""
        pid = self._draft_id(client)
        client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        index = _index_map(factory_root)
        assert index.get(pid) == "ai-note"
        assert "unnamed-project" not in " ".join(index.values())

    def test_confirm_updates_org_mirror_id_stable(self, client, factory_root):
        """引用更新: org/projects.json 镜像 (id 不变, slug/name/lifecycle 更新)。"""
        pid = self._draft_id(client)
        resp = client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        assert resp.status_code == 200
        project = _org_project(factory_root, pid)
        assert project is not None
        assert project.id == pid  # id 稳定 (rename 不变)
        assert project.name == "AI Note"
        assert project.slug == "ai-note"
        assert project.lifecycle.value == "confirmed"
        assert project.draft is False

    def test_confirm_from_product_defined_keeps_product_definition(self, client, factory_root):
        """product_defined 状态 confirm → 200; product-definition.md 随目录保留。"""
        pid = self._draft_id(client)
        client.post(
            f"/api/projects/{pid}/discovery/answer",
            json={"question": "目标平台?", "answer": "手机 App"},
        )
        client.post(f"/api/projects/{pid}/discovery/complete")
        resp = client.post(f"/api/projects/{pid}/confirm", json={"name": "ScorePocket"})
        assert resp.status_code == 200
        assert resp.json()["lifecycle"] == "confirmed"
        new_dir = factory_root / "workspace" / "projects" / "scorepocket"
        assert (new_dir / "discovery" / "product-definition.md").is_file()

    def test_confirm_chinese_name_slug(self, client, factory_root):
        """中文名 → CJK slug 目录 (与 create_project 中文名保留同口径)。"""
        pid = self._draft_id(client)
        resp = client.post(f"/api/projects/{pid}/confirm", json={"name": "记账本"})
        assert resp.status_code == 200
        assert resp.json()["slug"] == "记账本"
        assert (factory_root / "workspace" / "projects" / "记账本").is_dir()

    def test_confirm_emits_lifecycle_changed(self, client, event_store):
        """事件: org.project.lifecycle_changed 落库 (confirm 审计)。"""
        pid = self._draft_id(client)
        client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        assert "org.project.lifecycle_changed" in event_types_of(event_store)


@requires_fastapi
class TestConfirmErrorsHttp:
    """confirm 错误/状态约束语义。"""

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

    def test_confirm_slug_conflict_409_untouched(self, client, factory_root):
        """slug 冲突 (已存在同名目录) → 409, 事务未开始 (目录/索引/引用不变)。"""
        pid_a = self._draft_id(client)
        client.post(f"/api/projects/{pid_a}/confirm", json={"name": "AI Note"})
        pid_b = self._draft_id(client)
        old_dir_b = _space_dir(factory_root, pid_b)
        index_before = _index_map(factory_root)
        org_before = _org_project(factory_root, pid_b)
        resp = client.post(f"/api/projects/{pid_b}/confirm", json={"name": "AI Note"})
        assert resp.status_code == 409
        assert old_dir_b.is_dir()  # B 目录未动
        assert _index_map(factory_root) == index_before  # 索引未动
        org_after = _org_project(factory_root, pid_b)
        assert org_after.lifecycle.value == "discovery"  # 状态未动
        assert org_after.draft is True
        assert org_after.name == org_before.name

    def test_confirm_empty_name_400(self, client):
        resp = client.post(f"/api/projects/{self._draft_id(client)}/confirm", json={"name": "   "})
        assert resp.status_code == 400

    def test_confirm_unslugifiable_name_400(self, client):
        """非法 name (无法 slug 化 — 空/纯符号) → 400。"""
        resp = client.post(
            f"/api/projects/{self._draft_id(client)}/confirm", json={"name": "!!! ..."}
        )
        assert resp.status_code == 400

    def test_confirm_missing_project_404(self, client):
        resp = client.post("/api/projects/P-nope/confirm", json={"name": "AI Note"})
        assert resp.status_code == 404

    def test_confirm_state_constraint_409(self, client):
        """非 discovery/product_defined 状态 (旧正式项目 lifecycle=idea) → 409。"""
        pid = client.post(
            "/api/projects", json={"idea": "开发一个记账 App", "name": "记账本"}
        ).json()["project_id"]
        resp = client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        assert resp.status_code == 409

    def test_confirm_idempotent_same_name_200(self, client, factory_root):
        """幂等: 已 confirmed 同 name 再次 confirm → 200 (原样返回, 目录不重复 rename)。"""
        pid = self._draft_id(client)
        first = client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        assert first.status_code == 200
        second = client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        assert second.status_code == 200
        assert second.json() == first.json()
        assert (factory_root / "workspace" / "projects" / "ai-note").is_dir()

    def test_confirm_confirmed_different_name_409(self, client):
        """已 confirmed 不同 name → 409 (已过确认点, 明确定义)。"""
        pid = self._draft_id(client)
        client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        resp = client.post(f"/api/projects/{pid}/confirm", json={"name": "Other Name"})
        assert resp.status_code == 409


@requires_fastapi
class TestConfirmRollbackHttp:
    """回滚路径: rename 中途失败 / rename 后镜像写失败 → 全量还原 (503)。"""

    def _make_client(self, factory_root: Path, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        return service, TestClient(app)

    def _state(self, factory_root, pid):
        """事务前磁盘状态快照 (旧目录/信源/索引/org 镜像)。"""
        from org.space import ProjectSpaceStore

        space = ProjectSpaceStore(factory_root)
        slug = space.get_slug(pid)
        old_dir = space.space_dir(slug)
        return {
            "slug": slug,
            "project_json": _file_bytes(old_dir / "project.json"),
            "index": _file_bytes(space.index_path),
            "org": _file_bytes(Path(factory_root) / "org" / "projects.json"),
        }

    def _assert_restored(self, factory_root, pid, snap):
        """回滚后磁盘状态逐字节还原 (目录/信源/索引/org 镜像/org 状态)。"""
        from org.space import ProjectSpaceStore
        from org.projects import ProjectStore

        space = ProjectSpaceStore(factory_root)
        assert space.has_space(snap["slug"]), "旧目录应还原"
        old_dir = space.space_dir(snap["slug"])
        assert (old_dir / "project.json").read_bytes() == snap["project_json"]
        assert _file_bytes(space.index_path) == snap["index"]
        assert _file_bytes(Path(factory_root) / "org" / "projects.json") == snap["org"]
        project = ProjectStore(factory_root / "org").get_project(pid)
        assert project is not None
        assert project.lifecycle.value == "discovery"
        assert project.draft is True

    def test_rollback_when_rename_fails(self, factory_root: Path, event_logger, monkeypatch):
        """目录 rename 中途失败 (os.replace 目录源 IO 错误) → 503 + 全量回滚。"""
        import org.space as org_space_module

        service, client = self._make_client(factory_root, event_logger)
        pid = client.post("/api/projects", json={"idea": "开发一个记账 App"}).json()[
            "project_id"
        ]
        snap = self._state(factory_root, pid)

        real_replace = org_space_module.os.replace

        def _failing_replace(src, dst):
            if Path(src).is_dir():
                raise OSError("simulated rename failure (目录 rename IO 错误)")
            return real_replace(src, dst)

        monkeypatch.setattr(org_space_module.os, "replace", _failing_replace)
        resp = client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        assert resp.status_code == 503
        self._assert_restored(factory_root, pid, snap)
        assert not (factory_root / "workspace" / "projects" / "ai-note").exists()

    def test_rollback_when_mirror_write_fails_after_rename(
        self, factory_root: Path, event_logger, monkeypatch
    ):
        """rename 后 org 镜像写失败 → 503 + 目录回滚 + 索引/引用还原。"""
        service, client = self._make_client(factory_root, event_logger)
        pid = client.post("/api/projects", json={"idea": "开发一个记账 App"}).json()[
            "project_id"
        ]
        snap = self._state(factory_root, pid)

        def _failing_save(project):
            raise OSError("simulated mirror write failure (org 镜像 IO 错误)")

        # 精确注入: 只让 service 持有的 org ProjectStore 实例 save_project 失败
        monkeypatch.setattr(service._project_store, "save_project", _failing_save)
        resp = client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        assert resp.status_code == 503
        self._assert_restored(factory_root, pid, snap)
        assert not (factory_root / "workspace" / "projects" / "ai-note").exists()


# ------------------------------------------------------------------ service 事务 (无 HTTP)


class TestConfirmService:
    def test_confirm_project_transaction(self, factory_root: Path, event_logger):
        """service.confirm_project: 事务成功 → name/slug/lifecycle/draft 更新, id 稳定。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        project = service.create_draft_project("开发一个记账 App")
        assert project is not None
        updated = service.confirm_project(project.id, "AI Note")
        assert updated is not None
        assert updated.id == project.id
        assert updated.name == "AI Note"
        assert updated.slug == "ai-note"
        assert updated.lifecycle.value == "confirmed"
        assert updated.draft is False

    def test_confirm_project_empty_name_raises(self, factory_root: Path, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        project = service.create_draft_project("开发一个记账 App")
        assert project is not None
        with pytest.raises(ValueError):
            service.confirm_project(project.id, "   ")

    def test_confirm_project_missing_project_none(self, factory_root: Path, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        assert service.confirm_project("P-nope", "AI Note") is None

    def test_confirm_project_no_store_none(self):
        """缺 store → None (HTTP 层 404/503 失败安全)。"""
        service = _service_mod.ConsoleService()
        assert service.confirm_project("P-1", "AI Note") is None

    def test_confirm_project_state_conflict_raises(self, factory_root: Path, event_logger):
        """非 discovery/product_defined → ProjectConfirmConflictError (HTTP 409)。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        project = service.create_project("开发一个记账 App", name="记账本")
        assert project is not None
        with pytest.raises(_service_mod.ProjectConfirmConflictError):
            service.confirm_project(project.id, "AI Note")

    def test_confirm_project_slug_conflict_raises(self, factory_root: Path, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        a = service.create_draft_project("开发一个记账 App")
        b = service.create_draft_project("做一个待办清单 App")
        assert a is not None and b is not None
        service.confirm_project(a.id, "AI Note")
        with pytest.raises(_service_mod.ProjectConfirmConflictError):
            service.confirm_project(b.id, "AI Note")

    def test_confirm_project_legacy_no_dir_ensure_space_then_rename(
        self, factory_root: Path, event_logger
    ):
        """兼容: 旧项目 (仅 org 记录, 无目录) confirm → 先 ensure_space 再 rename。"""
        from org.models import utcnow
        from org.projects import Project, ProjectState, ProjectStore

        store = ProjectStore(factory_root / "org")
        legacy = Project(
            id="P-legacy",
            name="unnamed-project-legacy",
            slug="",
            user_id="console",
            goal="旧项目无目录",
            lifecycle=ProjectState.PRODUCT_DEFINED,
            draft=True,
            updated_at=utcnow(),
        )
        store.save_project(legacy)
        assert not (factory_root / "workspace" / "projects").exists()  # 无任何目录
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        updated = service.confirm_project("P-legacy", "AI Note")
        assert updated is not None
        assert updated.slug == "ai-note"
        assert (factory_root / "workspace" / "projects" / "ai-note").is_dir()
        assert store.get_project("P-legacy").slug == "ai-note"

    def test_confirm_project_idempotent(self, factory_root: Path, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        project = service.create_draft_project("开发一个记账 App")
        assert project is not None
        first = service.confirm_project(project.id, "AI Note")
        second = service.confirm_project(project.id, "AI Note")
        assert first is not None and second is not None
        assert second.id == first.id
        assert second.slug == "ai-note"

    def test_confirm_rollback_rename_failure_service(
        self, factory_root: Path, event_logger, monkeypatch
    ):
        """service 级回滚: rename 失败 → 目录/信源/索引/镜像逐字节还原 + 抛异常。"""
        import org.space as org_space_module

        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        project = service.create_draft_project("开发一个记账 App")
        assert project is not None
        from org.space import ProjectSpaceStore

        space = ProjectSpaceStore(factory_root)
        slug = space.get_slug(project.id)
        old_dir = space.space_dir(slug)
        before = {
            "project_json": (old_dir / "project.json").read_bytes(),
            "index": _file_bytes(space.index_path),
            "org": _file_bytes(Path(factory_root) / "org" / "projects.json"),
        }
        real_replace = org_space_module.os.replace

        def _failing_replace(src, dst):
            if Path(src).is_dir():
                raise OSError("simulated rename failure (目录 rename IO 错误)")
            return real_replace(src, dst)

        monkeypatch.setattr(org_space_module.os, "replace", _failing_replace)
        with pytest.raises(_service_mod.ConfirmTransactionError):
            service.confirm_project(project.id, "AI Note")
        assert space.has_space(slug)
        assert (old_dir / "project.json").read_bytes() == before["project_json"]
        assert _file_bytes(space.index_path) == before["index"]
        assert _file_bytes(Path(factory_root) / "org" / "projects.json") == before["org"]
        assert not (factory_root / "workspace" / "projects" / "ai-note").exists()


# ------------------------------------------------------------------ 路由函数 (无 HTTP 依赖)


class TestConfirmRouteFunction:
    """api/projects confirm_project_route (无 HTTP 依赖) 语义。"""

    def test_confirm_route_empty_name_raises(self):
        with pytest.raises(ValueError):
            _api.confirm_project_route(_NoStoreService(), "P-1", "   ")

    def test_confirm_route_no_store_returns_none(self):
        summary = _api.confirm_project_route(_NoStoreService(), "P-1", "AI Note")
        assert summary is None

    def test_confirm_route_success_shape(self, factory_root: Path, event_logger):
        """路由函数成功 → ConfirmProjectSummary {project_id, name, slug, lifecycle}。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        project = service.create_draft_project("开发一个记账 App")
        assert project is not None
        summary = _api.confirm_project_route(service, project.id, "AI Note")
        assert summary is not None
        assert summary.to_dict() == {
            "project_id": project.id,
            "name": "AI Note",
            "slug": "ai-note",
            "lifecycle": "confirmed",
        }
