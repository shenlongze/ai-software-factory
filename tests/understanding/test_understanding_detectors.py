"""tests/understanding/test_understanding_detectors.py — 产物检测器 (Phase 7, ADR-0021)。

覆盖: ArtifactDetector 7 类 code_patterns 检测 / 三态匹配语义 (basename 精确 /
路径前缀 / 子串 / glob) / HIDDEN_DIRS 依赖目录跳过 / detail 上限 8 条 + 计数 /
scan_extensions / scan_manifests (pubspec → flutter) / DocumentAnalyzer 文档类
产物 (doc_patterns) / 注册表可扩展 (注入自定义检测器)。
"""

from __future__ import annotations

from pathlib import Path

from understanding.analyzers.artifact_detector import (
    ARTIFACT_DETECTORS,
    ArtifactDetector,
    ArtifactDetectorDef,
    DOCUMENT_KEYS,
    collect_files,
)
from understanding.analyzers.document_analyzer import DocumentAnalyzer
from understanding.models import ARTIFACT_KEYS

from understanding_helpers import (
    code_project,
    code_test_project,
    empty_project,
    make_project,
    ops_project,
    prd_project,
    prod_project,
    release_project,
    ui_project,
)


class TestCollectFiles:
    def test_empty_dir_no_files(self, tmp_path):
        root = empty_project(tmp_path / "p")
        assert collect_files(root) == []

    def test_hidden_dirs_skipped(self, tmp_path):
        root = make_project(tmp_path / "p", {
            "src/main.py": "x",
            ".git/config": "x",
            "node_modules/pkg/index.js": "x",
            "build/out.o": "x",
            ".venv/lib/a.py": "x",
            ".github/workflows/ci.yml": "x",  # .github 不在 HIDDEN_DIRS — 保留
        })
        rels = [p.as_posix() for p in collect_files(root)]
        assert "src/main.py" in rels
        assert ".github/workflows/ci.yml" in rels
        for hidden in (".git/config", "node_modules/pkg/index.js",
                       "build/out.o", ".venv/lib/a.py"):
            assert hidden not in rels

    def test_sorted_output(self, tmp_path):
        root = make_project(tmp_path / "p", {"b.txt": "1", "a.txt": "2"})
        rels = [p.as_posix() for p in collect_files(root)]
        assert rels == ["a.txt", "b.txt"]


class TestArtifactDetector:
    def test_source_code_via_src_dir(self, tmp_path):
        root = code_project(tmp_path / "p")
        det = ArtifactDetector().detect(root)
        assert det["SOURCE_CODE"].present is True
        assert "src" in det["SOURCE_CODE"].detail

    def test_source_code_via_extension(self, tmp_path):
        root = make_project(tmp_path / "p", {"main.py": "x"})
        det = ArtifactDetector().detect(root)
        assert det["SOURCE_CODE"].present is True

    def test_source_code_via_manifest(self, tmp_path):
        root = make_project(tmp_path / "p", {"pubspec.yaml": "name: app\n"})
        det = ArtifactDetector().detect(root)
        assert det["SOURCE_CODE"].present is True

    def test_test_via_tests_dir(self, tmp_path):
        root = code_test_project(tmp_path / "p")
        det = ArtifactDetector().detect(root)
        assert det["TEST"].present is True

    def test_test_via_singular_test_dir(self, tmp_path):
        # test/ (单数) 目录前缀命中任意深度测试文件
        root = make_project(tmp_path / "p", {"src/a.py": "x", "test/unit/test_a.py": "x"})
        det = ArtifactDetector().detect(root)
        assert det["TEST"].present is True

    def test_deployment_via_dockerfile(self, tmp_path):
        root = prod_project(tmp_path / "p")
        det = ArtifactDetector().detect(root)
        assert det["DEPLOYMENT"].present is True
        assert "dockerfile" in det["DEPLOYMENT"].detail.lower()

    def test_deployment_via_k8s_dir(self, tmp_path):
        root = make_project(tmp_path / "p", {"k8s/deploy.yaml": "x"})
        det = ArtifactDetector().detect(root)
        assert det["DEPLOYMENT"].present is True

    def test_operation_via_ops_dir(self, tmp_path):
        root = ops_project(tmp_path / "p")
        det = ArtifactDetector().detect(root)
        assert det["OPERATION"].present is True

    def test_operation_via_github_workflows(self, tmp_path):
        root = make_project(tmp_path / "p", {
            ".github/workflows/ci.yml": "x",
        })
        det = ArtifactDetector().detect(root)
        assert det["OPERATION"].present is True

    def test_empty_project_nothing_present(self, tmp_path):
        root = empty_project(tmp_path / "p")
        det = ArtifactDetector().detect(root)
        assert all(not d.present for d in det.values())

    def test_detector_keys_cover_code_artifacts(self):
        # code_patterns 非空的键 = SOURCE_CODE/TEST/DEPLOYMENT/OPERATION (4 类)
        code_keys = {k for k, d in ARTIFACT_DETECTORS.items() if d.code_patterns}
        assert code_keys == {"SOURCE_CODE", "TEST", "DEPLOYMENT", "OPERATION"}

    def test_detail_cap_eight_with_count(self, tmp_path):
        files = {f"src/m{i}.py": "x" for i in range(12)}
        root = make_project(tmp_path / "p", files)
        det = ArtifactDetector().detect(root)
        d = det["SOURCE_CODE"].detail
        assert d.count(",") == 7  # 前 8 条路径 (上限)
        assert d.startswith("源码: src/m0.py")

    def test_injectable_registry_extension(self, tmp_path):
        # 注册化扩展: 注入自定义检测器键 → 检测结果含新键 (模型不校验枚举)
        custom = dict(ARTIFACT_DETECTORS)
        custom["LICENSE_CHECK"] = ArtifactDetectorDef(
            key="LICENSE_CHECK", name="license", description="license file",
            code_patterns=("license", "license.txt"),
        )
        root = make_project(tmp_path / "p", {"LICENSE": "MIT\n"})
        det = ArtifactDetector(registry=custom).detect(root)
        assert det["LICENSE_CHECK"].present is True


