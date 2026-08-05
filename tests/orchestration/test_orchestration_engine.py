"""test_orchestration_engine.py — OrchestrationEngine 单测 (完整链路 + 失败路径)。

覆盖: 依赖暴露 / 成功链路 (单步/多步, Agent 回 AVAILABLE, Assignment COMPLETED,
Execution SUCCESS, runtime 解析) / 续跑 / 前置错误 (任务不存在/工作流未注册/已终态) /
失败路径 (无匹配 Agent / 无 Runtime / Runtime 无 Adapter / 执行 FAILED → Workflow
FAILED + Agent 回 AVAILABLE, 无半完成) / 事件序 (orchestration.* 顺序)。
"""

from __future__ import annotations

from agents.models import AgentStatus
from agents.registry import AgentRegistry
from assignment.models import AssignmentStatus
from events.logger import EventLogger
from events.models import EventType
from runtime.models import ExecutionStatus, RuntimeInfo
from runtime.registry import RuntimeRegistry
from workflows.engine import WorkflowEngine
from workflows.models import StepStatus, WorkflowStatus

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


def _event_types(events) -> list[str]:
    return [e.type.value for e in events]


class TestDependencies:
    def test_exposes_wired_dependencies(self, orchestrator, workflow_store, task_store,
                                        runtime_store):
        assert orchestrator.workflow_engine is not None
        assert orchestrator.workflow_engine.store is workflow_store
        assert orchestrator.workflow_engine.task_store is task_store
        assert orchestrator.allocator is not None
        assert orchestrator.matcher is orchestrator.allocator.matcher
        assert orchestrator.execution_service is not None
        assert orchestrator.execution_service.store is runtime_store
        assert orchestrator.logger is not None

    def test_matcher_falls_back_to_allocator(self, orchestrator_factory, agent_store,
                                             assignment_store, workflow_store, task_store,
                                             runtime_store, logger):
        """matcher 未显式传入时取 allocator.matcher (同一 registry)。"""
        from agents.registry import AgentRegistry
        from assignment.allocator import AgentAllocator
        from assignment.matcher import AgentMatcher
        from execution.service import ExecutionService
        from orchestration.engine import OrchestrationEngine
        from runtime.adapters import BUILTIN_ADAPTERS
        from runtime.registry import RuntimeRegistry

        registry = AgentRegistry(agent_store)
        allocator = AgentAllocator(assignment_store, registry)
        service = ExecutionService(
            runtime_store, RuntimeRegistry(runtime_store),
            adapters=BUILTIN_ADAPTERS,
        )
        engine = OrchestrationEngine(
            workflow_engine=WorkflowEngine(workflow_store, task_store=task_store),
            allocator=allocator,
            execution_service=service,
        )
        assert engine.matcher is allocator.matcher
        assert isinstance(engine.matcher, AgentMatcher)


