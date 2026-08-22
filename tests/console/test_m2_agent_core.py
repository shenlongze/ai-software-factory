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


# ================================================================ A3 ExpertFactory

class TestExpertFactoryContract:
    def test_assemble_seven_software_experts(self, tmp_path):
        """契约: assemble 7 个软件行业专家 (pm/market/competitive/ux/architect/
        backend/qa — A3 口径 + 管线链角色), 全部 agt-it-* id + 非空技能。"""
        factory = FACTORY.ExpertFactory()
        # A3 验收口径: 7 角色 (pm/market/competitive/ux/architect/backend/qa)
        a3_roles = ["pm", "market", "competitive", "ux", "architect", "backend", "qa"]
        team = factory.build_team(roles=a3_roles, provider=_provider())
        assert len(team) == 7
        assert [a.role for a in team] == a3_roles
        for agent in team:
            assert agent.id.startswith("agt-it-")
            assert agent.id.endswith("-1")
            assert agent.skills, f"{agent.id} 缺技能"
            assert agent.provider is not None
            assert agent.system_prompt
        # 管线链 7 角色 (A5 用)
        chain = factory.build_team()
        assert [a.role for a in chain] == list(FACTORY.PIPELINE_ROLES)

    def test_assemble_uses_registry_numbering(self, tmp_path):
        """装配编号经注册表 next_id: 已注册专家 → 下个编号 (各角色/行业独立)。"""
        reg = REG.AgentRegistry(tmp_path / "agents.json")
        factory = FACTORY.ExpertFactory(registry=reg)
        a1 = factory.assemble("pm")
        assert a1.id == "agt-it-pm-1"
        # assemble 不自动落盘 (KISS: 持久化归 AgentRegistry.add) — "expert build"
        # 语义 = assemble + add 两步
        reg.add(a1)
        a2 = factory.assemble("pm")
        assert a2.id == "agt-it-pm-2"
        assert reg.count(industry="it") == 1

    def test_assemble_then_persist_flow(self, tmp_path):
        """"expert build" 语义: assemble → AgentEntity → registry.add 落盘 agents.json。"""
        reg = REG.AgentRegistry(tmp_path / "agents.json")
        factory = FACTORY.ExpertFactory(registry=reg)
        agent = factory.assemble("pm", provider=_provider())
        reg.add(agent)
        assert reg.get("agt-it-pm-1") == agent
        assert (tmp_path / "agents.json").is_file()
        assert "agt-it-pm-1" in (tmp_path / "agents.json").read_text(encoding="utf-8")

    def test_missing_skill_raises_clear_error(self, tmp_path):
        """契约: 引用不存在 skill → 明确报错 (不静默, 列出缺失技能)。"""
        import pytest
        factory = FACTORY.ExpertFactory()
        with pytest.raises(FACTORY.ExpertAssemblyError) as exc:
            factory.assemble("pm", skills=["product_strategy", "no_such_skill_xyz"])
        msg = str(exc.value)
        assert "no_such_skill_xyz" in msg
        assert "装配" in msg

    def test_unknown_role_raises(self):
        import pytest
        factory = FACTORY.ExpertFactory()
        with pytest.raises(FACTORY.ExpertAssemblyError):
            factory.assemble("no_such_role")

    def test_unknown_workflow_raises(self):
        import pytest
        factory = FACTORY.ExpertFactory()
        with pytest.raises(FACTORY.ExpertAssemblyError) as exc:
            factory.assemble("pm", workflow_ref="no_such_workflow")
        assert "workflow" in str(exc.value)

    def test_unknown_knowledge_raises(self):
        import pytest
        factory = FACTORY.ExpertFactory()
        with pytest.raises(FACTORY.ExpertAssemblyError) as exc:
            factory.assemble("pm", knowledge_ref="no_such_knowledge")
        assert "knowledge" in str(exc.value)

    def test_workflow_knowledge_defaults_valid(self):
        """默认工作流/知识挂载均通过装配校验 (真实内置流程/知识源)。"""
        factory = FACTORY.ExpertFactory()
        for role in FACTORY.PIPELINE_ROLES:
            agent = factory.assemble(role)
            assert agent.workflow_ref in ("feature-delivery", "")
            assert agent.knowledge_ref in FACTORY.KNOWLEDGE_SOURCES

    def test_no_llm_deterministic_fallback_nonempty(self):
        """契约: 无 LLM (provider=None) → 确定性兜底非空 (全 7 角色)。"""
        factory = FACTORY.ExpertFactory()
        team = factory.build_team(provider=None)
        product = _product()
        for agent in team:
            assert agent.provider is None
            md = factory.deterministic_content(agent.role, product)
            assert md and md.strip(), f"{agent.role} 兜底为空"
            assert "（待补充）" in md or "#" in md  # 非空可审计

    def test_injected_skill_checker_used(self, tmp_path):
        """注入 skill 校验器生效 (自定义技能目录可挂载)。"""
        custom = {"custom_skill_a"}
        factory = FACTORY.ExpertFactory(skill_exists=lambda s: s in custom)
        agent = factory.assemble("pm", skills=["custom_skill_a"])
        assert agent.skills == ["custom_skill_a"]


