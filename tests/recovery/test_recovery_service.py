"""tests/recovery/test_recovery_service.py — RecoveryService checkpoint/recover 测试。

覆盖四恢复场景 (phase4c3-status.md §2):
- 场景1: Workflow RUNNING 中断 → 继续当前 Step (resume_ok=True)
- 场景2: Execution RUNNING 中断 → 标记可重试 (RUNNING → PENDING, 可重新派发)
- 场景3: Agent WORKING 中断 → 释放 Agent (→ AVAILABLE) + Assignment → RELEASED
- 场景4: 已完成 Workflow → 拒绝 (resume_ok=False)
"""

from __future__ import annotations

import pytest

from agents.models import AgentStatus
from assignment.models import AgentAssignment, AssignmentStatus
from events.models import EventType
from execution.service import ExecutionService
from recovery.models import Checkpoint, RecoveryResult
from recovery.service import RecoveryError, RecoveryService, RecoveryStateError, TaskNotFoundError
from runtime.adapters import BUILTIN_ADAPTERS
from runtime.models import ExecutionStatus, RuntimeInfo
from runtime.registry import RuntimeRegistry
from workflows.engine import WorkflowEngine
from workflows.models import WorkflowStatus
from assignment.allocator import AgentAllocator

from recovery_helpers import make_agent, make_task, make_workflow


def seed_running(service, logger, *, task_id: str = "T-001", steps=("s1", "s2")):
    """种子: 任务 + 工作流定义 + 启动 run (RUNNING, 第一步 RUNNING)。返回 (engine, run)。

    engine 装配 runtime_store (execute_step 边界要求, workflows/engine.py)。"""
    wf = make_workflow("wf-a", steps=list(steps))
    service.workflow_store.save_workflow(wf)
    service.task_store.create(make_task(task_id, workflow="wf-a"))
    engine = WorkflowEngine(service.workflow_store, task_store=service.task_store,
                            logger=logger, runtime_store=service.runtime_store)
    run, _ = engine.start_workflow(task_id)
    return engine, run


# ------------------------------------------------------------------ checkpoint

class TestCheckpoint:
    def test_checkpoint_creates_snapshot(self, service, logger):
        engine, run = seed_running(service, logger)
        request, _ = engine.execute_step("T-001", "s1")
        cp, ev = service.checkpoint("T-001")
        assert isinstance(cp, Checkpoint)
        assert cp.id == "CKPT-T-001"
        assert cp.task_id == "T-001"
        assert cp.workflow_id == "wf-a"
        assert cp.event_seq > 0  # 最近事件 seq 锚点
        assert cp.current_step == "s1"
        assert cp.workflow_state == run.to_dict()
        assert cp.executions == {request.id: "PENDING"}
        assert ev is not None and ev.type is EventType.RECOVERY_COMPLETED

    def test_checkpoint_event_seq_is_last_task_event(self, service, logger):
        seed_running(service, logger)
        cp, _ = service.checkpoint("T-001")
        events = logger.store.by_task("T-001")
        # 锚点是快照时刻的最后任务事件: checkpoint 自身的 recovery.* 事件不计入
        task_events = [e for e in events if e.type not in
                       (EventType.RECOVERY_STARTED, EventType.RECOVERY_COMPLETED)]
        assert cp.event_seq == task_events[-1].seq

    def test_checkpoint_event_seq_zero_when_no_events(self, service):
        service.task_store.create(make_task("T-001", workflow="wf-a"))
        cp, _ = service.checkpoint("T-001")
        assert cp.event_seq == 0
        assert cp.workflow_id is None
        assert cp.workflow_state is None
        assert cp.current_step is None

    def test_checkpoint_with_agent_snapshot(self, service, logger):
        engine, _ = seed_running(service, logger)
        service.agent_registry.register(make_agent("A-001"))
        allocator = AgentAllocator(service.assignment_store, service.agent_registry, logger=logger)
        asg, _ = allocator.assign("T-001", agent_id="A-001", workflow_id="wf-a",
                                  workflow_step_id="s1")
        allocator.start(asg.id)  # Agent → WORKING
        cp, _ = service.checkpoint("T-001")
        assert cp.agents == {"A-001": "WORKING"}
        assert cp.executions == {}

    def test_checkpoint_persists_to_store(self, service, logger):
        seed_running(service, logger)
        cp, _ = service.checkpoint("T-001")
        assert service.checkpoint_store.load("T-001") is not None
        assert service.checkpoint_store.load("T-001").id == cp.id

    def test_checkpoint_overwrites_previous(self, service, logger):
        seed_running(service, logger)
        service.checkpoint("T-001")
        first = service.checkpoint_store.load("T-001")
        service.checkpoint("T-001")  # 重复 checkpoint: 覆盖 (最新停靠点)
        second = service.checkpoint_store.load("T-001")
        assert second.event_seq >= first.event_seq

    def test_checkpoint_task_not_found(self, service):
        with pytest.raises(TaskNotFoundError):
            service.checkpoint("T-999")

    def test_checkpoint_without_store_raises(self, task_store, workflow_store,
                                             assignment_store, runtime_store,
                                             agent_registry, event_store, logger):
        svc = RecoveryService(
            task_store=task_store, workflow_store=workflow_store,
            assignment_store=assignment_store, runtime_store=runtime_store,
            agent_registry=agent_registry, event_store=event_store,
            checkpoint_store=None, logger=logger,
        )
        svc.task_store.create(make_task("T-001", workflow="wf-a"))
        with pytest.raises(RecoveryStateError):
            svc.checkpoint("T-001")

    def test_checkpoint_no_logger_returns_none_event(self, service_no_logger):
        service_no_logger.task_store.create(make_task("T-001", workflow="wf-a"))
        cp, ev = service_no_logger.checkpoint("T-001")
        assert cp.task_id == "T-001"
        assert ev is None

    def test_checkpoint_emits_started_then_completed(self, service, logger):
        seed_running(service, logger)
        service.checkpoint("T-001")
        types = [e.type.value for e in logger.store.by_task("T-001")]
        assert "recovery.started" in types
        assert "recovery.completed" in types
        completed = [e for e in logger.store.by_task("T-001")
                     if e.type is EventType.RECOVERY_COMPLETED][0]
        assert completed.result == "OK"
        assert completed.payload["checkpoint_id"] == "CKPT-T-001"


