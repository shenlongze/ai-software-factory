"""tests/understanding/test_understanding_models.py — 注册表 + Pydantic 模型 (Phase 7, ADR-0021)。

覆盖: STAGES 10 阶段注册表 (顺序 = 阶段链, 可扩展) / ARTIFACT_KEYS 7 类产物
(与检测器注册表一一对应, 可扩展) / stage_index / StageDetection (归一化 + 非法
阶段拒绝 + confidence 边界) / ArtifactDetection (artifact 清理) / MissingAnalysis /
NextAction (非空校验 + approval_required 默认) / ProjectBasicInfo / 报告 to_dict。
"""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from understanding.models import (
    ARTIFACT_KEYS,
    STAGES,
    ArtifactDetection,
    MissingAnalysis,
    NextAction,
    ProjectBasicInfo,
    ProjectUnderstandingReport,
    StageDetection,
    stage_index,
)


class TestStagesRegistry:
    def test_ten_stages_in_chain_order(self):
        # 阶段链单调推进 (后者蕴含前者), 顺序即链序
        assert STAGES == (
            "IDEA", "RESEARCH", "PRD", "UI_DESIGN", "ARCHITECTURE",
            "DEVELOPMENT", "TESTING", "RELEASE", "PRODUCTION", "OPERATION",
        )

    def test_stage_index_chain_positions(self):
        assert stage_index("IDEA") == 0
        assert stage_index("DEVELOPMENT") == 5
        assert stage_index("OPERATION") == 9

    def test_stage_index_unknown_is_past_end(self):
        # 未知阶段 → len(STAGES) (链比较时视为最新, 不抛错)
        assert stage_index("UNKNOWN") == len(STAGES)

    def test_stages_are_unique_and_upper(self):
        assert len(set(STAGES)) == len(STAGES)
        assert all(s == s.upper() for s in STAGES)


class TestArtifactKeysRegistry:
    def test_seven_artifact_keys(self):
        assert ARTIFACT_KEYS == (
            "PRD", "UI_DESIGN", "ARCHITECTURE", "SOURCE_CODE",
            "TEST", "DEPLOYMENT", "OPERATION",
        )

    def test_artifact_keys_unique(self):
        assert len(set(ARTIFACT_KEYS)) == len(ARTIFACT_KEYS)

    def test_artifact_keys_match_detector_registry(self):
        # 模型注册表与检测器注册表一一对应 (注册化扩展, 集合完整性由测试守住)
        from understanding.analyzers.artifact_detector import ARTIFACT_DETECTORS

        assert set(ARTIFACT_KEYS) == set(ARTIFACT_DETECTORS)


class TestStageDetection:
    def test_defaults(self):
        s = StageDetection()
        assert s.stage == "IDEA"
        assert s.confidence == 0.0
        assert s.evidence == []

    def test_normalizes_stage_case_and_whitespace(self):
        s = StageDetection(stage="  development ", confidence=0.8)
        assert s.stage == "DEVELOPMENT"

    def test_unknown_stage_rejected(self):
        with pytest.raises(ValidationError, match="unknown stage"):
            StageDetection(stage="NOPE")

    def test_non_string_stage_rejected(self):
        with pytest.raises(ValidationError, match="must be a string"):
            StageDetection(stage=123)

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            StageDetection(stage="PRD", confidence=-0.1)
        with pytest.raises(ValidationError):
            StageDetection(stage="PRD", confidence=1.1)
        assert StageDetection(stage="PRD", confidence=1.0).confidence == 1.0

    def test_to_dict(self):
        s = StageDetection(stage="PRD", confidence=0.6, evidence=["evidence:PRD (x)"])
        d = s.to_dict()
        assert d == {"stage": "PRD", "confidence": 0.6, "evidence": ["evidence:PRD (x)"]}


