"""tests/org/test_org_workflow_registry.py — S10-012 Task 005: Workflow Template Registry (TDD)。

设计依据 (唯一):
- docs/sprint10/S10-012-architecture-design.md §二 (WorkflowTemplate 模型:
  id/name/industry/steps/required_agents/required_skills) + §三 (Registry 架构:
  目录信源 workspace/capabilities/workflows/{id}.json + CRUD + enabled 过滤 +
  默认种子 software-development workflow + 懒迁移) + §四 (引用校验 — 缺失 →
  警告标注, 不崩溃) + §四b (生命周期 DRAFT→ACTIVE→DEPRECATED→ARCHIVED,
  archived 终态, enabled 独立运行开关 — ACTIVE+enabled 才可选)
- AF-PRD-v1.md §4.8 (Software Development Workflow 公共资源默认:
  Requirement Analysis → ... → Developer → Test → Release)
- Task 005 任务书: steps 有序 (requirement-analysis → architecture →
  development → testing → release) + required_agents (pm/architect/developer/qa)
  + required_skills 对应; steps 校验 非空/有序 (顺序语义); required_agents/
  skills 引用 registry (缺失 → 警告); 种子 software-development-lifecycle
- org/capabilities.py Task 002/003/004 Skill/Agent/MCP Registry 同构模式
  (原子写/失败安全/懒迁移/生命周期)

覆盖 (org/capabilities.py — CapabilityRegistry workflows 部分):
- 目录信源: register_workflow → workspace/capabilities/workflows/{id}.json
  (原子写, 全字段 roundtrip); 无 capabilities/ 目录 → 首次 register 创建
  (懒迁移); 重复 id → 覆盖 (upsert)
- CRUD: register_workflow / get_workflow (缺失 → None) / list_workflows
  (enabled_only 过滤: 只返回 ACTIVE+enabled, 按 id 排序) / update_workflow
  (部分字段更新, 缺失 → None) / delete_workflow (缺失 → False, 幂等)
- WorkflowTemplate 字段: industry (Industry id 引用) / steps (list 有序 —
  列表顺序即执行顺序, roundtrip 保持) / required_agents / required_skills
- steps 校验: 非空 (空列表拒绝) + 有序语义 + step 含非空 id + step id 唯一
- 生命周期: transition_workflow (受控单向, 落盘持久; 非法转换 ValueError
  且不落盘; 缺失 → None)
- 引用校验: validate_workflow_refs — required_agents 引用 agents/ 目录 +
  required_skills 引用 skills/ 目录 (缺失 → 警告标注, 不崩溃; 空列表 =
  全部解析; 缺失 workflow → None)
- 失败安全: 损坏 JSON / 非法 schema → list 跳过 / get None (绝不崩溃)
- 默认种子: seed_defaults() 预置 software-development-lifecycle workflow
  (5 steps 有序 + 4 required_agents + required_skills, ACTIVE+enabled,
  幂等不覆盖用户修改; 种子自洽 — 引用全部解析零警告)

basename 全仓库唯一 (test_org_workflow_registry); 不跨目录依赖 helper。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# noqa: E402 — tests/org/conftest.py 已挂 factory-org 到 sys.path (org 包父目录)
from org.capabilities import (  # noqa: E402
    CapabilityRegistry,
    CapabilityState,
    WorkflowTemplate,
)

#: 种子 workflow 标准 steps (AF-PRD §4.8: 有序执行链, 顺序即语义)
SEED_STEPS: list[dict[str, str]] = [
    {"id": "requirement-analysis", "name": "Requirement Analysis"},
    {"id": "architecture", "name": "Architecture"},
    {"id": "development", "name": "Development"},
    {"id": "testing", "name": "Testing"},
    {"id": "release", "name": "Release"},
]


@pytest.fixture
def registry(tmp_path: Path) -> CapabilityRegistry:
    """独立工厂根 (<tmp>/factory → workspace/capabilities/workflows/)。"""
    return CapabilityRegistry(tmp_path / "factory")


@pytest.fixture
def workflows_dir(registry: CapabilityRegistry) -> Path:
    return registry.workflows_dir


def make_workflow(workflow_id: str = "software-development", **overrides) -> WorkflowTemplate:
    """确定性 WorkflowTemplate 工厂 (显式 id, 断言友好; steps 有序列表)。"""
    data = {
        "id": workflow_id,
        "name": f"Workflow {workflow_id}",
        "industry": "software-development",
        "steps": [
            {"id": "requirement-analysis", "name": "Requirement Analysis"},
            {"id": "development", "name": "Development"},
        ],
        "required_agents": ["product-manager-agent", "developer-agent"],
        "required_skills": ["product-management", "backend-development"],
        "enabled": True,
        "state": "active",
    }
    data.update(overrides)
    return WorkflowTemplate.model_validate(data)


# ------------------------------------------------------------------ 目录信源


class TestWorkflowRegistryDirSource:
    def test_register_workflow_writes_json_file(
        self, registry: CapabilityRegistry, workflows_dir: Path
    ):
        """register → workspace/capabilities/workflows/{id}.json (目录信源)。"""
        registry.register_workflow(make_workflow("software-development"))
        path = workflows_dir / "software-development.json"
        assert path.is_file()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["id"] == "software-development"
        assert data["name"] == "Workflow software-development"
        assert data["industry"] == "software-development"
        assert data["steps"] == [
            {"id": "requirement-analysis", "name": "Requirement Analysis"},
            {"id": "development", "name": "Development"},
        ]
        assert data["required_agents"] == ["product-manager-agent", "developer-agent"]
        assert data["required_skills"] == ["product-management", "backend-development"]
        assert data["state"] == "active"
        assert data["enabled"] is True

    def test_register_creates_workflows_dir_lazily(
        self, registry: CapabilityRegistry, workflows_dir: Path
    ):
        """懒迁移: 无 capabilities/ 目录 → 首次 register 创建 (不预先建目录)。"""
        assert not workflows_dir.exists()
        registry.register_workflow(make_workflow("software-development"))
        assert workflows_dir.is_dir()

    def test_register_duplicate_id_overwrites(
        self, registry: CapabilityRegistry, workflows_dir: Path
    ):
        """重复 id → 覆盖 (单文件单实体, 同 Skill/Agent/MCP upsert 模式)。"""
        registry.register_workflow(make_workflow("software-development", name="v1"))
        registry.register_workflow(make_workflow("software-development", name="v2"))
        files = [p.name for p in workflows_dir.iterdir() if p.is_file()]
        assert files == ["software-development.json"]  # 不产生多版本文件
        assert registry.get_workflow("software-development").name == "v2"

    def test_register_illegal_id_rejected(self, registry: CapabilityRegistry):
        """id 含路径分隔符 → 拒绝 (防目录信源路径穿越)。"""
        with pytest.raises(ValueError):
            registry.register_workflow(make_workflow("../escape"))
        with pytest.raises(ValueError):
            registry.register_workflow(make_workflow("a/b"))

    def test_register_empty_id_rejected(self, registry: CapabilityRegistry):
        """空 id → 拒绝 (非空字符串防御)。"""
        with pytest.raises(ValueError):
            registry.register_workflow(make_workflow(""))

    def test_get_workflow_roundtrip_full_fields(self, registry: CapabilityRegistry):
        """register → get 全字段往返 (industry/steps/required_agents/skills 干净可复现)。"""
        original = make_workflow(
            "release-pipeline",
            name="Release Pipeline",
            industry="software-development",
            steps=[
                {"id": "build", "name": "Build"},
                {"id": "deploy", "name": "Deploy"},
                {"id": "verify", "name": "Verify"},
            ],
            required_agents=["qa-agent"],
            required_skills=["qa-testing"],
            state="draft",
        )
        registry.register_workflow(original)
        loaded = registry.get_workflow("release-pipeline")
        assert loaded is not None
        assert loaded.to_dict() == original.to_dict()

    def test_get_missing_returns_none(self, registry: CapabilityRegistry):
        """缺失 id → None (不是空实体)。"""
        assert registry.get_workflow("no-such-workflow") is None

    def test_get_after_delete_returns_none(self, registry: CapabilityRegistry):
        """删除后 get → None (目录信源一致)。"""
        registry.register_workflow(make_workflow("software-development"))
        registry.delete_workflow("software-development")
        assert registry.get_workflow("software-development") is None

    def test_list_workflows_sorted_by_id(self, registry: CapabilityRegistry):
        """list 全部 workflows, 按 id 排序 (确定性, 审计友好)。"""
        for wf_id in ("z-workflow", "a-workflow", "m-workflow"):
            registry.register_workflow(make_workflow(wf_id))
        ids = [w.id for w in registry.list_workflows()]
        assert ids == ["a-workflow", "m-workflow", "z-workflow"]

    def test_list_workflows_empty_when_no_files(self, registry: CapabilityRegistry):
        """无任何 workflow → 空列表 (目录不存在也合法)。"""
        assert registry.list_workflows() == []

    def test_delete_workflow_removes_file(
        self, registry: CapabilityRegistry, workflows_dir: Path
    ):
        """delete → 文件删除, 返回 True。"""
        registry.register_workflow(make_workflow("software-development"))
        assert registry.delete_workflow("software-development") is True
        assert not (workflows_dir / "software-development.json").exists()

    def test_delete_missing_returns_false(self, registry: CapabilityRegistry):
        """缺失 → False (幂等删除)。"""
        assert registry.delete_workflow("no-such-workflow") is False


# ------------------------------------------------------------------ industry / steps 有序 / required_agents / required_skills


class TestWorkflowTemplateFields:
    def test_steps_ordered_semantics_preserved(self, registry: CapabilityRegistry):
        """steps 有序: 列表顺序即执行顺序 — register→get roundtrip 顺序不变。"""
        steps = [
            {"id": "requirement-analysis", "name": "Requirement Analysis"},
            {"id": "architecture", "name": "Architecture"},
            {"id": "development", "name": "Development"},
            {"id": "testing", "name": "Testing"},
            {"id": "release", "name": "Release"},
        ]
        registry.register_workflow(
            make_workflow("software-development", steps=steps)
        )
        loaded = registry.get_workflow("software-development")
        assert loaded is not None
        assert [s["id"] for s in loaded.steps] == [
            "requirement-analysis",
            "architecture",
            "development",
            "testing",
            "release",
        ]

    def test_steps_empty_rejected_on_register(self, registry: CapabilityRegistry):
        """steps 非空: 空列表 register → ValueError (无步骤的工作流无意义)。"""
        with pytest.raises(ValueError):
            registry.register_workflow(make_workflow("empty-steps", steps=[]))

    def test_step_missing_id_rejected(self, registry: CapabilityRegistry):
        """step 缺少 id (或空 id) → ValueError (step 必须可标识)。"""
        with pytest.raises(ValueError):
            registry.register_workflow(
                make_workflow("bad-step", steps=[{"name": "No Id"}])
            )
        with pytest.raises(ValueError):
            registry.register_workflow(
                make_workflow("bad-step", steps=[{"id": "  "}])
            )

    def test_step_duplicate_id_rejected(self, registry: CapabilityRegistry):
        """step id 重复 → ValueError (步骤唯一可标识)。"""
        with pytest.raises(ValueError):
            registry.register_workflow(
                make_workflow(
                    "dup-step",
                    steps=[{"id": "build"}, {"id": "build"}],
                )
            )

    def test_industry_reference_roundtrip(self, registry: CapabilityRegistry):
        """industry 为 Industry id 引用 (字符串) — 自定义值 roundtrip 可复现。"""
        registry.register_workflow(
            make_workflow("fintech-workflow", industry="fintech")
        )
        loaded = registry.get_workflow("fintech-workflow")
        assert loaded is not None
        assert loaded.industry == "fintech"

    def test_required_agents_skills_roundtrip(self, registry: CapabilityRegistry):
        """required_agents/required_skills 列表 roundtrip 可复现。"""
        registry.register_workflow(
            make_workflow(
                "full-workflow",
                required_agents=["pm-agent", "qa-agent"],
                required_skills=["product-management", "qa-testing"],
            )
        )
        loaded = registry.get_workflow("full-workflow")
        assert loaded is not None
        assert loaded.required_agents == ["pm-agent", "qa-agent"]
        assert loaded.required_skills == ["product-management", "qa-testing"]


# ------------------------------------------------------------------ update


class TestWorkflowRegistryUpdate:
    def test_update_workflow_partial_fields(self, registry: CapabilityRegistry):
        """update: 部分字段更新, 其余保留 (industry/steps 不动)。"""
        registry.register_workflow(make_workflow("software-development"))
        updated = registry.update_workflow("software-development", {"name": "SDLC v2"})
        assert updated is not None
        assert updated.name == "SDLC v2"
        assert updated.industry == "software-development"  # 未动字段保留
        assert [s["id"] for s in updated.steps] == [
            "requirement-analysis",
            "development",
        ]
        assert registry.get_workflow("software-development").name == "SDLC v2"  # 落盘

    def test_update_workflow_steps_ordered(self, registry: CapabilityRegistry):
        """steps 整体替换 + 顺序保持 (新顺序即新执行语义)。"""
        registry.register_workflow(make_workflow("software-development"))
        new_steps = [
            {"id": "planning", "name": "Planning"},
            {"id": "delivery", "name": "Delivery"},
        ]
        updated = registry.update_workflow(
            "software-development", {"steps": new_steps}
        )
        assert updated is not None
        assert [s["id"] for s in updated.steps] == ["planning", "delivery"]
        loaded = registry.get_workflow("software-development")
        assert [s["id"] for s in loaded.steps] == ["planning", "delivery"]  # 落盘

    def test_update_workflow_empty_steps_rejected(self, registry: CapabilityRegistry):
        """update 后 steps 空 → ValueError, 不落盘 (原文件保持)。"""
        registry.register_workflow(make_workflow("software-development"))
        with pytest.raises(ValueError):
            registry.update_workflow("software-development", {"steps": []})
        loaded = registry.get_workflow("software-development")
        assert [s["id"] for s in loaded.steps] == [
            "requirement-analysis",
            "development",
        ]  # 原样保持

    def test_update_workflow_industry(self, registry: CapabilityRegistry):
        """industry 可更新 (重定向 Industry 域)。"""
        registry.register_workflow(
            make_workflow("software-development", industry="software-development")
        )
        updated = registry.update_workflow(
            "software-development", {"industry": "fintech"}
        )
        assert updated is not None
        assert updated.industry == "fintech"

    def test_update_workflow_required_agents_skills(self, registry: CapabilityRegistry):
        """required_agents/required_skills 可整体替换。"""
        registry.register_workflow(make_workflow("software-development"))
        updated = registry.update_workflow(
            "software-development",
            {
                "required_agents": ["ui-designer-agent"],
                "required_skills": ["frontend-development"],
            },
        )
        assert updated is not None
        assert updated.required_agents == ["ui-designer-agent"]
        assert updated.required_skills == ["frontend-development"]
        loaded = registry.get_workflow("software-development")
        assert loaded.required_agents == ["ui-designer-agent"]  # 落盘

    def test_update_workflow_missing_returns_none(self, registry: CapabilityRegistry):
        """update 缺失 id → None (不创建幽灵实体)。"""
        assert registry.update_workflow("no-such-workflow", {"name": "x"}) is None

    def test_update_workflow_invalid_state_rejected(self, registry: CapabilityRegistry):
        """update 非法 state → ValueError (pydantic 校验, 不落盘)。"""
        registry.register_workflow(make_workflow("software-development"))
        with pytest.raises(ValueError):
            registry.update_workflow("software-development", {"state": "bogus"})
        assert (
            registry.get_workflow("software-development").state
            == CapabilityState.ACTIVE
        )

    def test_update_workflow_unknown_field_rejected(self, registry: CapabilityRegistry):
        """update 未知字段 → ValueError (extra=forbid, 不落盘)。"""
        registry.register_workflow(make_workflow("software-development"))
        with pytest.raises(ValueError):
            registry.update_workflow("software-development", {"bogus_field": 1})


# ------------------------------------------------------------------ 生命周期 + enabled


class TestWorkflowRegistryLifecycle:
    def test_transition_workflow_persists(self, registry: CapabilityRegistry):
        """transition: DRAFT → ACTIVE 落盘 (get 重新加载为新状态)。"""
        registry.register_workflow(make_workflow("software-development", state="draft"))
        activated = registry.transition_workflow("software-development", "active")
        assert activated is not None
        assert activated.state == CapabilityState.ACTIVE
        assert (
            registry.get_workflow("software-development").state
            == CapabilityState.ACTIVE
        )

    def test_transition_full_chain(self, registry: CapabilityRegistry):
        """受控单向全链路: DRAFT→ACTIVE→DEPRECATED→ARCHIVED 逐步落盘。"""
        registry.register_workflow(make_workflow("software-development", state="draft"))
        for target in ("active", "deprecated", "archived"):
            wf = registry.transition_workflow("software-development", target)
            assert wf is not None
            assert wf.state == CapabilityState.parse(target)
        assert (
            registry.get_workflow("software-development").state
            == CapabilityState.ARCHIVED
        )

    def test_transition_illegal_raises_and_not_persisted(
        self, registry: CapabilityRegistry
    ):
        """非法转换 (跳级 DRAFT→ARCHIVED) → ValueError, 原文件保持原状态。"""
        registry.register_workflow(make_workflow("software-development", state="draft"))
        with pytest.raises(ValueError):
            registry.transition_workflow("software-development", "archived")
        assert (
            registry.get_workflow("software-development").state
            == CapabilityState.DRAFT
        )

    def test_transition_missing_returns_none(self, registry: CapabilityRegistry):
        """transition 缺失 id → None。"""
        assert registry.transition_workflow("no-such-workflow", "active") is None

    def test_list_workflows_enabled_only_filters(self, registry: CapabilityRegistry):
        """enabled_only=True → 只返回 ACTIVE+enabled (DRAFT 与 ACTIVE+disabled 排除)。"""
        registry.register_workflow(make_workflow("active-on", state="active", enabled=True))
        registry.register_workflow(make_workflow("draft-wf", state="draft", enabled=True))
        registry.register_workflow(make_workflow("active-off", state="active", enabled=False))
        registry.register_workflow(
            make_workflow("deprecated-on", state="deprecated", enabled=True)
        )
        selectable = [w.id for w in registry.list_workflows(enabled_only=True)]
        assert selectable == ["active-on"]

    def test_list_workflows_all_includes_everything(self, registry: CapabilityRegistry):
        """enabled_only 缺省 False → 全部实体 (生命周期各态均在)。"""
        registry.register_workflow(make_workflow("active-on", state="active", enabled=True))
        registry.register_workflow(make_workflow("draft-wf", state="draft", enabled=True))
        assert {w.id for w in registry.list_workflows()} == {
            "active-on",
            "draft-wf",
        }


# ------------------------------------------------------------------ 引用校验 (required_agents/required_skills)


class TestWorkflowRefValidation:
    def test_validate_workflow_refs_empty_when_all_resolve(
        self, registry: CapabilityRegistry
    ):
        """required_agents/required_skills 全部存在于 registry → 空警告列表。"""
        registry.register_workflow(make_workflow("software-development"))
        # 用最小实体注册 (Agent/Skill 构造依赖 org.capabilities 其余实体)
        from org.capabilities import Agent, Skill

        registry.register_agent(
            Agent.model_validate(
                {
                    "id": "product-manager-agent",
                    "name": "PM",
                    "role": "pm",
                    "state": "active",
                }
            )
        )
        registry.register_agent(
            Agent.model_validate(
                {"id": "developer-agent", "name": "Dev", "state": "active"}
            )
        )
        registry.register_skill(
            Skill.model_validate(
                {
                    "id": "product-management",
                    "name": "Product Management",
                    "state": "active",
                }
            )
        )
        registry.register_skill(
            Skill.model_validate(
                {
                    "id": "backend-development",
                    "name": "Backend Development",
                    "state": "active",
                }
            )
        )
        assert registry.validate_workflow_refs("software-development") == []

    def test_validate_workflow_refs_missing_warnings(
        self, registry: CapabilityRegistry
    ):
        """required_agents/skills 引用缺失 → 警告标注 (不崩溃, 不抛异常)。"""
        registry.register_workflow(make_workflow("software-development"))
        warnings = registry.validate_workflow_refs("software-development")
        assert isinstance(warnings, list)
        assert len(warnings) == 4  # 2 agents + 2 skills 全部缺失
        text = "\n".join(warnings)
        assert "product-manager-agent" in text
        assert "developer-agent" in text
        assert "product-management" in text
        assert "backend-development" in text
        assert "missing" in text

    def test_validate_workflow_refs_partial_missing(self, registry: CapabilityRegistry):
        """部分缺失 → 只警告缺失项 (已存在引用不警告)。"""
        from org.capabilities import Skill

        registry.register_workflow(make_workflow("software-development"))
        registry.register_skill(
            Skill.model_validate(
                {
                    "id": "backend-development",
                    "name": "Backend Development",
                    "state": "active",
                }
            )
        )
        warnings = registry.validate_workflow_refs("software-development")
        assert len(warnings) == 3
        text = "\n".join(warnings)
        assert "backend-development" not in text  # 已存在 → 不警告

    def test_validate_workflow_refs_empty_lists_no_warnings(
        self, registry: CapabilityRegistry
    ):
        """无 required_agents/required_skills → 空警告 (可空字段合法)。"""
        registry.register_workflow(
            make_workflow("bare-workflow", required_agents=[], required_skills=[])
        )
        assert registry.validate_workflow_refs("bare-workflow") == []

    def test_validate_workflow_refs_missing_workflow_none(
        self, registry: CapabilityRegistry
    ):
        """校验缺失 workflow → None (同 get_workflow 语义)。"""
        assert registry.validate_workflow_refs("no-such-workflow") is None


# ------------------------------------------------------------------ 失败安全


class TestWorkflowRegistryFailSafe:
    def test_corrupt_json_skipped_in_list(
        self, registry: CapabilityRegistry, workflows_dir: Path
    ):
        """损坏 JSON 文件 → list 跳过 (不崩溃, 失败安全)。"""
        registry.register_workflow(make_workflow("good-workflow"))
        (workflows_dir / "corrupt.json").write_text(
            "{ not valid json !!!", encoding="utf-8"
        )
        ids = [w.id for w in registry.list_workflows()]
        assert ids == ["good-workflow"]  # 损坏文件静默跳过

    def test_corrupt_json_get_returns_none(
        self, registry: CapabilityRegistry, workflows_dir: Path
    ):
        """损坏 JSON → get None (单实体失败安全, 不抛异常)。"""
        workflows_dir.mkdir(parents=True)  # 懒迁移 — 手工构造损坏文件需先建目录
        (workflows_dir / "corrupt.json").write_text("{ broken", encoding="utf-8")
        assert registry.get_workflow("corrupt") is None

    def test_invalid_schema_json_skipped(
        self, registry: CapabilityRegistry, workflows_dir: Path
    ):
        """JSON 合法但 schema 非法 (缺 id/name) → list 跳过 / get None。"""
        registry.register_workflow(make_workflow("good-workflow"))
        (workflows_dir / "bad-schema.json").write_text(
            json.dumps({"name": "no id here"}), encoding="utf-8"
        )
        (workflows_dir / "not-dict.json").write_text("[1, 2, 3]", encoding="utf-8")
        ids = [w.id for w in registry.list_workflows()]
        assert ids == ["good-workflow"]
        assert registry.get_workflow("bad-schema") is None
        assert registry.get_workflow("not-dict") is None

    def test_atomic_write_no_tmp_leftover(
        self, registry: CapabilityRegistry, workflows_dir: Path
    ):
        """原子写: 临时文件不残留 (写后目录只有 {id}.json)。"""
        registry.register_workflow(make_workflow("software-development"))
        registry.update_workflow("software-development", {"name": "v1.1"})
        files = [p.name for p in workflows_dir.iterdir() if p.is_file()]
        assert files == ["software-development.json"]


# ------------------------------------------------------------------ 默认种子 (software-development-lifecycle)


class TestWorkflowRegistrySeed:
    def test_seed_defaults_registers_sdlc_workflow(self, registry: CapabilityRegistry):
        """默认种子: software-development-lifecycle workflow (验收场景4)。"""
        count = registry.seed_defaults()
        assert count >= 1
        seeded = registry.get_workflow("software-development-lifecycle")
        assert seeded is not None
        assert seeded.name == "Software Development Lifecycle"
        assert seeded.industry == "software-development"
        assert seeded.state == CapabilityState.ACTIVE
        assert seeded.enabled is True

    def test_seed_workflow_steps_ordered_five(self, registry: CapabilityRegistry):
        """种子 steps: 5 步有序 (requirement-analysis → ... → release, 顺序语义)。"""
        registry.seed_defaults()
        seeded = registry.get_workflow("software-development-lifecycle")
        assert seeded is not None
        assert [s["id"] for s in seeded.steps] == [
            "requirement-analysis",
            "architecture",
            "development",
            "testing",
            "release",
        ]

    def test_seed_workflow_required_agents_four(self, registry: CapabilityRegistry):
        """种子 required_agents: 4 角色 (pm/architect/developer/qa)。"""
        registry.seed_defaults()
        seeded = registry.get_workflow("software-development-lifecycle")
        assert seeded is not None
        assert seeded.required_agents == [
            "product-manager-agent",
            "architect-agent",
            "developer-agent",
            "qa-agent",
        ]

    def test_seed_workflow_required_skills_resolve(self, registry: CapabilityRegistry):
        """种子 required_skills 对应 (产品/后端/前端/测试) — 引用全部落在种子内。"""
        registry.seed_defaults()
        seeded = registry.get_workflow("software-development-lifecycle")
        assert seeded is not None
        assert seeded.required_skills == [
            "product-management",
            "backend-development",
            "frontend-development",
            "qa-testing",
        ]

    def test_seed_workflow_selectable(self, registry: CapabilityRegistry):
        """种子 workflow ACTIVE+enabled → enabled_only list 包含 (验收场景4)。"""
        registry.seed_defaults()
        selectable = [w.id for w in registry.list_workflows(enabled_only=True)]
        assert "software-development-lifecycle" in selectable

    def test_seed_workflow_refs_self_consistent(self, registry: CapabilityRegistry):
        """种子自洽: skills+agents+workflows 同时种子 → 引用全部解析零警告。"""
        registry.seed_defaults()
        assert registry.validate_workflow_refs("software-development-lifecycle") == []

    def test_seed_defaults_idempotent_keeps_user_changes(
        self, registry: CapabilityRegistry
    ):
        """幂等: 已存在不覆盖 — 二次 seed 后用户修改保留 (workflows 部分)。"""
        registry.seed_defaults()
        registry.update_workflow("software-development-lifecycle", {"name": "Custom SDLC"})
        second = registry.seed_defaults()
        assert second == 0  # 已全部存在 → 无新建
        assert registry.get_workflow("software-development-lifecycle").name == "Custom SDLC"

    def test_seed_defaults_does_not_touch_existing_dir(
        self, registry: CapabilityRegistry
    ):
        """已存在的同名自定义 workflow → 种子不覆盖 (用户注册优先)。"""
        registry.register_workflow(
            make_workflow("software-development-lifecycle", name="My Own")
        )
        registry.seed_defaults()
        assert registry.get_workflow("software-development-lifecycle").name == "My Own"
