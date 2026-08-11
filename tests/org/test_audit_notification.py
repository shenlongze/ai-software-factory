"""tests/org/test_audit_notification.py — S10-011 Task 006: Notification + Audit Log (TDD)。

设计依据 (唯一): docs/sprint10/S10-011-architecture-design.md §二 6 (Log/Audit 模型:
logs/audit.log 追加不可变, 记录 {time, actor, action, entity, input, output, result},
actor: scheduler|dispatcher|executor|user|system) + §三 Task 006 (audit.log 全链路记录
+ notification 预留接口) + §五 验收场景 1/5 + docs/design/execution-engine.md §七
(Notification Engine — AI 主动提醒) + AF-PRD-v1.md 4.10 (Audit Log)。

被测 (org/execution.py Task 006 新增/完善):
- 全链路审计: 每转换/每 actor 写 audit 条目 —
  - execute_instance 每次转换 (CREATED→RUNNING→SUCCESS/FAILED) → audit (actor=executor)
  - dispatch_task → audit (actor=dispatcher, action=instance.dispatched)
  - ExecutionEngine 门面 plan → audit (actor=scheduler, action=plan.created)
  - Task 状态联动 → audit (actor=executor, action=task.linked)
  - 每条目 7 字段 {time, actor, action, entity, input, output, result} 完整
- AuditStore.list_audit: 按 time 排序 + 过滤 (actor/entity/action);
  项目空间隔离 (store 按 space_dir 归属)
- 不可变语义: 只追加不覆盖 (append-only); 读取返回副本 (外部修改不影响落盘事实)
- NotificationSink 预留接口: notify(project_id, event, payload) 默认 no-op;
  可注入 sink (零 mock 收集子类); ExecutionEngine 门面终态通知
  (instance SUCCESS → event="task.completed"; FAILED → event="task.failed")
- ExecutionEngine 门面全链验收 (§五 场景 1/5):
  READY → plan→dispatch→execute → instance SUCCESS + Task 联动
  (IN_PROGRESS→REVIEW→DONE 链可达) + runtime + audit + notify;
  失败 → instance FAILED + Task BLOCKED + audit + notify (task.failed)

basename 全仓库唯一 (test_org_* 前缀目录约定); 不跨目录依赖 helper。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core", _ROOT / "factory-org"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# noqa: E402 — sys.path 就绪后导入
from org.execution import (  # noqa: E402
    AuditStore,
    ExecutionEngine,
    NotificationSink,
    ProjectExecutionResult,
    RuntimeStore,
    WorkflowInstance,
    WorkflowInstanceStatus,
    dispatch_task,
    execute_instance,
    transition_task_locked,
)
from org.management import (  # noqa: E402
    Task,
    TaskPriority,
    TaskStatus,
    transition_task,
)

#: audit 条目 7 字段全集 (S10-011 §二 6 — 字段完整性断言)。
_AUDIT_FIELDS = {"time", "actor", "action", "entity", "input", "output", "result"}


def _task(
    task_id: str,
    *,
    status: TaskStatus | str = TaskStatus.READY,
    priority: TaskPriority | str = TaskPriority.P2,
    dependency: list[str] | None = None,
    assignee: str = "",
) -> Task:
    """最小 Task 构造 (status 默认 READY — 执行前置状态)。"""
    return Task(
        id=task_id,
        title=f"task {task_id}",
        priority=priority,
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


def _write_raw_entries(audit: AuditStore, entries: list[dict[str, Any]]) -> None:
    """直接写原始 JSON 行 (绕过 append — 构造乱序时间, 测试 list_audit 排序)。"""
    audit.path.parent.mkdir(parents=True, exist_ok=True)
    with open(audit.path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class _CollectingSink(NotificationSink):
    """收集 (project_id, event, payload) 的通知 sink (真实子类, 零 mock)。

    notify 覆盖为收集 — 断言调度/完成/失败通知的注入路径。
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def notify(self, project_id: str, event: str, payload: dict[str, Any]) -> None:
        self.events.append((project_id, event, dict(payload)))


