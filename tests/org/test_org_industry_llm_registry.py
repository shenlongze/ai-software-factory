"""tests/org/test_org_industry_llm_registry.py — S10-012 Task 006: Industry + LLM Config Registry (TDD)。

设计依据 (唯一):
- docs/sprint10/S10-012-architecture-design.md §二 (Industry: id/name/description/
  workflow_templates; LLMConfig: id/provider/model/endpoint/parameters) + §三
  (Registry 架构: 目录信源 workspace/capabilities/industries/{id}.json +
  llm-configs/{id}.json + CRUD + enabled 过滤 + 默认种子 + 懒迁移) + §四
  (引用校验 — 缺失 → 警告标注, 不崩溃) + §四b (生命周期 DRAFT→ACTIVE→
  DEPRECATED→ARCHIVED, archived 终态, enabled 独立运行开关 — ACTIVE+enabled
  才可选)
- Task 006 任务书: industries/ CRUD (workflow_templates 引用 + 种子 software
  绑 software-development-lifecycle workflow) + llm-configs/ CRUD
  (provider/model/endpoint/parameters + 种子 deepseek-default 无 key 明文)
  + 统一门面 get_capability/list_capabilities (供 Task 007 Dispatcher 集成)
- org/capabilities.py Task 002/003/004/005 Skill/Agent/MCP/Workflow Registry
  同构模式 (原子写/失败安全/懒迁移/生命周期/种子幂等)

覆盖 (org/capabilities.py — CapabilityRegistry industries + llm-configs 部分 +
统一门面):
- industries 目录信源: register_industry → workspace/capabilities/industries/
  {id}.json (原子写, 全字段 roundtrip); 懒迁移; 重复 id → 覆盖 (upsert)
- industries CRUD: register/get/list/update/delete + workflow_templates 引用
  (列表 roundtrip; 缺失 → validate_industry_refs 警告标注不崩溃) + 生命周期
  (transition_industry 受控单向, 落盘; 非法转换 ValueError 不落盘) +
  enabled_only 过滤
- llm-configs 目录信源: register_llm_config → workspace/capabilities/
  llm-configs/{id}.json; 懒迁移; 重复 id → 覆盖
- llm-configs CRUD: register/get/list/update/delete + provider/model/endpoint/
  parameters 字段 roundtrip + 生命周期 + enabled_only 过滤
- key 禁明文: LLMConfig 模型无 key 字段 (id/provider/model/endpoint/parameters/
  enabled/state); 种子 deepseek-default 文件内容不含任何 key/api_key 明文
- 统一门面: get_capability(kind, id) / list_capabilities(kind, enabled_only=)
  单入口跨类型查询 (skill/agent/mcp/workflow/industry/llm_config; 大小写不敏感,
  "-" → "_", 复数别名; 未知 kind → ValueError; 缺失 id → None)
- 默认种子: seed_defaults() 预置 industry software (ACTIVE+enabled, 绑
  software-development-lifecycle) + llm config deepseek-default
  (provider=deepseek, model=v4-pro 占位, endpoint 占位 — 不含真实 key);
  幂等不覆盖用户修改; 种子自洽 (validate_industry_refs 零警告)
- 失败安全: 损坏 JSON / 非法 schema → list 跳过 / get None (绝不崩溃)

basename 全仓库唯一 (test_org_industry_llm_registry); 不跨目录依赖 helper。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# noqa: E402 — tests/org/conftest.py 已挂 factory-org 到 sys.path (org 包父目录)
from org.capabilities import (  # noqa: E402
    Agent,
    CapabilityRegistry,
    CapabilityState,
    Industry,
    LLMConfig,
    MCP,
    Skill,
    WorkflowTemplate,
)

#: 种子 industry 标准 workflow 引用 (S10-012 §三: software 行业绑定 SDLC workflow)
SEED_WORKFLOW_REF = "software-development-lifecycle"


@pytest.fixture
def registry(tmp_path: Path) -> CapabilityRegistry:
    """独立工厂根 (<tmp>/factory → workspace/capabilities/industries|llm-configs/)。"""
    return CapabilityRegistry(tmp_path / "factory")


@pytest.fixture
def industries_dir(registry: CapabilityRegistry) -> Path:
    return registry.industries_dir


@pytest.fixture
def llm_configs_dir(registry: CapabilityRegistry) -> Path:
    return registry.llm_configs_dir


def make_industry(industry_id: str = "software", **overrides) -> Industry:
    """确定性 Industry 工厂 (显式 id, 断言友好; workflow_templates 引用列表)。"""
    data = {
        "id": industry_id,
        "name": f"Industry {industry_id}",
        "description": f"行业域 {industry_id} 描述",
        "workflow_templates": [SEED_WORKFLOW_REF],
        "enabled": True,
        "state": "active",
    }
    data.update(overrides)
    return Industry.model_validate(data)


def make_llm_config(config_id: str = "deepseek-default", **overrides) -> LLMConfig:
    """确定性 LLMConfig 工厂 (显式 id; provider/model/endpoint/parameters)。"""
    data = {
        "id": config_id,
        "provider": "deepseek",
        "model": "v4-pro",
        "endpoint": "https://api.deepseek.com/v1",
        "parameters": {"temperature": 0.7, "max_tokens": 4096},
        "enabled": True,
        "state": "active",
    }
    data.update(overrides)
    return LLMConfig.model_validate(data)


# ------------------------------------------------------------------ industries 目录信源


class TestIndustryRegistryDirSource:
    def test_register_industry_writes_json_file(
        self, registry: CapabilityRegistry, industries_dir: Path
    ):
        """register → workspace/capabilities/industries/{id}.json (目录信源)。"""
        registry.register_industry(make_industry("software"))
        path = industries_dir / "software.json"
        assert path.is_file()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["id"] == "software"
        assert data["name"] == "Industry software"
        assert data["description"] == "行业域 software 描述"
        assert data["workflow_templates"] == [SEED_WORKFLOW_REF]
        assert data["state"] == "active"
        assert data["enabled"] is True

    def test_register_creates_industries_dir_lazily(
        self, registry: CapabilityRegistry, industries_dir: Path
    ):
        """懒迁移: 无 capabilities/ 目录 → 首次 register 创建 (不预先建目录)。"""
        assert not industries_dir.exists()
        registry.register_industry(make_industry("software"))
        assert industries_dir.is_dir()

    def test_register_duplicate_id_overwrites(
        self, registry: CapabilityRegistry, industries_dir: Path
    ):
        """重复 id → 覆盖 (单文件单实体, 同 Skill/Agent/MCP upsert 模式)。"""
        registry.register_industry(make_industry("software", name="v1"))
        registry.register_industry(make_industry("software", name="v2"))
        files = [p.name for p in industries_dir.iterdir() if p.is_file()]
        assert files == ["software.json"]  # 不产生多版本文件
        assert registry.get_industry("software").name == "v2"

    def test_register_illegal_id_rejected(self, registry: CapabilityRegistry):
        """id 含路径分隔符 → 拒绝 (防目录信源路径穿越)。"""
        with pytest.raises(ValueError):
            registry.register_industry(make_industry("../escape"))
        with pytest.raises(ValueError):
            registry.register_industry(make_industry("a/b"))

    def test_register_empty_id_rejected(self, registry: CapabilityRegistry):
        """空 id → 拒绝 (非空字符串防御)。"""
        with pytest.raises(ValueError):
            registry.register_industry(make_industry(""))

    def test_get_industry_roundtrip_full_fields(self, registry: CapabilityRegistry):
        """register → get 全字段往返 (workflow_templates 干净可复现)。"""
        original = make_industry(
            "fintech",
            name="Fintech",
            description="金融科技行业",
            workflow_templates=["risk-compliance-workflow"],
            state="draft",
        )
        registry.register_industry(original)
        loaded = registry.get_industry("fintech")
        assert loaded is not None
        assert loaded.to_dict() == original.to_dict()

    def test_get_missing_returns_none(self, registry: CapabilityRegistry):
        """缺失 id → None (不是空实体)。"""
        assert registry.get_industry("no-such-industry") is None

    def test_get_after_delete_returns_none(self, registry: CapabilityRegistry):
        """删除后 get → None (目录信源一致)。"""
        registry.register_industry(make_industry("software"))
        registry.delete_industry("software")
        assert registry.get_industry("software") is None

    def test_list_industries_sorted_by_id(self, registry: CapabilityRegistry):
        """list 全部 industries, 按 id 排序 (确定性, 审计友好)。"""
        for ind_id in ("z-industry", "a-industry", "m-industry"):
            registry.register_industry(make_industry(ind_id))
        ids = [i.id for i in registry.list_industries()]
        assert ids == ["a-industry", "m-industry", "z-industry"]

    def test_list_industries_empty_when_no_files(self, registry: CapabilityRegistry):
        """无任何 industry → 空列表 (目录不存在也合法)。"""
        assert registry.list_industries() == []

    def test_delete_industry_removes_file(
        self, registry: CapabilityRegistry, industries_dir: Path
    ):
        """delete → 文件删除, 返回 True。"""
        registry.register_industry(make_industry("software"))
        assert registry.delete_industry("software") is True
        assert not (industries_dir / "software.json").exists()

    def test_delete_missing_returns_false(self, registry: CapabilityRegistry):
        """缺失 → False (幂等删除)。"""
        assert registry.delete_industry("no-such-industry") is False


# ------------------------------------------------------------------ Industry 字段 (workflow_templates 引用)


class TestIndustryFields:
    def test_workflow_templates_roundtrip(self, registry: CapabilityRegistry):
        """workflow_templates 引用列表 roundtrip 可复现 (顺序保持)。"""
        registry.register_industry(
            make_industry(
                "software",
                workflow_templates=[
                    "software-development-lifecycle",
                    "release-pipeline",
                ],
            )
        )
        loaded = registry.get_industry("software")
        assert loaded is not None
        assert loaded.workflow_templates == [
            "software-development-lifecycle",
            "release-pipeline",
        ]

    def test_workflow_templates_empty_allowed(self, registry: CapabilityRegistry):
        """空 workflow_templates 合法 (行业域可暂未挂任何模板)。"""
        registry.register_industry(make_industry("bare", workflow_templates=[]))
        loaded = registry.get_industry("bare")
        assert loaded is not None
        assert loaded.workflow_templates == []

    def test_workflow_templates_none_coerced_to_empty(self, registry: CapabilityRegistry):
        """workflow_templates=None 输入 → 归一为空列表 (宽松解析, 不崩溃)。"""
        registry.register_industry(make_industry("null-templates", workflow_templates=None))
        loaded = registry.get_industry("null-templates")
        assert loaded is not None
        assert loaded.workflow_templates == []

    def test_register_missing_template_ref_not_rejected(
        self, registry: CapabilityRegistry
    ):
        """注册时引用缺失不拒绝 (懒校验 — 引用校验独立于 CRUD, 缺失只是警告)。"""
        # "no-such-workflow" 未注册 → register 仍成功 (不抛异常)
        industry = registry.register_industry(
            make_industry("ghost-ref", workflow_templates=["no-such-workflow"])
        )
        assert industry is not None
        assert registry.get_industry("ghost-ref").workflow_templates == ["no-such-workflow"]


# ------------------------------------------------------------------ industries update


class TestIndustryRegistryUpdate:
    def test_update_industry_partial_fields(self, registry: CapabilityRegistry):
        """update: 部分字段更新, 其余保留 (workflow_templates 不动)。"""
        registry.register_industry(make_industry("software"))
        updated = registry.update_industry("software", {"name": "Software Dev v2"})
        assert updated is not None
        assert updated.name == "Software Dev v2"
        assert updated.description == "行业域 software 描述"  # 未动字段保留
        assert updated.workflow_templates == [SEED_WORKFLOW_REF]
        assert registry.get_industry("software").name == "Software Dev v2"  # 落盘

    def test_update_industry_workflow_templates(self, registry: CapabilityRegistry):
        """workflow_templates 可整体替换 (重新绑定模板集)。"""
        registry.register_industry(make_industry("software"))
        updated = registry.update_industry(
            "software", {"workflow_templates": ["release-pipeline"]}
        )
        assert updated is not None
        assert updated.workflow_templates == ["release-pipeline"]
        loaded = registry.get_industry("software")
        assert loaded.workflow_templates == ["release-pipeline"]  # 落盘

    def test_update_industry_description(self, registry: CapabilityRegistry):
        """description 可更新。"""
        registry.register_industry(make_industry("software"))
        updated = registry.update_industry("software", {"description": "新描述"})
        assert updated is not None
        assert updated.description == "新描述"

    def test_update_industry_missing_returns_none(self, registry: CapabilityRegistry):
        """update 缺失 id → None (不创建幽灵实体)。"""
        assert registry.update_industry("no-such-industry", {"name": "x"}) is None

    def test_update_industry_invalid_state_rejected(self, registry: CapabilityRegistry):
        """update 非法 state → ValueError (pydantic 校验, 不落盘)。"""
        registry.register_industry(make_industry("software"))
        with pytest.raises(ValueError):
            registry.update_industry("software", {"state": "bogus"})
        assert (
            registry.get_industry("software").state == CapabilityState.ACTIVE
        )

    def test_update_industry_unknown_field_rejected(self, registry: CapabilityRegistry):
        """update 未知字段 → ValueError (extra=forbid, 不落盘)。"""
        registry.register_industry(make_industry("software"))
        with pytest.raises(ValueError):
            registry.update_industry("software", {"bogus_field": 1})


# ------------------------------------------------------------------ industries 生命周期 + enabled


class TestIndustryRegistryLifecycle:
    def test_transition_industry_persists(self, registry: CapabilityRegistry):
        """transition: DRAFT → ACTIVE 落盘 (get 重新加载为新状态)。"""
        registry.register_industry(make_industry("software", state="draft"))
        activated = registry.transition_industry("software", "active")
        assert activated is not None
        assert activated.state == CapabilityState.ACTIVE
        assert (
            registry.get_industry("software").state == CapabilityState.ACTIVE
        )

    def test_transition_full_chain(self, registry: CapabilityRegistry):
        """受控单向全链路: DRAFT→ACTIVE→DEPRECATED→ARCHIVED 逐步落盘。"""
        registry.register_industry(make_industry("software", state="draft"))
        for target in ("active", "deprecated", "archived"):
            ind = registry.transition_industry("software", target)
            assert ind is not None
            assert ind.state == CapabilityState.parse(target)
        assert (
            registry.get_industry("software").state == CapabilityState.ARCHIVED
        )

    def test_transition_illegal_raises_and_not_persisted(
        self, registry: CapabilityRegistry
    ):
        """非法转换 (跳级 DRAFT→ARCHIVED) → ValueError, 原文件保持原状态。"""
        registry.register_industry(make_industry("software", state="draft"))
        with pytest.raises(ValueError):
            registry.transition_industry("software", "archived")
        assert (
            registry.get_industry("software").state == CapabilityState.DRAFT
        )

    def test_transition_missing_returns_none(self, registry: CapabilityRegistry):
        """transition 缺失 id → None。"""
        assert registry.transition_industry("no-such-industry", "active") is None

    def test_list_industries_enabled_only_filters(self, registry: CapabilityRegistry):
        """enabled_only=True → 只返回 ACTIVE+enabled (DRAFT 与 ACTIVE+disabled 排除)。"""
        registry.register_industry(make_industry("active-on", state="active", enabled=True))
        registry.register_industry(make_industry("draft-ind", state="draft", enabled=True))
        registry.register_industry(make_industry("active-off", state="active", enabled=False))
        registry.register_industry(
            make_industry("deprecated-on", state="deprecated", enabled=True)
        )
        selectable = [i.id for i in registry.list_industries(enabled_only=True)]
        assert selectable == ["active-on"]

    def test_list_industries_all_includes_everything(self, registry: CapabilityRegistry):
        """enabled_only 缺省 False → 全部实体 (生命周期各态均在)。"""
        registry.register_industry(make_industry("active-on", state="active", enabled=True))
        registry.register_industry(make_industry("draft-ind", state="draft", enabled=True))
        assert {i.id for i in registry.list_industries()} == {
            "active-on",
            "draft-ind",
        }


# ------------------------------------------------------------------ industries 引用校验 (workflow_templates)


class TestIndustryRefValidation:
    def test_validate_industry_refs_empty_when_all_resolve(
        self, registry: CapabilityRegistry
    ):
        """workflow_templates 全部存在于 registry → 空警告列表。"""
        registry.register_industry(make_industry("software"))
        registry.register_workflow(
            WorkflowTemplate.model_validate(
                {
                    "id": SEED_WORKFLOW_REF,
                    "name": "SDLC",
                    "steps": [{"id": "plan", "name": "Plan"}],
                    "state": "active",
                }
            )
        )
        assert registry.validate_industry_refs("software") == []

    def test_validate_industry_refs_missing_warnings(
        self, registry: CapabilityRegistry
    ):
        """workflow_templates 引用缺失 → 警告标注 (不崩溃, 不抛异常)。"""
        registry.register_industry(make_industry("software"))
        warnings = registry.validate_industry_refs("software")
        assert isinstance(warnings, list)
        assert len(warnings) == 1
        assert "software-development-lifecycle" in warnings[0]
        assert "missing" in warnings[0]

    def test_validate_industry_refs_partial_missing(self, registry: CapabilityRegistry):
        """部分缺失 → 只警告缺失项 (已存在引用不警告)。"""
        registry.register_industry(
            make_industry(
                "software",
                workflow_templates=[SEED_WORKFLOW_REF, "release-pipeline"],
            )
        )
        registry.register_workflow(
            WorkflowTemplate.model_validate(
                {
                    "id": SEED_WORKFLOW_REF,
                    "name": "SDLC",
                    "steps": [{"id": "plan", "name": "Plan"}],
                    "state": "active",
                }
            )
        )
        warnings = registry.validate_industry_refs("software")
        assert len(warnings) == 1
        assert "release-pipeline" in warnings[0]
        assert SEED_WORKFLOW_REF not in warnings[0]  # 已存在 → 不警告

    def test_validate_industry_refs_empty_lists_no_warnings(
        self, registry: CapabilityRegistry
    ):
        """无 workflow_templates → 空警告 (可空字段合法)。"""
        registry.register_industry(make_industry("bare", workflow_templates=[]))
        assert registry.validate_industry_refs("bare") == []

    def test_validate_industry_refs_missing_industry_none(
        self, registry: CapabilityRegistry
    ):
        """校验缺失 industry → None (同 get_industry 语义)。"""
        assert registry.validate_industry_refs("no-such-industry") is None


# ------------------------------------------------------------------ llm-configs 目录信源


class TestLLMConfigRegistryDirSource:
    def test_register_llm_config_writes_json_file(
        self, registry: CapabilityRegistry, llm_configs_dir: Path
    ):
        """register → workspace/capabilities/llm-configs/{id}.json (目录信源)。"""
        registry.register_llm_config(make_llm_config("deepseek-default"))
        path = llm_configs_dir / "deepseek-default.json"
        assert path.is_file()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["id"] == "deepseek-default"
        assert data["provider"] == "deepseek"
        assert data["model"] == "v4-pro"
        assert data["endpoint"] == "https://api.deepseek.com/v1"
        assert data["parameters"] == {"temperature": 0.7, "max_tokens": 4096}
        assert data["state"] == "active"
        assert data["enabled"] is True

    def test_register_creates_llm_configs_dir_lazily(
        self, registry: CapabilityRegistry, llm_configs_dir: Path
    ):
        """懒迁移: 无 capabilities/ 目录 → 首次 register 创建 (不预先建目录)。"""
        assert not llm_configs_dir.exists()
        registry.register_llm_config(make_llm_config("deepseek-default"))
        assert llm_configs_dir.is_dir()

    def test_register_duplicate_id_overwrites(
        self, registry: CapabilityRegistry, llm_configs_dir: Path
    ):
        """重复 id → 覆盖 (单文件单实体, 同 Skill/Agent/MCP upsert 模式)。"""
        registry.register_llm_config(make_llm_config("deepseek-default", model="v1"))
        registry.register_llm_config(make_llm_config("deepseek-default", model="v2"))
        files = [p.name for p in llm_configs_dir.iterdir() if p.is_file()]
        assert files == ["deepseek-default.json"]  # 不产生多版本文件
        assert registry.get_llm_config("deepseek-default").model == "v2"

    def test_register_illegal_id_rejected(self, registry: CapabilityRegistry):
        """id 含路径分隔符 → 拒绝 (防目录信源路径穿越)。"""
        with pytest.raises(ValueError):
            registry.register_llm_config(make_llm_config("../escape"))
        with pytest.raises(ValueError):
            registry.register_llm_config(make_llm_config("a/b"))

    def test_register_empty_id_rejected(self, registry: CapabilityRegistry):
        """空 id → 拒绝 (非空字符串防御)。"""
        with pytest.raises(ValueError):
            registry.register_llm_config(make_llm_config(""))

    def test_get_llm_config_roundtrip_full_fields(self, registry: CapabilityRegistry):
        """register → get 全字段往返 (provider/model/endpoint/parameters 干净可复现)。"""
        original = make_llm_config(
            "custom-config",
            provider="anthropic",
            model="claude-3.5-sonnet",
            endpoint="https://api.anthropic.com/v1",
            parameters={"temperature": 0.2},
            state="draft",
        )
        registry.register_llm_config(original)
        loaded = registry.get_llm_config("custom-config")
        assert loaded is not None
        assert loaded.to_dict() == original.to_dict()

    def test_get_missing_returns_none(self, registry: CapabilityRegistry):
        """缺失 id → None (不是空实体)。"""
        assert registry.get_llm_config("no-such-config") is None

    def test_get_after_delete_returns_none(self, registry: CapabilityRegistry):
        """删除后 get → None (目录信源一致)。"""
        registry.register_llm_config(make_llm_config("deepseek-default"))
        registry.delete_llm_config("deepseek-default")
        assert registry.get_llm_config("deepseek-default") is None

    def test_list_llm_configs_sorted_by_id(self, registry: CapabilityRegistry):
        """list 全部 llm configs, 按 id 排序 (确定性, 审计友好)。"""
        for cfg_id in ("z-config", "a-config", "m-config"):
            registry.register_llm_config(make_llm_config(cfg_id))
        ids = [c.id for c in registry.list_llm_configs()]
        assert ids == ["a-config", "m-config", "z-config"]

    def test_list_llm_configs_empty_when_no_files(self, registry: CapabilityRegistry):
        """无任何 llm config → 空列表 (目录不存在也合法)。"""
        assert registry.list_llm_configs() == []

    def test_delete_llm_config_removes_file(
        self, registry: CapabilityRegistry, llm_configs_dir: Path
    ):
        """delete → 文件删除, 返回 True。"""
        registry.register_llm_config(make_llm_config("deepseek-default"))
        assert registry.delete_llm_config("deepseek-default") is True
        assert not (llm_configs_dir / "deepseek-default.json").exists()

    def test_delete_missing_returns_false(self, registry: CapabilityRegistry):
        """缺失 → False (幂等删除)。"""
        assert registry.delete_llm_config("no-such-config") is False


# ------------------------------------------------------------------ LLMConfig 字段 (provider/model/endpoint/parameters)


class TestLLMConfigFields:
    def test_provider_model_endpoint_roundtrip(self, registry: CapabilityRegistry):
        """provider/model/endpoint 字符串字段 roundtrip 可复现。"""
        registry.register_llm_config(
            make_llm_config(
                "openai-default",
                provider="openai",
                model="gpt-4o",
                endpoint="https://api.openai.com/v1",
            )
        )
        loaded = registry.get_llm_config("openai-default")
        assert loaded is not None
        assert loaded.provider == "openai"
        assert loaded.model == "gpt-4o"
        assert loaded.endpoint == "https://api.openai.com/v1"

    def test_parameters_roundtrip(self, registry: CapabilityRegistry):
        """parameters dict roundtrip 可复现 (provider 参数透传)。"""
        params = {"temperature": 0.1, "max_tokens": 2048, "top_p": 0.9}
        registry.register_llm_config(make_llm_config("params-cfg", parameters=params))
        loaded = registry.get_llm_config("params-cfg")
        assert loaded is not None
        assert loaded.parameters == params

    def test_parameters_empty_default(self, registry: CapabilityRegistry):
        """parameters 缺省 → {} (可空 dict, 无参数配置合法)。"""
        registry.register_llm_config(make_llm_config("bare-cfg", parameters=None))
        loaded = registry.get_llm_config("bare-cfg")
        assert loaded is not None
        assert loaded.parameters == {}

    def test_config_has_no_key_field(self, registry: CapabilityRegistry):
        """LLMConfig 模型无 key 字段 — 模型层禁明文凭据 (id/provider/model/
        endpoint/parameters/enabled/state 六字段 + 生命周期)。"""
        registry.register_llm_config(make_llm_config("deepseek-default"))
        data = json.loads(
            (registry.llm_configs_dir / "deepseek-default.json").read_text(
                encoding="utf-8"
            )
        )
        assert "api_key" not in data
        assert "key" not in data
        assert "secret" not in data
        assert "token" not in data


# ------------------------------------------------------------------ llm-configs update


class TestLLMConfigRegistryUpdate:
    def test_update_llm_config_partial_fields(self, registry: CapabilityRegistry):
        """update: 部分字段更新, 其余保留 (provider/endpoint 不动)。"""
        registry.register_llm_config(make_llm_config("deepseek-default"))
        updated = registry.update_llm_config(
            "deepseek-default", {"model": "v4-pro-0325"}
        )
        assert updated is not None
        assert updated.model == "v4-pro-0325"
        assert updated.provider == "deepseek"  # 未动字段保留
        assert updated.endpoint == "https://api.deepseek.com/v1"
        assert registry.get_llm_config("deepseek-default").model == "v4-pro-0325"  # 落盘

    def test_update_llm_config_provider_endpoint(self, registry: CapabilityRegistry):
        """provider/endpoint 可整体替换 (切换供应商)。"""
        registry.register_llm_config(make_llm_config("deepseek-default"))
        updated = registry.update_llm_config(
            "deepseek-default",
            {"provider": "openai", "endpoint": "https://api.openai.com/v1"},
        )
        assert updated is not None
        assert updated.provider == "openai"
        assert updated.endpoint == "https://api.openai.com/v1"
        loaded = registry.get_llm_config("deepseek-default")
        assert loaded.provider == "openai"  # 落盘

    def test_update_llm_config_parameters(self, registry: CapabilityRegistry):
        """parameters 可整体替换。"""
        registry.register_llm_config(make_llm_config("deepseek-default"))
        updated = registry.update_llm_config(
            "deepseek-default", {"parameters": {"temperature": 0.0}}
        )
        assert updated is not None
        assert updated.parameters == {"temperature": 0.0}

    def test_update_llm_config_missing_returns_none(self, registry: CapabilityRegistry):
        """update 缺失 id → None (不创建幽灵实体)。"""
        assert registry.update_llm_config("no-such-config", {"model": "x"}) is None

    def test_update_llm_config_invalid_state_rejected(
        self, registry: CapabilityRegistry
    ):
        """update 非法 state → ValueError (pydantic 校验, 不落盘)。"""
        registry.register_llm_config(make_llm_config("deepseek-default"))
        with pytest.raises(ValueError):
            registry.update_llm_config("deepseek-default", {"state": "bogus"})
        assert (
            registry.get_llm_config("deepseek-default").state
            == CapabilityState.ACTIVE
        )

    def test_update_llm_config_unknown_field_rejected(
        self, registry: CapabilityRegistry
    ):
        """update 未知字段 (如 api_key) → ValueError (extra=forbid, 不落盘 —
        禁明文凭据字段进入配置)。"""
        registry.register_llm_config(make_llm_config("deepseek-default"))
        with pytest.raises(ValueError):
            registry.update_llm_config("deepseek-default", {"api_key": "sk-123"})
        data = json.loads(
            (registry.llm_configs_dir / "deepseek-default.json").read_text(
                encoding="utf-8"
            )
        )
        assert "api_key" not in data  # 不落盘, 原文件无 key


# ------------------------------------------------------------------ llm-configs 生命周期 + enabled


class TestLLMConfigRegistryLifecycle:
    def test_transition_llm_config_persists(self, registry: CapabilityRegistry):
        """transition: DRAFT → ACTIVE 落盘 (get 重新加载为新状态)。"""
        registry.register_llm_config(make_llm_config("deepseek-default", state="draft"))
        activated = registry.transition_llm_config("deepseek-default", "active")
        assert activated is not None
        assert activated.state == CapabilityState.ACTIVE
        assert (
            registry.get_llm_config("deepseek-default").state
            == CapabilityState.ACTIVE
        )

    def test_transition_full_chain(self, registry: CapabilityRegistry):
        """受控单向全链路: DRAFT→ACTIVE→DEPRECATED→ARCHIVED 逐步落盘。"""
        registry.register_llm_config(make_llm_config("deepseek-default", state="draft"))
        for target in ("active", "deprecated", "archived"):
            cfg = registry.transition_llm_config("deepseek-default", target)
            assert cfg is not None
            assert cfg.state == CapabilityState.parse(target)
        assert (
            registry.get_llm_config("deepseek-default").state
            == CapabilityState.ARCHIVED
        )

    def test_transition_illegal_raises_and_not_persisted(
        self, registry: CapabilityRegistry
    ):
        """非法转换 (跳级 DRAFT→ARCHIVED) → ValueError, 原文件保持原状态。"""
        registry.register_llm_config(make_llm_config("deepseek-default", state="draft"))
        with pytest.raises(ValueError):
            registry.transition_llm_config("deepseek-default", "archived")
        assert (
            registry.get_llm_config("deepseek-default").state
            == CapabilityState.DRAFT
        )

    def test_transition_missing_returns_none(self, registry: CapabilityRegistry):
        """transition 缺失 id → None。"""
        assert registry.transition_llm_config("no-such-config", "active") is None

    def test_list_llm_configs_enabled_only_filters(
        self, registry: CapabilityRegistry
    ):
        """enabled_only=True → 只返回 ACTIVE+enabled (DRAFT 与 ACTIVE+disabled 排除)。"""
        registry.register_llm_config(make_llm_config("active-on", state="active", enabled=True))
        registry.register_llm_config(make_llm_config("draft-cfg", state="draft", enabled=True))
        registry.register_llm_config(make_llm_config("active-off", state="active", enabled=False))
        registry.register_llm_config(
            make_llm_config("deprecated-on", state="deprecated", enabled=True)
        )
        selectable = [c.id for c in registry.list_llm_configs(enabled_only=True)]
        assert selectable == ["active-on"]

    def test_list_llm_configs_all_includes_everything(
        self, registry: CapabilityRegistry
    ):
        """enabled_only 缺省 False → 全部实体 (生命周期各态均在)。"""
        registry.register_llm_config(make_llm_config("active-on", state="active", enabled=True))
        registry.register_llm_config(make_llm_config("draft-cfg", state="draft", enabled=True))
        assert {c.id for c in registry.list_llm_configs()} == {
            "active-on",
            "draft-cfg",
        }


# ------------------------------------------------------------------ 失败安全 (industries + llm-configs)


class TestIndustryLLMRegistryFailSafe:
    def test_corrupt_industry_json_skipped_in_list(
        self, registry: CapabilityRegistry, industries_dir: Path
    ):
        """损坏 industry JSON 文件 → list 跳过 (不崩溃, 失败安全)。"""
        registry.register_industry(make_industry("good-industry"))
        (industries_dir / "corrupt.json").write_text(
            "{ not valid json !!!", encoding="utf-8"
        )
        ids = [i.id for i in registry.list_industries()]
        assert ids == ["good-industry"]  # 损坏文件静默跳过

    def test_corrupt_industry_json_get_returns_none(
        self, registry: CapabilityRegistry, industries_dir: Path
    ):
        """损坏 JSON → get None (单实体失败安全, 不抛异常)。"""
        industries_dir.mkdir(parents=True)  # 懒迁移 — 手工构造损坏文件需先建目录
        (industries_dir / "corrupt.json").write_text("{ broken", encoding="utf-8")
        assert registry.get_industry("corrupt") is None

    def test_invalid_schema_industry_skipped(
        self, registry: CapabilityRegistry, industries_dir: Path
    ):
        """JSON 合法但 schema 非法 (缺 id/name) → list 跳过 / get None。"""
        registry.register_industry(make_industry("good-industry"))
        (industries_dir / "bad-schema.json").write_text(
            json.dumps({"name": "no id here"}), encoding="utf-8"
        )
        (industries_dir / "not-dict.json").write_text("[1, 2, 3]", encoding="utf-8")
        ids = [i.id for i in registry.list_industries()]
        assert ids == ["good-industry"]
        assert registry.get_industry("bad-schema") is None
        assert registry.get_industry("not-dict") is None

    def test_corrupt_llm_config_json_skipped_in_list(
        self, registry: CapabilityRegistry, llm_configs_dir: Path
    ):
        """损坏 llm-config JSON 文件 → list 跳过 (不崩溃, 失败安全)。"""
        registry.register_llm_config(make_llm_config("good-config"))
        (llm_configs_dir / "corrupt.json").write_text(
            "{ not valid json !!!", encoding="utf-8"
        )
        ids = [c.id for c in registry.list_llm_configs()]
        assert ids == ["good-config"]  # 损坏文件静默跳过

    def test_corrupt_llm_config_json_get_returns_none(
        self, registry: CapabilityRegistry, llm_configs_dir: Path
    ):
        """损坏 JSON → get None (单实体失败安全, 不抛异常)。"""
        llm_configs_dir.mkdir(parents=True)
        (llm_configs_dir / "corrupt.json").write_text("{ broken", encoding="utf-8")
        assert registry.get_llm_config("corrupt") is None

    def test_invalid_schema_llm_config_skipped(
        self, registry: CapabilityRegistry, llm_configs_dir: Path
    ):
        """JSON 合法但 schema 非法 (缺 id/name) → list 跳过 / get None。"""
        registry.register_llm_config(make_llm_config("good-config"))
        (llm_configs_dir / "bad-schema.json").write_text(
            json.dumps({"provider": "no id here"}), encoding="utf-8"
        )
        (llm_configs_dir / "not-dict.json").write_text("[1, 2, 3]", encoding="utf-8")
        ids = [c.id for c in registry.list_llm_configs()]
        assert ids == ["good-config"]
        assert registry.get_llm_config("bad-schema") is None
        assert registry.get_llm_config("not-dict") is None

    def test_atomic_write_no_tmp_leftover(
        self, registry: CapabilityRegistry, industries_dir: Path, llm_configs_dir: Path
    ):
        """原子写: 临时文件不残留 (写后目录只有 {id}.json)。"""
        registry.register_industry(make_industry("software"))
        registry.update_industry("software", {"name": "v1.1"})
        registry.register_llm_config(make_llm_config("deepseek-default"))
        registry.update_llm_config("deepseek-default", {"model": "v1.1"})
        ind_files = [p.name for p in industries_dir.iterdir() if p.is_file()]
        cfg_files = [p.name for p in llm_configs_dir.iterdir() if p.is_file()]
        assert ind_files == ["software.json"]
        assert cfg_files == ["deepseek-default.json"]


# ------------------------------------------------------------------ 统一门面 get_capability / list_capabilities


class TestCapabilityFacade:
    def test_get_capability_industry(self, registry: CapabilityRegistry):
        """get_capability('industry', id) → Industry 实体 (Task 007 集成入口)。"""
        registry.register_industry(make_industry("software"))
        cap = registry.get_capability("industry", "software")
        assert isinstance(cap, Industry)
        assert cap.id == "software"
        assert cap.workflow_templates == [SEED_WORKFLOW_REF]

    def test_get_capability_llm_config(self, registry: CapabilityRegistry):
        """get_capability('llm_config', id) → LLMConfig 实体。"""
        registry.register_llm_config(make_llm_config("deepseek-default"))
        cap = registry.get_capability("llm_config", "deepseek-default")
        assert isinstance(cap, LLMConfig)
        assert cap.provider == "deepseek"

    def test_get_capability_kind_aliases(self, registry: CapabilityRegistry):
        """kind 别名: 复数/大小写/连字符 → 归一 (industries → industry,
        LLM-CONFIG → llm_config)。"""
        registry.register_industry(make_industry("software"))
        registry.register_llm_config(make_llm_config("deepseek-default"))
        assert isinstance(
            registry.get_capability("industries", "software"), Industry
        )
        assert isinstance(
            registry.get_capability("LLM-CONFIG", "deepseek-default"), LLMConfig
        )
        assert isinstance(
            registry.get_capability("llm-configs", "deepseek-default"), LLMConfig
        )

    def test_get_capability_cross_kind_after_seed(self, registry: CapabilityRegistry):
        """跨类型单入口: seed 后 skill/agent/workflow 均经同一门面查询。"""
        registry.seed_defaults()
        assert isinstance(
            registry.get_capability("skill", "backend-development"), Skill
        )
        assert isinstance(
            registry.get_capability("agent", "developer-agent"), Agent
        )
        assert isinstance(
            registry.get_capability("workflow", "software-development-lifecycle"),
            WorkflowTemplate,
        )

    def test_get_capability_mcp(self, registry: CapabilityRegistry):
        """get_capability('mcp', id) → MCP 实体 (门面覆盖全部六类)。"""
        registry.register_mcp(
            MCP.model_validate(
                {"id": "filesystem-mcp", "name": "FS", "type": "stdio"}
            )
        )
        cap = registry.get_capability("mcp", "filesystem-mcp")
        assert isinstance(cap, MCP)
        assert cap.type == "stdio"

    def test_get_capability_missing_returns_none(self, registry: CapabilityRegistry):
        """缺失 id → None (跨类型统一缺失语义)。"""
        assert registry.get_capability("industry", "no-such") is None
        assert registry.get_capability("llm_config", "no-such") is None
        assert registry.get_capability("skill", "no-such") is None

    def test_get_capability_unknown_kind_raises(self, registry: CapabilityRegistry):
        """未知 kind → ValueError (不静默返回 None — 拼写错误显式暴露)。"""
        with pytest.raises(ValueError):
            registry.get_capability("bogus-kind", "software")

    def test_list_capabilities_industry(self, registry: CapabilityRegistry):
        """list_capabilities('industry') → 全部 industries (按 id 排序)。"""
        for ind_id in ("z-industry", "a-industry"):
            registry.register_industry(make_industry(ind_id))
        caps = registry.list_capabilities("industry")
        assert [c.id for c in caps] == ["a-industry", "z-industry"]

    def test_list_capabilities_llm_config_enabled_only(
        self, registry: CapabilityRegistry
    ):
        """list_capabilities('llm_config', enabled_only=True) → ACTIVE+enabled 过滤。"""
        registry.register_llm_config(make_llm_config("active-on", state="active", enabled=True))
        registry.register_llm_config(make_llm_config("draft-cfg", state="draft", enabled=True))
        ids = [c.id for c in registry.list_capabilities("llm_config", enabled_only=True)]
        assert ids == ["active-on"]

    def test_list_capabilities_cross_kind_after_seed(
        self, registry: CapabilityRegistry
    ):
        """跨类型: seed 后 list skill/agent/workflow/industry/llm_config 同一门面。"""
        registry.seed_defaults()
        assert "backend-development" in [
            s.id for s in registry.list_capabilities("skill")
        ]
        assert "developer-agent" in [
            a.id for a in registry.list_capabilities("agents")
        ]
        assert "software-development-lifecycle" in [
            w.id for w in registry.list_capabilities("workflows")
        ]
        assert "software" in [i.id for i in registry.list_capabilities("industries")]
        assert "deepseek-default" in [
            c.id for c in registry.list_capabilities("llm-config")
        ]

    def test_list_capabilities_unknown_kind_raises(self, registry: CapabilityRegistry):
        """未知 kind → ValueError (统一门面显式拒绝)。"""
        with pytest.raises(ValueError):
            registry.list_capabilities("bogus-kind")


# ------------------------------------------------------------------ 默认种子 (software + deepseek-default)


class TestRegistrySeed:
    def test_seed_industry_software(self, registry: CapabilityRegistry):
        """默认种子: industry software (验收场景4 — 行业域存在)。"""
        count = registry.seed_defaults()
        assert count >= 1
        seeded = registry.get_industry("software")
        assert seeded is not None
        assert seeded.name == "Software Development"
        assert seeded.state == CapabilityState.ACTIVE
        assert seeded.enabled is True

    def test_seed_industry_binds_sdlc_workflow(self, registry: CapabilityRegistry):
        """种子 software 绑定 software-development-lifecycle workflow 引用。"""
        registry.seed_defaults()
        seeded = registry.get_industry("software")
        assert seeded is not None
        assert seeded.workflow_templates == [SEED_WORKFLOW_REF]

    def test_seed_llm_config_deepseek_default(self, registry: CapabilityRegistry):
        """默认种子: llm config deepseek-default (provider/model/endpoint 占位)。"""
        registry.seed_defaults()
        seeded = registry.get_llm_config("deepseek-default")
        assert seeded is not None
        assert seeded.provider == "deepseek"
        assert seeded.model == "v4-pro"  # 占位模型名 (只建实体不连接)
        assert seeded.endpoint == "https://api.deepseek.com/v1"  # 公共端点占位
        assert seeded.state == CapabilityState.ACTIVE
        assert seeded.enabled is True

    def test_seed_deepseek_default_no_key_plaintext(
        self, registry: CapabilityRegistry, llm_configs_dir: Path
    ):
        """种子文件内容禁明文凭据: 无 api_key/key/secret/token 键, 无 sk- 值。

        精确键名匹配 (max_tokens 是合法 provider 采样参数, 含 "token" 子串
        但不是凭据键 — 不作误报); 字符串值不以 sk- 开头 (无明文 key 值)。
        """
        registry.seed_defaults()
        path = llm_configs_dir / "deepseek-default.json"
        assert path.is_file()
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        # 凭据键名精确集合 — 顶层与 parameters 均不得出现
        credential_keys = {"api_key", "apikey", "key", "secret", "token", "access_token"}
        assert credential_keys.isdisjoint(data.keys())
        assert credential_keys.isdisjoint(data.get("parameters", {}).keys())
        # 无明文 key 值 (sk- 前缀 = 常见 API key 明文形态)
        for value in data.values():
            if isinstance(value, str):
                assert not value.startswith("sk-")
        # 模型字段集合收窄: 无凭据槽位
        assert set(data) <= {
            "id",
            "provider",
            "model",
            "endpoint",
            "parameters",
            "enabled",
            "state",
        }

    def test_seed_llm_config_selectable(self, registry: CapabilityRegistry):
        """种子 llm config ACTIVE+enabled → enabled_only list 包含。"""
        registry.seed_defaults()
        selectable = [
            c.id for c in registry.list_llm_configs(enabled_only=True)
        ]
        assert "deepseek-default" in selectable

    def test_seed_industry_refs_self_consistent(self, registry: CapabilityRegistry):
        """种子自洽: 全量种子后 software industry 的 workflow 引用全部解析零警告。"""
        registry.seed_defaults()
        assert registry.validate_industry_refs("software") == []

    def test_seed_defaults_idempotent_keeps_user_changes(
        self, registry: CapabilityRegistry
    ):
        """幂等: 已存在不覆盖 — 二次 seed 后用户修改保留 (industries+llm-configs)。"""
        registry.seed_defaults()
        registry.update_industry("software", {"name": "Custom Industry"})
        registry.update_llm_config("deepseek-default", {"model": "custom-model"})
        second = registry.seed_defaults()
        assert second == 0  # 已全部存在 → 无新建
        assert registry.get_industry("software").name == "Custom Industry"
        assert registry.get_llm_config("deepseek-default").model == "custom-model"

    def test_seed_defaults_does_not_touch_existing_dir(
        self, registry: CapabilityRegistry
    ):
        """已存在的同名自定义 industry/llm config → 种子不覆盖 (用户注册优先)。"""
        registry.register_industry(make_industry("software", name="My Own"))
        registry.register_llm_config(
            make_llm_config("deepseek-default", provider="my-provider")
        )
        registry.seed_defaults()
        assert registry.get_industry("software").name == "My Own"
        assert registry.get_llm_config("deepseek-default").provider == "my-provider"
