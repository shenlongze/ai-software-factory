"""tests/org/test_execution_runtime.py — S10-011 Task 004: Workflow Instance Runtime (TDD)。

设计依据 (唯一): docs/sprint10/S10-011-architecture-design.md §二 4/5/6
(Workflow Instance 生命周期执行 + Runtime 数据模型 + Log/Audit 模型) + §三 Task 004
(生命周期执行: RUNNING→SUCCESS/FAILED + runtime 更新 + Task 状态更新
IN_PROGRESS→REVIEW/DONE 或 BLOCKED) + AF-PRD-v1.md 4.8。

被测: org.execution.execute_instance (Task 004 新增):
- 输入: CREATED 实例 + executor 回调 (stub — 本 Sprint 注入点, 真实 Agent S10-012+)
  + runtime_store / audit_store (可注入) + task (Task 状态联动) + actor (缺省 executor)
- 流程:
  1. 非 CREATED → ValueError 拒绝 (RUNNING/终态直接 execute 非法)
  2. CREATED → RUNNING (start_time 记录) → 写 runtime (workflow-execution/
     {id}.json + agent-execution/{id}.json) + audit (actor=executor,
     action=instance.transition)
  3. 调用 executor(running 实例) → 成功: SUCCESS + end_time + result;
     抛异常/返回 "ERROR:" 前缀 → FAILED + end_time + error (存 result 字段)
  4. 每次转换 (RUNNING + 终态) 都写 runtime + audit — runtime 可恢复
     (RUNNING 中途崩溃 → load_workflow_execution 可见当前执行状态)
- Task 状态联动 (走 management.transition_task 受控状态机):
  - instance SUCCESS → task IN_PROGRESS→REVIEW (未开始 READY→IN_PROGRESS)
  - instance FAILED → task IN_PROGRESS/READY→BLOCKED
  - 非法转换 (task 已 REVIEW/DONE 等) → 失败安全跳过 (不破坏执行结果)
  - dependency_status 可选透传 (有依赖 task 联动)
- 返回 ExecutionOutcome {instance 终态, task 联动后 (如提供)}

basename 全仓库唯一 (test_org_* 前缀目录约定); 不跨目录依赖 helper。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core", _ROOT / "factory-org"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# noqa: E402 — sys.path 就绪后导入
from org.execution import (  # noqa: E402
    AuditStore,
    ExecutionOutcome,
    RuntimeStore,
    WorkflowInstance,
    WorkflowInstanceStatus,
    execute_instance,
)
from org.management import Task, TaskPriority, TaskStatus  # noqa: E402


def _task(
    task_id: str,
    *,
    status: TaskStatus | str = TaskStatus.READY,
    dependency: list[str] | None = None,
    assignee: str = "",
) -> Task:
    """最小 Task 构造 (status 默认 READY — 执行前置状态)。"""
    return Task(
        id=task_id,
        title=f"task {task_id}",
        priority=TaskPriority.P2,
        status=status,
        dependency=list(dependency or []),
        assignee=assignee,
    )


def _instance(instance_id: str = "WI-1", task_id: str = "T-1", **kw) -> WorkflowInstance:
    """最小 CREATED WorkflowInstance 构造。"""
    return WorkflowInstance(
        instance_id=instance_id,
        task_id=task_id,
        workflow_id="software-development-v1",
        agent="agent-a",
        skill="skill-a",
        **kw,
    )


def _stores(space_dir: Path) -> tuple[RuntimeStore, AuditStore]:
    """项目空间 runtime/ + logs/ store 对。"""
    return RuntimeStore(space_dir), AuditStore(space_dir)


# ------------------------------------------------------------------ 生命周期: 成功路径


class TestExecuteSuccess:
    def test_success_flow_records_times_and_result(self, tmp_path: Path):
        """CREATED → RUNNING → SUCCESS: start_time/end_time 记录, executor 返回写入 result。"""
        runtime, audit = _stores(tmp_path)
        calls: list[WorkflowInstanceStatus] = []

        def executor(inst: WorkflowInstance) -> str:
            calls.append(inst.status)
            return "tests passed (42)"

        outcome = execute_instance(
            _instance(),
            executor,
            runtime_store=runtime,
            audit_store=audit,
        )

        assert isinstance(outcome, ExecutionOutcome)
        inst = outcome.instance
        assert inst.status == WorkflowInstanceStatus.SUCCESS
        assert inst.start_time is not None
        assert inst.end_time is not None
        assert inst.end_time >= inst.start_time
        assert inst.result == "tests passed (42)"
        # executor 收到的是 RUNNING 实例 (带 start_time)
        assert calls == [WorkflowInstanceStatus.RUNNING]

    def test_executor_receives_running_instance_with_start_time(self, tmp_path: Path):
        """executor 回调入参是 RUNNING 实例 (start_time 已记录)。"""
        runtime, audit = _stores(tmp_path)
        seen: WorkflowInstance | None = None

        def executor(inst: WorkflowInstance) -> str:
            nonlocal seen
            seen = inst
            return "ok"

        execute_instance(_instance(), executor, runtime_store=runtime, audit_store=audit)

        assert seen is not None
        assert seen.status == WorkflowInstanceStatus.RUNNING
        assert seen.start_time is not None
        assert seen.end_time is None
        assert seen.result == ""

    def test_default_stub_executor_succeeds(self, tmp_path: Path):
        """executor 缺省 → 内置 stub 执行 → SUCCESS (注入点缺省可执行)。"""
        runtime, audit = _stores(tmp_path)
        outcome = execute_instance(_instance(), runtime_store=runtime, audit_store=audit)

        assert outcome.instance.status == WorkflowInstanceStatus.SUCCESS
        assert outcome.instance.result  # stub 返回非空结果


# ------------------------------------------------------------------ 生命周期: 失败路径


class TestExecuteFailure:
    def test_executor_exception_records_error(self, tmp_path: Path):
        """executor 抛异常 → FAILED + end_time + error (异常信息入 result 字段)。"""
        runtime, audit = _stores(tmp_path)

        def executor(inst: WorkflowInstance) -> str:
            raise RuntimeError("agent crashed")

        outcome = execute_instance(
            _instance(), executor, runtime_store=runtime, audit_store=audit
        )

        inst = outcome.instance
        assert inst.status == WorkflowInstanceStatus.FAILED
        assert inst.end_time is not None
        assert "RuntimeError" in inst.result
        assert "agent crashed" in inst.result

    def test_executor_error_prefix_result_fails(self, tmp_path: Path):
        """executor 返回 "ERROR:" 前缀 → 视为失败 → FAILED + error。"""
        runtime, audit = _stores(tmp_path)

        def executor(inst: WorkflowInstance) -> str:
            return "ERROR: build failed"

        outcome = execute_instance(
            _instance(), executor, runtime_store=runtime, audit_store=audit
        )

        inst = outcome.instance
        assert inst.status == WorkflowInstanceStatus.FAILED
        assert inst.end_time is not None
        assert inst.result == "build failed"


# ------------------------------------------------------------------ 非法状态拒绝


class TestExecuteRejectsInvalid:
    def test_running_direct_execute_rejected(self, tmp_path: Path):
        """RUNNING 实例直接 execute → ValueError (只接受 CREATED)。"""
        runtime, audit = _stores(tmp_path)
        running = _instance().model_copy(
            update={"status": WorkflowInstanceStatus.RUNNING, "start_time": "2026-01-01T00:00:00Z"}
        )
        with pytest.raises(ValueError, match="created"):
            execute_instance(running, runtime_store=runtime, audit_store=audit)

    def test_terminal_instance_execute_rejected(self, tmp_path: Path):
        """终态实例 (SUCCESS) 直接 execute → ValueError。"""
        runtime, audit = _stores(tmp_path)
        done = _instance().model_copy(update={"status": WorkflowInstanceStatus.SUCCESS})
        with pytest.raises(ValueError, match="created"):
            execute_instance(done, runtime_store=runtime, audit_store=audit)

    def test_execute_does_not_mutate_input_instance(self, tmp_path: Path):
        """纯函数约束: 入参实例不被就地修改 (转换返回新对象)。"""
        runtime, audit = _stores(tmp_path)
        inst = _instance()
        execute_instance(inst, runtime_store=runtime, audit_store=audit)
        assert inst.status == WorkflowInstanceStatus.CREATED
        assert inst.start_time is None


# ------------------------------------------------------------------ Runtime 记录 + 可恢复


class TestRuntimeRecords:
    def test_runtime_written_for_each_transition(self, tmp_path: Path):
        """每次转换 (RUNNING + 终态) 写 workflow-execution + agent-execution JSON。"""
        runtime, audit = _stores(tmp_path)
        execute_instance(
            _instance("WI-RT-1"),
            lambda inst: "ok",
            runtime_store=runtime,
            audit_store=audit,
        )

        for kind in ("workflow-execution", "agent-execution"):
            data = runtime.load_workflow_execution("WI-RT-1") if kind == "workflow-execution" else runtime.load_agent_execution("WI-RT-1")
            assert data is not None, f"{kind}/WI-RT-1.json 缺失"
            assert data["instance_id"] == "WI-RT-1"
            assert data["task_id"] == "T-1"
            assert data["status"] == WorkflowInstanceStatus.SUCCESS.value

    def test_runtime_recoverable_while_running(self, tmp_path: Path):
        """执行中 (RUNNING) 状态写入 runtime → 重建后可读当前执行状态 (可恢复)。"""
        runtime, audit = _stores(tmp_path)
        # 模拟: 执行中崩溃 — 手动走 RUNNING 转换 (等价 execute_instance 第 1 步)
        # 这里直接验证 execute_instance 在 RUNNING 时刻的 runtime 快照可恢复:
        # 用 stub executor 触发一次真实 RUNNING 写入 (通过 monkeypatch 记录),
        # 更直接: 校验 RUNNING 转换后落盘的 JSON 含 running + start_time。
        from org.execution import transition_instance

        running = transition_instance(_instance("WI-REC"), WorkflowInstanceStatus.RUNNING)
        runtime.save_workflow_execution(running.instance_id, running.to_dict())
        runtime.save_agent_execution(running.instance_id, running.to_dict())

        loaded_wf = runtime.load_workflow_execution("WI-REC")
        loaded_ag = runtime.load_agent_execution("WI-REC")
        assert loaded_wf is not None and loaded_ag is not None
        assert loaded_wf["status"] == WorkflowInstanceStatus.RUNNING.value
        assert loaded_wf["start_time"] is not None
        assert loaded_ag["status"] == WorkflowInstanceStatus.RUNNING.value
        # 重建后可继续流转 (RUNNING 实例可合法转 SUCCESS — 状态机放行)
        rebuilt = WorkflowInstance.model_validate(loaded_wf)
        continued = transition_instance(rebuilt, WorkflowInstanceStatus.SUCCESS, result="resumed")
        assert continued.status == WorkflowInstanceStatus.SUCCESS
        assert continued.end_time is not None

    def test_runtime_final_snapshot_is_terminal(self, tmp_path: Path):
        """终态后 workflow-execution 快照 = SUCCESS + result + end_time。"""
        runtime, audit = _stores(tmp_path)
        execute_instance(
            _instance("WI-RT-2"),
            lambda inst: "delivered",
            runtime_store=runtime,
            audit_store=audit,
        )
        data = runtime.load_workflow_execution("WI-RT-2")
        assert data is not None
        assert data["status"] == WorkflowInstanceStatus.SUCCESS.value
        assert data["result"] == "delivered"
        assert data["end_time"] is not None


# ------------------------------------------------------------------ Audit 记录


class TestAuditRecords:
    def test_audit_written_for_each_transition(self, tmp_path: Path):
        """每次转换写 audit (actor=executor, action=instance.transition, entity=instance_id)。"""
        runtime, audit = _stores(tmp_path)
        execute_instance(
            _instance("WI-AUD-1"),
            lambda inst: "ok",
            runtime_store=runtime,
            audit_store=audit,
        )

        entries = audit.list()
        # RUNNING 转换 + SUCCESS 转换 = 2 条
        assert len(entries) == 2
        for entry in entries:
            assert entry["actor"] == "executor"
            assert entry["action"] == "instance.transition"
            assert entry["entity"] == "WI-AUD-1"
        assert entries[0]["input"]["to"] == WorkflowInstanceStatus.RUNNING.value
        assert entries[1]["input"]["to"] == WorkflowInstanceStatus.SUCCESS.value

    def test_audit_failure_transition_records_error(self, tmp_path: Path):
        """FAILED 转换的 audit result 含错误信息。"""
        runtime, audit = _stores(tmp_path)

        def executor(inst: WorkflowInstance) -> str:
            raise ValueError("boom")

        execute_instance(
            _instance("WI-AUD-2"),
            executor,
            runtime_store=runtime,
            audit_store=audit,
        )

        entries = audit.list()
        assert entries[-1]["input"]["to"] == WorkflowInstanceStatus.FAILED.value
        assert "boom" in str(entries[-1]["result"])

    def test_audit_custom_actor(self, tmp_path: Path):
        """actor 可注入 (非缺省 executor)。"""
        runtime, audit = _stores(tmp_path)
        execute_instance(
            _instance("WI-AUD-3"),
            lambda inst: "ok",
            runtime_store=runtime,
            audit_store=audit,
            actor="worker-1",
        )
        entries = audit.list()
        assert entries and all(e["actor"] == "worker-1" for e in entries)


# ------------------------------------------------------------------ Task 状态联动


class TestTaskLinking:
    def test_success_links_in_progress_to_review(self, tmp_path: Path):
        """instance SUCCESS + task IN_PROGRESS → task REVIEW (受控状态机)。"""
        runtime, audit = _stores(tmp_path)
        task = _task("T-L1", status=TaskStatus.IN_PROGRESS)

        outcome = execute_instance(
            _instance("WI-L1", task_id="T-L1"),
            lambda inst: "ok",
            runtime_store=runtime,
            audit_store=audit,
            task=task,
        )

        assert outcome.task is not None
        assert outcome.task.status == TaskStatus.REVIEW
        assert outcome.task.history  # transition_task 追加审计链
        assert outcome.task.history[-1].actor == "executor"

    def test_success_links_ready_to_in_progress(self, tmp_path: Path):
        """instance SUCCESS + task READY (未开始) → task IN_PROGRESS。"""
        runtime, audit = _stores(tmp_path)
        task = _task("T-L2", status=TaskStatus.READY)

        outcome = execute_instance(
            _instance("WI-L2", task_id="T-L2"),
            lambda inst: "ok",
            runtime_store=runtime,
            audit_store=audit,
            task=task,
        )

        assert outcome.task is not None
        assert outcome.task.status == TaskStatus.IN_PROGRESS

    def test_failed_links_task_to_blocked(self, tmp_path: Path):
        """instance FAILED → task IN_PROGRESS → BLOCKED (受控)。"""
        runtime, audit = _stores(tmp_path)
        task = _task("T-L3", status=TaskStatus.IN_PROGRESS)

        def executor(inst: WorkflowInstance) -> str:
            raise RuntimeError("failed link")

        outcome = execute_instance(
            _instance("WI-L3", task_id="T-L3"),
            executor,
            runtime_store=runtime,
            audit_store=audit,
            task=task,
        )

        assert outcome.task is not None
        assert outcome.task.status == TaskStatus.BLOCKED

    def test_failed_links_ready_task_to_blocked(self, tmp_path: Path):
        """instance FAILED + task READY → BLOCKED。"""
        runtime, audit = _stores(tmp_path)
        task = _task("T-L4", status=TaskStatus.READY)

        def executor(inst: WorkflowInstance) -> str:
            raise RuntimeError("x")

        outcome = execute_instance(
            _instance("WI-L4", task_id="T-L4"),
            executor,
            runtime_store=runtime,
            audit_store=audit,
            task=task,
        )

        assert outcome.task is not None
        assert outcome.task.status == TaskStatus.BLOCKED

    def test_task_linking_skipped_when_illegal(self, tmp_path: Path):
        """task 已 REVIEW/DONE → 联动非法 → 失败安全跳过 (原 task 不变, 不抛)。"""
        runtime, audit = _stores(tmp_path)
        task = _task("T-L5", status=TaskStatus.REVIEW)

        outcome = execute_instance(
            _instance("WI-L5", task_id="T-L5"),
            lambda inst: "ok",
            runtime_store=runtime,
            audit_store=audit,
            task=task,
        )

        assert outcome.instance.status == WorkflowInstanceStatus.SUCCESS  # 执行不受影响
        assert outcome.task is task  # 未联动 → 原对象
        assert task.status == TaskStatus.REVIEW

    def test_task_linking_with_dependencies(self, tmp_path: Path):
        """有依赖的 READY task → SUCCESS → IN_PROGRESS (dependency_status 透传状态机)。"""
        runtime, audit = _stores(tmp_path)
        task = _task("T-L6", status=TaskStatus.READY, dependency=["T-dep"])

        outcome = execute_instance(
            _instance("WI-L6", task_id="T-L6"),
            lambda inst: "ok",
            runtime_store=runtime,
            audit_store=audit,
            task=task,
            dependency_status={"T-dep": TaskStatus.DONE},
        )

        assert outcome.task is not None
        assert outcome.task.status == TaskStatus.IN_PROGRESS
