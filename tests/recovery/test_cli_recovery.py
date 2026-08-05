"""tests/recovery/test_cli_recovery.py — CLI checkpoint/recover 命令测试。

复用 tests/cli/cli_helpers (run_cli/open_events/event_types); 中断现场经库级
调用种子 (CLI 是待测接口, 现场构造可用存储层, 同既有 CLI 测试模式)。
"""

from __future__ import annotations

import pytest

from agents.models import Agent, AgentStatus
from agents.registry import AgentRegistry
from agents.store import AgentStore
from assignment.allocator import AgentAllocator
from assignment.store import AssignmentStore
from cli_helpers import event_types, open_events, run_cli
from cli.main import main
from events.logger import EventLogger
from events.models import EventType
from events.store import EventStore
from runtime.models import ExecutionStatus
from runtime.store import RuntimeStore
from workflows.engine import WorkflowEngine
from workflows.store import WorkflowStore


def _seed_task_workflow_run(root, *, task_id: str = "T-001", steps=("s1", "s2")) -> None:
    """库级种子: 任务 + 工作流定义 + 启动 run (RUNNING, 第一步 RUNNING)。"""
    from tasks.models import Task

    TaskStore = __import__("tasks.store", fromlist=["TaskStore"]).TaskStore
    TaskStore(root / "tasks").create(
        Task(id=task_id, title=f"任务 {task_id}", project="p", type="feature",
             workflow="wf-a")
    )
    wf_store = WorkflowStore(root / "workflows")
    from workflows.models import Workflow, WorkflowStep

    wf_store.save_workflow(Workflow(
        id="wf-a", name="wf-a", description="",
        steps=[WorkflowStep(id=s, name=s, order=i + 1) for i, s in enumerate(steps)],
    ))
    with EventStore(root / "factory.db") as store:
        engine = WorkflowEngine(wf_store, task_store=TaskStore(root / "tasks"),
                                logger=EventLogger(store))
        engine.start_workflow(task_id)


def _simulate_interrupted_execution(root, *, task_id: str = "T-001", step_id: str = "s1"):
    """模拟派发中断: 创建 execution 并置 RUNNING (持久化 + 事件), 返回 execution id。"""
    runtime_store = RuntimeStore(root / "runtimes")
    with EventStore(root / "factory.db") as store:
        logger = EventLogger(store)
        engine = WorkflowEngine(WorkflowStore(root / "workflows"),
                                task_store=__import__("tasks.store", fromlist=["TaskStore"]).TaskStore(root / "tasks"),
                                logger=logger, runtime_store=runtime_store)
        request, _ = engine.execute_step(task_id, step_id)
        request.status = ExecutionStatus.RUNNING
        runtime_store.save_execution(request)
        logger.record(
            EventType.EXECUTION_STARTED, source="execution_runner", task_id=task_id,
            payload={"execution_id": request.id, "workflow_id": "wf-a", "step_id": step_id},
        )
        return request.id


def _assign_agent_working(root, *, task_id: str = "T-001", agent_id: str = "A-001"):
    """库级种子: 注册 Agent + 分配并开始工作 (Agent → WORKING, Assignment WORKING)。"""
    registry = AgentRegistry(AgentStore(root / "agents"))
    registry.register(Agent(id=agent_id, name=agent_id, role="backend-developer"))
    with EventStore(root / "factory.db") as store:
        allocator = AgentAllocator(
            AssignmentStore(root / "assignments"),
            AgentRegistry(AgentStore(root / "agents")),
            logger=EventLogger(store),
        )
        asg, _ = allocator.assign(task_id, agent_id=agent_id, workflow_id="wf-a",
                                  workflow_step_id="s1")
        allocator.start(asg.id)
    return registry.get(agent_id)


