"""tests/console/test_console_agent_executor_api.py — S10-016 Agent Executor Service + API 测试。

覆盖 (Task 002 — Agent Executor, Console 侧装配):
- Service 层 (ConsoleService.execute_runtime_task + 注入 AgentExecutor):
  - 全链路 Success: Task/Agent 校验 → Session → LLM (FakeProvider) → SUCCESS
    → {runtime_session_id, status, output}
  - 空 task_id/agent_id → ValueError (HTTP 400)
  - Task 不存在 / Agent 不存在 → ValueError (AgentExecutorError 转 400)
  - LLM Provider 错误 → status failed + output 保留 (不静默)
  - 无注入 executor 自装配 (无已配置 Provider) → 诚实 FAILED session
  - store/exec 未装配 → None (404 失败安全)
- API 层 (真实装配 build_console_service → build_app → TestClient):
  - POST /api/runtime/execute 端到端 (真实 HTTP): success → 200
    {runtime_session_id, status, output}; invalid task/agent → 400;
    LLM fail → 200 status=failed + output 保留

basename 全仓库唯一 (test_console_* 前缀); fastapi/httpx 未安装 → HTTP 类跳过
(与 test_console_runtime_session_api.py 同模式)。
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
_TESTS_EXEC = _ROOT / "tests" / "exec"
if str(_TESTS_EXEC) not in sys.path:  # exec_helpers (唯一名 helper, 无遮蔽)
    sys.path.insert(0, str(_TESTS_EXEC))

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

#: FakeProvider 成功 content: <patch>NO_CHANGE</patch> — 合法「无修改」交付
#: (DeveloperAgent 空补丁 → 验证通过 → SUCCESS; 非伪造真实 LLM 结果)。
NO_CHANGE_PATCH = "<patch>NO_CHANGE</patch>"

MINI_PROJECT = {
    "calc.py": "def add(a, b):\n    return a + b\n",
}


def _task_store(factory_root: Path):
    from tasks.store import TaskStore

    return TaskStore(factory_root / "tasks")


def _agent_registry(factory_root: Path):
    from agents.registry import AgentRegistry
    from agents.store import AgentStore

    return AgentRegistry(AgentStore(factory_root / "agents"))


def _make_task(factory_root: Path, task_id: str = "T-101", title: str = "fix the sub bug"):
    from tasks.models import Task

    store = _task_store(factory_root)
    store.create(Task(id=task_id, title=title, project="demo", type="feature", workflow="dev"))
    return store


def _make_agent(factory_root: Path, agent_id: str = "developer-1"):
    from agents.models import Agent

    registry = _agent_registry(factory_root)
    registry.register(Agent(id=agent_id, name="Developer", role="developer"))
    return registry


def _injected_executor(factory_root: Path, *, provider=None, runtime=None, session_root=None):
    """注入 AgentExecutor (FakeProvider 真实 runtime — 复用执行引擎)。"""
    from exec.agent_executor import AgentExecutor
    from exec.agent_runtime import AgentRuntime
    from exec.runtime_session import RuntimeSessionStore
    from exec_helpers import FakeProvider, write_files

    root = Path(factory_root)
    session_store = RuntimeSessionStore(session_root or (root / "runtime-sessions"))
    project_dir = root / "project"
    write_files(project_dir, MINI_PROJECT)
    provider = provider or FakeProvider(
        content=NO_CHANGE_PATCH, usage={"input_tokens": 10, "output_tokens": 5}
    )
    if runtime is None:
        work_root = root / "work"
        work_root.mkdir(parents=True, exist_ok=True)  # mkdtemp(dir=...) 须已存在
        runtime = AgentRuntime(provider, work_root=work_root, validation_command=None)
    return AgentExecutor(
        task_store=_task_store(root),
        agent_registry=_agent_registry(root),
        session_store=session_store,
        runtime=runtime,
    ), session_store, project_dir


# ------------------------------------------------------------------ Service 层


class TestAgentExecutorService:
    def test_execute_success_full_chain(self, tmp_path: Path):
        """execute_runtime_task 全链路: Task/Agent 校验 → Session → LLM → SUCCESS
        → {runtime_session_id, status, output} (输出保留)。"""
        root = tmp_path / "factory"
        _make_task(root)
        _make_agent(root)
        executor, session_store, project_dir = _injected_executor(root)
        service = _service_mod.ConsoleService(
            session_store=session_store, agent_executor=executor
        )

        result = service.execute_runtime_task(
            "T-101", "developer-1", context={"project_dir": str(project_dir)}
        )

        assert result["runtime_session_id"].startswith("rs-")
        assert result["status"] == "success"
        assert result["output"]["execution_output"]
        assert result["output"]["execution_summary"]
        assert result["output"]["raw_response"]
        # Session 落库: 事件链含 LLM 边界 + 终态
        session = session_store.get(result["runtime_session_id"])
        assert session.status.value == "success"
        assert [e.type.value for e in session.events][-1] == "execution_completed"

    def test_empty_task_id_rejected(self, tmp_path: Path):
        """空 task_id → ValueError (HTTP 400 — 执行必须锚定 Task)。"""
        service = _service_mod.ConsoleService()
        with pytest.raises(ValueError):
            service.execute_runtime_task("  ", "developer-1")

    def test_empty_agent_id_rejected(self, tmp_path: Path):
        """空 agent_id → ValueError (HTTP 400 — 执行者必须明确)。"""
        service = _service_mod.ConsoleService()
        with pytest.raises(ValueError):
            service.execute_runtime_task("T-101", "")

    def test_task_not_found_maps_to_value_error(self, tmp_path: Path):
        """Invalid Task → ValueError (AgentExecutorError → 400)。"""
        root = tmp_path / "factory"
        _make_agent(root)
        executor, session_store, _project = _injected_executor(root)
        service = _service_mod.ConsoleService(
            session_store=session_store, agent_executor=executor
        )
        with pytest.raises(ValueError, match="task not found"):
            service.execute_runtime_task("T-nope", "developer-1")

    def test_agent_not_found_maps_to_value_error(self, tmp_path: Path):
        """Agent Not Found → ValueError (400)。"""
        root = tmp_path / "factory"
        _make_task(root)
        executor, session_store, _project = _injected_executor(root)
        service = _service_mod.ConsoleService(
            session_store=session_store, agent_executor=executor
        )
        with pytest.raises(ValueError, match="agent not found"):
            service.execute_runtime_task("T-101", "no-such-agent")

    def test_llm_failure_returns_failed_session(self, tmp_path: Path):
        """LLM Provider 错误 → status failed + output 保留 (错误进事件不静默)。"""
        from exec_helpers import FakeProvider

        root = tmp_path / "factory"
        _make_task(root)
        _make_agent(root)
        failing = FakeProvider(error="anthropic api key missing: demo")
        executor, session_store, project_dir = _injected_executor(
            root, provider=failing
        )
        service = _service_mod.ConsoleService(
            session_store=session_store, agent_executor=executor
        )

        result = service.execute_runtime_task(
            "T-101", "developer-1", context={"project_dir": str(project_dir)}
        )

        assert result["status"] == "failed"
        assert "api key missing" in result["output"]["execution_output"]
        session = session_store.get(result["runtime_session_id"])
        assert session.status.value == "failed"
        assert session.events[-1].type.value == "execution_failed"

    def test_no_injected_executor_self_assembled_honest_failed(self, tmp_path: Path):
        """无注入 executor → 自装配; 无已配置 Provider → 诚实 FAILED session
        (Provider Adapter Interface — 不伪造 LLM 结果)。"""
        root = tmp_path / "factory"
        _make_task(root)
        _make_agent(root)
        from exec.runtime_session import RuntimeSessionStore

        session_store = RuntimeSessionStore(root / "runtime-sessions")
        service = _service_mod.ConsoleService(
            session_store=session_store,
            task_store=_task_store(root),
            agent_registry=_agent_registry(root),
        )

        result = service.execute_runtime_task("T-101", "developer-1")

        assert result["status"] == "failed"
        session = session_store.get(result["runtime_session_id"])
        assert session.status.value == "failed"
        assert "provider" in session.events[-1].data.get("error", "").lower()

    def test_exec_missing_returns_none(self, tmp_path: Path):
        """store/exec 未装配 (ConsoleService 空构造) → None (404 失败安全)。"""
        service = _service_mod.ConsoleService()
        assert service.execute_runtime_task("T-101", "developer-1") is None


# ------------------------------------------------------------------ API 层


@requires_fastapi
def _api_client(factory_root: Path, *, agent_executor=None, event_logger=None):
    """真实装配 (build_console_service → AgentExecutor 注入 → TestClient)。"""
    service = _adapter.build_console_service(
        factory_root, event_logger=event_logger, agent_executor=agent_executor
    )
    app = _adapter.build_app(service, event_logger=event_logger)
    return TestClient(app)


@requires_fastapi
class TestAgentExecutorApi:
    def test_execute_endpoint_success(self, tmp_path: Path):
        """POST /api/runtime/execute → 200 {runtime_session_id, status: success,
        output} — 端到端 (真实 HTTP + 真实沙箱执行链)。"""
        root = tmp_path / "factory"
        _make_task(root)
        _make_agent(root)
        executor, _session_store, project_dir = _injected_executor(root)
        with _api_client(root, agent_executor=executor) as client:
            resp = client.post(
                "/api/runtime/execute",
                json={
                    "task_id": "T-101",
                    "agent_id": "developer-1",
                    "context": {"project_dir": str(project_dir)},
                },
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["runtime_session_id"].startswith("rs-")
            assert body["status"] == "success"
            assert body["output"]["execution_summary"]

    def test_execute_endpoint_invalid_task_400(self, tmp_path: Path):
        """invalid task → 400 (不创建 Session)。"""
        root = tmp_path / "factory"
        _make_agent(root)
        executor, _session_store, _project = _injected_executor(root)
        with _api_client(root, agent_executor=executor) as client:
            resp = client.post(
                "/api/runtime/execute",
                json={"task_id": "T-nope", "agent_id": "developer-1"},
            )
            assert resp.status_code == 400, resp.text
            assert "task not found" in resp.json()["detail"]

    def test_execute_endpoint_agent_not_found_400(self, tmp_path: Path):
        """agent not found → 400。"""
        root = tmp_path / "factory"
        _make_task(root)
        executor, _session_store, _project = _injected_executor(root)
        with _api_client(root, agent_executor=executor) as client:
            resp = client.post(
                "/api/runtime/execute",
                json={"task_id": "T-101", "agent_id": "ghost"},
            )
            assert resp.status_code == 400, resp.text
            assert "agent not found" in resp.json()["detail"]

    def test_execute_endpoint_empty_fields_400(self, tmp_path: Path):
        """空 task_id/agent_id → 400。"""
        root = tmp_path / "factory"
        executor, _session_store, _project = _injected_executor(root)
        with _api_client(root, agent_executor=executor) as client:
            assert (
                client.post(
                    "/api/runtime/execute", json={"task_id": "  ", "agent_id": "dev-1"}
                ).status_code
                == 400
            )
            assert (
                client.post(
                    "/api/runtime/execute", json={"task_id": "T-1", "agent_id": ""}
                ).status_code
                == 400
            )

    def test_execute_endpoint_llm_failure_returns_failed(self, tmp_path: Path):
        """LLM Provider 错误 → 200 status=failed + output 保留 (错误进事件,
        不抛裸异常 / 不 5xx)。"""
        from exec_helpers import FakeProvider

        root = tmp_path / "factory"
        _make_task(root)
        _make_agent(root)
        executor, _session_store, project_dir = _injected_executor(
            root, provider=FakeProvider(error="anthropic api key missing: demo")
        )
        with _api_client(root, agent_executor=executor) as client:
            resp = client.post(
                "/api/runtime/execute",
                json={
                    "task_id": "T-101",
                    "agent_id": "developer-1",
                    "context": {"project_dir": str(project_dir)},
                },
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "failed"
            assert "api key missing" in body["output"]["execution_output"]

    def test_execute_endpoint_without_injection_honest_failed(self, tmp_path: Path):
        """无注入 executor (生产装配) → 无已配置 Provider → 200 status=failed
        (诚实 FAILED — 不伪造 LLM 结果)。"""
        root = tmp_path / "factory"
        _make_task(root)
        _make_agent(root)
        with _api_client(root, agent_executor=None) as client:
            resp = client.post(
                "/api/runtime/execute",
                json={"task_id": "T-101", "agent_id": "developer-1"},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "failed"
            assert "provider" in body["output"]["execution_output"].lower()