# ================================================================ A4 HandoffBus

class TestHandoffBusContract:
    def _team(self, provider=True):
        factory = FACTORY.ExpertFactory()
        return factory.build_team(
            provider=_provider() if provider else None
        )

    def test_send_writes_artifact_with_agent_id(self, tmp_path):
        """契约: send → ArtifactRegistry.write(created_by=agent_id,
        parent_event_id, metadata.parent_artifact)。"""
        bus = BUS.HandoffBus(tmp_path, "crm")
        pm, market = self._team()[:2]
        msg, record = bus.send(
            pm, market, artifact_type="product", content="# 产品策略",
            source="conv-1", parent_artifact_id="",
        )
        assert msg.status == BUS.MSG_STATUS_DELIVERED
        assert msg.from_agent == "agt-it-pm-1"
        assert msg.to_agent == "agt-it-market-1"
        assert msg.artifacts == [record.id]
        assert record.created_by == "agt-it-pm-1"
        assert (record.metadata or {}).get("parent_artifact") == ""
        assert record.content_ref  # 落盘

    def test_route_seven_agents_parent_artifact_lineage(self, tmp_path):
        """契约: PM→Market→Competitive→UX→Architect→QA→SeniorPM 依次消费
        上一产出; 每资产 metadata.parent_artifact 指向上一资产。"""
        bus = BUS.HandoffBus(tmp_path, "crm")
        team = self._team()
        assert [a.role for a in team] == list(FACTORY.PIPELINE_ROLES)

        def produce(agent, prev_id, product, prev_content=""):
            return f"# {agent.role}\n消费上一产出: {prev_id or '(根)'}"

        result = bus.route(team, produce=produce, product=_product(), source="conv-1")
        assert len(result.records) == 7
        assert [r.type for r in result.records] == [
            "product", "market_analysis", "competitive_analysis",
            "ux_flow", "architecture", "test_plan", "prd",
        ]
        for i, r in enumerate(result.records):
            assert r.created_by.startswith("agt-")
            expected = result.records[i - 1].id if i > 0 else ""
            assert (r.metadata or {}).get("parent_artifact") == expected
            if i > 0:
                assert r.parent_event_id == result.records[i - 1].event_id
                assert r.parent_event_id  # 审计血缘非空
        assert len(result.messages) == 7
        # 末环 to=自身 (终止交接, PRD 为终产物)
        assert result.messages[-1].to_agent == "agt-it-prd-1"
        # 消息落盘
        assert len(bus.load_messages()) == 7

    def test_route_produce_receives_previous_content(self, tmp_path):
        """S10-088 T2: 后一角色 produce 收到上一资产正文 (交接消费, 非仅 id)。

        断言: 第 4 参 prev_content 含上一环落盘正文 (经 ArtifactRegistry.read
        回读, 非仅 asset id); 首环 (根) 为空。
        """
        bus = BUS.HandoffBus(tmp_path, "crm")
        team = self._team()
        received = []

        def produce(agent, prev_id, product, prev_content=""):
            marker = "根"
            if prev_content and "MARKER-" in prev_content:
                marker = prev_content.split("MARKER-")[-1].split("\n")[0]
            received.append((agent.role, prev_id, prev_content))
            return f"# {agent.role} 产出\nMARKER-{agent.role}-{marker}"

        result = bus.route(team, produce=produce, product=_product(), source="conv-1")
        assert len(received) == 7
        # 首环: 根资产无上一产出 (id 与正文均为空)
        role0, prev_id0, content0 = received[0]
        assert prev_id0 == ""
        assert content0 == ""
        # 后续每环: prev_id 指向上一资产 id + prev_content 含上一环落盘正文
        for i in range(1, 7):
            role, prev_id, content = received[i]
            assert prev_id == result.records[i - 1].id, role
            assert content and content.strip(), f"{role} 未收到上一资产正文"
            prev_role = received[i - 1][0]
            assert f"MARKER-{prev_role}-" in content, (
                f"{role} 上一资产正文未传入 (prev_role={prev_role}, content={content[:60]!r})"
            )

    def test_conflict_routes_to_review_gate_pending(self, tmp_path):
        """契约: 冲突 → ConflictResolver → ReviewGate 挂起等审批 (pending_review)。"""
        bus = BUS.HandoffBus(tmp_path, "crm")
        team = self._team()

        def produce(agent, prev_id, product, prev_content=""):
            return f"# {agent.role}"

        def conflicts_for(index, agent):
            if index == 2:  # competitive → ux 交接冲突
                return [{"file": "a.py", "task_a": agent.id, "task_b": "agt-it-ux-1"}]
            return None

        import pytest
        with pytest.raises(BUS.HandoffBlocked) as exc:
            bus.route(team, produce=produce, product=_product(), conflicts_for=conflicts_for)
        blocked = exc.value
        assert blocked.message.status == BUS.MSG_STATUS_PENDING_REVIEW
        assert blocked.message.review_id
        # 审批挂起记录
        pending = bus.review_gate.pending()
        assert pending, "冲突应产生挂起审批"
        assert str(pending[0].project_id) if hasattr(pending[0], "project_id") else True
        # 阻断前资产已写, 阻断点无资产 (未静默写脏资产)
        assert len(bus.registry.list()) == 2  # pm, market 已产出; competitive 未产出

    def test_review_required_pending_without_conflict(self, tmp_path):
        """review_required=True (无冲突) → 同样走 ReviewGate 挂起。"""
        bus = BUS.HandoffBus(tmp_path, "crm")
        pm, market = self._team()[:2]
        msg, record = bus.send(
            pm, market, artifact_type="product", content="# 产品策略",
            review_required=True,
        )
        assert msg.status == BUS.MSG_STATUS_PENDING_REVIEW
        assert record is None
        assert bus.review_gate.pending()

    def test_messages_persist_and_load(self, tmp_path):
        bus = BUS.HandoffBus(tmp_path, "crm")
        pm, market = self._team()[:2]
        bus.send(pm, market, artifact_type="product", content="# x", decisions=["d1"],
                 constraints=["c1"])
        msgs = bus.load_messages()
        assert len(msgs) == 1
        assert msgs[0]["from"] == "agt-it-pm-1"
        assert msgs[0]["to"] == "agt-it-market-1"
        assert msgs[0]["decisions"] == ["d1"]
        assert msgs[0]["constraints"] == ["c1"]
        assert msgs[0]["artifacts"]


