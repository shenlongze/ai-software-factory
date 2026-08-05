"""test_cli_execution_run.py — CLI: factory execution run/status (Echo 链路, 发 execution.* 事件)。

种子模式同 4B-1 CLI 测试: CLI 建 workflow/task/run + runtime 身份, 再经引擎
execute_step 落一条 pending 执行 (CLI 无 execute-step 命令), 最后 execution run/status。
"""

from __future__ import annotations

import json

import pytest

from cli.main import main
from cli_helpers import event_types, open_events, run_cli
from events.logger import EventLogger
from events.store import EventStore
from runtime.models import ExecutionRequest, ExecutionStatus
from runtime.store import RuntimeStore
from tasks.store import TaskStore
from workflows.engine import WorkflowEngine
from workflows.store import WorkflowStore


def _seed_cli_execution(
    capsys, cli_root, *, task_id: str = "T-001", steps: str = "s1,s2",
    runtime: bool = True, input: dict | None = None, runtime_id: str | None = None,
) -> str:
    """CLI 装配 workflow/task/run (+ runtime 身份), 经引擎 execute_step 落 pending 执行。

    - runtime=False: 不注册 runtime 身份 (测无可用 Runtime 分支)。
    - input: 覆盖执行请求输入 (测 Echo fail 分支)。
    - runtime_id: 覆盖请求显式 runtime (测未注册 runtime 分支)。
    """
    run_cli(capsys, cli_root, "workflow", "add", "--id", "wf-test", "--steps", steps)
    run_cli(capsys, cli_root, "task", "create", "--id", task_id, "--title", "任务",
            "--workflow", "wf-test")
    run_cli(capsys, cli_root, "workflow", "run", task_id)
    if runtime:
        run_cli(capsys, cli_root, "runtime", "add", "--id", "echo", "--type", "mock")
    store = EventStore(cli_root / "factory.db")
    try:
        engine = WorkflowEngine(
            WorkflowStore(cli_root / "workflows"),
            task_store=TaskStore(cli_root / "tasks"),
            runtime_store=RuntimeStore(cli_root / "runtimes"),
            logger=EventLogger(store),  # execution.created 同样入事件库
        )
        req, _ = engine.execute_step(task_id, steps.split(",")[0])
        if input is not None or runtime_id is not None:
            req = req.model_copy(update={
                "input": input if input is not None else req.input,
                "runtime_id": runtime_id if runtime_id is not None else req.runtime_id,
            })
            RuntimeStore(cli_root / "runtimes").save_execution(req)
    finally:
        store.close()
    return req.id


