"""tests/org/test_management_model.py — S10-010 Task 001: Management Domain Model (TDD)。

覆盖 (org/management.py 实体 + ManagementStore 目录信源 + R1 修复):
- Task 全字段: id/title/description/priority(P0-P3)/status(TODO/READY/IN_PROGRESS/
  BLOCKED/REVIEW/DONE)/assignee/dependency/created_at/updated_at/history
  (list[{time,actor,action,result}] — 审计: 谁什么时候干了什么, PRD 4.6)
- Backlog 层级: Epic→Feature→Story→Task (children 引用, 非包含)
- Sprint: Task-Reference 引用模型 (task_refs 非包含, PRD 4.4/4.5) +
  goal/planning/start_date/end_date/status(planning/active/completed)/
  daily_progress/review
- Milestone: id/name/description/target_date/status/task_refs; Roadmap: milestone_refs
- ManagementStore 目录信源 (project-management-system.md §十):
  workspace/projects/{slug}/management/ 下 backlog/task|epic|feature|story.json +
  sprint/{sprint-id}.json + milestone.json + roadmap.md
  - CRUD: save/get/list/delete + 幂等 (delete 不存在 → False) + 失败安全
    (损坏 JSON → 空/默认, 不抛错) + 懒建 (S10-009 旧项目无 management/ 目录 → 零破坏)
  - Sprint 引用 Task 非包含: task_refs 更新不影响 Task 本身; 删除 Task →
    sprint 引用保留 (引用语义)
- R1 修复 (S10-009 GATE-PASS R1): create_draft_project 同秒两次 → slug 不碰撞
  (slug 含项目 id 片段)

basename 全仓库唯一 (test_org_* 前缀目录约定); 不跨目录依赖 helper。
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core", _ROOT / "factory-org"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# noqa: E402 — sys.path 就绪后导入
from org.management import (  # noqa: E402
    Epic,
    Feature,
    ManagementStore,
    Milestone,
    Roadmap,
    Sprint,
    SprintStatus,
    Story,
    Task,
    TaskPriority,
    TaskStatus,
)

#: factory-console 包名含连字符 → importlib 加载 (同 tests/console 模式;
#: service.py 顶层零 Core 依赖, 延迟导入 — Removal Isolation)
_console_mod = importlib.import_module("factory-console.service")


def _mgmt_dir(tmp_path: Path) -> Path:
    """管理数据空间 (workspace/projects/{slug}/management)。"""
    return tmp_path / "ws" / "projects" / "demo" / "management"


# ------------------------------------------------------------------ 实体模型


class TestTaskModel:
    def test_task_full_fields(self):
        """Task 全字段: id/title/description/priority/status/assignee/dependency/
        created_at/updated_at/history (PRD 4.3/4.6 — 可审计)。"""
        task = Task(
            id="TASK-001",
            title="Implement Login API",
            description="登录接口实现",
            priority="P1",
            status="in_progress",
            assignee="backend-agent",
            dependency=["TASK-000"],
            history=[
                {
                    "time": "2026-08-11T00:00:00Z",
                    "actor": "PM Agent",
                    "action": "create",
                    "result": "OK",
                }
            ],
        )
        assert task.id == "TASK-001"
        assert task.title == "Implement Login API"
        assert task.description == "登录接口实现"
        assert task.priority == TaskPriority.P1
        assert task.status == TaskStatus.IN_PROGRESS
        assert task.assignee == "backend-agent"
        assert task.dependency == ["TASK-000"]
        assert task.created_at is not None
        assert task.updated_at is not None
        assert task.history[0].actor == "PM Agent"
        assert task.history[0].action == "create"
        assert task.history[0].result == "OK"
        # JSON 友好导出含全部字段
        d = task.to_dict()
        assert {
            "id", "title", "description", "priority", "status", "assignee",
            "dependency", "created_at", "updated_at", "history",
        } <= set(d)

    def test_task_defaults(self):
        """默认值: priority=P2, status=TODO, 空列表/空串 (宽容输入 None)。"""
        task = Task(id="TASK-002", title="x", dependency=None, history=None)
        assert task.priority == TaskPriority.P2
        assert task.status == TaskStatus.TODO
        assert task.assignee == ""
        assert task.description == ""
        assert task.dependency == []
        assert task.history == []

    def test_task_priority_enum_values(self):
        """Priority 枚举: P0-P3 (宽容解析大小写不敏感)。"""
        assert TaskPriority.parse("p0") == TaskPriority.P0
        assert TaskPriority.parse("P3") == TaskPriority.P3
        assert [p.value for p in TaskPriority] == ["P0", "P1", "P2", "P3"]

    def test_task_status_enum_values(self):
        """Status 枚举: TODO/READY/IN_PROGRESS/BLOCKED/REVIEW/FAILED/DONE (P1-FIX)。"""
        assert [s.value for s in TaskStatus] == [
            "todo", "ready", "in_progress", "blocked", "review", "failed", "done",
        ]
        assert TaskStatus.parse("READY") == TaskStatus.READY
        assert TaskStatus.parse("DONE") == TaskStatus.DONE

    def test_task_invalid_values_rejected(self):
        """非法 priority/status → ValueError (受控枚举, 不静默)。"""
        with pytest.raises(ValueError):
            Task(id="TASK-003", title="x", priority="P9")
        with pytest.raises(ValueError):
            Task(id="TASK-004", title="x", status="DOING")


class TestBacklogHierarchy:
    def test_epic_feature_story_hierarchy(self):
        """层级: Epic→Feature→Story→Task (children 引用 id, 非包含)。"""
        epic = Epic(id="E-1", name="用户系统", children=["F-1"])
        feature = Feature(id="F-1", name="登录模块", children=["S-1"])
        story = Story(id="S-1", name="用户登录", children=["TASK-001"])
        assert epic.children == ["F-1"]
        assert feature.children == ["S-1"]
        assert story.children == ["TASK-001"]
        for m in (epic, feature, story):
            assert m.name
            assert m.description == ""
            assert m.created_at is not None
            assert m.updated_at is not None
            assert m.children is not None

    def test_hierarchy_defaults(self):
        """默认: description 空串, children 空列表 (None 输入宽容)。"""
        epic = Epic(id="E-2", name="n", children=None)
        assert epic.children == []
        assert epic.description == ""


class TestSprintModel:
    def test_sprint_reference_model(self):
        """Sprint: task_refs 引用 Task (非包含) + goal/planning/progress/review。"""
        sprint = Sprint(
            id="S-1",
            name="Sprint 1",
            goal="完成登录 + 计分核心",
            planning="两周完成 MVP",
            task_refs=["TASK-001", "TASK-002"],
            start_date="2026-08-11",
            end_date="2026-08-24",
            status="planning",
            daily_progress=[{"date": "2026-08-11", "note": "规划完成"}],
            review="待定",
        )
        assert sprint.id == "S-1"
        assert sprint.goal == "完成登录 + 计分核心"
        assert sprint.planning == "两周完成 MVP"
        assert sprint.task_refs == ["TASK-001", "TASK-002"]
        assert sprint.start_date == "2026-08-11"
        assert sprint.end_date == "2026-08-24"
        assert sprint.status == SprintStatus.PLANNING
        assert sprint.daily_progress[0]["note"] == "规划完成"
        assert sprint.review == "待定"

    def test_sprint_status_enum(self):
        """Sprint 状态: planning/active/completed (宽容解析)。"""
        assert [s.value for s in SprintStatus] == [
            "planning", "active", "completed",
        ]
        assert SprintStatus.parse("ACTIVE") == SprintStatus.ACTIVE
        assert SprintStatus.parse("completed") == SprintStatus.COMPLETED
        with pytest.raises(ValueError):
            SprintStatus.parse("done")

    def test_sprint_defaults(self):
        """默认: 空 goal/planning/task_refs/review, planning 状态。"""
        sprint = Sprint(id="S-2", name="Sprint 2")
        assert sprint.goal == ""
        assert sprint.task_refs == []
        assert sprint.status == SprintStatus.PLANNING
        assert sprint.start_date == ""
        assert sprint.end_date == ""
        assert sprint.daily_progress == []
        assert sprint.review == ""


class TestMilestoneRoadmapModel:
    def test_milestone_fields(self):
        """Milestone: id/name/description/target_date/status/task_refs。"""
        ms = Milestone(
            id="M1",
            name="App Store 首发",
            description="首版发布",
            target_date="2026-09-01",
            status="planned",
            task_refs=["TASK-001"],
        )
        assert ms.id == "M1"
        assert ms.name == "App Store 首发"
        assert ms.description == "首版发布"
        assert ms.target_date == "2026-09-01"
        assert ms.status == "planned"
        assert ms.task_refs == ["TASK-001"]

    def test_roadmap_milestone_refs(self):
        """Roadmap: milestone_refs 引用 Milestone (非包含)。"""
        rm = Roadmap(milestone_refs=["M1", "M2"])
        assert rm.id == "roadmap"
        assert rm.milestone_refs == ["M1", "M2"]
        assert rm.updated_at is not None
        assert Roadmap().milestone_refs == []


# ------------------------------------------------------------------ ManagementStore CRUD


class TestManagementStoreFiles:
    def test_lazy_create_dirs_and_files(self, tmp_path: Path):
        """懒建: 未写前 management/ 目录不存在 (S10-009 旧项目兼容);
        首次 save → 目录 + backlog/task.json 生成 (文件按需, 不预建)。"""
        d = _mgmt_dir(tmp_path)
        store = ManagementStore(d)
        assert not d.exists()  # 零破坏: 无 management/ 的旧项目不预建
        store.save_task(Task(id="TASK-1", title="t1"))
        assert d.is_dir()
        assert (d / "backlog" / "task.json").is_file()
        assert not (d / "backlog" / "epic.json").exists()  # 按需懒建

    def test_task_crud_roundtrip(self, tmp_path: Path):
        """Task CRUD: save/get/list/delete + upsert 覆盖 + delete 幂等。"""
        d = _mgmt_dir(tmp_path)
        store = ManagementStore(d)
        assert store.get_task("TASK-1") is None
        assert store.list_tasks() == []
        assert store.delete_task("TASK-1") is False  # 幂等: 不存在 → False
        store.save_task(Task(id="TASK-1", title="t1"))
        store.save_task(Task(id="TASK-2", title="t2"))
        assert [t.id for t in store.list_tasks()] == ["TASK-1", "TASK-2"]
        assert store.get_task("TASK-1").title == "t1"
        # upsert: 同 id 覆盖 (状态流转经 model_copy 后落库)
        store.save_task(Task(id="TASK-1", title="t1-updated"))
        assert len(store.list_tasks()) == 2
        assert store.get_task("TASK-1").title == "t1-updated"
        assert store.delete_task("TASK-2") is True
        assert store.get_task("TASK-2") is None
        assert store.delete_task("TASK-2") is False

    def test_backlog_entities_roundtrip(self, tmp_path: Path):
        """Epic/Feature/Story CRUD (backlog/*.json 各自独立文件)。"""
        d = _mgmt_dir(tmp_path)
        store = ManagementStore(d)
        store.save_epic(Epic(id="E-1", name="用户系统", children=["F-1"]))
        store.save_feature(Feature(id="F-1", name="登录", children=["S-1"]))
        store.save_story(Story(id="S-1", name="登录", children=["TASK-1"]))
        assert (d / "backlog" / "epic.json").is_file()
        assert (d / "backlog" / "feature.json").is_file()
        assert (d / "backlog" / "story.json").is_file()
        assert store.get_epic("E-1").children == ["F-1"]
        assert store.get_feature("F-1").children == ["S-1"]
        assert store.get_story("S-1").children == ["TASK-1"]
        assert [e.id for e in store.list_epics()] == ["E-1"]
        assert store.delete_feature("F-1") is True
        assert store.get_feature("F-1") is None
        assert store.delete_feature("F-1") is False

    def test_sprint_crud_per_file(self, tmp_path: Path):
        """Sprint CRUD: sprint/{sprint-id}.json 每 Sprint 一文件 (信源)。"""
        d = _mgmt_dir(tmp_path)
        store = ManagementStore(d)
        store.save_sprint(Sprint(id="S-1", name="Sprint 1", goal="g1"))
        store.save_sprint(Sprint(id="S-2", name="Sprint 2"))
        assert (d / "sprint" / "S-1.json").is_file()
        assert (d / "sprint" / "S-2.json").is_file()
        assert [s.id for s in store.list_sprints()] == ["S-1", "S-2"]
        assert store.get_sprint("S-1").goal == "g1"
        assert store.delete_sprint("S-2") is True
        assert store.get_sprint("S-2") is None
        assert not (d / "sprint" / "S-2.json").exists()
        assert store.delete_sprint("S-2") is False

    def test_milestone_roadmap_roundtrip(self, tmp_path: Path):
        """Milestone (milestone.json) + Roadmap (roadmap.md) 读写。"""
        d = _mgmt_dir(tmp_path)
        store = ManagementStore(d)
        store.save_milestone(
            Milestone(id="M1", name="App Store 首发", task_refs=["TASK-1"])
        )
        assert (d / "milestone.json").is_file()
        assert store.get_milestone("M1").name == "App Store 首发"
        assert [m.id for m in store.list_milestones()] == ["M1"]
        assert store.delete_milestone("M1") is True
        assert store.get_milestone("M1") is None
        # Roadmap: roadmap.md 为信源, 默认空 (无文件 → 默认实体)
        store.save_roadmap(Roadmap(milestone_refs=["M1"]))
        assert (d / "roadmap.md").is_file()
        assert store.get_roadmap().milestone_refs == ["M1"]
        assert Roadmap().milestone_refs == []


class TestSprintTaskReferenceSemantics:
    def test_sprint_references_task_not_contained(self, tmp_path: Path):
        """Sprint 引用 Task 非包含: task_refs 更新不影响 Task 本身;
        删除 Task → sprint 引用保留 (Task 属 Backlog, Sprint 只是引用 — PRD 4.4)。"""
        d = _mgmt_dir(tmp_path)
        store = ManagementStore(d)
        store.save_task(Task(id="TASK-1", title="t1"))
        store.save_sprint(Sprint(id="S-1", name="S1", task_refs=["TASK-1"]))
        # 更新 sprint 引用 (加 TASK-2) → Task 文件不受影响
        store.save_sprint(
            store.get_sprint("S-1").model_copy(
                update={"task_refs": ["TASK-1", "TASK-2"]}
            )
        )
        assert store.get_task("TASK-1").title == "t1"  # Task 本身未变
        # 删除 Task → sprint 引用保留 (引用语义, 非包含)
        assert store.delete_task("TASK-1") is True
        assert store.get_task("TASK-1") is None
        assert store.get_sprint("S-1").task_refs == ["TASK-1", "TASK-2"]


class TestManagementStoreFailSafe:
    def test_corrupt_json_returns_empty(self, tmp_path: Path):
        """失败安全: 损坏 JSON → get None / list 空 / 不抛错 (目录信源可重建)。"""
        d = _mgmt_dir(tmp_path)
        store = ManagementStore(d)
        store.save_task(Task(id="TASK-1", title="t1"))
        task_json = d / "backlog" / "task.json"
        task_json.write_text("{corrupt json", encoding="utf-8")
        assert store.get_task("TASK-1") is None
        assert store.list_tasks() == []
        # 损坏不阻塞后续 save (覆盖恢复)
        store.save_task(Task(id="TASK-2", title="t2"))
        assert store.get_task("TASK-2").title == "t2"
        # 损坏 sprint 文件 → list 跳过
        (d / "sprint").mkdir(exist_ok=True)
        (d / "sprint" / "S-1.json").write_text("not json", encoding="utf-8")
        assert store.list_sprints() == []
        assert store.get_sprint("S-1") is None
        # 损坏 milestone.json (非 dict 结构) → 空
        (d / "milestone.json").write_text("[1, 2]", encoding="utf-8")
        assert store.list_milestones() == []
        assert store.get_milestone("M1") is None
        # 损坏 roadmap.md (无结构化块) → 默认空 Roadmap
        (d / "roadmap.md").write_text("# Roadmap\nno json block\n", encoding="utf-8")
        assert store.get_roadmap().milestone_refs == []

    def test_no_management_dir_compatible(self, tmp_path: Path):
        """S10-009 旧项目 (无 management/ 目录) → 全空/None, 零破坏不预建。"""
        d = tmp_path / "ws" / "projects" / "legacy" / "management"
        assert not d.exists()
        store = ManagementStore(d)
        assert store.list_tasks() == []
        assert store.get_task("TASK-1") is None
        assert store.list_epics() == []
        assert store.list_features() == []
        assert store.list_stories() == []
        assert store.list_sprints() == []
        assert store.get_sprint("S-1") is None
        assert store.list_milestones() == []
        assert store.get_roadmap().milestone_refs == []
        assert store.delete_task("TASK-1") is False
        assert not d.exists()  # 只读访问不预建目录

    def test_task_history_dependency_audit(self, tmp_path: Path):
        """Task.history 审计链 (谁什么时候干了什么 — PRD 4.6) + dependency。"""
        d = _mgmt_dir(tmp_path)
        store = ManagementStore(d)
        store.save_task(
            Task(
                id="TASK-1",
                title="t",
                dependency=["TASK-0"],
                history=[
                    {"time": "t1", "actor": "PM", "action": "create", "result": "OK"}
                ],
            )
        )
        got = store.get_task("TASK-1")
        assert got.dependency == ["TASK-0"]
        assert got.history[0].time == "t1"
        assert got.history[0].action == "create"
        # 追加历史 (model_copy — 状态流转审计)
        updated = got.model_copy(
            update={
                "history": got.history
                + [
                    {
                        "time": "t2",
                        "actor": "Dev",
                        "action": "start",
                        "result": "RUNNING",
                    }
                ],
            }
        )
        store.save_task(updated)
        history = store.get_task("TASK-1").history
        assert len(history) == 2
        assert history[1].actor == "Dev"
        assert history[1].result == "RUNNING"


# ------------------------------------------------------------------ R1 修复 (S10-009 GATE-PASS R1)


def _console_service(root: Path):
    """轻量装配 ConsoleService (org ProjectStore + ProjectSpaceStore — 同
    build_console_service 的 org 部分; service.py 顶层零 Core 依赖)。"""
    from org.projects import ProjectStore
    from org.space import ProjectSpaceStore

    return _console_mod.ConsoleService(
        project_store=ProjectStore(root / "org"),
        project_space=ProjectSpaceStore(root),
    )


def _space_slug(root: Path, project_id: str) -> str | None:
    from org.space import ProjectSpaceStore

    return ProjectSpaceStore(root).get_slug(project_id)


class TestDraftSlugR1Fix:
    def test_draft_slug_no_collision_same_second(self, tmp_path: Path):
        """R1 修复: create_draft_project 同秒两次 → slug 不碰撞 (秒级时间戳
        相同但 name 含项目 id 片段 → 目录名唯一, get_slug 不再 None)。"""
        root = tmp_path / "factory"
        service = _console_service(root)
        a = service.create_draft_project("想法 A")
        b = service.create_draft_project("想法 B")
        assert a is not None and b is not None
        assert a.id != b.id
        slug_a = _space_slug(root, a.id)
        slug_b = _space_slug(root, b.id)
        assert slug_a is not None and slug_b is not None
        assert slug_a != slug_b  # 同秒创建不碰撞
        assert slug_a.startswith("unnamed-project-")
        assert slug_b.startswith("unnamed-project-")

    def test_draft_slug_contains_id_fragment(self, tmp_path: Path):
        """R1 修复: draft 目录 slug 含项目 id 片段 (防同秒碰撞 — 第二个 slug
        含 id 片段, 建议修复路径: unnamed-project-<ts>-<id 后 8 位>)。"""
        root = tmp_path / "factory"
        service = _console_service(root)
        a = service.create_draft_project("想法 A")
        assert a is not None
        slug_a = _space_slug(root, a.id)
        assert slug_a is not None
        assert a.id[2:] in slug_a  # id 片段 (uuid hex 后 8 位) 进入目录名
        # 第二个 draft 同样含自身 id 片段
        b = service.create_draft_project("想法 B")
        assert b is not None
        slug_b = _space_slug(root, b.id)
        assert slug_b is not None
        assert b.id[2:] in slug_b
