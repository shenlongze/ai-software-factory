"""tests/console/test_artifact_contract.py — 产出物契约 C-1 (Manifest + 历史 + 追溯)。

覆盖 (factory-console/artifact_contract.py + GET /api/projects/{id}/artifacts):
- set_artifact: 写当前 + manifest entry (producer/trace_id) + 项目版本 bump
- 历史不丢: 第二次写 → 旧版归档 history/, versions 链完整, get_artifact_version 可读
- scan_project: manifest 视图 (存在/缺失/版本链/格式)
- validate_project / validate_all: missing/history-missing/no-version/drift 如实
- HTTP: GET artifacts (manifest 视图) + versions/{v} (历史内容)
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

_ac = importlib.import_module("factory-console.artifact_contract")
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")

try:
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except Exception:  # noqa: BLE001
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装 (console 侧 venv 需安装)"
)


class TestContract:
    def test_set_artifact_writes_manifest_and_bumps(self, tmp_path):
        root = tmp_path
        (root / "projects" / "p1").mkdir(parents=True, exist_ok=True)
        entry = _ac.set_artifact(root, "p1", "product", {"name": "记账"}, producer="pipeline", trace_id="t-1")
        assert entry["version"] == 1
        assert entry["producer"] == "pipeline"
        assert entry["trace_id"] == "t-1"
        assert entry["file"] == "product.json"
        # 项目版本信号
        scan = _ac.scan_project(root, "p1")
        assert scan["meta"]["version"] == 1
        # 文件真实落盘
        assert json.loads((root / "projects" / "p1" / "product.json").read_text(encoding="utf-8"))["name"] == "记账"

    def test_history_preserved_on_update(self, tmp_path):
        root = tmp_path
        (root / "projects" / "p1").mkdir(parents=True, exist_ok=True)
        _ac.set_artifact(root, "p1", "prd", None, raw_text="# 需求 v1", producer="pipeline")
        e2 = _ac.set_artifact(root, "p1", "prd", None, raw_text="# 需求 v2", producer="change-control", trace_id="t-2")
        assert e2["version"] == 2
        # 当前 = v2
        assert (root / "projects" / "p1" / "PRD.md").read_text(encoding="utf-8") == "# 需求 v2"
        # 历史 v1 归档 (不丢)
        hist = root / "projects" / "p1" / "history" / "PRD.v1.md"
        assert hist.is_file()
        assert hist.read_text(encoding="utf-8") == "# 需求 v1"
        # 版本链完整 + 可追溯
        entry = _ac.read_manifest(root, "p1")["artifacts"]["prd"]
        versions = {v["version"]: v for v in entry["versions"]}
        assert set(versions) == {1, 2}
        assert versions[2]["trace_id"] == "t-2"

    def test_get_artifact_version_reads_history(self, tmp_path):
        root = tmp_path
        (root / "projects" / "p1").mkdir(parents=True, exist_ok=True)
        _ac.set_artifact(root, "p1", "product", {"name": "v1"})
        _ac.set_artifact(root, "p1", "product", {"name": "v2"})
        v1 = _ac.get_artifact_version(root, "p1", "product", 1)
        v2 = _ac.get_artifact_version(root, "p1", "product", 2)
        assert json.loads(v1["content"])["name"] == "v1"
        assert json.loads(v2["content"])["name"] == "v2"
        assert v1["file"].startswith("history/")
        assert v2["file"] == "product.json"
        assert _ac.get_artifact_version(root, "p1", "product", 99) is None

    def test_unknown_type_raises(self, tmp_path):
        with pytest.raises(ValueError):
            _ac.set_artifact(tmp_path, "p1", "bogus", {})

    def test_scan_lists_produced_and_missing(self, tmp_path):
        root = tmp_path
        (root / "projects" / "p1").mkdir(parents=True, exist_ok=True)
        _ac.set_artifact(root, "p1", "prd", None, raw_text="# x")
        (root / "projects" / "p1" / "readme.md").write_text("# r", encoding="utf-8")  # 漂移
        scan = _ac.scan_project(root, "p1")
        by_type = {i["type"]: i for i in scan["items"]}
        assert by_type["prd"]["exists"] is True
        assert by_type["prd"]["version"] == 1
        assert by_type["product"]["exists"] is False  # 默认约定未产出 → 如实缺失
        assert "readme.md" in scan["drift"]
        assert scan["meta"]["version"] == 1

    def test_validate_reports_missing_and_no_version(self, tmp_path):
        root = tmp_path
        (root / "projects" / "p1").mkdir(parents=True, exist_ok=True)
        v = _ac.validate_project(root, "p1")
        assert v["ok"] is False
        issues = {p["issue"] for p in v["problems"]}
        assert "missing" in issues
        assert "no-version" in issues

    def test_validate_all_scans_every_project(self, tmp_path):
        root = tmp_path
        (root / "projects" / "p1").mkdir(parents=True, exist_ok=True)
        (root / "projects" / "p2").mkdir(parents=True, exist_ok=True)
        _ac.set_artifact(root, "p1", "product", {"name": "x"})
        report = _ac.validate_all(root)
        assert {p["project_id"] for p in report["projects"]} == {"p1", "p2"}


@requires_fastapi
class TestArtifactsHttp:
    def test_get_artifacts_manifest_view(self, tmp_path):
        (tmp_path / "projects" / "p1").mkdir(parents=True, exist_ok=True)
        _ac.set_artifact(tmp_path, "p1", "product", {"name": "记账"}, producer="cli")
        service = _adapter.build_console_service(tmp_path, event_logger=None)
        app = _adapter.build_app(service, event_logger=None, factory_root=tmp_path)
        with TestClient(app) as c:
            r = c.get("/api/projects/p1/artifacts")
            assert r.status_code == 200
            body = r.json()
            assert body["meta"]["version"] == 1
            by_type = {i["type"]: i for i in body["items"]}
            assert by_type["product"]["exists"] is True
            assert by_type["product"]["producer"] == "cli"
            assert by_type["tasks"]["exists"] is False

    def test_get_artifact_version_history(self, tmp_path):
        (tmp_path / "projects" / "p1").mkdir(parents=True, exist_ok=True)
        _ac.set_artifact(tmp_path, "p1", "prd", None, raw_text="# v1")
        _ac.set_artifact(tmp_path, "p1", "prd", None, raw_text="# v2")
        service = _adapter.build_console_service(tmp_path, event_logger=None)
        app = _adapter.build_app(service, event_logger=None, factory_root=tmp_path)
        with TestClient(app) as c:
            r = c.get("/api/projects/p1/artifacts/prd/versions/1")
            assert r.status_code == 200
            assert "# v1" in r.json()["content"]
            assert c.get("/api/projects/p1/artifacts/prd/versions/99").status_code == 404
