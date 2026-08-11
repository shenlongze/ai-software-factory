"""tests/org/test_org_skill_registry.py — S10-012 Task 002: Skill Registry (TDD)。

设计依据 (唯一):
- docs/sprint10/S10-012-architecture-design.md §三 (Registry 架构: 目录信源
  workspace/capabilities/{kind}/{id}.json + CRUD + enabled 过滤 + 版本 +
  默认种子 + 懒迁移) + §四b (生命周期 DRAFT→ACTIVE→DEPRECATED→ARCHIVED,
  archived 终态, enabled 独立运行开关 — ACTIVE+enabled 才可选)
- org/store.py 原子写模式 (临时文件 + os.replace) + org/space.py 懒迁移模式

覆盖 (org/capabilities.py — CapabilityRegistry skills 部分):
- 目录信源: register → workspace/capabilities/skills/{id}.json (原子写);
  无 capabilities/ 目录 → 首次 register 创建 (懒迁移)
- CRUD: register_skill (upsert — 重复 id 覆盖, 明确语义) / get_skill (缺失
  → None) / list_skills (enabled_only 过滤: 只返回 ACTIVE+enabled) /
  update_skill (部分字段更新, 缺失 → None; 升级 = version 更新) /
  delete_skill (缺失 → False, 幂等)
- 版本: id 主键, version 字段记录; 同 id 新 version → 覆盖 (升级 = update)
- 生命周期: transition_skill (受控单向, 落盘持久; 非法转换 ValueError 且
  不落盘; 缺失 → None)
- 失败安全: 损坏 JSON / 非法 schema → list 跳过 / get None (绝不崩溃)
- 默认种子: seed_defaults() 预置标准 skills (≥3, ACTIVE+enabled), 幂等
  (已存在不覆盖 — 用户修改保留)

basename 全仓库唯一 (test_org_skill_registry — 注意: tests/agents/ 已有
test_skill_registry.py, 同名模块会互相遮蔽, 故用 test_org_ 前缀);
不跨目录依赖 helper。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# noqa: E402 — tests/org/conftest.py 已挂 factory-org 到 sys.path (org 包父目录)
from org.capabilities import (  # noqa: E402
    CapabilityRegistry,
    CapabilityState,
    Skill,
)


@pytest.fixture
def registry(tmp_path: Path) -> CapabilityRegistry:
    """独立工厂根 (<tmp>/factory → workspace/capabilities/skills/)。"""
    return CapabilityRegistry(tmp_path / "factory")


@pytest.fixture
def skills_dir(registry: CapabilityRegistry) -> Path:
    return registry.skills_dir


def make_skill(skill_id: str = "backend-development", **overrides) -> Skill:
    """确定性 Skill 工厂 (显式 id, 断言友好)。"""
    data = {
        "id": skill_id,
        "name": f"Skill {skill_id}",
        "description": "test skill",
        "category": "software-development",
        "input_schema": {"inputs": [{"name": "task"}]},
        "output_schema": {"outputs": [{"name": "result"}]},
        "version": "1.0.0",
        "enabled": True,
        "state": "active",
    }
    data.update(overrides)
    return Skill.model_validate(data)


# ------------------------------------------------------------------ 目录信源


class TestRegistryDirSource:
    def test_register_skill_writes_json_file(self, registry: CapabilityRegistry, skills_dir: Path):
        """register → workspace/capabilities/skills/{id}.json (目录信源)。"""
        registry.register_skill(make_skill("backend-development"))
        path = skills_dir / "backend-development.json"
        assert path.is_file()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["id"] == "backend-development"
        assert data["name"] == "Skill backend-development"
        assert data["version"] == "1.0.0"
        assert data["state"] == "active"
        assert data["enabled"] is True

    def test_register_creates_skills_dir_lazily(self, registry: CapabilityRegistry, skills_dir: Path):
        """懒迁移: 无 capabilities/ 目录 → 首次 register 创建 (不预先建目录)。"""
        assert not skills_dir.exists()
        registry.register_skill(make_skill("backend-development"))
        assert skills_dir.is_dir()

    def test_register_duplicate_id_overwrites(self, registry: CapabilityRegistry, skills_dir: Path):
        """重复 id → 覆盖 (明确语义; 单文件单实体, 同 store.save upsert 模式)。"""
        registry.register_skill(make_skill("backend-development", version="1.0.0"))
        registry.register_skill(make_skill("backend-development", version="2.0.0"))
        files = [p.name for p in skills_dir.iterdir() if p.is_file()]
        assert files == ["backend-development.json"]  # 不产生多版本文件
        assert registry.get_skill("backend-development").version == "2.0.0"

    def test_register_illegal_id_rejected(self, registry: CapabilityRegistry):
        """id 含路径分隔符 → 拒绝 (防目录信源路径穿越)。"""
        with pytest.raises(ValueError):
            registry.register_skill(make_skill("../escape"))
        with pytest.raises(ValueError):
            registry.register_skill(make_skill("a/b"))

    def test_get_skill_roundtrip_full_fields(self, registry: CapabilityRegistry):
        """register → get 全字段往返 (JSON 干净, 可复现)。"""
        original = make_skill(
            "backend-development",
            name="Backend Development",
            description="后端开发",
            category="software-development",
            version="1.2.0",
            state="draft",
        )
        registry.register_skill(original)
        loaded = registry.get_skill("backend-development")
        assert loaded is not None
        assert loaded.to_dict() == original.to_dict()

    def test_get_missing_returns_none(self, registry: CapabilityRegistry):
        """缺失 id → None (不是空实体)。"""
        assert registry.get_skill("no-such-skill") is None

    def test_get_after_delete_returns_none(self, registry: CapabilityRegistry):
        """删除后 get → None (目录信源一致)。"""
        registry.register_skill(make_skill("backend-development"))
        registry.delete_skill("backend-development")
        assert registry.get_skill("backend-development") is None

    def test_list_skills_sorted_by_id(self, registry: CapabilityRegistry):
        """list 全部技能, 按 id 排序 (确定性, 审计友好)。"""
        for skill_id in ("z-skill", "a-skill", "m-skill"):
            registry.register_skill(make_skill(skill_id))
        ids = [s.id for s in registry.list_skills()]
        assert ids == ["a-skill", "m-skill", "z-skill"]

    def test_list_skills_empty_when_no_files(self, registry: CapabilityRegistry):
        """无任何技能 → 空列表 (目录不存在也合法)。"""
        assert registry.list_skills() == []

    def test_delete_skill_removes_file(self, registry: CapabilityRegistry, skills_dir: Path):
        """delete → 文件删除, 返回 True。"""
        registry.register_skill(make_skill("backend-development"))
        assert registry.delete_skill("backend-development") is True
        assert not (skills_dir / "backend-development.json").exists()

    def test_delete_missing_returns_false(self, registry: CapabilityRegistry):
        """缺失 → False (幂等删除)。"""
        assert registry.delete_skill("no-such-skill") is False


# ------------------------------------------------------------------ update / 版本


class TestRegistryUpdate:
    def test_update_skill_partial_fields(self, registry: CapabilityRegistry):
        """update: 部分字段更新, 其余保留 (升级 = update 语义)。"""
        registry.register_skill(make_skill("backend-development"))
        updated = registry.update_skill(
            "backend-development", {"name": "Backend v2", "description": "新描述"}
        )
        assert updated is not None
        assert updated.name == "Backend v2"
        assert updated.description == "新描述"
        assert updated.version == "1.0.0"  # 未动字段保留
        assert updated.state == CapabilityState.ACTIVE
        assert registry.get_skill("backend-development").name == "Backend v2"  # 落盘

    def test_update_skill_upgrade_version(self, registry: CapabilityRegistry):
        """版本: id 主键, version 字段记录; 升级 = update (同 id 新 version 覆盖)。"""
        registry.register_skill(make_skill("backend-development", version="1.0.0"))
        registry.update_skill("backend-development", {"version": "2.0.0"})
        assert registry.get_skill("backend-development").version == "2.0.0"
        assert registry.get_skill("backend-development").id == "backend-development"

    def test_update_skill_missing_returns_none(self, registry: CapabilityRegistry):
        """update 缺失 id → None (不创建幽灵实体)。"""
        assert registry.update_skill("no-such-skill", {"name": "x"}) is None

    def test_update_skill_invalid_state_rejected(self, registry: CapabilityRegistry):
        """update 非法 state → ValueError (pydantic 校验, 不落盘)。"""
        registry.register_skill(make_skill("backend-development"))
        with pytest.raises(ValueError):
            registry.update_skill("backend-development", {"state": "bogus"})
        assert registry.get_skill("backend-development").state == CapabilityState.ACTIVE

    def test_update_skill_unknown_field_rejected(self, registry: CapabilityRegistry):
        """update 未知字段 → ValueError (extra=forbid, 不落盘)。"""
        registry.register_skill(make_skill("backend-development"))
        with pytest.raises(ValueError):
            registry.update_skill("backend-development", {"bogus_field": 1})


# ------------------------------------------------------------------ 生命周期 + enabled


class TestRegistryLifecycle:
    def test_transition_skill_persists(self, registry: CapabilityRegistry):
        """transition: DRAFT → ACTIVE 落盘 (get 重新加载为新状态)。"""
        registry.register_skill(make_skill("backend-development", state="draft"))
        activated = registry.transition_skill("backend-development", "active")
        assert activated is not None
        assert activated.state == CapabilityState.ACTIVE
        assert registry.get_skill("backend-development").state == CapabilityState.ACTIVE

    def test_transition_full_chain(self, registry: CapabilityRegistry):
        """受控单向全链路: DRAFT→ACTIVE→DEPRECATED→ARCHIVED 逐步落盘。"""
        registry.register_skill(make_skill("backend-development", state="draft"))
        for target in ("active", "deprecated", "archived"):
            skill = registry.transition_skill("backend-development", target)
            assert skill is not None
            assert skill.state == CapabilityState.parse(target)
        assert registry.get_skill("backend-development").state == CapabilityState.ARCHIVED

    def test_transition_illegal_raises_and_not_persisted(self, registry: CapabilityRegistry):
        """非法转换 (跳级 DRAFT→ARCHIVED) → ValueError, 原文件保持原状态。"""
        registry.register_skill(make_skill("backend-development", state="draft"))
        with pytest.raises(ValueError):
            registry.transition_skill("backend-development", "archived")
        assert registry.get_skill("backend-development").state == CapabilityState.DRAFT

    def test_transition_missing_returns_none(self, registry: CapabilityRegistry):
        """transition 缺失 id → None。"""
        assert registry.transition_skill("no-such-skill", "active") is None

    def test_list_skills_enabled_only_filters(self, registry: CapabilityRegistry):
        """enabled_only=True → 只返回 ACTIVE+enabled (DRAFT 与 ACTIVE+disabled 排除)。"""
        registry.register_skill(make_skill("active-on", state="active", enabled=True))
        registry.register_skill(make_skill("draft-skill", state="draft", enabled=True))
        registry.register_skill(make_skill("active-off", state="active", enabled=False))
        registry.register_skill(make_skill("deprecated-on", state="deprecated", enabled=True))
        selectable = [s.id for s in registry.list_skills(enabled_only=True)]
        assert selectable == ["active-on"]

    def test_list_skills_all_includes_everything(self, registry: CapabilityRegistry):
        """enabled_only 缺省 False → 全部实体 (生命周期各态均在)。"""
        registry.register_skill(make_skill("active-on", state="active", enabled=True))
        registry.register_skill(make_skill("draft-skill", state="draft", enabled=True))
        assert {s.id for s in registry.list_skills()} == {"active-on", "draft-skill"}


# ------------------------------------------------------------------ 失败安全


class TestRegistryFailSafe:
    def test_corrupt_json_skipped_in_list(self, registry: CapabilityRegistry, skills_dir: Path):
        """损坏 JSON 文件 → list 跳过 (不崩溃, 失败安全)。"""
        registry.register_skill(make_skill("good-skill"))
        (skills_dir / "corrupt.json").write_text("{ not valid json !!!", encoding="utf-8")
        ids = [s.id for s in registry.list_skills()]
        assert ids == ["good-skill"]  # 损坏文件静默跳过

    def test_corrupt_json_get_returns_none(self, registry: CapabilityRegistry, skills_dir: Path):
        """损坏 JSON → get None (单实体失败安全, 不抛异常)。"""
        skills_dir.mkdir(parents=True)  # 目录信源懒迁移 — 手工构造损坏文件需先建目录
        (skills_dir / "corrupt.json").write_text("{ broken", encoding="utf-8")
        assert registry.get_skill("corrupt") is None

    def test_invalid_schema_json_skipped(self, registry: CapabilityRegistry, skills_dir: Path):
        """JSON 合法但 schema 非法 (缺 id/name) → list 跳过 / get None。"""
        registry.register_skill(make_skill("good-skill"))
        (skills_dir / "bad-schema.json").write_text(
            json.dumps({"name": "no id here"}), encoding="utf-8"
        )
        (skills_dir / "not-dict.json").write_text("[1, 2, 3]", encoding="utf-8")
        ids = [s.id for s in registry.list_skills()]
        assert ids == ["good-skill"]
        assert registry.get_skill("bad-schema") is None
        assert registry.get_skill("not-dict") is None

    def test_atomic_write_no_tmp_leftover(self, registry: CapabilityRegistry, skills_dir: Path):
        """原子写: 临时文件不残留 (写后目录只有 {id}.json)。"""
        registry.register_skill(make_skill("backend-development"))
        registry.update_skill("backend-development", {"version": "1.1.0"})
        files = [p.name for p in skills_dir.iterdir() if p.is_file()]
        assert files == ["backend-development.json"]


# ------------------------------------------------------------------ 默认种子


class TestSeedDefaults:
    def test_seed_defaults_registers_standard_skills(self, registry: CapabilityRegistry):
        """默认种子: ≥3 标准 skill (backend/frontend/qa/product/flutter)。"""
        count = registry.seed_defaults()
        assert count >= 3
        ids = {s.id for s in registry.list_skills()}
        assert {"backend-development", "frontend-development", "qa-testing"} <= ids
        assert "product-management" in ids
        assert "flutter-development" in ids

    def test_seed_defaults_creates_files(self, registry: CapabilityRegistry, skills_dir: Path):
        """种子技能落盘为目录信源文件 (可被 get 读取)。"""
        registry.seed_defaults()
        assert (skills_dir / "backend-development.json").is_file()
        seeded = registry.get_skill("backend-development")
        assert seeded is not None
        assert seeded.state == CapabilityState.ACTIVE
        assert seeded.enabled is True

    def test_seed_defaults_all_selectable(self, registry: CapabilityRegistry):
        """种子技能 ACTIVE+enabled → enabled_only list 全返回 (验收场景4)。"""
        registry.seed_defaults()
        all_skills = registry.list_skills()
        selectable = registry.list_skills(enabled_only=True)
        assert len(selectable) == len(all_skills) >= 3

    def test_seed_defaults_idempotent_keeps_user_changes(self, registry: CapabilityRegistry):
        """幂等: 已存在不覆盖 — 二次 seed 后用户修改保留。"""
        registry.seed_defaults()
        registry.update_skill("backend-development", {"name": "Custom Name"})
        second = registry.seed_defaults()
        assert second == 0  # 已全部存在 → 无新建
        assert registry.get_skill("backend-development").name == "Custom Name"

    def test_seed_defaults_does_not_touch_existing_dir(self, registry: CapabilityRegistry):
        """已存在的同名自定义技能 → 种子不覆盖 (用户注册优先)。"""
        registry.register_skill(
            make_skill("backend-development", name="My Own", version="9.9.9")
        )
        registry.seed_defaults()
        assert registry.get_skill("backend-development").name == "My Own"
        assert registry.get_skill("backend-development").version == "9.9.9"
