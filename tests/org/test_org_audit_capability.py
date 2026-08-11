"""tests/org/test_org_audit_capability.py — S10-012 Task 007-005: Audit Enhancement (TDD)。

设计依据 (唯一):
- 用户 Task 拆分 (S10-012-007 Task 005): Audit 条目增加 capability 信息
  {agent: {id, version}, skill: {id, version}, llm_config: {id, version}} —
  任何 AI 执行必须能回答: 谁执行? 用什么能力? 哪个版本? 何时? 结果?
- S10-011 §6 (AuditStore: {time, actor, action, entity, input, output,
  result} 单行 JSON 追加不可变) — 本 Task 扩展第 8 字段 capability
- 兼容约束: capability 缺省 None → 老条目不含该字段 (既有 7442 测试
  零破坏 — 字段只增不减, 读取不依赖固定字段集)

覆盖 (org/execution.py):
- AuditStore.append(capability=...) → 落盘条目含 capability 字段
- append 缺省 → 条目无 capability 字段 (老行为零破坏)
- dispatch + registry → instance.dispatched 审计 capability == snapshot
  {agent: {id, version}, skill: {id, version}, ...}
- 纯 legacy (registry None / snapshot {}) → 审计无 capability 字段
- execute_instance 状态转换审计 (instance.transition) 含 capability
- ExecutionEngine 全链路: plan.created 无 capability (计划阶段无实例) +
  instance.dispatched / instance.transition / task.linked 均带 capability

basename 全仓库唯一 (test_org_audit_capability); 不跨目录依赖 helper。
"""

from __future__ import annotations

from pathlib import Path

import pytest

# noqa: E402 — tests/org/conftest.py 已挂 factory-org 到 sys.path (org 包父目录)
from org.capabilities import (  # noqa: E402
    Agent,
    CapabilityRegistry,
    Skill,
)
from org.execution import (  # noqa: E402
    AuditStore,
    ExecutionEngine,
    WorkflowInstanceStatus,
    dispatch_task,
    execute_instance,
)
from org.management import Task, TaskStatus  # noqa: E402


@pytest.fixture
def registry(tmp_path: Path) -> CapabilityRegistry:
    """独立工厂根 (<tmp>/factory → workspace/capabilities/)。"""
    return CapabilityRegistry(tmp_path / "factory")


def make_skill(skill_id: str = "java", *, version: str = "1.0.0", **overrides) -> Skill:
    data = {
        "id": skill_id,
        "name": f"Skill {skill_id}",
        "description": "test skill",
        "category": "software-development",
        "input_schema": {"inputs": [{"name": "task"}]},
        "output_schema": {"outputs": [{"name": "result"}]},
        "version": version,
        "enabled": True,
        "state": "active",
    }
    data.update(overrides)
    return Skill.model_validate(data)


def make_agent(agent_id: str = "backend-agent", **overrides) -> Agent:
    data = {
        "id": agent_id,
        "name": f"Agent {agent_id}",
        "role": "backend",
        "description": "test agent",
        "enabled": True,
        "state": "active",
    }
    data.update(overrides)
    return Agent.model_validate(data)


def _task(task_id: str = "T-1", status: TaskStatus | str = TaskStatus.READY) -> Task:
    return Task(id=task_id, title=f"task {task_id}", status=status)


def _audit_store(tmp_path: Path) -> AuditStore:
    space = tmp_path / "space" / "projects" / "p1"
    space.mkdir(parents=True, exist_ok=True)
    return AuditStore(space)


# ------------------------------------------------------------------ AuditStore.append capability 字段


class TestAuditStoreCapabilityField:
    def test_append_with_capability_persists_field(self, tmp_path: Path):
        """append(capability={...}) → 落盘条目含 capability 字段。"""
        store = _audit_store(tmp_path)
        store.append(
            actor="dispatcher",
            action="instance.dispatched",
            entity="wi-1",
            capability={"agent": {"id": "a1", "version": ""}},
        )
        entries = store.list()
        assert len(entries) == 1
        assert entries[0]["capability"] == {"agent": {"id": "a1", "version": ""}}

    def test_append_without_capability_omits_field(self, tmp_path: Path):
        """append 缺省 capability → 条目无 capability 字段 (老行为零破坏)。"""
        store = _audit_store(tmp_path)
        store.append(actor="scheduler", action="plan.created", entity="plan-1")
        entries = store.list()
        assert len(entries) == 1
        assert "capability" not in entries[0]