# ================================================================ A5 product_pipeline 接线

class TestProductPipelineAgentChain:
    def test_run_uses_real_agents_with_agt_created_by(self, tmp_path):
        """契约: 让PM分析 → 7 专家真实产出; 每资产 created_by 以 agt- 开头。"""
        pipeline = PIPE.ProductPipeline(tmp_path, "crm")
        result = pipeline.run(_product(), source="conv-1")
        assert len(result.records) == 7
        for r in result.records:
            assert r.created_by.startswith("agt-"), r.created_by
            assert r.status == "draft"
            md = Path(r.content_ref).read_text(encoding="utf-8")
            assert md.strip()  # 内容非空 (无 LLM → deterministic 兜底)

    def test_lineage_parent_artifact_chain(self, tmp_path):
        """契约: 资产互引 — 每资产 metadata.parent_artifact 指向上一资产。"""
        pipeline = PIPE.ProductPipeline(tmp_path, "crm")
        result = pipeline.run(_product())
        for i, r in enumerate(result.records):
            expected = result.records[i - 1].id if i > 0 else ""
            assert (r.metadata or {}).get("parent_artifact") == expected
            if i > 0:
                assert r.parent_event_id == result.records[i - 1].event_id
                assert r.parent_event_id

    def test_llm_failure_falls_back_deterministic_nonempty(self, tmp_path):
        """契约: 无 LLM 环境 → 各角色确定性兜底非空。"""
        def boom(prompt, role):
            raise RuntimeError("llm down")
        pipeline = PIPE.ProductPipeline(tmp_path, "crm", llm_fn=boom)
        result = pipeline.run(_product())
        assert len(result.records) == 7
        for r in result.records:
            assert Path(r.content_ref).read_text(encoding="utf-8").strip()

    def test_llm_path_uses_agent_prompt(self, tmp_path):
        """LLM 路径: 提示词含角色 system_prompt 与上一资产血缘。"""
        seen = []
        def capture(prompt, role):
            seen.append(prompt)
            return f"# LLM 产出 {role}\n内容非空"
        pipeline = PIPE.ProductPipeline(tmp_path, "crm", llm_fn=capture)
        result = pipeline.run(_product())
        assert len(seen) == 7
        assert "你是软件行业产品经理" in seen[0]
        assert "agt-it-pm-1" in seen[1] or "product-v1-" in seen[1]
        # S10-088 T2: prompt 嵌上一资产正文 (非仅 id) — 根环明确 '(无 — 根资产)'
        assert "上一资产内容: (无 — 根资产)" in seen[0]
        assert "上一资产内容:" in seen[1]
        assert "上一资产内容" in seen[1]
        assert all(Path(r.content_ref).read_text(encoding="utf-8").strip()
                   for r in result.records)

    def test_rerun_bumps_versions(self, tmp_path):
        pipeline = PIPE.ProductPipeline(tmp_path, "crm")
        pipeline.run(_product())
        result = pipeline.run(_product())
        assert all(r.version == 2 for r in result.records)

    def test_agents_persisted_in_registry_after_build(self, tmp_path):
        """A3+A2 闭环: 装配 7 专家 → 落盘 agents.json (expert build 语义)。"""
        reg = REG.AgentRegistry(tmp_path / "agents.json")
        factory = FACTORY.ExpertFactory(registry=reg)
        for agent in factory.build_team(provider=_provider()):
            reg.add(agent)
        assert reg.count(industry="it") == 7
        data = reg.load()
        assert all(str(v["id"]).startswith("agt-") for v in data.values())


