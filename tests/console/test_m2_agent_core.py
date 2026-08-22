"""test_m2_agent_core.py — M2 员工内核契约测试 (S10-087, v1.1.9, A1-A5 全覆盖)。

覆盖 (契约见 docs/sprint10/S10-087-M2-sprint-spec.md §2):
- A1 AgentEntity: agt- 前缀 id / to_dict/from_dict roundtrip / 缺字段明确报错
- A2 AgentRegistry: 注册/取用/列表; 同 role 多 provider 并存; 行业隔离; agents.json
- A3 ExpertFactory: 装配 7 专家; 缺 skill 明确报错; 无 LLM 确定性兜底非空
- A4 HandoffBus: PM→…→SeniorPM 血缘互引; 冲突 → ReviewGate 挂起等审批
- A5 product_pipeline: created_by=agent_id; 资产互引; 无 LLM 兜底非空

basename 全仓库唯一 (test_s10_0XX_* / test_m2_* 前缀)。
"""

from __future__ import annotations

import importlib
from pathlib import Path

ACT = importlib.import_module("factory-console.session.actions")
ART = importlib.import_module("factory-console.session.artifact_registry")
ENTITY = importlib.import_module("factory-console.session.agent_entity")
REG = importlib.import_module("factory-console.session.agent_registry")
FACTORY = importlib.import_module("factory-console.session.expert_factory")
BUS = importlib.import_module("factory-console.session.handoff_bus")
PIPE = importlib.import_module("factory-console.session.pipeline_runner")
PROD = importlib.import_module("factory-console.session.product")
REVIEW = importlib.import_module("factory-console.session.review_gate")


def _product(**kw):
    data = dict(
        name="CRM",
        problem="客户管理混乱, 跟进靠表格",
        user="销售团队",
        core_features=["客户跟进", "报表"],
        raw="我要做CRM",
    )
    data.update(kw)
    return PROD.ProductIntent(**data)


def _provider(pid="reasoning", model="gpt-4o"):
    return ENTITY.ProviderRef(id=pid, model=model)


# ================================================================ A1 AgentEntity

class TestAgentEntityContract:
    def test_agt_prefix_id_roundtrip(self):
        """契约: agt- 前缀 id + to_dict/from_dict roundtrip 相等。"""
        agent = ENTITY.AgentEntity(
            id="agt-it-pm-1", role="pm", industry="it",
            provider=_provider(), system_prompt="你是产品经理",
            skills=["product_strategy", "market_research"],
            knowledge_ref="product_intelligence", workflow_ref="feature-delivery",
            tools=[], evaluation_ref="ev-1",
        )
        restored = ENTITY.AgentEntity.from_dict(agent.to_dict())
        assert restored == agent
        assert restored.id == "agt-it-pm-1"
        assert restored.provider.id == "reasoning"
        assert restored.provider.model == "gpt-4o"
        assert restored.skills == ["product_strategy", "market_research"]

    def test_id_must_have_agt_prefix(self):
        """契约: 非 agt- 前缀 id → 明确报错 (不静默)。"""
        import pytest
        with pytest.raises(Exception):
            ENTITY.AgentEntity(id="pm-1", role="pm", industry="it")

    def test_id_format_requires_industry_role_seq(self):
        import pytest
        for bad in ("agt-pm", "agt-it-", "agt-it-pm", "agt-it-pm-x"):
            with pytest.raises(Exception):
                ENTITY.AgentEntity(id=bad, role="pm", industry="it")

    def test_missing_required_field_raises(self):
        """契约: 缺必填字段 → 明确报错 (ValidationError, 不静默)。"""
        import pytest
        with pytest.raises(Exception):
            ENTITY.AgentEntity(id="agt-it-pm-1", role="pm")  # 缺 industry
        with pytest.raises(Exception):
            ENTITY.AgentEntity(id="agt-it-pm-1", industry="it")  # 缺 role
        with pytest.raises(Exception):
            ENTITY.AgentEntity(role="pm", industry="it")  # 缺 id

    def test_industry_must_match_id_prefix(self):
        """id 前缀与 industry 不一致 → 明确报错 (行业隔离在 id 可见)。"""
        import pytest
        with pytest.raises(Exception):
            ENTITY.AgentEntity(id="agt-ops-pm-1", role="pm", industry="it")

    def test_provider_optional_for_deterministic(self):
        """无 LLM: provider=None 合法 (确定性兜底可用面)。"""
        agent = ENTITY.AgentEntity(id="agt-it-pm-1", role="pm", industry="it")
        assert agent.provider is None
        assert agent.to_dict()["provider"] is None

    def test_profile_defaults(self):
        agent = ENTITY.AgentEntity(id="agt-it-pm-1", role="pm", industry="it")
        assert agent.profile.success_rate == 0.0
        assert agent.profile.samples == 0