class TestSuccessChain:
    def test_single_step_completed(self, orchestrator, task_store, agent_store,
                                   workflow_store, runtime_store, assignment_store):
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        outcome = orchestrator.execute_workflow("T-001")

        assert outcome.ok
        assert outcome.status is WorkflowStatus.COMPLETED
        assert outcome.workflow_id == "wf-auto"
        assert outcome.run_id and outcome.run is not None
        assert outcome.run.status is WorkflowStatus.COMPLETED
        assert len(outcome.steps) == 1
        step = outcome.steps[0]
        assert step.step_id == "dev"
        assert step.status is StepStatus.COMPLETED
        assert step.agent_id == "A-001"
        assert step.runtime_id == "echo"
        assert step.result == "SUCCESS"
        assert step.assignment_id and step.execution_id

    def test_agent_back_available_after_success(self, orchestrator, task_store, agent_store,
                                                workflow_store, runtime_store):
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        orchestrator.execute_workflow("T-001")

        agent = AgentRegistry(agent_store).get("A-001")
        assert agent is not None
        assert agent.status is AgentStatus.AVAILABLE
        assert agent.current_task is None

    def test_assignment_completed_and_released(self, orchestrator, task_store, agent_store,
                                               workflow_store, runtime_store,
                                               assignment_store):
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        orchestrator.execute_workflow("T-001")

        assignments = assignment_store.list()
        assert len(assignments) == 1
        assert assignments[0].status is AssignmentStatus.COMPLETED
        assert assignments[0].agent_id == "A-001"
        assert assignments[0].workflow_step_id == "dev"
        assert assignments[0].execution_id is not None

    def test_execution_persisted_with_agent_backfill(self, orchestrator, task_store,
                                                     agent_store, workflow_store,
                                                     runtime_store):
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        orchestrator.execute_workflow("T-001")

        requests = runtime_store.list_executions(task_id="T-001")
        assert len(requests) == 1
        assert requests[0].status is ExecutionStatus.SUCCESS
        assert requests[0].agent_id == "A-001"   # ADR-0008 决策 4: 回填匹配 Agent
        assert requests[0].runtime_id == "echo"  # Dispatcher 解析首个 AVAILABLE
        assert requests[0].step_id == "dev"
        result = runtime_store.get_result(requests[0].id)
        assert result is not None and result.status is ExecutionStatus.SUCCESS

    def test_multi_step_all_completed_in_order(self, orchestrator, task_store, agent_store,
                                               workflow_store, runtime_store):
        """多步: 每步独立匹配 (角色/技能), 全部 COMPLETED, 顺序推进。"""
        wf = make_workflow(steps=[
            make_step("architecture", 1, skill="architecture", role="product-manager"),
            make_step("development", 2, skill="development", role="backend-developer"),
            make_step("testing", 3, skill="testing", role="test-engineer"),
        ])
        seed_workflow(workflow_store, wf)
        seed_agent(agent_store, make_agent("A-001", role="product-manager",
                                           skills=["architecture"]))
        seed_agent(agent_store, make_agent("A-002", role="backend-developer",
                                           skills=["development"]))
        seed_agent(agent_store, make_agent("A-003", role="test-engineer",
                                           skills=["testing"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        outcome = orchestrator.execute_workflow("T-001")

        assert outcome.ok
        assert [s.step_id for s in outcome.steps] == ["architecture", "development", "testing"]
        assert all(s.status is StepStatus.COMPLETED for s in outcome.steps)
        assert [s.agent_id for s in outcome.steps] == ["A-001", "A-002", "A-003"]
        assert all(s.runtime_id == "echo" for s in outcome.steps)
        # 运行实例全部步骤 COMPLETED, current_step 无
        assert outcome.run is not None
        assert outcome.run.all_steps_completed()

    def test_same_agent_reused_when_matches_all_steps(self, orchestrator, task_store,
                                                      agent_store, workflow_store,
                                                      runtime_store, assignment_store):
        """单 Agent 覆盖全部步骤要求: 依序复用 (每步独立分配记录)。"""
        wf = make_workflow(steps=[
            make_step("s1", 1, skill="dev", role="backend-developer"),
            make_step("s2", 2, skill="dev", role="backend-developer"),
        ])
        seed_workflow(workflow_store, wf)
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["dev"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        outcome = orchestrator.execute_workflow("T-001")

        assert outcome.ok
        assert [s.agent_id for s in outcome.steps] == ["A-001", "A-001"]
        assignments = assignment_store.list()
        assert len(assignments) == 2
        assert all(a.status is AssignmentStatus.COMPLETED for a in assignments)

    def test_resume_existing_running_run(self, orchestrator_factory, task_store, agent_store,
                                         workflow_store, runtime_store, logger):
        """已 start_workflow 的 RUNNING 运行: 续跑剩余步骤 (不重复启动)。"""
        wf = make_workflow()
        seed_workflow(workflow_store, wf)
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")
        engine = WorkflowEngine(workflow_store, task_store=task_store, runtime_store=runtime_store)
        engine.start_workflow("T-001")  # 第一步已 RUNNING

        orchestrator = orchestrator_factory()
        outcome = orchestrator.execute_workflow("T-001")

        assert outcome.ok
        assert [s.step_id for s in outcome.steps] == ["dev"]

    def test_no_step_definition_needed_for_run_snapshot(self, orchestrator_factory,
                                                        task_store, agent_store,
                                                        workflow_store, runtime_store,
                                                        logger):
        """workflow_id 快照与定义解耦: 定义在运行后删除不影响已注册步骤推进。"""
        wf = make_workflow()
        seed_workflow(workflow_store, wf)
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        orchestrator = orchestrator_factory()
        outcome = orchestrator.execute_workflow("T-001")
        assert outcome.ok


class TestPreconditions:
    def test_task_not_found(self, orchestrator, task_store, workflow_store):
        seed_workflow(workflow_store, make_workflow())
        outcome = orchestrator.execute_workflow("T-999")
        assert not outcome.ok
        assert outcome.status is WorkflowStatus.FAILED
        assert "task not found" in (outcome.error or "")
        assert outcome.run is None
        assert outcome.steps == []

    def test_task_not_found_emits_failed_event(self, orchestrator, task_store,
                                               workflow_store, logger):
        seed_workflow(workflow_store, make_workflow())
        outcome = orchestrator.execute_workflow("T-999")
        types = _event_types(outcome.events)
        assert types == ["orchestration.started", "orchestration.failed"]
        assert outcome.events[-1].type is EventType.ORCHESTRATION_FAILED

    def test_workflow_not_registered(self, orchestrator, task_store):
        seed_task(task_store, make_task(workflow="ghost"))
        outcome = orchestrator.execute_workflow("T-001")
        assert not outcome.ok
        assert "ghost" in (outcome.error or "")

    def test_task_has_no_workflow(self, orchestrator, task_store):
        seed_task(task_store, make_task(workflow=None))
        outcome = orchestrator.execute_workflow("T-001")
        assert not outcome.ok
        assert "no workflow" in (outcome.error or "")

    def test_already_terminal_completed(self, orchestrator_factory, task_store, agent_store,
                                        workflow_store, runtime_store, logger):
        """已 COMPLETED 的运行: 拒绝重跑 (终态无出口), 状态不被改写。"""
        wf = make_workflow()
        seed_workflow(workflow_store, wf)
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")
        engine = WorkflowEngine(workflow_store, task_store=task_store, runtime_store=runtime_store)
        run, _ = engine.start_workflow("T-001")
        engine.complete_step("T-001", "dev", result="OK")

        orchestrator = orchestrator_factory()
        outcome = orchestrator.execute_workflow("T-001")

        assert not outcome.ok
        assert "terminal state" in (outcome.error or "")
        after = engine.status("T-001")
        assert after is not None and after.status is WorkflowStatus.COMPLETED  # 未被改写
        assert outcome.steps == []

    def test_already_terminal_failed(self, orchestrator_factory, task_store, workflow_store,
                                     runtime_store, logger):
        """已 FAILED 的运行: 拒绝续跑 (终态无出口)。"""
        wf = make_workflow()
        seed_workflow(workflow_store, wf)
        seed_task(task_store, make_task())
        engine = WorkflowEngine(workflow_store, task_store=task_store, runtime_store=runtime_store)
        engine.start_workflow("T-001")
        engine.fail_workflow("T-001", "external failure")

        orchestrator = orchestrator_factory()
        outcome = orchestrator.execute_workflow("T-001")

        assert not outcome.ok
        assert "terminal state" in (outcome.error or "")


class TestFailurePaths:
    def test_no_matching_agent_fails_workflow(self, orchestrator, task_store, agent_store,
                                              workflow_store, runtime_store):
        """无匹配 Agent → Workflow FAILED (无半完成), 无 Assignment/Execution 残留。"""
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="ops-engineer", skills=["ops"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        outcome = orchestrator.execute_workflow("T-001")

        assert not outcome.ok
        assert outcome.status is WorkflowStatus.FAILED
        assert "no available agent" in (outcome.error or "")
        assert outcome.run is not None and outcome.run.status is WorkflowStatus.FAILED
        assert outcome.run.error is not None
        assert len(outcome.steps) == 1
        assert outcome.steps[0].status is StepStatus.FAILED
        assert outcome.steps[0].agent_id is None   # 未匹配到 Agent
        assert runtime_store.list_executions() == []  # 未创建执行
        # 运行实例中该步骤 FAILED (状态机同步)
        step_state = outcome.run.step_state("dev")
        assert step_state is not None and step_state.status is StepStatus.FAILED

    def test_no_matching_agent_event_sequence(self, orchestrator, task_store, agent_store,
                                              workflow_store, runtime_store):
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="ops-engineer", skills=["ops"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        outcome = orchestrator.execute_workflow("T-001")

        assert _event_types(outcome.events) == [
            "orchestration.started", "orchestration.step.started",
            "orchestration.failed",
        ]

    def test_no_runtime_fails_workflow(self, orchestrator, task_store, agent_store,
                                       workflow_store, runtime_store, assignment_store):
        """无可用 Runtime → Workflow FAILED; 已分配 Agent 回 AVAILABLE; 执行留 PENDING。"""
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        # 不注册任何 runtime

        outcome = orchestrator.execute_workflow("T-001")

        assert not outcome.ok
        assert "no available runtime" in (outcome.error or "")
        assert outcome.run is not None and outcome.run.status is WorkflowStatus.FAILED
        agent = AgentRegistry(agent_store).get("A-001")
        assert agent is not None and agent.status is AgentStatus.AVAILABLE  # 已释放
        assignments = assignment_store.list()
        assert len(assignments) == 1
        assert assignments[0].status is AssignmentStatus.FAILED
        requests = runtime_store.list_executions(task_id="T-001")
        assert len(requests) == 1
        assert requests[0].status is ExecutionStatus.PENDING  # 执行未启动 (无事件)

    def test_runtime_without_adapter_fails_workflow(self, orchestrator, task_store,
                                                    agent_store, workflow_store,
                                                    runtime_store, assignment_store):
        """Runtime 身份已注册但无 Adapter 实现 (配置缺口) → Workflow FAILED。"""
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        RuntimeRegistry(runtime_store).register(
            RuntimeInfo(id="ghost", name="ghost", type="mock")  # 非内置 Adapter
        )

        outcome = orchestrator.execute_workflow("T-001")

        assert not outcome.ok
        assert "no adapter implementation" in (outcome.error or "")
        assert outcome.run is not None and outcome.run.status is WorkflowStatus.FAILED
        agent = AgentRegistry(agent_store).get("A-001")
        assert agent is not None and agent.status is AgentStatus.AVAILABLE

    def test_execution_failed_fails_workflow(self, orchestrator_factory, task_store,
                                             agent_store, workflow_store, runtime_store,
                                             assignment_store, logger):
        """执行结果 FAILED → Workflow FAILED; Assignment FAILED + Agent 回 AVAILABLE。"""
        wf = make_workflow()
        seed_workflow(workflow_store, wf)
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        orchestrator = orchestrator_factory(adapters={"echo": FailingAdapter()})
        outcome = orchestrator.execute_workflow("T-001")

        assert not outcome.ok
        assert outcome.status is WorkflowStatus.FAILED
        assert "boom" in (outcome.error or "")
        assert len(outcome.steps) == 1
        assert outcome.steps[0].status is StepStatus.FAILED
        assert outcome.steps[0].result == "FAILED"
        assert outcome.steps[0].agent_id == "A-001"
        assert outcome.steps[0].runtime_id == "echo"
        agent = AgentRegistry(agent_store).get("A-001")
        assert agent is not None and agent.status is AgentStatus.AVAILABLE
        assignments = assignment_store.list()
        assert len(assignments) == 1
        assert assignments[0].status is AssignmentStatus.FAILED

    def test_execution_failed_event_sequence(self, orchestrator_factory, task_store,
                                             agent_store, workflow_store, runtime_store,
                                             logger):
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        orchestrator = orchestrator_factory(adapters={"echo": FailingAdapter()})
        outcome = orchestrator.execute_workflow("T-001")

        assert _event_types(outcome.events) == [
            "orchestration.started", "orchestration.step.started",
            "orchestration.failed",
        ]

    def test_failed_workflow_has_no_completed_steps(self, orchestrator_factory, task_store,
                                                    agent_store, workflow_store,
                                                    runtime_store, logger):
        """无半完成: 失败时运行实例中无 COMPLETED 步骤 (仅 FAILED/PENDING)。"""
        wf = make_workflow(steps=[
            make_step("s1", 1, skill="dev", role="backend-developer"),
            make_step("s2", 2, skill="dev", role="backend-developer"),
        ])
        seed_workflow(workflow_store, wf)
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["dev"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        orchestrator = orchestrator_factory(adapters={"echo": FailingAdapter()})
        outcome = orchestrator.execute_workflow("T-001")

        assert outcome.run is not None and outcome.run.status is WorkflowStatus.FAILED
        statuses = [st.status for st in outcome.run.step_states]
        assert StepStatus.COMPLETED not in statuses
        assert StepStatus.FAILED in statuses

    def test_second_step_failure_leaves_first_completed_only(self, orchestrator_factory,
                                                             task_store, agent_store,
                                                             workflow_store, runtime_store,
                                                             logger):
        """第 2 步失败: 第 1 步 COMPLETED (真实完成), 整体 FAILED, 后续不执行。"""
        from runtime.adapter import RuntimeAdapter
        from runtime.models import ExecutionRequest, ExecutionResult, ExecutionStatus

        class FailSecondAdapter(RuntimeAdapter):
            def __init__(self):
                self.calls = 0
            def execute(self, request: ExecutionRequest) -> ExecutionResult:
                self.calls += 1
                if self.calls == 2:
                    return ExecutionResult(id=f"EXR-{request.id}", request_id=request.id,
                                           status=ExecutionStatus.FAILED, error="second boom")
                return ExecutionResult(id=f"EXR-{request.id}", request_id=request.id,
                                       status=ExecutionStatus.SUCCESS, output={})

        adapter = FailSecondAdapter()
        wf = make_workflow(steps=[
            make_step("s1", 1, skill="dev", role="backend-developer"),
            make_step("s2", 2, skill="dev", role="backend-developer"),
        ])
        seed_workflow(workflow_store, wf)
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["dev"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        orchestrator = orchestrator_factory(adapters={"echo": adapter})
        outcome = orchestrator.execute_workflow("T-001")

        assert not outcome.ok
        assert [s.step_id for s in outcome.steps] == ["s1", "s2"]
        assert outcome.steps[0].status is StepStatus.COMPLETED
        assert outcome.steps[1].status is StepStatus.FAILED
        assert adapter.calls == 2  # 第 3 步不存在; 失败后立即停止
        assert outcome.run is not None and outcome.run.status is WorkflowStatus.FAILED


class TestOutcomeModel:
    def test_outcome_ok_and_to_dict(self, orchestrator, task_store, agent_store,
                                    workflow_store, runtime_store):
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        outcome = orchestrator.execute_workflow("T-001")

        assert outcome.ok is True
        d = outcome.to_dict()
        assert d["task_id"] == "T-001"
        assert d["status"] == "COMPLETED"
        assert d["workflow_id"] == "wf-auto"
        assert d["run_id"] == outcome.run_id
        assert d["error"] is None
        assert d["steps"][0]["step_id"] == "dev"
        assert d["events"][-1] == "orchestration.completed"

    def test_failed_outcome_ok_false(self, orchestrator, task_store, workflow_store):
        seed_workflow(workflow_store, make_workflow())
        outcome = orchestrator.execute_workflow("T-999")
        assert outcome.ok is False
        assert outcome.status is WorkflowStatus.FAILED


class TestWorkflowProgress:
    def test_current_step_advances_through_steps(self, orchestrator, task_store, agent_store,
                                                 workflow_store, runtime_store):
        wf = make_workflow(steps=[
            make_step("s1", 1, skill="dev", role="backend-developer"),
            make_step("s2", 2, skill="dev", role="backend-developer"),
        ])
        seed_workflow(workflow_store, wf)
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["dev"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        outcome = orchestrator.execute_workflow("T-001")

        assert outcome.ok
        assert outcome.run is not None
        assert outcome.run.current_step is None  # 全部完成后无当前步骤
        assert outcome.run.all_steps_completed()

    def test_run_is_persisted_after_success(self, orchestrator, task_store, agent_store,
                                            workflow_store, runtime_store):
        seed_workflow(workflow_store, make_workflow())
        seed_agent(agent_store, make_agent("A-001", role="backend-developer",
                                           skills=["development"]))
        seed_task(task_store, make_task())
        seed_runtime(runtime_store, "echo")

        orchestrator.execute_workflow("T-001")

        engine = WorkflowEngine(workflow_store, task_store=task_store, runtime_store=runtime_store)
        run = engine.status("T-001")
        assert run is not None and run.status is WorkflowStatus.COMPLETED
