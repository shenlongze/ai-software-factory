"""tests/console/test_console_management_acceptance.py — S10-010 Task 005: 兼容集成 + Acceptance (TDD)。

覆盖 (AF-PRD-v1.md 4.3-4.5 + project-management-system.md + GATE-PASS B3/B4,
真实装配端到端 — build_console_service → org ProjectStore + ProjectSpaceStore +
ManagementStore 落盘 factory_root, 零 mock):

- 场景 1 (Backlog 全链): 创建项目 (正式) → Epic "用户系统" → Feature "登录"
  (绑定 Epic) → Story "用户登录" (绑定 Feature) → Task "实现登录 API" (P0,
  绑定 Story) → Task "登录测试" (依赖前者) — 层级 children 绑定 + 目录信源
- 场景 2 (Sprint): Sprint-001 (task_refs 乱序引用 2 Task) → plan 端点建议
  (priority 排序 P0 前) → Task 状态推进 (ready→in_progress→review→done) →
  Sprint 受控推进 (planning→active→completed)
- 场景 3 (依赖阻塞): Task B 依赖 A (A 未 done) → B 转 ready 拒绝 (400) →
  A 走完 done → B 可推进 (200)
- 场景 4 (持久化): 重建 service (新实例, 同 factory_root) → backlog/sprint/
  milestone/roadmap 数据仍在 (目录信源)
- 场景 5 (S10-009 集成): draft→discovery(问答)→complete→confirm 后 → 创建
  backlog/sprint → management/ 目录在同一项目空间 (workspace/projects/{slug}/)
- B3 治理: DELETE 项目 → workspace/projects/{slug}/ 目录清理 (防幽灵 —
  rebuild_index 后列表不含已删项目)
- B4 治理: PATCH rename 项目 (update_project) → 目录镜像同步 (project.json
  信源不陈旧) + 目录 rename + 索引更新 + org 记录同步

basename 全仓库唯一 (test_console_* 前缀); fastapi/httpx 未安装 → HTTP 类
跳过; 测试真实装配 (build_console_service → org ProjectStore + ProjectSpaceStore
+ ManagementStore 落盘 factory_root)。
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


def _create_project(client: Any, name: str = "Backlog Demo") -> str:
    """真实装配创建正式项目 (有 name → 旧兼容路径), 返回 project_id。"""
    resp = client.post(
        "/api/projects", json={"idea": "开发一个记账 App", "name": name}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["project_id"]


def _space_dir(factory_root: Path, project_id: str) -> Path:
    """项目空间目录 (workspace/projects/{slug} — 经 index 自愈查询)。"""
    from org.space import ProjectSpaceStore

    space = ProjectSpaceStore(factory_root)
    slug = space.get_slug(project_id)
    assert slug is not None, f"no space slug for project {project_id}"
    return space.space_dir(slug)


def _backlog_dir(factory_root: Path, project_id: str) -> Path:
    """项目 management/backlog 目录 (目录信源断言)。"""
    return _space_dir(factory_root, project_id) / "management" / "backlog"


def _org_project(factory_root: Path, project_id: str) -> Any:
    """org/projects.json 镜像记录。"""
    from org.projects import ProjectStore

    return ProjectStore(factory_root / "org").get_project(project_id)


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


def _create_sprint(
    client: Any,
    project_id: str,
    name: str = "Sprint One",
    *,
    goal: str = "",
    task_refs: list[str] | None = None,
) -> dict:
    body: dict = {"name": name}
    if goal:
        body["goal"] = goal
    if task_refs is not None:
        body["task_refs"] = task_refs
    resp = client.post(f"/api/projects/{project_id}/sprints", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_milestone(
    client: Any,
    project_id: str,
    name: str = "Milestone One",
    *,
    description: str = "",
    target_date: str = "",
    task_refs: list[str] | None = None,
) -> dict:
    body: dict = {"name": name}
    if description:
        body["description"] = description
    if target_date:
        body["target_date"] = target_date
    if task_refs is not None:
        body["task_refs"] = task_refs
    resp = client.post(f"/api/projects/{project_id}/milestones", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _advance_task_to_done(client: Any, project_id: str, task_id: str) -> None:
    """Task 状态机合法链走完: todo→ready→in_progress→review→done。"""
    for status in ("ready", "in_progress", "review", "done"):
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/{task_id}",
            json={"status": status},
        )
        assert resp.status_code == 200, resp.text


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


# ============================================================ 场景 1: Backlog 全链


@requires_fastapi
class TestScenario1BacklogChain:
    """验收场景 1: Epic→Feature→Story→Task 全链 (AF-PRD-v1.md 4.3 层级)。"""

    def test_epic_feature_story_task_chain(self, project, factory_root: Path):
        """正式项目 → 全链创建: 层级 children 绑定 + backlog 全量分组 + 目录信源。"""
        client, project_id = project
        epic = _create_epic(client, project_id, name="用户系统")
        feature = _create_feature(
            client, project_id, name="登录", epic_id=epic["id"]
        )
        story = _create_story(
            client, project_id, name="用户登录", feature_id=feature["id"]
        )
        task1 = _create_task(
            client, project_id, title="实现登录 API", priority="P0", story_id=story["id"]
        )
        task2 = _create_task(
            client, project_id, title="登录测试", dependency=[task1["id"]]
        )
        # 层级绑定 (children 引用, 非包含)
        assert feature["epic_id"] == epic["id"]
        assert story["feature_id"] == feature["id"]
        assert task1["story_id"] == story["id"]
        assert task2["dependency"] == [task1["id"]]
        # 全量分组
        resp = client.get(f"/api/projects/{project_id}/backlog")
        assert resp.status_code == 200
        body = resp.json()
        assert [e["id"] for e in body["epics"]] == [epic["id"]]
        assert [f["id"] for f in body["features"]] == [feature["id"]]
        assert [s["id"] for s in body["stories"]] == [story["id"]]
        assert {t["id"] for t in body["tasks"]} == {task1["id"], task2["id"]}
        # 目录信源 (management/backlog/*.json)
        backlog_dir = _backlog_dir(factory_root, project_id)
        for filename in ("epic.json", "feature.json", "story.json", "task.json"):
            assert (backlog_dir / filename).is_file(), f"missing {filename}"


# ================================================================ 场景 2: Sprint


@requires_fastapi
class TestScenario2SprintLifecycle:
    """验收场景 2: Sprint-001 + plan 建议 + Task 推进 → done + Sprint completed。"""

    def test_sprint_plan_advance_complete(self, project):
        """Sprint-001 (乱序 task_refs) → plan 按 priority 排序 → Task 走完 →
        Sprint 受控推进到 completed。"""
        client, project_id = project
        t1 = _create_task(client, project_id, title="核心 API", priority="P0")
        t2 = _create_task(client, project_id, title="辅助任务", priority="P1")
        sprint = _create_sprint(
            client, project_id, name="Sprint-001", task_refs=[t2["id"], t1["id"]]
        )
        assert sprint["task_refs"] == [t2["id"], t1["id"]]
        # plan 端点 → 建议列表 (priority 排序: P0 在前, 与 task_refs 乱序无关)
        resp = client.post(
            f"/api/projects/{project_id}/sprints/{sprint['id']}/plan", json={}
        )
        assert resp.status_code == 200, resp.text
        suggestions = resp.json()["suggestions"]
        assert [s["id"] for s in suggestions] == [t1["id"], t2["id"]]
        assert all(s["dependency_satisfied"] for s in suggestions)
        # Task 状态推进 (ready→in_progress→review→done)
        _advance_task_to_done(client, project_id, t1["id"])
        _advance_task_to_done(client, project_id, t2["id"])
        # Sprint 受控推进 → completed
        for status in ("active", "completed"):
            resp = client.patch(
                f"/api/projects/{project_id}/sprints/{sprint['id']}",
                json={"status": status},
            )
            assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "completed"


# =============================================================== 场景 3: 依赖阻塞


@requires_fastapi
class TestScenario3DependencyGate:
    """验收场景 3: Task B 依赖 A — A 未 done → B 推进拒绝; A done → B 可推进。"""

    def test_dependency_blocks_then_releases(self, project):
        """依赖 gate 真实端到端: 阻塞 (400) → 前置完成 → 放行 (200)。"""
        client, project_id = project
        a = _create_task(client, project_id, title="前置 A")
        b = _create_task(client, project_id, title="后继 B", dependency=[a["id"]])
        # A 未 done → B 转 ready → 400 (依赖未满足, 诚实拒绝)
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/{b['id']}",
            json={"status": "ready"},
        )
        assert resp.status_code == 400
        assert "dependenc" in resp.json()["error"]["message"]
        # B 状态未被破坏 (仍 todo)
        detail = client.get(
            f"/api/projects/{project_id}/backlog/task/{b['id']}"
        ).json()
        assert detail["status"] == "todo"
        # A 推进到 done → B 可推进 (200)
        _advance_task_to_done(client, project_id, a["id"])
        resp = client.patch(
            f"/api/projects/{project_id}/backlog/task/{b['id']}",
            json={"status": "ready"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"


# ================================================================ 场景 4: 持久化


@requires_fastapi
class TestScenario4Persistence:
    """验收场景 4: 重建 service (新实例) → backlog/sprint/milestone/roadmap 数据仍在。"""

    def test_rebuild_service_all_management_data_survives(
        self, factory_root: Path, event_logger
    ):
        """第一实例创建 backlog+sprint+milestone+roadmap → 第二实例 (同 factory_root)
        → 全量数据仍在 (目录信源, 非内存)。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            project_id = _create_project(c, name="Persist Demo")
            epic = _create_epic(c, project_id, name="持久化 Epic")
            task = _create_task(c, project_id, title="持久化 Task", priority="P0")
            sprint = _create_sprint(
                c, project_id, name="Sprint-P", task_refs=[task["id"]]
            )
            ms = _create_milestone(c, project_id, name="M1", target_date="2026-09-30")
            resp = c.post(
                f"/api/projects/{project_id}/roadmap/milestone-ref",
                json={"milestone_id": ms["id"]},
            )
            assert resp.status_code == 200, resp.text
        # 重建 service + app (新实例 — 目录信源)
        service2 = _adapter.build_console_service(
            factory_root, event_logger=event_logger
        )
        app2 = _adapter.build_app(service2, event_logger=event_logger)
        with TestClient(app2) as c2:
            backlog = c2.get(f"/api/projects/{project_id}/backlog")
            assert backlog.status_code == 200
            assert [e["id"] for e in backlog.json()["epics"]] == [epic["id"]]
            assert [t["id"] for t in backlog.json()["tasks"]] == [task["id"]]
            sprints = c2.get(f"/api/projects/{project_id}/sprints").json()["sprints"]
            assert [s["id"] for s in sprints] == [sprint["id"]]
            assert [s["status"] for s in sprints] == ["planning"]
            milestones = c2.get(
                f"/api/projects/{project_id}/milestones"
            ).json()["milestones"]
            assert [m["id"] for m in milestones] == [ms["id"]]
            roadmap = c2.get(f"/api/projects/{project_id}/roadmap").json()
            assert ms["id"] in roadmap["milestone_refs"]