# ------------------------------------------------------------------ 场景1: RUNNING 继续

class TestScenario1RunningContinue:
    def test_running_workflow_resumes(self, service, logger):
        seed_running(service, logger)
        result, ev = service.recover("T-001")
        assert isinstance(result, RecoveryResult)
        assert result.resume_ok is True
        assert result.state == "RUNNING"
        assert any("continue step s1" in a for a in result.actions)
        assert result.last_event > 0
        assert result.workflow is not None
        assert ev is not None and ev.type is EventType.RECOVERY_COMPLETED

    def test_running_second_step_continues(self, service, logger):
        engine, _ = seed_running(service, logger)
        engine.complete_step("T-001", "s1", result="OK")  # s1 COMPLETED, s2 当前
        result, _ = service.recover("T-001")
        assert result.resume_ok is True
        assert any("continue step s2" in a for a in result.actions)

    def test_recover_no_events_still_resumes(self, service):
        """无事件链 (纯存储现场) 也按持久化状态恢复: RUNNING → 继续。"""
        service.task_store.create(make_task("T-001", workflow="wf-a"))
        wf = make_workflow("wf-a", steps=["s1"])
        service.workflow_store.save_workflow(wf)
        engine = WorkflowEngine(service.workflow_store, task_store=service.task_store)
        engine.start_workflow("T-001")
        result, _ = service.recover("T-001")
        assert result.resume_ok is True
        assert result.state == "RUNNING"
        # 事件链为空 → 回放锚点仅含 recover 自身发的 recovery.started (seq=1)
        assert result.last_event > 0


# ------------------------------------------------------------------ 场景2: Execution 重试

