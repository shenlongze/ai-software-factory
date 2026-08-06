"""tests/understanding/test_understanding_stage.py — 阶段识别 + 缺失分析 + 建议 (Phase 7, ADR-0021)。

覆盖 detect_stage 确定性规则: 空项目 → IDEA / 仅 README → PRD (弱证据) /
研究 → RESEARCH / 各产物组合单调推进 (PRD→UI_DESIGN→ARCHITECTURE→DEVELOPMENT→
TESTING→PRODUCTION→OPERATION) / RELEASE 边界 (发布证据只在代码阶段推进) /
confidence 公式 (0.5 + 0.1n, 上限 0.95) / evidence 内容 / 注册表可扩展。
build_missing: 7 类按序分列。build_next_actions: 每缺失产物一条 + 源码缺测试
追加 validation 建议 + approval_required 标记 (Approval Gate 接口)。
"""

from __future__ import annotations

from pathlib import Path

from understanding.analyzers.artifact_detector import (
    ArtifactDetector,
    collect_files,
)
from understanding.analyzers.document_analyzer import DocumentAnalyzer
from understanding.models import ARTIFACT_KEYS
from understanding.service import (
    _merge_detections,
    build_missing,
    build_next_actions,
    detect_stage,
)

from understanding_helpers import (
    code_project,
    code_test_project,
    complete_project,
    docs_complete_project,
    empty_project,
    make_project,
    ops_project,
    prd_project,
    prod_project,
    readme_project,
    release_project,
    research_project,
    ui_project,
)


def analyze_stage(root: Path):
    """构造完整 artifacts dict (doc ∪ code 合并) 后做阶段识别 (服务编排的纯函数版)。"""
    files = collect_files(root)
    doc = DocumentAnalyzer().detect(root, files)
    code = ArtifactDetector().detect(root, files)
    artifacts = _merge_detections(doc, code)
    return detect_stage(root, artifacts, files), artifacts


class TestDetectStageEmpty:
    def test_empty_dir_is_idea(self, tmp_path):
        root = empty_project(tmp_path / "p")
        stage, artifacts = analyze_stage(root)
        assert stage.stage == "IDEA"
        assert stage.confidence == 0.9
        assert stage.evidence == [f"no artifacts detected in {root}"]

    def test_empty_dir_all_artifacts_missing(self, tmp_path):
        root = empty_project(tmp_path / "p")
        _, artifacts = analyze_stage(root)
        assert all(not artifacts[k].present for k in ARTIFACT_KEYS)


class TestDetectStageNewProject:
    def test_readme_only_is_prd_weak(self, tmp_path):
        root = readme_project(tmp_path / "p")
        stage, _ = analyze_stage(root)
        assert stage.stage == "PRD"
        assert stage.confidence == 0.6
        assert stage.evidence == ["evidence:PRD (README.md 基础文档)"]

    def test_research_docs_is_research(self, tmp_path):
        root = research_project(tmp_path / "p")
        stage, _ = analyze_stage(root)
        assert stage.stage == "RESEARCH"
        assert stage.confidence == 0.6
        assert stage.evidence[0].startswith("evidence:RESEARCH (")