# ========================================================== 场景 5: S10-009 集成


@requires_fastapi
class TestScenario5S1009Integration:
    """验收场景 5: draft→discovery→complete→confirm 后 → backlog/sprint 与
    management/ 目录在同一项目空间 (S10-009 与 S10-010 无缝衔接)。"""

    def test_draft_confirm_then_management_same_space(self, project, factory_root: Path):
        """draft (无 name) → 问答 → complete → confirm "Backlog Pro" → 创建
        epic/task/sprint → management/ 落在 workspace/projects/backlog-pro/ 下。"""
        client, _ = project
        # 1. draft (S10-009 路径)
        resp = client.post("/api/projects", json={"idea": "我要做一个AI笔记软件"})
        assert resp.status_code == 201
        pid = resp.json()["project_id"]
        assert resp.json()["draft"] is True
        # 2. discovery 问答 + complete → product_defined
        resp = client.post(
            f"/api/projects/{pid}/discovery/answer",
            json={"question": "目标平台?", "answer": "手机 App"},
        )
        assert resp.status_code == 200
        resp = client.post(f"/api/projects/{pid}/discovery/complete")
        assert resp.status_code == 200
        assert resp.json()["lifecycle"] == "product_defined"
        # 3. confirm → 正式命名 (backlog-pro/ 目录 + CONFIRMED)
        resp = client.post(f"/api/projects/{pid}/confirm", json={"name": "Backlog Pro"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["slug"] == "backlog-pro"
        # 4. 同一空间创建 backlog + sprint (S10-010 路径)
        epic = _create_epic(client, pid, name="用户系统")
        task = _create_task(client, pid, title="实现登录", priority="P0")
        sprint = _create_sprint(client, pid, name="Sprint-001", task_refs=[task["id"]])
        # management/ 目录在同一项目空间 (workspace/projects/backlog-pro/)
        space_dir = _space_dir(factory_root, pid)
        assert space_dir.name == "backlog-pro"
        assert (space_dir / "management" / "backlog" / "epic.json").is_file()
        assert (
            space_dir / "management" / "sprint" / f"{sprint['id']}.json"
        ).is_file()
        # 数据经 S10-010 API 可读 (同空间回读)
        backlog = client.get(f"/api/projects/{pid}/backlog").json()
        assert [e["id"] for e in backlog["epics"]] == [epic["id"]]
        assert [s["id"] for s in client.get(f"/api/projects/{pid}/sprints").json()["sprints"]] == [
            sprint["id"]
        ]


# ============================================================ B3 治理: DELETE 清理


@requires_fastapi
class TestGovernanceB3DeleteCleanup:
    """GATE-PASS B3: DELETE 项目 → ProjectSpace 目录清理 (防幽灵 — rebuild_index
    后列表不含已删项目)。"""

    def test_delete_project_cleans_space_dir(self, project, factory_root: Path):
        """删除项目 → workspace/projects/{slug}/ 目录被清理 + 索引/列表无幽灵。"""
        client, project_id = project
        _create_task(client, project_id)  # 触发 management/ 目录 (space 骨架)
        from org.space import ProjectSpaceStore

        space = ProjectSpaceStore(factory_root)
        slug = space.get_slug(project_id)
        assert slug is not None and space.has_space(slug)
        assert (space.space_dir(slug) / "management").is_dir()
        # DELETE 项目 → 200
        resp = client.delete(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": True, "project_id": project_id}
        # 目录清理 (防幽灵 — 不残留孤儿目录)
        assert not space.space_dir(slug).exists()
        # rebuild_index 后索引与列表均不含已删项目
        index = space.rebuild_index()
        assert project_id not in index
        listed = {p["id"] for p in client.get("/api/projects").json()["items"]}
        assert project_id not in listed


# ========================================================== B4 治理: rename 镜像


@requires_fastapi
class TestGovernanceB4RenameMirror:
    """GATE-PASS B4: PATCH rename 项目 → 目录镜像同步 (信源不陈旧) + 目录
    rename + 索引更新 + org 记录同步。"""

    def test_patch_rename_syncs_space_mirror(self, project, factory_root: Path):
        """rename "Backlog Demo" → "Project Alpha": 目录 rename (backlog-demo →
        project-alpha), project.json 镜像 name 同步, 索引/org 记录一致, 既有
        management 数据随目录保留。"""
        client, project_id = project
        _create_task(client, project_id)  # 触发 space 目录 + management 数据
        from org.space import ProjectSpaceStore

        space = ProjectSpaceStore(factory_root)
        old_slug = space.get_slug(project_id)
        assert old_slug == "backlog-demo" and space.has_space(old_slug)
        # PATCH rename → 200
        resp = client.patch(f"/api/projects/{project_id}", json={"name": "Project Alpha"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Project Alpha"
        # 目录 rename: 新目录存在, 旧目录不残留
        new_slug = space.get_slug(project_id)
        assert new_slug == "project-alpha"
        assert new_slug != old_slug
        assert space.has_space(new_slug)
        assert not space.has_space(old_slug)
        # 目录镜像同步 (信源不陈旧 — project.json 的 name 已更新)
        mirror = json.loads(
            (space.space_dir(new_slug) / "project.json").read_text(encoding="utf-8")
        )
        assert mirror["id"] == project_id
        assert mirror["name"] == "Project Alpha"
        # org 记录同步
        org = _org_project(factory_root, project_id)
        assert org is not None and org.name == "Project Alpha"
        # 既有 management 数据随目录 rename 保留 (零丢失)
        assert (space.space_dir(new_slug) / "management" / "backlog" / "task.json").is_file()
        # 列表仍可见新名
        listed = {p["id"]: p for p in client.get("/api/projects").json()["items"]}
        assert listed[project_id]["name"] == "Project Alpha"

    def test_patch_idea_syncs_mirror(self, project, factory_root: Path):
        """仅改 idea → 目录不动, project.json 镜像 goal 同步更新 (信源不陈旧)。"""
        client, project_id = project
        _create_task(client, project_id)
        resp = client.patch(f"/api/projects/{project_id}", json={"idea": "记账 + 报表"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["idea"] == "记账 + 报表"
        from org.space import ProjectSpaceStore

        space = ProjectSpaceStore(factory_root)
        slug = space.get_slug(project_id)
        mirror = json.loads(
            (space.space_dir(slug) / "project.json").read_text(encoding="utf-8")
        )
        assert mirror["goal"] == "记账 + 报表"
        assert mirror["name"] == "Backlog Demo"  # name 未动


# ============================================================ 路由函数层 (无 HTTP)


class TestManagementAcceptanceRoutes:
    """路由函数层补充 (不经 HTTP — fastapi 缺失时仍可运行)。"""

    def test_route_create_chain_value_error_semantics(self, factory_root, event_logger):
        """全链创建入口均可用 (真实装配, 直接调 service)。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        summary = service.create_project("验收想法", name="Route Accept")
        assert summary is not None
        epic = _api.create_epic(service, summary.id, name="E", description="")
        assert epic is not None and epic["id"].startswith("EPIC-")
        with pytest.raises(ValueError):
            _api.create_epic(service, summary.id, name="   ", description="")
        with pytest.raises(ValueError):
            _api.create_sprint(service, summary.id, name="  ")
