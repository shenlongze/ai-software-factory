"""tests/org/test_dispatcher.py — S10-011 Task 003: Dispatcher (TDD)。

设计依据 (唯一): docs/sprint10/S10-011-architecture-design.md §二 2/3/4
(Dispatcher 架构 + binding + Workflow Instance 生命周期) + §五 验收场景 2/3
+ AF-PRD-v1.md 4.8 (Workflow Execution — project binding workflow_ref):

- dispatch_task(task, bindings, all_tasks, workflow_id) 纯函数:
  1. can_execute 校验: 依赖未满足 → DispatchError (reason: Waiting dependency);
     BLOCKED/非 READY → DispatchError (拒绝)
  2. 创建 WorkflowInstance: status=CREATED, task_id, workflow_id
     (bindings.workflow.workflow_ref 优先, 缺省参数默认 software-development-v1),
     agent/skill/mcp 从 bindings 选择 (取列表第一个; 空 → 空串)
  3. instance_id 唯一
- bindings 为空 → agent/skill/mcp 空, 仍可执行 (CREATED, 无绑定标注)
- WorkflowInstance 持久化: workflow-instance/{instance_id}.json 目录信源
  (设计 §4: workspace/projects/{slug}/workflow-instance/) — save_instance/
  load_instance (失败安全: 缺失/损坏 → None) + list_instances
- 状态机集成: 创建后 CREATED; transition (RUNNING/SUCCESS/FAILED/CANCELLED)
  受控 (复用 transition_instance); 持久化实例可继续流转

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
    DispatchError,
    WorkflowInstance,
    WorkflowInstanceStatus,
    WorkflowInstanceStore,
    dispatch_task,
    transition_instance,
)
from org.management import Task, TaskPriority, TaskStatus  # noqa: E402


def _task(
    task_id: str,
    *,
    priority: TaskPriority | str = TaskPriority.P2,
    status: TaskStatus | str = TaskStatus.READY,
    dependency: list[str] | None = None,
    assignee: str = "",
) -> Task:
    """最小 Task 构造 (id 必填, 其余默认; status 默认 READY 便于分发测试)。"""
    return Task(
        id=task_id,
        title=f"task {task_id}",
        priority=priority,
        status=status,
        dependency=list(dependency or []),
        assignee=assignee,
    )


def _instance(instance_id: str = "WI-1", task_id: str = "T-1", **kw) -> WorkflowInstance:
    """最小 WorkflowInstance 构造 (instance_id/task_id 可覆盖, 其余默认)。"""
    return WorkflowInstance(instance_id=instance_id, task_id=task_id, **kw)


# ------------------------------------------------------------------ can_execute 校验


class TestDispatchCanExecute:
    def test_ready_no_dependency_dispatched(self):
        """READY 且无依赖 → 分发成功: instance CREATED + task_id 绑定。"""
        inst = dispatch_task(_task("T-1"))
        assert isinstance(inst, WorkflowInstance)
        assert inst.status == WorkflowInstanceStatus.CREATED
        assert inst.task_id == "T-1"

    def test_ready_dependency_done_dispatched(self):
        """READY 且依赖全部 DONE → 分发成功。"""
        done = _task("T-dep", status=TaskStatus.DONE)
        ready = _task("T-1", dependency=["T-dep"])
        inst = dispatch_task(ready, all_tasks=[done, ready])
        assert inst.status == WorkflowInstanceStatus.CREATED
        assert inst.task_id == "T-1"

    def test_dependency_unsatisfied_raises(self):
        """依赖未满足 → DispatchError (reason: Waiting dependency) (验收场景 2)。"""
        dep = _task("T-dep", status=TaskStatus.IN_PROGRESS)
        ready = _task("T-1", dependency=["T-dep"])
        with pytest.raises(DispatchError) as ei:
            dispatch_task(ready, all_tasks=[dep, ready])
        assert ei.value.reason == "Waiting dependency Task T-dep"

    def test_missing_dependency_task_raises(self):
        """依赖任务不在列表 (未知 id) → DispatchError (原因含依赖 id)。"""
        ready = _task("T-1", dependency=["T-ghost"])
        with pytest.raises(DispatchError) as ei:
            dispatch_task(ready, all_tasks=[ready])
        assert "T-ghost" in ei.value.reason

    def test_blocked_rejected(self):
        """BLOCKED → DispatchError 拒绝 (BLOCKED 不执行 — 验收场景 3)。"""
        with pytest.raises(DispatchError) as ei:
            dispatch_task(_task("T-1", status=TaskStatus.BLOCKED))
        assert "blocked" in ei.value.reason

    def test_non_ready_rejected(self):
        """非 READY (TODO/IN_PROGRESS/REVIEW/DONE) → DispatchError 拒绝。"""
        for status in (
            TaskStatus.TODO,
            TaskStatus.IN_PROGRESS,
            TaskStatus.REVIEW,
            TaskStatus.DONE,
        ):
            with pytest.raises(DispatchError):
                dispatch_task(_task("T-1", status=status))


# ------------------------------------------------------------------ binding 选择


class TestDispatchBindings:
    def test_bindings_select_agent_skill_mcp(self):
        """bindings 选择: agent/skill/mcp 取列表第一个引用 (设计 §2/§3)。"""
        bindings = {
            "agents": ["dev-agent"],
            "skills": ["flutter-development"],
            "mcps": ["filesystem"],
            "workflow": {"workflow_ref": "software-development-v1"},
        }
        inst = dispatch_task(_task("T-1"), bindings=bindings)
        assert inst.agent == "dev-agent"
        assert inst.skill == "flutter-development"
        assert inst.mcp == "filesystem"
        assert inst.workflow_id == "software-development-v1"

    def test_bindings_agent_dict_entry_ref_extracted(self):
        """agents 条目为 dict ({agent_ref, role} — project-lifecycle.md) → 取 agent_ref。"""
        bindings = {"agents": [{"agent_ref": "PM-Agent-v2", "role": "pm"}]}
        inst = dispatch_task(_task("T-1"), bindings=bindings)
        assert inst.agent == "PM-Agent-v2"

    def test_first_binding_wins(self):
        """取第一个匹配: agents 多条目 → 第一个。"""
        bindings = {"agents": ["a1", "a2"], "skills": ["s1", "s2"], "mcps": ["m1", "m2"]}
        inst = dispatch_task(_task("T-1"), bindings=bindings)
        assert inst.agent == "a1"
        assert inst.skill == "s1"
        assert inst.mcp == "m1"

    def test_partial_bindings_fill_missing_empty(self):
        """部分绑定: 只配 agents → skill/mcp 空串。"""
        inst = dispatch_task(_task("T-1"), bindings={"agents": ["dev"]})
        assert inst.agent == "dev"
        assert inst.skill == ""
        assert inst.mcp == ""

    def test_workflow_id_from_bindings_overrides_default(self):
        """workflow 绑定 workflow_ref → workflow_id (PRD 4.8 覆盖默认)。"""
        inst = dispatch_task(
            _task("T-1"), bindings={"workflow": {"workflow_ref": "custom-wf-v2"}}
        )
        assert inst.workflow_id == "custom-wf-v2"

    def test_workflow_instance_key_compat(self):
        """兼容 PRD 4.8 workflow_instance 键 (workflow_ref) — 设计文档形式。"""
        inst = dispatch_task(
            _task("T-1"),
            bindings={"workflow_instance": {"workflow_ref": "software-development-v1"}},
        )
        assert inst.workflow_id == "software-development-v1"

    def test_workflow_id_param_override(self):
        """workflow_id 参数显式指定 (bindings 无 workflow) → 参数生效。"""
        inst = dispatch_task(_task("T-1"), workflow_id="wf-x")
        assert inst.workflow_id == "wf-x"

    def test_workflow_id_default(self):
        """无绑定无参数 → 默认 software-development-v1 (PRD 4.8 公共资源默认)。"""
        inst = dispatch_task(_task("T-1"))
        assert inst.workflow_id == "software-development-v1"

    def test_empty_bindings_executable(self):
        """bindings 为空 → agent/skill/mcp 空, 仍可执行 (CREATED, 无绑定标注)。"""
        inst = dispatch_task(_task("T-1"), bindings={})
        assert inst.status == WorkflowInstanceStatus.CREATED
        assert inst.agent == ""
        assert inst.skill == ""
        assert inst.mcp == ""

    def test_none_bindings_executable(self):
        """bindings=None (缺省) → 同空绑定: 可执行, 无绑定字段空。"""
        inst = dispatch_task(_task("T-1"))
        assert inst.status == WorkflowInstanceStatus.CREATED
        assert inst.agent == "" and inst.skill == "" and inst.mcp == ""


# ------------------------------------------------------------------ instance_id 唯一


class TestDispatchInstanceId:
    def test_instance_id_unique_per_dispatch(self):
        """每次分发 instance_id 唯一 (多次调用互不相同)。"""
        ids = {dispatch_task(_task(f"T-{i}")).instance_id for i in range(10)}
        assert len(ids) == 10
        assert all(iid for iid in ids)  # 非空

    def test_instance_id_is_string(self):
        """instance_id 为非空字符串 (实例唯一标识)。"""
        inst = dispatch_task(_task("T-1"))
        assert isinstance(inst.instance_id, str) and inst.instance_id


# ------------------------------------------------------------------ 纯函数


class TestDispatchPure:
    def test_no_input_mutation(self):
        """纯函数: 不改入参 (task 字段与 bindings 字典分发后不变)。"""
        task = _task("T-1")
        bindings = {"agents": ["dev"], "skills": ["s1"]}
        snapshot_task = task.model_dump()
        snapshot_bindings = dict(bindings)
        dispatch_task(task, bindings=bindings)
        assert task.model_dump() == snapshot_task
        assert bindings == snapshot_bindings


# ------------------------------------------------------------------ WorkflowInstanceStore (workflow-instance/ 目录信源)


class TestWorkflowInstanceStore:
    def _store(self, tmp_path: Path) -> WorkflowInstanceStore:
        return WorkflowInstanceStore(tmp_path / "space")

    def test_save_load_roundtrip(self, tmp_path):
        """save_instance → workflow-instance/{id}.json; load_instance 全字段往返。"""
        store = self._store(tmp_path)
        inst = _instance(agent="dev", skill="s1", mcp="m1")
        store.save_instance(inst)
        path = tmp_path / "space" / "workflow-instance" / "WI-1.json"
        assert path.is_file()
        loaded = store.load_instance("WI-1")
        assert isinstance(loaded, WorkflowInstance)
        assert loaded.to_dict() == inst.to_dict()

    def test_save_dispatched_instance_roundtrip(self, tmp_path):
        """分发产物可直接持久化: CREATED 状态 + binding 字段往返 (设计 §4 信源)。"""
        store = self._store(tmp_path)
        inst = dispatch_task(_task("T-1"), bindings={"agents": ["dev"]})
        store.save_instance(inst)
        loaded = store.load_instance(inst.instance_id)
        assert loaded is not None
        assert loaded.instance_id == inst.instance_id
        assert loaded.status == WorkflowInstanceStatus.CREATED
        assert loaded.agent == "dev"
        assert loaded.workflow_id == "software-development-v1"

    def test_load_missing_returns_none(self, tmp_path):
        """缺失文件 → None (失败安全)。"""
        store = self._store(tmp_path)
        assert store.load_instance("nope") is None

    def test_load_corrupt_json_returns_none(self, tmp_path):
        """损坏 JSON → None (失败安全, 信源可重建不致命)。"""
        store = self._store(tmp_path)
        path = tmp_path / "space" / "workflow-instance" / "WI-1.json"
        path.parent.mkdir(parents=True)
        path.write_text("{ not json", encoding="utf-8")
        assert store.load_instance("WI-1") is None

    def test_save_overwrites_atomically(self, tmp_path):
        """原子写覆盖: 二次保存完整替换, 无临时文件残留。"""
        store = self._store(tmp_path)
        store.save_instance(_instance(status=WorkflowInstanceStatus.CREATED))
        running = transition_instance(_instance(), "running")
        store.save_instance(running)
        loaded = store.load_instance("WI-1")
        assert loaded is not None
        assert loaded.status == WorkflowInstanceStatus.RUNNING
        leftovers = list((tmp_path / "space" / "workflow-instance").rglob("*.tmp"))
        assert leftovers == []

    def test_list_instances_sorted(self, tmp_path):
        """list_instances: 目录信源枚举 (按 instance_id 排序)。"""
        store = self._store(tmp_path)
        store.save_instance(_instance(instance_id="WI-2", task_id="T-2"))
        store.save_instance(_instance(instance_id="WI-1", task_id="T-1"))
        store.save_instance(_instance(instance_id="WI-3", task_id="T-3"))
        ids = [i.instance_id for i in store.list_instances()]
        assert ids == ["WI-1", "WI-2", "WI-3"]

    def test_list_instances_empty_dir(self, tmp_path):
        """目录不存在/空 → 空列表 (失败安全)。"""
        store = self._store(tmp_path)
        assert store.list_instances() == []


# ------------------------------------------------------------------ 状态机集成


class TestStateMachineIntegration:
    def _store(self, tmp_path: Path) -> WorkflowInstanceStore:
        return WorkflowInstanceStore(tmp_path / "space")

    def test_dispatch_created_then_full_lifecycle(self):
        """创建后 CREATED; 主路径 CREATED→RUNNING→SUCCESS 受控流转。"""
        inst = dispatch_task(_task("T-1"))
        assert inst.status == WorkflowInstanceStatus.CREATED
        inst = transition_instance(inst, "running")
        assert inst.status == WorkflowInstanceStatus.RUNNING
        inst = transition_instance(inst, "success")
        assert inst.status == WorkflowInstanceStatus.SUCCESS
        assert inst.end_time is not None

    def test_dispatch_created_cancelled(self):
        """创建后未启动即取消: CREATED→CANCELLED 合法。"""
        inst = dispatch_task(_task("T-1"))
        inst = transition_instance(inst, "cancelled")
        assert inst.status == WorkflowInstanceStatus.CANCELLED

    def test_dispatch_failed_path(self):
        """失败路径: CREATED→RUNNING→FAILED (result 记录)。"""
        inst = transition_instance(dispatch_task(_task("T-1")), "running")
        inst = transition_instance(inst, "failed", result="executor error")
        assert inst.status == WorkflowInstanceStatus.FAILED
        assert inst.result == "executor error"

    def test_persisted_lifecycle_across_save_load(self, tmp_path):
        """持久化实例可继续流转: save CREATED → load → RUNNING → save → load (状态保持)。"""
        store = self._store(tmp_path)
        inst = dispatch_task(_task("T-1"), bindings={"agents": ["dev"]})
        store.save_instance(inst)
        loaded = store.load_instance(inst.instance_id)
        assert loaded is not None
        assert loaded.status == WorkflowInstanceStatus.CREATED
        assert loaded.agent == "dev"
        running = transition_instance(loaded, "running")
        store.save_instance(running)
        reloaded = store.load_instance(inst.instance_id)
        assert reloaded is not None
        assert reloaded.status == WorkflowInstanceStatus.RUNNING
        assert reloaded.start_time is not None

    def test_illegal_transition_after_load_rejected(self, tmp_path):
        """持久化实例状态机仍受控: 加载后非法转换 (CREATED→SUCCESS 跳级) → ValueError。"""
        store = self._store(tmp_path)
        inst = dispatch_task(_task("T-1"))
        store.save_instance(inst)
        loaded = store.load_instance(inst.instance_id)
        assert loaded is not None
        with pytest.raises(ValueError):
            transition_instance(loaded, "success")
