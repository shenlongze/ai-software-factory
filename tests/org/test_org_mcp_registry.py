"""tests/org/test_org_mcp_registry.py — S10-012 Task 004: MCP Registry (TDD)。

设计依据 (唯一):
- docs/sprint10/S10-012-architecture-design.md §二 (MCP 模型: id/name/type/
  endpoint/auth_config/capabilities) + §三 (Registry 架构: 目录信源
  workspace/capabilities/{kind}/{id}.json + CRUD + enabled 过滤 + 懒迁移)
  + §四b (生命周期 DRAFT→ACTIVE→DEPRECATED→ARCHIVED, archived 终态,
  enabled 独立运行开关 — ACTIVE+enabled 才可选)
- Task 004 任务书: MCP 默认种子 = 无 (MCP 是外部工具, 不预置 — 由用户注册);
  auth_config 占位 (不实现认证逻辑); type 为连接类型 (http/sse/stdio 等,
  自由字符串不设枚举)
- org/capabilities.py Task 002/003 Skill/Agent Registry 同构模式
  (原子写/失败安全/懒迁移/生命周期)

覆盖 (org/capabilities.py — CapabilityRegistry mcps 部分):
- 目录信源: register_mcp → workspace/capabilities/mcps/{id}.json (原子写);
  无 capabilities/ 目录 → 首次 register 创建 (懒迁移)
- MCP 字段: type (http/sse/stdio) / endpoint / auth_config (占位 dict) /
  capabilities (list) — 全字段 roundtrip 可复现
- CRUD: register_mcp (upsert — 重复 id 覆盖) / get_mcp (缺失 → None) /
  list_mcps (enabled_only 过滤: 只返回 ACTIVE+enabled) / update_mcp
  (部分字段更新, 缺失 → None) / delete_mcp (缺失 → False, 幂等)
- 生命周期: transition_mcp (受控单向, 落盘持久; 非法转换 ValueError 且
  不落盘; 缺失 → None)
- 失败安全: 损坏 JSON / 非法 schema → list 跳过 / get None (绝不崩溃)
- 默认种子: seed_defaults() 不预置 MCP (外部工具, 由用户注册 → 0 个)

basename 全仓库唯一 (test_org_mcp_registry — tests/agents/ 已有
test_agent_registry.py (旧 agents/registry.py), 同名模块会互相遮蔽, 故用
test_org_ 前缀); 不跨目录依赖 helper。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# noqa: E402 — tests/org/conftest.py 已挂 factory-org 到 sys.path (org 包父目录)
from org.capabilities import (  # noqa: E402
    CapabilityRegistry,
    CapabilityState,
    MCP,
)


@pytest.fixture
def registry(tmp_path: Path) -> CapabilityRegistry:
    """独立工厂根 (<tmp>/factory → workspace/capabilities/mcps/)。"""
    return CapabilityRegistry(tmp_path / "factory")


@pytest.fixture
def mcps_dir(registry: CapabilityRegistry) -> Path:
    return registry.mcps_dir


def make_mcp(mcp_id: str = "filesystem-mcp", **overrides) -> MCP:
    """确定性 MCP 工厂 (显式 id, 断言友好; auth_config 占位 dict)。"""
    data = {
        "id": mcp_id,
        "name": f"MCP {mcp_id}",
        "type": "http",
        "endpoint": "https://example.com/mcp",
        "auth_config": {"type": "bearer", "token_env": "MCP_TOKEN"},
        "capabilities": ["tools", "resources"],
        "enabled": True,
        "state": "active",
    }
    data.update(overrides)
    return MCP.model_validate(data)


# ------------------------------------------------------------------ 目录信源


class TestMcpRegistryDirSource:
    def test_register_mcp_writes_json_file(
        self, registry: CapabilityRegistry, mcps_dir: Path
    ):
        """register → workspace/capabilities/mcps/{id}.json (目录信源)。"""
        registry.register_mcp(make_mcp("filesystem-mcp"))
        path = mcps_dir / "filesystem-mcp.json"
        assert path.is_file()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["id"] == "filesystem-mcp"
        assert data["name"] == "MCP filesystem-mcp"
        assert data["type"] == "http"
        assert data["endpoint"] == "https://example.com/mcp"
        assert data["auth_config"] == {"type": "bearer", "token_env": "MCP_TOKEN"}
        assert data["capabilities"] == ["tools", "resources"]
        assert data["state"] == "active"
        assert data["enabled"] is True

    def test_register_creates_mcps_dir_lazily(
        self, registry: CapabilityRegistry, mcps_dir: Path
    ):
        """懒迁移: 无 capabilities/ 目录 → 首次 register 创建 (不预先建目录)。"""
        assert not mcps_dir.exists()
        registry.register_mcp(make_mcp("filesystem-mcp"))
        assert mcps_dir.is_dir()

    def test_register_duplicate_id_overwrites(
        self, registry: CapabilityRegistry, mcps_dir: Path
    ):
        """重复 id → 覆盖 (单文件单实体, 同 Skill/Agent upsert 模式)。"""
        registry.register_mcp(make_mcp("filesystem-mcp", name="v1"))
        registry.register_mcp(make_mcp("filesystem-mcp", name="v2"))
        files = [p.name for p in mcps_dir.iterdir() if p.is_file()]
        assert files == ["filesystem-mcp.json"]  # 不产生多版本文件
        assert registry.get_mcp("filesystem-mcp").name == "v2"

    def test_register_illegal_id_rejected(self, registry: CapabilityRegistry):
        """id 含路径分隔符 → 拒绝 (防目录信源路径穿越)。"""
        with pytest.raises(ValueError):
            registry.register_mcp(make_mcp("../escape"))
        with pytest.raises(ValueError):
            registry.register_mcp(make_mcp("a/b"))

    def test_register_empty_id_rejected(self, registry: CapabilityRegistry):
        """空 id → 拒绝 (非空字符串防御)。"""
        with pytest.raises(ValueError):
            registry.register_mcp(make_mcp(""))

    def test_get_mcp_roundtrip_full_fields(self, registry: CapabilityRegistry):
        """register → get 全字段往返 (type/endpoint/auth_config/capabilities 干净可复现)。"""
        original = make_mcp(
            "github-mcp",
            name="GitHub MCP",
            type="sse",
            endpoint="https://api.github.com/mcp",
            auth_config={},
            capabilities=["pull_requests", "issues"],
            state="draft",
        )
        registry.register_mcp(original)
        loaded = registry.get_mcp("github-mcp")
        assert loaded is not None
        assert loaded.to_dict() == original.to_dict()

    def test_get_missing_returns_none(self, registry: CapabilityRegistry):
        """缺失 id → None (不是空实体)。"""
        assert registry.get_mcp("no-such-mcp") is None

    def test_get_after_delete_returns_none(self, registry: CapabilityRegistry):
        """删除后 get → None (目录信源一致)。"""
        registry.register_mcp(make_mcp("filesystem-mcp"))
        registry.delete_mcp("filesystem-mcp")
        assert registry.get_mcp("filesystem-mcp") is None

    def test_list_mcps_sorted_by_id(self, registry: CapabilityRegistry):
        """list 全部 mcps, 按 id 排序 (确定性, 审计友好)。"""
        for mcp_id in ("z-mcp", "a-mcp", "m-mcp"):
            registry.register_mcp(make_mcp(mcp_id))
        ids = [m.id for m in registry.list_mcps()]
        assert ids == ["a-mcp", "m-mcp", "z-mcp"]

    def test_list_mcps_empty_when_no_files(self, registry: CapabilityRegistry):
        """无任何 mcp → 空列表 (目录不存在也合法)。"""
        assert registry.list_mcps() == []

    def test_delete_mcp_removes_file(
        self, registry: CapabilityRegistry, mcps_dir: Path
    ):
        """delete → 文件删除, 返回 True。"""
        registry.register_mcp(make_mcp("filesystem-mcp"))
        assert registry.delete_mcp("filesystem-mcp") is True
        assert not (mcps_dir / "filesystem-mcp.json").exists()

    def test_delete_missing_returns_false(self, registry: CapabilityRegistry):
        """缺失 → False (幂等删除)。"""
        assert registry.delete_mcp("no-such-mcp") is False


# ------------------------------------------------------------------ update / auth_config / capabilities


class TestMcpRegistryUpdate:
    def test_update_mcp_partial_fields(self, registry: CapabilityRegistry):
        """update: 部分字段更新, 其余保留 (type/endpoint/auth_config 不动)。"""
        registry.register_mcp(make_mcp("filesystem-mcp"))
        updated = registry.update_mcp("filesystem-mcp", {"name": "FS v2"})
        assert updated is not None
        assert updated.name == "FS v2"
        assert updated.type == "http"  # 未动字段保留
        assert updated.endpoint == "https://example.com/mcp"
        assert updated.auth_config == {"type": "bearer", "token_env": "MCP_TOKEN"}
        assert registry.get_mcp("filesystem-mcp").name == "FS v2"  # 落盘

    def test_update_mcp_type_and_endpoint(self, registry: CapabilityRegistry):
        """type (http→stdio) + endpoint 可更新。"""
        registry.register_mcp(make_mcp("filesystem-mcp", type="http"))
        updated = registry.update_mcp(
            "filesystem-mcp",
            {"type": "stdio", "endpoint": ""},
        )
        assert updated is not None
        assert updated.type == "stdio"
        assert updated.endpoint == ""

    def test_update_mcp_auth_config(self, registry: CapabilityRegistry):
        """auth_config 占位 dict 可整体替换 (不实现认证逻辑)。"""
        registry.register_mcp(make_mcp("filesystem-mcp"))
        updated = registry.update_mcp(
            "filesystem-mcp", {"auth_config": {"type": "api_key", "key_env": "MCP_KEY"}}
        )
        assert updated is not None
        assert updated.auth_config == {"type": "api_key", "key_env": "MCP_KEY"}
        assert registry.get_mcp("filesystem-mcp").auth_config == {
            "type": "api_key",
            "key_env": "MCP_KEY",
        }  # 落盘

    def test_update_mcp_capabilities(self, registry: CapabilityRegistry):
        """capabilities 列表可整体替换。"""
        registry.register_mcp(make_mcp("filesystem-mcp"))
        updated = registry.update_mcp(
            "filesystem-mcp", {"capabilities": ["read", "write"]}
        )
        assert updated is not None
        assert updated.capabilities == ["read", "write"]
        loaded = registry.get_mcp("filesystem-mcp")
        assert loaded.capabilities == ["read", "write"]  # 落盘

    def test_update_mcp_missing_returns_none(self, registry: CapabilityRegistry):
        """update 缺失 id → None (不创建幽灵实体)。"""
        assert registry.update_mcp("no-such-mcp", {"name": "x"}) is None

    def test_update_mcp_invalid_state_rejected(self, registry: CapabilityRegistry):
        """update 非法 state → ValueError (pydantic 校验, 不落盘)。"""
        registry.register_mcp(make_mcp("filesystem-mcp"))
        with pytest.raises(ValueError):
            registry.update_mcp("filesystem-mcp", {"state": "bogus"})
        assert registry.get_mcp("filesystem-mcp").state == CapabilityState.ACTIVE

    def test_update_mcp_unknown_field_rejected(self, registry: CapabilityRegistry):
        """update 未知字段 → ValueError (extra=forbid, 不落盘)。"""
        registry.register_mcp(make_mcp("filesystem-mcp"))
        with pytest.raises(ValueError):
            registry.update_mcp("filesystem-mcp", {"bogus_field": 1})


# ------------------------------------------------------------------ 生命周期 + enabled


class TestMcpRegistryLifecycle:
    def test_transition_mcp_persists(self, registry: CapabilityRegistry):
        """transition: DRAFT → ACTIVE 落盘 (get 重新加载为新状态)。"""
        registry.register_mcp(make_mcp("filesystem-mcp", state="draft"))
        activated = registry.transition_mcp("filesystem-mcp", "active")
        assert activated is not None
        assert activated.state == CapabilityState.ACTIVE
        assert registry.get_mcp("filesystem-mcp").state == CapabilityState.ACTIVE

    def test_transition_full_chain(self, registry: CapabilityRegistry):
        """受控单向全链路: DRAFT→ACTIVE→DEPRECATED→ARCHIVED 逐步落盘。"""
        registry.register_mcp(make_mcp("filesystem-mcp", state="draft"))
        for target in ("active", "deprecated", "archived"):
            mcp = registry.transition_mcp("filesystem-mcp", target)
            assert mcp is not None
            assert mcp.state == CapabilityState.parse(target)
        assert (
            registry.get_mcp("filesystem-mcp").state == CapabilityState.ARCHIVED
        )

    def test_transition_illegal_raises_and_not_persisted(
        self, registry: CapabilityRegistry
    ):
        """非法转换 (跳级 DRAFT→ARCHIVED) → ValueError, 原文件保持原状态。"""
        registry.register_mcp(make_mcp("filesystem-mcp", state="draft"))
        with pytest.raises(ValueError):
            registry.transition_mcp("filesystem-mcp", "archived")
        assert registry.get_mcp("filesystem-mcp").state == CapabilityState.DRAFT

    def test_transition_missing_returns_none(self, registry: CapabilityRegistry):
        """transition 缺失 id → None。"""
        assert registry.transition_mcp("no-such-mcp", "active") is None

    def test_list_mcps_enabled_only_filters(self, registry: CapabilityRegistry):
        """enabled_only=True → 只返回 ACTIVE+enabled (DRAFT 与 ACTIVE+disabled 排除)。"""
        registry.register_mcp(make_mcp("active-on", state="active", enabled=True))
        registry.register_mcp(make_mcp("draft-mcp", state="draft", enabled=True))
        registry.register_mcp(make_mcp("active-off", state="active", enabled=False))
        registry.register_mcp(
            make_mcp("deprecated-on", state="deprecated", enabled=True)
        )
        selectable = [m.id for m in registry.list_mcps(enabled_only=True)]
        assert selectable == ["active-on"]

    def test_list_mcps_all_includes_everything(self, registry: CapabilityRegistry):
        """enabled_only 缺省 False → 全部实体 (生命周期各态均在)。"""
        registry.register_mcp(make_mcp("active-on", state="active", enabled=True))
        registry.register_mcp(make_mcp("draft-mcp", state="draft", enabled=True))
        assert {m.id for m in registry.list_mcps()} == {
            "active-on",
            "draft-mcp",
        }


# ------------------------------------------------------------------ 失败安全


class TestMcpRegistryFailSafe:
    def test_corrupt_json_skipped_in_list(
        self, registry: CapabilityRegistry, mcps_dir: Path
    ):
        """损坏 JSON 文件 → list 跳过 (不崩溃, 失败安全)。"""
        registry.register_mcp(make_mcp("good-mcp"))
        (mcps_dir / "corrupt.json").write_text("{ not valid json !!!", encoding="utf-8")
        ids = [m.id for m in registry.list_mcps()]
        assert ids == ["good-mcp"]  # 损坏文件静默跳过

    def test_corrupt_json_get_returns_none(
        self, registry: CapabilityRegistry, mcps_dir: Path
    ):
        """损坏 JSON → get None (单实体失败安全, 不抛异常)。"""
        mcps_dir.mkdir(parents=True)  # 懒迁移 — 手工构造损坏文件需先建目录
        (mcps_dir / "corrupt.json").write_text("{ broken", encoding="utf-8")
        assert registry.get_mcp("corrupt") is None

    def test_invalid_schema_json_skipped(
        self, registry: CapabilityRegistry, mcps_dir: Path
    ):
        """JSON 合法但 schema 非法 (缺 id/name) → list 跳过 / get None。"""
        registry.register_mcp(make_mcp("good-mcp"))
        (mcps_dir / "bad-schema.json").write_text(
            json.dumps({"name": "no id here"}), encoding="utf-8"
        )
        (mcps_dir / "not-dict.json").write_text("[1, 2, 3]", encoding="utf-8")
        ids = [m.id for m in registry.list_mcps()]
        assert ids == ["good-mcp"]
        assert registry.get_mcp("bad-schema") is None
        assert registry.get_mcp("not-dict") is None

    def test_atomic_write_no_tmp_leftover(
        self, registry: CapabilityRegistry, mcps_dir: Path
    ):
        """原子写: 临时文件不残留 (写后目录只有 {id}.json)。"""
        registry.register_mcp(make_mcp("filesystem-mcp"))
        registry.update_mcp("filesystem-mcp", {"name": "v1.1"})
        files = [p.name for p in mcps_dir.iterdir() if p.is_file()]
        assert files == ["filesystem-mcp.json"]


# ------------------------------------------------------------------ 默认种子 (MCP 不预置)


class TestMcpRegistrySeed:
    def test_seed_defaults_registers_no_mcps(self, registry: CapabilityRegistry):
        """默认种子不预置 MCP (外部工具, 由用户注册 — 0 个)。"""
        registry.seed_defaults()
        assert registry.list_mcps() == []

    def test_seed_defaults_does_not_create_mcps_dir(
        self, registry: CapabilityRegistry, mcps_dir: Path
    ):
        """seed_defaults 不创建 mcps/ 目录 (懒迁移只发生在首次 register)。"""
        registry.seed_defaults()
        assert not mcps_dir.exists()

    def test_user_registered_mcp_survives_seed(
        self, registry: CapabilityRegistry
    ):
        """用户注册的 MCP 在 seed_defaults 后保留 (种子不覆盖/不清空)。"""
        registry.register_mcp(make_mcp("user-mcp"))
        registry.seed_defaults()
        loaded = registry.get_mcp("user-mcp")
        assert loaded is not None
        assert loaded.name == "MCP user-mcp"
