"""tests/org/test_org_capability_gate.py — S10-012 Task 007-004: Capability Validation Gate (TDD)。

设计依据 (唯一):
- 用户 Task 拆分 (S10-012-007 Task 004): READY Task 执行前 Capability
  Validation — entity 存在 / enabled / lifecycle ACTIVE / version 可用;
  失败 → Task 状态 BLOCKED + audit 记录 capability_unavailable
- docs/sprint10/S10-012-architecture-design.md §四b (capability_selectable =
  ACTIVE 且 enabled=true 才可选用) + §五 (Dispatcher 集成 Registry)
- Task 007-003 兼容约束: 只对 registry 提供 + binding 可解析场景做 gate;
  registry 缺省 None (纯 legacy) 与 legacy 降级引用 (Registry 无对应 →
  warning + 裸字符串保留) 一律不做 gate — 零破坏 (003 测试已锁行为)

覆盖 (org/execution.py):
- dispatch 层 gate: disabled / 非 ACTIVE / version pin 不匹配 / 无 version
  → DispatchError (reason 含 "capability unavailable" + 具体原因)
- gate 通过: enabled+ACTIVE+version 实体 → CREATED; 无 version 字段实体
  (agent/mcp/llm_config) → version N/A 通过
- legacy 引用 (Registry 无对应) → 不 gate, 仍 CREATED (003 兼容)
- ExecutionEngine 门面: gate 失败 → Task BLOCKED (不创建 instance) +
  audit capability.unavailable (result=BLOCKED) + final_tasks blocked
- registry 缺省 None → 不做 gate (纯 legacy 零破坏 — 003 已覆盖, 此处
  再确认一条)

basename 全仓库唯一 (test_org_capability_gate); 不跨目录依赖 helper。
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
    DispatchError,
    ExecutionEngine,
    WorkflowInstanceStatus,
    dispatch_task,
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


# ------------------------------------------------------------------ dispatch 层 gate (RED: DispatchError)


class TestDispatchGate:
    def test_disabled_skill_rejected(self, registry: CapabilityRegistry):
        """enabled=false → DispatchError (reason 含 not enabled)。"""
        registry.register_skill(make_skill("java", enabled=False))
        with pytest.raises(DispatchError) as exc:
            dispatch_task(
                _task("T-1"),
                bindings={"skills": ["java"]},
                registry=registry,
            )
        assert "capability unavailable" in exc.value.reason
        assert "java" in exc.value.reason
        assert "not enabled" in exc.value.reason

    def test_draft_skill_rejected(self, registry: CapabilityRegistry):
        """state=draft (非 ACTIVE) → DispatchError (reason 含 expected active)。"""
        registry.register_skill(make_skill("java", state="draft"))
        with pytest.raises(DispatchError) as exc:
            dispatch_task(
                _task("T-1"),
                bindings={"skills": ["java"]},
                registry=registry,
            )
        assert "capability unavailable" in exc.value.reason
        assert "java" in exc.value.reason
        assert "active" in exc.value.reason

    def test_version_pin_mismatch_rejected(self, registry: CapabilityRegistry):
        """binding dict pin version 与实体 version 不一致 → DispatchError。"""
        registry.register_skill(make_skill("java", version="1.0.0"))
        with pytest.raises(DispatchError) as exc:
            dispatch_task(
                _task("T-1"),
                bindings={"skills": [{"skill_ref": "java", "version": "9.9.9"}]},
                registry=registry,
            )
        assert "capability unavailable" in exc.value.reason
        assert "9.9.9" in exc.value.reason
        assert "1.0.0" in exc.value.reason

    def test_skill_without_version_rejected(self, registry: CapabilityRegistry):
        """Skill 实体 version 为空 (不可用) → DispatchError。"""
        registry.register_skill(make_skill("java", version=""))
        with pytest.raises(DispatchError) as exc:
            dispatch_task(
                _task("T-1"),
                bindings={"skills": ["java"]},
                registry=registry,
            )
        assert "capability unavailable" in exc.value.reason
        assert "version" in exc.value.reason

    def test_version_pin_on_versionless_entity_rejected(self, registry: CapabilityRegistry):
        """实体无 version 字段 (agent) 但 binding pin 了 version → DispatchError。"""
        registry.register_agent(make_agent("backend-agent"))
        with pytest.raises(DispatchError) as exc:
            dispatch_task(
                _task("T-1"),
                bindings={"agents": [{"agent_ref": "backend-agent", "version": "1.0"}]},
                registry=registry,
            )
        assert "capability unavailable" in exc.value.reason


class TestDispatchGatePass:
    def test_active_enabled_skill_passes(self, registry: CapabilityRegistry):
        """enabled+ACTIVE+version → gate 通过, CREATED。"""
        registry.register_skill(make_skill("java"))
        inst = dispatch_task(
            _task("T-1"),
            bindings={"skills": ["java"]},
            registry=registry,
        )
        assert inst.status == WorkflowInstanceStatus.CREATED
        assert inst.capability_snapshot["skill"] == {"id": "java", "version": "1.0.0"}

    def test_versionless_entity_passes(self, registry: CapabilityRegistry):
        """Agent 无 version 字段 → version N/A, gate 通过。"""
        registry.register_agent(make_agent("backend-agent"))
        inst = dispatch_task(
            _task("T-1"),
            bindings={"agents": ["backend-agent"]},
            registry=registry,
        )
        assert inst.status == WorkflowInstanceStatus.CREATED

    def test_mixed_pass_and_legacy(self, registry: CapabilityRegistry, caplog):
        """解析成功项通过 + legacy 引用不 gate → 仍 CREATED (003 兼容)。"""
        registry.register_skill(make_skill("java"))
        inst = dispatch_task(
            _task("T-1"),
            bindings={"agents": ["ghost-agent"], "skills": ["java"]},
            registry=registry,
        )
        assert inst.status == WorkflowInstanceStatus.CREATED
        assert inst.capability_snapshot["agent"] == "ghost-agent"  # legacy 保留
        assert inst.capability_snapshot["skill"] == {"id": "java", "version": "1.0.0"}

    def test_no_registry_no_gate(self):
        """registry 缺省 None → 不做 gate (纯 legacy 零破坏)。"""
        inst = dispatch_task(
            _task("T-1"),
            bindings={"skills": ["java"]},
        )
        assert inst.status == WorkflowInstanceStatus.CREATED


# ------------------------------------------------------------------ ExecutionEngine 门面: gate 失败 → Task BLOCKED + audit


class TestEngineGateBlocked:
    def test_disabled_skill_blocks_task(self, registry: CapabilityRegistry, tmp_path: Path):
        """gate 失败 → Task BLOCKED, 不创建 instance, 不执行。"""
        registry.register_skill(make_skill("java", enabled=False))
        engine = ExecutionEngine()
        task = _task("T-1")
        result = engine.execute_project_tasks(
            "gate-project",
            [task],
            bindings={"skills": ["java"]},
            registry=registry,
        )
        assert result.instances == []
        assert result.outcomes == []
        assert result.final_tasks["T-1"] == TaskStatus.BLOCKED.value
        # 入参 task 不变 (纯函数风格); 新 task 状态 BLOCKED 由调用方取得
        assert task.status == TaskStatus.READY

    def test_blocked_writes_capability_unavailable_audit(
        self, registry: CapabilityRegistry, tmp_path: Path
    ):
        """audit_store 收到 capability.unavailable 条目 (result=BLOCKED)。"""
        registry.register_skill(make_skill("java", state="draft"))
        audit_store = _make_audit_store(tmp_path)
        engine = ExecutionEngine()
        engine.execute_project_tasks(
            "gate-audit-project",
            [_task("T-1")],
            bindings={"skills": ["java"]},
            audit_store=audit_store,
            registry=registry,
        )
        entries = audit_store.list_audit(action="capability.unavailable")
        assert len(entries) == 1
        entry = entries[0]
        assert entry["actor"] == "dispatcher"
        assert entry["entity"] == "T-1"
        assert entry["result"] == "BLOCKED"
        assert entry["input"]["task_id"] == "T-1"
        assert "java" in entry["input"]["reason"]
        assert entry["output"]["status"] == "blocked"

    def test_gate_pass_engine_no_blocked_audit(
        self, registry: CapabilityRegistry, tmp_path: Path
    ):
        """gate 通过 → 正常执行, 无 capability.unavailable 审计。"""
        registry.register_skill(make_skill("java"))
        registry.register_agent(make_agent("backend-agent"))
        audit_store = _make_audit_store(tmp_path)
        engine = ExecutionEngine()
        result = engine.execute_project_tasks(
            "gate-pass-project",
            [_task("T-1")],
            bindings={"agents": ["backend-agent"], "skills": ["java"]},
            audit_store=audit_store,
            registry=registry,
        )
        assert len(result.outcomes) == 1
        assert result.outcomes[0].instance.status == WorkflowInstanceStatus.SUCCESS
        assert result.final_tasks["T-1"] == TaskStatus.IN_PROGRESS.value  # READY→IN_PROGRESS 联动
        assert audit_store.list_audit(action="capability.unavailable") == []

    def test_legacy_engine_no_gate_no_audit(self, tmp_path: Path):
        """registry 缺省 None → 旧项目裸 binding 正常执行 (零破坏)。"""
        audit_store = _make_audit_store(tmp_path)
        engine = ExecutionEngine()
        result = engine.execute_project_tasks(
            "legacy-gate-project",
            [_task("T-1")],
            bindings={"skills": ["java"]},
            audit_store=audit_store,
        )
        assert len(result.outcomes) == 1
        assert result.outcomes[0].instance.status == WorkflowInstanceStatus.SUCCESS
        assert audit_store.list_audit(action="capability.unavailable") == []


# ------------------------------------------------------------------ helpers


def _make_audit_store(tmp_path: Path):
    """独立项目空间审计 store (space_dir=<tmp>/space/projects/{slug})。"""
    from org.execution import AuditStore

    space = tmp_path / "space" / "projects" / "p1"
    space.mkdir(parents=True, exist_ok=True)
    return AuditStore(space)