class TestScenario2ExecutionRetry:
    def _seed_running_execution(self, service, logger, task_id: str = "T-001"):
        engine, run = seed_running(service, logger, task_id=task_id)
        request, _ = engine.execute_step(task_id, "s1")
        # 模拟派发中断: runner 置 RUNNING 后进程死亡 (无 completed/failed)
        request.status = ExecutionStatus.RUNNING
        service.runtime_store.save_execution(request)
        logger.record(
            EventType.EXECUTION_STARTED, source="execution_runner", task_id=task_id,
            payload={"execution_id": request.id, "workflow_id": "wf-a", "step_id": "s1"},
        )
        return request

    def test_running_execution_marked_retryable(self, service, logger):
        request = self._seed_running_execution(service, logger)
        result, _ = service.recover("T-001")
        assert result.resume_ok is True
        assert any("retry execution" in a for a in result.actions)
        # 持久化已纠正: RUNNING → PENDING (可重新派发至 RUNNING)
        req = service.runtime_store.get_execution(request.id)
        assert req.status is ExecutionStatus.PENDING

    def test_retried_execution_can_rerun_to_success(self, service, logger):
        """恢复后 execution 可重新派发 → SUCCESS (证明 RUNNING → PENDING 可重跑)。"""
        request = self._seed_running_execution(service, logger)
        RuntimeRegistry(service.runtime_store, logger=logger).register(
            RuntimeInfo(id="echo", name="echo", type="mock")
        )
        service.recover("T-001")
        svc = ExecutionService(
            service.runtime_store, RuntimeRegistry(service.runtime_store),
            adapters=BUILTIN_ADAPTERS, logger=logger,
        )
        outcome = svc.run(request.id)
        assert outcome.request.status is ExecutionStatus.SUCCESS

    def test_pending_execution_untouched(self, service, logger):
        """PENDING execution 不需恢复 (未派发, 无中断痕迹)。"""
        engine, _ = seed_running(service, logger)
        engine.execute_step("T-001", "s1")  # execution.created (PENDING)
        result, _ = service.recover("T-001")
        assert not any("retry execution" in a for a in result.actions)
        reqs = service.runtime_store.list_executions(task_id="T-001")
        assert all(r.status is ExecutionStatus.PENDING for r in reqs)

    def test_terminal_execution_untouched(self, service, logger):
        """SUCCESS execution 终态不重试。"""
        engine, _ = seed_running(service, logger)
        request, _ = engine.execute_step("T-001", "s1")
        request.status = ExecutionStatus.SUCCESS
        service.runtime_store.save_execution(request)
        result, _ = service.recover("T-001")
        assert not any("retry execution" in a for a in result.actions)
        assert service.runtime_store.get_execution(request.id).status is ExecutionStatus.SUCCESS


# ------------------------------------------------------------------ 场景3: Agent 释放

class TestScenario3AgentRelease:
    def _seed_working_agent(self, service, logger, task_id: str = "T-001"):
        engine, run = seed_running(service, logger, task_id=task_id)
        service.agent_registry.register(make_agent("A-001"))
        allocator = AgentAllocator(service.assignment_store, service.agent_registry,
                                   logger=logger)
        asg, _ = allocator.assign(task_id, agent_id="A-001", workflow_id="wf-a",
                                  workflow_step_id="s1")
        allocator.start(asg.id)  # Agent → WORKING
        return asg

    def test_working_agent_released(self, service, logger):
        asg = self._seed_working_agent(service, logger)
        result, _ = service.recover("T-001")
        assert result.resume_ok is True
        assert any("release agent A-001" in a for a in result.actions)
        assert service.agent_registry.get("A-001").status is AgentStatus.AVAILABLE
        assert service.agent_registry.get("A-001").current_task is None

    def test_assignment_marked_released(self, service, logger):
        asg = self._seed_working_agent(service, logger)
        service.recover("T-001")
        got = service.assignment_store.load(asg.id)
        assert got.status is AssignmentStatus.RELEASED
        assert got.completed_at is not None

    def test_available_agent_untouched(self, service, logger):
        """AVAILABLE Agent 不需释放 (无占用残留)。"""
        seed_running(service, logger)
        service.agent_registry.register(make_agent("A-001"))  # AVAILABLE, 无 assignment
        result, _ = service.recover("T-001")
        assert not any("release agent" in a for a in result.actions)
        assert service.agent_registry.get("A-001").status is AgentStatus.AVAILABLE

    def test_working_agent_of_other_task_untouched(self, service, logger):
        """其他任务的 WORKING Agent 不受本任务恢复影响。"""
        asg = self._seed_working_agent(service, logger, task_id="T-001")
        # 另一任务也占用同一 Agent (WORKING): 直接持久化第二条 assignment — 真实中断现场
        # 允许同一 Agent 被两任务占用 (分配器禁止二次分配, 故绕过 allocator 造现场)
        seed_running(service, logger, task_id="T-002")
        asg2 = AgentAssignment(
            id=service.assignment_store.next_id(),
            agent_id="A-001", task_id="T-002", workflow_id="wf-a",
            workflow_step_id="s1", status=AssignmentStatus.WORKING,
        )
        service.assignment_store.save(asg2)
        result, _ = service.recover("T-001")
        # 本任务 assignment 释放; 其他任务 assignment 不动 (Agent 仍被 T-002 占用)
        assert service.assignment_store.load(asg.id).status is AssignmentStatus.RELEASED
        assert service.assignment_store.load(asg2.id).status is AssignmentStatus.WORKING

    def test_release_emits_no_agent_released_event(self, service, logger):
        """恢复纠正不发 agent.released — 审计由 recovery.* 承载 (ADR-0011 决策 3)。"""
        self._seed_working_agent(service, logger)
        service.recover("T-001")
        types = [e.type.value for e in logger.store.by_task("T-001")]
        assert "agent.released" not in types


