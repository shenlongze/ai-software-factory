"""tests/org/test_scheduler.py — S10-011 Task 002: Scheduler (TDD)。

设计依据 (唯一): docs/sprint10/S10-011-architecture-design.md §二 1 (Scheduler
架构) + §五 验收场景 2/3/4 + AF-PRD-v1.md 4.7 (AI Task Scheduler):
- 只选 READY 任务 (TODO/IN_PROGRESS/REVIEW/DONE/BLOCKED 不入选)
- dependency 必须满足 (依赖任务全部 DONE); 未满足的 READY 任务不入选,
  但记录 waiting_dependency 原因
- BLOCKED 不执行
- priority 排序: P0>P1>P2>P3 (同 priority → 创建序稳定)
- max_parallel 分批 (缺省 5): parallel_batch 每批 ≤ max_parallel
- 空输入 → 空 plan; 全不满足 → 空 tasks
- can_execute(task, all_tasks): 手动检查 → (ok, reason)

覆盖 (org/execution.py 新增纯函数):
- plan_tasks(tasks, max_parallel=5) → ExecutionPlan (无副作用, 不改入参)
- can_execute(task, all_tasks) → (bool, reason)

basename 全仓库唯一 (test_org_* 前缀目录约定); 不跨目录依赖 helper。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core", _ROOT / "factory-org"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# noqa: E402 — sys.path 就绪后导入
from org.execution import ExecutionPlan, can_execute, plan_tasks  # noqa: E402
from org.management import Task, TaskPriority, TaskStatus  # noqa: E402


def _task(
    task_id: str,
    *,
    priority: TaskPriority | str = TaskPriority.P2,
    status: TaskStatus | str = TaskStatus.READY,
    dependency: list[str] | None = None,
    assignee: str = "",
) -> Task:
    """最小 Task 构造 (id 必填, 其余默认; status 默认 READY 便于调度测试)。"""
    return Task(
        id=task_id,
        title=f"task {task_id}",
        priority=priority,
        status=status,
        dependency=list(dependency or []),
        assignee=assignee,
    )


# ------------------------------------------------------------------ 空 / 全不满足


class TestPlanTasksEmpty:
    def test_empty_input_returns_empty_plan(self):
        """空输入 → 空 plan: tasks=[] / parallel_batch=[] / max_parallel 缺省 5。"""
        plan = plan_tasks([])
        assert isinstance(plan, ExecutionPlan)
        assert plan.tasks == []
        assert plan.parallel_batch == []
        assert plan.max_parallel == 5
        assert plan.waiting_dependency == {}
        assert isinstance(plan.plan_id, str) and plan.plan_id

    def test_all_unsatisfied_returns_empty_tasks(self):
        """全不满足: 全部 READY 但依赖未 DONE → 空 tasks + 空 batches + 原因记录。"""
        t1 = _task("T-1", dependency=["T-2"])
        t2 = _task("T-2", dependency=["T-3"])
        plan = plan_tasks([t1, t2])
        assert plan.tasks == []
        assert plan.parallel_batch == []
        assert set(plan.waiting_dependency) == {"T-1", "T-2"}


# ------------------------------------------------------------------ 入选规则


class TestPlanTasksSelection:
    def test_only_ready_selected(self):
        """只选 READY: TODO/IN_PROGRESS/REVIEW/DONE/BLOCKED 全部不入选。"""
        tasks = [
            _task("T-todo", status=TaskStatus.TODO),
            _task("T-ip", status=TaskStatus.IN_PROGRESS),
            _task("T-review", status=TaskStatus.REVIEW),
            _task("T-done", status=TaskStatus.DONE),
            _task("T-blocked", status=TaskStatus.BLOCKED),
            _task("T-ready"),
        ]
        plan = plan_tasks(tasks)
        assert [pt.task_id for pt in plan.tasks] == ["T-ready"]

    def test_blocked_not_executed(self):
        """BLOCKED 不执行 (验收场景 3): blocked 任务永不入选。"""
        plan = plan_tasks([_task("T-b", status=TaskStatus.BLOCKED), _task("T-r")])
        assert [pt.task_id for pt in plan.tasks] == ["T-r"]

    def test_dependency_satisfied_selected(self):
        """依赖满足 (全部 DONE) → 入选。"""
        done = _task("T-dep", status=TaskStatus.DONE)
        ready = _task("T-1", dependency=["T-dep"])
        plan = plan_tasks([done, ready])
        assert [pt.task_id for pt in plan.tasks] == ["T-1"]

    def test_dependency_unsatisfied_excluded_with_reason(self):
        """依赖未满足的 READY 任务不入选, 但记录 waiting_dependency 原因 (验收场景 2)。"""
        in_progress = _task("T-dep", status=TaskStatus.IN_PROGRESS)
        ready = _task("T-1", dependency=["T-dep"])
        plan = plan_tasks([in_progress, ready])
        assert [pt.task_id for pt in plan.tasks] == []
        assert plan.waiting_dependency["T-1"] == "Waiting dependency Task T-dep"

    def test_missing_dependency_task_not_satisfied(self):
        """依赖任务不在列表 (未知 id) → 视为未满足。"""
        ready = _task("T-1", dependency=["T-ghost"])
        plan = plan_tasks([ready])
        assert plan.tasks == []
        assert "Waiting dependency Task T-ghost" in plan.waiting_dependency["T-1"]

    def test_multiple_unsatisfied_deps_reason_lists_all(self):
        """多个依赖未满足 → reason 列出全部。"""
        ready = _task("T-1", dependency=["T-a", "T-b"])
        plan = plan_tasks([ready])
        reason = plan.waiting_dependency["T-1"]
        assert "T-a" in reason and "T-b" in reason

    def test_only_ready_tasks_get_waiting_reason(self):
        """waiting_dependency 只记录 READY 任务: 非 READY (如 TODO) 即使有依赖也不记录。"""
        todo = _task("T-todo", status=TaskStatus.TODO, dependency=["T-a"])
        plan = plan_tasks([todo])
        assert plan.waiting_dependency == {}


# ------------------------------------------------------------------ 排序


class TestPlanTasksOrdering:
    def test_priority_sorting_p0_first(self):
        """priority 排序: P0 > P1 > P2 > P3。"""
        tasks = [
            _task("T-p3", priority=TaskPriority.P3),
            _task("T-p1", priority=TaskPriority.P1),
            _task("T-p0", priority=TaskPriority.P0),
            _task("T-p2", priority=TaskPriority.P2),
        ]
        plan = plan_tasks(tasks)
        assert [pt.task_id for pt in plan.tasks] == ["T-p0", "T-p1", "T-p2", "T-p3"]

    def test_same_priority_keeps_creation_order(self):
        """同 priority → 创建序稳定 (输入顺序保持, 稳定排序)。"""
        tasks = [
            _task("T-1", priority=TaskPriority.P0),
            _task("T-2", priority=TaskPriority.P0),
            _task("T-3", priority=TaskPriority.P0),
        ]
        plan = plan_tasks(tasks)
        assert [pt.task_id for pt in plan.tasks] == ["T-1", "T-2", "T-3"]

    def test_priority_then_creation_order(self):
        """先 priority 后创建序: P1 同组保持输入序, 且整体 P0 在前。"""
        tasks = [
            _task("T-a", priority=TaskPriority.P1),
            _task("T-b", priority=TaskPriority.P0),
            _task("T-c", priority=TaskPriority.P1),
        ]
        plan = plan_tasks(tasks)
        assert [pt.task_id for pt in plan.tasks] == ["T-b", "T-a", "T-c"]


# ------------------------------------------------------------------ 分批


class TestPlanTasksBatching:
    def test_max_parallel_batching(self):
        """6 任务 max_parallel=5 → 两批 [[5], [1]] (验收场景 4)。"""
        tasks = [_task(f"T-{i}") for i in range(6)]
        plan = plan_tasks(tasks, max_parallel=5)
        assert plan.max_parallel == 5
        assert plan.parallel_batch == [["T-0", "T-1", "T-2", "T-3", "T-4"], ["T-5"]]

    def test_batches_flat_equal_tasks_order(self):
        """分批拍平 == tasks 顺序 (调度顺序 = 执行顺序)。"""
        tasks = [_task(f"T-{i}") for i in range(7)]
        plan = plan_tasks(tasks, max_parallel=3)
        flat = [tid for batch in plan.parallel_batch for tid in batch]
        assert flat == [pt.task_id for pt in plan.tasks]
        assert [len(b) for b in plan.parallel_batch] == [3, 3, 1]

    def test_max_parallel_one_serial(self):
        """max_parallel=1 → 每任务一批 (全串行)。"""
        tasks = [_task("T-1"), _task("T-2")]
        plan = plan_tasks(tasks, max_parallel=1)
        assert plan.parallel_batch == [["T-1"], ["T-2"]]

    def test_max_parallel_less_than_one_clamped(self):
        """max_parallel ≤ 0 → 按 1 处理 (防御, 不抛错)。"""
        plan = plan_tasks([_task("T-1")], max_parallel=0)
        assert plan.max_parallel == 1
        assert plan.parallel_batch == [["T-1"]]

    def test_no_batch_when_no_tasks(self):
        """无入选任务 → parallel_batch 空列表 (不产生空批)。"""
        plan = plan_tasks([_task("T-1", status=TaskStatus.TODO)])
        assert plan.parallel_batch == []


# ------------------------------------------------------------------ PlanTask 条目 / 纯函数


class TestPlanTaskEntries:
    def test_plan_task_fields(self):
        """PlanTask 条目: task_id + agent_hint (来自 assignee) + order 1 起递增。"""
        tasks = [_task("T-1", assignee="dev"), _task("T-2", assignee="qa")]
        plan = plan_tasks(tasks)
        assert [pt.task_id for pt in plan.tasks] == ["T-1", "T-2"]
        assert plan.tasks[0].agent_hint == "dev"
        assert plan.tasks[1].agent_hint == "qa"
        assert [pt.order for pt in plan.tasks] == [1, 2]

    def test_plan_is_pure_no_input_mutation(self):
        """纯函数: 不改入参 (tasks 原列表/元素不变)。"""
        tasks = [_task("T-1"), _task("T-2", status=TaskStatus.TODO)]
        snapshot = [(t.id, t.status, t.priority) for t in tasks]
        plan_tasks(tasks)
        assert [(t.id, t.status, t.priority) for t in tasks] == snapshot
        assert len(tasks) == 2


# ------------------------------------------------------------------ can_execute 手动检查


class TestCanExecute:
    def test_ready_no_dependency_ok(self):
        """READY 且无依赖 → (True, "")。"""
        assert can_execute(_task("T-1"), []) == (True, "")

    def test_ready_dependency_done_ok(self):
        """READY 且依赖全部 DONE → (True, "")。"""
        done = _task("T-dep", status=TaskStatus.DONE)
        ready = _task("T-1", dependency=["T-dep"])
        assert can_execute(ready, [done, ready]) == (True, "")

    def test_ready_dependency_unsatisfied_reason(self):
        """READY 但依赖未满足 → (False, "Waiting dependency Task X") (验收场景 2)。"""
        in_progress = _task("T-dep", status=TaskStatus.IN_PROGRESS)
        ready = _task("T-1", dependency=["T-dep"])
        assert can_execute(ready, [in_progress, ready]) == (
            False,
            "Waiting dependency Task T-dep",
        )

    def test_ready_missing_dependency_task_reason(self):
        """依赖任务不在列表 → (False, 原因含依赖 id)。"""
        ready = _task("T-1", dependency=["T-ghost"])
        ok, reason = can_execute(ready, [ready])
        assert ok is False
        assert "T-ghost" in reason

    def test_blocked_not_executable(self):
        """BLOCKED → (False, ...) 不可执行 (BLOCKED 不执行)。"""
        ok, reason = can_execute(_task("T-1", status=TaskStatus.BLOCKED), [])
        assert ok is False
        assert "blocked" in reason

    def test_non_ready_not_executable(self):
        """非 READY (TODO/IN_PROGRESS/REVIEW/DONE) → (False, 非空原因)。"""
        for status in (
            TaskStatus.TODO,
            TaskStatus.IN_PROGRESS,
            TaskStatus.REVIEW,
            TaskStatus.DONE,
        ):
            ok, reason = can_execute(_task("T-1", status=status), [])
            assert ok is False
            assert reason
