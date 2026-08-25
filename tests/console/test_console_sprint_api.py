"""tests/console/test_console_sprint_api.py — S10-010 Task 004: Sprint/Milestone/Roadmap API (TDD)。

覆盖 (factory-console/api/sprint.py + service.py sprint/milestone/roadmap_* 方法 +
web/backend/fastapi_adapter.py 端点 + org/management.py Sprint 状态机复用):
- POST /api/projects/{id}/sprints {name, goal?, start_date?, end_date?,
  task_refs?} → Sprint (默认 planning; 空 name → 400; 项目不存在 → 404;
  task_ref 引用不存在 Task → 400)
- GET /api/projects/{id}/sprints → 列表 (诚实空态); GET .../sprints/{sprint_id}
  → 详情 (不存在 → 404)
- PATCH .../sprints/{sprint_id} {goal?/task_refs?/status?/daily_progress?/
  review?}:
  - task_refs 引用 Task (非包含 — 更新引用不影响 Task 本身)
  - task_ref 引用不存在 Task → 400
  - status 受控转换 planning→active→completed (非法跳级/回退 → 409;
    非法值 → 400)
- DELETE .../sprints/{sprint_id} → 200 {deleted} (Task 保留 — 引用非包含)
- POST .../sprints/{id}/plan {goal?} → 可执行任务建议 (sort_tasks 纯函数:
  依赖满足组优先 + priority 排序; 不实际调度)
- POST /api/projects/{id}/milestones {name, description?, target_date?,
  task_refs?} → Milestone + GET/PATCH/DELETE (同 Sprint 模式)
- GET /api/projects/{id}/roadmap → {milestone_refs, updated_at};
  POST .../roadmap/milestone-ref {milestone_id} → 追加引用 (milestone 不存在
  → 400; 重复追加去重)
- 错误: 项目 404 / Sprint/Milestone 不存在 404 / task_ref 不存在 400
- 持久化: 目录信源 management/sprint/{id}.json + milestone.json + roadmap.md
  (重建 service → 数据仍在)

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
        "/api/projects", json={"idea": "开发一个记账 App", "name": "Sprint Demo"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["project_id"]


def _management_dir(factory_root: Path, project_id: str) -> Path:
    """项目 management 目录 (目录信源断言)。"""
    from org.space import ProjectSpaceStore

    space = ProjectSpaceStore(factory_root)
    slug = space.get_slug(project_id)
    assert slug is not None, f"no space slug for project {project_id}"
    return space.space_dir(slug) / "management"


def _create_task(
    client: Any,
    project_id: str,
    title: str = "Task One",
    *,
    priority: str | None = None,
    dependency: list[str] | None = None,
) -> dict:
    body: dict = {"title": title, "description": "首个 Task"}
    if priority is not None:
        body["priority"] = priority
    if dependency is not None:
        body["dependency"] = dependency
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


# ------------------------------------------------------------------ Sprint 创建


@requires_fastapi
class TestSprintCreateHttp:
    def test_create_sprint_201_shape(self, project):
        """POST /sprints {name, goal, start_date, end_date} → 201 Sprint。"""
        client, project_id = project
        resp = client.post(
            f"/api/projects/{project_id}/sprints",
            json={
                "name": "迭代一",
                "goal": "完成支付闭环",
                "start_date": "2026-08-01",
                "end_date": "2026-08-14",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["id"].startswith("SPRINT-")
        assert body["name"] == "迭代一"
        assert body["goal"] == "完成支付闭环"
        assert body["start_date"] == "2026-08-01"
        assert body["end_date"] == "2026-08-14"
        assert body["status"] == "planning"  # 默认 planning
        assert body["task_refs"] == []
        assert body["created_at"] and body["updated_at"]

    def test_create_sprint_with_task_refs(self, project):
        """task_refs 提供 → Sprint 引用 Task (非包含)。"""
        client, project_id = project
        t1 = _create_task(client, project_id, title="任务一")
        t2 = _create_task(client, project_id, title="任务二")
        body = _create_sprint(client, project_id, task_refs=[t1["id"], t2["id"]])
        assert body["task_refs"] == [t1["id"], t2["id"]]

    def test_create_sprint_empty_name_400(self, project):
        client, project_id = project
        resp = client.post(
            f"/api/projects/{project_id}/sprints", json={"name": "   "}
        )
        assert resp.status_code == 400
        assert "name" in resp.json()["error"]["message"]

    def test_create_sprint_task_ref_missing_400(self, project):
        """task_ref 引用不存在 Task → 400 (引用校验, 输入错误)。"""
        client, project_id = project
        resp = client.post(
            f"/api/projects/{project_id}/sprints",
            json={"name": "S", "task_refs": ["TASK-nope"]},
        )
        assert resp.status_code == 400
        assert "task" in resp.json()["error"]["message"]

    def test_create_sprint_project_missing_404(self, factory_root, event_logger):
        """项目不存在 → 404。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            resp = c.post("/api/projects/P-nope/sprints", json={"name": "S"})
        assert resp.status_code == 404