# ================================================================== 全链路审计


class TestAuditFullChain:
    """全链路: 每转换/每 actor 写 audit 条目 (7 字段完整)。"""

    def test_execute_instance_each_transition_audited(self, tmp_path: Path):
        """execute_instance 每次转换 (CREATED→RUNNING→SUCCESS) → audit 条目。"""
        runtime, audit = _stores(tmp_path)
        execute_instance(
            _instance("WI-A1", task_id="T-A1"),
            lambda inst: "ok",
            runtime_store=runtime,
            audit_store=audit,
        )

        entries = audit.list_audit()
        assert len(entries) == 2  # RUNNING + SUCCESS 两转换
        for entry in entries:
            assert set(entry) == _AUDIT_FIELDS, f"audit 7 字段不完整: {entry}"
        assert entries[0]["input"]["to"] == WorkflowInstanceStatus.RUNNING.value
        assert entries[1]["input"]["to"] == WorkflowInstanceStatus.SUCCESS.value

    def test_execute_instance_failure_transition_audited(self, tmp_path: Path):
        """失败路径: CREATED→RUNNING→FAILED 两转换都写 audit (result 含错误)。"""
        runtime, audit = _stores(tmp_path)

        def boom(inst: WorkflowInstance) -> str:
            raise RuntimeError("audit boom")

        execute_instance(
            _instance("WI-A2", task_id="T-A2"),
            boom,
            runtime_store=runtime,
            audit_store=audit,
        )

        entries = audit.list_audit()
        assert len(entries) == 2
        assert entries[0]["input"]["to"] == WorkflowInstanceStatus.RUNNING.value
        assert entries[1]["input"]["to"] == WorkflowInstanceStatus.FAILED.value
        assert "audit boom" in str(entries[1]["result"])

    def test_dispatch_task_audits_dispatcher(self, tmp_path: Path):
        """dispatch_task (audit_store 注入) → 1 条 audit (actor=dispatcher)。"""
        audit = AuditStore(tmp_path / "space")
        inst = dispatch_task(_task("T-D1"), audit_store=audit)

        entries = audit.list_audit()
        assert len(entries) == 1
        entry = entries[0]
        assert set(entry) == _AUDIT_FIELDS
        assert entry["actor"] == "dispatcher"
        assert entry["action"] == "instance.dispatched"
        assert entry["entity"] == inst.instance_id
        assert entry["input"]["task_id"] == "T-D1"
        assert entry["input"]["workflow_id"] == "software-development-v1"
        assert entry["output"]["instance_id"] == inst.instance_id
        assert entry["output"]["status"] == WorkflowInstanceStatus.CREATED.value
        assert entry["result"] == "OK"

    def test_dispatch_task_locked_path_audits_dispatcher(self, tmp_path: Path):
        """写路径持锁 (project_id) + audit_store → dispatcher 审计同样落盘。"""
        audit = AuditStore(tmp_path / "space")
        inst = dispatch_task(_task("T-D2"), project_id="p1", audit_store=audit)

        entries = audit.list_audit(actor="dispatcher")
        assert len(entries) == 1
        assert entries[0]["entity"] == inst.instance_id

    def test_facade_plan_audits_scheduler(self, tmp_path: Path):
        """ExecutionEngine 门面 plan → audit (actor=scheduler, action=plan.created)。"""
        audit = AuditStore(tmp_path / "space")
        engine = ExecutionEngine()
        engine.execute_project_tasks(
            "p1",
            [_task("T-S1", priority=TaskPriority.P0), _task("T-S2", priority=TaskPriority.P1)],
            audit_store=audit,
        )

        entries = audit.list_audit(actor="scheduler")
        assert len(entries) == 1
        entry = entries[0]
        assert set(entry) == _AUDIT_FIELDS
        assert entry["action"] == "plan.created"
        assert entry["entity"].startswith("plan-")
        assert entry["input"]["project_id"] == "p1"
        # priority 排序后入选 (P0 在前)
        assert entry["input"]["task_ids"] == ["T-S1", "T-S2"]
        assert entry["output"]["tasks"]  # 计划任务列表非空
        assert entry["output"]["max_parallel"] == 5
        assert entry["result"] == "OK"

    def test_task_linking_audited_by_executor(self, tmp_path: Path):
        """Task 状态联动 (IN_PROGRESS→REVIEW) → audit (actor=executor, action=task.linked)。"""
        runtime, audit = _stores(tmp_path)
        task = _task("T-LK1", status=TaskStatus.IN_PROGRESS)
        execute_instance(
            _instance("WI-LK1", task_id="T-LK1"),
            lambda inst: "ok",
            runtime_store=runtime,
            audit_store=audit,
            task=task,
        )

        linked = [e for e in audit.list_audit() if e["action"] == "task.linked"]
        assert len(linked) == 1
        entry = linked[0]
        assert set(entry) == _AUDIT_FIELDS
        assert entry["actor"] == "executor"
        assert entry["entity"] == "T-LK1"
        assert entry["input"] == {"from": "in_progress", "to": "review"}
        assert entry["output"]["instance_id"] == "WI-LK1"
        assert entry["output"]["status"] == WorkflowInstanceStatus.SUCCESS.value
        assert entry["result"] == WorkflowInstanceStatus.SUCCESS.value

    def test_task_linking_failure_audited_by_executor(self, tmp_path: Path):
        """联动失败路径 (READY→BLOCKED) → audit (actor=executor, action=task.linked)。"""
        runtime, audit = _stores(tmp_path)

        def boom(inst: WorkflowInstance) -> str:
            raise RuntimeError("link fail")

        execute_instance(
            _instance("WI-LK2", task_id="T-LK2"),
            boom,
            runtime_store=runtime,
            audit_store=audit,
            task=_task("T-LK2", status=TaskStatus.READY),
        )

        linked = [e for e in audit.list_audit() if e["action"] == "task.linked"]
        assert len(linked) == 1
        assert linked[0]["input"] == {"from": "ready", "to": "blocked"}
        assert linked[0]["result"] == WorkflowInstanceStatus.FAILED.value

    def test_full_chain_actor_sequence(self, tmp_path: Path):
        """门面一次执行全链 actor 序: scheduler(plan) → dispatcher → executor×2 (转换) → executor (联动)。"""
        runtime, audit = _stores(tmp_path)
        engine = ExecutionEngine()
        engine.execute_project_tasks(
            "p1", [_task("T-C1")], runtime_store=runtime, audit_store=audit
        )

        entries = audit.list_audit()
        assert [e["actor"] for e in entries] == [
            "scheduler",
            "dispatcher",
            "executor",
            "executor",
            "executor",
        ]
        assert [e["action"] for e in entries] == [
            "plan.created",
            "instance.dispatched",
            "instance.transition",
            "instance.transition",
            "task.linked",
        ]