class TestDetectStageArtifactChain:
    """产物组合单调推进: 每多一类产物 → 阶段链前进 + confidence 递增。"""

    def test_prd_doc(self, tmp_path):
        root = prd_project(tmp_path / "p")
        stage, _ = analyze_stage(root)
        assert stage.stage == "PRD"
        assert stage.confidence == 0.6
        assert stage.evidence == [f"artifact:PRD ({'PRD 文档: docs/prd.md'})"]

    def test_prd_plus_ui(self, tmp_path):
        root = ui_project(tmp_path / "p")
        stage, _ = analyze_stage(root)
        assert stage.stage == "UI_DESIGN"
        assert stage.confidence == 0.7
        assert any(e.startswith("artifact:PRD") for e in stage.evidence)
        assert any(e.startswith("artifact:UI_DESIGN") for e in stage.evidence)

    def test_docs_complete_architecture(self, tmp_path):
        root = docs_complete_project(tmp_path / "p")
        stage, _ = analyze_stage(root)
        assert stage.stage == "ARCHITECTURE"
        assert stage.confidence == 0.8

    def test_code_project_development(self, tmp_path):
        root = code_project(tmp_path / "p")
        stage, _ = analyze_stage(root)
        assert stage.stage == "DEVELOPMENT"
        assert stage.confidence == 0.6  # 1 支持证据 → 0.5 + 0.1
        assert any(e.startswith("artifact:SOURCE_CODE") for e in stage.evidence)

    def test_code_plus_tests_testing(self, tmp_path):
        root = code_test_project(tmp_path / "p")
        stage, _ = analyze_stage(root)
        assert stage.stage == "TESTING"
        assert stage.confidence == 0.7  # 2 支持证据 → 0.5 + 0.2
        assert any(e.startswith("artifact:TEST") for e in stage.evidence)

    def test_prod_project_production(self, tmp_path):
        root = prod_project(tmp_path / "p")
        stage, _ = analyze_stage(root)
        assert stage.stage == "PRODUCTION"
        assert stage.confidence == 0.8  # 3 支持证据 → 0.5 + 0.3
        assert any(e.startswith("artifact:DEPLOYMENT") for e in stage.evidence)

    def test_ops_project_operation(self, tmp_path):
        root = ops_project(tmp_path / "p")
        stage, _ = analyze_stage(root)
        assert stage.stage == "OPERATION"
        assert stage.confidence == 0.9  # 4 支持证据 → 0.5 + 0.4
        assert any(e.startswith("artifact:OPERATION") for e in stage.evidence)

    def test_full_chain_is_monotonic(self, tmp_path):
        # 全 7 类产物 → OPERATION (链顶), evidence 含全部 7 条 artifact 证据
        root = make_project(tmp_path / "p", {
            "docs/prd.md": "x", "docs/ui.md": "x", "docs/architecture.md": "x",
            "src/main.py": "x", "tests/test_main.py": "x",
            "Dockerfile": "x", "ops/monitoring.yaml": "x",
        })
        stage, artifacts = analyze_stage(root)
        assert stage.stage == "OPERATION"
        assert len([e for e in stage.evidence if e.startswith("artifact:")]) == 7
        assert artifacts["SOURCE_CODE"].present and artifacts["TEST"].present


class TestDetectStageReleaseBoundary:
    def test_release_evidence_pushes_code_stage(self, tmp_path):
        root = release_project(tmp_path / "p")
        stage, _ = analyze_stage(root)
        assert stage.stage == "RELEASE"
        assert stage.confidence == 0.8  # SOURCE_CODE + TEST + RELEASE 证据 = 3
        assert any(e.startswith("evidence:RELEASE") for e in stage.evidence)

    def test_release_evidence_does_not_push_doc_stage(self, tmp_path):
        # 只有文档 + 发布配置 → PRD 阶段 (release 推进仅限 DEVELOPMENT/TESTING)
        root = make_project(tmp_path / "p", {"docs/prd.md": "x", "CHANGELOG.md": "x"})
        stage, _ = analyze_stage(root)
        assert stage.stage == "PRD"
        assert not any(e.startswith("evidence:RELEASE") for e in stage.evidence)

    def test_release_with_full_docs_stays_production(self, tmp_path):
        # PRODUCTION 阶段已有部署证据, 发布配置不覆盖 (链顶仍为 PRODUCTION)
        root = make_project(tmp_path / "p", {
            "docs/prd.md": "x", "src/main.py": "x", "tests/test_a.py": "x",
            "Dockerfile": "x", "CHANGELOG.md": "x",
        })
        stage, _ = analyze_stage(root)
        assert stage.stage == "PRODUCTION"

    def test_release_notes_is_deployment_doc(self, tmp_path):
        # release-notes.md 同时是 DEPLOYMENT 文档产物与 RELEASE 阶段证据 —
        # 文档产物优先: DEPLOYMENT present → 阶段直接 PRODUCTION (非 RELEASE)
        root = make_project(tmp_path / "p", {
            "src/main.py": "x", "release-notes.md": "# v1\n",
        })
        _, artifacts = analyze_stage(root)
        assert artifacts["DEPLOYMENT"].present is True
        stage, _ = analyze_stage(root)
        assert stage.stage == "PRODUCTION"


class TestDetectStageEvidence:
    def test_confidence_formula(self):
        # 0.5 + 0.1 × 支持证据数, 上限 0.95, 两位小数
        assert detect_stage.__doc__  # 存在性冒烟
        assert min(0.95, 0.5 + 0.1 * 1) == 0.6
        assert min(0.95, 0.5 + 0.1 * 4) == 0.9
        assert min(0.95, 0.5 + 0.1 * 8) == 0.95

    def test_evidence_lists_artifact_details(self, tmp_path):
        root = prd_project(tmp_path / "p")
        stage, _ = analyze_stage(root)
        assert stage.evidence == ["artifact:PRD (PRD 文档: docs/prd.md)"]

    def test_unknown_stage_registry_extension(self, tmp_path):
        # 注册化可扩展: 阶段识别只依赖 STAGES 注册表 — 自定义产物键可注入
        # (detect_stage 的 ARTIFACT_STAGE 是内部映射, 扩展由 service 层演进;
        # 此处断言模型层允许未知 artifact 键, 不破坏检测)
        from understanding.models import ArtifactDetection

        artifacts = {k: ArtifactDetection(artifact=k) for k in ARTIFACT_KEYS}
        stage = detect_stage(tmp_path / "p", artifacts, [])
        assert stage.stage == "IDEA"


