"""tests/org/test_org_capability_resolver.py — S10-012 Task 007-001: Capability Resolver (TDD)。

设计依据 (唯一):
- docs/sprint10/S10-012-architecture-design.md §五 (Execution Engine 集成:
  binding → CapabilityRegistry 解析 → 实体) + §四 (CapabilityBinding 引用
  {type, id, version?} — version pin 可复现)
- 用户 Task 拆分补充 (S10-012-007 Task 001): Resolver 支持
  Agent/Skill/MCP/WorkflowTemplate/LLMConfig 五类; 输出含 id/name/version/
  status/metadata; binding_ref 可为字符串 (旧格式) 或 dict
  ({agent_ref/skill_ref/... 或 {id, version?}}); kind 映射经统一门面
  get_capability (大小写/复数/连字符别名已处理)

覆盖 (org/execution.py — resolve_capability + CapabilityResolution):
- 解析成功: 字符串引用 / dict 引用 (ref_key / ref / id 键) → resolution
  含 id/name/version/status/metadata + entity (Registry 实体实例)
- 缺失: Registry 无对应实体 → None (业务状态非异常, 不抛)
- 未知 kind → ValueError (拼写错误显式暴露)
- 五类实体: agent/skill/mcp/workflow/llm_config 全部可解析
- kind 规范化: 大小写不敏感 / 复数别名 / 连字符 (llm-configs → llm_config)
- version pin: dict {ref_key, version} → resolution.version_pin 保留
- metadata: 实体无独立 metadata 字段 → 以 to_dict() 全量字段输出 (报告注明)

basename 全仓库唯一 (test_org_capability_resolver — 遵循 test_org_ 前缀);
不跨目录依赖 helper (实体工厂本地定义, 同 test_org_skill_registry.py 惯例)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

# noqa: E402 — tests/org/conftest.py 已挂 factory-org 到 sys.path (org 包父目录)
from org.capabilities import (  # noqa: E402
    Agent,
    CapabilityRegistry,
    CapabilityState,
    LLMConfig,
    MCP,
    Skill,
    WorkflowTemplate,
)
from org.execution import CapabilityResolution, resolve_capability  # noqa: E402


@pytest.fixture
def registry(tmp_path: Path) -> CapabilityRegistry:
    """独立工厂根 (<tmp>/factory → workspace/capabilities/)。"""
    return CapabilityRegistry(tmp_path / "factory")


# ------------------------------------------------------------------ 实体工厂 (本地, 同 registry 测试惯例)


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


def make_workflow(wf_id: str = "software-development-v1", **overrides) -> WorkflowTemplate:
    data = {
        "id": wf_id,
        "name": f"Workflow {wf_id}",
        "industry": "software",
        "steps": [{"id": "s1", "name": "build"}],
        "enabled": True,
        "state": "active",
    }
    data.update(overrides)
    return WorkflowTemplate.model_validate(data)


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


# ------------------------------------------------------------------ 解析成功


class TestResolveSuccess:
    def test_resolve_skill_string_ref(self, registry: CapabilityRegistry):
        """字符串引用 (旧格式) → 解析为 Skill 实体。"""
        registry.register_skill(make_skill("java"))
        res = resolve_capability("java", registry, kind="skill")
        assert res is not None
        assert res.resolved is True
        assert res.kind == "skill"
        assert res.id == "java"
        assert isinstance(res.entity, Skill)

    def test_resolve_skill_dict_ref_ref_key(self, registry: CapabilityRegistry):
        """dict 引用 {skill_ref: ...} (project-lifecycle.md 形式) → 解析成功。"""
        registry.register_skill(make_skill("java"))
        res = resolve_capability({"skill_ref": "java", "level": "advanced"}, registry, kind="skill", ref_key="skill_ref")
        assert res is not None
        assert res.resolved is True
        assert res.id == "java"

    def test_resolve_dict_ref_fallback_ref_key(self, registry: CapabilityRegistry):
        """dict 引用 {ref: ...} 回退键 → 解析成功。"""
        registry.register_skill(make_skill("java"))
        res = resolve_capability({"ref": "java"}, registry, kind="skill")
        assert res is not None
        assert res.id == "java"

    def test_resolve_dict_ref_fallback_id_key(self, registry: CapabilityRegistry):
        """dict 引用 {id, version?} (CapabilityBinding 形式) → 解析成功。"""
        registry.register_skill(make_skill("java"))
        res = resolve_capability({"id": "java", "version": "1.0.0"}, registry, kind="skill")
        assert res is not None
        assert res.id == "java"
        assert res.version_pin == "1.0.0"

    def test_resolution_fields_complete(self, registry: CapabilityRegistry):
        """输出字段: id/name/version/status/metadata 齐全 (Task 001 要求)。"""
        registry.register_skill(make_skill("java", version="2.1.0"))
        res = resolve_capability("java", registry, kind="skill")
        assert res is not None
        assert res.name == "Skill java"
        assert res.version == "2.1.0"
        assert res.status == CapabilityState.ACTIVE.value
        # 实体无独立 metadata 字段 → 以 to_dict() 全量字段输出 (报告注明)
        assert isinstance(res.metadata, dict)
        assert res.metadata["id"] == "java"
        assert res.metadata["version"] == "2.1.0"
        assert res.metadata["state"] == "active"
        assert "name" in res.metadata and "enabled" in res.metadata

    def test_resolve_five_kinds(self, registry: CapabilityRegistry):
        """五类实体 (Agent/Skill/MCP/WorkflowTemplate/LLMConfig) 全部可解析。"""
        registry.register_agent(make_agent("backend-agent"))
        registry.register_skill(make_skill("java"))
        registry.register_mcp(make_mcp("git-tools"))
        registry.register_workflow(make_workflow("software-development-v1"))
        registry.register_llm_config(make_llm_config("deepseek-default"))

        cases = [
            ("agent", "backend-agent", Agent),
            ("skill", "java", Skill),
            ("mcp", "git-tools", MCP),
            ("workflow", "software-development-v1", WorkflowTemplate),
            ("llm_config", "deepseek-default", LLMConfig),
        ]
        for kind, ref_id, entity_cls in cases:
            res = resolve_capability(ref_id, registry, kind=kind)
            assert res is not None, f"kind={kind} ref={ref_id} 应解析成功"
            assert res.resolved is True
            assert res.id == ref_id
            assert res.kind == kind
            assert isinstance(res.entity, entity_cls)

    def test_resolve_agent_dict_ref_with_version_pin(self, registry: CapabilityRegistry):
        """dict 引用带 version pin → version_pin 保留 (可复现 binding)。"""
        registry.register_agent(make_agent("backend-agent"))
        res = resolve_capability(
            {"agent_ref": "backend-agent", "version": "1.2.0"}, registry,
            kind="agent", ref_key="agent_ref",
        )
        assert res is not None
        assert res.id == "backend-agent"
        assert res.version_pin == "1.2.0"

    def test_resolve_entity_identity(self, registry: CapabilityRegistry):
        """解析结果 entity 即 Registry 实体 (目录信源重读 → 数据相等非同一实例)。"""
        registry.register_skill(make_skill("java"))
        res = resolve_capability("java", registry, kind="skill")
        assert res is not None
        assert res.entity is not None
        assert res.entity.id == "java"
        assert res.entity.name == "Skill java"
        assert res.entity.version == "1.0.0"


# ------------------------------------------------------------------ 缺失 / 无有效引用


class TestResolveMissing:
    def test_missing_entity_returns_none(self, registry: CapabilityRegistry):
        """Registry 无对应实体 → None (缺失是业务状态, 不抛错)。"""
        assert resolve_capability("ghost-skill", registry, kind="skill") is None

    def test_missing_entity_empty_registry(self, registry: CapabilityRegistry):
        """空 Registry (无任何注册) → 任意引用解析 None。"""
        assert resolve_capability("anything", registry, kind="agent") is None

    def test_dict_ref_without_ref_keys_returns_none(self, registry: CapabilityRegistry):
        """dict 无 ref/ref_key/id 键 (如 {role: pm}) → None (无有效引用)。"""
        registry.register_agent(make_agent("backend-agent"))
        assert resolve_capability({"role": "pm"}, registry, kind="agent", ref_key="agent_ref") is None

    def test_empty_string_ref_returns_none(self, registry: CapabilityRegistry):
        """空字符串引用 → None。"""
        registry.register_skill(make_skill("java"))
        assert resolve_capability("", registry, kind="skill") is None


# ------------------------------------------------------------------ 未知 kind


class TestResolveUnknownKind:
    def test_unknown_kind_raises(self, registry: CapabilityRegistry):
        """未知 kind → ValueError (拼写错误显式暴露, 不静默 None)。"""
        with pytest.raises(ValueError, match="unknown capability binding kind"):
            resolve_capability("java", registry, kind="industry")  # industry 不参与执行绑定
        with pytest.raises(ValueError, match="unknown capability binding kind"):
            resolve_capability("java", registry, kind="skil")  # 拼写错误

    def test_empty_kind_raises(self, registry: CapabilityRegistry):
        with pytest.raises(ValueError, match="non-empty string"):
            resolve_capability("java", registry, kind="")

    def test_kind_normalization(self, registry: CapabilityRegistry):
        """kind 规范化: 大小写不敏感 / 复数别名 / 连字符 → 规范名。"""
        registry.register_skill(make_skill("java"))
        for kind in ("SKILL", "skills", "Skill", " skill "):
            res = resolve_capability("java", registry, kind=kind)
            assert res is not None
            assert res.kind == "skill"

    def test_kind_llm_config_aliases(self, registry: CapabilityRegistry):
        """llm_config 别名: llm-config / llm-configs / llms 全部解析。"""
        registry.register_llm_config(make_llm_config("deepseek-default"))
        for kind in ("llm-config", "llm-configs", "LLM_CONFIGS", "llms"):
            res = resolve_capability("deepseek-default", registry, kind=kind)
            assert res is not None, f"kind={kind} 应解析成功"
            assert res.kind == "llm_config"
