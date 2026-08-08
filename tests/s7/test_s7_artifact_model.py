"""tests/s7/test_s7_artifact_model.py — S7-002 Artifact 完整模型 (Unit, ADR-0039)。

覆盖 (任务清单: Artifact 完整模型 + 向后兼容):
- 完整模型默认值: id/project_id/stage_id/task_id/type/producer_role/
  producer_agent/version/status/location/metadata 全字段
- 向后兼容: S7-001 基础字段 dict (无新增字段) 加载零破坏; 既有
  artifacts.json (S7-001 格式) 经 ProjectStore 加载零破坏
- 状态枚举宽容解析 (大小写不敏感/非法响亮失败); metadata None → {}
- to_dict JSON 友好 (datetime → ISO); extra=forbid 严格字段
- 受控转换表 ARTIFACT_TRANSITIONS: 形状/主链可达/终态/失败恢复

依赖: 本目录 conftest 已挂 factory-core + factory-org + factory-exec。
"""

from __future__ import annotations

import json

import pytest

from org.projects import (
    ARTIFACT_TRANSITIONS,
    Artifact,
    ArtifactStatus,
    ArtifactType,
)

from s7_helpers import make_artifact_full


class TestArtifactFullModel:
    def test_full_model_defaults(self):
        a = Artifact(id="A-1", stage_id="STG-1", type="prd")
        assert a.id == "A-1"
        assert a.stage_id == "STG-1"
        assert a.type == ArtifactType.PRD
        assert a.project_id == ""
        assert a.task_id == ""
        assert a.producer_role == ""
        assert a.producer_agent == ""
        assert a.version == "1"
        assert a.status == ArtifactStatus.CREATED
        assert a.location == ""
        assert a.metadata == {}
        assert a.ref == ""
        assert a.archived_at is None
        assert a.invalid_reason == ""
        assert not a.is_archived

    def test_full_model_all_fields(self):
        a = make_artifact_full(
            artifact_id="A-1",
            stage_id="STG-1",
            type_="release",
            project_id="P-1",
            task_id="T-1",
            ref="ref://rel",
            producer_role="tester",
            producer_agent="ag-1",
            version="2.1.0",
            status="validated",
            location="file:///dist",
            metadata={"version": "2.1.0", "notes": "n", "artifact_ref": "A-2"},
        )
        assert a.project_id == "P-1"
        assert a.task_id == "T-1"
        assert a.type == ArtifactType.RELEASE
        assert a.status == ArtifactStatus.VALIDATED
        assert a.version == "2.1.0"

    def test_s7001_minimal_dict_loads(self):
        """S7-001 基础字段 dict (无新增字段) 加载零破坏 (向后兼容)。"""
        a = Artifact.model_validate(
            {"id": "A-1", "stage_id": "STG-1", "type": "code", "ref": "file:///x"}
        )
        assert a.type == ArtifactType.CODE
        assert a.status == ArtifactStatus.CREATED
        assert a.version == "1"
        assert a.project_id == ""

    def test_old_artifacts_json_file_loads(self, project_store, org_dir):
        """既有 artifacts.json (S7-001 格式) 经 ProjectStore 加载零破坏。"""
        org_dir.mkdir(parents=True, exist_ok=True)
        (org_dir / "artifacts.json").write_text(
            json.dumps(
                {
                    "artifacts": {
                        "A-1": {
                            "id": "A-1",
                            "stage_id": "STG-1",
                            "type": "prd",
                            "ref": "ref://req",
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        a = project_store.get_artifact("A-1")
        assert a is not None
        assert a.type == ArtifactType.PRD
        assert a.status == ArtifactStatus.CREATED

    def test_status_parse_tolerant(self):
        assert ArtifactStatus.parse("VALIDATED") == ArtifactStatus.VALIDATED
        assert ArtifactStatus.parse(" invalid ") == ArtifactStatus.INVALID
        assert ArtifactStatus.parse(ArtifactStatus.CONSUMED) == ArtifactStatus.CONSUMED
        with pytest.raises(ValueError, match="invalid artifact status"):
            ArtifactStatus.parse("bogus")

    def test_type_parse_rejects_unknown(self):
        with pytest.raises(ValueError, match="invalid artifact type"):
            ArtifactType.parse("bogus")

    def test_metadata_none_normalized(self):
        a = Artifact(id="A-1", stage_id="STG-1", type="prd", metadata=None)
        assert a.metadata == {}

    def test_to_dict_json_safe(self):
        a = make_artifact_full(
            artifact_id="A-1",
            stage_id="STG-1",
            type_="test",
            metadata={"results": {"passed": 3}, "bugs": []},
        )
        d = a.to_dict()
        assert d["type"] == "test"
        assert d["status"] == "created"
        assert d["version"] == "1"
        assert d["metadata"] == {"results": {"passed": 3}, "bugs": []}
        assert isinstance(d["created_at"], str)
        assert "T" in d["created_at"]  # datetime → ISO 字符串

    def test_extra_field_forbidden(self):
        with pytest.raises(ValueError):
            Artifact(id="A-1", stage_id="STG-1", type="prd", bogus=1)

    def test_status_roundtrip_through_store(self, project_store):
        project_store.save_artifact(
            make_artifact_full(
                artifact_id="A-1", stage_id="STG-1", type_="code",
                status="consumed", version="2",
            )
        )
        a = project_store.get_artifact("A-1")
        assert a.status == ArtifactStatus.CONSUMED
        assert a.version == "2"

    def test_is_archived_property(self):
        assert make_artifact_full(
            artifact_id="A-1", stage_id="STG-1", type_="prd", status="archived"
        ).is_archived
        assert not make_artifact_full(
            artifact_id="A-1", stage_id="STG-1", type_="prd", status="created"
        ).is_archived


class TestArtifactTransitionsTable:
    def test_table_shape(self):
        """受控转换表声明 (S7-002: 主链 + 失败路径 + 终态)。"""
        assert ARTIFACT_TRANSITIONS == {
            "created": ("generated", "invalid"),
            "generated": ("validated", "invalid"),
            "validated": ("consumed", "archived", "invalid"),
            "consumed": ("archived", "invalid"),
            "invalid": ("generated", "archived"),
            "archived": (),
        }

    def test_main_chain_reachable(self):
        """主链可达: created→generated→validated→consumed→archived。"""
        state = "created"
        for nxt in ("generated", "validated", "consumed", "archived"):
            assert nxt in ARTIFACT_TRANSITIONS[state]
            state = nxt

    def test_archived_terminal(self):
        assert ARTIFACT_TRANSITIONS["archived"] == ()

    def test_created_cannot_archive_directly(self):
        """CREATED 不能直接 ARCHIVED (受控, 任务硬性要求)。"""
        assert "archived" not in ARTIFACT_TRANSITIONS["created"]

    def test_invalid_recovery_paths(self):
        """失败恢复: invalid → generated (重生成) / archived (废弃)。"""
        assert ARTIFACT_TRANSITIONS["invalid"] == ("generated", "archived")

    def test_every_state_has_entry(self):
        """枚举与转换表同源: 每个状态都有转换条目 (防遗漏)。"""
        for s in ArtifactStatus:
            assert s.value in ARTIFACT_TRANSITIONS