class TestExecutionRun:
    def test_run_ok(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root, steps="s1")
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id)
        assert rc == 0
        assert exec_id in out and "echo" in out and "SUCCESS" in out
        assert "workflow" in out

    def test_run_json(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root, steps="s1")
        rc, out, err = run_cli(capsys, cli_root, "--json", "execution", "run", exec_id)
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True
        assert data["status"] == "SUCCESS"
        assert data["runtime"] == "echo"
        assert data["execution"]["runtime_id"] == "echo"
        assert data["result"]["status"] == "SUCCESS"
        assert data["result"]["output"]["runtime_id"] == "echo"
        assert data["workflow"]["step_completed"] is True
        assert data["events"] == ["execution.started", "execution.completed"]

    def test_run_persists_success(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id)
        store = RuntimeStore(cli_root / "runtimes")
        assert store.get_execution(exec_id).status is ExecutionStatus.SUCCESS
        assert store.get_result(exec_id).status is ExecutionStatus.SUCCESS

    def test_run_full_event_chain_success(self, capsys, cli_root):
        """成功链路事件序尾部: started → completed → step.completed → workflow.completed。"""
        exec_id = _seed_cli_execution(capsys, cli_root, steps="s1")
        run_cli(capsys, cli_root, "execution", "run", exec_id)
        store = open_events(cli_root)
        try:
            types = event_types(store)
            assert types[-4:] == [
                "execution.started", "execution.completed",
                "workflow.step.completed", "workflow.completed",
            ]
        finally:
            store.close()

    def test_run_multi_step_keeps_workflow_running(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root, steps="s1,s2")
        run_cli(capsys, cli_root, "execution", "run", exec_id)
        store = open_events(cli_root)
        try:
            types = event_types(store)
            assert types[-3:] == [
                "execution.started", "execution.completed", "workflow.step.completed",
            ]
        finally:
            store.close()

    def test_run_failed_input_status_failed(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root, input={"fail": "boom"})
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id)
        assert rc == 0  # run 命令本身成功; 业务结果为 FAILED
        assert "FAILED" in out and "boom" in out

    def test_run_failed_json(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root, input={"fail": "boom"})
        rc, out, err = run_cli(capsys, cli_root, "--json", "execution", "run", exec_id)
        data = json.loads(out)
        assert data["status"] == "FAILED"
        assert data["result"]["error"] == "boom"
        assert data["workflow"]["workflow_failed"] is True
        assert data["events"] == ["execution.started", "execution.failed"]

    def test_run_failed_emits_workflow_failed(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root, input={"fail": "boom"})
        run_cli(capsys, cli_root, "execution", "run", exec_id)
        store = open_events(cli_root)
        try:
            types = event_types(store)
            assert types[-2:] == ["execution.failed", "workflow.failed"]
        finally:
            store.close()

    def test_run_not_found_rc7(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", "EX-999")
        assert rc == 7
        assert "not found" in err

    def test_run_no_available_runtime_rc1(self, capsys, cli_root):
        """未注册任何 runtime → 状态冲突 rc 1, 执行保持 PENDING。"""
        exec_id = _seed_cli_execution(capsys, cli_root, runtime=False)
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id)
        assert rc == 1
        assert "no available runtime" in err
        assert RuntimeStore(cli_root / "runtimes").get_execution(exec_id).status is ExecutionStatus.PENDING

    def test_run_unknown_runtime_rc7(self, capsys, cli_root):
        """请求显式指定未注册 runtime → 未找到 rc 7。"""
        exec_id = _seed_cli_execution(capsys, cli_root, runtime_id="R-999")
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id)
        assert rc == 7
        assert "R-999" in err

    def test_run_state_conflict_rc1(self, capsys, cli_root):
        """已执行的请求不可重跑 (results 1:1) → 状态冲突 rc 1。"""
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id)
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id)
        assert rc == 1
        assert "expected PENDING" in err

    def test_run_missing_arg_usage_error(self, cli_root):
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "execution", "run"])
        assert exc.value.code == 2

    def test_run_registered_runtime_without_impl_rc1(self, capsys, cli_root):
        """身份已注册但无实现 → 配置缺口 rc 1 (RuntimeAdapterNotFoundError)。"""
        exec_id = _seed_cli_execution(capsys, cli_root, runtime=True)
        # 把 echo 身份移除, 换注册一个无实现的 runtime
        RuntimeStore(cli_root / "runtimes").remove_runtime("echo")
        run_cli(capsys, cli_root, "runtime", "add", "--id", "R-001")
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id)
        assert rc == 1
        assert "no adapter implementation" in err


class TestExecutionStatus:
    def test_status_pending(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "execution", "status", exec_id)
        assert rc == 0
        assert "PENDING" in out and "(尚无结果)" in out

    def test_status_after_run(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id)
        rc, out, err = run_cli(capsys, cli_root, "execution", "status", exec_id)
        assert rc == 0
        assert "SUCCESS" in out and "echo" in out

    def test_status_json(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id)
        rc, out, err = run_cli(capsys, cli_root, "--json", "execution", "status", exec_id)
        data = json.loads(out)
        assert data["ok"] is True
        assert data["execution"]["id"] == exec_id
        assert data["execution"]["status"] == "SUCCESS"
        assert data["result"]["status"] == "SUCCESS"

    def test_status_not_found_rc7(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "execution", "status", "EX-999")
        assert rc == 7
        assert "not found" in err

    def test_status_emits_execution_viewed(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "status", exec_id)
        store = open_events(cli_root)
        try:
            types = event_types(store)
            assert "execution.created" in types
            assert types[-1] == "execution.viewed"
        finally:
            store.close()

    def test_status_missing_arg_usage_error(self, cli_root):
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "execution", "status"])
        assert exc.value.code == 2
