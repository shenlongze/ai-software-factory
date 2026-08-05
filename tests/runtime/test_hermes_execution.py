"""test_hermes_execution.py — hermes-runtime 注册 + 派发/执行集成 (Mock subprocess.run)。

覆盖: RuntimeInfo 身份 / CLI runtime add / registry 解析 / Dispatcher 装配 /
ExecutionRunner 生命周期 (SUCCESS/FAILED 事件与终态) / CLI execution run 全链路
(workflow execute_step → dispatch → hermes adapter)。
"""

from __future__ import annotations

import json

from cli_helpers import event_types, open_events, run_cli
from events.logger import EventLogger
from events.store import EventStore
from execution.dispatcher import ExecutionDispatcher
from execution.runner import ExecutionRunner
from runtime.adapters import BUILTIN_ADAPTERS, HermesRuntimeAdapter
from runtime.models import ExecutionStatus, RuntimeInfo, RuntimeStatus
from runtime.registry import RuntimeRegistry
from runtime.store import RuntimeStore
from tasks.store import TaskStore
from workflows.engine import WorkflowEngine
from workflows.store import WorkflowStore

from runtime_helpers import make_request


class _FakeCompleted:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_run(monkeypatch, result: _FakeCompleted | None = None, exc: Exception | None = None):
    def fake_run(argv, **kwargs):
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr("runtime.adapters.hermes.subprocess.run", fake_run)


def _register_hermes_runtime(store: RuntimeStore) -> RuntimeInfo:
    """registry 注册 hermes-runtime 身份 (id/name/type/status 契约)。"""
    registry = RuntimeRegistry(store)
    runtime, _ = registry.register(RuntimeInfo(
        id="hermes-runtime", name="Hermes Agent", type="agent",
        description="Hermes Agent CLI runtime",
    ))
    return runtime


class TestHermesRegistration:
    def test_runtime_info_contract(self):
        """身份契约: id=hermes-runtime / name=Hermes Agent / type=agent / AVAILABLE。"""
        runtime = RuntimeInfo(
            id="hermes-runtime", name="Hermes Agent", type="agent",
        )
        assert runtime.id == "hermes-runtime"
        assert runtime.name == "Hermes Agent"
        assert runtime.type == "agent"
        assert runtime.status is RuntimeStatus.AVAILABLE

    def test_builtin_adapter_available(self):
        assert "hermes-runtime" in BUILTIN_ADAPTERS
        assert isinstance(BUILTIN_ADAPTERS["hermes-runtime"], HermesRuntimeAdapter)

    def test_cli_add_hermes_runtime(self, capsys, cli_root):
        rc, out, err = run_cli(
            capsys, cli_root, "--json", "runtime", "add",
            "--id", "hermes-runtime", "--name", "Hermes Agent", "--type", "agent",
            "--description", "Hermes Agent CLI runtime",
        )
        assert rc == 0
        data = json.loads(out)
        assert data["runtime"]["id"] == "hermes-runtime"
        assert data["runtime"]["type"] == "agent"
        assert data["runtime"]["status"] == "AVAILABLE"

    def test_cli_add_hermes_emits_registered(self, capsys, cli_root):
        run_cli(capsys, cli_root, "runtime", "add", "--id", "hermes-runtime")
        store = open_events(cli_root)
        try:
            assert event_types(store) == ["runtime.registered"]
        finally:
            store.close()

    def test_registry_resolve_hermes(self, runtime_store):
        """唯一 AVAILABLE → resolve_runtime_id 返回 hermes-runtime (派发解析)。"""
        _register_hermes_runtime(runtime_store)
        registry = RuntimeRegistry(runtime_store)
        assert registry.resolve_runtime_id() == "hermes-runtime"
        assert registry.resolve_runtime_id("hermes-runtime") == "hermes-runtime"

    def test_dispatcher_resolves_builtin_adapter(self, runtime_store):
        """Dispatcher 经 BUILTIN_ADAPTERS 装配: hermes-runtime 有实现可派发。"""
        _register_hermes_runtime(runtime_store)
        dispatcher = ExecutionDispatcher(RuntimeRegistry(runtime_store), BUILTIN_ADAPTERS)
        assert dispatcher.get_adapter("hermes-runtime") is BUILTIN_ADAPTERS["hermes-runtime"]
        assert isinstance(dispatcher.get_adapter("hermes-runtime"), HermesRuntimeAdapter)


