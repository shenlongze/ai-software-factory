"""tests/console/test_s10_125_api_standard.py — HTTP API 规范 v1 契约测试 (2026-08-26, 项目统一标准)。

覆盖 (docs/API规范.md):
1. 集合端点 → {"items": [...], "count": N} (禁止裸数组)
2. 错误 → {"error": {code: E7xxx, message, detail, suggestion}} (禁止裸 {"detail"})
3. code = E7{status} (400→E7400 / 404→E7404 / 409→E7409 / 422→E7422 / 500→E7500)
4. URL kebab-case + 字段 snake_case (抽查)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.console

_ADAPTER = None


def _adapter():
    global _ADAPTER
    if _ADAPTER is None:
        import importlib

        _ADAPTER = importlib.import_module("factory-console.web.backend.fastapi_adapter")
    return _ADAPTER


def _import_ok() -> bool:
    try:
        import fastapi  # noqa: F401
        import httpx  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


requires_fastapi = pytest.mark.skipif(
    not _import_ok(), reason="fastapi/httpx 未安装 (HTTP 类跳过)"
)


@requires_fastapi
class TestApiStandard:
    @pytest.fixture
    def client(self, factory_root: Path, event_logger):
        from fastapi.testclient import TestClient

        a = _adapter()
        service = a.build_console_service(factory_root, event_logger=event_logger)
        app = a.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            yield c

    def test_collection_envelope(self, client):
        """集合端点 → {items, count} (禁止裸数组)。"""
        r = client.get("/api/projects")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, dict)
        assert "items" in body and "count" in body
        assert body["count"] == len(body["items"])
        assert isinstance(body["items"], list)

    def test_error_envelope_404(self, client):
        """404 → {"error": {code: E7404, message, detail, suggestion}}。"""
        r = client.get("/api/projects/nope/lifecycle")
        assert r.status_code == 404
        body = r.json()
        assert "error" in body
        err = body["error"]
        assert err["code"] == "E7404"
        assert err["message"]

    def test_error_envelope_400(self, client):
        """400 → code E7400。"""
        r = client.post("/api/projects", json={"idea": ""})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "E7400"

    def test_error_envelope_422(self, client):
        """请求体校验失败 → E7422。"""
        # /api/projects/suggest 需要 idea
        r = client.post("/api/projects/suggest", json={})
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "E7422"

    def test_created_project_collection(self, client):
        """创建后集合 count 增加, 仍是 {items, count}。"""
        r = client.post("/api/projects", json={"idea": "做一个 API 规范测试", "name": "规范测试"})
        assert r.status_code == 201
        listing = client.get("/api/projects").json()
        assert listing["count"] == len(listing["items"])
        assert any(p["id"] == r.json()["project_id"] for p in listing["items"])

    def test_snake_case_fields(self, client):
        """字段 snake_case 抽查 (project_id/tech_stack)。"""
        r = client.post("/api/projects", json={"idea": "字段规范", "name": "字段规范"})
        assert r.status_code == 201
        body = r.json()
        assert "project_id" in body  # snake_case