class TestCheckpointCli:
    def test_checkpoint_create(self, cli_root, capsys):
        rc, out, err = run_cli(capsys, cli_root, "task", "create", "--id", "T-001",
                               "--title", "x", "--workflow", "wf-a")
        assert rc == 0
        rc, out, err = run_cli(capsys, cli_root, "checkpoint", "create", "T-001")
        assert rc == 0, err
        assert "CKPT-T-001" in out
        assert (cli_root / "checkpoints" / "T-001.json").exists()

    def test_checkpoint_create_task_not_found(self, cli_root, capsys):
        rc, out, err = run_cli(capsys, cli_root, "checkpoint", "create", "T-999")
        assert rc == 7
        assert "task not found" in err

    def test_checkpoint_list_empty(self, cli_root, capsys):
        rc, out, err = run_cli(capsys, cli_root, "checkpoint", "list")
        assert rc == 0
        assert "0 checkpoints" in out

    def test_checkpoint_create_then_list(self, cli_root, capsys):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "x",
                "--workflow", "wf-a")
        run_cli(capsys, cli_root, "checkpoint", "create", "T-001")
        rc, out, err = run_cli(capsys, cli_root, "checkpoint", "list")
        assert rc == 0
        assert "CKPT-T-001" in out
        assert "T-001" in out

    def test_checkpoint_list_json(self, cli_root, capsys):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "x",
                "--workflow", "wf-a")
        run_cli(capsys, cli_root, "checkpoint", "create", "T-001")
        rc, out, err = run_cli(capsys, cli_root, "--json", "checkpoint", "list")
        assert rc == 0
        import json as jsonlib
        data = jsonlib.loads(out)
        assert data["count"] == 1
        assert data["checkpoints"][0]["id"] == "CKPT-T-001"

    def test_checkpoint_missing_subcommand_usage_error(self, cli_root, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "checkpoint"])
        assert exc.value.code == 2

    def test_checkpoint_create_emits_recovery_events(self, cli_root, capsys):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "x",
                "--workflow", "wf-a")
        run_cli(capsys, cli_root, "checkpoint", "create", "T-001")
        with open_events(cli_root) as store:
            types = event_types(store)
        assert "recovery.started" in types
        assert "recovery.completed" in types
        assert "recovery.failed" not in types

    def test_checkpoint_list_emits_audit_event(self, cli_root, capsys):
        run_cli(capsys, cli_root, "checkpoint", "list")
        with open_events(cli_root) as store:
            types = event_types(store)
        assert "recovery.started" in types


