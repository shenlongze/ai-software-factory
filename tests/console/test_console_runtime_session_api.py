"""tests/console/test_console_runtime_session_api.py — S10-016 Runtime Session Service + API 测试。

覆盖 (Task 001 — AI Employee Runtime Foundation, Console 侧装配):
- Service 层 (ConsoleService + RuntimeSessionStore 注入):
  - create_session → PENDING / start → RUNNING / append_event → 事件链 /
    complete → SUCCESS|FAILED / cancel → CANCELLED (生命周期全链路)
  - list_running_sessions / get_session / get_sessions_by_task 查询
  - 非法状态转换 → RuntimeSessionError (响亮); 空 agent_id/task_id → ValueError
  - store 缺失 → 失败安全 (None/[]); 持久化 (service 重建后仍可查)
- API 层 (真实装配 build_console_service → build_app → TestClient):
  - POST /api/agents/{agent_id}/sessions (400 空 task_id)
  - POST /api/runtime-sessions/{id}/start|events|complete|cancel
    (404 不存在 / 409 状态机 / 400 非法事件类型)
  - GET /api/runtime-sessions?status=running / {id} / /api/tasks/{id}/runtime
  - 端到端: create → start → 事件 → complete → 查询验证 (真实 HTTP)

basename 全仓库唯一 (test_console_* 前缀); fastapi/httpx 未安装 → HTTP 类跳过
(与 test_console_lifecycle_acceptance.py 同模式)。
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
if str(_FACTORY_EXEC) not in sys.path:  # exec 包父目录 (runtime_session 域)
    sys.path.insert(0, str(_FACTORY_EXEC))

#: factory-console 包名含连字符 → importlib 加载 (同 tests/console 其余测试模式)
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")
_service_mod = importlib.import_module("factory-console.service")

try:
    from fastapi.testclient import TestClient  # noqa: E402

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装 (console 侧 venv 需安装)"
)


def _session_store(factory_root: Path):
    """RuntimeSessionStore (<root>/runtime-sessions — 独立数据空间, 原子写)。"""
    from exec.runtime_session import RuntimeSessionStore

    return RuntimeSessionStore(factory_root / "runtime-sessions")


def _make_service(factory_root: Path):
    """最小 ConsoleService (全部依赖缺省, 仅注入 session_store — 单测隔离)。"""
    return _service_mod.ConsoleService(session_store=_session_store(factory_root))


# ------------------------------------------------------------------ Service 层


class TestRuntimeSessionService:
    def test_create_session_pending(self, tmp_path: Path):
        """create_session: PENDING + 字段完整 (session_id/agent/task/workflow/时间戳)。"""
        service = _make_service(tmp_path / "factory")
        session = service.create_session("dev-1", "T-1", workflow_id="W-1")
        assert session is not None
        assert session.session_id.startswith("rs-")
        assert session.agent_id == "dev-1"
        assert session.task_id == "T-1"
        assert session.workflow_id == "W-1"
        assert session.status.value == "pending"
        assert session.created_at is not None
        assert session.started_at is None

    def test_create_session_workflow_optional(self, tmp_path: Path):
        """workflow_id 可选 (独立执行); 缺省空串。"""
        service = _make_service(tmp_path / "factory")
        session = service.create_session("dev-1", "T-1")
        assert session.workflow_id == ""

    @pytest.mark.parametrize("agent_id", ["", "   "])
    def test_create_session_empty_agent_rejected(self, tmp_path: Path, agent_id: str):
        """空 agent_id → ValueError (HTTP 层 400 — 执行者必须明确)。"""
        service = _make_service(tmp_path / "factory")
        with pytest.raises(ValueError):
            service.create_session(agent_id, "T-1")

    @pytest.mark.parametrize("task_id", ["", "   "])
    def test_create_session_empty_task_rejected(self, tmp_path: Path, task_id: str):
        """空 task_id → ValueError (400 — Session 是 Task 的执行会话, 必须锚定)。"""
        service = _make_service(tmp_path / "factory")
        with pytest.raises(ValueError):
            service.create_session("dev-1", task_id)

    def test_full_lifecycle_success(self, tmp_path: Path):
        """全链路: create → start (started_at) → 3 事件 → complete(success=True)
        → SUCCESS (finished_at); 事件链保序。"""
        service = _make_service(tmp_path / "factory")
        session = service.create_session("dev-1", "T-1")
        assert session.status.value == "pending"

        running = service.start_session(session.session_id)
        assert running.status.value == "running"
        assert running.started_at is not None

        ev1 = service.append_event(
            running.session_id, "agent_started", "Agent 已唤醒"
        )
        ev2 = service.append_event(
            running.session_id, "tool_called", "调用 sandbox.apply_patch",
            data={"patch": "p1"},
        )
        ev3 = service.append_event(
            running.session_id, "output_generated", "生成 patch 产物"
        )
        assert ev1.event_id.startswith("ev-")
        assert ev2.data == {"patch": "p1"}
        assert [e.message for e in service.get_session(session.session_id).events] == [
            "Agent 已唤醒",
            "调用 sandbox.apply_patch",
            "生成 patch 产物",
        ]

        done = service.complete_session(running.session_id, success=True)
        assert done.status.value == "success"
        assert done.finished_at is not None
        # 终态后事件冻结: 再追加 → RuntimeSessionError
        with pytest.raises(_service_mod.RuntimeSessionError):
            service.append_event(done.session_id, "tool_called", "late")

    def test_complete_failed_and_cancel(self, tmp_path: Path):
        """FAILED (complete success=False) 与 CANCELLED (cancel) 分支。"""
        service = _make_service(tmp_path / "factory")
        s1 = service.create_session("dev-1", "T-1")
        failed = service.complete_session(
            service.start_session(s1.session_id).session_id, success=False
        )
        assert failed.status.value == "failed"

        s2 = service.create_session("dev-1", "T-1")
        cancelled = service.cancel_session(
            service.start_session(s2.session_id).session_id
        )
        assert cancelled.status.value == "cancelled"

    def test_illegal_transition_raises(self, tmp_path: Path):
        """非法转换: PENDING→complete / SUCCESS→start → RuntimeSessionError。"""
        service = _make_service(tmp_path / "factory")
        session = service.create_session("dev-1", "T-1")
        with pytest.raises(_service_mod.RuntimeSessionError):
            service.complete_session(session.session_id, success=True)

        done = service.complete_session(
            service.start_session(session.session_id).session_id, success=True
        )
        with pytest.raises(_service_mod.RuntimeSessionError):
            service.start_session(done.session_id)

    def test_invalid_event_type_raises(self, tmp_path: Path):
        """非法事件类型 → ValueError (400)。"""
        service = _make_service(tmp_path / "factory")
        session = service.create_session("dev-1", "T-1")
        running = service.start_session(session.session_id)
        with pytest.raises(ValueError):
            service.append_event(running.session_id, "not_a_real_event", "x")

    def test_get_session_missing_none(self, tmp_path: Path):
        """不存在 session → None (404 语义)。"""
        service = _make_service(tmp_path / "factory")
        assert service.get_session("rs-nope") is None

    def test_list_running_sessions_filters(self, tmp_path: Path):
        """list_running_sessions: 只返回 RUNNING (含 PENDING/终态排除)。"""
        service = _make_service(tmp_path / "factory")
        service.create_session("dev-1", "T-1")  # pending
        s2 = service.create_session("dev-2", "T-2")
        service.start_session(s2.session_id)
        s3 = service.create_session("dev-3", "T-3")
        service.start_session(s3.session_id)
        service.complete_session(s3.session_id, success=True)
        running = service.list_running_sessions()
        assert [s.agent_id for s in running] == ["dev-2"]

    def test_get_sessions_by_task(self, tmp_path: Path):
        """get_sessions_by_task: 按 task_id 过滤 (多次执行 = 多 session)。"""
        service = _make_service(tmp_path / "factory")
        service.create_session("dev-1", "T-1")
        service.create_session("dev-2", "T-2")
        service.create_session("dev-1", "T-1")
        sessions = service.get_sessions_by_task("T-1")
        assert len(sessions) == 2
        assert {s.agent_id for s in sessions} == {"dev-1"}
        assert service.get_sessions_by_task("T-nope") == []

    def test_persistence_across_service_recreation(self, tmp_path: Path):
        """重启语义: 重建 service (同 store 目录) 后 session 仍可查。"""
        root = tmp_path / "factory"
        service = _make_service(root)
        session = service.create_session("dev-1", "T-1")
        running = service.start_session(session.session_id)
        service.append_event(running.session_id, "agent_started", "hi")
        done = service.complete_session(running.session_id, success=True)

        reopened = _make_service(root)
        loaded = reopened.get_session(session.session_id)
        assert loaded.status.value == "success"
        assert len(loaded.events) == 1
        assert loaded.finished_at is not None

    def test_store_missing_failsafe(self, tmp_path: Path):
        """store 缺失 → 失败安全: 查询空, 写返回 None (Console 冷启动不崩溃)。"""
        service = _service_mod.ConsoleService()
        assert service.list_running_sessions() == []
        assert service.get_sessions_by_task("T-1") == []
        assert service.get_session("rs-x") is None
        assert service.create_session("dev-1", "T-1") is None
        assert service.start_session("rs-x") is None
        assert service.complete_session("rs-x", success=True) is None
        assert service.cancel_session("rs-x") is None
        assert service.append_event("rs-x", "agent_started", "x") is None


# ------------------------------------------------------------------ API 层


@requires_fastapi
def _api_client(factory_root: Path, event_logger=None):
    """真实装配 (build_console_service → RuntimeSessionStore 落盘 factory_root)。"""
    service = _adapter.build_console_service(factory_root, event_logger=event_logger)
    app = _adapter.build_app(service, event_logger=event_logger)
    return TestClient(app)


@requires_fastapi
class TestRuntimeSessionApi:
    def test_create_session_endpoint(self, tmp_path: Path):
        """POST /api/agents/{id}/sessions → PENDING session (真实 HTTP)。"""
        with _api_client(tmp_path / "factory") as client:
            resp = client.post(
                "/api/agents/dev-1/sessions",
                json={"task_id": "T-1", "workflow_id": "W-1"},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["session_id"].startswith("rs-")
            assert body["agent_id"] == "dev-1"
            assert body["task_id"] == "T-1"
            assert body["workflow_id"] == "W-1"
            assert body["status"] == "pending"
            assert body["events"] == []

    def test_create_session_empty_task_400(self, tmp_path: Path):
        """空 task_id → 400 (Session 必须锚定 Task)。"""
        with _api_client(tmp_path / "factory") as client:
            resp = client.post(
                "/api/agents/dev-1/sessions", json={"task_id": "  "}
            )
            assert resp.status_code == 400, resp.text

    def test_full_lifecycle_via_http(self, tmp_path: Path):
        """端到端 (HTTP): create → start → 事件 ×3 → complete → 查询验证。

        Runtime Event Timeline: 详情端点返回 events (保序); 运行中列表只含
        RUNNING; task 查询按 task_id 命中。"""
        with _api_client(tmp_path / "factory") as client:
            created = client.post(
                "/api/agents/dev-1/sessions", json={"task_id": "T-1"}
            ).json()
            sid = created["session_id"]

            started = client.post(f"/api/runtime-sessions/{sid}/start").json()
            assert started["status"] == "running"
            assert started["started_at"] is not None

            for ev_type, msg in [
                ("agent_started", "Agent 已唤醒"),
                ("execution_started", "进入执行循环"),
                ("tool_called", "调用 sandbox"),
            ]:
                resp = client.post(
                    f"/api/runtime-sessions/{sid}/events",
                    json={"type": ev_type, "message": msg},
                )
                assert resp.status_code == 200, resp.text
                assert resp.json()["type"] == ev_type

            completed = client.post(
                f"/api/runtime-sessions/{sid}/complete", json={"success": True}
            ).json()
            assert completed["status"] == "success"
            assert completed["finished_at"] is not None

            # 详情 + 事件时间线
            detail = client.get(f"/api/runtime-sessions/{sid}").json()
            assert detail["status"] == "success"
            assert [e["type"] for e in detail["events"]] == [
                "agent_started",
                "execution_started",
                "tool_called",
            ]

            # 运行中列表: 已终态 → 不含本 session
            running = client.get("/api/runtime-sessions?status=running").json()["items"]
            assert all(s["session_id"] != sid for s in running)

            # task 查询
            task_runtime = client.get("/api/tasks/T-1/runtime").json()["items"]
            assert [s["session_id"] for s in task_runtime] == [sid]

    def test_events_endpoint_with_data_and_status_filter(self, tmp_path: Path):
        """事件带 data 载荷; GET ?status=running 过滤; 非法事件类型 → 400。"""
        with _api_client(tmp_path / "factory") as client:
            sid = client.post(
                "/api/agents/dev-1/sessions", json={"task_id": "T-1"}
            ).json()["session_id"]
            client.post(f"/api/runtime-sessions/{sid}/start")
            ev = client.post(
                f"/api/runtime-sessions/{sid}/events",
                json={"type": "output_generated", "message": "产物", "data": {"n": 1}},
            ).json()
            assert ev["data"] == {"n": 1}

            bad = client.post(
                f"/api/runtime-sessions/{sid}/events",
                json={"type": "not_a_real_event", "message": "x"},
            )
            assert bad.status_code == 400, bad.text

            running = client.get("/api/runtime-sessions?status=running").json()["items"]
            assert [s["session_id"] for s in running] == [sid]

    def test_error_semantics_404_409(self, tmp_path: Path):
        """404 (不存在) / 409 (状态机非法流转) 语义。"""
        with _api_client(tmp_path / "factory") as client:
            assert client.get("/api/runtime-sessions/rs-nope").status_code == 404
            assert client.post("/api/runtime-sessions/rs-nope/start").status_code == 404
            assert client.post("/api/runtime-sessions/rs-nope/complete",
                               json={"success": True}).status_code == 404
            assert client.get("/api/tasks/T-x/runtime").status_code == 200  # 空态 []

            sid = client.post(
                "/api/agents/dev-1/sessions", json={"task_id": "T-1"}
            ).json()["session_id"]
            # PENDING → complete 非法 (409)
            assert client.post(
                f"/api/runtime-sessions/{sid}/complete", json={"success": True}
            ).status_code == 409
            # PENDING → cancel 非法 (409)
            assert client.post(f"/api/runtime-sessions/{sid}/cancel").status_code == 409
            # 正常 start 后 cancel
            client.post(f"/api/runtime-sessions/{sid}/start")
            assert client.post(f"/api/runtime-sessions/{sid}/cancel").status_code == 200
            # 终态 → start 非法 (409)
            assert client.post(f"/api/runtime-sessions/{sid}/start").status_code == 409
            # 终态 → events 非法 (409)
            assert client.post(
                f"/api/runtime-sessions/{sid}/events",
                json={"type": "tool_called", "message": "x"},
            ).status_code == 409

    def test_cancel_and_failed_lifecycle(self, tmp_path: Path):
        """cancel → CANCELLED 终态; complete success=False → FAILED。"""
        with _api_client(tmp_path / "factory") as client:
            sid = client.post(
                "/api/agents/dev-1/sessions", json={"task_id": "T-1"}
            ).json()["session_id"]
            client.post(f"/api/runtime-sessions/{sid}/start")
            assert client.post(
                f"/api/runtime-sessions/{sid}/complete", json={"success": False}
            ).json()["status"] == "failed"

            sid2 = client.post(
                "/api/agents/dev-1/sessions", json={"task_id": "T-2"}
            ).json()["session_id"]
            client.post(f"/api/runtime-sessions/{sid2}/start")
            assert client.post(f"/api/runtime-sessions/{sid2}/cancel").json()[
                "status"
            ] == "cancelled"

    def test_events_included_in_list_running(self, tmp_path: Path):
        """运行中列表条目含事件链 (前端 RuntimeActivity 数据源)。"""
        with _api_client(tmp_path / "factory") as client:
            sid = client.post(
                "/api/agents/dev-1/sessions", json={"task_id": "T-1"}
            ).json()["session_id"]
            client.post(f"/api/runtime-sessions/{sid}/start")
            client.post(
                f"/api/runtime-sessions/{sid}/events",
                json={"type": "agent_started", "message": "hi"},
            )
            running = client.get("/api/runtime-sessions?status=running").json()["items"]
            assert running[0]["events"][0]["type"] == "agent_started"