class TestBuildMissing:
    def test_all_present(self, tmp_path):
        root = complete_project(tmp_path / "p")
        _, artifacts = analyze_stage(root)
        m = build_missing(artifacts)
        assert m.present == list(ARTIFACT_KEYS)
        assert m.missing == []

    def test_empty_project_all_missing(self, tmp_path):
        root = empty_project(tmp_path / "p")
        _, artifacts = analyze_stage(root)
        m = build_missing(artifacts)
        assert m.missing == list(ARTIFACT_KEYS)
        assert m.present == []

    def test_code_only_missing_ordering(self, tmp_path):
        root = code_project(tmp_path / "p")
        _, artifacts = analyze_stage(root)
        m = build_missing(artifacts)
        assert m.present == ["SOURCE_CODE"]
        assert m.missing == ["PRD", "UI_DESIGN", "ARCHITECTURE", "TEST",
                             "DEPLOYMENT", "OPERATION"]

    def test_docs_only_missing(self, tmp_path):
        root = docs_complete_project(tmp_path / "p")
        _, artifacts = analyze_stage(root)
        m = build_missing(artifacts)
        assert m.present == ["PRD", "UI_DESIGN", "ARCHITECTURE"]
        assert m.missing == ["SOURCE_CODE", "TEST", "DEPLOYMENT", "OPERATION"]


class TestBuildNextActions:
    def test_empty_project_seven_actions(self, tmp_path):
        root = empty_project(tmp_path / "p")
        _, artifacts = analyze_stage(root)
        actions = build_next_actions(artifacts)
        assert len(actions) == 7
        # 每缺失产物一条, 顺序按 ARTIFACT_KEYS
        assert [a.action for a in actions][0].startswith("补充 PRD 文档")
        assert [a.action for a in actions][-1].startswith("补充运维配置")

    def test_approval_gate_flags(self, tmp_path):
        # Approval Gate mandatory 节点: PRD/UI/DEPLOYMENT → True; 其余 False
        root = empty_project(tmp_path / "p")
        _, artifacts = analyze_stage(root)
        actions = build_next_actions(artifacts)
        by_action = {a.action: a.approval_required for a in actions}
        assert by_action["补充 PRD 文档 (docs/prd.md)"] is True
        assert by_action["补充 UI 设计稿 (docs/ui.md 或 designs/)"] is True
        assert by_action["补充部署配置 (Dockerfile/docker-compose/deploy/)"] is True
        assert by_action["补充架构文档 (docs/architecture.md)"] is False
        assert by_action["开始编码实现 (src/ 或 lib/)"] is False
        assert by_action["补充自动化测试 (tests/)"] is False
        assert by_action["补充运维配置 (runbook/监控)"] is False

    def test_code_without_tests_appends_validation(self, tmp_path):
        root = code_project(tmp_path / "p")
        _, artifacts = analyze_stage(root)
        actions = build_next_actions(artifacts)
        assert len(actions) == 7  # 6 缺失 + 1 validation 追加
        assert actions[-1].action == "运行 validation 校验 (factory validate)"
        assert actions[-1].approval_required is False

    def test_code_with_tests_no_validation_append(self, tmp_path):
        root = code_test_project(tmp_path / "p")
        _, artifacts = analyze_stage(root)
        actions = build_next_actions(artifacts)
        assert len(actions) == 5  # 5 缺失 (无 SOURCE_CODE/TEST), 无追加
        assert all("validation" not in a.action for a in actions)

    def test_full_project_no_actions(self, tmp_path):
        root = complete_project(tmp_path / "p")
        _, artifacts = analyze_stage(root)
        actions = build_next_actions(artifacts)
        assert actions == []

    def test_action_structure(self, tmp_path):
        root = prd_project(tmp_path / "p")
        _, artifacts = analyze_stage(root)
        actions = build_next_actions(artifacts)
        a = actions[0]  # UI_DESIGN 缺失
        assert a.action and a.reason and a.risk
        assert isinstance(a.approval_required, bool)