class TestProductPipelineAction:
    """A5 接线: actions.product_pipeline ('让PM分析') 走真 Agent 链。"""

    def _run_through_session(self, tmp_path, monkeypatch, capsys):
        class FakeOrgCli:
            def __init__(self):
                self.calls = []

            def cmd_project_register(self, root, args):
                self.calls.append((root, args))
                return {
                    "ok": True,
                    "project": {"id": "p1", "name": args.name, "slug": "crm"},
                    "exit_code": 0,
                }

        import factory_console.session.context as ctx_mod
        import factory_console.session.session as sess_mod
        org = FakeOrgCli()
        monkeypatch.setattr(ACT, "_load_org_cli", lambda: org)
        root = tmp_path / "ws"
        root.mkdir()
        sess = sess_mod.InteractiveSession(
            context_manager=ctx_mod.ContextManager(workspace=str(root)),
        )
        sess._dispatch("我想做CRM")
        sess._dispatch("客户管理混乱，跟进靠表格")
        sess._dispatch("销售团队")
        sess._dispatch("客户跟进、报表")
        sess._dispatch("y")
        capsys.readouterr()
        sess._dispatch("让PM分析")
        return capsys.readouterr().out, root

    def test_action_pipeline_real_agent_chain(self, tmp_path, monkeypatch, capsys):
        out, root = self._run_through_session(tmp_path, monkeypatch, capsys)
        assert "产品管线完成" in out
        assert "7 个资产" in out
        # 落盘资产 created_by 以 agt- 开头 + parent_artifact 血缘
        artifacts = ART.ArtifactRegistry(root, "crm")
        records = artifacts.list()
        assert len(records) == 7
        # 按管线链顺序 (list() 按 type 字典序 — 链序需按 PIPELINE_ROLES 映射)
        chain_types = [
            "product", "market_analysis", "competitive_analysis",
            "ux_flow", "architecture", "test_plan", "prd",
        ]
        by_type = {r.type: r for r in records}
        ordered = [by_type[t] for t in chain_types]
        for i, r in enumerate(ordered):
            assert r.created_by.startswith("agt-")
            expected = ordered[i - 1].id if i > 0 else ""
            assert (r.metadata or {}).get("parent_artifact") == expected