# ------------------------------------------------------------------ Sprint 列表/详情


@requires_fastapi
class TestSprintListDetailHttp:
    def test_list_sprints_empty(self, project):
        client, project_id = project
        resp = client.get(f"/api/projects/{project_id}/sprints")
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == project_id
        assert body["sprints"] == []

    def test_list_sprints_returns_created(self, project):
        client, project_id = project
        s1 = _create_sprint(client, project_id, name="迭代一")
        s2 = _create_sprint(client, project_id, name="迭代二")
        resp = client.get(f"/api/projects/{project_id}/sprints")
        assert resp.status_code == 200
        ids = [s["id"] for s in resp.json()["sprints"]]
        assert sorted(ids) == sorted([s1["id"], s2["id"]])

    def test_get_sprint_detail_200(self, project):
        client, project_id = project
        sprint = _create_sprint(client, project_id, name="详情迭代")
        resp = client.get(f"/api/projects/{project_id}/sprints/{sprint['id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == sprint["id"]
        assert body["name"] == "详情迭代"
        assert body["status"] == "planning"

    def test_get_sprint_missing_404(self, project):
        client, project_id = project
        resp = client.get(f"/api/projects/{project_id}/sprints/SPRINT-nope")
        assert resp.status_code == 404
        assert "sprint" in resp.json()["error"]["message"]

    def test_list_sprints_project_missing_404(self, factory_root, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            resp = c.get("/api/projects/P-nope/sprints")
        assert resp.status_code == 404


# ------------------------------------------------------------------ Sprint PATCH


@requires_fastapi
class TestSprintPatchHttp:
    def test_patch_sprint_fields_200(self, project):
        """PATCH goal/daily_progress/review/日期 → 字段更新落库。"""
        client, project_id = project
        sprint = _create_sprint(client, project_id)
        resp = client.patch(
            f"/api/projects/{project_id}/sprints/{sprint['id']}",
            json={
                "goal": "新目标",
                "review": "首轮评审",
                "daily_progress": [{"day": "2026-08-03", "note": "进度 30%"}],
                "start_date": "2026-08-02",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["goal"] == "新目标"
        assert body["review"] == "首轮评审"
        assert body["daily_progress"] == [{"day": "2026-08-03", "note": "进度 30%"}]
        assert body["start_date"] == "2026-08-02"

    def test_patch_sprint_task_refs_reference_not_containment(self, project):
        """task_refs 更新只改 Sprint 引用, 不影响 Task 本身 (非包含)。"""
        client, project_id = project
        t1 = _create_task(client, project_id, title="任务甲")
        t2 = _create_task(client, project_id, title="任务乙")
        sprint = _create_sprint(client, project_id, task_refs=[t1["id"]])
        resp = client.patch(
            f"/api/projects/{project_id}/sprints/{sprint['id']}",
            json={"task_refs": [t1["id"], t2["id"]]},
        )
        assert resp.status_code == 200
        assert resp.json()["task_refs"] == [t1["id"], t2["id"]]
        # Task 本身不受影响 (title/status 原样)
        resp = client.get(f"/api/projects/{project_id}/backlog/task/{t1['id']}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "任务甲"
        assert resp.json()["status"] == "todo"

    def test_patch_sprint_task_ref_missing_400(self, project):
        client, project_id = project
        sprint = _create_sprint(client, project_id)
        resp = client.patch(
            f"/api/projects/{project_id}/sprints/{sprint['id']}",
            json={"task_refs": ["TASK-nope"]},
        )
        assert resp.status_code == 400
        assert "task" in resp.json()["error"]["message"]

    def test_patch_sprint_status_planning_to_active_200(self, project):
        """受控转换: planning → active → 200。"""
        client, project_id = project
        sprint = _create_sprint(client, project_id)
        resp = client.patch(
            f"/api/projects/{project_id}/sprints/{sprint['id']}",
            json={"status": "active"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "active"

    def test_patch_sprint_status_active_to_completed_200(self, project):
        """受控转换: planning → active → completed → 200。"""
        client, project_id = project
        sprint = _create_sprint(client, project_id)
        for status in ("active", "completed"):
            resp = client.patch(
                f"/api/projects/{project_id}/sprints/{sprint['id']}",
                json={"status": status},
            )
            assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "completed"

    def test_patch_sprint_status_illegal_409(self, project):
        """非法转换 (跳级 planning → completed / 终态回退) → 409。"""
        client, project_id = project
        sprint = _create_sprint(client, project_id)
        resp = client.patch(
            f"/api/projects/{project_id}/sprints/{sprint['id']}",
            json={"status": "completed"},
        )
        assert resp.status_code == 409
        assert "transition" in resp.json()["error"]["message"]
        # 走完合法链后回退 → 409
        for status in ("active", "completed"):
            resp = client.patch(
                f"/api/projects/{project_id}/sprints/{sprint['id']}",
                json={"status": status},
            )
            assert resp.status_code == 200, resp.text
        resp = client.patch(
            f"/api/projects/{project_id}/sprints/{sprint['id']}",
            json={"status": "active"},
        )
        assert resp.status_code == 409

    def test_patch_sprint_status_invalid_value_400(self, project):
        """非法 status 值 → 400 (输入校验, 非状态冲突)。"""
        client, project_id = project
        sprint = _create_sprint(client, project_id)
        resp = client.patch(
            f"/api/projects/{project_id}/sprints/{sprint['id']}",
            json={"status": "paused"},
        )
        assert resp.status_code == 400
        assert "status" in resp.json()["error"]["message"]

    def test_patch_sprint_missing_404(self, project):
        client, project_id = project
        resp = client.patch(
            f"/api/projects/{project_id}/sprints/SPRINT-nope",
            json={"goal": "x"},
        )
        assert resp.status_code == 404


# ------------------------------------------------------------------ Sprint DELETE


@requires_fastapi
class TestSprintDeleteHttp:
    def test_delete_sprint_200_keeps_task(self, project):
        """删除 Sprint → 200 {deleted}; Task 保留 (引用非包含)。"""
        client, project_id = project
        task = _create_task(client, project_id)
        sprint = _create_sprint(client, project_id, task_refs=[task["id"]])
        resp = client.delete(f"/api/projects/{project_id}/sprints/{sprint['id']}")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": True, "sprint_id": sprint["id"]}
        # Sprint 详情 → 404; Task 仍在
        resp = client.get(f"/api/projects/{project_id}/sprints/{sprint['id']}")
        assert resp.status_code == 404
        resp = client.get(f"/api/projects/{project_id}/backlog/task/{task['id']}")
        assert resp.status_code == 200

    def test_delete_sprint_missing_404(self, project):
        client, project_id = project
        resp = client.delete(f"/api/projects/{project_id}/sprints/SPRINT-nope")
        assert resp.status_code == 404


# ------------------------------------------------------------------ Sprint Planning 预留


@requires_fastapi
class TestSprintPlanHttp:
    def test_plan_sprint_sorts_by_dependency_and_priority(self, project):
        """plan → 建议列表: 依赖满足组优先, 组内按 priority (P0 最前)。"""
        client, project_id = project
        # A (P0, 无依赖) / B (P2, 依赖 A) / C (P1, 无依赖, 未完成)
        a = _create_task(client, project_id, title="A", priority="P0")
        b = _create_task(client, project_id, title="B", priority="P2", dependency=[a["id"]])
        c = _create_task(client, project_id, title="C", priority="P1")
        # A 走完 → done; C 保持 todo
        for status in ("ready", "in_progress", "review", "done"):
            resp = client.patch(
                f"/api/projects/{project_id}/backlog/task/{a['id']}",
                json={"status": status},
            )
            assert resp.status_code == 200, resp.text
        sprint = _create_sprint(
            client, project_id, task_refs=[b["id"], a["id"], c["id"]]
        )
        resp = client.post(
            f"/api/projects/{project_id}/sprints/{sprint['id']}/plan", json={}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["sprint_id"] == sprint["id"]
        suggestions = body["suggestions"]
        # A 已 DONE → B (依赖 [A]) 依赖满足 = True; 按 priority: A(P0) C(P1) B(P2)
        by_id = {s["id"]: s for s in suggestions}
        assert set(by_id) == {a["id"], b["id"], c["id"]}
        assert by_id[b["id"]]["dependency_satisfied"] is True
        assert by_id[a["id"]]["dependency_satisfied"] is True
        assert by_id[c["id"]]["dependency_satisfied"] is True
        assert [s["id"] for s in suggestions] == [a["id"], c["id"], b["id"]]  # P0 P1 P2

    def test_plan_sprint_echoes_goal(self, project):
        """plan {goal} → 回显 goal (预留端点不落库, 只给建议)。"""
        client, project_id = project
        sprint = _create_sprint(client, project_id)
        resp = client.post(
            f"/api/projects/{project_id}/sprints/{sprint['id']}/plan",
            json={"goal": "冲刺目标"},
        )
        assert resp.status_code == 200
        assert resp.json()["goal"] == "冲刺目标"

    def test_plan_sprint_missing_404(self, project):
        client, project_id = project
        resp = client.post("/api/projects/P-x/sprints/SPRINT-nope/plan", json={})
        assert resp.status_code == 404


# ------------------------------------------------------------------ Milestone 创建


@requires_fastapi
class TestMilestoneCreateHttp:
    def test_create_milestone_201_shape(self, project):
        """POST /milestones {name, description, target_date} → 201 Milestone。"""
        client, project_id = project
        resp = client.post(
            f"/api/projects/{project_id}/milestones",
            json={
                "name": "内测发布",
                "description": "可玩版本",
                "target_date": "2026-09-30",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["id"].startswith("MS-")
        assert body["name"] == "内测发布"
        assert body["description"] == "可玩版本"
        assert body["target_date"] == "2026-09-30"
        assert body["status"] == "planned"  # 默认 planned (自由文本宽容)
        assert body["task_refs"] == []

    def test_create_milestone_with_task_refs(self, project):
        client, project_id = project
        t1 = _create_task(client, project_id)
        body = _create_milestone(client, project_id, task_refs=[t1["id"]])
        assert body["task_refs"] == [t1["id"]]

    def test_create_milestone_task_ref_missing_400(self, project):
        client, project_id = project
        resp = client.post(
            f"/api/projects/{project_id}/milestones",
            json={"name": "M", "task_refs": ["TASK-nope"]},
        )
        assert resp.status_code == 400
        assert "task" in resp.json()["error"]["message"]

    def test_create_milestone_empty_name_400(self, project):
        client, project_id = project
        resp = client.post(
            f"/api/projects/{project_id}/milestones", json={"name": "  "}
        )
        assert resp.status_code == 400


# ------------------------------------------------------------------ Milestone 列表/PATCH/DELETE


@requires_fastapi
class TestMilestoneListPatchDeleteHttp:
    def test_list_milestones(self, project):
        client, project_id = project
        resp = client.get(f"/api/projects/{project_id}/milestones")
        assert resp.status_code == 200
        assert resp.json()["milestones"] == []
        m1 = _create_milestone(client, project_id, name="里程碑一")
        resp = client.get(f"/api/projects/{project_id}/milestones")
        assert [m["id"] for m in resp.json()["milestones"]] == [m1["id"]]

    def test_get_milestone_detail_200_and_missing_404(self, project):
        client, project_id = project
        m = _create_milestone(client, project_id)
        resp = client.get(f"/api/projects/{project_id}/milestones/{m['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Milestone One"
        resp = client.get(f"/api/projects/{project_id}/milestones/MS-nope")
        assert resp.status_code == 404
        assert "milestone" in resp.json()["error"]["message"]

    def test_patch_milestone_fields_200(self, project):
        client, project_id = project
        m = _create_milestone(client, project_id)
        resp = client.patch(
            f"/api/projects/{project_id}/milestones/{m['id']}",
            json={
                "name": "改名里程碑",
                "description": "新描述",
                "target_date": "2026-10-01",
                "status": "in_progress",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "改名里程碑"
        assert body["description"] == "新描述"
        assert body["target_date"] == "2026-10-01"
        assert body["status"] == "in_progress"  # 自由文本宽容

    def test_patch_milestone_task_refs_200_and_missing_400(self, project):
        """task_refs 引用 Task (非包含); 引用不存在 → 400。"""
        client, project_id = project
        t1 = _create_task(client, project_id, title="里程碑任务")
        m = _create_milestone(client, project_id)
        resp = client.patch(
            f"/api/projects/{project_id}/milestones/{m['id']}",
            json={"task_refs": [t1["id"]]},
        )
        assert resp.status_code == 200
        assert resp.json()["task_refs"] == [t1["id"]]
        # Task 本身不受影响
        resp = client.get(f"/api/projects/{project_id}/backlog/task/{t1['id']}")
        assert resp.json()["title"] == "里程碑任务"
        resp = client.patch(
            f"/api/projects/{project_id}/milestones/{m['id']}",
            json={"task_refs": ["TASK-nope"]},
        )
        assert resp.status_code == 400

    def test_patch_milestone_missing_404(self, project):
        client, project_id = project
        resp = client.patch(
            f"/api/projects/{project_id}/milestones/MS-nope", json={"name": "x"}
        )
        assert resp.status_code == 404

    def test_delete_milestone_200_and_missing_404(self, project):
        client, project_id = project
        m = _create_milestone(client, project_id)
        resp = client.delete(f"/api/projects/{project_id}/milestones/{m['id']}")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": True, "milestone_id": m["id"]}
        resp = client.get(f"/api/projects/{project_id}/milestones/{m['id']}")
        assert resp.status_code == 404
        resp = client.delete(f"/api/projects/{project_id}/milestones/MS-nope")
        assert resp.status_code == 404


# ------------------------------------------------------------------ Roadmap


@requires_fastapi
class TestRoadmapHttp:
    def test_get_roadmap_empty(self, project):
        """GET /roadmap → 诚实空态 {milestone_refs: []}。"""
        client, project_id = project
        resp = client.get(f"/api/projects/{project_id}/roadmap")
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == project_id
        assert body["milestone_refs"] == []
        assert body["updated_at"]

    def test_roadmap_append_milestone_ref_200(self, project):
        """POST /roadmap/milestone-ref {milestone_id} → 追加引用。"""
        client, project_id = project
        m = _create_milestone(client, project_id, name="发布节点")
        resp = client.post(
            f"/api/projects/{project_id}/roadmap/milestone-ref",
            json={"milestone_id": m["id"]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["milestone_refs"] == [m["id"]]
        resp = client.get(f"/api/projects/{project_id}/roadmap")
        assert resp.json()["milestone_refs"] == [m["id"]]

    def test_roadmap_ref_missing_milestone_400(self, project):
        """milestone 不存在 → 400 (引用校验, 同 task_ref 语义)。"""
        client, project_id = project
        resp = client.post(
            f"/api/projects/{project_id}/roadmap/milestone-ref",
            json={"milestone_id": "MS-nope"},
        )
        assert resp.status_code == 400
        assert "milestone" in resp.json()["error"]["message"]

    def test_roadmap_append_dedupes(self, project):
        """重复追加同一 milestone → 去重 (幂等)。"""
        client, project_id = project
        m = _create_milestone(client, project_id)
        resp = None
        for _ in range(2):
            resp = client.post(
                f"/api/projects/{project_id}/roadmap/milestone-ref",
                json={"milestone_id": m["id"]},
            )
            assert resp.status_code == 200, resp.text
        assert resp is not None
        assert resp.json()["milestone_refs"] == [m["id"]]


# ------------------------------------------------------------------ 持久化 (目录信源)


@requires_fastapi
class TestManagementPersistence:
    def test_sprint_file_written(self, project, factory_root):
        """目录信源: management/sprint/{id}.json 落盘。"""
        client, project_id = project
        sprint = _create_sprint(client, project_id, name="持久化迭代")
        path = _management_dir(factory_root, project_id) / "sprint" / f"{sprint['id']}.json"
        assert path.is_file(), f"missing {path}"
        data = json.loads(path.read_text(encoding="utf-8"))["sprint"]
        assert data["id"] == sprint["id"]
        assert data["name"] == "持久化迭代"

    def test_milestone_json_written(self, project, factory_root):
        client, project_id = project
        m = _create_milestone(client, project_id)
        path = _management_dir(factory_root, project_id) / "milestone.json"
        assert path.is_file(), f"missing {path}"
        data = json.loads(path.read_text(encoding="utf-8"))["milestones"]
        assert m["id"] in data

    def test_roadmap_md_written(self, project, factory_root):
        """roadmap.md 信源: 结构化块 + markdown 引用列表。"""
        client, project_id = project
        m = _create_milestone(client, project_id)
        resp = client.post(
            f"/api/projects/{project_id}/roadmap/milestone-ref",
            json={"milestone_id": m["id"]},
        )
        assert resp.status_code == 200
        path = _management_dir(factory_root, project_id) / "roadmap.md"
        assert path.is_file(), f"missing {path}"
        text = path.read_text(encoding="utf-8")
        assert "<!-- management-json:" in text
        assert m["id"] in text  # markdown 引用列表也含

    def test_persistence_survives_reload(
        self, project, factory_root, event_logger
    ):
        """重建 service (同 factory_root) → sprint/milestone/roadmap 仍在。"""
        client, project_id = project
        sprint = _create_sprint(client, project_id)
        m = _create_milestone(client, project_id)
        client.post(
            f"/api/projects/{project_id}/roadmap/milestone-ref",
            json={"milestone_id": m["id"]},
        )
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c2:
            resp = c2.get(f"/api/projects/{project_id}/sprints")
            assert [s["id"] for s in resp.json()["sprints"]] == [sprint["id"]]
            resp = c2.get(f"/api/projects/{project_id}/milestones")
            assert [x["id"] for x in resp.json()["milestones"]] == [m["id"]]
            resp = c2.get(f"/api/projects/{project_id}/roadmap")
            assert resp.json()["milestone_refs"] == [m["id"]]


# ------------------------------------------------------------------ 路由函数 (无 HTTP)


class TestManagementRoutes:
    """路由函数层错误语义 (不经 HTTP): ValueError → 400 面 / None → 404 面。"""

    def test_route_create_sprint_empty_name_valueerror(
        self, factory_root, event_logger
    ):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        summary = service.create_project("测试想法", name="Route Sprint Demo")
        assert summary is not None
        with pytest.raises(ValueError):
            _api.create_sprint(service, summary.id, name="   ")

    def test_route_task_ref_missing_valueerror(self, factory_root, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        summary = service.create_project("测试想法", name="Route Ref Demo")
        with pytest.raises(ValueError):
            _api.create_sprint(
                service, summary.id, name="S", task_refs=["TASK-nope"]
            )

    def test_route_plan_sorts_pure_function(self, factory_root, event_logger):
        """plan 建议走 org.management.sort_tasks 纯函数 (依赖满足+priority)。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        summary = service.create_project("测试想法", name="Route Plan Demo")
        project_id = summary.id
        # 建 2 个任务: 无依赖 P0 (todo) + 依赖它的 P3
        t_a = _api.create_task(service, project_id, title="A", priority="P0")
        assert t_a is not None
        t_b = _api.create_task(
            service, project_id, title="B", priority="P3", dependency=[t_a["id"]]
        )
        assert t_b is not None
        sprint = _api.create_sprint(
            service, project_id, name="S", task_refs=[t_a["id"], t_b["id"]]
        )
        assert sprint is not None
        plan = _api.plan_sprint(service, project_id, sprint["id"], goal="g")
        assert plan is not None
        assert plan["suggestions"][-1]["id"] == t_b["id"]  # 依赖未满足沉底
        assert plan["suggestions"][0]["id"] == t_a["id"]

    def test_route_project_missing_returns_none(self, factory_root, event_logger):
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        assert _api.create_sprint(service, "P-nope", name="S") is None
        assert _api.list_sprints(service, "P-nope") is None
        assert _api.get_sprint(service, "P-nope", "SPRINT-x") is None
        assert _api.update_sprint(service, "P-nope", "SPRINT-x", goal="g") is None
        assert _api.delete_sprint(service, "P-nope", "SPRINT-x") is None
        assert _api.plan_sprint(service, "P-nope", "SPRINT-x") is None
        assert _api.create_milestone(service, "P-nope", name="M") is None
        assert _api.list_milestones(service, "P-nope") is None
        assert _api.get_milestone(service, "P-nope", "MS-x") is None
        assert _api.update_milestone(service, "P-nope", "MS-x", name="m") is None
        assert _api.delete_milestone(service, "P-nope", "MS-x") is None
        assert _api.get_roadmap(service, "P-nope") is None
        assert _api.add_roadmap_milestone_ref(service, "P-nope", "MS-x") is None