# ------------------------------------------------------------------ 场景4: 已完成拒绝

class TestScenario4CompletedReject:
    def _complete_workflow(self, service, logger, task_id: str = "T-001"):
        engine, run = seed_running(service, logger, task_id=task_id)
        engine.complete_step(task_id, "s1", result="OK")
        engine.start_step(task_id, "s2")
        engine.complete_step(task_id, "s2", result="OK")  # → Workflow COMPLETED
        return engine, run

    def test_completed_workflow_rejected(self, service, logger):
        self._complete_workflow(service, logger)
        result, ev = service.recover("T-001")
        assert result.resume_ok is False
        assert result.state == "COMPLETED"
        assert any("reject recovery" in a for a in result.actions)
        assert ev.type is EventType.RECOVERY_COMPLETED
        assert ev.result == "rejected"

    def test_failed_workflow_rejected(self, service, logger):
        engine, _ = seed_running(service, logger)
        engine.fail_workflow("T-001", "boom")
        result, _ = service.recover("T-001")
        assert result.resume_ok is False
        assert result.state == "FAILED"
        assert any("reject recovery" in a for a in result.actions)

    def test_rejected_recovery_changes_nothing(self, service, logger):
        engine, run = self._complete_workflow(service, logger)
        result, _ = service.recover("T-001")
        assert not any(("retry" in a or "release" in a) for a in result.actions)
        # 终态现场保持原样
        assert service.workflow_store.get_run_by_task("T-001").status is WorkflowStatus.COMPLETED

    def test_no_run_rejected(self, service):
        """任务存在但无运行实例: 无现场可恢复 → 拒绝。"""
        service.task_store.create(make_task("T-001", workflow="wf-a"))
        result, _ = service.recover("T-001")
        assert result.resume_ok is False
        assert result.state == "none"
        assert any("no workflow run" in a for a in result.actions)

    def test_divergence_events_vs_persisted(self, service, logger):
        """事件链与持久化分歧: 事件说 FAILED, 持久化被改回 RUNNING →
        一致性提示 + 按持久化现场继续 (KISS: 提示不阻断)。"""
        engine, run = seed_running(service, logger)
        engine.fail_workflow("T-001", "boom")  # 事件链含 workflow.failed
        service.workflow_store.save_run(
            run.model_copy(update={"status": WorkflowStatus.RUNNING})
        )  # 持久化 run 异常回退为 RUNNING
        result, _ = service.recover("T-001")
        assert result.resume_ok is True  # 持久化 RUNNING 可继续
        assert any("inconsistency" in a for a in result.actions)


# ------------------------------------------------------------------ 事件流 & 边界

