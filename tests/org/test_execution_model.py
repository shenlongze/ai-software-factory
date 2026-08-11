"""tests/org/test_execution_model.py — S10-011 Task 001: Execution Domain Model (TDD)。

设计依据 (唯一): docs/sprint10/S10-011-architecture-design.md §二 4/5/6/7:
- §4 Workflow Instance 生命周期: CREATED → RUNNING → SUCCESS/FAILED/CANCELLED,
  受控转换表 (非法拒绝); 字段 instance_id/task_id/workflow_id/agent/skill/mcp/
  status/start_time/end_time/result/created_at
- §5 Runtime 数据模型: workspace/projects/{slug}/runtime/ 三类 JSON
  (task-execution/{task_id}.json / agent-execution/{instance_id}.json /
  workflow-execution/{instance_id}.json) — 运行上下文 (可恢复); 原子写 + 失败安全
- §6 Log/Audit: workspace/projects/{slug}/logs/audit.log 追加不可变,
  记录 {time, actor, action, entity, input, output, result}
- §7 并发控制: per-project 锁 (threading.RLock 进程内互斥):
  同项目互斥 + 同线程重入安全; 不同项目不互斥 (跨项目不阻塞)

覆盖 (org/execution.py 新模块):
- WorkflowInstance: 实体字段 + 状态机受控转换 (非法拒绝, 不可变纯函数)
- ExecutionPlan: tasks 有序列表 + parallel_batch 批 + max_parallel
- ExecutionLock: acquire/release — 同项目互斥 / 重入安全 / 跨项目不阻塞
- RuntimeStore: 三类 JSON 原子写 + 失败安全 (缺失/损坏 → None)
- AuditStore: audit.log 追加不可变 + 读取 (list) + 失败安全 (损坏行跳过)

basename 全仓库唯一 (test_org_* 前缀目录约定); 不跨目录依赖 helper。
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core", _ROOT / "factory-org"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# noqa: E402 — sys.path 就绪后导入
from org.execution import (  # noqa: E402
    WORKFLOW_INSTANCE_TRANSITIONS,
    AuditStore,
    ExecutionLock,
    ExecutionPlan,
    PlanTask,
    RuntimeStore,
    WorkflowInstance,
    WorkflowInstanceStatus,
    transition_instance,
)


def _instance(**kw) -> WorkflowInstance:
    """最小 WorkflowInstance 构造 (instance_id/task_id 必填, 其余默认)。"""
    return WorkflowInstance(instance_id="WI-1", task_id="T-1", workflow_id="W-1", **kw)


# ------------------------------------------------------------------ WorkflowInstance 实体


class TestWorkflowInstanceModel:
    def test_defaults(self):
        """字段默认值: status=CREATED, agent/skill/mcp/result 空, 时间未设置。"""
        inst = _instance()
        assert inst.status == WorkflowInstanceStatus.CREATED
        assert inst.agent == ""
        assert inst.skill == ""
        assert inst.mcp == ""
        assert inst.result == ""
        assert inst.start_time is None
        assert inst.end_time is None
        assert inst.created_at is not None

    def test_full_fields_roundtrip(self):
        """全字段构造 + to_dict 序列化 (datetime → ISO, JSON 友好)。"""
        inst = _instance(
            agent="dev",
            skill="python",
            mcp="fs",
            status=WorkflowInstanceStatus.RUNNING,
            result="partial",
        )
        d = inst.to_dict()
        assert d["instance_id"] == "WI-1"
        assert d["task_id"] == "T-1"
        assert d["workflow_id"] == "W-1"
        assert d["agent"] == "dev"
        assert d["skill"] == "python"
        assert d["mcp"] == "fs"
        assert d["status"] == "running"
        assert d["result"] == "partial"
        assert d["start_time"] is None
        assert d["end_time"] is None
        assert isinstance(d["created_at"], str) and d["created_at"]


# ------------------------------------------------------------------ WorkflowInstance 状态机


class TestWorkflowInstanceTransitions:
    def test_transition_table_matches_spec(self):
        """受控转换表: CREATED→(RUNNING, CANCELLED); RUNNING→(SUCCESS, FAILED,
        CANCELLED); 三个终态无任何合法去向 (S10-011 §4)。"""
        assert WORKFLOW_INSTANCE_TRANSITIONS == {
            WorkflowInstanceStatus.CREATED: (
                WorkflowInstanceStatus.RUNNING,
                WorkflowInstanceStatus.CANCELLED,
            ),
            WorkflowInstanceStatus.RUNNING: (
                WorkflowInstanceStatus.SUCCESS,
                WorkflowInstanceStatus.FAILED,
                WorkflowInstanceStatus.CANCELLED,
            ),
            WorkflowInstanceStatus.SUCCESS: (),
            WorkflowInstanceStatus.FAILED: (),
            WorkflowInstanceStatus.CANCELLED: (),
        }

    def test_all_statuses_covered(self):
        """全部状态在转换表中 (无遗漏态)。"""
        assert set(WORKFLOW_INSTANCE_TRANSITIONS) == set(WorkflowInstanceStatus)

    def test_forward_path_to_success(self):
        """主路径: CREATED→RUNNING→SUCCESS。"""
        inst = _instance()
        inst = transition_instance(inst, "running")
        assert inst.status == WorkflowInstanceStatus.RUNNING
        inst = transition_instance(inst, "success")
        assert inst.status == WorkflowInstanceStatus.SUCCESS

    def test_failed_path(self):
        """失败路径: CREATED→RUNNING→FAILED (result 记录错误)。"""
        inst = transition_instance(_instance(), "running")
        inst = transition_instance(inst, "failed", result="executor error")
        assert inst.status == WorkflowInstanceStatus.FAILED
        assert inst.result == "executor error"

    def test_cancelled_from_created(self):
        """未启动即取消: CREATED→CANCELLED (合法, 不经过 RUNNING)。"""
        inst = transition_instance(_instance(), "cancelled")
        assert inst.status == WorkflowInstanceStatus.CANCELLED

    def test_cancelled_from_running(self):
        """运行中取消: CREATED→RUNNING→CANCELLED。"""
        inst = transition_instance(_instance(), "running")
        inst = transition_instance(inst, "cancelled")
        assert inst.status == WorkflowInstanceStatus.CANCELLED

    @pytest.mark.parametrize(
        ("start", "target"),
        [
            (WorkflowInstanceStatus.CREATED, WorkflowInstanceStatus.SUCCESS),  # 跳级
            (WorkflowInstanceStatus.CREATED, WorkflowInstanceStatus.FAILED),   # 跳级
            (WorkflowInstanceStatus.RUNNING, WorkflowInstanceStatus.CREATED),  # 回退
            (WorkflowInstanceStatus.SUCCESS, WorkflowInstanceStatus.RUNNING),  # 终态后
            (WorkflowInstanceStatus.SUCCESS, WorkflowInstanceStatus.CREATED),  # 终态后
            (WorkflowInstanceStatus.FAILED, WorkflowInstanceStatus.RUNNING),   # 终态后
            (WorkflowInstanceStatus.CANCELLED, WorkflowInstanceStatus.RUNNING),  # 终态后
            (WorkflowInstanceStatus.CREATED, WorkflowInstanceStatus.CREATED),  # 同态无自环
            (WorkflowInstanceStatus.SUCCESS, WorkflowInstanceStatus.SUCCESS),  # 终态幂等拒绝
        ],
    )
    def test_illegal_transition_rejected(self, start, target):
        """非法流转 (跳级/回退/终态后/同态) → ValueError 受控拒绝。"""
        inst = _instance(status=start)
        with pytest.raises(ValueError):
            transition_instance(inst, target)

    def test_illegal_transition_leaves_instance_untouched(self):
        """非法拒绝是纯函数失败: 原实例状态/时间不变 (不可变语义)。"""
        inst = _instance(status=WorkflowInstanceStatus.RUNNING)
        before = inst.model_dump()
        with pytest.raises(ValueError):
            transition_instance(inst, WorkflowInstanceStatus.CREATED)
        assert inst.model_dump() == before

    def test_transition_is_immutable_original_unchanged(self):
        """合法转换返回新实例; 原对象保持 CREATED (纯函数)。"""
        inst = _instance()
        inst2 = transition_instance(inst, "running")
        assert inst2.status == WorkflowInstanceStatus.RUNNING
        assert inst.status == WorkflowInstanceStatus.CREATED

    def test_start_time_set_on_running(self):
        """进入 RUNNING 记录 start_time (ISO 字符串, 可审计)。"""
        inst = transition_instance(_instance(), "running")
        assert inst.start_time is not None
        assert isinstance(inst.to_dict()["start_time"], str)

    def test_start_time_preserved_on_terminal(self):
        """终态保留 start_time, 不覆盖 (运行窗口完整)。"""
        inst = transition_instance(_instance(), "running")
        started = inst.start_time
        inst = transition_instance(inst, "success")
        assert inst.start_time == started

    def test_end_time_set_on_terminal(self):
        """进入终态 (SUCCESS/FAILED/CANCELLED) 记录 end_time。"""
        for target in ("success", "failed", "cancelled"):
            inst = _instance()
            if target != "cancelled":
                inst = transition_instance(inst, "running")
            inst = transition_instance(inst, target)
            assert inst.end_time is not None, target


# ------------------------------------------------------------------ ExecutionPlan


class TestExecutionPlan:
    def test_tasks_ordered_list(self):
        """tasks 是有序列表: 按给定顺序保持 (调度顺序 = 执行顺序)。"""
        plan = ExecutionPlan(
            plan_id="P-1",
            tasks=[
                PlanTask(task_id="T-2", agent_hint="dev", order=2),
                PlanTask(task_id="T-1", order=1),
                PlanTask(task_id="T-3"),
            ],
        )
        assert [t.task_id for t in plan.tasks] == ["T-2", "T-1", "T-3"]
        assert plan.tasks[0].agent_hint == "dev"
        assert plan.tasks[0].order == 2
        assert plan.tasks[2].order == 0  # 缺省 order 0

    def test_parallel_batch_and_max_parallel_default(self):
        """parallel_batch 批结构 + max_parallel 缺省 5 (S10-011 §1)。"""
        plan = ExecutionPlan(
            plan_id="P-1",
            tasks=[PlanTask(task_id="T-1")],
            parallel_batch=[["T-1", "T-2"], ["T-3"]],
        )
        assert plan.parallel_batch == [["T-1", "T-2"], ["T-3"]]
        assert plan.max_parallel == 5

    def test_max_parallel_override(self):
        """max_parallel 可覆盖 (workspace/settings 语义)。"""
        plan = ExecutionPlan(plan_id="P-1", max_parallel=3)
        assert plan.max_parallel == 3

    def test_serialization(self):
        """to_dict JSON 友好 (PlanTask 元素展开为 dict)。"""
        plan = ExecutionPlan(
            plan_id="P-1",
            project_id="PRJ-1",
            tasks=[PlanTask(task_id="T-1", agent_hint="dev", order=0)],
            parallel_batch=[["T-1"]],
        )
        d = plan.to_dict()
        assert d["plan_id"] == "P-1"
        assert d["project_id"] == "PRJ-1"
        assert d["tasks"] == [{"task_id": "T-1", "agent_hint": "dev", "order": 0}]
        assert d["parallel_batch"] == [["T-1"]]
        assert d["max_parallel"] == 5


# ------------------------------------------------------------------ ExecutionLock (per-project 互斥)


class TestExecutionLock:
    def test_same_project_mutex_blocks_second_acquirer(self):
        """同项目互斥: 第一持有者未释放 → 第二 acquire 阻塞 (S10-011 §7)。"""
        lock = ExecutionLock()
        lock.acquire("p1")
        acquired = threading.Event()

        def worker():
            lock.acquire("p1")
            acquired.set()
            lock.release("p1")

        t = threading.Thread(target=worker)
        t.start()
        assert not acquired.wait(0.2), "second acquire should block on same project"
        lock.release("p1")
        t.join(timeout=2)
        assert acquired.is_set(), "second acquire should proceed after release"

    def test_release_allows_next_acquirer(self):
        """release 后同项目可被后续获取 (互斥释放语义)。"""
        lock = ExecutionLock()
        lock.acquire("p1")
        lock.release("p1")
        lock.acquire("p1")  # 不阻塞
        lock.release("p1")

    def test_reentrant_same_thread(self):
        """同线程重入安全 (RLock): 同项目嵌套 acquire 不阻塞 (S10-011 §7)。"""
        lock = ExecutionLock()
        lock.acquire("p1")
        lock.acquire("p1")  # 重入不阻塞
        lock.release("p1")
        lock.release("p1")

    def test_different_projects_not_blocked(self):
        """不同项目不互斥: 持有 p1 时 acquire p2 立即成功 (跨项目不阻塞)。"""
        lock = ExecutionLock()
        lock.acquire("p1")
        acquired = threading.Event()

        def worker():
            lock.acquire("p2")
            acquired.set()
            lock.release("p2")

        t = threading.Thread(target=worker)
        t.start()
        assert acquired.wait(1.0), "different project should not block"
        t.join(timeout=2)
        lock.release("p1")

    def test_release_unheld_project_silent(self):
        """未持有锁的 release 静默 (失败安全, 不抛 RuntimeError)。"""
        lock = ExecutionLock()
        lock.release("never-acquired")  # 不抛错

    def test_independent_lock_state_between_projects(self):
        """不同项目锁状态独立: p1 持锁不影响 p2 的获取/释放计数。"""
        lock = ExecutionLock()
        lock.acquire("p1")
        lock.acquire("p2")
        lock.release("p2")
        # p1 仍被持有 → 另一线程阻塞; p2 已释放 → 可重获
        lock.acquire("p2")
        lock.release("p2")
        lock.release("p1")


# ------------------------------------------------------------------ RuntimeStore


class TestRuntimeStore:
    def _store(self, tmp_path: Path) -> RuntimeStore:
        return RuntimeStore(tmp_path / "space")

    def test_task_execution_roundtrip(self, tmp_path):
        """task-execution/{task_id}.json 写入/读取往返 (运行上下文可恢复)。"""
        store = self._store(tmp_path)
        store.save_task_execution("T-1", {"status": "running", "attempt": 1})
        assert store.load_task_execution("T-1") == {"status": "running", "attempt": 1}
        path = tmp_path / "space" / "runtime" / "task-execution" / "T-1.json"
        assert path.is_file()

    def test_agent_execution_roundtrip(self, tmp_path):
        """agent-execution/{instance_id}.json 写入/读取往返。"""
        store = self._store(tmp_path)
        store.save_agent_execution("WI-1", {"agent": "dev", "progress": 0.5})
        assert store.load_agent_execution("WI-1") == {"agent": "dev", "progress": 0.5}
        path = tmp_path / "space" / "runtime" / "agent-execution" / "WI-1.json"
        assert path.is_file()

    def test_workflow_execution_roundtrip(self, tmp_path):
        """workflow-execution/{instance_id}.json 写入/读取往返。"""
        store = self._store(tmp_path)
        store.save_workflow_execution("WI-1", {"stage": 2, "total": 5})
        assert store.load_workflow_execution("WI-1") == {"stage": 2, "total": 5}
        path = tmp_path / "space" / "runtime" / "workflow-execution" / "WI-1.json"
        assert path.is_file()

    def test_three_kinds_isolated(self, tmp_path):
        """三类 JSON 互不串扰 (同名 key 落在各自子目录)。"""
        store = self._store(tmp_path)
        store.save_task_execution("X", {"kind": "task"})
        store.save_agent_execution("X", {"kind": "agent"})
        store.save_workflow_execution("X", {"kind": "workflow"})
        assert store.load_task_execution("X") == {"kind": "task"}
        assert store.load_agent_execution("X") == {"kind": "agent"}
        assert store.load_workflow_execution("X") == {"kind": "workflow"}

    def test_missing_returns_none(self, tmp_path):
        """缺失文件 → None (失败安全, 不抛错)。"""
        store = self._store(tmp_path)
        assert store.load_task_execution("nope") is None
        assert store.load_agent_execution("nope") is None
        assert store.load_workflow_execution("nope") is None

    def test_corrupt_json_returns_none(self, tmp_path):
        """损坏 JSON → None (失败安全 — 运行上下文可重建, 不致命)。"""
        store = self._store(tmp_path)
        path = tmp_path / "space" / "runtime" / "task-execution" / "T-1.json"
        path.parent.mkdir(parents=True)
        path.write_text("{ not json", encoding="utf-8")
        assert store.load_task_execution("T-1") is None

    def test_non_dict_json_returns_none(self, tmp_path):
        """合法 JSON 但非 dict → None (契约: 运行上下文为对象)。"""
        store = self._store(tmp_path)
        path = tmp_path / "space" / "runtime" / "task-execution" / "T-1.json"
        path.parent.mkdir(parents=True)
        path.write_text("[1, 2, 3]", encoding="utf-8")
        assert store.load_task_execution("T-1") is None

    def test_atomic_write_overwrites_cleanly(self, tmp_path):
        """原子写覆盖: 二次写入内容完整替换, 无临时文件残留。"""
        store = self._store(tmp_path)
        store.save_task_execution("T-1", {"status": "running"})
        store.save_task_execution("T-1", {"status": "done"})
        assert store.load_task_execution("T-1") == {"status": "done"}
        runtime = tmp_path / "space" / "runtime"
        leftovers = list(runtime.rglob("*.tmp"))
        assert leftovers == []

    def test_json_content_is_parseable(self, tmp_path):
        """落盘文件为合法 JSON (单行紧凑 + 原子写模式)。"""
        store = self._store(tmp_path)
        store.save_task_execution("T-1", {"status": "running"})
        path = tmp_path / "space" / "runtime" / "task-execution" / "T-1.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"status": "running"}


# ------------------------------------------------------------------ AuditStore


class TestAuditStore:
    def _store(self, tmp_path: Path) -> AuditStore:
        return AuditStore(tmp_path / "space")

    def test_append_records_all_seven_fields(self, tmp_path):
        """append 记录 {time, actor, action, entity, input, output, result} (§6)。"""
        store = self._store(tmp_path)
        store.append(
            actor="dispatcher",
            action="dispatch",
            entity="T-1",
            input={"agent": "dev"},
            output={"instance_id": "WI-1"},
            result="created",
        )
        entries = store.list()
        assert len(entries) == 1
        e = entries[0]
        assert e["actor"] == "dispatcher"
        assert e["action"] == "dispatch"
        assert e["entity"] == "T-1"
        assert e["input"] == {"agent": "dev"}
        assert e["output"] == {"instance_id": "WI-1"}
        assert e["result"] == "created"
        assert isinstance(e["time"], str) and e["time"]  # 审计时间非空

    def test_defaults_for_optional_fields(self, tmp_path):
        """可选字段缺省: input/output None, result 空串。"""
        store = self._store(tmp_path)
        store.append(actor="user", action="cancel", entity="WI-1")
        e = store.list()[0]
        assert e["input"] is None
        assert e["output"] is None
        assert e["result"] == ""

    def test_append_only_never_overwrites(self, tmp_path):
        """追加不可变: 多次 append 顺序保留, 旧条目不丢不覆盖。"""
        store = self._store(tmp_path)
        store.append(actor="a", action="x", entity="e1")
        store.append(actor="b", action="y", entity="e2")
        store.append(actor="c", action="z", entity="e3")
        entries = store.list()
        assert [e["entity"] for e in entries] == ["e1", "e2", "e3"]
        assert [e["actor"] for e in entries] == ["a", "b", "c"]

    def test_append_to_existing_log_preserves_history(self, tmp_path):
        """新建 store 实例 (同一日志文件) 读取既有历史 — 日志是持久不可变事实源。"""
        store = self._store(tmp_path)
        store.append(actor="a", action="x", entity="e1")
        store2 = self._store(tmp_path)
        store2.append(actor="b", action="y", entity="e2")
        entries = store.list()
        assert [e["entity"] for e in entries] == ["e1", "e2"]

    def test_corrupt_line_skipped(self, tmp_path):
        """损坏行跳过 (失败安全): 合法条目仍在, 不整体失败。"""
        store = self._store(tmp_path)
        store.append(actor="a", action="x", entity="e1")
        log = tmp_path / "space" / "logs" / "audit.log"
        log.write_text(log.read_text(encoding="utf-8") + "{ broken json\n", encoding="utf-8")
        entries = store.list()
        assert [e["entity"] for e in entries] == ["e1"]

    def test_missing_log_returns_empty(self, tmp_path):
        """日志不存在 → 空列表 (失败安全)。"""
        store = self._store(tmp_path)
        assert store.list() == []

    def test_log_path_and_single_line_per_entry(self, tmp_path):
        """日志位置 workspace/projects/{slug}/logs/audit.log; 每条一行 JSON。"""
        store = self._store(tmp_path)
        store.append(actor="a", action="x", entity="e1")
        log = tmp_path / "space" / "logs" / "audit.log"
        assert log.is_file()
        lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 1
        assert json.loads(lines[0])["entity"] == "e1"
