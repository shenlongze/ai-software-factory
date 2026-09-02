"""tests/org/test_task_state_machine.py — S10-010 Task 002: Task 生命周期状态机 (TDD)。

覆盖 (org/management.py 新增受控逻辑):
- TASK_TRANSITIONS 受控转换表 (PRD 4.3 + project-management-system.md §三 六态约定):
    todo → (ready, blocked)          ready → (in_progress, blocked)
    in_progress → (blocked, review)  blocked → (ready, in_progress)
    review → (in_progress, done)     done → ()
- transition_task: 合法逐步推进 / 非法拒绝 (跳级/回退/终态后/同态) /
  不可变 (返回新 Task, 原对象不变) / history 审计链每次转换追加
  {time, actor, action, result} (PRD 4.6 — 谁什么时候干了什么)
- Dependency 校验 (PRD 4.7 依赖链: Task A → Task B):
  - 依赖未满足拒绝: A depends_on B, B 未 DONE → A 不允许 READY/IN_PROGRESS
  - B DONE 后 → A 可推进
  - validate_dependency: 自引用拒绝 / 环检测 (A→B→A 及深层环) /
    dependency 列表规范 (非空 str id 引用, 去重保序)
- Priority 排序 (P0 Critical > P1 > P2 > P3 Normal, 纯函数不改入参):
  - sort_by_priority: P0 最前, 稳定排序
- AI 排序预留 (纯函数):
  - sort_tasks: dependency 感知 (依赖未满足排后, 依赖完成优先) +
    dependency_status 缺省退化为 priority 排序

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
from org.management import (  # noqa: E402
    TASK_TRANSITIONS,
    Task,
    TaskStatus,
    sort_by_priority,
    sort_tasks,
    transition_task,
    validate_dependency,
)


def _task(task_id: str, **kw) -> Task:
    """最小 Task 构造 (id 必填, 其余默认)。"""
    return Task(id=task_id, title=f"task-{task_id}", **kw)


# ------------------------------------------------------------------ 状态机: 转换表


class TestTransitionTable:
    def test_transition_table_matches_spec(self):
        """受控转换表: 七态合法去向 (P1-FIX: FAILED 独立, BLOCKED 仅依赖传播)。"""
        assert TASK_TRANSITIONS == {
            TaskStatus.TODO: (TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.CANCELLED),
            TaskStatus.READY: (TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.CANCELLED),
            TaskStatus.IN_PROGRESS: (TaskStatus.BLOCKED, TaskStatus.REVIEW, TaskStatus.FAILED, TaskStatus.CANCELLED),
            TaskStatus.BLOCKED: (TaskStatus.READY, TaskStatus.IN_PROGRESS),
            TaskStatus.REVIEW: (TaskStatus.IN_PROGRESS, TaskStatus.DONE, TaskStatus.FAILED),
            TaskStatus.FAILED: (TaskStatus.READY, TaskStatus.BLOCKED),
            TaskStatus.CANCELLED: (TaskStatus.READY,),
            TaskStatus.DONE: (),
        }

    def test_all_six_statuses_covered(self):
        """六态全在转换表 (无遗漏态)。"""
        assert set(TASK_TRANSITIONS) == set(TaskStatus)


# ------------------------------------------------------------------ 状态机: 合法流转


class TestLegalTransitions:
    def test_forward_path_todo_to_done(self):
        """主路径逐步推进: TODO→READY→IN_PROGRESS→REVIEW→DONE。"""
        t = _task("A")
        t = transition_task(t, "ready", actor="PM")
        assert t.status == TaskStatus.READY
        t = transition_task(t, "in_progress", actor="dev")
        assert t.status == TaskStatus.IN_PROGRESS
        t = transition_task(t, "review", actor="dev")
        assert t.status == TaskStatus.REVIEW
        t = transition_task(t, "done", actor="qa")
        assert t.status == TaskStatus.DONE

    def test_blocked_recovery_path(self):
        """异常路径受控往返: TODO→BLOCKED→READY→IN_PROGRESS→BLOCKED→IN_PROGRESS→REVIEW→DONE。"""
        t = _task("A")
        t = transition_task(t, TaskStatus.BLOCKED)
        assert t.status == TaskStatus.BLOCKED
        t = transition_task(t, TaskStatus.READY)
        assert t.status == TaskStatus.READY
        t = transition_task(t, TaskStatus.IN_PROGRESS)
        assert t.status == TaskStatus.IN_PROGRESS
        t = transition_task(t, TaskStatus.BLOCKED)
        assert t.status == TaskStatus.BLOCKED
        t = transition_task(t, TaskStatus.IN_PROGRESS)
        assert t.status == TaskStatus.IN_PROGRESS
        t = transition_task(t, TaskStatus.REVIEW)
        assert t.status == TaskStatus.REVIEW
        t = transition_task(t, TaskStatus.DONE)
        assert t.status == TaskStatus.DONE

    def test_review_back_to_in_progress(self):
        """REVIEW→IN_PROGRESS (返工) 合法; 再推进 DONE。"""
        t = _task("A")
        t = transition_task(t, "ready")
        t = transition_task(t, "in_progress")
        t = transition_task(t, "review")
        t = transition_task(t, "in_progress")
        assert t.status == TaskStatus.IN_PROGRESS
        t = transition_task(t, "review")
        t = transition_task(t, "done")
        assert t.status == TaskStatus.DONE


# ------------------------------------------------------------------ 状态机: 非法拒绝


class TestIllegalTransitions:
    @pytest.mark.parametrize(
        ("start", "target"),
        [
            (TaskStatus.TODO, TaskStatus.DONE),        # 跳级
            (TaskStatus.TODO, TaskStatus.IN_PROGRESS),  # 跳级
            (TaskStatus.TODO, TaskStatus.REVIEW),       # 跳级
            (TaskStatus.READY, TaskStatus.TODO),        # 回退
            (TaskStatus.IN_PROGRESS, TaskStatus.READY),  # 回退
            (TaskStatus.REVIEW, TaskStatus.BLOCKED),    # 回退
            (TaskStatus.DONE, TaskStatus.REVIEW),       # 终态后
            (TaskStatus.DONE, TaskStatus.DONE),         # 终态后 (幂等拒绝)
            (TaskStatus.TODO, TaskStatus.TODO),         # 同态无自环
        ],
    )
    def test_illegal_transition_rejected(self, start, target):
        """非法流转 (跳级/回退/终态后/同态) → ValueError 受控拒绝。"""
        t = _task("A", status=start)
        with pytest.raises(ValueError):
            transition_task(t, target)

    def test_illegal_transition_leaves_task_untouched(self):
        """非法拒绝是纯函数失败: 原 Task 状态/history 不变 (不可变语义)。"""
        t = _task("A", status=TaskStatus.READY)
        before = t.model_dump()
        with pytest.raises(ValueError):
            transition_task(t, TaskStatus.DONE)
        assert t.model_dump() == before


# ------------------------------------------------------------------ 状态机: history 审计


class TestTransitionHistory:
    def test_transition_appends_history_entry(self):
        """每次转换追加 history 条目 {time, actor, action, result} (PRD 4.6)。"""
        t = _task("A")
        t = transition_task(t, "ready", actor="PM Agent", action="start", result="READY")
        assert len(t.history) == 1
        entry = t.history[0]
        assert entry.actor == "PM Agent"
        assert entry.action == "start"
        assert entry.result == "READY"
        assert isinstance(entry.time, str) and entry.time  # 审计时间非空

    def test_history_accumulates_across_transitions(self):
        """连续转换 history 累积 (审计链: 谁什么时候干了什么)。"""
        t = _task("A")
        t = transition_task(t, "ready", actor="PM")
        t = transition_task(t, "in_progress", actor="dev")
        t = transition_task(t, "review", actor="dev")
        t = transition_task(t, "done", actor="qa")
        assert len(t.history) == 4
        assert [e.action for e in t.history] == ["transition"] * 4
        assert [e.actor for e in t.history] == ["PM", "dev", "dev", "qa"]
        assert all(e.result == "OK" for e in t.history)

    def test_transition_is_immutable_original_unchanged(self):
        """transition_task 返回新 Task; 原对象 status/history 不变 (纯函数)。"""
        t = _task("A")
        t2 = transition_task(t, "ready", actor="PM")
        assert t2.status == TaskStatus.READY
        assert t.status == TaskStatus.TODO
        assert t.history == []
        assert len(t2.history) == 1

    def test_transition_updates_updated_at(self):
        """状态转换刷新 updated_at (变更可追踪)。"""
        t = _task("A")
        t2 = transition_task(t, "ready")
        assert t2.updated_at is not None
        assert t2.updated_at >= t.created_at


# ------------------------------------------------------------------ Dependency: 依赖未满足拒绝


class TestDependencyGating:
    def test_dependency_unsatisfied_blocks_ready(self):
        """A depends_on B, B 未 DONE → A→READY 拒绝 (依赖未满足不可就绪)。"""
        a = _task("A", dependency=["B"])
        statuses = {TaskStatus.TODO, TaskStatus.READY, TaskStatus.IN_PROGRESS}
        for st in statuses:
            with pytest.raises(ValueError, match="depend"):
                transition_task(a, "ready", dependency_status={"B": st})

    def test_dependency_unsatisfied_blocks_in_progress(self):
        """A depends_on B, B 未 DONE → A→IN_PROGRESS 拒绝 (含 blocked 恢复路径)。"""
        a = _task("A", status=TaskStatus.READY, dependency=["B"])
        with pytest.raises(ValueError, match="depend"):
            transition_task(a, "in_progress", dependency_status={"B": TaskStatus.IN_PROGRESS})
        # blocked → in_progress 同样受依赖门控
        b = _task("A", status=TaskStatus.BLOCKED, dependency=["B"])
        with pytest.raises(ValueError, match="depend"):
            transition_task(b, "in_progress", dependency_status={"B": TaskStatus.BLOCKED})

    def test_dependency_satisfied_allows_progress(self):
        """B DONE 后 → A 可推进 READY→IN_PROGRESS (依赖满足放行)。"""
        a = _task("A", status=TaskStatus.READY, dependency=["B"])
        a = transition_task(a, "in_progress", dependency_status={"B": TaskStatus.DONE})
        assert a.status == TaskStatus.IN_PROGRESS
        # 多条依赖全部 DONE 才放行
        a2 = _task("A", status=TaskStatus.READY, dependency=["B", "C"])
        a2 = transition_task(
            a2, "in_progress", dependency_status={"B": TaskStatus.DONE, "C": TaskStatus.DONE}
        )
        assert a2.status == TaskStatus.IN_PROGRESS

    def test_missing_dependency_status_rejected(self):
        """有依赖但未提供依赖状态 → 拒绝 (受控: 不静默跳过校验)。"""
        a = _task("A", dependency=["B"])
        with pytest.raises(ValueError, match="depend"):
            transition_task(a, "ready", dependency_status=None)

    def test_no_dependency_no_gate(self):
        """无依赖 → READY/IN_PROGRESS 无需依赖状态 (不受门控)。"""
        a = _task("A")
        a = transition_task(a, "ready", dependency_status=None)
        assert a.status == TaskStatus.READY
        a = transition_task(a, "in_progress", dependency_status=None)
        assert a.status == TaskStatus.IN_PROGRESS

    def test_non_gated_transitions_ignore_dependency(self):
        """非就绪/执行态转换 (→BLOCKED / →REVIEW / →DONE) 不受依赖门控。"""
        a = _task("A", dependency=["B"])
        a = transition_task(a, "blocked", dependency_status={"B": TaskStatus.TODO})
        assert a.status == TaskStatus.BLOCKED
        a = transition_task(a, "in_progress", dependency_status={"B": TaskStatus.DONE})
        a = transition_task(a, "review", dependency_status={"B": TaskStatus.DONE})
        a = transition_task(a, "done", dependency_status={"B": TaskStatus.DONE})
        assert a.status == TaskStatus.DONE


# ------------------------------------------------------------------ Dependency: 列表规范 + 环检测


class TestDependencyValidation:
    def test_self_reference_rejected(self):
        """自引用拒绝: task 不能依赖自身 (dependency 列表规范)。"""
        with pytest.raises(ValueError, match="self"):
            validate_dependency(["A"], "A")

    def test_direct_cycle_rejected(self):
        """环检测: A→B→A (更新 A 的 dependency 时) → 拒绝。"""
        # A.dependency=[B] 已存在; 现更新 B.dependency=[A] → 检测 A→B→A
        with pytest.raises(ValueError, match="cycle"):
            validate_dependency(["A"], "B", known_dependencies={"A": ["B"]})
        # 反向更新 A 同样拒绝
        with pytest.raises(ValueError, match="cycle"):
            validate_dependency(["B"], "A", known_dependencies={"B": ["A"]})

    def test_deep_cycle_rejected(self):
        """深层环: A→B→C→A 拒绝 (DFS 可达性检测)。"""
        with pytest.raises(ValueError, match="cycle"):
            validate_dependency(
                ["B"], "A",
                known_dependencies={"B": ["C"], "C": ["A"]},
            )

    def test_acyclic_dependency_accepted(self):
        """无环依赖链放行 (A→B→C, 不回到 A)。"""
        deps = validate_dependency(
            ["B"], "A",
            known_dependencies={"B": ["C"], "C": ["D"]},
        )
        assert deps == ["B"]

    def test_non_string_dependency_rejected(self):
        """dependency 元素必须为非空 str id 引用 (规范列表)。"""
        with pytest.raises(ValueError):
            validate_dependency([123], "A")
        with pytest.raises(ValueError):
            validate_dependency([""], "A")

    def test_dependency_normalized_dedup_preserve_order(self):
        """规范化: 去重且保序 (B, B, C → B, C)。"""
        assert validate_dependency(["B", "B", "C"], "A") == ["B", "C"]
        assert validate_dependency(None, "A") == []

    def test_cycle_without_task_id_not_reported(self):
        """其它任务间的环与本任务无关 → 不误报 (只检测含本任务的环)。"""
        deps = validate_dependency(
            ["B"], "A",
            known_dependencies={"B": ["C"], "C": ["B"]},  # B↔C 环, 与 A 无关
        )
        assert deps == ["B"]


# ------------------------------------------------------------------ Priority 排序


class TestPrioritySort:
    def _tasks(self):
        return [
            _task("t3", priority="P3"),
            _task("t0", priority="P0"),
            _task("t1", priority="P1"),
            _task("t2", priority="P2"),
        ]

    def test_sort_by_priority_p0_first(self):
        """P0 最高: [P3, P0, P1, P2] → [P0, P1, P2, P3]。"""
        ids = [t.id for t in sort_by_priority(self._tasks())]
        assert ids == ["t0", "t1", "t2", "t3"]

    def test_sort_by_priority_stable(self):
        """同优先级稳定排序 (保持入参相对顺序)。"""
        tasks = [_task("a", priority="P2"), _task("b", priority="P2")]
        assert [t.id for t in sort_by_priority(tasks)] == ["a", "b"]

    def test_sort_by_priority_is_pure(self):
        """纯函数: 不修改入参列表, 返回新列表。"""
        tasks = self._tasks()
        original = list(tasks)
        sort_by_priority(tasks)
        assert tasks == original

    def test_sort_by_priority_empty(self):
        """空列表 → 空列表。"""
        assert sort_by_priority([]) == []


# ------------------------------------------------------------------ AI 排序预留 (dependency 感知)


class TestSortTasks:
    def _tasks(self):
        # A: P0 但依赖 B (未满足); B: P2 无依赖 (满足) → 依赖完成优先
        return [
            _task("A", priority="P0", dependency=["B"]),
            _task("B", priority="P2"),
        ]

    def test_sort_tasks_dependency_aware_unsatisfied_last(self):
        """依赖未满足的任务排后 (即使 P0); 依赖完成优先。"""
        tasks = self._tasks()
        ids = [t.id for t in sort_tasks(tasks, dependency_status={"B": TaskStatus.TODO})]
        assert ids == ["B", "A"]

    def test_sort_tasks_satisfied_falls_to_priority(self):
        """依赖满足后按优先级: B DONE → [A(P0), B(P2)]。"""
        tasks = self._tasks()
        ids = [t.id for t in sort_tasks(tasks, dependency_status={"B": TaskStatus.DONE})]
        assert ids == ["A", "B"]

    def test_sort_tasks_without_dependency_status_falls_back(self):
        """dependency_status 缺省 → 退化为纯 priority 排序。"""
        tasks = self._tasks()
        ids = [t.id for t in sort_tasks(tasks)]
        assert ids == ["A", "B"]

    def test_sort_tasks_is_pure(self):
        """纯函数: 入参列表与任务对象均不被修改。"""
        tasks = self._tasks()
        before = [t.model_dump() for t in tasks]
        sort_tasks(tasks, dependency_status={"B": TaskStatus.TODO})
        assert [t.model_dump() for t in tasks] == before