# ================================================================== AuditStore 读取: list_audit


class TestAuditStoreListAudit:
    """AuditStore.list_audit: 按 time 排序 + actor/entity/action 过滤。"""

    def test_list_audit_sorted_by_time(self, tmp_path: Path):
        """乱序时间写入 → list_audit 按 time 升序返回 (与追加顺序无关)。"""
        audit = AuditStore(tmp_path / "space")
        _write_raw_entries(
            audit,
            [
                {"time": "2026-01-01T00:00:02+00:00", "actor": "a", "action": "x", "entity": "e2", "input": None, "output": None, "result": ""},
                {"time": "2026-01-01T00:00:00+00:00", "actor": "b", "action": "y", "entity": "e0", "input": None, "output": None, "result": ""},
                {"time": "2026-01-01T00:00:01+00:00", "actor": "a", "action": "z", "entity": "e1", "input": None, "output": None, "result": ""},
            ],
        )

        entries = audit.list_audit()
        assert [e["entity"] for e in entries] == ["e0", "e1", "e2"]
        assert [e["time"] for e in entries] == [
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:01+00:00",
            "2026-01-01T00:00:02+00:00",
        ]

    def test_list_audit_filter_by_actor(self, tmp_path: Path):
        """actor 过滤: 只返回指定 actor 的条目。"""
        audit = AuditStore(tmp_path / "space")
        audit.append(actor="scheduler", action="plan.created", entity="plan-1")
        audit.append(actor="dispatcher", action="instance.dispatched", entity="WI-1")
        audit.append(actor="executor", action="instance.transition", entity="WI-1")

        assert len(audit.list_audit()) == 3
        scheduler = audit.list_audit(actor="scheduler")
        assert len(scheduler) == 1 and scheduler[0]["action"] == "plan.created"
        assert len(audit.list_audit(actor="executor")) == 1
        assert audit.list_audit(actor="nobody") == []

    def test_list_audit_filter_by_entity(self, tmp_path: Path):
        """entity 过滤: 只返回指定实体的条目。"""
        audit = AuditStore(tmp_path / "space")
        audit.append(actor="dispatcher", action="instance.dispatched", entity="WI-1")
        audit.append(actor="executor", action="instance.transition", entity="WI-1")
        audit.append(actor="executor", action="instance.transition", entity="WI-2")

        only_wi1 = audit.list_audit(entity="WI-1")
        assert len(only_wi1) == 2
        assert all(e["entity"] == "WI-1" for e in only_wi1)
        assert len(audit.list_audit(entity="WI-2")) == 1

    def test_list_audit_filter_combined(self, tmp_path: Path):
        """actor + entity 组合过滤。"""
        audit = AuditStore(tmp_path / "space")
        audit.append(actor="dispatcher", action="instance.dispatched", entity="WI-1")
        audit.append(actor="executor", action="instance.transition", entity="WI-1")
        audit.append(actor="executor", action="instance.transition", entity="WI-2")

        combined = audit.list_audit(actor="executor", entity="WI-1")
        assert len(combined) == 1
        assert combined[0]["entity"] == "WI-1"
        assert combined[0]["actor"] == "executor"

    def test_list_audit_filter_by_action(self, tmp_path: Path):
        """action 过滤: 只返回指定动作的条目。"""
        audit = AuditStore(tmp_path / "space")
        audit.append(actor="scheduler", action="plan.created", entity="plan-1")
        audit.append(actor="dispatcher", action="instance.dispatched", entity="WI-1")

        transitions = audit.list_audit(action="instance.transition")
        assert transitions == []
        assert len(audit.list_audit(action="plan.created")) == 1

    def test_list_audit_project_space_isolated(self, tmp_path: Path):
        """项目空间隔离: 不同 space_dir 的 AuditStore 互不可见。"""
        audit_a = AuditStore(tmp_path / "proj-a")
        audit_b = AuditStore(tmp_path / "proj-b")
        audit_a.append(actor="scheduler", action="plan.created", entity="plan-1")

        assert len(audit_a.list_audit()) == 1
        assert audit_b.list_audit() == []

    def test_list_audit_missing_file_empty(self, tmp_path: Path):
        """目录/文件缺失 → 空列表 (失败安全)。"""
        audit = AuditStore(tmp_path / "no-such-space")
        assert audit.list_audit() == []

    def test_list_audit_skips_corrupt_lines(self, tmp_path: Path):
        """损坏行跳过 (不可变事实源不整体失败), 有效行正常返回。"""
        audit = AuditStore(tmp_path / "space")
        audit.append(actor="dispatcher", action="instance.dispatched", entity="WI-1")
        with open(audit.path, "a", encoding="utf-8") as f:
            f.write("{not-valid-json}\n")
        audit.append(actor="executor", action="instance.transition", entity="WI-1")

        entries = audit.list_audit()
        assert len(entries) == 2  # 损坏行被跳过


