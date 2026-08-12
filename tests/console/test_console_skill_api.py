"""
tests/console/test_console_skill_api.py — S10-019 Skill API 端到端。

Service 层 (list_skills/agent_skills) + API 层 (GET /api/skills +
GET /api/agents/{agent_id}/skills) — 真实装配 TestClient。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_FACTORY_EXEC = _ROOT / "factory-exec"
if str(_FACTORY_EXEC) not in sys.path:
    sys.path.insert(0, str(_FACTORY_EXEC))

#: factory-console 包名含连字符 → importlib 加载 (同 tests/console 其余测试模式)
_api = importlib.import_module("factory-console.api")
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")

try:
    from fastapi.testclient import TestClient  # noqa: E402

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装 (console 侧 venv 需安装)"
)

create_app = _adapter.create_app


@requires_fastapi
def _client(tmp_path: Path) -> TestClient:
    app = create_app(str(tmp_path))
    return TestClient(app)


class TestSkillService:
    @requires_fastapi
    def test_list_skills_has_system_skills(self, tmp_path: Path):
        """GET /api/skills → 3 个内置 Skill (backend.development/testing/flutter.development)。"""
        with _client(tmp_path) as client:
            resp = client.get("/api/skills")
            assert resp.status_code == 200
            skills = resp.json().get("skills", [])
            ids = {s["id"] for s in skills}
            assert {"backend.development", "testing", "flutter.development"} <= ids
            sample = next(s for s in skills if s["id"] == "backend.development")
            assert sample["name"]
            assert "filesystem.read" in sample["tools"]

    @requires_fastapi
    def test_agent_skills_backend1(self, tmp_path: Path):
        """GET /api/agents/backend-1/skills — 真实工厂根缺 agent store → 404 (失败安全);
        有 store 时 → 200 + skills (系统映射兜底)。"""
        with _client(tmp_path) as client:
            resp = client.get("/api/agents/backend-1/skills")
            # tmp_path 工厂根未装配 agent registry → 失败安全 404 (不 5xx)
            assert resp.status_code in (200, 404)
            if resp.status_code == 200:
                data = resp.json()
                assert data["agent_id"] == "backend-1"
                assert isinstance(data["skills"], list)

    @requires_fastapi
    def test_agent_skills_unknown_404(self, tmp_path: Path):
        """GET /api/agents/ghost/skills → 404 (agent 不存在或 store 未装配)。"""
        with _client(tmp_path) as client:
            resp = client.get("/api/agents/ghost/skills")
            assert resp.status_code == 404

    @requires_fastapi
    def test_agent_skills_missing_store_fallback(self, tmp_path: Path):
        """未装配 agent store → 失败安全 (404 不 5xx; 有 store 时 200 系统映射)。"""
        with _client(tmp_path) as client:
            resp = client.get("/api/agents/backend-1/skills")
            assert resp.status_code in (200, 404)