class TestRecoveryEvents:
    def test_recover_emits_started_then_completed(self, service, logger):
        seed_running(service, logger)
        service.recover("T-001")
        task_events = logger.store.by_task("T-001")
        types = [e.type.value for e in task_events]
        assert "recovery.started" in types
        assert "recovery.completed" in types
        started_idx = types.index("recovery.started")
        completed_idx = types.index("recovery.completed")
        assert started_idx < completed_idx  # 事件序: started → completed

    def test_recover_completed_payload_carries_result(self, service, logger):
        seed_running(service, logger)
        result, ev = service.recover("T-001")
        assert ev.payload["resume_ok"] is True
        assert ev.payload["state"] == "RUNNING"
        assert ev.payload["actions"] == result.actions
        assert ev.payload["last_event"] == result.last_event

    def test_recover_emits_failed_on_error(self, service, logger, monkeypatch):
        seed_running(service, logger)
        def boom(*args, **kwargs):
            raise RuntimeError("event store exploded")
        monkeypatch.setattr(service.event_store, "by_task", boom)
        with pytest.raises(RecoveryError) as exc_info:
            service.recover("T-001")
        assert "event store exploded" in str(exc_info.value)
        # service.event_store 与 logger.store 是同一对象 (by_task 已被 patch);
        # 断言改用 query (独立方法, 未被 patch) 验证 recovery.* 事件仍落库
        types = [e.type.value for e in logger.store.query(task_id="T-001")]
        assert "recovery.started" in types
        assert "recovery.failed" in types

    def test_recover_task_not_found_emits_failed(self, service, logger):
        with pytest.raises(TaskNotFoundError):
            service.recover("T-999")
        events = logger.store.query(task_id="T-999")
        assert [e.type for e in events] == [
            EventType.RECOVERY_STARTED, EventType.RECOVERY_FAILED,
        ]

    def test_recover_no_logger_returns_none_event(self, service_no_logger):
        service_no_logger.task_store.create(make_task("T-001", workflow="wf-a"))
        result, ev = service_no_logger.recover("T-001")
        assert result.resume_ok is False
        assert ev is None


class TestRecoveryResultDetails:
    def test_result_workflow_snapshot(self, service, logger):
        engine, run = seed_running(service, logger)
        result, _ = service.recover("T-001")
        assert result.workflow["run_id"] == run.run_id
        assert result.workflow["status"] == "RUNNING"

    def test_result_executions_and_assignments(self, service, logger):
        engine, _ = seed_running(service, logger)
        request, _ = engine.execute_step("T-001", "s1")
        service.agent_registry.register(make_agent("A-001"))
        allocator = AgentAllocator(service.assignment_store, service.agent_registry)
        asg, _ = allocator.assign("T-001", agent_id="A-001", workflow_id="wf-a",
                                  workflow_step_id="s1")
        result, _ = service.recover("T-001")
        assert [e["id"] for e in result.executions] == [request.id]
        assert [a["id"] for a in result.assignments] == [asg.id]
        assert result.agents == {"A-001": "AVAILABLE"}

    def test_result_actions_ordered_continue_then_retry_then_release(self, service, logger):
        """RUNNING 场景动作序: 继续 Step → 重试 Execution → 释放 Agent。"""
        engine, _ = seed_running(service, logger)
        request, _ = engine.execute_step("T-001", "s1")
        request.status = ExecutionStatus.RUNNING
        service.runtime_store.save_execution(request)
        service.agent_registry.register(make_agent("A-001"))
        allocator = AgentAllocator(service.assignment_store, service.agent_registry)
        asg, _ = allocator.assign("T-001", agent_id="A-001", workflow_id="wf-a",
                                  workflow_step_id="s1")
        allocator.start(asg.id)
        result, _ = service.recover("T-001")
        texts = " | ".join(result.actions)
        assert texts.index("continue step") < texts.index("retry execution")
        assert texts.index("retry execution") < texts.index("release agent")


class TestRecoveryIdempotency:
    def test_recover_twice_stable(self, service, logger):
        engine, _ = seed_running(service, logger)
        request, _ = engine.execute_step("T-001", "s1")
        request.status = ExecutionStatus.RUNNING
        service.runtime_store.save_execution(request)
        first, _ = service.recover("T-001")
        second, _ = service.recover("T-001")
        assert first.resume_ok is second.resume_ok
        assert first.state == second.state
        # 锚点只增不减: 每次 recover 追加 recovery.* 审计事件 (事件链只追加, 不改写)
        assert second.last_event > first.last_event
        # 第二次无纠正动作 (现场已干净)
        assert not any("retry execution" in a for a in second.actions)
        assert service.runtime_store.get_execution(request.id).status is ExecutionStatus.PENDING

    def test_checkpoint_then_recover_roundtrip(self, service, logger):
        """checkpoint → recover 往返: 锚点一致, 恢复可继续。"""
        seed_running(service, logger)
        cp, _ = service.checkpoint("T-001")
        result, _ = service.recover("T-001")
        assert result.last_event >= cp.event_seq  # 回放锚点覆盖停靠点
        assert result.resume_ok is True
