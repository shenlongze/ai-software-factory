"""test_workflow_execute_step.py — WorkflowEngine.execute_step 边界:
创建 pending execution (绑定 workflow/task/step + agent_id 解析), 不自动执行 Runtime。"""

from __future__ import annotations

import pytest

from runtime.models import ExecutionRequest, ExecutionStatus
from workflows.engine import (
    StepNotFoundError,
    StepNotReadyError,
    WorkflowEngine,
    WorkflowEngineError,
    WorkflowRunNotFoundError,
    WorkflowStateError,
)
from workflows.models import StepStatus, WorkflowRun, WorkflowStatus

from runtime_helpers import make_task, make_workflow


class _Ready:
    """把任务 + 工作流 + run 装配到 RUNNING (第一步自动 RUNNING) 的公共前置。"""

    @staticmethod
    def setup(engine, task_store, workflow_store, task_id: str = "T-001", steps=("s1", "s2")):
        workflow_store.save_workflow(make_workflow("wf-test", steps=list(steps)))
        task_store.create(make_task(task_id, workflow="wf-test"))
        engine.start_workflow(task_id)


class TestExecuteStepBasics:
    def test_returns_pending_request(self, engine, task_store, workflow_store):
        _Ready.setup(engine, task_store, workflow_store)
        req, ev = engine.execute_step("T-001", "s1")
        assert isinstance(req, ExecutionRequest)
        assert req.status is ExecutionStatus.PENDING  # 创建即 PENDING, 不自动执行
        assert ev is None  # 无 logger → 纯存储

    def test_binds_task_workflow_step(self, engine, task_store, workflow_store):
        _Ready.setup(engine, task_store, workflow_store)
        req, _ = engine.execute_step("T-001", "s1")
        assert req.task_id == "T-001"
        assert req.workflow_id == "wf-test"
        assert req.step_id == "s1"

    def test_persists_to_runtime_store(self, engine, runtime_store, task_store, workflow_store):
        _Ready.setup(engine, task_store, workflow_store)
        req, _ = engine.execute_step("T-001", "s1")
        assert runtime_store.get_execution(req.id) == req

    def test_execution_id_auto_increment(self, engine, task_store, workflow_store):
        _Ready.setup(engine, task_store, workflow_store)
        req1, _ = engine.execute_step("T-001", "s1")
        assert req1.id == "EX-001"
        engine.complete_step("T-001", "s1")  # 推进当前步骤 → s2
        req2, _ = engine.execute_step("T-001", "s2")
        assert req2.id == "EX-002"

    def test_does_not_change_step_state(self, engine, task_store, workflow_store):
        """边界: 创建 execution 不推进步骤 (派发属 4B-2)。"""
        _Ready.setup(engine, task_store, workflow_store)
        before = engine.status("T-001").step_state("s1").status
        engine.execute_step("T-001", "s1")
        after = engine.status("T-001").step_state("s1").status
        assert before is StepStatus.RUNNING and after is StepStatus.RUNNING

    def test_no_result_created(self, engine, runtime_store, task_store, workflow_store):
        """边界: 无 Runtime 被调用 → 无 ExecutionResult。"""
        _Ready.setup(engine, task_store, workflow_store)
        engine.execute_step("T-001", "s1")
        assert runtime_store.list_results() == []

    def test_runtime_id_left_empty(self, engine, task_store, workflow_store):
        """runtime_id 本阶段恒空 (尚无 Runtime 实现, 派发层 4B-2 填充)。"""
        _Ready.setup(engine, task_store, workflow_store)
        req, _ = engine.execute_step("T-001", "s1")
        assert req.runtime_id is None


class TestExecuteStepPreconditions:
    def test_no_runtime_store_raises(self, workflow_store, task_store):
        engine = WorkflowEngine(workflow_store, task_store=task_store)  # 无 runtime_store
        with pytest.raises(WorkflowEngineError, match="runtime store"):
            engine.execute_step("T-001", "s1")

    def test_no_run_raises(self, engine, task_store, workflow_store):
        with pytest.raises(WorkflowRunNotFoundError):
            engine.execute_step("T-001", "s1")

    def test_run_not_running_raises(self, engine, task_store, workflow_store):
        """run 终态 (COMPLETED) → 拒绝创建执行。"""
        workflow_store.save_workflow(make_workflow("wf-test", steps=["s1"]))
        task_store.create(make_task("T-001", workflow="wf-test"))
        engine.start_workflow("T-001")
        engine.complete_step("T-001", "s1")
        with pytest.raises(WorkflowStateError, match="not running"):
            engine.execute_step("T-001", "s1")

    def test_unknown_step_raises(self, engine, task_store, workflow_store):
        _Ready.setup(engine, task_store, workflow_store)
        with pytest.raises(StepNotFoundError):
            engine.execute_step("T-001", "nope")

    def test_not_current_step_raises(self, engine, task_store, workflow_store):
        """顺序纪律: 只能为当前步骤 (按 order 第一个未完成) 创建执行。"""
        _Ready.setup(engine, task_store, workflow_store)
        with pytest.raises(StepNotReadyError, match="not the current step"):
            engine.execute_step("T-001", "s2")  # 当前是 s1

    def test_terminal_step_raises(self, engine, runtime_store, task_store, workflow_store):
        """防御分支: run RUNNING 但当前步骤已 FAILED (手工构造终态步骤)。"""
        workflow_store.save_workflow(make_workflow("wf-test", steps=["s1"]))
        run = WorkflowRun.from_workflow(
            run_id="WR-001", workflow=workflow_store.get_workflow("wf-test"), task_id="T-001",
        )
        run.step_state("s1").status = StepStatus.FAILED
        run.status = WorkflowStatus.RUNNING
        workflow_store.save_run(run)
        with pytest.raises(StepNotReadyError, match="terminal state"):
            engine.execute_step("T-001", "s1")

    def test_pending_current_step_allowed(self, engine, runtime_store, task_store, workflow_store):
        """PENDING 的当前步骤也允许创建 (步骤保持 PENDING, 不自动启动)。"""
        workflow_store.save_workflow(make_workflow("wf-test", steps=["s1"]))
        run = WorkflowRun.from_workflow(
            run_id="WR-001", workflow=workflow_store.get_workflow("wf-test"), task_id="T-001",
        )
        run.status = WorkflowStatus.RUNNING
        workflow_store.save_run(run)
        req, _ = engine.execute_step("T-001", "s1")
        assert req.status is ExecutionStatus.PENDING
        assert engine.status("T-001").step_state("s1").status is StepStatus.PENDING


