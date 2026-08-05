"""test_manager.py — WorkspaceManager 生命周期 (Phase 6A, ADR-0016)。

覆盖: create/load/add/remove/list/get + 事件 (workspace.created /
project.registered / project.removed) + 错误路径 (已存在/重复/缺失/损坏)
+ 无 workspace 回落自动发现 + 先解析后落盘 (失败不半写)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from events.logger import EventLogger
from events.store import EventStore
from workspace.config import WorkspaceConfigError, WorkspaceNotFoundError
from workspace.loader import managed_projects_dir
from workspace.manager import (
    ProjectExistsError,
    ProjectNotFoundError,
    WorkspaceExistsError,
    WorkspaceManager,
)


@pytest.fixture
def manager(factory_root: Path, examples_dir: Path) -> WorkspaceManager:
    return WorkspaceManager(factory_root, examples_dir=examples_dir)


@pytest.fixture
def logger(tmp_path: Path) -> EventLogger:
    s = EventStore(tmp_path / "events.db")
    yield EventLogger(s)
    s.close()


class TestCreateWorkspace:
    def test_default_name_is_root_name(self, manager, factory_root):
        ws, ev = manager.create_workspace()
        assert ws.name == factory_root.name
        assert ws.id == factory_root.name

    def test_explicit_name(self, manager):
        ws, _ = manager.create_workspace(name="my-workspace")
        assert ws.name == "my-workspace"
        assert ws.version == "1.0.0"

    def test_autodiscover_projects(self, manager):
        ws, _ = manager.create_workspace()
        assert ws.project_ids() == ["markpad", "scorepocket", "timeon"]

    def test_explicit_projects(self, manager):
        ws, _ = manager.create_workspace(projects=["markpad"])
        assert ws.project_ids() == ["markpad"]

    def test_writes_yaml_at_root(self, manager, factory_root):
        manager.create_workspace()
        assert (factory_root / "workspace.yaml").is_file()
        content = (factory_root / "workspace.yaml").read_text(encoding="utf-8")
        assert "markpad" in content and "timeon" in content

    def test_duplicate_raises_exists(self, manager):
        manager.create_workspace()
        with pytest.raises(WorkspaceExistsError):
            manager.create_workspace()

    def test_force_overwrites(self, manager):
        manager.create_workspace(name="first")
        ws, _ = manager.create_workspace(name="second", force=True)
        assert ws.name == "second"

    def test_missing_reference_fails_before_write(self, manager, factory_root):
        with pytest.raises(WorkspaceConfigError):
            manager.create_workspace(projects=["ghost-project"])
        assert not (factory_root / "workspace.yaml").exists()  # 不半写

    def test_emits_workspace_created(self, manager, logger):
        ws, ev = manager.create_workspace(logger=logger)
        assert ev is not None and ev.type.value == "workspace.created"
        assert ev.payload["name"] == ws.name
        assert ev.payload["projects"] == ws.project_ids()

    def test_no_logger_no_event(self, manager):
        ws, ev = manager.create_workspace(logger=None)
        assert ev is None
        assert ws.project_ids()

    def test_definitions_resolved(self, manager):
        ws, _ = manager.create_workspace()
        by_id = {p.id: p for p in ws.projects}
        assert by_id["scorepocket"].runtime_preferences == {"timeout_seconds": 120}
        assert by_id["timeon"].status == "archived"
        assert len(by_id["markpad"].agents) == 3  # 完整装配


class TestLoadWorkspace:
    def test_roundtrip(self, manager):
        manager.create_workspace(name="w")
        ws = manager.load_workspace()
        assert ws.name == "w"
        assert ws.project_ids() == ["markpad", "scorepocket", "timeon"]
        assert ws.root_path == str(manager.root)

    def test_missing_raises_not_found(self, manager):
        with pytest.raises(WorkspaceNotFoundError):
            manager.load_workspace()

    def test_corrupt_yaml_raises_config_error(self, manager, factory_root):
        factory_root.mkdir(parents=True, exist_ok=True)
        (factory_root / "workspace.yaml").write_text("name: [broken\n", encoding="utf-8")
        with pytest.raises(WorkspaceConfigError):
            manager.load_workspace()

    def test_reference_missing_project_raises(self, manager, factory_root):
        factory_root.mkdir(parents=True, exist_ok=True)
        (factory_root / "workspace.yaml").write_text(
            "name: w\nprojects:\n  - ghost\n", encoding="utf-8")
        with pytest.raises(WorkspaceConfigError):
            manager.load_workspace()

    def test_empty_projects_falls_back_to_discovery(self, manager, factory_root):
        manager.create_workspace()
        (factory_root / "workspace.yaml").write_text("name: w\nprojects: []\n", encoding="utf-8")
        ws = manager.load_workspace()
        assert ws.project_ids() == ["markpad", "scorepocket", "timeon"]


class TestListProjects:
    def test_with_workspace_uses_registry(self, manager):
        manager.create_workspace(projects=["markpad", "scorepocket"])
        projects = manager.list_projects()
        assert [p.id for p in projects] == ["markpad", "scorepocket"]

    def test_without_workspace_autodiscovers(self, manager):
        projects = manager.list_projects()
        assert [p.id for p in projects] == ["markpad", "scorepocket", "timeon"]

    def test_without_workspace_falls_back_to_default_examples(self, factory_root):
        # examples_dir 缺省 = 仓库根 examples (FACTORY_EXAMPLES_DIR 可覆盖) → 回落发现
        m = WorkspaceManager(factory_root)
        ids = [p.id for p in m.list_projects()]
        assert "markpad" in ids  # 默认 examples 源

    def test_sorted_by_id(self, manager):
        manager.create_workspace()
        ids = [p.id for p in manager.list_projects()]
        assert ids == sorted(ids)


class TestGetProject:
    def test_from_examples(self, manager):
        p = manager.get_project("markpad")
        assert p is not None and p.language == "dart"

    def test_from_managed_preferred(self, manager, factory_root):
        managed = managed_projects_dir(factory_root)
        (managed / "markpad").mkdir(parents=True)
        (managed / "markpad" / "project.yaml").write_text(
            "name: markpad\nlanguage: managed-override\n", encoding="utf-8")
        p = manager.get_project("markpad")
        assert p.language == "managed-override"

    def test_missing_returns_none(self, manager):
        assert manager.get_project("ghost") is None


class TestAddRemoveProject:
    def test_add_project(self, manager, logger):
        ws, ev = manager.create_workspace(projects=["markpad"])
        ws2, ev2 = manager.add_project("scorepocket", logger=logger)
        assert "scorepocket" in ws2.project_ids()
        assert ev2 is not None and ev2.type.value == "project.registered"
        assert ev2.project_id == "scorepocket"
        assert ev2.payload["language"] == "swift"

    def test_add_duplicate_raises(self, manager):
        manager.create_workspace(projects=["markpad"])
        with pytest.raises(ProjectExistsError):
            manager.add_project("markpad")

    def test_add_missing_project_raises(self, manager):
        manager.create_workspace(projects=[])
        with pytest.raises(WorkspaceConfigError):
            manager.add_project("ghost")

    def test_remove_project(self, manager, logger):
        manager.create_workspace(projects=["markpad", "timeon"])
        ws, ev = manager.remove_project("markpad", logger=logger)
        assert "markpad" not in ws.project_ids()
        assert ev is not None and ev.type.value == "project.removed"
        assert ev.project_id == "markpad"

    def test_remove_missing_raises(self, manager):
        manager.create_workspace(projects=["markpad"])
        with pytest.raises(ProjectNotFoundError):
            manager.remove_project("timeon")

    def test_remove_not_required_by_workspace(self, manager):
        # 移除引用不影响项目文件本身
        manager.create_workspace(projects=["markpad"])
        manager.remove_project("markpad")
        assert manager.get_project("markpad") is not None

    def test_add_remove_persisted(self, manager, logger):
        # 空 projects 列表在 load 时语义 = 自动发现兜底, 故用非空列表验证持久化
        manager.create_workspace(projects=["markpad", "timeon"])
        manager.remove_project("markpad", logger=logger)
        assert manager.load_workspace().project_ids() == ["timeon"]
        manager.add_project("markpad", logger=logger)
        assert manager.load_workspace().project_ids() == ["markpad", "timeon"]


class TestManagerEdgeCases:
    def test_examples_dir_property(self, manager, examples_dir):
        assert manager.examples_dir == examples_dir

    def test_workspace_path_property(self, manager, factory_root):
        assert manager.workspace_path == factory_root / "workspace.yaml"

    def test_create_without_examples(self, factory_root):
        m = WorkspaceManager(factory_root)
        ws, _ = m.create_workspace(projects=[])
        assert ws.project_ids() == []