class TestRecoverCli:
    def test_recover_running_workflow(self, cli_root, capsys):
        """场景1 (CLI): RUNNING → 可继续。"""
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "x",
                "--workflow", "wf-a")
        run_cli(capsys, cli_root, "workflow", "add", "--id", "wf-a", "--steps", "s1,s2")
        run_cli(capsys, cli_root, "workflow", "run", "T-001")
        rc, out, err = run_cli(capsys, cli_root, "recover", "T-001")
        assert rc == 0, err
        assert "可继续" in out
        assert "continue step s1" in out
        assert "RUNNING" in out

    def test_recover_interrupted_execution_and_agent(self, cli_root, capsys):
        """场景2+3 (CLI): 中断执行重试 + Agent 释放。"""
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "x",
                "--workflow", "wf-a")
        run_cli(capsys, cli_root, "workflow", "add", "--id", "wf-a", "--steps", "s1,s2")
        run_cli(capsys, cli_root, "workflow", "run", "T-001")
        execution_id = _simulate_interrupted_execution(cli_root)
        agent = _assign_agent_working(cli_root)
        assert agent.status is AgentStatus.WORKING

        rc, out, err = run_cli(capsys, cli_root, "recover", "T-001")
        assert rc == 0, err
        assert "retry execution" in out and execution_id in out
        assert "release agent" in out
        # 副作用落盘: execution → PENDING, agent → AVAILABLE
        assert RuntimeStore(cli_root / "runtimes").get_execution(execution_id).status \
            is ExecutionStatus.PENDING
        assert AgentRegistry(AgentStore(cli_root / "agents")).get("A-001").status \
            is AgentStatus.AVAILABLE

    def test_recover_completed_rejected(self, cli_root, capsys):
        """场景4 (CLI): 已完成 → 拒绝 (rc 0, 操作成功, resume_ok=False)。"""
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "x",
                "--workflow", "wf-a")
        run_cli(capsys, cli_root, "workflow", "add", "--id", "wf-a", "--steps", "s1")
        run_cli(capsys, cli_root, "agent", "add", "--id", "A-001", "--role", "backend-developer",
                "--skills", "dev")
        run_cli(capsys, cli_root, "runtime", "add", "--id", "echo", "--type", "mock")
        rc, out, err = run_cli(capsys, cli_root, "workflow", "run", "T-001", "--auto")
        assert rc == 0, err
        rc, out, err = run_cli(capsys, cli_root, "recover", "T-001")
        assert rc == 0, err
        assert "恢复被拒绝" in out
        assert "reject recovery" in out
        assert "COMPLETED" in out

    def test_recover_task_not_found(self, cli_root, capsys):
        rc, out, err = run_cli(capsys, cli_root, "recover", "T-999")
        assert rc == 7
        assert "task not found" in err

    def test_recover_missing_arg_usage_error(self, cli_root):
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "recover"])
        assert exc.value.code == 2

    def test_recover_json_output(self, cli_root, capsys):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "x",
                "--workflow", "wf-a")
        run_cli(capsys, cli_root, "workflow", "add", "--id", "wf-a", "--steps", "s1")
        run_cli(capsys, cli_root, "workflow", "run", "T-001")
        rc, out, err = run_cli(capsys, cli_root, "--json", "recover", "T-001")
        assert rc == 0
        import json as jsonlib
        data = jsonlib.loads(out)
        rec = data["recovery"]
        assert rec["task_id"] == "T-001"
        assert rec["resume_ok"] is True
        assert rec["state"] == "RUNNING"
        assert isinstance(rec["actions"], list)

    def test_recover_emits_events(self, cli_root, capsys):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "x",
                "--workflow", "wf-a")
        run_cli(capsys, cli_root, "workflow", "add", "--id", "wf-a", "--steps", "s1")
        run_cli(capsys, cli_root, "workflow", "run", "T-001")
        run_cli(capsys, cli_root, "recover", "T-001")
        with open_events(cli_root) as store:
            types = event_types(store)
            assert "recovery.started" in types
            assert "recovery.completed" in types
            completed = [e for e in store.query(task_id="T-001")
                         if e.type is EventType.RECOVERY_COMPLETED][0]
            assert completed.payload["resume_ok"] is True

    def test_recover_failed_task_emits_failed_event(self, cli_root, capsys):
        run_cli(capsys, cli_root, "recover", "T-999")
        with open_events(cli_root) as store:
            types = event_types(store)
        assert "recovery.started" in types
        assert "recovery.failed" in types

    def test_checkpoint_then_recover_cli_roundtrip(self, cli_root, capsys):
        """手动冒烟 (测试版): 模拟中断 → checkpoint → recover → 验证恢复结果。"""
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "x",
                "--workflow", "wf-a")
        run_cli(capsys, cli_root, "workflow", "add", "--id", "wf-a", "--steps", "s1,s2")
        run_cli(capsys, cli_root, "workflow", "run", "T-001")
        execution_id = _simulate_interrupted_execution(cli_root)
        _assign_agent_working(cli_root)

        rc, out, err = run_cli(capsys, cli_root, "checkpoint", "create", "T-001")
        assert rc == 0
        rc, out, err = run_cli(capsys, cli_root, "checkpoint", "list")
        assert rc == 0 and "CKPT-T-001" in out

        rc, out, err = run_cli(capsys, cli_root, "recover", "T-001")
        assert rc == 0
        assert "可继续" in out
        assert "retry execution" in out
        assert "release agent" in out
