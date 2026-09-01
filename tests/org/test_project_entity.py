"""tests/org/test_project_entity.py — Project Entity 扩展 (S10-009 Task 001)。

覆盖 (Task 001: 状态机 9 新态 + 字段扩展 + 转换表扩展):
- ProjectState: DRAFT/DISCOVERY/PRODUCT_DEFINED/DESIGN/ARCHITECTURE/CONFIRMED/
  DEVELOPMENT/RELEASE/MAINTAIN (9 新成员) + IDEA/ACTIVE/MAINTAINED/ARCHIVED
  (4 旧成员兼容, project-lifecycle.md §2)
- ProjectState.parse: 旧值 (idea/active/maintained/archived) 大小写不敏感宽容解析
- Project 新字段默认值: slug="" / draft=False / discovery=None / bindings=None /
  metadata={} — 旧 projects.json 数据 (无新字段) 加载零破坏
- PROJECT_TRANSITIONS: 新主链 draft→discovery→product_defined→design→architecture→
  confirmed→development→release→maintain→archived; 各态可→archived; 旧值
  (idea→active 等) 保留
- 转换表合法性: 无非法目标 / archived 终态 / 单向无环

约束: 零 console/frontend/Core 改动 — 本文件只测 org/projects.py 实体层。
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from org.projects import (
    PROJECT_TRANSITIONS,
    Project,
    ProjectState,
)


def _old_project_dict() -> dict:
    """S10-009 之前的旧 projects.json 记录 (无新字段, 模拟 ledger-app/markpad 数据)。"""
    return {
        "id": "P-1",
        "name": "MarkPad",
        "user_id": "U-1",
        "goal": "AI 笔记软件",
        "lifecycle": "active",
        "repo_path": "/repos/markpad",
        "language": "python",
        "framework": "",
        "build_command": "",
        "test_command": "",
        "project_type": "app",
        "analysis_ref": "",
        "baseline_ref": "",
        "snapshot_ref": "",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


class TestProjectStateMembers:
    """ProjectState 枚举: 9 新成员 + 4 旧成员兼容。"""

    def test_new_members_exist(self):
        for member in (
            ProjectState.DRAFT,
            ProjectState.DISCOVERY,
            ProjectState.PRODUCT_DEFINED,
            ProjectState.DESIGN,
            ProjectState.ARCHITECTURE,
            ProjectState.CONFIRMED,
            ProjectState.DEVELOPMENT,
            ProjectState.RELEASE,
            ProjectState.MAINTAIN,
        ):
            assert isinstance(member, ProjectState)

    def test_new_members_values(self):
        assert ProjectState.DRAFT.value == "draft"
        assert ProjectState.DISCOVERY.value == "discovery"
        assert ProjectState.PRODUCT_DEFINED.value == "product_defined"
        assert ProjectState.DESIGN.value == "design"
        assert ProjectState.ARCHITECTURE.value == "architecture"
        assert ProjectState.CONFIRMED.value == "confirmed"
        assert ProjectState.DEVELOPMENT.value == "development"
        assert ProjectState.RELEASE.value == "release"
        assert ProjectState.MAINTAIN.value == "maintain"

    def test_old_members_preserved(self):
        assert ProjectState.IDEA.value == "idea"
        assert ProjectState.ACTIVE.value == "active"
        assert ProjectState.MAINTAINED.value == "maintained"
        assert ProjectState.ARCHIVED.value == "archived"

    def test_total_members_count(self):
        # 9 新 + 4 旧 = 13
        assert len(list(ProjectState)) == 13


class TestProjectStateParse:
    """ProjectState.parse 宽容解析 (新值 + 旧值大小写不敏感)。"""

    def test_parse_new_values(self):
        assert ProjectState.parse("draft") is ProjectState.DRAFT
        assert ProjectState.parse("product_defined") is ProjectState.PRODUCT_DEFINED
        assert ProjectState.parse("architecture") is ProjectState.ARCHITECTURE
        assert ProjectState.parse("maintain") is ProjectState.MAINTAIN

    def test_parse_old_values_case_insensitive(self):
        assert ProjectState.parse("idea") is ProjectState.IDEA
        assert ProjectState.parse("IDEA") is ProjectState.IDEA
        assert ProjectState.parse("Active") is ProjectState.ACTIVE
        assert ProjectState.parse("MAINTAINED") is ProjectState.MAINTAINED
        assert ProjectState.parse("Archived") is ProjectState.ARCHIVED

    def test_parse_enum_object_identity(self):
        assert ProjectState.parse(ProjectState.DRAFT) is ProjectState.DRAFT
        assert ProjectState.parse(ProjectState.ARCHIVED) is ProjectState.ARCHIVED

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError) as exc_info:
            ProjectState.parse("bogus")
        assert "invalid project lifecycle" in str(exc_info.value)


class TestProjectModelDefaults:
    """Project 新字段默认值 (零破坏 — 旧数据加载正常)。"""

    def test_new_field_defaults(self):
        p = Project(id="P-1", name="x")
        assert p.slug == ""
        assert p.draft is False
        assert p.discovery is None
        assert p.bindings is None
        assert p.metadata == {}
        assert p.lifecycle == ProjectState.IDEA  # 既有默认不变

    def test_old_data_loads_zero_break(self):
        """旧 projects.json 记录 (无新字段) → model_validate 加载成功, 新字段落默认。"""
        p = Project.model_validate(_old_project_dict())
        assert p.id == "P-1"
        assert p.name == "MarkPad"
        assert p.lifecycle == ProjectState.ACTIVE
        assert p.slug == ""
        assert p.draft is False
        assert p.discovery is None
        assert p.bindings is None
        assert p.metadata == {}

    def test_old_json_file_loads_via_store(self, org_dir):
        """真实存储路径: 旧 projects.json 文件 → ProjectStore.get_project 零破坏。"""
        from org.projects import ProjectStore

        path = org_dir / "projects.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"projects": {"P-1": _old_project_dict()}}),
            encoding="utf-8",
        )
        store = ProjectStore(org_dir)
        loaded = store.get_project("P-1")
        assert loaded is not None
        assert loaded.name == "MarkPad"
        assert loaded.lifecycle == ProjectState.ACTIVE
        assert loaded.slug == ""
        assert loaded.draft is False
        assert loaded.discovery is None
        assert loaded.bindings is None
        assert loaded.metadata == {}

    def test_new_fields_settable(self):
        """新字段可显式写入 (预留扩展, 类型宽容: discovery/bindings 为 dict)。"""
        p = Project(
            id="P-2",
            name="ScorePocket",
            slug="scorepocket",
            draft=True,
            discovery={"session_id": "DS-1", "status": "active"},
            bindings={"workflow_ref": "software-development-v1"},
            metadata={"source": "draft"},
        )
        assert p.slug == "scorepocket"
        assert p.draft is True
        assert p.discovery == {"session_id": "DS-1", "status": "active"}
        assert p.bindings == {"workflow_ref": "software-development-v1"}
        assert p.metadata == {"source": "draft"}

    def test_metadata_none_normalized(self):
        p = Project(id="P-3", name="x", metadata=None)
        assert p.metadata == {}

    def test_to_dict_json_friendly(self):
        p = Project(id="P-1", name="x")
        d = p.to_dict()
        assert d["slug"] == ""
        assert d["draft"] is False
        assert d["discovery"] is None
        assert d["bindings"] is None
        assert d["metadata"] == {}

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            Project(id="P-1", name="x", bogus=1)


class TestProjectTransitions:
    """PROJECT_TRANSITIONS 扩展: 新主链 + 旧值保留 + 合法性 (无非法目标/终态/单向)。"""

    def test_transitions_table_matches_design(self):
        assert PROJECT_TRANSITIONS == {
            "draft": ("discovery", "archived"),
            "discovery": ("product_defined", "archived"),
            "product_defined": ("design", "archived"),
            "design": ("architecture", "archived"),
            "architecture": ("confirmed", "archived"),
            "confirmed": ("development", "archived"),
            "development": ("release", "archived"),
            "release": ("maintain", "archived"),
            "maintain": ("archived",),
            "idea": ("confirmed", "active", "archived"),  # 旧值兼容; confirmed=任务拆解完成 (S35-P0)
            "active": ("maintained", "archived"),  # 旧值兼容
            "maintained": ("archived",),           # 旧值兼容
            "archived": (),
        }

    def test_old_values_preserved(self):
        assert "active" in PROJECT_TRANSITIONS["idea"]
        assert "maintained" in PROJECT_TRANSITIONS["active"]
        assert PROJECT_TRANSITIONS["maintained"] == ("archived",)

    def test_archived_is_terminal(self):
        assert PROJECT_TRANSITIONS["archived"] == ()

    def test_every_state_has_entry(self):
        for state in ProjectState:
            assert state.value in PROJECT_TRANSITIONS

    def test_no_illegal_targets(self):
        """转换表合法性: 每个目标值都是合法 ProjectState (无非法目标)。"""
        valid = {s.value for s in ProjectState}
        for _src, targets in PROJECT_TRANSITIONS.items():
            for target in targets:
                assert target in valid, f"illegal target: {target}"

    def test_single_direction_acyclic(self):
        """转换表合法性: 单向 — 反向边不存在 (主链无环)。"""
        forward: set[tuple[str, str]] = set()
        for src, targets in PROJECT_TRANSITIONS.items():
            for target in targets:
                forward.add((src, target))
        for src, target in forward:
            assert (target, src) not in forward, (
                f"reverse edge exists: {target} → {src}"
            )

    def test_main_chain_flows(self):
        """主链依次可达: draft→discovery→product_defined→design→architecture→
        confirmed→development→release→maintain→archived。"""
        chain = [
            "draft",
            "discovery",
            "product_defined",
            "design",
            "architecture",
            "confirmed",
            "development",
            "release",
            "maintain",
            "archived",
        ]
        for src, dst in zip(chain, chain[1:]):
            assert dst in PROJECT_TRANSITIONS[src], (
                f"missing edge: {src} → {dst}"
            )
