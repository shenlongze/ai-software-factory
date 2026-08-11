"""tests/org/test_org_agent_registry.py — S10-012 Task 003: Agent Registry (TDD)。

设计依据 (唯一):
- docs/sprint10/S10-012-architecture-design.md §三 (Registry 架构: 目录信源
  workspace/capabilities/{kind}/{id}.json + CRUD + enabled 过滤 + 默认种子 +
  懒迁移) + §四 (binding 引用校验 — 缺失 → 警告标注, 不崩溃) + §四b
  (生命周期 DRAFT→ACTIVE→DEPRECATED→ARCHIVED, archived 终态, enabled 独立
  运行开关 — ACTIVE+enabled 才可选)
- org/capabilities.py Task 002 Skill Registry 同构模式 (原子写/失败安全/种子)

覆盖 (org/capabilities.py — CapabilityRegistry agents 部分):
- 目录信源: register_agent → workspace/capabilities/agents/{id}.json (原子写);
  无 capabilities/ 目录 → 首次 register 创建 (懒迁移)
- CRUD: register_agent (upsert — 重复 id 覆盖) / get_agent (缺失 → None) /
  list_agents (enabled_only 过滤: 只返回 ACTIVE+enabled) / update_agent
  (部分字段更新, 缺失 → None) / delete_agent (缺失 → False, 幂等)
- Agent 字段: skill_bindings/workflow_bindings (CapabilityBinding 引用列表,
  dict 宽松解析) + llm_config (LLMConfig id 引用, 可空)
- 生命周期: transition_agent (受控单向, 落盘持久; 非法转换 ValueError 且
  不落盘; 缺失 → None)
- binding 校验: validate_agent_bindings — agent.skill_bindings 引用 registry
  中 skill (缺失 → 警告标注, 不崩溃; 空列表 = 全部解析)
- 失败安全: 损坏 JSON / 非法 schema → list 跳过 / get None (绝不崩溃)
- 默认种子: seed_defaults() 预置标准 AI 员工角色 (≥4: product-manager/
  architect/developer/qa/ui-designer — 各带 skill 绑定, 幂等不覆盖用户修改)

basename 全仓库唯一 (test_org_agent_registry — 注意: tests/agents/ 已有
test_agent_registry.py (旧 agents/registry.py), 同名模块会互相遮蔽, 故用
test_org_ 前缀); 不跨目录依赖 helper。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# noqa: E402 — tests/org/conftest.py 已挂 factory-org 到 sys.path (org 包父目录)
from org.capabilities import (  # noqa: E402
    Agent,
    BindingType,
    CapabilityRegistry,
    CapabilityState,
    Skill,
)


@pytest.fixture
def registry(tmp_path: Path) -> CapabilityRegistry:
    """独立工厂根 (<tmp>/factory → workspace/capabilities/agents/)。"""
    return CapabilityRegistry(tmp_path / "factory")


@pytest.fixture
def agents_dir(registry: CapabilityRegistry) -> Path:
    return registry.agents_dir


def make_agent(agent_id: str = "developer-agent", **overrides) -> Agent:
    """确定性 Agent 工厂 (显式 id, 断言友好; bindings dict 宽松解析)。"""
    data = {
        "id": agent_id,
        "name": f"Agent {agent_id}",
        "role": "developer",
        "description": "test agent",
        "skill_bindings": [{"type": "skill", "id": "backend-development"}],
        "workflow_bindings": [{"type": "workflow", "id": "software-development"}],
        "llm_config": "default-llm",
        "enabled": True,
        "state": "active",
    }
    data.update(overrides)
    return Agent.model_validate(data)


def make_skill(skill_id: str = "backend-development") -> None:
    """注册一个最小 Skill (binding 校验正向场景用)。"""
    pass  # placeholder 占位 — 实际注册在测试体内直接调用 registry


# ------------------------------------------------------------------ 目录信源


class TestRegistryDirSource:
    def test_register_agent_writes_json_file(
        self, registry: CapabilityRegistry, agents_dir: Path
    ):
        """register → workspace/capabilities/agents/{id}.json (目录信源)。"""
        registry.register_agent(make_agent("developer-agent"))
        path = agents_dir / "developer-agent.json"
        assert path.is_file()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["id"] == "developer-agent"
        assert data["name"] == "Agent developer-agent"
        assert data["role"] == "developer"
        assert data["skill_bindings"][0]["type"] == "skill"
        assert data["skill_bindings"][0]["id"] == "backend-development"
        assert data["workflow_bindings"] == [
            {"type": "workflow", "id": "software-development", "version": None}
        ]
        assert data["llm_config"] == "default-llm"
        assert data["state"] == "active"
        assert data["enabled"] is True

    def test_register_creates_agents_dir_lazily(
        self, registry: CapabilityRegistry, agents_dir: Path
    ):
        """懒迁移: 无 capabilities/ 目录 → 首次 register 创建 (不预先建目录)。"""
        assert not agents_dir.exists()
        registry.register_agent(make_agent("developer-agent"))
        assert agents_dir.is_dir()

    def test_register_duplicate_id_overwrites(
        self, registry: CapabilityRegistry, agents_dir: Path
    ):
        """重复 id → 覆盖 (单文件单实体, 同 Skill upsert 模式)。"""
        registry.register_agent(make_agent("developer-agent", name="v1"))
        registry.register_agent(make_agent("developer-agent", name="v2"))
        files = [p.name for p in agents_dir.iterdir() if p.is_file()]
        assert files == ["developer-agent.json"]  # 不产生多版本文件
        assert registry.get_agent("developer-agent").name == "v2"

    def test_register_illegal_id_rejected(self, registry: CapabilityRegistry):
        """id 含路径分隔符 → 拒绝 (防目录信源路径穿越)。"""
        with pytest.raises(ValueError):
            registry.register_agent(make_agent("../escape"))
        with pytest.raises(ValueError):
            registry.register_agent(make_agent("a/b"))

    def test_get_agent_roundtrip_full_fields(self, registry: CapabilityRegistry):
        """register → get 全字段往返 (bindings/llm_config/state 干净可复现)。"""
        original = make_agent(
            "developer-agent",
            name="Developer Agent",
            role="developer",
            description="开发工程师",
            skill_bindings=[
                {"type": "skill", "id": "backend-development"},
                {"type": "skill", "id": "frontend-development"},
            ],
            workflow_bindings=[],
            llm_config="",
            state="draft",
        )
        registry.register_agent(original)
        loaded = registry.get_agent("developer-agent")
        assert loaded is not None
        assert loaded.to_dict() == original.to_dict()

    def test_get_missing_returns_none(self, registry: CapabilityRegistry):
        """缺失 id → None (不是空实体)。"""
        assert registry.get_agent("no-such-agent") is None

    def test_get_after_delete_returns_none(self, registry: CapabilityRegistry):
        """删除后 get → None (目录信源一致)。"""
        registry.register_agent(make_agent("developer-agent"))
        registry.delete_agent("developer-agent")
        assert registry.get_agent("developer-agent") is None

    def test_list_agents_sorted_by_id(self, registry: CapabilityRegistry):
        """list 全部 agents, 按 id 排序 (确定性, 审计友好)。"""
        for agent_id in ("z-agent", "a-agent", "m-agent"):
            registry.register_agent(make_agent(agent_id))
        ids = [a.id for a in registry.list_agents()]
        assert ids == ["a-agent", "m-agent", "z-agent"]

    def test_list_agents_empty_when_no_files(self, registry: CapabilityRegistry):
        """无任何 agent → 空列表 (目录不存在也合法)。"""
        assert registry.list_agents() == []

    def test_delete_agent_removes_file(
        self, registry: CapabilityRegistry, agents_dir: Path
    ):
        """delete → 文件删除, 返回 True。"""
        registry.register_agent(make_agent("developer-agent"))
        assert registry.delete_agent("developer-agent") is True
        assert not (agents_dir / "developer-agent.json").exists()

    def test_delete_missing_returns_false(self, registry: CapabilityRegistry):
        """缺失 → False (幂等删除)。"""
        assert registry.delete_agent("no-such-agent") is False


# ------------------------------------------------------------------ update / bindings / llm_config


class TestRegistryUpdate:
    def test_update_agent_partial_fields(self, registry: CapabilityRegistry):
        """update: 部分字段更新, 其余保留 (bindings/llm_config 不动)。"""
        registry.register_agent(make_agent("developer-agent"))
        updated = registry.update_agent(
            "developer-agent", {"name": "Dev v2", "description": "新描述"}
        )
        assert updated is not None
        assert updated.name == "Dev v2"
        assert updated.description == "新描述"
        assert updated.role == "developer"  # 未动字段保留
        assert updated.llm_config == "default-llm"
        assert updated.state == CapabilityState.ACTIVE
        assert registry.get_agent("developer-agent").name == "Dev v2"  # 落盘

    def test_update_agent_llm_config(self, registry: CapabilityRegistry):
        """llm_config (LLMConfig id 引用) 可更新; 空串可空。"""
        registry.register_agent(make_agent("developer-agent", llm_config=""))
        updated = registry.update_agent("developer-agent", {"llm_config": "gpt-4o"})
        assert updated is not None
        assert updated.llm_config == "gpt-4o"
        assert registry.get_agent("developer-agent").llm_config == "gpt-4o"

    def test_update_agent_skill_bindings(self, registry: CapabilityRegistry):
        """skill_bindings 可整体替换 (dict 宽松解析 → CapabilityBinding)。"""
        registry.register_agent(make_agent("developer-agent"))
        updated = registry.update_agent(
            "developer-agent",
            {
                "skill_bindings": [
                    {"type": "skill", "id": "qa-testing"},
                    {"type": "skill", "id": "flutter-development"},
                ]
            },
        )
        assert updated is not None
        assert [b.id for b in updated.skill_bindings] == [
            "qa-testing",
            "flutter-development",
        ]
        assert [b.type for b in updated.skill_bindings] == [
            BindingType.SKILL,
            BindingType.SKILL,
        ]
        loaded = registry.get_agent("developer-agent")
        assert [b.id for b in loaded.skill_bindings] == [
            "qa-testing",
            "flutter-development",
        ]  # 落盘

    def test_update_agent_missing_returns_none(self, registry: CapabilityRegistry):
        """update 缺失 id → None (不创建幽灵实体)。"""
        assert registry.update_agent("no-such-agent", {"name": "x"}) is None

    def test_update_agent_invalid_state_rejected(self, registry: CapabilityRegistry):
        """update 非法 state → ValueError (pydantic 校验, 不落盘)。"""
        registry.register_agent(make_agent("developer-agent"))
        with pytest.raises(ValueError):
            registry.update_agent("developer-agent", {"state": "bogus"})
        assert registry.get_agent("developer-agent").state == CapabilityState.ACTIVE

    def test_update_agent_unknown_field_rejected(self, registry: CapabilityRegistry):
        """update 未知字段 → ValueError (extra=forbid, 不落盘)。"""
        registry.register_agent(make_agent("developer-agent"))
        with pytest.raises(ValueError):
            registry.update_agent("developer-agent", {"bogus_field": 1})


# ------------------------------------------------------------------ 生命周期 + enabled


class TestRegistryLifecycle:
    def test_transition_agent_persists(self, registry: CapabilityRegistry):
        """transition: DRAFT → ACTIVE 落盘 (get 重新加载为新状态)。"""
        registry.register_agent(make_agent("developer-agent", state="draft"))
        activated = registry.transition_agent("developer-agent", "active")
        assert activated is not None
        assert activated.state == CapabilityState.ACTIVE
        assert registry.get_agent("developer-agent").state == CapabilityState.ACTIVE

    def test_transition_full_chain(self, registry: CapabilityRegistry):
        """受控单向全链路: DRAFT→ACTIVE→DEPRECATED→ARCHIVED 逐步落盘。"""
        registry.register_agent(make_agent("developer-agent", state="draft"))
        for target in ("active", "deprecated", "archived"):
            agent = registry.transition_agent("developer-agent", target)
            assert agent is not None
            assert agent.state == CapabilityState.parse(target)
        assert (
            registry.get_agent("developer-agent").state == CapabilityState.ARCHIVED
        )

    def test_transition_illegal_raises_and_not_persisted(
        self, registry: CapabilityRegistry
    ):
        """非法转换 (跳级 DRAFT→ARCHIVED) → ValueError, 原文件保持原状态。"""
        registry.register_agent(make_agent("developer-agent", state="draft"))
        with pytest.raises(ValueError):
            registry.transition_agent("developer-agent", "archived")
        assert registry.get_agent("developer-agent").state == CapabilityState.DRAFT

    def test_transition_missing_returns_none(self, registry: CapabilityRegistry):
        """transition 缺失 id → None。"""
        assert registry.transition_agent("no-such-agent", "active") is None

    def test_list_agents_enabled_only_filters(self, registry: CapabilityRegistry):
        """enabled_only=True → 只返回 ACTIVE+enabled (DRAFT 与 ACTIVE+disabled 排除)。"""
        registry.register_agent(make_agent("active-on", state="active", enabled=True))
        registry.register_agent(make_agent("draft-agent", state="draft", enabled=True))
        registry.register_agent(make_agent("active-off", state="active", enabled=False))
        registry.register_agent(
            make_agent("deprecated-on", state="deprecated", enabled=True)
        )
        selectable = [a.id for a in registry.list_agents(enabled_only=True)]
        assert selectable == ["active-on"]

    def test_list_agents_all_includes_everything(self, registry: CapabilityRegistry):
        """enabled_only 缺省 False → 全部实体 (生命周期各态均在)。"""
        registry.register_agent(make_agent("active-on", state="active", enabled=True))
        registry.register_agent(make_agent("draft-agent", state="draft", enabled=True))
        assert {a.id for a in registry.list_agents()} == {
            "active-on",
            "draft-agent",
        }


# ------------------------------------------------------------------ 失败安全


class TestRegistryFailSafe:
    def test_corrupt_json_skipped_in_list(
        self, registry: CapabilityRegistry, agents_dir: Path
    ):
        """损坏 JSON 文件 → list 跳过 (不崩溃, 失败安全)。"""
        registry.register_agent(make_agent("good-agent"))
        (agents_dir / "corrupt.json").write_text("{ not valid json !!!", encoding="utf-8")
        ids = [a.id for a in registry.list_agents()]
        assert ids == ["good-agent"]  # 损坏文件静默跳过

    def test_corrupt_json_get_returns_none(
        self, registry: CapabilityRegistry, agents_dir: Path
    ):
        """损坏 JSON → get None (单实体失败安全, 不抛异常)。"""
        agents_dir.mkdir(parents=True)  # 懒迁移 — 手工构造损坏文件需先建目录
        (agents_dir / "corrupt.json").write_text("{ broken", encoding="utf-8")
        assert registry.get_agent("corrupt") is None

    def test_invalid_schema_json_skipped(
        self, registry: CapabilityRegistry, agents_dir: Path
    ):
        """JSON 合法但 schema 非法 (缺 id/name) → list 跳过 / get None。"""
        registry.register_agent(make_agent("good-agent"))
        (agents_dir / "bad-schema.json").write_text(
            json.dumps({"name": "no id here"}), encoding="utf-8"
        )
        (agents_dir / "not-dict.json").write_text("[1, 2, 3]", encoding="utf-8")
        ids = [a.id for a in registry.list_agents()]
        assert ids == ["good-agent"]
        assert registry.get_agent("bad-schema") is None
        assert registry.get_agent("not-dict") is None

    def test_atomic_write_no_tmp_leftover(
        self, registry: CapabilityRegistry, agents_dir: Path
    ):
        """原子写: 临时文件不残留 (写后目录只有 {id}.json)。"""
        registry.register_agent(make_agent("developer-agent"))
        registry.update_agent("developer-agent", {"name": "v1.1"})
        files = [p.name for p in agents_dir.iterdir() if p.is_file()]
        assert files == ["developer-agent.json"]


# ------------------------------------------------------------------ binding 校验 (缺失警告, 不崩溃)


class TestBindingValidation:
    def test_validate_agent_bindings_empty_when_all_resolve(
        self, registry: CapabilityRegistry
    ):
        """全部 skill 引用存在于 registry → 空警告列表。"""
        registry.register_agent(make_agent("developer-agent"))
        registry.register_skill(
            Skill.model_validate(
                {
                    "id": "backend-development",
                    "name": "Backend Development",
                    "state": "active",
                }
            )
        )
        assert registry.validate_agent_bindings("developer-agent") == []

    def test_validate_agent_bindings_missing_skill_warning(
        self, registry: CapabilityRegistry
    ):
        """skill_bindings 引用缺失 skill → 警告标注 (不崩溃, 不抛异常)。"""
        registry.register_agent(make_agent("developer-agent"))  # 绑定 ghost-skill
        warnings = registry.validate_agent_bindings("developer-agent")
        assert isinstance(warnings, list)
        assert len(warnings) == 1
        assert "backend-development" in warnings[0]
        assert "missing" in warnings[0]

    def test_validate_agent_bindings_no_bindings_empty(
        self, registry: CapabilityRegistry
    ):
        """无 skill 绑定 → 空警告列表 (可空字段合法)。"""
        registry.register_agent(
            make_agent("bare-agent", skill_bindings=[], workflow_bindings=[])
        )
        assert registry.validate_agent_bindings("bare-agent") == []

    def test_validate_agent_bindings_multiple_missing(
        self, registry: CapabilityRegistry
    ):
        """多个缺失引用 → 每条一个警告 (逐条标注; 已存在引用不警告)。"""
        registry.register_skill(
            Skill.model_validate(
                {
                    "id": "backend-development",
                    "name": "Backend Development",
                    "state": "active",
                }
            )
        )
        registry.register_agent(
            make_agent(
                "multi-agent",
                skill_bindings=[
                    {"type": "skill", "id": "ghost-a"},
                    {"type": "skill", "id": "ghost-b"},
                    {"type": "skill", "id": "backend-development"},
                ],
            )
        )
        warnings = registry.validate_agent_bindings("multi-agent")
        assert len(warnings) == 2
        assert any("ghost-a" in w for w in warnings)
        assert any("ghost-b" in w for w in warnings)

    def test_validate_agent_bindings_missing_agent_none(
        self, registry: CapabilityRegistry
    ):
        """校验缺失 agent → None (同 get_agent 语义)。"""
        assert registry.validate_agent_bindings("no-such-agent") is None

    def test_validate_agent_bindings_empty_registry_warns(
        self, registry: CapabilityRegistry
    ):
        """空 registry (无 skills 目录) + 有绑定 → 警告而非崩溃 (失败安全)。"""
        registry.register_agent(make_agent("developer-agent"))
        warnings = registry.validate_agent_bindings("developer-agent")
        assert len(warnings) == 1  # skills 目录不存在 → 引用一律缺失标注


# ------------------------------------------------------------------ 默认种子


class TestSeedDefaults:
    def test_seed_defaults_registers_standard_agents(self, registry: CapabilityRegistry):
        """默认种子: ≥4 标准 AI 员工角色 (product-manager/architect/developer/qa/ui)。"""
        count = registry.seed_defaults()
        assert count >= 4
        ids = {a.id for a in registry.list_agents()}
        assert {
            "product-manager-agent",
            "architect-agent",
            "developer-agent",
            "qa-agent",
            "ui-designer-agent",
        } <= ids

    def test_seed_defaults_agents_active_enabled(self, registry: CapabilityRegistry):
        """种子 agents ACTIVE+enabled → enabled_only list 全返回 (验收场景4)。"""
        registry.seed_defaults()
        all_agents = registry.list_agents()
        selectable = registry.list_agents(enabled_only=True)
        assert len(selectable) == len(all_agents) >= 4
        for agent in selectable:
            assert agent.state == CapabilityState.ACTIVE
            assert agent.enabled is True

    def test_seed_defaults_developer_binds_backend_and_frontend(
        self, registry: CapabilityRegistry
    ):
        """developer-agent 绑定 backend-development + frontend-development。"""
        registry.seed_defaults()
        dev = registry.get_agent("developer-agent")
        assert dev is not None
        skill_ids = {b.id for b in dev.skill_bindings}
        assert {"backend-development", "frontend-development"} <= skill_ids
        assert all(b.type == BindingType.SKILL for b in dev.skill_bindings)

    def test_seed_defaults_qa_binds_qa_testing(self, registry: CapabilityRegistry):
        """qa-agent 绑定 qa-testing。"""
        registry.seed_defaults()
        qa = registry.get_agent("qa-agent")
        assert qa is not None
        assert {b.id for b in qa.skill_bindings} == {"qa-testing"}

    def test_seed_defaults_pm_and_ui_bindings(self, registry: CapabilityRegistry):
        """pm 绑 product-management; ui-designer 绑 frontend-development。"""
        registry.seed_defaults()
        pm = registry.get_agent("product-manager-agent")
        assert pm is not None
        assert {b.id for b in pm.skill_bindings} == {"product-management"}
        ui = registry.get_agent("ui-designer-agent")
        assert ui is not None
        assert {b.id for b in ui.skill_bindings} == {"frontend-development"}

    def test_seed_defaults_agent_bindings_resolve(self, registry: CapabilityRegistry):
        """种子 agent 的 skill 引用全部解析 (skills+agents 同时种子, 零警告)。"""
        registry.seed_defaults()
        for agent in registry.list_agents():
            assert registry.validate_agent_bindings(agent.id) == []

    def test_seed_defaults_creates_files(self, registry: CapabilityRegistry, agents_dir: Path):
        """种子 agents 落盘为目录信源文件 (可被 get 读取)。"""
        registry.seed_defaults()
        assert (agents_dir / "developer-agent.json").is_file()
        seeded = registry.get_agent("developer-agent")
        assert seeded is not None
        assert seeded.state == CapabilityState.ACTIVE
        assert seeded.enabled is True

    def test_seed_defaults_idempotent_keeps_user_changes(
        self, registry: CapabilityRegistry
    ):
        """幂等: 已存在不覆盖 — 二次 seed 后用户修改保留 (agents 部分)。"""
        registry.seed_defaults()
        registry.update_agent("developer-agent", {"name": "Custom Dev"})
        second = registry.seed_defaults()
        assert second == 0  # 已全部存在 → 无新建
        assert registry.get_agent("developer-agent").name == "Custom Dev"

    def test_seed_defaults_does_not_touch_existing_dir(
        self, registry: CapabilityRegistry
    ):
        """已存在的同名自定义 agent → 种子不覆盖 (用户注册优先)。"""
        registry.register_agent(make_agent("developer-agent", name="My Own", role="custom"))
        registry.seed_defaults()
        assert registry.get_agent("developer-agent").name == "My Own"
        assert registry.get_agent("developer-agent").role == "custom"
