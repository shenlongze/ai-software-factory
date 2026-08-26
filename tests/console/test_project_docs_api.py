"""tests/console/test_project_docs_api.py — 项目文档管理 API (v1.1.108)。

覆盖 (fastapi_adapter + session/board.read_project_doc_content):
- GET /api/projects/{id}/docs — 文档清单 (核心资产 PRD.md/工程计划 + 目录扫描)
- GET /api/projects/{id}/docs/{doc} — md/json/txt 内容; 越界路径 → 404;
  不支持类型/缺失 → 诚实 note
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


@pytest.fixture
def http_app(tmp_path):
    pdir = tmp_path / "projects" / "p-docs"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "PRD.md").write_text("# 需求文档\n\n- 功能A\n- 功能B", encoding="utf-8")
    (pdir / "engineering.json").write_text(json.dumps({"stages": 3}), encoding="utf-8")
    docs = pdir / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "guide.md").write_text("## 使用指南", encoding="utf-8")
    (pdir / "binary.docx").write_bytes(b"PK\x03\x04fake")
    service = _adapter.build_console_service(tmp_path, event_logger=None)
    app = _adapter.build_app(service, event_logger=None, factory_root=tmp_path)
    with TestClient(app) as c:
        yield c


@requires_fastapi
class TestProjectDocs:
    def test_list_includes_core_and_scanned(self, http_app):
        client = http_app
        r = client.get("/api/projects/p-docs/docs")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        names = {d["name"] for d in items}
        assert "PRD.md" in names
        assert "engineering.json" in names
        assert "docs/guide.md" in names  # 目录扫描
        prd = next(d for d in items if d["name"] == "PRD.md")
        assert prd["label"] == "需求文档"
        assert prd["kind"] == "md"

    def test_read_markdown_content(self, http_app):
        client = http_app
        r = client.get("/api/projects/p-docs/docs/PRD.md")
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "md"
        assert "功能A" in body["content"]
        assert body["label"] == "需求文档"

    def test_read_json_content(self, http_app):
        client = http_app
        r = client.get("/api/projects/p-docs/docs/engineering.json")
        assert r.status_code == 200
        assert "stages" in r.json()["content"]

    def test_read_nested_doc(self, http_app):
        client = http_app
        r = client.get("/api/projects/p-docs/docs/docs/guide.md")
        assert r.status_code == 200
        assert "使用指南" in r.json()["content"]

    def test_path_traversal_blocked(self, http_app, tmp_path):
        # HTTP 层: 越界路径不返回文档内容 (路由不匹配 405/404 均可 — 安全已拦)
        client = http_app
        r = client.get("/api/projects/p-docs/docs/../../providers.json")
        assert r.status_code in (404, 405)
        # 单元层: read_project_doc_content 直接拦越界 (路径安全核心)
        board = importlib.import_module("factory-console.session.board")
        res = board.read_project_doc_content(tmp_path, "p-docs", "../../providers.json")
        assert res.get("error") == "unsupported-path"
        # 绝对路径 / .git 也拦
        assert board.read_project_doc_content(tmp_path, "p-docs", str(tmp_path / "providers.json")).get("error") == "unsupported-path"

    def test_unsupported_type_honest_note(self, http_app):
        client = http_app
        r = client.get("/api/projects/p-docs/docs/binary.docx")
        assert r.status_code == 200
        assert r.json()["content"] is None
        assert "暂不支持在线预览" in r.json()["note"]

    def test_missing_doc_honest_note(self, http_app):
        client = http_app
        r = client.get("/api/projects/p-docs/docs/NOPE.md")
        assert r.status_code == 200
        assert r.json()["content"] is None
        assert r.json()["note"] == "未生成"