# ================================================================== 不可变语义


class TestAuditImmutability:
    """不可变: 只追加不覆盖; 读取返回副本 (外部修改不影响落盘事实)。"""

    def test_append_only_no_overwrite(self, tmp_path: Path):
        """追加只增不覆盖: 后写条目不修改已落盘条目 (行级追加)。"""
        audit = AuditStore(tmp_path / "space")
        audit.append(actor="dispatcher", action="instance.dispatched", entity="WI-1")
        first = audit.path.read_text(encoding="utf-8")

        audit.append(actor="executor", action="instance.transition", entity="WI-1")
        second = audit.path.read_text(encoding="utf-8")

        assert second.startswith(first), "已有条目必须原样保留 (追加)"
        assert len(second.strip().splitlines()) == 2

    def test_read_returns_copies(self, tmp_path: Path):
        """读取返回副本: 修改返回条目不影响后续读取 (落盘事实不变)。"""
        audit = AuditStore(tmp_path / "space")
        audit.append(
            actor="dispatcher",
            action="instance.dispatched",
            entity="WI-1",
            input={"task_id": "T-1"},
        )

        entries = audit.list_audit()
        entries[0]["input"]["task_id"] = "HACKED"
        entries[0]["result"] = "tampered"
        entries[0]["time"] = "2099-01-01T00:00:00+00:00"

        fresh = audit.list_audit()
        assert fresh[0]["input"]["task_id"] == "T-1"
        assert fresh[0]["result"] == ""
        assert fresh[0]["time"] != "2099-01-01T00:00:00+00:00"

    def test_list_returns_copies_too(self, tmp_path: Path):
        """list() 同样返回副本 (不可变语义统一)。"""
        audit = AuditStore(tmp_path / "space")
        audit.append(actor="dispatcher", action="instance.dispatched", entity="WI-1")

        entries = audit.list()
        entries[0]["entity"] = "TAMPERED"

        assert audit.list()[0]["entity"] == "WI-1"

    def test_reading_does_not_modify_file(self, tmp_path: Path):
        """读取无副作用: list/list_audit 前后文件字节不变。"""
        audit = AuditStore(tmp_path / "space")
        audit.append(actor="dispatcher", action="instance.dispatched", entity="WI-1")

        before = audit.path.read_bytes()
        audit.list()
        audit.list_audit()
        audit.list_audit(actor="dispatcher", entity="WI-1")

        assert audit.path.read_bytes() == before


