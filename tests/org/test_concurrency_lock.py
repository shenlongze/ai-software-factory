"""tests/org/test_concurrency_lock.py — S10-011 Task 005: Concurrency Lock (TDD)。

设计依据 (唯一): docs/sprint10/S10-011-architecture-design.md §二 7 (并发控制模型 —
per-project 锁集成: 写操作 task 状态更新/scheduler plan/workflow instance 创建持锁;
同项目串行 / 跨项目并行; 重入安全; 跨进程锁 S10-012+) + §三 Task 005
(per-project 锁集成: scheduler/dispatch/状态更新持锁) + AF-PRD-v1.md 4.7。

被测 (org/execution.py Task 005 新增/完善):
- ExecutionLock 完善: acquire(project_id, timeout=None) -> bool (超时不阻塞返回
  False; 阻塞成功返回 True) + locked(project_id, timeout) 上下文管理器
  (超时抛 LockTimeoutError) — 语义: 同项目互斥 / 同线程重入 / 跨项目不阻塞
- 写路径持锁集成 (project_id 提供时):
  - dispatch_task(..., project_id=, lock=) — workflow instance 创建持锁
  - execute_instance(..., project_id=, lock=) — 生命周期执行全程持锁
  - transition_task_locked(task, target, project_id, ...) — Task 状态更新封装
    (management.transition_task 受控状态机 per-project 锁内调用)
- ExecutionEngine 门面: execute_project_tasks (plan→dispatch→execute 持锁串行化)
  — 同项目并发写串行 (无交错/数据一致), 跨项目并行, 重入安全

并发测试全部真实多线程 (threading — barrier/event/span 记录), 零 mock。

basename 全仓库唯一 (test_org_* 前缀目录约定); 不跨目录依赖 helper。
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core", _ROOT / "factory-org"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# noqa: E402 — sys.path 就绪后导入
from org.execution import (  # noqa: E402
    AuditStore,
    ExecutionEngine,
    ExecutionLock,
    LockTimeoutError,
    ProjectExecutionResult,
    RuntimeStore,
    WorkflowInstance,
    WorkflowInstanceStatus,
    dispatch_task,
    execute_instance,
    plan_tasks,
    transition_task_locked,
)
from org.management import (  # noqa: E402
    Task,
    TaskPriority,
    TaskStatus,
    transition_task,
)


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


def _join(threads: list[threading.Thread], timeout: float = 5.0) -> None:
    """join 全部线程; 任一未退出 → AssertionError (防死锁悬挂测试)。"""
    for t in threads:
        t.join(timeout=timeout)
        assert not t.is_alive(), f"thread {t.name} did not finish within {timeout}s"


def _assert_no_interleave(log: list[str]) -> None:
    """断言 executor enter/exit 日志无交错 (enter 必须成对且不嵌套)。

    同项目持锁串行 → 任意时刻至多一个写执行; 交错 (enter,enter 相邻) 即失败。
    """
    depth = 0
    for entry in log:
        if entry.startswith("enter:"):
            assert depth == 0, f"interleaved write execution detected: {log}"
            depth += 1
        elif entry.startswith("exit:"):
            depth -= 1
            assert depth == 0, f"unbalanced executor log: {log}"
    assert depth == 0, f"unbalanced executor log: {log}"


def _make_tracked_executor(
    log: list[str], guard: threading.Lock, hold: float = 0.05
):
    """executor: enter/exit 记录 + 短驻留 (放大交错窗口, 让无锁竞争可观测)。"""

    def run(instance: WorkflowInstance) -> str:
        with guard:
            log.append(f"enter:{instance.instance_id}")
        time.sleep(hold)
        with guard:
            log.append(f"exit:{instance.instance_id}")
        return f"executed {instance.instance_id}"

    return run


class _SpanRecordingLock(ExecutionLock):
    """记录每次 acquire→release 时间跨度的 ExecutionLock (串行性观测, 真实锁)。

    overlapping_spans(project_id): 同项目任意两个持有区间重叠 → True (违反互斥)。
    """

    def __init__(self) -> None:
        super().__init__()
        self._spans: list[tuple[str, float, float]] = []
        self._guard = threading.Lock()
        self._active: dict[str, float] = {}

    def acquire(self, project_id: str, timeout: float | None = None) -> bool:
        ok = super().acquire(project_id, timeout=timeout)
        if ok:
            with self._guard:
                self._active[project_id] = time.monotonic()
        return ok

    def release(self, project_id: str) -> None:
        with self._guard:
            start = self._active.pop(project_id, None)
            if start is not None:
                self._spans.append((project_id, start, time.monotonic()))
        super().release(project_id)

    def overlapping_spans(self, project_id: str) -> bool:
        spans = [s for s in self._spans if s[0] == project_id]
        for i in range(len(spans)):
            for j in range(i + 1, len(spans)):
                a, b = spans[i], spans[j]
                if a[1] < b[2] and b[1] < a[2]:
                    return True
        return False


# ================================================================== ExecutionLock 语义 (Task 005 完善)


class TestExecutionLockTimeout:
    """acquire 超时语义: 不阻塞 / 返回 False / 释放后可获。"""

    def test_acquire_returns_true_when_free(self):
        """空闲锁 acquire 立即成功并返回 True (Task 005 返回值契约)。"""
        lock = ExecutionLock()
        assert lock.acquire("p1") is True
        lock.release("p1")

    def test_acquire_timeout_returns_false_when_held(self):
        """同项目被持有时 acquire(timeout) 超时不阻塞 → 返回 False。"""
        lock = ExecutionLock()
        lock.acquire("p1")
        started = threading.Event()
        done: list[bool] = []
        elapsed: list[float] = []

        def worker():
            started.set()
            t0 = time.monotonic()
            ok = lock.acquire("p1", timeout=0.2)
            elapsed.append(time.monotonic() - t0)
            done.append(ok)

        t = threading.Thread(target=worker)
        t.start()
        assert started.wait(1.0)
        _join([t])
        assert done == [False], "held lock acquire(timeout) must return False"
        assert elapsed[0] >= 0.15, "timeout acquire must actually wait until timeout"
        lock.release("p1")

    def test_acquire_timeout_succeeds_after_release(self):
        """释放后同项目 acquire(timeout) 立即成功 (超时语义不影响释放后获取)。"""
        lock = ExecutionLock()
        lock.acquire("p1")
        lock.release("p1")
        assert lock.acquire("p1", timeout=0.5) is True
        lock.release("p1")

    def test_locked_context_manager_blocks_until_release(self):
        """with lock.locked(project_id) 持锁; 退出后其他线程可立即获取。"""
        lock = ExecutionLock()
        entered = threading.Event()
        released = threading.Event()
        acquired_after = threading.Event()

        def holder():
            with lock.locked("p1"):
                entered.set()
                assert released.wait(2.0), "context manager never released"
            acquired_after.set()

        def waiter():
            assert entered.wait(2.0)
            lock.acquire("p1")  # holder 未退出前阻塞; 退出后成功
            acquired_after.set()
            lock.release("p1")

        t_holder = threading.Thread(target=holder)
        t_waiter = threading.Thread(target=waiter)
        t_holder.start()
        t_waiter.start()
        assert entered.wait(2.0)
        time.sleep(0.2)
        assert not acquired_after.is_set(), "waiter must block while lock held"
        released.set()
        _join([t_holder, t_waiter])
        assert acquired_after.is_set(), "waiter must acquire after release"

    def test_locked_context_manager_timeout_raises(self):
        """locked(project_id, timeout) 超时 → LockTimeoutError (不无限阻塞)。"""
        lock = ExecutionLock()
        lock.acquire("p1")
        started = threading.Event()
        outcome: list[BaseException] = []

        def worker():
            started.set()
            try:
                with lock.locked("p1", timeout=0.2):
                    outcome.append(None)
            except LockTimeoutError as exc:
                outcome.append(exc)

        t = threading.Thread(target=worker)
        t.start()
        assert started.wait(1.0)
        _join([t])
        assert outcome and isinstance(outcome[0], LockTimeoutError)
        lock.release("p1")

    def test_release_then_other_thread_acquires(self):
        """释放后其他线程可 acquire (锁状态干净, 无残留计数)。"""
        lock = ExecutionLock()
        acquired = threading.Event()

        def worker():
            lock.acquire("p1")
            acquired.set()
            lock.release("p1")

        lock.acquire("p1")
        lock.release("p1")
        t = threading.Thread(target=worker)
        t.start()
        assert acquired.wait(1.0), "other thread must acquire after release"
        _join([t])


# ================================================================== 写路径持锁集成


class TestWritePathLockIntegration:
    """dispatch_task / execute_instance 提供 project_id 时持 per-project 锁。"""

    def test_dispatch_task_blocks_while_same_project_held(self):
        """同项目锁被持有时 dispatch_task 阻塞直到释放 (写路径持锁)。"""
        lock = ExecutionLock()
        lock.acquire("p1")
        done = threading.Event()
        outcome: list[BaseException | WorkflowInstance] = []

        def worker():
            try:
                outcome.append(dispatch_task(_task("T-1"), project_id="p1", lock=lock))
            except BaseException as exc:  # noqa: BLE001 — 记录供主线程断言
                outcome.append(exc)
            finally:
                done.set()

        t = threading.Thread(target=worker)
        t.start()
        assert not done.wait(0.2), "dispatch must block while project lock held"
        lock.release("p1")
        assert done.wait(2.0), "dispatch must proceed after lock release"
        _join([t])
        assert isinstance(outcome[0], WorkflowInstance)

    def test_execute_instance_blocks_while_same_project_held(self):
        """同项目锁被持有时 execute_instance 阻塞直到释放 (生命周期执行持锁)。"""
        lock = ExecutionLock()
        lock.acquire("p1")
        done = threading.Event()

        def worker():
            try:
                execute_instance(_instance("WI-1"), project_id="p1", lock=lock)
            finally:
                done.set()

        t = threading.Thread(target=worker)
        t.start()
        assert not done.wait(0.2), "execute must block while project lock held"
        lock.release("p1")
        assert done.wait(2.0), "execute must proceed after lock release"
        _join([t])

    def test_cross_project_write_not_blocked(self):
        """跨项目不阻塞: 持有 p1 时 dispatch/execute p2 立即成功 (并行)。"""
        lock = ExecutionLock()
        lock.acquire("p1")
        dispatched = threading.Event()
        executed = threading.Event()

        def worker():
            dispatch_task(_task("T-2"), project_id="p2", lock=lock)
            dispatched.set()
            execute_instance(_instance("WI-2"), project_id="p2", lock=lock)
            executed.set()

        t = threading.Thread(target=worker)
        t.start()
        assert dispatched.wait(1.0), "cross-project dispatch must not block"
        assert executed.wait(1.0), "cross-project execute must not block"
        _join([t])
        lock.release("p1")

    def test_reentrant_execute_invokes_dispatch_same_project(self):
        """重入安全: execute_instance 内 (executor 回调) 调 dispatch_task 同项目不 deadlock。"""
        inner: list[WorkflowInstance] = []

        def executor(running: WorkflowInstance) -> str:
            inner.append(
                dispatch_task(_task("T-inner"), project_id="p1", lock=lock)
            )
            return f"done {running.instance_id}"

        lock = ExecutionLock()
        outcome = execute_instance(
            _instance("WI-1"), executor=executor, project_id="p1", lock=lock
        )
        assert outcome.instance.status == WorkflowInstanceStatus.SUCCESS
        assert len(inner) == 1, "nested dispatch inside executor must complete"
        assert inner[0].task_id == "T-inner"
        assert inner[0].status == WorkflowInstanceStatus.CREATED

    def test_reentrant_nested_locked_same_thread(self):
        """重入安全: 同线程嵌套 locked() 上下文不 deadlock (写路径嵌套)。"""
        lock = ExecutionLock()
        with lock.locked("p1"):
            with lock.locked("p1"):
                inst = dispatch_task(_task("T-1"), project_id="p1", lock=lock)
        assert inst.status == WorkflowInstanceStatus.CREATED

    def test_dispatch_without_project_id_unchanged(self):
        """不提供 project_id → 纯函数行为不变 (无锁, 现有调用兼容)。"""
        inst = dispatch_task(_task("T-1"))
        assert inst.status == WorkflowInstanceStatus.CREATED
        assert inst.task_id == "T-1"


class TestTransitionTaskLocked:
    """Task 状态更新封装: transition_task_locked 持 per-project 锁 + 状态机透传。"""

    def test_blocks_while_same_project_held(self):
        """同项目锁被持有时 transition_task_locked 阻塞直到释放。"""
        lock = ExecutionLock()
        lock.acquire("p1")
        done = threading.Event()
        task = _task("T-1", status=TaskStatus.READY)
        outcome: list[BaseException | Task] = []

        def worker():
            try:
                outcome.append(
                    transition_task_locked(
                        task, TaskStatus.IN_PROGRESS, "p1", lock=lock
                    )
                )
            except BaseException as exc:  # noqa: BLE001
                outcome.append(exc)
            finally:
                done.set()

        t = threading.Thread(target=worker)
        t.start()
        assert not done.wait(0.2), "transition must block while project lock held"
        lock.release("p1")
        assert done.wait(2.0), "transition must proceed after lock release"
        _join([t])
        assert isinstance(outcome[0], Task)
        assert outcome[0].status == TaskStatus.IN_PROGRESS

    def test_reentrant_same_thread(self):
        """重入安全: locked() 内再调 transition_task_locked 同项目不 deadlock。"""
        lock = ExecutionLock()
        task = _task("T-1", status=TaskStatus.READY)
        with lock.locked("p1"):
            updated = transition_task_locked(
                task, TaskStatus.IN_PROGRESS, "p1", lock=lock
            )
        assert updated.status == TaskStatus.IN_PROGRESS

    def test_state_machine_validation_preserved(self):
        """受控状态机校验透传: 非法转换 (TODO→DONE 跳级) 仍抛 ValueError。"""
        lock = ExecutionLock()
        task = _task("T-1", status=TaskStatus.TODO)
        with pytest.raises(ValueError):
            transition_task_locked(task, TaskStatus.DONE, "p1", lock=lock)

    def test_dependency_gate_preserved(self):
        """依赖门控透传: 有依赖且未提供 dependency_status → ValueError。"""
        lock = ExecutionLock()
        task = _task("T-1", status=TaskStatus.READY, dependency=["T-0"])
        with pytest.raises(ValueError):
            transition_task_locked(task, TaskStatus.IN_PROGRESS, "p1", lock=lock)

    def test_dependency_satisfied_transition(self):
        """依赖满足时 READY→IN_PROGRESS 成功 (dependency_status 透传)。"""
        lock = ExecutionLock()
        task = _task("T-1", status=TaskStatus.READY, dependency=["T-0"])
        updated = transition_task_locked(
            task,
            TaskStatus.IN_PROGRESS,
            "p1",
            lock=lock,
            actor="executor",
            action="instance.linked",
            dependency_status={"T-0": TaskStatus.DONE},
        )
        assert updated.status == TaskStatus.IN_PROGRESS

    def test_pure_function_unchanged(self):
        """封装不改入参 (原 task 不变, 返回新对象 — 与 transition_task 同语义)。"""
        lock = ExecutionLock()
        task = _task("T-1", status=TaskStatus.READY)
        updated = transition_task_locked(task, TaskStatus.IN_PROGRESS, "p1", lock=lock)
        assert task.status == TaskStatus.READY
        assert updated.status == TaskStatus.IN_PROGRESS


# ================================================================== 真实多线程并发写安全


class TestConcurrentWriteSafety:
    """真实多线程 (threading) 并发写: 同项目串行 / 无交错 / 数据一致。"""

    def test_two_threads_execute_same_project_serialized(self, tmp_path: Path):
        """两线程同时 execute_instance (同项目) → 顺序执行 (executor 无交错)。"""
        log: list[str] = []
        guard = threading.Lock()
        executor = _make_tracked_executor(log, guard)
        store = RuntimeStore(tmp_path / "space")
        audit = AuditStore(tmp_path / "space")
        barrier = threading.Barrier(2)
        outcomes: list[BaseException | object] = []

        def worker(inst: WorkflowInstance):
            try:
                barrier.wait(timeout=5)
                outcomes.append(
                    execute_instance(
                        inst,
                        executor=executor,
                        runtime_store=store,
                        audit_store=audit,
                        project_id="p1",
                    )
                )
            except BaseException as exc:  # noqa: BLE001
                outcomes.append(exc)

        threads = [
            threading.Thread(target=worker, args=(_instance("WI-A", "T-A"),)),
            threading.Thread(target=worker, args=(_instance("WI-B", "T-B"),)),
        ]
        for t in threads:
            t.start()
        _join(threads)

        _assert_no_interleave(log)
        assert len(outcomes) == 2 and all(
            not isinstance(o, BaseException) for o in outcomes
        )
        # 数据一致: 两个实例 runtime 均落盘为终态 SUCCESS
        for inst_id in ("WI-A", "WI-B"):
            record = store.load_workflow_execution(inst_id)
            assert record is not None, f"runtime record missing for {inst_id}"
            assert record["status"] == WorkflowInstanceStatus.SUCCESS.value
            assert record["result"].startswith("executed ")
        assert len(audit.list()) == 4, "2 instances × (RUNNING + terminal) audit entries"

    def test_two_threads_plan_dispatch_same_project_no_race(self):
        """两线程同时 plan+dispatch (同项目) → 无 race: 持锁区间不重叠 + 实例数正确。"""
        tasks = [
            _task("T-1", priority=TaskPriority.P0),
            _task("T-2", priority=TaskPriority.P1),
            _task("T-3", priority=TaskPriority.P2),
        ]
        lock = _SpanRecordingLock()
        barrier = threading.Barrier(2)
        results: list[BaseException | list[WorkflowInstance]] = []

        def worker():
            try:
                barrier.wait(timeout=5)
                plan = plan_tasks(tasks, max_parallel=5)
                instances = [
                    dispatch_task(t, all_tasks=tasks, project_id="p1", lock=lock)
                    for t in tasks
                    if t.id in {pt.task_id for pt in plan.tasks}
                ]
                results.append(instances)
            except BaseException as exc:  # noqa: BLE001
                results.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        _join(threads)

        assert not lock.overlapping_spans("p1"), "same-project lock spans must not overlap"
        assert len(results) == 2 and all(
            not isinstance(r, BaseException) for r in results
        )
        a_instances, b_instances = results[0], results[1]
        assert len(a_instances) == 3 and len(b_instances) == 3, "each thread dispatches full plan"
        all_ids = [i.instance_id for i in a_instances + b_instances]
        assert len(all_ids) == len(set(all_ids)) == 6, "instance ids unique across threads"
        for instances in (a_instances, b_instances):
            assert {i.task_id for i in instances} == {"T-1", "T-2", "T-3"}

    def test_parallel_execution_across_projects(self):
        """跨项目并行: 两线程不同项目同时 execute → 互不阻塞 (总耗时≈单次)。"""
        log: list[str] = []
        guard = threading.Lock()
        barrier = threading.Barrier(2)
        outcomes: list[BaseException | object] = []

        def worker(inst: WorkflowInstance, project_id: str):
            try:
                barrier.wait(timeout=5)
                outcomes.append(
                    execute_instance(
                        inst,
                        executor=_make_tracked_executor(log, guard, hold=0.15),
                        project_id=project_id,
                    )
                )
            except BaseException as exc:  # noqa: BLE001
                outcomes.append(exc)

        t0 = time.monotonic()
        threads = [
            threading.Thread(target=worker, args=(_instance("WI-A", "T-A"), "p1")),
            threading.Thread(target=worker, args=(_instance("WI-B", "T-B"), "p2")),
        ]
        for t in threads:
            t.start()
        _join(threads)
        elapsed = time.monotonic() - t0

        assert len(outcomes) == 2 and all(
            not isinstance(o, BaseException) for o in outcomes
        )
        assert elapsed < 0.28, f"cross-project should run in parallel, took {elapsed:.2f}s"


# ================================================================== ExecutionEngine 门面


class TestExecutionEngineFacade:
    """ExecutionEngine.execute_project_tasks: plan→dispatch→execute 持锁串行化。"""

    def _engine(self, **kw) -> ExecutionEngine:
        return ExecutionEngine(**kw)

    def test_execute_project_tasks_full_flow(self):
        """门面全流程: plan (priority 排序) → dispatch → execute (SUCCESS) → task 联动。"""
        tasks = [
            _task("T-1", priority=TaskPriority.P2),
            _task("T-2", priority=TaskPriority.P0),
            _task("T-3", priority=TaskPriority.P1),
        ]
        engine = self._engine()
        result = engine.execute_project_tasks("p1", tasks)

        assert isinstance(result, ProjectExecutionResult)
        assert result.project_id == "p1"
        assert [pt.task_id for pt in result.plan.tasks] == ["T-2", "T-3", "T-1"]
        assert len(result.instances) == 3
        assert len(result.outcomes) == 3
        for outcome in result.outcomes:
            assert outcome.instance.status == WorkflowInstanceStatus.SUCCESS
        # READY → IN_PROGRESS 联动 (task 状态更新走受控状态机)
        assert result.final_tasks == {"T-1": "in_progress", "T-2": "in_progress", "T-3": "in_progress"}

    def test_execute_project_tasks_holds_lock_across_whole_flow(self):
        """门面全程持锁: 外部持有同项目锁 → execute_project_tasks 阻塞直到释放。"""
        lock = ExecutionLock()
        lock.acquire("p1")
        done = threading.Event()
        result: list[BaseException | ProjectExecutionResult] = []

        def worker():
            try:
                result.append(
                    self._engine(lock=lock).execute_project_tasks(
                        "p1", [_task("T-1")]
                    )
                )
            except BaseException as exc:  # noqa: BLE001
                result.append(exc)
            finally:
                done.set()

        t = threading.Thread(target=worker)
        t.start()
        assert not done.wait(0.2), "engine must block while project lock held"
        lock.release("p1")
        assert done.wait(2.0), "engine must proceed after lock release"
        _join([t])
        assert isinstance(result[0], ProjectExecutionResult)
        assert len(result[0].instances) == 1
        assert (
            result[0].outcomes[0].instance.status
            == WorkflowInstanceStatus.SUCCESS
        )

    def test_two_engines_same_project_concurrent_serialized(self, tmp_path: Path):
        """两线程同项目并发 execute_project_tasks → 串行 (executor 无交错) + 结果完整。"""
        log: list[str] = []
        guard = threading.Lock()
        store = RuntimeStore(tmp_path / "space")
        audit = AuditStore(tmp_path / "space")
        engine = self._engine()
        tasks = [_task("T-1"), _task("T-2")]
        barrier = threading.Barrier(2)
        results: list[BaseException | ProjectExecutionResult] = []

        def worker():
            try:
                barrier.wait(timeout=5)
                results.append(
                    engine.execute_project_tasks(
                        "p1",
                        tasks,
                        executor=_make_tracked_executor(log, guard),
                        runtime_store=store,
                        audit_store=audit,
                    )
                )
            except BaseException as exc:  # noqa: BLE001
                results.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        _join(threads)

        _assert_no_interleave(log)
        assert len(results) == 2 and all(
            not isinstance(r, BaseException) for r in results
        )
        for r in results:
            assert len(r.instances) == 2
            assert all(
                o.instance.status == WorkflowInstanceStatus.SUCCESS for o in r.outcomes
            )
        # 数据一致: 4 个实例 runtime 全部终态 SUCCESS (每实例 RUNNING+终态 2 条 audit)
        assert len(audit.list()) == 8, "4 instances × 2 transitions"

    def test_cross_project_engine_runs_in_parallel(self):
        """跨项目并行: p1 慢执行 (持锁) 期间 p2 的 execute_project_tasks 不受阻塞。"""
        engine = self._engine()
        done_p2 = threading.Event()
        done_p1 = threading.Event()
        barrier = threading.Barrier(2)

        def slow(instance: WorkflowInstance) -> str:
            time.sleep(0.4)
            return f"slow {instance.instance_id}"

        def worker_p1():
            barrier.wait(timeout=5)
            engine.execute_project_tasks(
                "p1", [_task("T-1")], executor=slow
            )
            done_p1.set()

        def worker_p2():
            barrier.wait(timeout=5)
            engine.execute_project_tasks("p2", [_task("T-2")])
            done_p2.set()

        t1 = threading.Thread(target=worker_p1)
        t2 = threading.Thread(target=worker_p2)
        t1.start()
        t2.start()
        assert done_p2.wait(2.0), "p2 must complete while p1 still executing"
        assert not done_p1.is_set(), "p1 (slow) should still be running"
        _join([t1, t2])

    def test_skips_non_ready_and_records_waiting_dependency(self):
        """门面只执行 READY+依赖满足; TODO/BLOCKED 不执行; 依赖未满足记录原因。"""
        tasks = [
            _task("T-1", status=TaskStatus.READY),
            _task("T-2", status=TaskStatus.TODO),          # 非 READY → 不入选
            _task("T-3", status=TaskStatus.BLOCKED),       # BLOCKED → 不执行
            _task("T-4", status=TaskStatus.READY, dependency=["T-X"]),  # 依赖未满足
        ]
        engine = self._engine()
        result = engine.execute_project_tasks("p1", tasks)

        assert [pt.task_id for pt in result.plan.tasks] == ["T-1"]
        assert result.plan.waiting_dependency == {"T-4": "Waiting dependency Task T-X"}
        assert len(result.instances) == 1
        assert result.instances[0].task_id == "T-1"
        assert result.final_tasks == {
            "T-1": "in_progress",
            "T-2": "todo",
            "T-3": "blocked",
            "T-4": "ready",
        }

    def test_failed_execution_marks_task_blocked(self):
        """executor 抛异常 → instance FAILED + task BLOCKED (失败路径联动)。"""
        def boom(instance: WorkflowInstance) -> str:
            raise RuntimeError("boom")

        tasks = [_task("T-1")]
        engine = self._engine()
        result = engine.execute_project_tasks("p1", tasks, executor=boom)

        assert len(result.outcomes) == 1
        outcome = result.outcomes[0]
        assert outcome.instance.status == WorkflowInstanceStatus.FAILED
        assert outcome.instance.result == "RuntimeError: boom"
        assert result.final_tasks == {"T-1": "blocked"}

    def test_runtime_and_audit_written_by_engine(self, tmp_path: Path):
        """门面注入 runtime/audit store → 每次转换落盘 (可恢复 + 审计链)。"""
        store = RuntimeStore(tmp_path / "space")
        audit = AuditStore(tmp_path / "space")
        engine = self._engine()
        result = engine.execute_project_tasks(
            "p1", [_task("T-1")], runtime_store=store, audit_store=audit
        )

        inst_id = result.instances[0].instance_id
        running = store.load_workflow_execution(inst_id)
        assert running is not None and running["status"] == WorkflowInstanceStatus.SUCCESS.value
        entries = audit.list()
        assert len(entries) == 2
        assert [e["action"] for e in entries] == ["instance.transition", "instance.transition"]
        assert [e["result"] for e in entries] == ["OK", "OK"]

    def test_reentrant_engine_inside_executor(self):
        """重入安全: executor 回调内再调 execute_project_tasks 同项目不 deadlock。"""
        engine = self._engine()
        inner: list[ProjectExecutionResult] = []

        def nested(instance: WorkflowInstance) -> str:
            inner.append(engine.execute_project_tasks("p1", [_task("T-inner")]))
            return "nested done"

        result = engine.execute_project_tasks("p1", [_task("T-1")], executor=nested)
        assert len(inner) == 1
        assert (
            inner[0].outcomes[0].instance.status
            == WorkflowInstanceStatus.SUCCESS
        )
        assert result.outcomes[0].instance.status == WorkflowInstanceStatus.SUCCESS

    def test_transition_task_still_available_for_direct_use(self):
        """回归: management.transition_task 直接使用不受影响 (封装未破坏纯函数)。"""
        task = _task("T-1", status=TaskStatus.READY)
        updated = transition_task(task, TaskStatus.IN_PROGRESS, actor="user")
        assert updated.status == TaskStatus.IN_PROGRESS
        assert task.status == TaskStatus.READY
