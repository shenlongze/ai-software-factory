"""tests/org/test_org_legacy_binding.py — S10-012 Task 007-003: Legacy Binding Compatibility (TDD)。

设计依据 (唯一):
- docs/sprint10/S10-012-architecture-design.md §五 (兼容: 旧 binding 裸字符串
  仍可执行 — Registry 无对应 → 保留字符串标注) + §七 验收场景 5 (旧项目
  无 bindings 零破坏)
- 用户 Task 拆分补充 (S10-012-007 Task 003): Registry 存在对应 → resolve
  entity (写入 snapshot); Registry 无对应 → legacy mode 保留裸字符串行为 +
  warning; 禁止破坏既有 7442 测试 (test_dispatcher.py 等大量用裸字符串);
  dispatch_task 增加可选参数 registry (默认 None → 纯 legacy, 零破坏)

覆盖 (org/execution.py):
- 纯 legacy 路径: registry 缺省 None → 裸字符串 binding 原样执行 (snapshot {})
- registry 存在路径: 裸字符串引用 → Registry 实体 → snapshot {id, version}
- registry 缺失路径: Registry 无对应 → snapshot 保留裸字符串 + warning
  (logging.warning — caplog 断言)
- dict 条目 legacy ({agent_ref: ghost}) → 同样降级 + warning
- ExecutionEngine 门面: registry 缺省 None → 旧项目裸 binding 全流程执行
  (零破坏); registry 提供 → instances 带 snapshot

basename 全仓库唯一 (test_org_legacy_binding); 不跨目录依赖 helper。
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

# noqa: E402 — tests/org/conftest.py 已挂 factory-org 到 sys.path (org 包父目录)
from org.capabilities import (  # noqa: E402
    Agent,
    CapabilityRegistry,
    Skill,
)
from org.execution import (  # noqa: E402
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


# ------------------------------------------------------------------ 纯 legacy 路径 (registry 缺省 None)


class TestLegacyNoRegistry:
    def test_bare_string_bindings_execute(self):
        """旧项目裸字符串 binding → 原样执行 (与 S10-011 行为一致)。"""
        bindings = {"agents": ["backend-agent"], "skills": ["java"], "mcps": ["m1"]}
        inst = dispatch_task(_task("T-1"), bindings=bindings)
        assert inst.status == WorkflowInstanceStatus.CREATED
        assert inst.agent == "backend-agent"
        assert inst.skill == "java"
        assert inst.mcp == "m1"
        assert inst.capability_snapshot == {}  # 无 registry → 无快照 (纯 legacy)

    def test_no_bindings_executes(self):
        """旧项目无 bindings → 仍可执行 (验收场景 5: 零破坏)。"""
        inst = dispatch_task(_task("T-1"))
        assert inst.status == WorkflowInstanceStatus.CREATED
        assert inst.agent == "" and inst.skill == "" and inst.mcp == ""

    def test_dict_entries_legacy_without_registry(self):
        """dict 条目 (旧格式 {agent_ref: ...}) 无 registry → 引用串提取原样。"""
        bindings = {"agents": [{"agent_ref": "PM-Agent-v2", "role": "pm"}]}
        inst = dispatch_task(_task("T-1"), bindings=bindings)
        assert inst.agent == "PM-Agent-v2"
        assert inst.capability_snapshot == {}


# ------------------------------------------------------------------ registry 存在路径


class TestLegacyRegistryPresent:
    def test_string_refs_resolve_to_entities(self, registry: CapabilityRegistry):
        """registry 提供 + 实体存在 → 裸字符串引用解析为实体 (snapshot 写入)。"""
        registry.register_agent(make_agent("backend-agent"))
        registry.register_skill(make_skill("java"))
        bindings = {"agents": ["backend-agent"], "skills": ["java"]}
        inst = dispatch_task(_task("T-1"), bindings=bindings, registry=registry)
        assert inst.agent == "backend-agent"
        assert inst.skill == "java"
        assert inst.capability_snapshot == {
            "agent": {"id": "backend-agent", "version": ""},
            "skill": {"id": "java", "version": "1.0.0"},
        }

    def test_dict_entries_resolve_with_registry(self, registry: CapabilityRegistry):
        """dict 条目 + registry → 解析为实体 (ref_key 提取 + 实体写入)。"""
        registry.register_agent(make_agent("backend-agent"))
        inst = dispatch_task(
            _task("T-1"),
            bindings={"agents": [{"agent_ref": "backend-agent", "role": "backend"}]},
            registry=registry,
        )
        assert inst.capability_snapshot["agent"] == {"id": "backend-agent", "version": ""}


# ------------------------------------------------------------------ registry 缺失路径 (legacy 降级 + warning)


class TestLegacyRegistryMissing:
    def test_missing_ref_legacy_preserved_with_warning(self, registry: CapabilityRegistry, caplog):
        """Registry 无对应 → legacy: snapshot 保留裸字符串 + warning。"""
        registry.register_skill(make_skill("java"))
        bindings = {"agents": ["ghost-agent"], "skills": ["java"]}
        with caplog.at_level(logging.WARNING, logger="org.execution"):
            inst = dispatch_task(_task("T-1"), bindings=bindings, registry=registry)
        assert inst.capability_snapshot["agent"] == "ghost-agent"  # 裸字符串保留
        assert inst.capability_snapshot["skill"] == {"id": "java", "version": "1.0.0"}
        assert any("legacy mode" in r.message and "ghost-agent" in r.message for r in caplog.records)
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_missing_dict_entry_legacy_with_warning(self, registry: CapabilityRegistry, caplog):
        """dict 条目引用缺失 → 同样 legacy 降级 + warning。"""
        with caplog.at_level(logging.WARNING, logger="org.execution"):
            inst = dispatch_task(
                _task("T-1"),
                bindings={"agents": [{"agent_ref": "ghost-agent", "role": "pm"}]},
                registry=registry,
            )
        assert inst.capability_snapshot["agent"] == "ghost-agent"
        assert inst.status == WorkflowInstanceStatus.CREATED  # 不崩溃, 可执行
        assert any("ghost-agent" in r.message for r in caplog.records)

    def test_all_refs_missing_still_executes(self, registry: CapabilityRegistry, caplog):
        """全部引用缺失 → 实例仍 CREATED (legacy 可执行, 仅 warning)。"""
        bindings = {"agents": ["ghost"], "skills": ["ghost-skill"], "mcps": ["ghost-mcp"]}
        with caplog.at_level(logging.WARNING, logger="org.execution"):
            inst = dispatch_task(_task("T-1"), bindings=bindings, registry=registry)
        assert inst.status == WorkflowInstanceStatus.CREATED
        assert inst.capability_snapshot == {
            "agent": "ghost", "skill": "ghost-skill", "mcp": "ghost-mcp",
        }
        assert len([r for r in caplog.records if "legacy mode" in r.message]) == 3


# ------------------------------------------------------------------ ExecutionEngine 门面兼容


class TestLegacyEngine:
    def test_engine_without_registry_legacy_flow(self, tmp_path: Path):
        """门面 registry 缺省 None → 旧项目裸 binding 全流程执行 (零破坏)。"""
        engine = ExecutionEngine()
        tasks = [_task("T-1"), _task("T-2")]
        result = engine.execute_project_tasks(
            "legacy-project",
            tasks,
            bindings={"agents": ["backend-agent"], "skills": ["java"]},
        )
        assert len(result.instances) == 2
        assert len(result.outcomes) == 2
        for outcome in result.outcomes:
            assert outcome.instance.status == WorkflowInstanceStatus.SUCCESS
            assert outcome.instance.capability_snapshot == {}  # 纯 legacy
        assert result.final_tasks["T-1"] == "in_progress"  # READY→IN_PROGRESS 联动

    def test_engine_with_registry_resolves(self, registry: CapabilityRegistry, tmp_path: Path):
        """门面 registry 提供 → 实例带 snapshot (实体解析)。"""
        registry.register_agent(make_agent("backend-agent"))
        registry.register_skill(make_skill("java"))
        engine = ExecutionEngine()
        result = engine.execute_project_tasks(
            "modern-project",
            [_task("T-1")],
            bindings={"agents": ["backend-agent"], "skills": ["java"]},
            registry=registry,
        )
        assert len(result.instances) == 1
        assert len(result.outcomes) == 1
        inst = result.outcomes[0].instance
        assert inst.status == WorkflowInstanceStatus.SUCCESS
        assert inst.capability_snapshot["agent"] == {"id": "backend-agent", "version": ""}
        assert inst.capability_snapshot["skill"] == {"id": "java", "version": "1.0.0"}
