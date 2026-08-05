"""test_config.py — workspace.yaml 配置模型与读写 (Phase 6A, ADR-0016)。

覆盖: 格式约定 (name/version/projects) / 缺省值 / 引用列表去重保序 /
损坏配置明确报错 (绝不静默返回空) / 稳定 dump (人工审计与 git 差异)。
"""

from __future__ import annotations

import pytest

from workspace.config import (
    WORKSPACE_FILENAME,
    WorkspaceConfig,
    WorkspaceConfigError,
    WorkspaceNotFoundError,
    dump_config,
    load_config,
)


class TestWorkspaceConfigModel:
    def test_defaults(self):
        c = WorkspaceConfig(name="w")
        assert c.name == "w"
        assert c.version == "1.0.0"
        assert c.projects == []

    def test_name_required(self):
        with pytest.raises(Exception):
            WorkspaceConfig(name="")

    def test_projects_dedupe_keep_order(self):
        c = WorkspaceConfig(name="w", projects=["b", "a", "b", "a"])
        assert c.projects == ["b", "a"]

    def test_projects_filter_blank(self):
        c = WorkspaceConfig(name="w", projects=["markpad", "", "  ", "timeon"])
        assert c.projects == ["markpad", "timeon"]

    def test_to_dict(self):
        c = WorkspaceConfig(name="w", projects=["markpad"])
        assert c.to_dict() == {"name": "w", "version": "1.0.0", "projects": ["markpad"]}


class TestDumpConfig:
    def test_full(self):
        c = WorkspaceConfig(name="my-workspace", projects=["markpad", "scorepocket"])
        assert dump_config(c) == (
            "name: my-workspace\nversion: 1.0.0\nprojects:\n  - markpad\n  - scorepocket\n"
        )

    def test_empty_projects(self):
        assert dump_config(WorkspaceConfig(name="w")) == (
            "name: w\nversion: 1.0.0\nprojects: []\n"
        )

    def test_roundtrip(self, tmp_path):
        p = tmp_path / "workspace.yaml"
        p.write_text(dump_config(WorkspaceConfig(name="w", projects=["markpad"])), encoding="utf-8")
        c = load_config(p)
        assert c.name == "w"
        assert c.projects == ["markpad"]


class TestLoadConfig:
    def test_load_valid(self, tmp_path):
        p = tmp_path / "workspace.yaml"
        p.write_text("name: w\nversion: 1.0.0\nprojects:\n  - markpad\n", encoding="utf-8")
        c = load_config(p)
        assert c.name == "w"
        assert c.version == "1.0.0"
        assert c.projects == ["markpad"]

    def test_missing_raises_not_found(self, tmp_path):
        with pytest.raises(WorkspaceNotFoundError):
            load_config(tmp_path / "nope.yaml")

    def test_invalid_yaml_raises_config_error(self, tmp_path):
        p = tmp_path / "workspace.yaml"
        p.write_text("name: [unclosed\n", encoding="utf-8")
        with pytest.raises(WorkspaceConfigError):
            load_config(p)

    def test_non_mapping_raises_config_error(self, tmp_path):
        p = tmp_path / "workspace.yaml"
        p.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(WorkspaceConfigError):
            load_config(p)

    def test_bad_name_raises_config_error(self, tmp_path):
        p = tmp_path / "workspace.yaml"
        p.write_text("name: ''\n", encoding="utf-8")
        with pytest.raises(WorkspaceConfigError):
            load_config(p)

    def test_missing_version_defaults(self, tmp_path):
        p = tmp_path / "workspace.yaml"
        p.write_text("name: w\n", encoding="utf-8")
        assert load_config(p).version == "1.0.0"

    def test_missing_projects_defaults_empty(self, tmp_path):
        p = tmp_path / "workspace.yaml"
        p.write_text("name: w\n", encoding="utf-8")
        assert load_config(p).projects == []

    def test_filename_constant(self):
        assert WORKSPACE_FILENAME == "workspace.yaml"