# ------------------------------------------------------------------ dispatch 审计 capability


class TestDispatchAuditCapability:
    def test_dispatched_audit_carries_snapshot(self, registry: CapabilityRegistry, tmp_path: Path):
        """dispatch + registry → instance.dispatched 审计 capability == snapshot。"""
        registry.register_agent(make_agent("backend-agent"))
        registry.register_skill(make_skill("java"))
        store = _audit_store(tmp_path)
        inst = dispatch_task(
            _task("T-1"),
            bindings={"agents": ["backend-agent"], "skills": ["java"]},
            audit_store=store,
            registry=registry,
        )
        entries = store.list_audit(action="instance.dispatched")
        assert len(entries) == 1
        assert entries[0]["capability"] == inst.capability_snapshot == {
            "agent": {"id": "backend-agent", "version": ""},
            "skill": {"id": "java", "version": "1.0.0"},
        }

    def test_legacy_no_registry_omits_capability(self, tmp_path: Path):
        """纯 legacy (registry None) → 审计无 capability 字段 (零破坏)。"""
        store = _audit_store(tmp_path)
        dispatch_task(
            _task("T-1"),
            bindings={"agents": ["backend-agent"]},
            audit_store=store,
        )
        entries = store.list_audit(action="instance.dispatched")
        assert len(entries) == 1
        assert "capability" not in entries[0]


# ------------------------------------------------------------------ 执行审计 capability


class TestExecuteAuditCapability:
    def test_transition_audit_carries_snapshot(self, registry: CapabilityRegistry, tmp_path: Path):
        """execute_instance 转换审计 (instance.transition) 含 capability。"""
        registry.register_agent(make_agent("backend-agent"))
        store = _audit_store(tmp_path)
        inst = dispatch_task(
            _task("T-1"),
            bindings={"agents": ["backend-agent"]},
            audit_store=store,
            registry=registry,
        )
        execute_instance(inst, audit_store=store)
        transitions = store.list_audit(action="instance.transition")
        assert len(transitions) == 2  # CREATED→RUNNING + RUNNING→SUCCESS
        for entry in transitions:
            assert entry["capability"] == {"agent": {"id": "backend-agent", "version": ""}}

    def test_legacy_transition_omits_capability(self, tmp_path: Path):
        """纯 legacy 执行转换审计 → 无 capability 字段。"""
        store = _audit_store(tmp_path)
        inst = dispatch_task(_task("T-1"), bindings={"agents": ["backend-agent"]}, audit_store=store)
        execute_instance(inst, audit_store=store)
        transitions = store.list_audit(action="instance.transition")
        assert len(transitions) == 2
        assert all("capability" not in e for e in transitions)


# ------------------------------------------------------------------ ExecutionEngine 全链路


class TestEngineAuditCapability:
    def test_full_chain_capability_fields(
        self, registry: CapabilityRegistry, tmp_path: Path
    ):
        """全链路: plan.created 无 capability; dispatched/transition/task.linked 带。"""
        registry.register_agent(make_agent("backend-agent"))
        registry.register_skill(make_skill("java"))
        store = _audit_store(tmp_path)
        engine = ExecutionEngine()
        engine.execute_project_tasks(
            "audit-chain-project",
            [_task("T-1")],
            bindings={"agents": ["backend-agent"], "skills": ["java"]},
            audit_store=store,
            registry=registry,
        )
        expected = {
            "agent": {"id": "backend-agent", "version": ""},
            "skill": {"id": "java", "version": "1.0.0"},
        }
        # plan.created — 计划阶段无实例能力 → 无 capability 字段
        plans = store.list_audit(action="plan.created")
        assert len(plans) == 1
        assert "capability" not in plans[0]
        # instance.dispatched
        dispatched = store.list_audit(action="instance.dispatched")
        assert len(dispatched) == 1
        assert dispatched[0]["capability"] == expected
        # instance.transition (2 次: →RUNNING, →SUCCESS)
        transitions = store.list_audit(action="instance.transition")
        assert len(transitions) == 2
        assert all(e["capability"] == expected for e in transitions)
        # task.linked
        linked = store.list_audit(action="task.linked")
        assert len(linked) == 1
        assert linked[0]["capability"] == expected
