"""test_loader.py — 项目自动发现与 ProjectDefinition 解析 (Phase 6A, ADR-0016)。

覆盖: 项目源解析顺序 (managed 优先, examples 兜底) / 按 project.yaml 存在性
扫描 / 配置损坏明确报错 / ProjectConfig → ProjectDefinition 装配 (id 引用 +
增强字段透传)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from workspace.config import WorkspaceConfigError
from workspace.loader import (
    definition_from_config,
    discover_project_ids,
    discover_projects,
    load_project_definition,
    managed_projects_dir,
    resolve_projects_root,
)

from project.loader import load_project


class TestManagedProjectsDir:
    def test_convention(self, tmp_path):
        assert managed_projects_dir(tmp_path) == tmp_path / "workspace" / "projects"


class TestResolveProjectsRoot:
    def test_managed_preferred_over_examples(self, factory_root, examples_dir):
        # managed 与 examples 同时有 markpad → managed 优先
        managed = managed_projects_dir(factory_root)
        (managed / "markpad").mkdir(parents=True)
        (managed / "markpad" / "project.yaml").write_text(
            (examples_dir / "markpad" / "project.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        assert resolve_projects_root(factory_root, "markpad", examples_dir) == managed

    def test_examples_fallback(self, factory_root, examples_dir):
        assert resolve_projects_root(factory_root, "markpad", examples_dir) == examples_dir

    def test_missing_returns_none(self, factory_root, examples_dir):
        assert resolve_projects_root(factory_root, "nope", examples_dir) is None

    def test_managed_dir_absent(self, factory_root, examples_dir):
        # managed 目录不存在 → 直接回落 examples, 不创建
        assert resolve_projects_root(factory_root, "timeon", examples_dir) == examples_dir


class TestLoadProjectDefinition:
    def test_load_from_examples(self, factory_root, examples_dir):
        d = load_project_definition(factory_root, "markpad", examples_dir)
        assert d is not None
        assert d.id == "markpad"
        assert d.language == "dart"
        assert d.repository == "/Users/Shared/work/markpad"
        assert d.tech_stack == ["flutter", "dart"]

    def test_load_from_managed(self, factory_root, examples_dir):
        managed = managed_projects_dir(factory_root)
        (managed / "custom").mkdir(parents=True)
        (managed / "custom" / "project.yaml").write_text(
            "name: custom\nlanguage: go\n", encoding="utf-8")
        d = load_project_definition(factory_root, "custom", examples_dir)
        assert d is not None
        assert d.language == "go"

    def test_missing_returns_none(self, factory_root, examples_dir):
        assert load_project_definition(factory_root, "nope", examples_dir) is None

    def test_corrupt_project_raises_config_error(self, factory_root, examples_dir):
        (examples_dir / "broken").mkdir(parents=True)
        (examples_dir / "broken" / "project.yaml").write_text("name: [broken\n", encoding="utf-8")
        with pytest.raises(WorkspaceConfigError):
            load_project_definition(factory_root, "broken", examples_dir)


class TestDefinitionFromConfig:
    def test_maps_references(self, factory_root, examples_dir):
        cfg = load_project(examples_dir, "markpad")
        d = definition_from_config(cfg)
        assert d.agents == ["architect", "flutter-developer", "tester"]
        assert set(d.skills) == {"flutter", "dart", "testing", "architecture"}
        assert d.workflows == ["bug-fix", "feature", "release"]

    def _cfg(self, **project_kw):
        from project.models import ProjectConfig, ProjectDef
        return ProjectConfig(project=ProjectDef(name="x", language="go", **project_kw))

    def test_passes_runtime_preferences(self):
        d = definition_from_config(self._cfg(runtime_preferences={"timeout_seconds": 99}))
        assert d.runtime_preferences == {"timeout_seconds": 99}

    def test_passes_status(self):
        d = definition_from_config(self._cfg(status="archived"))
        assert d.status == "archived"

    def test_status_default_active(self):
        d = definition_from_config(self._cfg())
        assert d.status == "active"

    def test_minimal_project_empty_lists(self):
        d = definition_from_config(self._cfg())
        assert d.agents == [] and d.skills == [] and d.workflows == []


class TestDiscoverProjectIds:
    def test_examples_only(self, factory_root, examples_dir):
        ids = discover_project_ids(factory_root, examples_dir)
        assert ids == ["markpad", "scorepocket", "timeon"]

    def test_managed_union_examples_dedup(self, factory_root, examples_dir):
        managed = managed_projects_dir(factory_root)
        (managed / "markpad").mkdir(parents=True)
        (managed / "markpad" / "project.yaml").write_text("name: markpad\n", encoding="utf-8")
        (managed / "local-only").mkdir(parents=True)
        (managed / "local-only" / "project.yaml").write_text("name: local-only\n", encoding="utf-8")
        ids = discover_project_ids(factory_root, examples_dir)
        assert ids == ["local-only", "markpad", "scorepocket", "timeon"]

    def test_empty_when_nothing(self, factory_root, tmp_path):
        # examples_dir 缺省会回落仓库根 examples → 显式传不存在的目录
        assert discover_project_ids(factory_root, tmp_path / "no-examples") == []

    def test_ignores_dirs_without_project_yaml(self, factory_root, examples_dir):
        (examples_dir / "no-project").mkdir(parents=True)
        (examples_dir / "no-project" / "readme.txt").write_text("x", encoding="utf-8")
        assert "no-project" not in discover_project_ids(factory_root, examples_dir)


class TestDiscoverProjects:
    def test_loads_all_sorted(self, factory_root, examples_dir):
        projects = discover_projects(factory_root, examples_dir)
        assert [p.id for p in projects] == ["markpad", "scorepocket", "timeon"]

    def test_scores_sport_definition_fields(self, factory_root, examples_dir):
        projects = discover_projects(factory_root, examples_dir)
        by_id = {p.id: p for p in projects}
        sp = by_id["scorepocket"]
        assert sp.language == "swift"
        assert sp.runtime_preferences == {"timeout_seconds": 120}
        assert sp.status == "active"
        assert by_id["timeon"].status == "archived"

    def test_corrupt_any_project_fails_hard(self, factory_root, examples_dir):
        (examples_dir / "broken").mkdir(parents=True)
        (examples_dir / "broken" / "project.yaml").write_text("name: [broken\n", encoding="utf-8")
        with pytest.raises(WorkspaceConfigError):
            discover_projects(factory_root, examples_dir)

    def test_empty_when_no_sources(self, factory_root, tmp_path):
        assert discover_projects(factory_root, tmp_path / "no-examples") == []

    def test_loads_managed_custom(self, factory_root, examples_dir):
        managed = managed_projects_dir(factory_root)
        (managed / "local-only").mkdir(parents=True)
        (managed / "local-only" / "project.yaml").write_text(
            "name: local-only\nlanguage: rust\n", encoding="utf-8")
        ids = [p.id for p in discover_projects(factory_root, examples_dir)]
        assert ids == ["local-only", "markpad", "scorepocket", "timeon"]
