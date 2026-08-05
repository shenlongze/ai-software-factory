"""test_cli_runtime.py — CLI: factory runtime add/list + execution list (发 runtime.*/execution.* 事件)。"""

from __future__ import annotations

import json

import pytest

from cli.main import main
from cli_helpers import event_types, open_events, run_cli
from events.logger import EventLogger
from events.store import EventStore
from runtime.models import ExecutionResult
from runtime.store import RuntimeStore
from tasks.store import TaskStore
from workflows.engine import WorkflowEngine
from workflows.store import WorkflowStore


class TestRuntimeAdd:
    def test_add_ok(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "runtime", "add", "--id", "R-001")
        assert rc == 0
        assert "R-001" in out and "已注册" in out

    def test_add_json(self, capsys, cli_root):
        rc, out, err = run_cli(
            capsys, cli_root, "--json", "runtime", "add",
            "--id", "R-001", "--name", "mock", "--type", "agent", "--description", "test rt",
        )
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True
        assert data["runtime"]["id"] == "R-001"
        assert data["runtime"]["name"] == "mock"
        assert data["runtime"]["type"] == "agent"
        assert data["runtime"]["status"] == "AVAILABLE"
        assert data["event_seq"] > 0

    def test_add_creates_dir_and_file(self, capsys, cli_root):
        """runtimes/ 目录由首次写自动创建 (ADR-0006 决策 5)。"""
        run_cli(capsys, cli_root, "runtime", "add", "--id", "R-001")
        assert (cli_root / "runtimes" / "runtimes.json").exists()

    def test_add_emits_runtime_registered(self, capsys, cli_root):
        run_cli(capsys, cli_root, "runtime", "add", "--id", "R-001")
        store = open_events(cli_root)
        try:
            assert event_types(store) == ["runtime.registered"]
        finally:
            store.close()

    def test_add_duplicate_rc1(self, capsys, cli_root):
        run_cli(capsys, cli_root, "runtime", "add", "--id", "R-001")
        rc, out, err = run_cli(capsys, cli_root, "runtime", "add", "--id", "R-001")
        assert rc == 1
        assert "already exists" in err

    def test_add_missing_id_usage_error(self, cli_root):
        """argparse 缺必选参数 → SystemExit(2) (发生在 main 返回前)。"""
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "runtime", "add"])
        assert exc.value.code == 2


class TestRuntimeList:
    def test_list_empty(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "runtime", "list")
        assert rc == 0
        assert "(无记录)" in out and "0 runtimes" in out

    def test_list_after_add(self, capsys, cli_root):
        run_cli(capsys, cli_root, "runtime", "add", "--id", "R-001", "--name", "mock")
        rc, out, err = run_cli(capsys, cli_root, "runtime", "list")
        assert rc == 0
        assert "R-001" in out and "mock" in out and "AVAILABLE" in out
        assert "1 runtimes" in out

    def test_list_json(self, capsys, cli_root):
        run_cli(capsys, cli_root, "runtime", "add", "--id", "R-001")
        rc, out, err = run_cli(capsys, cli_root, "--json", "runtime", "list")
        data = json.loads(out)
        assert data["ok"] is True and data["count"] == 1
        assert data["runtimes"][0]["id"] == "R-001"

    def test_list_filter_status(self, capsys, cli_root):
        run_cli(capsys, cli_root, "runtime", "add", "--id", "R-001")
        rc, out, err = run_cli(capsys, cli_root, "--json", "runtime", "list", "--status", "DISABLED")
        assert json.loads(out)["count"] == 0
        rc, out, err = run_cli(capsys, cli_root, "--json", "runtime", "list", "--status", "AVAILABLE")
        assert json.loads(out)["count"] == 1

    def test_list_invalid_status_rc2(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "runtime", "list", "--status", "bogus")
        assert rc == 2

    def test_list_emits_runtime_viewed(self, capsys, cli_root):
        run_cli(capsys, cli_root, "runtime", "add", "--id", "R-001")
        run_cli(capsys, cli_root, "runtime", "list")
        store = open_events(cli_root)
        try:
            assert event_types(store) == ["runtime.registered", "runtime.viewed"]
        finally:
            store.close()


class TestExecutionList:
    def _seed_execution(self, capsys, cli_root, task_id: str = "T-001") -> str:
        """CLI 建任务/工作流/run, 再经引擎 execute_step 造一条 pending 执行 (CLI 无 execute-step 命令)。"""
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
                logger=EventLogger(store),  # execution.created 同样入事件库
            )
            req, _ = engine.execute_step(task_id, "s1")
        finally:
            store.close()
        return req.id

    def test_list_empty(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "execution", "list")
        assert rc == 0
        assert "(无记录)" in out and "0 executions" in out

    def test_list_after_execute_step(self, capsys, cli_root):
        exec_id = self._seed_execution(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "execution", "list")
        assert rc == 0
        assert exec_id in out and "T-001" in out and "PENDING" in out
        assert "1 executions" in out

    def test_list_json(self, capsys, cli_root):
        exec_id = self._seed_execution(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "--json", "execution", "list")
        data = json.loads(out)
        assert data["ok"] is True and data["count"] == 1
        item = data["executions"][0]
        assert item["id"] == exec_id
        assert item["status"] == "PENDING"
        assert item["step_id"] == "s1"
        assert item["workflow_id"] == "wf-test"
        assert item["runtime_id"] is None
        assert item["result"] is None

    def test_list_filter_task(self, capsys, cli_root):
        self._seed_execution(capsys, cli_root, task_id="T-001")
        self._seed_execution(capsys, cli_root, task_id="T-002")
        rc, out, err = run_cli(capsys, cli_root, "--json", "execution", "list", "--task", "T-002")
        data = json.loads(out)
        assert data["count"] == 1
        assert data["executions"][0]["task_id"] == "T-002"

    def test_list_shows_result(self, capsys, cli_root):
        """执行有结果时一并展示 (results 节以 request_id 关联)。"""
        exec_id = self._seed_execution(capsys, cli_root)
        RuntimeStore(cli_root / "runtimes").save_result(
            ExecutionResult(id="EXR-1", request_id=exec_id, output={"summary": "done"})
        )
        rc, out, err = run_cli(capsys, cli_root, "--json", "execution", "list")
        data = json.loads(out)
        result = data["executions"][0]["result"]
        assert result["id"] == "EXR-1"
        assert result["status"] == "SUCCESS"
        assert result["output"] == {"summary": "done"}

    def test_list_emits_execution_viewed(self, capsys, cli_root):
        self._seed_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "list")
        store = open_events(cli_root)
        try:
            types = event_types(store)
            assert "execution.created" in types
            assert types[-1] == "execution.viewed"
        finally:
            store.close()
