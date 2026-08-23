"""tests/console/test_m3c_scheduler.py — M3c 并行调度执行契约测试 (S10-090 M3-3)。

覆盖 (Hermes 规格 §6, 轮次手算对照):
1. 无依赖并行: A/B/C 无依赖, max_c=3 → 1 轮 [A,B,C] (同轮并行)
2. 单链串行: db→api→frontend→test → 4 轮, 每轮 1 任务 (关键路径语义)
3. 汇聚: {A,B}→C → 轮1 [A,B], 轮2 [C] (先并行后串行)
4. 同文件冲突: A/B 同 target_file → 串行 (不同轮) + conflicts 记录
5. 并发上限: 5 就绪任务 max_c=2 → 轮1[2], 轮2[2], 轮3[1]
6. 向后兼容: max_c=1 → 单任务轮 (零变化); 无 plan → 旧路径 (诚实降级)

额外 (规格验收):
- schedule.json 落盘 {rounds, order, conflicts, max_concurrency, created_at}
- 环 → 失败安全降级顺序执行 (诚实标注, 不伪造并行)
- orchestrator parallel 模式: 消费 plan.json → rounds 依序执行 (solo 零变化)

basename 全仓库唯一 (test_console_* 前缀); 本目录自洽 (conftest 已挂仓库根)。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

C_MOD = importlib.import_module("factory-console.session.conflicts")
ORCH_MOD = importlib.import_module("factory-console.session.orchestrator")
SCH_MOD = importlib.import_module("factory-console.session.scheduler")

TaskScheduler = SCH_MOD.TaskScheduler
ScheduleResult = SCH_MOD.ScheduleResult


def _task(tid: str, **kw) -> dict:
    """原子任务构造 (显式 target_file 参与冲突检测; 缺省无文件可并行)。"""
    d = {"id": tid, "name": tid, "agent_type": "backend", "agent": "backend-1"}
    d.update(kw)
    return d


def _plan(tasks: list[dict], edges: list[tuple[str, str]] | None = None) -> dict:
    """M3b plan.json 内容模型 (tasks + edges, 验收 §0 口径)。"""
    return {
        "project_id": "demo",
        "tasks": tasks,
        "edges": [
            {"from_task": src, "to_task": dst} for src, dst in (edges or [])
        ],
        "order": [t["id"] for t in tasks],
    }


class _Sched:
    """测试装配: 独立调度器 + 项目级冲突解决文件 (零 ~/.factory 污染)。

    schedule 调用缺省注入 tmp 冲突解决器 (同 orchestrator parallel 装配口径);
    prepare/ready_tasks 透传 — 与真实 TaskScheduler 接口一致。
    """

    def __init__(self, sched: TaskScheduler, resolver: C_MOD.ConflictResolver) -> None:
        self._sched = sched
        self._resolver = resolver

    def schedule(self, plan, state, **kw):
        kw.setdefault("conflict_resolver", self._resolver)
        return self._sched.schedule(plan, state, **kw)

    def prepare(self, *args, **kw):
        return self._sched.prepare(*args, conflict_resolver=self._resolver, **kw)

    def ready_tasks(self, *args, **kw):
        return self._sched.ready_tasks(*args, **kw)


def _scheduler(tmp_path: Path) -> tuple[_Sched, Path]:
    """独立调度器 (tmp 工作区 + 项目级冲突解决文件 — 零 ~/.factory 污染)。"""
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    resolver = C_MOD.ConflictResolver(resolution_file=ws / "conflict_resolution.json")
    return _Sched(TaskScheduler(workspace=ws), resolver), ws


# ---------------------------------------------------------------- 1. 无依赖并行

class TestIndependentParallel:
    def test_three_no_deps_max_c3_same_round(self, tmp_path):
        """A/B/C 无依赖, max_c=3 → 1 轮 [A,B,C] (同轮并行)。"""
        sched, _ = _scheduler(tmp_path)
        r = sched.schedule(
            _plan([_task("A"), _task("B"), _task("C")]),
            {"completed": []},
            max_concurrency=3,
        )
        assert r.rounds == [["A", "B", "C"]]
        assert r.order == ["A", "B", "C"]
        assert r.degraded is False
        assert r.conflicts == []

    def test_ready_tasks_indegree_zero(self, tmp_path):
        """ready_tasks: 无依赖任务在 completed=∅ 时就绪; 有依赖则需先完成。"""
        sched, _ = _scheduler(tmp_path)
        sched.prepare(
            _plan([_task("A"), _task("B"), _task("C")], edges=[("A", "C"), ("B", "C")])
        )
        assert sorted(sched.ready_tasks(set())) == ["A", "B"]
        assert sched.ready_tasks({"A"}) == ["A", "B"]
        assert sched.ready_tasks({"A", "B"}) == ["A", "B", "C"]


# ---------------------------------------------------------------- 2. 单链串行

class TestSingleChain:
    def test_db_api_frontend_test_four_rounds(self, tmp_path):
        """db→api→frontend→test → 4 轮, 每轮 1 任务 (关键路径语义串行)。"""
        sched, _ = _scheduler(tmp_path)
        tasks = [_task("db"), _task("api"), _task("frontend"), _task("test")]
        edges = [("db", "api"), ("api", "frontend"), ("frontend", "test")]
        r = sched.schedule(_plan(tasks, edges), {"completed": []}, max_concurrency=4)
        assert r.rounds == [["db"], ["api"], ["frontend"], ["test"]]
        assert r.order == ["db", "api", "frontend", "test"]
        assert r.degraded is False


# ---------------------------------------------------------------- 3. 汇聚

class TestMerge:
    def test_merge_parallel_then_serial(self, tmp_path):
        """{A,B}→C → 轮1 [A,B] (并行支路), 轮2 [C] (汇聚后串行)。"""
        sched, _ = _scheduler(tmp_path)
        tasks = [_task("A"), _task("B"), _task("C")]
        edges = [("A", "C"), ("B", "C")]
        r = sched.schedule(_plan(tasks, edges), {"completed": []}, max_concurrency=3)
        assert r.rounds == [["A", "B"], ["C"]]
        assert r.order == ["A", "B", "C"]
        assert r.degraded is False


# ---------------------------------------------------------------- 4. 同文件冲突

class TestFileConflict:
    def test_same_target_file_serialized_with_conflicts(self, tmp_path):
        """A/B 同 target_file → 不同轮 (串行) + conflicts 记录 (task/reason/resolution)。"""
        sched, _ = _scheduler(tmp_path)
        tasks = [_task("A", target_file="src/model.py"), _task("B", target_file="src/model.py")]
        r = sched.schedule(_plan(tasks), {"completed": []}, max_concurrency=3)
        # 串行化: A 先, B 后 (不同轮)
        assert r.rounds == [["A"], ["B"]]
        assert r.order == ["A", "B"]
        assert r.degraded is False
        assert len(r.conflicts) == 1
        c = r.conflicts[0]
        assert c["task"] == "B"
        assert "src/model.py" in c["reason"]
        assert c.get("resolution") in ("dependency_delay", "serial_execution", "task_reorder")

    def test_conflict_with_third_independent_task(self, tmp_path):
        """A/B 同文件冲突串行; 独立 C 与 A 同轮 (冲突只串行冲突对)。"""
        sched, _ = _scheduler(tmp_path)
        tasks = [
            _task("A", target_file="src/model.py"),
            _task("B", target_file="src/model.py"),
            _task("C", target_file="src/other.py"),
        ]
        r = sched.schedule(_plan(tasks), {"completed": []}, max_concurrency=3)
        assert r.rounds == [["A", "C"], ["B"]]
        assert [c["task"] for c in r.conflicts] == ["B"]


# ---------------------------------------------------------------- 5. 并发上限

class TestConcurrencyLimit:
    def test_five_ready_max_c2_three_rounds(self, tmp_path):
        """5 就绪任务 max_c=2 → 轮1[2], 轮2[2], 轮3[1] (分桶语义)。"""
        sched, _ = _scheduler(tmp_path)
        tasks = [_task("A"), _task("B"), _task("C"), _task("D"), _task("E")]
        r = sched.schedule(_plan(tasks), {"completed": []}, max_concurrency=2)
        assert r.rounds == [["A", "B"], ["C", "D"], ["E"]]
        assert r.order == ["A", "B", "C", "D", "E"]
        assert r.degraded is False

    def test_concurrency_combines_with_dependencies(self, tmp_path):
        """依赖 + 并发上限: {A,B}→C, max_c=1 → A/B 分两轮, C 第三轮。"""
        sched, _ = _scheduler(tmp_path)
        tasks = [_task("A"), _task("B"), _task("C")]
        edges = [("A", "C"), ("B", "C")]
        r = sched.schedule(_plan(tasks, edges), {"completed": []}, max_concurrency=1)
        assert r.rounds == [["A"], ["B"], ["C"]]


# ---------------------------------------------------------------- 6. 向后兼容

class TestBackwardCompatibility:
    def test_max_c1_single_task_rounds(self, tmp_path):
        """max_c=1 → 每轮单任务 (旧顺序零变化: order = 计划序)。"""
        sched, _ = _scheduler(tmp_path)
        tasks = [_task("A"), _task("B"), _task("C")]
        r = sched.schedule(_plan(tasks), {"completed": []}, max_concurrency=1)
        assert r.rounds == [["A"], ["B"], ["C"]]
        assert r.order == ["A", "B", "C"]
        assert r.max_concurrency == 1
        assert r.degraded is False

    def test_no_plan_degrades_sequential_honest(self, tmp_path):
        """无 plan (None) → 降级顺序 (degraded=True 诚实标注, 不伪造并行)。"""
        sched, _ = _scheduler(tmp_path)
        r = sched.schedule(None, {"completed": []}, max_concurrency=3)
        assert r.rounds == []
        assert r.order == []
        assert r.degraded is True
        assert "降级" in r.degradation_reason

    def test_empty_plan_degrades_sequential_honest(self, tmp_path):
        """plan 无任务 → 降级顺序 (degraded=True 诚实标注)。"""
        sched, _ = _scheduler(tmp_path)
        r = sched.schedule({"tasks": [], "edges": []}, {"completed": []}, max_concurrency=3)
        assert r.degraded is True
        assert "无 plan" in r.degradation_reason


# ---------------------------------------------------------------- 落盘 + 失败安全

class TestPersistenceAndFailSafe:
    def test_schedule_json_persisted(self, tmp_path):
        """schedule.json 落盘 {rounds, order, conflicts, max_concurrency, created_at}。"""
        sched, ws = _scheduler(tmp_path)
        sched_file = ws / "projects" / "demo" / "schedule.json"
        tasks = [_task("A"), _task("B"), _task("C")]
        edges = [("A", "C"), ("B", "C")]
        r = sched.schedule(
            _plan(tasks, edges),
            {"completed": [], "schedule_file": str(sched_file)},
            max_concurrency=3,
        )
        assert sched_file.is_file()
        data = json.loads(sched_file.read_text(encoding="utf-8"))
        assert data["rounds"] == [["A", "B"], ["C"]]
        assert data["order"] == ["A", "B", "C"]
        assert data["max_concurrency"] == 3
        assert data["created_at"]
        assert "conflicts" in data
        # ScheduleResult.state 携带落盘路径 (可审计)
        assert Path(r.state["schedule_file"]) == sched_file
        assert r.state["rounds"] == [["A", "B"], ["C"]]

    def test_cycle_degrades_sequential_honest(self, tmp_path):
        """依赖成环 → 失败安全降级顺序执行 (degraded=True, 不伪造并行, 不抛)。"""
        sched, _ = _scheduler(tmp_path)
        tasks = [_task("A"), _task("B")]
        edges = [("A", "B"), ("B", "A")]  # 环
        r = sched.schedule(_plan(tasks, edges), {"completed": []}, max_concurrency=3)
        assert r.degraded is True
        assert "成环" in r.degradation_reason
        # 降级后仍产出完整顺序 (顺序执行, 每任务单轮)
        assert r.rounds == [["A"], ["B"]]
        assert sorted(r.order) == ["A", "B"]

    def test_resume_completed_tasks_skipped_in_ready(self, tmp_path):
        """state 含已完成任务 → 后续就绪判定跳过 (resume 语义)。"""
        sched, _ = _scheduler(tmp_path)
        tasks = [_task("A"), _task("B"), _task("C")]
        edges = [("A", "C"), ("B", "C")]
        r = sched.schedule(
            _plan(tasks, edges),
            {"completed": ["A", "B"], "tasks": [
                {"id": "A", "status": "completed"},
                {"id": "B", "status": "completed"},
                {"id": "C", "status": "pending"},
            ]},
            max_concurrency=3,
        )
        assert r.rounds == [["C"]]
        assert r.order == ["C"]


# ---------------------------------------------------------------- orchestrator parallel

class TestOrchestratorParallelMode:
    def _project(
        self, root: Path, *, plan_tasks: list[dict], exec_tasks: list[dict], with_plan: bool = True
    ) -> Path:
        """projects/<slug>/ 固定资产 (execution_plan.json + project.json + 可选 plan.json)。"""
        pdir = root / "projects" / "demo"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "execution_plan.json").write_text(
            json.dumps({"tasks": exec_tasks, "count": len(exec_tasks)}, ensure_ascii=False),
            encoding="utf-8",
        )
        (pdir / "project.json").write_text(
            json.dumps({"name": "demo", "status": "execution_ready"}, ensure_ascii=False),
            encoding="utf-8",
        )
        if with_plan:
            (pdir / "plan.json").write_text(
                json.dumps(_plan(plan_tasks), ensure_ascii=False), encoding="utf-8"
            )
        return pdir

    def _run(self, orch, slug="demo", **kw):
        calls: list[str] = []
        def execute_fn(task, project_dir, workspace):
            calls.append(str(task.get("id")))
            return {"success": True, "artifact": ""}
        result = orch.execute_project(slug, execute_fn=execute_fn, **kw)
        return result, calls

    def test_parallel_consumes_plan_rounds(self, tmp_path):
        """parallel 模式: plan.json rounds [A,B] → [C] 依序执行 (A,B 同轮先, C 后)。"""
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        pdir = self._project(
            tmp_path,
            plan_tasks=[
                _task("A", target_file="src/a.py"),
                _task("B", target_file="src/b.py"),
                _task("C", target_file="src/c.py"),
            ],
            exec_tasks=[
                _task("A"), _task("B"), _task("C"),
            ],
        )
        # plan.json 边: A→C, B→C (汇聚)
        plan = json.loads((pdir / "plan.json").read_text(encoding="utf-8"))
        plan["edges"] = [{"from_task": "A", "to_task": "C"}, {"from_task": "B", "to_task": "C"}]
        (pdir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        result, calls = self._run(orch, mode="parallel", max_concurrency=3)
        assert result.failed_tasks == 0
        assert calls == ["A", "B", "C"]
        state = orch._load_state(pdir)
        assert state.schedule["rounds"] == [["A", "B"], ["C"]]
        assert state.schedule["degraded"] is False
        data = json.loads((pdir / "schedule.json").read_text(encoding="utf-8"))
        assert data["rounds"] == [["A", "B"], ["C"]]
        assert data["max_concurrency"] == 3

    def test_parallel_no_plan_degrades_to_sequential(self, tmp_path):
        """parallel 无 plan.json → 降级顺序执行 (诚实标注, 任务全执行不失败)。"""
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        pdir = self._project(
            tmp_path,
            plan_tasks=[],
            exec_tasks=[_task("A"), _task("B")],
            with_plan=False,
        )
        result, calls = self._run(orch, mode="parallel", max_concurrency=2)
        assert result.failed_tasks == 0
        assert calls == ["A", "B"]
        state = orch._load_state(pdir)
        assert state.schedule["degraded"] is True
        assert "降级" in state.schedule["reason"]

    def test_solo_mode_unchanged(self, tmp_path):
        """solo 模式 (默认) 零变化: 无 schedule 落盘 / state.schedule 为空。"""
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        pdir = self._project(
            tmp_path,
            plan_tasks=[_task("A"), _task("B")],
            exec_tasks=[_task("A"), _task("B")],
            with_plan=True,
        )
        result, calls = self._run(orch, mode="solo")
        assert result.failed_tasks == 0
        assert calls == ["A", "B"]
        assert not (pdir / "schedule.json").is_file()
        assert orch._load_state(pdir).schedule == {}
