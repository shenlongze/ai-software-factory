"""tests/console/test_console_sessions.py — K-7e Web 会话栏 (会话存储 + API + 回复)。

覆盖 (factory-console/console_sessions.py + fastapi_adapter 端点):
- SessionStore: create/list/get/update(改名/归档/恢复)/auto-title/messages/cap/
  损坏文件失败安全
- send_message: 用户+assistant 落库; 项目级 prompt 含事实卡; 公司级 persona;
  llm_fn=None/抛错 → 诚实降级 (不假装 AI 回答); 空消息/不存在会话 → 错误
- HTTP: GET/POST /api/sessions · PATCH /api/sessions/{id} ·
  GET/POST /api/sessions/{id}/messages (400 非法作用域 / 404 会话不存在)
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

_sessions = importlib.import_module("factory-console.console_sessions")
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


# ------------------------------------------------------------------ Store 单测


class TestSessionStore:
    def test_create_and_list(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        s = store.create_session(scope="company")
        assert s["scope"] == "company"
        assert s["status"] == "active"
        assert s["title"] == "新会话"
        items = store.list_sessions()
        assert len(items) == 1
        assert items[0]["id"] == s["id"]

    def test_project_scope_requires_project_id(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        with pytest.raises(ValueError):
            store.create_session(scope="project")
        s = store.create_session(scope="project", project_id="P-1")
        assert s["project_id"] == "P-1"

    def test_invalid_scope(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        with pytest.raises(ValueError):
            store.create_session(scope="dept")

    def test_filter_by_scope_and_project(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        store.create_session(scope="company", title="公司")
        store.create_session(scope="project", project_id="P-1", title="P1")
        store.create_session(scope="project", project_id="P-2", title="P2")
        assert len(store.list_sessions(scope="company")) == 1
        assert len(store.list_sessions(scope="project", project_id="P-1")) == 1
        assert len(store.list_sessions(scope="project")) == 2

    def test_update_title_status_summary(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        s = store.create_session(scope="company")
        upd = store.update_session(s["id"], title="改需求: 导出", status="archived")
        assert upd["title"] == "改需求: 导出"
        assert upd["status"] == "archived"
        assert store.update_session("nope") is None
        with pytest.raises(ValueError):
            store.update_session(s["id"], status="bogus")

    # ---- 想法→细化→待办链路 (v1.1.144): 模块锚点 feature_id ----
    def test_create_session_with_feature_anchor(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        s = store.create_session(scope="project", project_id="P-1", feature_id="FEAT-1")
        assert s["feature_id"] == "FEAT-1"
        s2 = store.create_session(scope="project", project_id="P-1")
        assert s2["feature_id"] is None

    def test_list_sessions_filter_feature(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        store.create_session(scope="project", project_id="P-1", feature_id="FEAT-1", title="细化A")
        store.create_session(scope="project", project_id="P-1", feature_id="FEAT-2", title="细化B")
        store.create_session(scope="project", project_id="P-1", title="项目级")
        got = store.list_sessions(scope="project", feature_id="FEAT-1")
        assert [s["title"] for s in got] == ["细化A"]

    def test_list_sessions_filter_task_id(self, tmp_path):
        """T-3: 按 task_id 过滤会话 (跨会话恢复定位上次会话)。"""
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        store.create_session(scope="project", project_id="P-1", task_id="TASK-1", title="会话A")
        store.create_session(scope="project", project_id="P-1", task_id="TASK-2", title="会话B")
        store.create_session(scope="project", project_id="P-1", title="会话C")
        got = store.list_sessions(task_id="TASK-1")
        assert [s["title"] for s in got] == ["会话A"]
        assert store.list_sessions(task_id="TASK-X") == []

    def test_update_session_feature_anchor(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        s = store.create_session(scope="project", project_id="P-1", feature_id="FEAT-1")
        upd = store.update_session(s["id"], feature_id="FEAT-2")
        assert upd["feature_id"] == "FEAT-2"
        # None = 不修改 (API 惯例: 未提供字段不更新)
        upd2 = store.update_session(s["id"], title="改名")
        assert upd2["feature_id"] == "FEAT-2"

    def test_append_messages_and_auto_title(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        s = store.create_session(scope="company")
        m = store.append_message(s["id"], "user", "我想做一个记账App")
        assert m["role"] == "user"
        # 首条用户消息 → 自动标题
        assert store.get_session(s["id"])["title"] == "我想做一个记账App"
        store.append_message(s["id"], "assistant", "好的")
        msgs = store.list_messages(s["id"])
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        assert store.message_count(s["id"]) == 2
        assert store.append_message("nope", "user", "x") is None

    def test_message_cap_rolling_window(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        s = store.create_session(scope="company")
        for i in range(_sessions.MAX_MESSAGES_PER_SESSION + 10):
            store.append_message(s["id"], "user", f"msg-{i}")
        msgs = store.list_messages(s["id"])
        assert len(msgs) == _sessions.MAX_MESSAGES_PER_SESSION
        assert msgs[0]["content"] == "msg-10"

    def test_corrupt_file_failsafe(self, tmp_path):
        p = tmp_path / "console_sessions.json"
        p.write_text("{not json", encoding="utf-8")
        store = _sessions.SessionStore(p)
        assert store.list_sessions() == []
        s = store.create_session(scope="company")
        assert s["id"]
        # 损坏文件被覆盖为合法数据
        assert json.loads(p.read_text(encoding="utf-8"))["sessions"][s["id"]]["id"] == s["id"]

    def test_reload_persistence(self, tmp_path):
        p = tmp_path / "console_sessions.json"
        store = _sessions.SessionStore(p)
        s = store.create_session(scope="project", project_id="P-1", title="t")
        store.append_message(s["id"], "user", "hi")
        store2 = _sessions.SessionStore(p)
        assert store2.get_session(s["id"])["title"] == "t"
        assert len(store2.list_messages(s["id"])) == 1


class TestSendMessage:
    def test_project_prompt_has_facts_and_reply_recorded(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        s = store.create_session(scope="project", project_id="P-1")
        seen: list[str] = []

        def fake_llm(prompt: str) -> str:
            seen.append(prompt)
            return "项目回复: 生命周期是 development"

        result = _sessions.send_message(
            store, s["id"], "项目现在什么阶段?", facts="名称: Demo\n生命周期: development", llm_fn=fake_llm
        )
        assert result["user"]["content"] == "项目现在什么阶段?"
        assert result["assistant"]["content"] == "项目回复: 生命周期是 development"
        assert "名称: Demo" in seen[0]
        assert "生命周期: development" in seen[0]

    def test_company_prompt_persona(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        s = store.create_session(scope="company")
        seen: list[str] = []

        def fake_llm(prompt: str) -> str:
            seen.append(prompt)
            return "公司回复"

        result = _sessions.send_message(store, s["id"], "帮我看看想法", llm_fn=fake_llm)
        assert "公司 (全局)" in seen[0]
        assert result["assistant"]["content"] == "公司回复"

    def test_llm_none_honest_fallback(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        s = store.create_session(scope="company")

        def fake_llm(_prompt: str) -> None:
            return None

        result = _sessions.send_message(store, s["id"], "你好", llm_fn=fake_llm)
        assert "暂不可用" in result["assistant"]["content"]
        assert result["user"]["content"] == "你好"

    def test_llm_raise_honest_fallback(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        s = store.create_session(scope="company")

        def fake_llm(_prompt: str) -> str:
            raise RuntimeError("boom")

        result = _sessions.send_message(store, s["id"], "hi", llm_fn=fake_llm)
        assert "暂不可用" in result["assistant"]["content"]

    def test_empty_message_and_missing_session(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "console_sessions.json")
        s = store.create_session(scope="company")
        with pytest.raises(ValueError):
            _sessions.send_message(store, s["id"], "   ", llm_fn=lambda p: "x")
        with pytest.raises(ValueError):
            _sessions.send_message(store, "nope", "hi", llm_fn=lambda p: "x")


# ------------------------------------------------------------------ HTTP


@pytest.fixture
def http_app(tmp_path):
    """真实装配: build_console_service + build_app(factory_root=tmp) → TestClient。

    传 factory_root → sessions_store 落 tmp (不污染 ~/.factory)。
    """
    event_logger = None
    service = _adapter.build_console_service(tmp_path, event_logger=event_logger)
    app = _adapter.build_app(service, event_logger=event_logger, factory_root=tmp_path)
    with TestClient(app) as c:
        yield c, tmp_path


@requires_fastapi
class TestSessionsHttp:
    def test_create_list_patch_messages(self, http_app):
        client, root = http_app
        r = client.post("/api/sessions", json={"scope": "company"})
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        # 列表
        r = client.get("/api/sessions")
        assert r.status_code == 200
        assert [s["id"] for s in r.json()["items"]] == [sid]
        # 过滤
        r = client.get("/api/sessions?scope=project")
        assert r.json()["count"] == 0
        # patch 改名
        r = client.patch(f"/api/sessions/{sid}", json={"title": "讨论: 记账"})
        assert r.json()["title"] == "讨论: 记账"
        # 消息发送 (注入真实 LLM 会挂 → 诚实降级; 但 store 真实落库)
        r = client.post(f"/api/sessions/{sid}/messages", json={"message": "你好"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user"]["content"] == "你好"
        assert body["assistant"]["content"]
        # 消息列表
        r = client.get(f"/api/sessions/{sid}/messages")
        assert r.json()["count"] == 2
        # 会话文件落 tmp
        assert (root / "console_sessions.json").is_file()

    def test_project_session_facts(self, http_app):
        client, _ = http_app
        r = client.post("/api/sessions", json={"scope": "project", "project_id": "P-zzz"})
        assert r.status_code == 200
        sid = r.json()["id"]
        r = client.post(f"/api/sessions/{sid}/messages", json={"message": "什么阶段"})
        assert r.status_code == 200
        assert r.json()["user"]["content"] == "什么阶段"

    def test_errors(self, http_app):
        client, _ = http_app
        assert client.post("/api/sessions", json={"scope": "dept"}).status_code == 400
        assert client.post("/api/sessions", json={"scope": "project"}).status_code == 400
        assert client.get("/api/sessions?scope=bogus").status_code == 400
        assert client.patch("/api/sessions/nope", json={"title": "x"}).status_code == 404
        assert client.get("/api/sessions/nope/messages").status_code == 404
        assert client.post("/api/sessions/nope/messages", json={"message": "x"}).status_code == 404
        # 空消息 → 400
        r = client.post("/api/sessions", json={"scope": "company"})
        sid = r.json()["id"]
        assert client.post(f"/api/sessions/{sid}/messages", json={"message": "  "}).status_code == 400


class TestWebAwarePrompts:
    def test_company_prompt_capabilities(self, tmp_path):
        """公司级提示词: Web 感知 + 会话真实能力清单 (Founder: 会话不能自我贬低)。"""
        store = _sessions.SessionStore(tmp_path / "s.json")
        sess = store.create_session(scope="company")
        seen: list[str] = []
        _sessions.send_message(store, sess["id"], "现在在哪个项目", llm_fn=lambda p: (seen.append(p) or "公司/全局"))
        assert "公司 / 全局" in seen[0]
        # 会话知道自己能真实执行 (建任务/操作/扫描/推送), 不是"不能操作文件系统"
        assert "我能真实执行的操作" in seen[0]
        assert "标记完成" in seen[0]
        assert "git" in seen[0].lower() or "推送" in seen[0]
        assert "不要建议用户运行" not in seen[0]

    def test_project_prompt_has_facts_and_capabilities(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "s.json")
        sess = store.create_session(scope="project", project_id="P-1")
        seen: list[str] = []
        _sessions.send_message(
            store, sess["id"], "当前是哪个项目",
            facts="名称: 记账\n生命周期: development", llm_fn=lambda p: (seen.append(p) or "记账"),
        )
        assert "名称: 记账" in seen[0]
        assert "我能真实执行" in seen[0]
        assert "不要建议运行" not in seen[0]
