"""tests/org/test_project_space.py — S10-009 Task 003: Project Space 目录 + Workspace Index。

覆盖 (Task 003: ProjectSpaceStore — workspace/projects/{slug}/ 骨架 + project.json
信源 + workspace index 缓存 + lazy migration + 隔离):
- 目录骨架: ensure_space 初始化完整骨架 (project.json + idea/discovery/product/design/
  architecture/workflow-instance/source/artifacts/knowledge/runtime/logs/management;
  runtime/ 与 logs/ 平级 — 设计 §四: runtime = AI Runtime Data, logs = Audit Data)
- 骨架幂等: 已存在目录重复 ensure_space 不报错/不重复创建/已有内容保留
- project.json 信源: save_project 写 {slug}/project.json (全字段 JSON 可序列化);
  load_project 读回一致 (目录信源优先 — 不依赖 index 缓存)
- workspace index 缓存: rebuild_index 目录扫描生成 id→slug 映射并落盘; 删除 index
  后重新扫描恢复 (场景4); get_slug 缓存缺失自愈重建
- lazy migration: 旧项目 (仅 org/projects.json, 无目录) → migrate_legacy/ensure_space
  回填目录镜像, 幂等 (二次调用 0 迁移; slug 缺省 → name slug 化目录名)
- 隔离: slug 不同 → 独立目录, save/load 互不污染

约束: 零 console/frontend/Core 改动 — 只测 org/space.py (org 层新模块)。

"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from org.projects import Project, ProjectState, ProjectStore
from org.space import ProjectSpaceStore

#: 骨架目录 (project-lifecycle.md §四 + S10-009-plan.md Task 3; runtime/ 与 logs/ 平级)
SKELETON_DIRS: tuple[str, ...] = (
    "idea",
    "discovery",
    "product",
    "design",
    "architecture",
    "workflow-instance",
    "source",
    "artifacts",
    "knowledge",
    "runtime",
    "logs",
    "management",
)


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """工厂根 (workspace/ 与 org/ 平级 — 与 conftest org_dir 同根, 不冲突)。"""
    return tmp_path / "factory"


@pytest.fixture
def space(factory_root: Path) -> ProjectSpaceStore:
    return ProjectSpaceStore(factory_root)


@pytest.fixture
def project_store(factory_root: Path) -> ProjectStore:
    """旧项目载体 (org/projects.json 集中式 — ProjectStore, 非 OrgStore)。"""
    return ProjectStore(factory_root / "org")


def _make_project(
    *,
    project_id: str = "P-1",
    name: str = "ScorePocket",
    slug: str = "scorepocket",
    **kw: object,
) -> Project:
    return Project(id=project_id, name=name, slug=slug, **kw)  # type: ignore[arg-type]


def _rich_project() -> Project:
    """全字段 Project (id/name/slug/lifecycle/draft/discovery/bindings/metadata +
    S9-004 字段) — project.json 信源序列化往返断言。"""
    return Project(
        id="P-9",
        name="ScorePocket",
        user_id="U-1",
        goal="台球计分 App",
        lifecycle=ProjectState.CONFIRMED,
        slug="scorepocket",
        draft=False,
        discovery={"session_id": "DS-1", "status": "completed"},
        bindings={"workflow_instance": {"workflow_ref": "software-development-v1"}},
        metadata={"priority": "high"},
        repo_path="/tmp/scorepocket",
        language="python",
        framework="fastapi",
        build_command="pytest",
        test_command="pytest tests/",
        project_type="app",
    )


def _assert_skeleton(space_dir: Path) -> None:
    """骨架断言: 11 内容目录 + project.json。"""
    assert space_dir.is_dir()
    for name in SKELETON_DIRS:
        assert (space_dir / name).is_dir(), f"missing skeleton dir: {name}"
    assert (space_dir / "project.json").is_file()


class TestSpaceSkeleton:
    """目录骨架创建 + 幂等。"""

    def test_ensure_space_creates_full_skeleton(self, space: ProjectSpaceStore):
        space_dir = space.ensure_space(_make_project())
        assert space_dir == space.projects_dir / "scorepocket"
        _assert_skeleton(space_dir)
        # runtime/ 与 logs/ 平级 (设计 §四: 非嵌套)
        assert (space_dir / "runtime").is_dir()
        assert (space_dir / "logs").is_dir()
        assert not (space_dir / "runtime" / "logs").exists()

    def test_layout_under_workspace_projects(self, space: ProjectSpaceStore):
        space.save_project(_make_project())
        assert space.workspace == space.root / "workspace"
        assert space.projects_dir == space.root / "workspace" / "projects"
        assert (space.root / "workspace" / "projects" / "scorepocket" / "project.json").is_file()
        assert space.index_path == space.root / "workspace" / "projects.json"

    def test_ensure_space_idempotent_keeps_existing_content(self, space: ProjectSpaceStore):
        project = _make_project()
        first = space.ensure_space(project)
        marker = first / "idea" / "idea.md"  # 模拟后续写入的既有产物
        marker.write_text("keep me", encoding="utf-8")
        second = space.ensure_space(project)  # 已存在 → 不报错/不重复创建
        assert second == first
        assert marker.read_text(encoding="utf-8") == "keep me"  # 内容保留
        assert (first / "project.json").is_file()

    def test_ensure_space_writes_mirror_project_json(self, space: ProjectSpaceStore):
        project = _make_project(lifecycle=ProjectState.DISCOVERY, draft=True)
        space_dir = space.ensure_space(project)
        data = json.loads((space_dir / "project.json").read_text(encoding="utf-8"))
        assert data["id"] == "P-1"
        assert data["slug"] == "scorepocket"
        assert data["lifecycle"] == "discovery"
        assert data["draft"] is True


class TestProjectJsonSource:
    """project.json 信源: save_project 写 / load_project 读回 (目录信源优先)。"""

    def test_save_project_writes_all_fields_serializable(self, space: ProjectSpaceStore):
        project = _rich_project()
        space.save_project(project)
        raw = (space.projects_dir / "scorepocket" / "project.json").read_text(encoding="utf-8")
        data = json.loads(raw)  # 全字段 JSON 可序列化 (datetime → ISO)
        assert data == project.to_dict()

    def test_load_project_reads_back_all_fields(self, space: ProjectSpaceStore):
        project = _rich_project()
        space.save_project(project)
        loaded = space.load_project("scorepocket")
        assert loaded is not None
        assert loaded.to_dict() == project.to_dict()  # 全字段读回一致

    def test_load_project_missing_returns_none(self, space: ProjectSpaceStore):
        assert space.load_project("no-such-slug") is None

    def test_load_project_prefers_dir_source_over_index(self, space: ProjectSpaceStore):
        """目录信源优先: 删除 index 缓存后 load_project 仍可读 (不依赖缓存)。"""
        space.save_project(_make_project())
        space.rebuild_index()
        assert space.index_path.exists()
        space.index_path.unlink()  # 删除缓存
        assert space.load_project("scorepocket") is not None  # 信源仍在


class TestWorkspaceIndex:
    """workspace index 缓存 (id→slug 映射; 目录扫描可重建)。"""

    def test_rebuild_index_lists_id_slug_mapping(self, space: ProjectSpaceStore):
        space.save_project(_make_project(project_id="P-1", slug="scorepocket"))
        space.save_project(_make_project(project_id="P-2", name="AI Note", slug="ai-note"))
        index = space.rebuild_index()
        assert index == {"P-1": "scorepocket", "P-2": "ai-note"}
        data = json.loads(space.index_path.read_text(encoding="utf-8"))  # 缓存落盘
        assert data["projects"] == {"P-1": "scorepocket", "P-2": "ai-note"}

    def test_rebuild_recovers_after_index_deleted(self, space: ProjectSpaceStore):
        """场景4: 删除 index 后重新扫描恢复。"""
        space.save_project(_make_project(project_id="P-1", slug="scorepocket"))
        space.rebuild_index()
        assert space.index_path.exists()
        space.index_path.unlink()
        assert not space.index_path.exists()
        index = space.rebuild_index()  # 目录扫描重建
        assert index == {"P-1": "scorepocket"}
        assert space.index_path.exists()

    def test_list_index_empty_when_missing(self, space: ProjectSpaceStore):
        assert space.list_index() == {}

    def test_get_slug_lookup_and_self_heal(self, space: ProjectSpaceStore):
        space.save_project(_make_project(project_id="P-1", slug="scorepocket"))
        # 缓存缺失 (index 未建) → 自愈重建后命中
        assert space.get_slug("P-1") == "scorepocket"
        assert space.get_slug("P-999") is None
        # 删除缓存后再次命中 (重建)
        space.index_path.unlink()
        assert space.get_slug("P-1") == "scorepocket"


class TestLazyMigration:
    """旧项目 (仅 org/projects.json, 无目录) → 回填目录镜像 (幂等)。"""

    def test_migrate_legacy_backfills_mirror(self, space: ProjectSpaceStore, project_store: ProjectStore):
        legacy = Project(
            id="P-old", name="MarkPad", slug="", lifecycle=ProjectState.ACTIVE
        )
        project_store.save_project(legacy)  # 旧项目: 仅 org/projects.json, 无目录
        assert not space.has_space("markpad")
        migrated = space.migrate_legacy(project_store)
        assert migrated == 1
        _assert_skeleton(space.projects_dir / "markpad")
        mirror = json.loads(
            (space.projects_dir / "markpad" / "project.json").read_text(encoding="utf-8")
        )
        assert mirror["id"] == "P-old"
        assert mirror["lifecycle"] == "active"

    def test_migrate_legacy_idempotent(self, space: ProjectSpaceStore, project_store: ProjectStore):
        project_store.save_project(Project(id="P-old", name="MarkPad", slug=""))
        assert space.migrate_legacy(project_store) == 1
        assert space.migrate_legacy(project_store) == 0  # 已回填 → 不再迁移

    def test_ensure_space_backfills_old_project_directly(self, space: ProjectSpaceStore):
        legacy = Project(id="P-old", name="AI Factory", slug="")
        space_dir = space.ensure_space(legacy)  # 懒迁移原语: 首次访问回填
        assert space_dir.name == "ai-factory"  # slug 缺省 → 从 name 派生目录名
        assert (space_dir / "project.json").is_file()
        assert space.has_space("ai-factory")

    def test_migrate_legacy_skips_existing_spaces(self, space: ProjectSpaceStore, project_store: ProjectStore):
        project_store.save_project(Project(id="P-1", name="ScorePocket", slug="scorepocket"))
        space.ensure_space(Project(id="P-1", name="ScorePocket", slug="scorepocket"))
        assert space.migrate_legacy(project_store) == 0  # 已有目录 → 跳过


class TestIsolation:
    """隔离: 每项目独立目录, slug 不同不互相影响。"""

    def test_different_slugs_get_independent_dirs(self, space: ProjectSpaceStore):
        a = space.ensure_space(_make_project(project_id="P-1", slug="scorepocket"))
        b = space.ensure_space(_make_project(project_id="P-2", name="AI Note", slug="ai-note"))
        assert a != b
        assert a.name == "scorepocket"
        assert b.name == "ai-note"
        assert a.parent == b.parent  # 同根 (workspace/projects/) 不同分支

    def test_save_load_do_not_cross_contaminate(self, space: ProjectSpaceStore):
        space.save_project(_make_project(project_id="P-1", name="ScorePocket", slug="scorepocket"))
        space.save_project(_make_project(project_id="P-2", name="AI Note", slug="ai-note"))
        p1 = space.load_project("scorepocket")
        p2 = space.load_project("ai-note")
        assert p1 is not None and p2 is not None
        assert p1.id == "P-1"
        assert p2.id == "P-2"
        # 更新一个不影响另一个
        updated = p1.model_copy(update={"name": "ScorePocket Pro"})
        space.save_project(updated)
        assert space.load_project("ai-note").id == "P-2"  # type: ignore[union-attr]
        assert space.load_project("scorepocket").name == "ScorePocket Pro"  # type: ignore[union-attr]