class TestExecuteStepAgentResolution:
    """agent_id 解析 (ADR-0006 决策 4): task.owner 精确引用 → 否则留空。"""

    def test_agent_id_from_owner(self, agent_store, runtime_store, workflow_store, task_store):
        from agents.models import Agent
        from agents.registry import AgentRegistry

        agent_registry = AgentRegistry(agent_store)
        agent_registry.register(Agent(id="A-001", name="a1", role="dev"))
        engine = WorkflowEngine(
            workflow_store, task_store=task_store, runtime_store=runtime_store,
            agent_registry=agent_registry,
        )
        workflow_store.save_workflow(make_workflow("wf-test", steps=["s1"]))
        task_store.create(make_task("T-001", workflow="wf-test", owner="A-001"))
        engine.start_workflow("T-001")
        req, _ = engine.execute_step("T-001", "s1")
        assert req.agent_id == "A-001"

    def test_agent_id_none_without_registry(self, engine, task_store, workflow_store):
        """engine 无 agent_registry → 留空。"""
        _Ready.setup(engine, task_store, workflow_store)
        req, _ = engine.execute_step("T-001", "s1")
        assert req.agent_id is None

    def test_agent_id_none_when_owner_unregistered(self, agent_store, runtime_store, workflow_store, task_store):
        from agents.registry import AgentRegistry

        engine = WorkflowEngine(
            workflow_store, task_store=task_store, runtime_store=runtime_store,
            agent_registry=AgentRegistry(agent_store),
        )
        workflow_store.save_workflow(make_workflow("wf-test", steps=["s1"]))
        task_store.create(make_task("T-001", workflow="wf-test", owner="A-999"))  # 未注册
        engine.start_workflow("T-001")
        req, _ = engine.execute_step("T-001", "s1")
        assert req.agent_id is None

    def test_agent_id_none_when_no_owner(self, engine, task_store, workflow_store):
        _Ready.setup(engine, task_store, workflow_store)
        req, _ = engine.execute_step("T-001", "s1")
        assert req.agent_id is None

    def test_agent_id_from_owner_after_reload(self, agent_store, runtime_store, workflow_store, task_store):
        """owner 解析读注册表 (跨进程/重载后仍命中)。"""
        from agents.models import Agent
        from agents.registry import AgentRegistry

        AgentRegistry(agent_store).register(Agent(id="A-001", name="a1", role="dev"))
        engine = WorkflowEngine(
            workflow_store, task_store=task_store, runtime_store=runtime_store,
            agent_registry=AgentRegistry(agent_store),
        )
        workflow_store.save_workflow(make_workflow("wf-test", steps=["s1"]))
        task_store.create(make_task("T-001", workflow="wf-test", owner="A-001"))
        engine.start_workflow("T-001")
        req, _ = engine.execute_step("T-001", "s1")
        assert req.agent_id == "A-001"


class TestExecuteStepEventIntegration:
    def test_emits_execution_created_with_logger(self, event_engine, task_store, workflow_store):
        workflow_store.save_workflow(make_workflow("wf-test", steps=["s1"]))
        task_store.create(make_task("T-001", workflow="wf-test"))
        event_engine.start_workflow("T-001")
        req, ev = event_engine.execute_step("T-001", "s1")
        assert ev is not None and ev.type.value == "execution.created"
        assert ev.payload["execution_id"] == req.id
        assert ev.payload["status"] == "PENDING"

    def test_execute_step_is_boundary_only(self, engine, task_store, workflow_store, runtime_store):
        """边界验证: 创建 execution 不自动执行 — 无结果、步骤状态不变、无 runtime 派发。"""
        _Ready.setup(engine, task_store, workflow_store)
        engine.execute_step("T-001", "s1")
        assert runtime_store.list_results() == []
        assert engine.status("T-001").step_state("s1").status is StepStatus.RUNNING
        assert len(runtime_store.list_executions()) == 1
