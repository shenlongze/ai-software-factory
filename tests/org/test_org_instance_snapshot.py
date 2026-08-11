"""tests/org/test_org_instance_snapshot.py — S10-012 Task 007-002: WorkflowInstance Capability Snapshot (TDD)。

设计依据 (唯一):
- docs/sprint10/S10-012-architecture-design.md §五 (Execution Engine 集成:
  binding → CapabilityRegistry 解析 → WorkflowInstance 记录实体) + §四
  (binding 引用 {id, version?} — version 可复现)
- 用户 Task 拆分补充 (S10-012-007 Task 002): WorkflowInstance 增加
  capability_snapshot 字段 {agent:{id,version}, skill:{id,version},
  mcp:{id,version}, llm:{id,version}}; 执行实例历史可复现 — Registry 后续
  升级不影响历史 Runtime; 旧实例 (无该字段) 加载不报错 (默认 {})

覆盖 (org/execution.py):
- dispatch_task(registry=...) → instance.capability_snapshot 填充
  (agent/skill/mcp/llm 四类 {id, version}; llm 兼容 llm_configs 与 llm 键)
- registry 缺省 None → snapshot {} (纯 legacy, 零破坏)
- 序列化 round-trip: WorkflowInstanceStore save/load 保留 snapshot
- 旧数据兼容: 无 capability_snapshot 字段的 JSON → 加载默认 {} (不报错)
- dict binding 条目 (agent_ref/skill_ref/...) → snapshot 正常解析

basename 全仓库唯一 (test_org_instance_snapshot); 不跨目录依赖 helper
(实体工厂本地定义, 同 registry 测试惯例)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

# noqa: E402 — tests/org/conftest.py 已挂 factory-org 到 sys.path (org 包父目录)
from org.capabilities import (  # noqa: E402
    Agent,
    CapabilityRegistry,
    LLMConfig,
    MCP,
    Skill,
)
from org.execution import (  # noqa: E402
    WorkflowInstance,
    WorkflowInstanceStore,
    dispatch_task,
)
from org.management import Task, TaskStatus  # noqa: E402


@pytest.fixture
def registry(tmp_path: Path) -> CapabilityRegistry:
    """独立工厂根 (<tmp>/factory → workspace/capabilities/)。"""
    return CapabilityRegistry(tmp_path / "factory")


@pytest.fixture
def space_dir(tmp_path: Path) -> Path:
    """项目空间 (workspace/projects/{slug} 布局 — WorkflowInstanceStore 根)。"""
    return tmp_path / "proj"


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


def make_mcp(mcp_id: str = "git-tools", **overrides) -> MCP:
    data = {
        "id": mcp_id,
        "name": f"MCP {mcp_id}",
        "type": "http",
        "endpoint": "https://example.com/mcp",
        "capabilities": ["git"],
        "enabled": True,
        "state": "active",
    }
    data.update(overrides)
    return MCP.model_validate(data)


def make_llm_config(llm_id: str = "deepseek-default", **overrides) -> LLMConfig:
    data = {
        "id": llm_id,
        "provider": "deepseek",
        "model": "deepseek-v4",
        "endpoint": "https://api.deepseek.com",
        "parameters": {"temperature": 0.2},
        "enabled": True,
        "state": "active",
    }
    data.update(overrides)
    return LLMConfig.model_validate(data)


def _task(task_id: str = "T-1", status: TaskStatus | str = TaskStatus.READY) -> Task:
    return Task(id=task_id, title=f"task {task_id}", status=status)


def _seed_all(registry: CapabilityRegistry) -> None:
    """注册 agent/skill/mcp/llm 四实体 (ACTIVE+enabled)。"""
    registry.register_agent(make_agent("backend-agent"))
    registry.register_skill(make_skill("java", version="2.3.0"))
    registry.register_mcp(make_mcp("git-tools"))
    registry.register_llm_config(make_llm_config("deepseek-default"))


# ------------------------------------------------------------------ snapshot 填充


class TestDispatchSnapshot:
    def test_snapshot_filled_from_resolved_refs(self, registry: CapabilityRegistry):
        """registry 提供 + 实体存在 → snapshot {agent/skill/mcp/llm: {id, version}}。"""
        _seed_all(registry)
        bindings = {
            "agents": ["backend-agent"],
            "skills": ["java"],
            "mcps": ["git-tools"],
            "llm_configs": ["deepseek-default"],
        }
        inst = dispatch_task(_task(), bindings=bindings, registry=registry)
        assert inst.capability_snapshot == {
            "agent": {"id": "backend-agent", "version": ""},   # Agent 实体无 version 字段
            "skill": {"id": "java", "version": "2.3.0"},        # Skill 带 version
            "mcp": {"id": "git-tools", "version": ""},          # MCP 实体无 version 字段
            "llm": {"id": "deepseek-default", "version": ""},   # LLMConfig 无 version 字段
        }

    def test_snapshot_dict_binding_entries(self, registry: CapabilityRegistry):
        """dict binding 条目 ({agent_ref/skill_ref/...}) → snapshot 正常解析。"""
        _seed_all(registry)
        bindings = {
            "agents": [{"agent_ref": "backend-agent", "role": "backend"}],
            "skills": [{"skill_ref": "java"}],
            "mcps": [{"mcp_ref": "git-tools"}],
            "llm_configs": [{"llm_config_ref": "deepseek-default"}],
        }
        inst = dispatch_task(_task(), bindings=bindings, registry=registry)
        assert inst.capability_snapshot["agent"] == {"id": "backend-agent", "version": ""}
        assert inst.capability_snapshot["skill"] == {"id": "java", "version": "2.3.0"}
        assert inst.capability_snapshot["mcp"] == {"id": "git-tools", "version": ""}
        assert inst.capability_snapshot["llm"] == {"id": "deepseek-default", "version": ""}

    def test_snapshot_llm_shorthand_key(self, registry: CapabilityRegistry):
        """llm binding 兼容 bindings[\"llm\"] 简写键。"""
        _seed_all(registry)
        inst = dispatch_task(_task(), bindings={"llm": ["deepseek-default"]}, registry=registry)
        assert inst.capability_snapshot["llm"] == {"id": "deepseek-default", "version": ""}

    def test_snapshot_empty_without_registry(self):
        """registry 缺省 None → snapshot {} (纯 legacy 行为, 零破坏)。"""
        bindings = {"agents": ["backend-agent"], "skills": ["java"], "mcps": ["git-tools"]}
        inst = dispatch_task(_task(), bindings=bindings)
        assert inst.capability_snapshot == {}

    def test_snapshot_empty_no_bindings(self, registry: CapabilityRegistry):
        """无 bindings → snapshot {} (无绑定可执行, 不产生快照)。"""
        inst = dispatch_task(_task(), registry=registry)
        assert inst.capability_snapshot == {}

    def test_snapshot_partial_bindings(self, registry: CapabilityRegistry):
        """部分 binding (只有 skill) → snapshot 只含 skill 键。"""
        registry.register_skill(make_skill("java"))
        inst = dispatch_task(_task(), bindings={"skills": ["java"]}, registry=registry)
        assert inst.capability_snapshot == {"skill": {"id": "java", "version": "1.0.0"}}

    def test_snapshot_legacy_ref_preserved_raw(self, registry: CapabilityRegistry):
        """Registry 无对应 → legacy 保留裸字符串 (不崩溃, snapshot 可读)。"""
        _seed_all(registry)
        bindings = {"agents": ["ghost-agent"], "skills": ["java"]}
        inst = dispatch_task(_task(), bindings=bindings, registry=registry)
        assert inst.capability_snapshot["agent"] == "ghost-agent"
        assert inst.capability_snapshot["skill"] == {"id": "java", "version": "2.3.0"}


# ------------------------------------------------------------------ 序列化 / 旧数据兼容


class TestSnapshotPersistence:
    def test_store_round_trip_preserves_snapshot(self, registry: CapabilityRegistry, space_dir: Path):
        """save → load 保留 capability_snapshot (历史可复现)。"""
        _seed_all(registry)
        inst = dispatch_task(
            _task("T-1"),
            bindings={"agents": ["backend-agent"], "skills": ["java"]},
            registry=registry,
        )
        store = WorkflowInstanceStore(space_dir)
        store.save_instance(inst)
        loaded = store.load_instance(inst.instance_id)
        assert loaded is not None
        assert loaded.capability_snapshot == inst.capability_snapshot
        assert loaded.to_dict() == inst.to_dict()

    def test_to_dict_round_trip_preserves_snapshot(self, registry: CapabilityRegistry):
        """to_dict → model_validate round-trip 保留 snapshot。"""
        _seed_all(registry)
        inst = dispatch_task(_task("T-1"), bindings={"skills": ["java"]}, registry=registry)
        reloaded = WorkflowInstance.model_validate(inst.to_dict())
        assert reloaded.capability_snapshot == inst.capability_snapshot
        assert reloaded.capability_snapshot == {"skill": {"id": "java", "version": "2.3.0"}}

    def test_old_data_without_snapshot_loads_empty(self, space_dir: Path):
        """旧实例 JSON (无 capability_snapshot 字段) → 加载不报错, 默认 {}。"""
        old = WorkflowInstance(instance_id="WI-old", task_id="T-old")
        assert old.capability_snapshot == {}
        store = WorkflowInstanceStore(space_dir)
        store.save_instance(old)
        loaded = store.load_instance("WI-old")
        assert loaded is not None
        assert loaded.capability_snapshot == {}
        assert loaded.instance_id == "WI-old"

    def test_old_data_file_without_field_loads_empty(self, space_dir: Path):
        """直接写不含 capability_snapshot 字段的 JSON 文件 → 加载默认 {}。"""
        import json

        store = WorkflowInstanceStore(space_dir)
        raw = {
            "instance_id": "WI-old2",
            "task_id": "T-old2",
            "workflow_id": "",
            "agent": "backend-agent",
            "skill": "",
            "mcp": "",
            "status": "created",
            "start_time": None,
            "end_time": None,
            "result": "",
            "created_at": "2026-08-11T00:00:00Z",
        }
        path = store.instance_dir / "WI-old2.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw), encoding="utf-8")
        loaded = store.load_instance("WI-old2")
        assert loaded is not None
        assert loaded.capability_snapshot == {}

    def test_snapshot_value_semantics_frozen_at_dispatch(self, registry: CapabilityRegistry):
        """snapshot 是分发时值拷贝 — Registry 后续升级不影响历史实例。"""
        registry.register_skill(make_skill("java", version="1.0.0"))
        inst = dispatch_task(_task("T-1"), bindings={"skills": ["java"]}, registry=registry)
        assert inst.capability_snapshot["skill"] == {"id": "java", "version": "1.0.0"}
        # Registry 升级 (同 id 新 version 覆盖)
        registry.register_skill(make_skill("java", version="2.0.0"))
        # 历史实例 snapshot 保持旧 version
        assert inst.capability_snapshot["skill"] == {"id": "java", "version": "1.0.0"}
