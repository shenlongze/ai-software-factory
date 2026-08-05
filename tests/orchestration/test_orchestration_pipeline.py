"""test_orchestration_pipeline.py — orchestration.pipeline.execute_workflow(task_id) 完整链路。

覆盖: 组合根装配 (全部既有模块, 不复制) / 成功链路 (store 维度持久化) / 失败路径
(无 Agent / 无 Runtime / 前置错误) / 自定义 adapters / 无 logger 纯存储场景 /
事件经 EventLogger 落库 (与 workflow.*/assignment.*/execution.* 全序)。
"""

from __future__ import annotations

from agents.models import AgentStatus
from agents.registry import AgentRegistry
from events.logger import EventLogger
from events.models import EventType
from orchestration.pipeline import execute_workflow
from workflows.engine import WorkflowEngine
from workflows.models import WorkflowStatus

from conftest import (
    FailingAdapter,
    make_agent,
    make_step,
    make_task,
    make_workflow,
    seed_agent,
    seed_runtime,
    seed_task,
    seed_workflow,
)


class TestPipelineSuccess:
    def test_full_chain_completed(self, workflow_store, task_store, agent_store,
                                  assignment_store, runtime_store, logger):
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
        )

        assert outcome.ok
        assert outcome.status is WorkflowStatus.COMPLETED
        assert outcome.workflow_id == "wf-auto"
        assert outcome.run_id.startswith("WR-")
        assert len(outcome.steps) == 1

    def test_workflow_run_persisted(self, workflow_store, task_store, agent_store,
                                    assignment_store, runtime_store, logger):
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        execute_workflow("T-001", workflow_store=workflow_store, task_store=task_store,
                         agent_store=agent_store, assignment_store=assignment_store,
                         runtime_store=runtime_store, logger=logger)

        engine = WorkflowEngine(workflow_store, task_store=task_store)
        run = engine.status("T-001")
        assert run is not None and run.status is WorkflowStatus.COMPLETED
        assert run.all_steps_completed()

    def test_full_event_sequence_in_store(self, workflow_store, task_store, agent_store,
                                          assignment_store, runtime_store, logger):
        """全事件序: orchestration.started 在 workflow.started 前; completed 收尾。"""
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        execute_workflow("T-001", workflow_store=workflow_store, task_store=task_store,
                         agent_store=agent_store, assignment_store=assignment_store,
                         runtime_store=runtime_store, logger=logger)

        types = [e.type.value for e in logger.store.query()]
        assert types[0] == "orchestration.started"
        assert "workflow.started" in types
        assert "workflow.step.started" in types
        assert "agent.assignment.created" in types
        assert "agent.assignment.started" in types
        assert "agent.assignment.completed" in types
        assert "agent.released" in types
        assert "execution.created" in types
        assert "execution.started" in types
        assert "execution.completed" in types
        assert "workflow.step.completed" in types
        assert "orchestration.step.started" in types
        assert "orchestration.step.completed" in types
        assert "workflow.completed" in types
        assert types[-1] == "orchestration.completed"

    def test_events_carry_audit_dimensions(self, workflow_store, task_store, agent_store,
                                           assignment_store, runtime_store, logger):
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        execute_workflow("T-001", workflow_store=workflow_store, task_store=task_store,
                         agent_store=agent_store, assignment_store=assignment_store,
                         runtime_store=runtime_store, logger=logger)

        events = logger.store.query()
        step_ev = [e for e in events if e.type is EventType.ORCHESTRATION_STEP_STARTED][0]
        assert step_ev.task_id == "T-001"
        assert step_ev.payload["step_id"] == "dev"
        # workflow.* 事件带 run_id 审计维度
        started = [e for e in events if e.type is EventType.WORKFLOW_STARTED][0]
        assert started.payload["run_id"].startswith("WR-")

    def test_multi_step_chain(self, workflow_store, task_store, agent_store,
                              assignment_store, runtime_store, logger):
        wf = make_workflow(steps=[
            make_step("a", 1, skill="x", role="r1"),
            make_step("b", 2, skill="y", role="r2"),
        ])
        seed_workflow(workflow_store, wf)
        seed_agent(agent_store, make_agent("A-001", role="r1", skills=["x"]))
        seed_agent(agent_store, make_agent("A-002", role="r2", skills=["y"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
        )

        assert outcome.ok
        assert [s.step_id for s in outcome.steps] == ["a", "b"]
        assert [s.agent_id for s in outcome.steps] == ["A-001", "A-002"]
        assert len(runtime_store.list_executions()) == 2
        assert len(assignment_store.list()) == 2

    def test_no_logger_pure_storage(self, workflow_store, task_store, agent_store,
                                    assignment_store, runtime_store):
        """logger 缺省 (库/纯存储场景): 链路照常, outcome.events 为空。"""
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store,
        )

        assert outcome.ok
        assert outcome.events == []
        assert outcome.steps[0].status.value == "COMPLETED"


class TestPipelineFailure:
    def test_no_agent_failed(self, workflow_store, task_store, agent_store,
                             assignment_store, runtime_store, logger):
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="wrong", skills=["wrong"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
        )

        assert not outcome.ok
        assert "no available agent" in (outcome.error or "")
        engine = WorkflowEngine(workflow_store, task_store=task_store)
        assert engine.status("T-001").status is WorkflowStatus.FAILED
        assert outcome.events[-1].type is EventType.ORCHESTRATION_FAILED

    def test_no_runtime_failed(self, workflow_store, task_store, agent_store,
                               assignment_store, runtime_store, logger):
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        # 不注册 runtime

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
        )

        assert not outcome.ok
        assert "no available runtime" in (outcome.error or "")
        assert AgentRegistry(agent_store).get("A-001").status is AgentStatus.AVAILABLE

    def test_execution_failed_with_custom_adapter(self, workflow_store, task_store,
                                                  agent_store, assignment_store,
                                                  runtime_store, logger):
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
            adapters={"echo": FailingAdapter()},
        )

        assert not outcome.ok
        assert "boom" in (outcome.error or "")
        assert outcome.run.status is WorkflowStatus.FAILED
        # 失败事件序: 无 step.completed/completed
        types = [e.type.value for e in outcome.events]
        assert "orchestration.step.completed" not in types
        assert "orchestration.completed" not in types
        assert types[-1] == "orchestration.failed"

    def test_task_not_found_failed(self, workflow_store, task_store, agent_store,
                                   assignment_store, runtime_store, logger):
        seed_workflow(workflow_store, make_workflow())
        outcome = execute_workflow(
            "T-999", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
        )
        assert not outcome.ok
        assert "task not found" in (outcome.error or "")
        # 前置错误: 未创建运行实例
        engine = WorkflowEngine(workflow_store, task_store=task_store)
        assert engine.status("T-999") is None

    def test_no_half_completed_after_failure(self, workflow_store, task_store, agent_store,
                                             assignment_store, runtime_store, logger):
        """失败即整体 FAILED: 运行实例终态 FAILED, 步骤无 COMPLETED 混入。"""
        wf = make_workflow(steps=[
            make_step("a", 1, skill="x", role="r1"),
            make_step("b", 2, skill="y", role="r2"),
        ])
        seed_workflow(workflow_store, wf)
        seed_agent(agent_store, make_agent("A-001", role="r1", skills=["x"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
            adapters={"echo": FailingAdapter()},
        )

        assert outcome.run is not None
        assert outcome.run.status is WorkflowStatus.FAILED
        statuses = [st.status.value for st in outcome.run.step_states]
        assert "COMPLETED" not in statuses