# ================================================================ A2 AgentRegistry

class TestAgentRegistryContract:
    def test_register_get_list(self, tmp_path):
        """契约: register→get→list + agents.json 持久化。"""
        reg = REG.AgentRegistry(tmp_path / "agents.json")
        agent = ENTITY.AgentEntity(
            id="agt-it-pm-1", role="pm", industry="it", provider=_provider(),
            skills=["product_strategy"],
        )
        reg.add(agent)
        assert reg.get("agt-it-pm-1") == agent
        assert reg.list() == [agent]
        assert (tmp_path / "agents.json").is_file()
        # 重新加载 (持久化)
        reg2 = REG.AgentRegistry(tmp_path / "agents.json")
        assert reg2.get("agt-it-pm-1") == agent

    def test_same_role_multiple_providers_coexist(self, tmp_path):
        """契约: 同 role 多 provider 并存 (agent id 唯一键)。"""
        reg = REG.AgentRegistry(tmp_path / "agents.json")
        reg.add(ENTITY.AgentEntity(id="agt-it-pm-1", role="pm", industry="it",
                                   provider=_provider("reasoning", "gpt-4o"),
                                   skills=["product_strategy"]))
        reg.add(ENTITY.AgentEntity(id="agt-it-pm-2", role="pm", industry="it",
                                   provider=_provider("reasoning-b", "claude"),
                                   skills=["product_strategy"]))
        agents = reg.list(industry="it")
        assert len(agents) == 2
        assert {a.id for a in agents} == {"agt-it-pm-1", "agt-it-pm-2"}
        assert {a.provider.id for a in agents} == {"reasoning", "reasoning-b"}

    def test_duplicate_id_raises(self, tmp_path):
        import pytest
        reg = REG.AgentRegistry(tmp_path / "agents.json")
        agent = ENTITY.AgentEntity(id="agt-it-pm-1", role="pm", industry="it",
                                   skills=["product_strategy"])
        reg.add(agent)
        with pytest.raises(REG.AgentAlreadyExists):
            reg.add(agent)

    def test_industry_isolation(self, tmp_path):
        """契约: 跨行业互不可见 (it.* / ops.*)。"""
        reg = REG.AgentRegistry(tmp_path / "agents.json")
        reg.add(ENTITY.AgentEntity(id="agt-it-pm-1", role="pm", industry="it",
                                   skills=["product_strategy"]))
        reg.add(ENTITY.AgentEntity(id="agt-ops-qa-1", role="qa", industry="ops",
                                   skills=["quality_assurance"]))
        assert reg.count(industry="it") == 1
        assert reg.count(industry="ops") == 1
        assert reg.list(industry="it")[0].id == "agt-it-pm-1"
        assert reg.list(industry="ops")[0].id == "agt-ops-qa-1"
        assert reg.list() == sorted(reg.list(), key=lambda a: a.id)
        assert reg.get("agt-it-pm-1") is not None
        assert reg.get("agt-ops-qa-1") is not None

    def test_invalid_industry_rejected(self, tmp_path):
        import pytest
        reg = REG.AgentRegistry(tmp_path / "agents.json")
        with pytest.raises(REG.InvalidIndustry):
            reg.add(ENTITY.AgentEntity(id="agt-xyz-pm-1", role="pm", industry="xyz",
                                       skills=["product_strategy"]))
        with pytest.raises(REG.InvalidIndustry):
            reg.next_id("xyz", "pm")

    def test_next_id_sequences_per_industry_role(self, tmp_path):
        reg = REG.AgentRegistry(tmp_path / "agents.json")
        assert reg.next_id("it", "pm") == "agt-it-pm-1"
        reg.add(ENTITY.AgentEntity(id="agt-it-pm-1", role="pm", industry="it",
                                   skills=["product_strategy"]))
        assert reg.next_id("it", "pm") == "agt-it-pm-2"
        assert reg.next_id("it", "qa") == "agt-it-qa-1"   # 各角色独立序号
        assert reg.next_id("ops", "pm") == "agt-ops-pm-1"  # 各行业独立序号

    def test_remove_missing_raises(self, tmp_path):
        import pytest
        reg = REG.AgentRegistry(tmp_path / "agents.json")
        with pytest.raises(REG.AgentNotFound):
            reg.remove("agt-it-pm-1")
