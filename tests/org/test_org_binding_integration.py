"""tests/org/test_org_binding_integration.py — S10-012 Task 007-006: Integration Test (TDD 验收)。

设计依据 (唯一):
- 用户 Task 拆分 (S10-012-007 Task 006): 4 场景全链验收 —
  1. Registry Agent+Skill+LLM → Dispatcher resolve → WorkflowInstance
     snapshot → Runtime success
  2. Capability 不可用 → BLOCKED
  3. 旧项目裸 binding → 正常执行 (零破坏)
  4. Capability version upgrade → 历史 instance 保持旧 version
- docs/sprint10/S10-012-architecture-design.md §七 (验收场景 1/3/5)
- Task 007-003/004/005 已锁行为 (legacy 降级 / gate 语义 / audit capability)

说明 (设计约束, 非遗漏):
- 场景 2 "Capability 不存在": 003 兼容约束下, registry 提供 + 引用
  Registry 无对应 (ghost) → legacy 降级 CREATED (003 测试已锁); 因此
  场景 2 覆盖 gate 语义的 "不可用" = 解析成功但 disabled / 非 ACTIVE →
  Task BLOCKED + audit capability_unavailable (004 验收)。ghost 引用的
  legacy 行为见 test_org_legacy_binding.py。

basename 全仓库唯一 (test_org_binding_integration); 不跨目录依赖 helper。
"""

from __future__ import annotations

from pathlib import Path

import pytest

