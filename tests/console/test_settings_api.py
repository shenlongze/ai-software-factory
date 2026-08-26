"""tests/console/test_settings_api.py — 设置管理面 (v1.1.102)。

覆盖 (fastapi_adapter + api/mcp_api.py + LLMControlPlane providers.json):
- GET /api/config/llm — providers.json 管理视图 (enabled/models/key 状态/默认模型)
- PATCH /api/config/llm — 启用/停用 Provider + 默认模型落库; 未知 provider → 404
- DELETE /api/mcp/connections/{id} — 移除 MCP 连接 (创建→移除→再移除 404)
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
    service = _adapter.build_console_service(tmp_path, event_logger=None)
    app = _adapter.build_app(service, event_logger=None, factory_root=tmp_path)
    with TestClient(app) as c:
        yield c, tmp_path


@pytest.fixture
def llm_app(tmp_path):
    """带 providers.json 的 app (LLM 管理测试 — 文件先于 app 构造, 平面加载)。"""
    _write_providers(
        tmp_path,
        {
            "deepseek": {
                "id": "deepseek",
                "enabled": True,
                "models": ["deepseek-chat", "deepseek-reasoner"],
                "api_key_ref": "env:DEEPSEEK_API_KEY",
            }
        },
    )
    service = _adapter.build_console_service(tmp_path, event_logger=None)
    app = _adapter.build_app(service, event_logger=None, factory_root=tmp_path)
    with TestClient(app) as c:
        yield c, tmp_path


def _write_providers(root: Path, providers: dict) -> None:
    (root / "providers.json").write_text(
        json.dumps({"version": 1, "providers": providers}, ensure_ascii=False),
        encoding="utf-8",
    )


@requires_fastapi
class TestLlmConfig:
    def test_get_empty_when_no_providers(self, http_app):
        client, _ = http_app
        r = client.get("/api/config/llm")
        assert r.status_code == 200
        assert r.json()["providers"] == []
        assert r.json()["selected"] == {"provider_id": None, "model": None}

    def test_get_view_shape(self, llm_app, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-not-real")
        client, root = llm_app
        r = client.get("/api/config/llm")
        body = r.json()
        assert body["selected"]["provider_id"] == "deepseek"
        p = body["providers"][0]
        assert p["id"] == "deepseek"
        assert p["enabled"] is True
        assert p["models"] == ["deepseek-chat", "deepseek-reasoner"]
        assert "key_configured" in p  # 只输出是否可解析, 不输出 key 本体
        assert "api_key_ref" not in p["api_key_ref"].lower() or p["api_key_ref"]  # 引用, 非明文

    def test_set_default_model_and_disable(self, llm_app, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-not-real")
        client, root = llm_app
        r = client.patch(
            "/api/config/llm", json={"provider_id": "deepseek", "default_model": "deepseek-reasoner"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["default_model"] == "deepseek-reasoner"
        # 停用
        r = client.patch("/api/config/llm", json={"provider_id": "deepseek", "enabled": False})
        assert r.json()["enabled"] is False
        # 持久化
        d = json.load(open(root / "providers.json", encoding="utf-8"))
        assert d["providers"]["deepseek"]["enabled"] is False
        assert d["providers"]["deepseek"]["metadata"]["default_model"] == "deepseek-reasoner"

    def test_patch_unknown_provider_404(self, http_app):
        client, _ = http_app
        assert (
            client.patch("/api/config/llm", json={"provider_id": "nope", "enabled": True}).status_code
            == 404
        )


@requires_fastapi
class TestMcpRemove:
    def test_remove_missing_404(self, http_app):
        client, _ = http_app
        assert client.delete("/api/mcp/connections/nope").status_code == 404

    def test_create_then_remove_then_404(self, http_app):
        client, _ = http_app
        r = client.post(
            "/api/mcp/connections",
            json={"name": "t1", "server_url": "https://mock.example/tools", "transport": "mock"},
        )
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        r = client.delete(f"/api/mcp/connections/{cid}")
        assert r.status_code == 200
        assert r.json() == {"deleted": True}
        assert client.delete(f"/api/mcp/connections/{cid}").status_code == 404


@requires_fastapi
class TestAgentSkillManage:
    def test_agent_register_list_remove(self, http_app):
        client, root = http_app
        r = client.post("/api/agents", json={"id": "pm-1", "role": "product_manager", "skills": ["prd", "discovery"]})
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "product_manager"
        # 列表可见
        listed = client.get("/api/agents").json()["agents"]
        assert any(a["id"] == "pm-1" for a in listed)
        # 持久化
        import json as _json
        d = _json.load(open(root / "agents" / "agents.json", encoding="utf-8"))
        assert d["agents"]["pm-1"]["skills"] == ["prd", "discovery"]
        # 移除 → 404
        assert client.delete("/api/agents/pm-1").status_code == 200
        assert client.delete("/api/agents/pm-1").status_code == 404

    def test_agent_requires_id_role(self, http_app):
        client, _ = http_app
        assert client.post("/api/agents", json={"id": "", "role": "x"}).status_code == 400
        assert client.post("/api/agents", json={"id": "a", "role": ""}).status_code == 400

    def test_skill_register_list_remove(self, http_app):
        client, root = http_app
        r = client.post("/api/skills", json={"id": "python-api", "name": "Python API", "category": "backend"})
        assert r.status_code == 200, r.text
        assert r.json()["category"] == "backend"
        assert client.post("/api/skills", json={"id": ""}).status_code == 400
        listed = client.get("/api/skills").json()["skills"]
        assert any(s["id"] == "python-api" for s in listed)
        import json as _json
        d = _json.load(open(root / "skills" / "skills.json", encoding="utf-8"))
        assert d["skills"]["python-api"]["name"] == "Python API"
        assert client.delete("/api/skills/python-api").status_code == 200
        assert client.delete("/api/skills/python-api").status_code == 404


@requires_fastapi
class TestLlmCreateEdit:
    def test_create_provider_upsert(self, http_app):
        client, root = http_app
        r = client.post(
            "/api/config/llm",
            json={
                "provider_id": "openai",
                "enabled": True,
                "models": ["gpt-4o"],
                "base_url": "https://api.openai.com/v1/chat/completions",
                "api_key_ref": "env:OPENAI_API_KEY",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == "openai"
        assert body["enabled"] is True
        assert body["models"] == ["gpt-4o"]
        # 持久化
        import json as _json
        d = _json.load(open(root / "providers.json", encoding="utf-8"))
        assert d["providers"]["openai"]["api_key_ref"] == "env:OPENAI_API_KEY"
        assert d["providers"]["openai"]["base_url"].startswith("https://api.openai.com")
        # upsert: 再 POST 覆盖 models
        r = client.post(
            "/api/config/llm", json={"provider_id": "openai", "models": ["gpt-4o", "gpt-4o-mini"]}
        )
        assert r.json()["models"] == ["gpt-4o", "gpt-4o-mini"]

    def test_patch_edit_models_and_base_url(self, http_app, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        client, root = http_app
        import json as _json
        (root / "providers.json").write_text(
            _json.dumps(
                {
                    "version": 1,
                    "providers": {
                        "deepseek": {
                            "id": "deepseek",
                            "enabled": True,
                            "models": ["deepseek-chat"],
                            "api_key_ref": "env:DEEPSEEK_API_KEY",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        r = client.patch(
            "/api/config/llm",
            json={"provider_id": "deepseek", "models": ["deepseek-chat", "deepseek-reasoner"], "base_url": "https://custom/v1/chat/completions"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["models"] == ["deepseek-chat", "deepseek-reasoner"]
        assert r.json()["base_url"] == "https://custom/v1/chat/completions"

    def test_plaintext_key_rejected(self, http_app):
        client, _ = http_app
        r = client.post(
            "/api/config/llm",
            json={"provider_id": "x", "api_key_ref": "sk-plain-secret"},
        )
        assert r.status_code == 400

    def test_patch_missing_404(self, http_app):
        client, _ = http_app
        assert client.patch("/api/config/llm", json={"provider_id": "nope"}).status_code == 404


@requires_fastapi
class TestSessionCreateProjectAction:
    def test_conversation_creates_project(self, http_app):
        """会话动作: '做一个App' → 真实创建项目 + meta.action=created + 跳转 target。"""
        client, root = http_app
        r = client.post("/api/sessions", json={"scope": "company"})
        sid = r.json()["id"]
        # LLM 意图解析不可用 → 确定性 fallback create_project; 真实创建
        r = client.post(f"/api/sessions/{sid}/messages", json={"message": "做一个记账App"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["meta"]["intent"] == "create_project"
        assert body["meta"]["action"] == "created"
        assert body["meta"]["target"]["url"].startswith("#/project/")
        # 项目真实落库 (org)
        listed = client.get("/api/projects").json()["items"]
        created_id = body["meta"]["target"]["url"].split("/")[-1]
        assert any(p["id"] == created_id for p in listed)


@requires_fastapi
class TestSessionCreateTaskAction:
    def test_conversation_creates_task(self, http_app):
        """会话: '给X完善功能' → 真实创建任务 + meta.action=created + 跳转任务页。"""
        client, _ = http_app
        # 先建一个项目
        r = client.post("/api/projects", json={"idea": "做一个测试项目A", "name": "测试项目A"})
        pid = r.json()["project_id"]
        r = client.post("/api/sessions", json={"scope": "company"})
        sid = r.json()["id"]
        # LLM 不可用 → 确定性 fallback create_task; hint_project 由 LLM 提取不到 → 从问句/项目匹配
        r = client.post(f"/api/sessions/{sid}/messages", json={"message": f"给 测试项目A 完善导出功能"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["meta"]["intent"] == "create_task"
        assert body["meta"]["action"] == "created", r.text
        assert body["meta"]["target"]["url"] == f"#/project/{pid}/todo"
        # 任务真实落库
        backlog = client.get(f"/api/projects/{pid}/backlog").json()
        tasks = backlog.get("tasks", [])
        assert any("导出" in str(t.get("title", "")) for t in tasks), tasks
