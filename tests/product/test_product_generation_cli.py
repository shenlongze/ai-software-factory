"""tests/product/test_product_generation_cli.py — factory product generate/experience CLI (Phase 9B, ADR-0027)。

覆盖: product generate (mock Provider 注入 — 装配点延迟导入 monkeypatch 配方,
显式 --provider 走 selector explicit 层) 产出 Artifact + PRD 自动审批 pending +
事件链 (generation.started → provider.selected → execution.* → completed →
approval.required); idea 未找到 rc 7; product experience record (从 Lineage
推导 provider/confidence + experience.recorded) + list (experience.viewed 审计)。
"""

from __future__ import annotations

import json

import pytest

from cli_helpers import event_types, open_events, run_cli

from product_helpers import MockAdapter


def _mock_provider(monkeypatch, cli_root) -> None:
    """装配点延迟导入 monkeypatch 配方 (§11): 原位改模块级 dict 即生效
    (_open_product_generator 调用时 dict() 拷贝)。显式 --provider mock 走
    selector explicit 层 — 注册且 ACTIVE 即命中, 不降级, 确定性最佳。"""
    import providers.adapters
    import providers.definitions

    from providers.capability import ProviderCapabilityProfile
    from providers.models import ProviderDefinition
    from providers.registry import ProviderRegistry
    from providers.store import ProviderStore

    monkeypatch.setitem(
        providers.definitions.DEFAULT_CAPABILITY_PROFILES, "mock",
        ProviderCapabilityProfile(
            provider_id="mock",
            matrix={"analysis": 0.8, "generation": 0.8, "reasoning": 0.8},
        ),
    )
    monkeypatch.setitem(
        providers.adapters.BUILTIN_PROVIDER_ADAPTERS, "mock",
        MockAdapter(provider_id="mock"),
    )
    registry = ProviderRegistry(ProviderStore(cli_root / "providers"))
    registry.register(ProviderDefinition(
        id="mock", name="Mock Provider",
        capabilities=["analysis", "generation", "reasoning"],
        models=["mock-model"],
    ))


class TestGenerateCli:
    def test_generate_prd_creates_artifact_and_approval_pending(
        self, capsys, cli_root, monkeypatch,
    ):
        _mock_provider(monkeypatch, cli_root)
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "AI 助手")

        rc, out, err = run_cli(
            capsys, cli_root, "product", "generate", "PI-001",
            "--type", "prd", "--provider", "mock",
        )
        assert rc == 0, err
        assert "✔ 生成 prd Artifact ART-" in out
        assert "status     completed" in out
        assert "等待人工批准" in out  # PRD mandatory → approval pending
        assert "product.generation.completed seq=" in out

        # 事件链: started → selected → execution.* → completed → approval.required
        store = open_events(cli_root)
        types = event_types(store)
        store.close()
        assert "product.generation.started" in types
        assert "provider.selected" in types
        assert "provider.execution.completed" in types
        assert "product.generation.completed" in types
        assert "approval.required" in types
        # 单一 completed 事件 (双事件回归)
        assert types.count("product.generation.completed") == 1

    def test_generate_json_shape(self, capsys, cli_root, monkeypatch):
        _mock_provider(monkeypatch, cli_root)
        run_cli(capsys, cli_root, "product", "idea", "create", "--title", "t")
        rc, out, _ = run_cli(
            capsys, cli_root, "--json", "product", "generate", "PI-001",
            "--type", "research", "--provider", "mock",
        )
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True
        assert data["artifact"]["type"] == "research"
        assert data["artifact"]["status"] == "completed"
        assert data["artifact"]["provider_id"] == "mock"
        assert data["approval"] is None  # research 无默认门
        assert data["context"]["provider_id"] == "mock"
        assert data["event_seq"] >= 1

    def test_generate_missing_idea_rc7(self, capsys, cli_root, monkeypatch):
        _mock_provider(monkeypatch, cli_root)
        rc, _, err = run_cli(
            capsys, cli_root, "product", "generate", "PI-999",
            "--type", "research", "--provider", "mock",
        )
        assert rc == 7
        assert "idea not found" in err

    def test_generate_invalid_type_usage_error(self, cli_root):
        from cli.main import main

        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "product", "generate", "PI-001",
                  "--type", "architecture"])
        assert exc.value.code == 2


class TestExperienceCli:
    def test_experience_record_and_list(self, capsys, cli_root):
        # 服务层 seed idea + Artifact (CLI 未暴露 create_artifact; generate 需 mock 注入)
        from product.service import ProductService
        from product.store import ProductStore

        svc = ProductService(ProductStore(cli_root / "product"))
        idea = svc.create_idea("AI 助手")
        artifact = svc.create_artifact(
            "prd", content={"content": "x"}, provider_id="mock",
            confidence=0.6, idea_id=idea.id, status="completed",
        )

        rc, out, err = run_cli(
            capsys, cli_root, "product", "experience", "record", artifact.id,
            "--rating", "4", "--approved", "true", "--comment", "很棒", "--by", "reviewer",
        )
        assert rc == 0, err
        assert "✔ 经验已记录" in out
        assert "rating     4" in out
        assert "product.experience.recorded seq=" in out

        rc, out, err = run_cli(
            capsys, cli_root, "product", "experience", "list",
        )
        assert rc == 0, err
        assert "1 experiences" in out
        assert "prd" in out

        # 过滤 + 事件审计 (ADR-0002: 读命令产生事件)
        rc, out, _ = run_cli(
            capsys, cli_root, "product", "experience", "list", "--artifact-type", "prd",
        )
        assert rc == 0
        assert "1 experiences" in out
        store = open_events(cli_root)
        types = event_types(store)
        store.close()
        assert "product.experience.recorded" in types
        assert "product.experience.viewed" in types

    def test_experience_record_missing_artifact_rc7(self, capsys, cli_root):
        rc, _, err = run_cli(
            capsys, cli_root, "product", "experience", "record", "ART-999", "--rating", "3",
        )
        assert rc == 7
        assert "artifact not found" in err