# ================================================================== NotificationSink 预留接口


class TestNotificationSink:
    """notify(project_id, event, payload): 默认 no-op; 可注入; 门面终态通知。"""

    def test_default_sink_is_noop(self):
        """默认 NotificationSink.notify → 无操作 (返回 None, 不抛)。"""
        sink = NotificationSink()
        assert sink.notify("p1", "task.completed", {"task_id": "T-1"}) is None

    def test_engine_without_injection_runs_noop(self, tmp_path: Path):
        """不注入 sink → 门面正常执行 (默认 no-op, 不抛)。"""
        engine = ExecutionEngine()
        result = engine.execute_project_tasks("p1", [_task("T-1")])
        assert result.outcomes[0].instance.status == WorkflowInstanceStatus.SUCCESS

    def test_injectable_sink_replaces_default(self, tmp_path: Path):
        """可注入: 注入 sink 生效 (engine.notification 即注入实例)。"""
        sink = _CollectingSink()
        engine = ExecutionEngine(notification=sink)
        assert engine.notification is sink

    def test_engine_notifies_task_completed(self, tmp_path: Path):
        """门面: instance SUCCESS → notify(project_id, "task.completed", payload)。"""
        sink = _CollectingSink()
        engine = ExecutionEngine(notification=sink)
        result = engine.execute_project_tasks("p1", [_task("T-1")])

        assert len(sink.events) == 1
        project_id, event, payload = sink.events[0]
        assert project_id == "p1"
        assert event == "task.completed"
        assert payload["task_id"] == "T-1"
        assert payload["instance_id"] == result.instances[0].instance_id
        assert payload["status"] == WorkflowInstanceStatus.SUCCESS.value
        assert payload["result"]  # 成功摘要

    def test_engine_notifies_task_failed(self, tmp_path: Path):
        """门面: instance FAILED → notify(project_id, "task.failed", payload)。"""
        def boom(instance: WorkflowInstance) -> str:
            raise RuntimeError("notify boom")

        sink = _CollectingSink()
        engine = ExecutionEngine(notification=sink)
        engine.execute_project_tasks("p1", [_task("T-1")], executor=boom)

        assert len(sink.events) == 1
        project_id, event, payload = sink.events[0]
        assert project_id == "p1"
        assert event == "task.failed"
        assert payload["task_id"] == "T-1"
        assert payload["status"] == WorkflowInstanceStatus.FAILED.value
        assert "notify boom" in payload["result"]

    def test_engine_notifies_per_task(self, tmp_path: Path):
        """多任务: 每任务终态各发一条通知 (成功/失败混合)。"""
        sink = _CollectingSink()
        engine = ExecutionEngine(notification=sink)

        def mixed(instance: WorkflowInstance) -> str:
            return "ok" if instance.task_id == "T-OK" else "ERROR: nope"

        engine.execute_project_tasks(
            "p1", [_task("T-OK"), _task("T-BAD")], executor=mixed
        )

        assert [e[1] for e in sink.events] == ["task.completed", "task.failed"]
        assert [e[2]["task_id"] for e in sink.events] == ["T-OK", "T-BAD"]