# noqa: E402 — tests/org/conftest.py 已挂 factory-org 到 sys.path (org 包父目录)
from org.capabilities import (  # noqa: E402
    Agent,
    CapabilityRegistry,
    LLMConfig,
    Skill,
)
from org.execution import (  # noqa: E402
    AuditStore,
    ExecutionEngine,
    RuntimeStore,
    WorkflowInstanceStatus,
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


def make_llm(llm_id: str = "deepseek-default", **overrides) -> LLMConfig:
    data = {
        "id": llm_id,
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "endpoint": "",
        "parameters": {},
        "enabled": True,
        "state": "active",
    }
    data.update(overrides)
    return LLMConfig.model_validate(data)


def _task(task_id: str = "T-1", status: TaskStatus | str = TaskStatus.READY) -> Task:
    return Task(id=task_id, title=f"task {task_id}", status=status)


def _stores(tmp_path: Path) -> tuple[AuditStore, RuntimeStore]:
    """独立项目空间 audit + runtime store (space_dir=<tmp>/space/projects/p1)。"""
    space = tmp_path / "space" / "projects" / "p1"
    space.mkdir(parents=True, exist_ok=True)
    return AuditStore(space), RuntimeStore(space)


# ------------------------------------------------------------------ Scenario 1: 全链 Registry → snapshot → Runtime success


class TestScenario1FullChain:
    def test_agent_skill_llm_full_chain(
        self, registry: CapabilityRegistry, tmp_path: Path
    ):
        """Registry Agent+Skill+LLM → resolve → snapshot → runtime success。"""
        registry.register_agent(make_agent("backend-agent"))
        registry.register_skill(make_skill("java", version="1.0.0"))
        registry.register_llm_config(make_llm("deepseek-default"))
        audit_store, runtime_store = _stores(tmp_path)
        engine = ExecutionEngine()

        result = engine.execute_project_tasks(
            "scenario-1-project",
            [_task("T-1"), _task("T-2")],
            bindings={
                "agents": ["backend-agent"],
                "skills": ["java"],
                "llm_configs": ["deepseek-default"],
            },
            audit_store=audit_store,
            runtime_store=runtime_store,
            registry=registry,
        )

        # Dispatcher resolve → WorkflowInstance snapshot (三能力全量)
        assert len(result.instances) == 2
        expected_snapshot = {
            "agent": {"id": "backend-agent", "version": ""},  # Agent 无 version 字段
            "skill": {"id": "java", "version": "1.0.0"},
            "llm": {"id": "deepseek-default", "version": ""},  # LLMConfig 无 version 字段
        }
        for inst in result.instances:
            assert inst.capability_snapshot == expected_snapshot
        # Runtime success
        assert len(result.outcomes) == 2
        assert all(o.instance.status == WorkflowInstanceStatus.SUCCESS for o in result.outcomes)
        assert all(o.instance.start_time is not None and o.instance.end_time is not None
                   for o in result.outcomes)
        assert all(o.instance.result.startswith("executed by backend-agent")
                   for o in result.outcomes)
        # Task 联动
        assert result.final_tasks["T-1"] == TaskStatus.IN_PROGRESS.value
        # Runtime 落盘 (workflow-execution 快照可恢复)
        for inst in result.instances:
            saved = runtime_store.load_workflow_execution(inst.instance_id)
            assert saved is not None and saved["status"] == "success"
        # Audit capability 全链
        dispatched = audit_store.list_audit(action="instance.dispatched")
        assert len(dispatched) == 2
        assert all(e["capability"] == expected_snapshot for e in dispatched)


# ------------------------------------------------------------------ Scenario 2: Capability 不可用 → BLOCKED


class TestScenario2CapabilityUnavailable:
    def test_disabled_capability_blocks_task(
        self, registry: CapabilityRegistry, tmp_path: Path
    ):
        """解析成功但 disabled → Task BLOCKED + audit capability_unavailable。"""
        registry.register_agent(make_agent("backend-agent"))
        registry.register_skill(make_skill("java", enabled=False))
        audit_store, _ = _stores(tmp_path)
        engine = ExecutionEngine()

        result = engine.execute_project_tasks(
            "scenario-2-project",
            [_task("T-1"), _task("T-2")],
            bindings={"agents": ["backend-agent"], "skills": ["java"]},
            audit_store=audit_store,
            registry=registry,
        )

        assert result.instances == []  # gate 失败 → 不创建 instance
        assert result.outcomes == []
        assert result.final_tasks == {"T-1": "blocked", "T-2": "blocked"}
        blocked_audits = audit_store.list_audit(action="capability.unavailable")
        assert len(blocked_audits) == 2
        assert all(e["result"] == "BLOCKED" for e in blocked_audits)
        assert all("java" in e["input"]["reason"] for e in blocked_audits)

    def test_draft_capability_blocks_task(self, registry: CapabilityRegistry, tmp_path: Path):
        """非 ACTIVE (draft) → Task BLOCKED (生命周期门)。"""
        registry.register_skill(make_skill("java", state="draft"))
        audit_store, _ = _stores(tmp_path)
        engine = ExecutionEngine()
        result = engine.execute_project_tasks(
            "scenario-2b-project",
            [_task("T-1")],
            bindings={"skills": ["java"]},
            audit_store=audit_store,
            registry=registry,
        )
        assert result.instances == []
        assert result.final_tasks["T-1"] == "blocked"
        assert len(audit_store.list_audit(action="capability.unavailable")) == 1


# ------------------------------------------------------------------ Scenario 3: 旧项目裸 binding 零破坏


class TestScenario3LegacyProject:
    def test_bare_string_bindings_execute(self, tmp_path: Path):
        """旧项目裸 binding (无 registry) → 正常执行, snapshot {} (零破坏)。"""
        audit_store, runtime_store = _stores(tmp_path)
        engine = ExecutionEngine()
        result = engine.execute_project_tasks(
            "legacy-project",
            [_task("T-1")],
            bindings={"agents": ["backend-agent"], "skills": ["java"]},
            audit_store=audit_store,
            runtime_store=runtime_store,
        )
        assert len(result.outcomes) == 1
        inst = result.outcomes[0].instance
        assert inst.status == WorkflowInstanceStatus.SUCCESS
        assert inst.capability_snapshot == {}  # 纯 legacy: 无快照
        assert result.final_tasks["T-1"] == TaskStatus.IN_PROGRESS.value
        # 审计照常 (无 capability 字段 — 005 兼容)
        dispatched = audit_store.list_audit(action="instance.dispatched")
        assert len(dispatched) == 1
        assert "capability" not in dispatched[0]

    def test_no_bindings_execute(self, tmp_path: Path):
        """旧项目无 bindings → 仍可执行 (验收场景 5: 零破坏)。"""
        engine = ExecutionEngine()
        result = engine.execute_project_tasks("legacy-empty-project", [_task("T-1")])
        assert len(result.outcomes) == 1
        assert result.outcomes[0].instance.status == WorkflowInstanceStatus.SUCCESS


# ------------------------------------------------------------------ Scenario 4: version upgrade → 历史 instance 保持旧 version


class TestScenario4VersionUpgrade:
    def test_historical_instance_keeps_old_version(
        self, registry: CapabilityRegistry, tmp_path: Path
    ):
        """能力升级 → 新 instance 新 version, 历史 instance 快照保持旧 version。"""
        registry.register_skill(make_skill("java", version="1.0.0"))
        engine = ExecutionEngine()

        # 第一次执行 (v1.0.0)
        r1 = engine.execute_project_tasks(
            "scenario-4-project",
            [_task("T-1")],
            bindings={"skills": ["java"]},
            registry=registry,
        )
        hist = r1.outcomes[0].instance
        assert hist.status == WorkflowInstanceStatus.SUCCESS
        assert hist.capability_snapshot["skill"] == {"id": "java", "version": "1.0.0"}

        # Registry 升级 v2.0.0
        upgraded = registry.update_skill("java", {"version": "2.0.0"})
        assert upgraded is not None and upgraded.version == "2.0.0"

        # 第二次执行 (v2.0.0)
        r2 = engine.execute_project_tasks(
            "scenario-4-project",
            [_task("T-2")],
            bindings={"skills": ["java"]},
            registry=registry,
        )
        fresh = r2.outcomes[0].instance
        assert fresh.capability_snapshot["skill"] == {"id": "java", "version": "2.0.0"}

        # 历史 instance 保持 v1.0.0 (快照固化 — 可复现, 不受 Registry 升级影响)
        assert hist.capability_snapshot["skill"] == {"id": "java", "version": "1.0.0"}
        assert hist.capability_snapshot != fresh.capability_snapshot

    def test_version_pin_binding_historical_reproducible(
        self, registry: CapabilityRegistry, tmp_path: Path
    ):
        """binding pin 旧 version → 升级后 pin 仍解析旧版 (可复现); 反例失败。"""
        registry.register_skill(make_skill("java", version="1.0.0"))
        engine = ExecutionEngine()

        r1 = engine.execute_project_tasks(
            "scenario-4b-project",
            [_task("T-1")],
            bindings={"skills": [{"skill_ref": "java", "version": "1.0.0"}]},
            registry=registry,
        )
        assert r1.outcomes[0].instance.capability_snapshot["skill"] == {
            "id": "java", "version": "1.0.0",
        }
        # 升级到 2.0.0
        registry.update_skill("java", {"version": "2.0.0"})
        # pin 2.0.0 → 新 instance 用新版
        r2 = engine.execute_project_tasks(
            "scenario-4b-project",
            [_task("T-2")],
            bindings={"skills": [{"skill_ref": "java", "version": "2.0.0"}]},
            registry=registry,
        )
        assert r2.outcomes[0].instance.capability_snapshot["skill"] == {
            "id": "java", "version": "2.0.0",
        }
        # pin 1.0.0 但实体已升级 → gate 拒绝 (BLOCKED — 004 语义: pin 不可满足)
        audit_store, _ = _stores(tmp_path)
        r3 = engine.execute_project_tasks(
            "scenario-4b-project",
            [_task("T-3")],
            bindings={"skills": [{"skill_ref": "java", "version": "1.0.0"}]},
            audit_store=audit_store,
            registry=registry,
        )
        assert r3.instances == []
        assert r3.final_tasks["T-3"] == "blocked"
        assert len(audit_store.list_audit(action="capability.unavailable")) == 1
