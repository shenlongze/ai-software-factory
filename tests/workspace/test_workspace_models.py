"""test_models.py — Workspace / ProjectDefinition 领域模型 (Phase 6A, ADR-0016)。

覆盖: 默认值 / id 引用键校验 / status 归一化 / 增强字段 (runtime_preferences) /
查询辅助 (project_ids/get) / JSON 序列化。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from workspace.models import ProjectDefinition, Workspace


class TestProjectDefinition:
    def test_defaults(self):
        p = ProjectDefinition(id="markpad")
        assert p.id == "markpad"
        assert p.name == ""            # 显示名缺省空 (由装配层填 = id)
        assert p.description == ""
        assert p.language == ""
        assert p.repository == ""
        assert p.tech_stack == []
        assert p.agents == []
        assert p.skills == []
        assert p.workflows == []
        assert p.runtime_preferences == {}
        assert p.status == "active"

    def test_full_definition(self):
        p = ProjectDefinition(
            id="scorepocket", name="ScorePocket", description="本地记分板",
            language="swift", repository="/tmp/scorepocket",
            tech_stack=["swift", "ios"], agents=["A-001"], skills=["swift"],
            workflows=["feature"], runtime_preferences={"timeout_seconds": 120},
            status="active",
        )
        assert p.name == "ScorePocket"
        assert p.runtime_preferences["timeout_seconds"] == 120
        assert p.tech_stack == ["swift", "ios"]

    def test_id_rejects_path_separator(self):
        with pytest.raises(ValidationError):
            ProjectDefinition(id="a/b")

    def test_id_rejects_backslash(self):
        with pytest.raises(ValidationError):
            ProjectDefinition(id="a\\b")

    def test_id_rejects_dot_dot(self):
        with pytest.raises(ValidationError):
            ProjectDefinition(id="..")

    def test_id_rejects_empty(self):
        with pytest.raises(ValidationError):
            ProjectDefinition(id="  ")

    def test_id_strips_whitespace(self):
        p = ProjectDefinition(id="  markpad  ")
        assert p.id == "markpad"

    def test_name_strips_whitespace(self):
        p = ProjectDefinition(id="x", name="  MarkPad  ")
        assert p.name == "MarkPad"

    def test_status_normalized_lower(self):
        assert ProjectDefinition(id="x", status="ARCHIVED").status == "archived"

    def test_status_empty_falls_back_active(self):
        assert ProjectDefinition(id="x", status="  ").status == "active"

    def test_to_dict_json_friendly(self):
        p = ProjectDefinition(id="markpad", runtime_preferences={"t": 1})
        d = p.to_dict()
        assert d["id"] == "markpad"
        assert d["status"] == "active"
        assert d["runtime_preferences"] == {"t": 1}
        assert isinstance(d, dict)


class TestWorkspace:
    def test_defaults(self):
        ws = Workspace()
        assert ws.id == "workspace"
        assert ws.name == "workspace"
        assert ws.version == "1.0.0"
        assert ws.root_path == ""
        assert ws.projects == []

    def test_name_required_nonempty(self):
        with pytest.raises(ValidationError):
            Workspace(name="   ")

    def test_id_rejects_slash(self):
        with pytest.raises(ValidationError):
            Workspace(id="a/b")

    def test_projects_roundtrip(self):
        ws = Workspace(
            name="my-factory", root_path="/tmp/f",
            projects=[
                ProjectDefinition(id="timeon"),
                ProjectDefinition(id="markpad"),
                ProjectDefinition(id="scorepocket"),
            ],
        )
        assert ws.project_ids() == ["timeon", "markpad", "scorepocket"]

    def test_project_ids_sorted(self):
        ws = Workspace(projects=[
            ProjectDefinition(id="timeon"),
            ProjectDefinition(id="markpad"),
        ])
        assert ws.project_ids() == ["timeon", "markpad"]  # 保持定义序 (装配层已排序)

    def test_get_found(self):
        ws = Workspace(projects=[ProjectDefinition(id="markpad")])
        assert ws.get("markpad") is not None
        assert ws.get("markpad").id == "markpad"

    def test_get_missing_returns_none(self):
        ws = Workspace(projects=[ProjectDefinition(id="markpad")])
        assert ws.get("nope") is None

    def test_get_empty_workspace(self):
        assert Workspace().get("markpad") is None

    def test_to_dict_includes_nested_projects(self):
        ws = Workspace(name="w", projects=[ProjectDefinition(id="markpad", status="active")])
        d = ws.to_dict()
        assert d["name"] == "w"
        assert d["projects"][0]["id"] == "markpad"
        assert d["projects"][0]["status"] == "active"

    def test_to_dict_json_serializable(self):
        import json
        ws = Workspace(name="w", root_path="/tmp/f")
        json.dumps(ws.to_dict())  # 不抛