class TestMatchSemantics:
    """三态匹配: basename 精确 / 路径前缀 (目录) / 路径子串 / glob。"""

    def test_exact_basename_dockerfile(self, tmp_path):
        root = make_project(tmp_path / "p", {"Dockerfile": "x"})
        assert ArtifactDetector().detect(root)["DEPLOYMENT"].present

    def test_prefix_src_dir(self, tmp_path):
        root = make_project(tmp_path / "p", {"src/main.dart": "x"})
        assert ArtifactDetector().detect(root)["SOURCE_CODE"].present

    def test_substring_test_dir(self, tmp_path):
        # "tests/" 子串命中 "tests/unit/test_a.py"
        root = make_project(tmp_path / "p", {"tests/unit/test_a.py": "x"})
        assert ArtifactDetector().detect(root)["TEST"].present

    def test_glob_extension(self, tmp_path):
        root = make_project(tmp_path / "p", {"src/x.py": "x"})
        assert ArtifactDetector().detect(root)["SOURCE_CODE"].present

    def test_case_insensitive(self, tmp_path):
        root = make_project(tmp_path / "p", {"SRC/MAIN.PY": "x"})
        assert ArtifactDetector().detect(root)["SOURCE_CODE"].present


class TestScanExtensions:
    def test_extension_counts(self, tmp_path):
        root = make_project(tmp_path / "p", {
            "a.py": "x", "b.py": "x", "c.dart": "x", "readme.md": "x",
        })
        files = collect_files(root)
        counts = ArtifactDetector.scan_extensions(files)
        assert counts == {"python": 2, "dart": 1}

    def test_empty(self):
        assert ArtifactDetector.scan_extensions([]) == {}


class TestScanManifests:
    def test_pubspec_yields_dart_and_flutter(self, tmp_path):
        root = make_project(tmp_path / "p", {"pubspec.yaml": "name: app\n"})
        stack = ArtifactDetector.scan_manifests(collect_files(root))
        assert "dart" in stack
        assert "flutter" in stack

    def test_package_json_yields_node(self, tmp_path):
        root = make_project(tmp_path / "p", {"package.json": "{}\n"})
        stack = ArtifactDetector.scan_manifests(collect_files(root))
        assert "node" in stack

    def test_empty(self):
        assert ArtifactDetector.scan_manifests([]) == []


class TestDocumentAnalyzer:
    def test_detects_prd(self, tmp_path):
        root = prd_project(tmp_path / "p")
        det = DocumentAnalyzer().detect(root)
        assert det["PRD"].present is True
        assert "prd.md" in det["PRD"].detail

    def test_detects_ui_design(self, tmp_path):
        root = ui_project(tmp_path / "p")
        det = DocumentAnalyzer().detect(root)
        assert det["PRD"].present and det["UI_DESIGN"].present

    def test_detects_architecture(self, tmp_path):
        root = make_project(tmp_path / "p", {"docs/architecture.md": "x"})
        det = DocumentAnalyzer().detect(root)
        assert det["ARCHITECTURE"].present is True

    def test_detects_deployment_doc(self, tmp_path):
        root = make_project(tmp_path / "p", {"docs/deployment.md": "x"})
        det = DocumentAnalyzer().detect(root)
        assert det["DEPLOYMENT"].present is True

    def test_detects_operation_doc(self, tmp_path):
        root = make_project(tmp_path / "p", {"docs/runbook.md": "x"})
        det = DocumentAnalyzer().detect(root)
        assert det["OPERATION"].present is True

    def test_doc_analyzer_only_doc_keys(self, tmp_path):
        # 文档检测器只含 doc_patterns 键 (PRD/UI_DESIGN/ARCHITECTURE/DEPLOYMENT/OPERATION)
        root = code_test_project(tmp_path / "p")  # 只有源码+测试
        det = DocumentAnalyzer().detect(root)
        assert set(det) == {"PRD", "UI_DESIGN", "ARCHITECTURE", "DEPLOYMENT", "OPERATION"}
        assert all(not d.present for d in det.values())

    def test_document_keys_match_doc_patterns(self):
        assert set(DOCUMENT_KEYS) == {
            k for k, d in ARTIFACT_DETECTORS.items() if d.doc_patterns
        }

    def test_doc_and_code_merge_complementary(self, tmp_path):
        # prod_project: Dockerfile 是 code 证据; docs/deployment.md 是 doc 证据 —
        # 两类检测器各自命中, 合并后 present
        root = prod_project(tmp_path / "p")
        doc = DocumentAnalyzer().detect(root)
        code = ArtifactDetector().detect(root)
        keys_present = {k for k in ARTIFACT_KEYS
                        if (doc.get(k) and doc[k].present) or (code.get(k) and code[k].present)}
        assert "DEPLOYMENT" in keys_present
        assert "SOURCE_CODE" in keys_present
        assert "TEST" in keys_present


class TestRegistryCompleteness:
    def test_every_artifact_key_has_detector(self):
        assert set(ARTIFACT_KEYS) == set(ARTIFACT_DETECTORS)

    def test_detector_defs_nonempty_names(self):
        for key, d in ARTIFACT_DETECTORS.items():
            assert d.key == key
            assert d.name and d.description
            assert d.doc_patterns or d.code_patterns