class TestRunnerIntegration:
    """ExecutionRunner + hermes-runtime (subprocess mock): 生命周期与事件。"""

    def _setup(self, runtime_store: RuntimeStore, logger=None):
        registry = RuntimeRegistry(runtime_store, logger=logger)
        _register_hermes_runtime(runtime_store)
        dispatcher = ExecutionDispatcher(registry, BUILTIN_ADAPTERS)
        return ExecutionRunner(runtime_store, dispatcher, logger=logger)

    def test_runner_success(self, monkeypatch, runtime_store):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        runner = self._setup(runtime_store)
        runner.store.save_execution(
            make_request("EX-H1", input={"instruction": "hi"})
        )
        outcome = runner.run("EX-H1")
        assert outcome.result.status is ExecutionStatus.SUCCESS
        assert outcome.result.output["stdout"] == "OK"
        assert outcome.request.status is ExecutionStatus.SUCCESS

    def test_runner_result_persisted(self, monkeypatch, runtime_store):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        runner = self._setup(runtime_store)
        runner.store.save_execution(make_request("EX-H2"))
        runner.run("EX-H2")
        result = runtime_store.get_result("EX-H2")
        assert result is not None
        assert result.status is ExecutionStatus.SUCCESS
        assert result.request_id == "EX-H2"

    def test_runner_emits_started_completed(self, monkeypatch, runtime_store, logger):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        runner = self._setup(runtime_store, logger=logger)
        runner.store.save_execution(make_request("EX-H3"))
        outcome = runner.run("EX-H3")
        types = [e.type.value for e in outcome.events]
        assert types == ["execution.started", "execution.completed"]

    def test_runner_failed_exit(self, monkeypatch, runtime_store, logger):
        _patch_run(monkeypatch, result=_FakeCompleted(returncode=1, stderr="boom"))
        runner = self._setup(runtime_store, logger=logger)
        runner.store.save_execution(make_request("EX-H4"))
        outcome = runner.run("EX-H4")
        assert outcome.result.status is ExecutionStatus.FAILED
        assert "exited with code 1" in outcome.result.error
        assert outcome.request.status is ExecutionStatus.FAILED
        types = [e.type.value for e in outcome.events]
        assert types == ["execution.started", "execution.failed"]

    def test_runner_failed_command_not_found(self, monkeypatch, runtime_store):
        """命令不存在经 Runner 走 FAILED 终态 (Adapter 不抛 → 无需防御 catch)。"""
        _patch_run(monkeypatch, exc=FileNotFoundError())
        runner = self._setup(runtime_store)
        runner.store.save_execution(make_request("EX-H5"))
        outcome = runner.run("EX-H5")
        assert outcome.result.status is ExecutionStatus.FAILED
        assert "command not found" in outcome.result.error

    def test_runner_failed_stdout_empty(self, monkeypatch, runtime_store):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout=""))
        runner = self._setup(runtime_store)
        runner.store.save_execution(make_request("EX-H6"))
        outcome = runner.run("EX-H6")
        assert outcome.result.status is ExecutionStatus.FAILED
        assert "no output" in outcome.result.error


class TestCliExecutionRun:
    """CLI 全链路: workflow execute_step → execution run → hermes adapter (mock)。"""

    def _seed_execution(self, capsys, cli_root, task_id: str = "T-001") -> str:
        """CLI 建任务/工作流/run, 再经引擎 execute_step 造一条 pending 执行。"""
        run_cli(capsys, cli_root, "workflow", "add", "--id", "wf-test", "--steps", "s1,s2")
        run_cli(capsys, cli_root, "task", "create", "--id", task_id, "--title", "任务",
                "--workflow", "wf-test")
        run_cli(capsys, cli_root, "workflow", "run", task_id)
        store = EventStore(cli_root / "factory.db")
        try:
            engine = WorkflowEngine(
                WorkflowStore(cli_root / "workflows"),
                task_store=TaskStore(cli_root / "tasks"),
                runtime_store=RuntimeStore(cli_root / "runtimes"),
                logger=EventLogger(store),
            )
            req, _ = engine.execute_step(task_id, "s1")
        finally:
            store.close()
        return req.id

    def test_execution_run_hermes_success(self, capsys, cli_root, monkeypatch):
        """注册 hermes-runtime → 造执行 → execution run: started→completed, SUCCESS。"""
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        run_cli(capsys, cli_root, "runtime", "add", "--id", "hermes-runtime")
        exec_id = self._seed_execution(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "--json", "execution", "run", exec_id)
        data = json.loads(out)
        assert rc == 0
        assert data["runtime"] == "hermes-runtime"
        assert data["status"] == "SUCCESS"
        assert data["result"]["status"] == "SUCCESS"
        assert data["result"]["output"]["stdout"] == "OK"
        assert data["events"] == ["execution.started", "execution.completed"]

    def test_execution_run_hermes_failed(self, capsys, cli_root, monkeypatch):
        """hermes 失败 (exit≠0): 业务 FAILED 结果, run 命令 rc 0, execution.failed。"""
        _patch_run(monkeypatch, result=_FakeCompleted(returncode=1, stderr="boom"))
        run_cli(capsys, cli_root, "runtime", "add", "--id", "hermes-runtime")
        exec_id = self._seed_execution(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "--json", "execution", "run", exec_id)
        data = json.loads(out)
        assert rc == 0
        assert data["status"] == "FAILED"
        assert data["result"]["status"] == "FAILED"
        assert "exited with code 1" in data["result"]["error"]
        assert "execution.failed" in data["events"]

    def test_execution_run_hermes_stdout_empty(self, capsys, cli_root, monkeypatch):
        """stdout 空: FAILED 业务结果 + execution.failed 事件 (失败规则贯通 Runner)。"""
        _patch_run(monkeypatch, result=_FakeCompleted(stdout=""))
        run_cli(capsys, cli_root, "runtime", "add", "--id", "hermes-runtime")
        exec_id = self._seed_execution(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "--json", "execution", "run", exec_id)
        data = json.loads(out)
        assert rc == 0
        assert data["result"]["status"] == "FAILED"
        assert "no output" in data["result"]["error"]
        store = open_events(cli_root)
        try:
            assert "execution.failed" in event_types(store)
        finally:
            store.close()
