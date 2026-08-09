"""tests/s9/test_s9_004_registration.py — Project Registration + CONTRACTS
(org 侧单元, S9-004)。

覆盖:
- Project 模型: 新字段默认值 (向后兼容 — 旧数据零破坏) / 字段赋值与落库
- CONTRACTS: project_analysis / baseline 契约校验 (合法 + 缺失两路径)
- ArtifactType: 新类型宽容解析
- ProjectAdoption 失败安全: repo_path 非目录 → ValueError; exec 不可用 →
  注册仍成功 (全链 unavailable 记录)

依赖: 本目录 conftest (sys.path 挂 factory-core + factory-org + factory-exec);
logger=None 全静默 (事件断言在集成文件)。exec 不可用路径经 monkeypatch
(org.project_adoption._load_exec_adoption → None — Removal Isolation 语义)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from org.artifact import ArtifactType, validate_artifact
from org.project_adoption import (
    BaselineRecord,
    ContextSnapshotRecord,
    ProjectAdoption,
    ProjectAdoptionStore,
    ProjectAnalysisRecord,
    _analysis_unavailable_payload,
)
from org.projects import Project, ProjectStore

from s9_helpers import (
    analysis_payload_ok,
    baseline_payload_ok,
    make_python_repo,
)


# ------------------------------------------------------------ Project 模型


def test_project_model_defaults_backward_compat():
    """旧数据 (无 S9-004 字段) → 默认值加载, 零破坏 (向后兼容)。"""
    project = Project(id="P-old", name="Legacy")
    assert project.repo_path == ""
    assert project.language == ""
    assert project.framework == ""
    assert project.build_command == ""
    assert project.test_command == ""
    assert project.project_type == ""
    assert project.analysis_ref == ""
    assert project.baseline_ref == ""
    assert project.snapshot_ref == ""


def test_project_model_adoption_fields_roundtrip(project_store: ProjectStore):
    """S9-004 字段赋值 → 落库 → 读回一致 (ProjectStore 持久化)。"""
    project = Project(
        id="P-adopt",
        name="Adopted",
        repo_path="/tmp/existing-app",
        language="dart",
        framework="flutter",
        build_command="dart pub get",
        test_command="dart test",
        project_type="app",
        analysis_ref="PA-1",
        baseline_ref="BL-1",
        snapshot_ref="CS-1",
    )
    project_store.save_project(project)
    loaded = project_store.get_project("P-adopt")
    assert loaded is not None
    assert loaded.language == "dart"
    assert loaded.framework == "flutter"
    assert loaded.build_command == "dart pub get"
    assert loaded.test_command == "dart test"
    assert loaded.project_type == "app"
    assert loaded.analysis_ref == "PA-1"
    assert loaded.baseline_ref == "BL-1"
    assert loaded.snapshot_ref == "CS-1"


def test_project_store_old_json_zero_break(tmp_path: Path):
    """既有 projects.json (旧字段) 文件 → ProjectStore 读回零破坏。"""
    org_dir = tmp_path / "org"
    org_dir.mkdir(parents=True)
    (org_dir / "projects.json").write_text(
        '{"projects": {"P-9": {"id": "P-9", "name": "Old App", '
        '"lifecycle": "active"}}}',
        encoding="utf-8",
    )
    store = ProjectStore(org_dir)
    loaded = store.get_project("P-9")
    assert loaded is not None
    assert loaded.name == "Old App"
    assert loaded.language == ""  # 新字段默认值
    assert loaded.lifecycle.value == "active"


# ------------------------------------------------------------ CONTRACTS


def test_contract_project_analysis_valid():
    """合法 project_analysis 载荷 → ok (契约与 exec 载荷同源)。"""
    result = validate_artifact(ArtifactType.PROJECT_ANALYSIS, analysis_payload_ok())
    assert result.ok is True
    assert result.missing == []


def test_contract_project_analysis_missing_fields():
    """缺 language/structure → 校验失败 (missing 列出)。"""
    result = validate_artifact(
        ArtifactType.PROJECT_ANALYSIS, {"framework": "", "test_method": "pytest"}
    )
    assert result.ok is False
    assert "language" in result.missing
    assert "structure" in result.missing


def test_contract_project_analysis_bad_rule():
    """structure 非 list → errors (规则失败)。"""
    result = validate_artifact(
        ArtifactType.PROJECT_ANALYSIS,
        {**analysis_payload_ok(), "structure": "not-a-list"},
    )
    assert result.ok is False
    assert any("structure" in e for e in result.errors)


def test_contract_baseline_valid():
    """合法 baseline 载荷 → ok。"""
    result = validate_artifact(ArtifactType.BASELINE, baseline_payload_ok())
    assert result.ok is True


def test_contract_baseline_missing_build_keys():
    """build 缺 status/command → errors (required_keys)。"""
    result = validate_artifact(
        ArtifactType.BASELINE,
        {
            "build": {"output_head": "x"},
            "test": {"status": "passed", "passed": 2, "failed": 0},
            "analysis_ref": "PA-1",
        },
    )
    assert result.ok is False
    assert any("build" in e for e in result.errors)


def test_contract_baseline_missing_analysis_ref():
    """缺 analysis_ref 字段 → missing。"""
    payload = baseline_payload_ok()
    del payload["analysis_ref"]
    result = validate_artifact(ArtifactType.BASELINE, payload)
    assert result.ok is False
    assert "analysis_ref" in result.missing


def test_artifact_type_parse_new_types():
    """新类型宽容解析 (大小写不敏感) + 旧类型不受影响。"""
    assert ArtifactType.parse("project_analysis") == ArtifactType.PROJECT_ANALYSIS
    assert ArtifactType.parse("PROJECT_ANALYSIS") == ArtifactType.PROJECT_ANALYSIS
    assert ArtifactType.parse("baseline") == ArtifactType.BASELINE
    assert ArtifactType.parse("release") == ArtifactType.RELEASE


# ------------------------------------------------------------ 记录模型


def test_analysis_record_roundtrip(tmp_path: Path):
    """分析记录落库/读回 (ProjectAdoptionStore 数据空间)。"""
    store = ProjectAdoptionStore(tmp_path / "org")
    record = ProjectAnalysisRecord(
        id="PA-1", project_id="P-1", payload=analysis_payload_ok()
    )
    store.save_analysis(record)
    loaded = store.get_analysis("PA-1")
    assert loaded is not None
    assert loaded.payload["language"] == "python"
    assert loaded.valid is True
    assert store.files() == [tmp_path / "org" / "project_analyses.json"]


def test_baseline_and_snapshot_records(tmp_path: Path):
    """基线 + 快照记录落库/读回 (三文件数据空间并存)。"""
    store = ProjectAdoptionStore(tmp_path / "org")
    store.save_baseline(
        BaselineRecord(id="BL-1", project_id="P-1", payload=baseline_payload_ok())
    )
    store.save_snapshot(
        ContextSnapshotRecord(
            id="CS-1", project_id="P-1", payload={"tree": [], "tree_entries": 0}
        )
    )
    assert store.get_baseline("BL-1").payload["test"]["passed"] == 2
    assert store.get_snapshot("CS-1").payload["tree_entries"] == 0
    assert len(store.files()) == 2


# ------------------------------------------------------------ 注册失败安全


def test_register_repo_path_missing_raises(project_store: ProjectStore):
    """repo_path 非目录 → ValueError (响亮失败, 不静默)。"""
    adoption = ProjectAdoption(project_store, logger=None)
    with pytest.raises(ValueError, match="not a directory"):
        adoption.register("/nonexistent/repo/xyz")


def test_register_exec_unavailable_failure_safe(
    project_store: ProjectStore, monkeypatch: pytest.MonkeyPatch
):
    """exec 不可用 → 注册仍成功; 分析/基线/快照记录 unavailable (Removal
    Isolation 语义 — org 侧零硬依赖)。"""
    import org.project_adoption as pa_mod

    monkeypatch.setattr(pa_mod, "_load_exec_adoption", lambda: None)
    adoption = ProjectAdoption(project_store, logger=None)
    project = adoption.register(
        str(make_python_repo(project_store.dir.parent, name="s9_004_noexec"))
    )
    assert project.language == "unknown"
    assert project.analysis_ref
    assert project.baseline_ref
    assert project.snapshot_ref
    analysis = adoption.get_analysis(project.analysis_ref)
    assert analysis is not None
    assert analysis.payload["build_method"] == "unavailable"
    assert "exec not installed" in analysis.errors[0]
    baseline = adoption.get_baseline(project.baseline_ref)
    assert baseline is not None
    assert baseline.payload["build"]["status"] == "unavailable"
    assert baseline.payload["test"]["status"] == "unavailable"
    snapshot = adoption.get_snapshot(project.snapshot_ref)
    assert snapshot is not None
    assert snapshot.payload["tree_entries"] == 0


def test_analysis_unavailable_payload_contract_shape():
    """不可用分析载荷 → 契约形状合法 (validate_artifact ok — 不崩溃)。"""
    payload = _analysis_unavailable_payload("exec not installed")
    result = validate_artifact(ArtifactType.PROJECT_ANALYSIS, payload)
    assert result.ok is True
    assert payload["language"] == "unknown"
    assert payload["build_method"] == "unavailable"