# ================================================================== ExecutionEngine 门面全链验收


class TestExecutionEngineAcceptance:
    """S10-011 §五 场景 1/5 全链: plan→dispatch→execute + runtime + audit + notify。"""

    def test_acceptance_scenario1_ready_to_success_full_chain(self, tmp_path: Path):
        """场景1: READY → 全链执行 → instance SUCCESS + Task 联动 + runtime + audit + notify;
        Task REVIEW/DONE 链可达 (受控状态机放行)。"""
        runtime, audit = _stores(tmp_path)
        sink = _CollectingSink()
        engine = ExecutionEngine(notification=sink)
        result = engine.execute_project_tasks(
            "p1",
            [_task("T-ACC1", priority=TaskPriority.P0)],
            runtime_store=runtime,
            audit_store=audit,
        )

        assert isinstance(result, ProjectExecutionResult)
        assert result.project_id == "p1"
        assert [pt.task_id for pt in result.plan.tasks] == ["T-ACC1"]
        # instance 终态 SUCCESS + 运行窗口 + result
        outcome = result.outcomes[0]
        assert outcome.instance.status == WorkflowInstanceStatus.SUCCESS
        assert outcome.instance.start_time is not None
        assert outcome.instance.end_time is not None
        assert outcome.instance.result
        # Task 联动: READY → IN_PROGRESS (受控状态机), REVIEW→DONE 后续链可达
        assert result.final_tasks == {"T-ACC1": "in_progress"}
        review = transition_task(
            outcome.task, TaskStatus.REVIEW, actor="executor", action="review.completed"
        )
        done = transition_task(review, TaskStatus.DONE, actor="executor", action="review.approved")
        assert done.status == TaskStatus.DONE
        # runtime 可恢复: workflow-execution 终态快照
        inst_id = outcome.instance.instance_id
        snapshot = runtime.load_workflow_execution(inst_id)
        assert snapshot is not None
        assert snapshot["status"] == WorkflowInstanceStatus.SUCCESS.value
        assert snapshot["end_time"] is not None
        # audit 全链路 (scheduler/dispatcher/executor 转换 + task 联动), 7 字段完整
        entries = audit.list_audit()
        assert len(entries) == 5
        assert [e["actor"] for e in entries] == [
            "scheduler", "dispatcher", "executor", "executor", "executor",
        ]
        assert [e["action"] for e in entries] == [
            "plan.created", "instance.dispatched",
            "instance.transition", "instance.transition", "task.linked",
        ]
        assert all(set(e) == _AUDIT_FIELDS for e in entries)
        # notify: task.completed
        assert sink.events == [
            (
                "p1",
                "task.completed",
                {
                    "project_id": "p1",
                    "task_id": "T-ACC1",
                    "instance_id": inst_id,
                    "status": WorkflowInstanceStatus.SUCCESS.value,
                    "result": outcome.instance.result,
                },
            )
        ]

    def test_acceptance_scenario5_failure_to_blocked_full_chain(self, tmp_path: Path):
        """场景5: 失败 → instance FAILED + Task BLOCKED + audit + notify (task.failed)。"""
        runtime, audit = _stores(tmp_path)
        sink = _CollectingSink()
        engine = ExecutionEngine(notification=sink)

        def boom(instance: WorkflowInstance) -> str:
            raise RuntimeError("build failed")

        result = engine.execute_project_tasks(
            "p1",
            [_task("T-ACC2")],
            executor=boom,
            runtime_store=runtime,
            audit_store=audit,
        )

        outcome = result.outcomes[0]
        assert outcome.instance.status == WorkflowInstanceStatus.FAILED
        assert outcome.instance.end_time is not None
        assert "build failed" in outcome.instance.result
        assert result.final_tasks == {"T-ACC2": "blocked"}
        # audit: FAILED 转换 (result 含错误) + task.linked (ready→blocked)
        entries = audit.list_audit()
        assert [e["action"] for e in entries] == [
            "plan.created", "instance.dispatched",
            "instance.transition", "instance.transition", "task.linked",
        ]
        assert entries[3]["input"]["to"] == WorkflowInstanceStatus.FAILED.value
        assert "build failed" in str(entries[3]["result"])
        assert entries[4]["input"] == {"from": "ready", "to": "blocked"}
        # notify: task.failed
        assert len(sink.events) == 1
        assert sink.events[0][1] == "task.failed"
        assert sink.events[0][2]["status"] == WorkflowInstanceStatus.FAILED.value

    def test_acceptance_multiple_tasks_parallel_batch(self, tmp_path: Path):
        """多任务全链: priority 排序 + parallel_batch + 每任务 audit/notify 完整。"""
        runtime, audit = _stores(tmp_path)
        sink = _CollectingSink()
        engine = ExecutionEngine(notification=sink)
        result = engine.execute_project_tasks(
            "p1",
            [
                _task("T-3", priority=TaskPriority.P2),
                _task("T-1", priority=TaskPriority.P0),
                _task("T-2", priority=TaskPriority.P1),
            ],
            runtime_store=runtime,
            audit_store=audit,
        )

        assert [pt.task_id for pt in result.plan.tasks] == ["T-1", "T-2", "T-3"]
        assert result.plan.parallel_batch == [["T-1", "T-2", "T-3"]]
        assert len(result.instances) == 3
        assert all(
            o.instance.status == WorkflowInstanceStatus.SUCCESS for o in result.outcomes
        )
        # 全链 audit: 1 plan + 3 × (dispatch + 2 transition + task.linked) = 13
        entries = audit.list_audit()
        assert len(entries) == 13
        assert len(audit.list_audit(actor="scheduler")) == 1
        assert len(audit.list_audit(actor="dispatcher")) == 3
        assert len(audit.list_audit(actor="executor", action="instance.transition")) == 6
        assert len(audit.list_audit(actor="executor", action="task.linked")) == 3
        # 每任务一条 task.completed 通知
        assert [e[1] for e in sink.events] == ["task.completed"] * 3
        assert sorted(e[2]["task_id"] for e in sink.events) == ["T-1", "T-2", "T-3"]

    def test_acceptance_transition_task_locked_still_works(self, tmp_path: Path):
        """回归: transition_task_locked 与全链审计共存 (封装不受影响)。"""
        audit = AuditStore(tmp_path / "space")
        task = _task("T-LOCK1", status=TaskStatus.READY)
        updated = transition_task_locked(task, TaskStatus.IN_PROGRESS, "p1", actor="user")
        assert updated.status == TaskStatus.IN_PROGRESS
        assert audit.list_audit() == []  # transition_task_locked 不写 audit.log (Task history 自有审计链)