class TestArtifactDetection:
    def test_defaults(self):
        a = ArtifactDetection(artifact="PRD")
        assert a.present is False
        assert a.detail == ""

    def test_artifact_cleaned(self):
        a = ArtifactDetection(artifact="  PRD  ")
        assert a.artifact == "PRD"

    def test_empty_artifact_rejected(self):
        with pytest.raises(ValidationError, match="non-empty"):
            ArtifactDetection(artifact="  ")

    def test_unknown_artifact_key_allowed(self):
        # artifact 不做枚举校验 — 注册化扩展: 新增检测器键即合法
        a = ArtifactDetection(artifact="NEW_ARTIFACT", present=True, detail="x")
        assert a.artifact == "NEW_ARTIFACT"

    def test_to_dict(self):
        a = ArtifactDetection(artifact="TEST", present=True, detail="tests/: a")
        assert a.to_dict() == {"artifact": "TEST", "present": True, "detail": "tests/: a"}


class TestMissingAnalysis:
    def test_empty_defaults(self):
        m = MissingAnalysis()
        assert m.missing == [] and m.present == []

    def test_lists_preserved(self):
        m = MissingAnalysis(missing=["A", "B"], present=["C"])
        assert m.missing == ["A", "B"]
        assert m.present == ["C"]

    def test_to_dict(self):
        m = MissingAnalysis(missing=["PRD"], present=["SOURCE_CODE"])
        assert m.to_dict() == {"missing": ["PRD"], "present": ["SOURCE_CODE"]}


class TestNextAction:
    def test_defaults(self):
        na = NextAction(action="a", reason="r", risk="k")
        assert na.approval_required is False

    def test_approval_flag(self):
        na = NextAction(action="a", reason="r", risk="k", approval_required=True)
        assert na.approval_required is True

    def test_fields_stripped(self):
        na = NextAction(action="  do it  ", reason="  because  ", risk="  low  ")
        assert na.action == "do it"
        assert na.reason == "because"
        assert na.risk == "low"

    def test_empty_action_rejected(self):
        with pytest.raises(ValidationError, match="non-empty"):
            NextAction(action="  ", reason="r", risk="k")

    def test_empty_reason_rejected(self):
        with pytest.raises(ValidationError, match="non-empty"):
            NextAction(action="a", reason="", risk="k")

    def test_empty_risk_rejected(self):
        with pytest.raises(ValidationError, match="non-empty"):
            NextAction(action="a", reason="r", risk="  ")

    def test_to_dict(self):
        na = NextAction(action="a", reason="r", risk="k", approval_required=True)
        assert na.to_dict() == {
            "action": "a", "reason": "r", "risk": "k", "approval_required": True,
        }


class TestProjectBasicInfo:
    def test_defaults(self):
        bi = ProjectBasicInfo()
        assert bi.type == "empty"
        assert bi.scale == "tiny"
        assert bi.status == "empty"
        assert bi.file_count == 0 and bi.dir_count == 0

    def test_scale_thresholds(self):
        from understanding.analyzers.project_analyzer import ProjectAnalyzer

        scale = ProjectAnalyzer._scale
        assert scale(0) == "tiny"
        assert scale(5) == "tiny"
        assert scale(6) == "small"
        assert scale(50) == "small"
        assert scale(51) == "medium"
        assert scale(300) == "medium"
        assert scale(301) == "large"

    def test_to_dict(self):
        bi = ProjectBasicInfo(name="demo", type="application", languages=["python"])
        d = bi.to_dict()
        assert d["name"] == "demo" and d["type"] == "application"
        assert d["languages"] == ["python"]


class TestProjectUnderstandingReport:
    def test_defaults(self):
        r = ProjectUnderstandingReport(path="/tmp/x")
        assert r.path == "/tmp/x"
        assert r.stage.stage == "IDEA"
        assert r.artifacts == []
        assert r.missing.missing == []
        assert r.next_actions == []
        assert r.generated_at  # 非空 UTC 时间戳

    def test_to_dict_shape(self):
        r = ProjectUnderstandingReport(path="/tmp/x")
        d = r.to_dict()
        assert d["path"] == "/tmp/x"
        assert "basic_info" in d and "stage" in d and "artifacts" in d
        assert "missing" in d and "next_actions" in d and "generated_at" in d
        assert isinstance(d["stage"], dict)
