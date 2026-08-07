"""tests/exec/test_exec_capability.py — Model Capability Registry 单元测试 (Sprint 5 T5.4)。

覆盖 (全部纯本地, 零 LLM 零网络):
- ModelCapability: 创建 (最小/全评分) / provider+model 必填 (缺失/空白拒绝) /
  7 项评分 0-1 clamp (越界钳制/非法输入中性 0) / extra=forbid /
  to_dict↔from_dict round-trip / scores 属性 / score() 单项查询
- CapabilityRegistry CRUD: register (ModelCapability/dict)/get/has/list 排序/
  count/remove/upsert 覆盖 (updated_at 刷新, created_at 保留)
- find_by_capability: 命中/阈值过滤/降序排序/未知能力名 ValueError/无命中空
- 持久化: save→reload / 原子写无残留 tmp / 损坏文件失败安全空 / 单条坏跳过 /
  缺文件空 / 内存模式不落盘 / seed_defaults (内置声明式配置, 不覆盖已有)
- 快照: 已知模型冻结 / 未知模型 {} / registry None {} (中性不臆造)
- ModelExperienceStats: 记录/成功率/按任务类型/汇总/总量/round-trip/
  空 model 跳过/批量 / 禁自动改分强断言 (喂任意多失败 → 注册表评分逐位不变,
  评分唯一写入口 = register)

basename 唯一 (test_exec_* 前缀); helper 复用 tests/exec/exec_helpers.py。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from exec.capability import (
    CAPABILITY_SCORES,
    DEFAULT_CONFIG_FILE,
    ModelCapability,
    ModelExperienceStats,
    CapabilityRegistry,
    capability_key,
    capability_snapshot,
    load_default_config,
)
from exec.candidate import ExecutionCandidate


def make_capability(**overrides: Any) -> ModelCapability:
    """能力档案工厂 (唯一缺省键; 显式传参覆盖)。"""
    defaults: dict[str, Any] = {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "coding_score": 0.6,
        "reasoning_score": 0.8,
        "stability_score": 0.3,
        "context_score": 0.7,
        "tool_use_score": 0.5,
        "cost_score": 0.9,
        "latency_score": 0.8,
    }
    defaults.update(overrides)
    return ModelCapability(**defaults)


def make_stats_registry() -> tuple[CapabilityRegistry, ModelExperienceStats]:
    """内存 registry + stats (禁自动改分断言用)。"""
    reg = CapabilityRegistry()
    reg.register(make_capability())
    stats = ModelExperienceStats()
    return reg, stats


# ================================================================ ModelCapability 创建/校验

class TestModelCapabilityCreate:
    def test_minimal_creation(self) -> None:
        cap = ModelCapability(provider="openai", model="gpt-x")
        assert cap.provider == "openai"
        assert cap.model == "gpt-x"
        assert cap.scores == {name: 0.0 for name in CAPABILITY_SCORES}

    def test_full_scores(self) -> None:
        cap = make_capability(
            coding_score=0.5, reasoning_score=0.9, stability_score=0.4,
            context_score=0.8, tool_use_score=0.7, cost_score=0.6,
            latency_score=0.2,
        )
        assert cap.coding_score == 0.5
        assert cap.reasoning_score == 0.9
        assert cap.stability_score == 0.4
        assert cap.context_score == 0.8
        assert cap.tool_use_score == 0.7
        assert cap.cost_score == 0.6
        assert cap.latency_score == 0.2

    def test_provider_required(self) -> None:
        with pytest.raises(ValidationError):
            ModelCapability(model="deepseek-v4-flash")

    def test_model_required(self) -> None:
        with pytest.raises(ValidationError):
            ModelCapability(provider="deepseek")

    def test_blank_provider_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelCapability(provider="  ", model="deepseek-v4-flash")

    def test_blank_model_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelCapability(provider="deepseek", model="")

    def test_provider_stripped(self) -> None:
        cap = ModelCapability(provider="  deepseek  ", model="m")
        assert cap.provider == "deepseek"

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ModelCapability(provider="p", model="m", bogus=1)


class TestModelCapabilityScoreClamp:
    def test_clamp_high(self) -> None:
        cap = make_capability(coding_score=1.5)
        assert cap.coding_score == 1.0

    def test_clamp_low(self) -> None:
        cap = make_capability(coding_score=-0.5)
        assert cap.coding_score == 0.0

    def test_clamp_all_scores(self) -> None:
        cap = make_capability(
            coding_score=2.0, reasoning_score=-1.0, stability_score=99,
            context_score=-99, tool_use_score=0.5, cost_score=1.1,
            latency_score=0.0,
        )
        assert cap.scores == {
            "coding_score": 1.0, "reasoning_score": 0.0, "stability_score": 1.0,
            "context_score": 0.0, "tool_use_score": 0.5, "cost_score": 1.0,
            "latency_score": 0.0,
        }

    def test_clamp_non_numeric_neutral(self) -> None:
        cap = make_capability(coding_score="abc")
        assert cap.coding_score == 0.0

    def test_clamp_none_neutral(self) -> None:
        cap = make_capability(coding_score=None)
        assert cap.coding_score == 0.0

    def test_boundary_values_kept(self) -> None:
        cap = make_capability(coding_score=0.0, reasoning_score=1.0)
        assert cap.coding_score == 0.0
        assert cap.reasoning_score == 1.0


class TestModelCapabilitySerialize:
    def test_roundtrip(self) -> None:
        cap = make_capability()
        restored = ModelCapability.from_dict(cap.to_dict())
        assert restored.to_dict() == cap.to_dict()

    def test_to_dict_json_friendly(self) -> None:
        data = make_capability().to_dict()
        json.dumps(data)  # 必须可 JSON 序列化
        assert set(data) == set(CAPABILITY_SCORES) | {
            "provider", "model", "created_at", "updated_at",
        }

    def test_scores_property(self) -> None:
        cap = make_capability()
        assert list(cap.scores) == list(CAPABILITY_SCORES)
        assert cap.scores["cost_score"] == 0.9

    def test_score_getter_known(self) -> None:
        cap = make_capability()
        assert cap.score("coding_score") == 0.6

    def test_score_getter_unknown_neutral(self) -> None:
        cap = make_capability()
        assert cap.score("bogus_score") == 0.0


# ================================================================ Registry CRUD

class TestRegistryCrud:
    def test_register_get(self) -> None:
        reg = CapabilityRegistry()
        cap = make_capability()
        reg.register(cap)
        got = reg.get("deepseek", "deepseek-v4-flash")
        assert got is not None
        assert got.to_dict() == cap.to_dict()

    def test_register_dict(self) -> None:
        reg = CapabilityRegistry()
        reg.register(make_capability().to_dict())
        assert reg.get("deepseek", "deepseek-v4-flash") is not None

    def test_get_missing_none(self) -> None:
        reg = CapabilityRegistry()
        assert reg.get("deepseek", "nope") is None

    def test_has(self) -> None:
        reg = CapabilityRegistry()
        assert not reg.has("deepseek", "deepseek-v4-flash")
        reg.register(make_capability())
        assert reg.has("deepseek", "deepseek-v4-flash")

    def test_list_sorted(self) -> None:
        reg = CapabilityRegistry()
        reg.register(make_capability(model="zeta"))
        reg.register(make_capability(model="alpha"))
        assert [c.model for c in reg.list()] == ["alpha", "zeta"]

    def test_count(self) -> None:
        reg = CapabilityRegistry()
        assert reg.count() == 0
        reg.register(make_capability())
        reg.register(make_capability(model="deepseek-v4-pro"))
        assert reg.count() == 2

    def test_remove(self) -> None:
        reg = CapabilityRegistry()
        reg.register(make_capability())
        assert reg.remove("deepseek", "deepseek-v4-flash") is True
        assert reg.count() == 0

    def test_remove_missing_false(self) -> None:
        reg = CapabilityRegistry()
        assert reg.remove("deepseek", "nope") is False

    def test_upsert_overwrites(self) -> None:
        reg = CapabilityRegistry()
        reg.register(make_capability(coding_score=0.6))
        reg.register(make_capability(coding_score=0.9))
        got = reg.get("deepseek", "deepseek-v4-flash")
        assert got is not None
        assert got.coding_score == 0.9
        assert reg.count() == 1

    def test_upsert_preserves_created_at(self) -> None:
        reg = CapabilityRegistry()
        first = reg.register(make_capability())
        original_created = first.created_at
        second = reg.register(make_capability(coding_score=0.9))
        assert second.created_at == original_created
        assert second.updated_at >= original_created

    def test_memory_mode_no_file(self, tmp_path: Path) -> None:
        reg = CapabilityRegistry(root=None)
        reg.register(make_capability())
        assert not (tmp_path / "model_capabilities.json").exists()


# ================================================================ find_by_capability

class TestFindByCapability:
    def _reg(self) -> CapabilityRegistry:
        reg = CapabilityRegistry()
        reg.register(make_capability(model="flash", coding_score=0.6, cost_score=0.9))
        reg.register(make_capability(model="pro", coding_score=0.7, cost_score=0.7))
        reg.register(make_capability(model="mini", coding_score=0.2, cost_score=0.4))
        return reg

    def test_hits_above_threshold(self) -> None:
        reg = self._reg()
        hits = reg.find_by_capability("coding_score", 0.5)
        assert {c.model for c in hits} == {"flash", "pro"}

    def test_min_score_zero_all(self) -> None:
        reg = self._reg()
        assert len(reg.find_by_capability("coding_score", 0.0)) == 3

    def test_no_hits_empty(self) -> None:
        reg = self._reg()
        assert reg.find_by_capability("coding_score", 0.95) == []

    def test_sorted_desc(self) -> None:
        reg = self._reg()
        hits = reg.find_by_capability("coding_score", 0.0)
        assert [c.model for c in hits] == ["pro", "flash", "mini"]

    def test_unknown_capability_raises(self) -> None:
        reg = self._reg()
        with pytest.raises(ValueError):
            reg.find_by_capability("bogus_score", 0.5)

    def test_min_score_clamped(self) -> None:
        reg = self._reg()
        # min_score 越界 → clamp [0,1]; 1.5 → 1.0 → 无命中
        assert reg.find_by_capability("coding_score", 1.5) == []
        # -1 → 0.0 → 全部命中
        assert len(reg.find_by_capability("coding_score", -1.0)) == 3


# ================================================================ Registry 持久化

class TestRegistryPersistence:
    def test_save_reload(self, tmp_path: Path) -> None:
        reg = CapabilityRegistry(tmp_path)
        reg.register(make_capability())
        reg.register(make_capability(model="deepseek-v4-pro", coding_score=0.7))
        reloaded = CapabilityRegistry(tmp_path)
        assert reloaded.count() == 2
        assert reloaded.get("deepseek", "deepseek-v4-flash").coding_score == 0.6

    def test_atomic_write_no_temp_left(self, tmp_path: Path) -> None:
        reg = CapabilityRegistry(tmp_path)
        reg.register(make_capability())
        leftovers = list(tmp_path.glob("*.tmp"))
        assert leftovers == []

    def test_corrupt_file_failsafe(self, tmp_path: Path) -> None:
        (tmp_path / "model_capabilities.json").write_text(
            "{not valid json!!", encoding="utf-8"
        )
        reg = CapabilityRegistry(tmp_path)
        assert reg.count() == 0  # 损坏 → 空表, 不抛

    def test_partial_corrupt_skips_bad(self, tmp_path: Path) -> None:
        good = make_capability().to_dict()
        bad = make_capability(model="bad").to_dict()
        bad.pop("provider")  # 必填缺失 → 单条校验失败 → 跳过
        (tmp_path / "model_capabilities.json").write_text(
            json.dumps([good, bad]), encoding="utf-8"
        )
        reg = CapabilityRegistry(tmp_path)
        assert reg.count() == 1
        assert reg.get("deepseek", "deepseek-v4-flash") is not None

    def test_missing_file_empty(self, tmp_path: Path) -> None:
        reg = CapabilityRegistry(tmp_path)
        assert reg.count() == 0

    def test_non_list_root_failsafe(self, tmp_path: Path) -> None:
        (tmp_path / "model_capabilities.json").write_text(
            json.dumps({"oops": "dict root"}), encoding="utf-8"
        )
        reg = CapabilityRegistry(tmp_path)
        assert reg.count() == 0

    def test_save_overwrites(self, tmp_path: Path) -> None:
        reg = CapabilityRegistry(tmp_path)
        reg.register(make_capability(coding_score=0.6))
        reg2 = CapabilityRegistry(tmp_path)
        reg2.register(make_capability(coding_score=0.9))
        reg3 = CapabilityRegistry(tmp_path)
        assert reg3.count() == 1
        assert reg3.get("deepseek", "deepseek-v4-flash").coding_score == 0.9

    def test_remove_persists(self, tmp_path: Path) -> None:
        reg = CapabilityRegistry(tmp_path)
        reg.register(make_capability())
        reg.register(make_capability(model="deepseek-v4-pro"))
        reg.remove("deepseek", "deepseek-v4-flash")
        reloaded = CapabilityRegistry(tmp_path)
        assert reloaded.count() == 1
        assert reloaded.get("deepseek", "deepseek-v4-flash") is None


# ================================================================ 内置示例配置

class TestDefaultConfig:
    def test_default_config_file_exists(self) -> None:
        assert DEFAULT_CONFIG_FILE.is_file()

    def test_load_default_config_declarative(self) -> None:
        caps = load_default_config()
        assert len(caps) >= 2
        for cap in caps:
            assert cap.provider
            assert cap.model
            assert all(0.0 <= s <= 1.0 for s in cap.scores.values())

    def test_default_config_has_flash(self) -> None:
        caps = {c.model: c for c in load_default_config()}
        flash = caps.get("deepseek-v4-flash")
        assert flash is not None
        assert flash.stability_score == 0.3  # T5.1 设计: reasoning 耗尽风险低稳定
        assert flash.cost_score == 0.9

    def test_load_missing_file_failsafe(self, tmp_path: Path) -> None:
        assert load_default_config(tmp_path / "nope.json") == []

    def test_load_corrupt_file_failsafe(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("###", encoding="utf-8")
        assert load_default_config(bad) == []

    def test_seed_defaults(self, tmp_path: Path) -> None:
        reg = CapabilityRegistry(tmp_path, seed_defaults=True)
        assert reg.count() >= 2
        assert reg.get("deepseek", "deepseek-v4-flash") is not None

    def test_seed_defaults_not_overwrite(self, tmp_path: Path) -> None:
        reg = CapabilityRegistry(tmp_path)
        reg.register(make_capability(coding_score=0.99))
        added = reg.seed_defaults()
        assert added >= 1  # pro 新增
        assert reg.get("deepseek", "deepseek-v4-flash").coding_score == 0.99

    def test_seed_defaults_force(self, tmp_path: Path) -> None:
        reg = CapabilityRegistry(tmp_path)
        reg.register(make_capability(coding_score=0.99))
        reg.seed_defaults(force=True)
        assert reg.get("deepseek", "deepseek-v4-flash").coding_score == 0.6

    def test_seed_persists(self, tmp_path: Path) -> None:
        reg = CapabilityRegistry(tmp_path, seed_defaults=True)
        reloaded = CapabilityRegistry(tmp_path)
        assert reloaded.count() == reg.count()


# ================================================================ 快照

class TestSnapshot:
    def test_snapshot_known_model(self) -> None:
        reg = CapabilityRegistry()
        reg.register(make_capability())
        snap = reg.snapshot("deepseek", "deepseek-v4-flash")
        assert snap["provider"] == "deepseek"
        assert snap["model"] == "deepseek-v4-flash"
        assert snap["scores"]["cost_score"] == 0.9
        assert snap["captured_at"]

    def test_snapshot_unknown_model_neutral(self) -> None:
        reg = CapabilityRegistry()
        assert reg.snapshot("deepseek", "nope") == {}

    def test_snapshot_registry_none_neutral(self) -> None:
        assert capability_snapshot(None, "p", "m") == {}

    def test_snapshot_duck_typed_no_method(self) -> None:
        assert capability_snapshot(object(), "p", "m") == {}

    def test_snapshot_frozen_scores(self) -> None:
        reg = CapabilityRegistry()
        reg.register(make_capability(coding_score=0.6))
        snap = reg.snapshot("deepseek", "deepseek-v4-flash")
        reg.register(make_capability(coding_score=0.99))
        assert snap["scores"]["coding_score"] == 0.6  # 历史冻结, 不受后续影响


# ================================================================ ModelExperienceStats

class TestModelExperienceStats:
    def test_record_success_failure(self) -> None:
        stats = ModelExperienceStats()
        stats.record(provider="deepseek", model="deepseek-v4-flash", success=True)
        stats.record(provider="deepseek", model="deepseek-v4-flash", success=False)
        assert stats.attempts("deepseek", "deepseek-v4-flash") == 2
        assert stats.successes("deepseek", "deepseek-v4-flash") == 1
        assert stats.failures("deepseek", "deepseek-v4-flash") == 1

    def test_success_rate(self) -> None:
        stats = ModelExperienceStats()
        for _ in range(3):
            stats.record(provider="p", model="m", success=True)
        stats.record(provider="p", model="m", success=False)
        assert stats.success_rate("p", "m") == 0.75

    def test_success_rate_no_samples_none(self) -> None:
        stats = ModelExperienceStats()
        assert stats.success_rate("p", "m") is None

    def test_attempts_unknown_zero(self) -> None:
        stats = ModelExperienceStats()
        assert stats.attempts("p", "m") == 0
        assert stats.failures("p", "m") == 0

    def test_by_task_type(self) -> None:
        stats = ModelExperienceStats()
        stats.record(provider="p", model="m", success=True, task_type="bugfix")
        stats.record(provider="p", model="m", success=False, task_type="bugfix")
        stats.record(provider="p", model="m", success=True, task_type="feature")
        assert stats.attempts("p", "m", task_type="bugfix") == 2
        assert stats.success_rate("p", "m", task_type="bugfix") == 0.5
        assert stats.success_rate("p", "m", task_type="feature") == 1.0
        assert stats.attempts("p", "m", task_type="unknown") == 0

    def test_model_summary(self) -> None:
        stats = ModelExperienceStats()
        stats.record(provider="p", model="m", success=True, task_type="bugfix")
        stats.record(provider="p", model="m", success=False, task_type="bugfix")
        summary = stats.model_summary("p", "m")
        assert summary is not None
        assert summary["attempts"] == 2
        assert summary["successes"] == 1
        assert summary["failures"] == 1
        assert summary["success_rate"] == 0.5
        assert summary["by_task_type"]["bugfix"]["attempts"] == 2

    def test_model_summary_unknown_none(self) -> None:
        stats = ModelExperienceStats()
        assert stats.model_summary("p", "nope") is None

    def test_totals(self) -> None:
        stats = ModelExperienceStats()
        stats.record(provider="p", model="m", success=True)
        stats.record(provider="p", model="m", success=False)
        stats.record(provider="q", model="n", success=True)
        assert stats.totals() == {"attempts": 3, "successes": 2, "failures": 1}

    def test_keys_sorted(self) -> None:
        stats = ModelExperienceStats()
        stats.record(provider="b", model="m", success=True)
        stats.record(provider="a", model="m", success=True)
        assert stats.keys() == [("a", "m"), ("b", "m")]

    def test_skip_empty_model(self) -> None:
        stats = ModelExperienceStats()
        stats.record(provider="p", model="", success=True)
        stats.record(provider="p", model="  ", success=False)
        assert stats.totals() == {"attempts": 0, "successes": 0, "failures": 0}

    def test_roundtrip(self) -> None:
        stats = ModelExperienceStats()
        stats.record(provider="p", model="m", success=True, task_type="bugfix")
        stats.record(provider="p", model="m", success=False)
        restored = ModelExperienceStats(stats.to_dict())
        assert restored.to_dict() == stats.to_dict()
        assert restored.success_rate("p", "m") == stats.success_rate("p", "m")

    def test_from_dict_invalid_counts_clamped(self) -> None:
        stats = ModelExperienceStats(
            {"p::m": {"attempts": -5, "successes": "x", "failures": 2,
                      "by_task_type": {}}}
        )
        assert stats.attempts("p", "m") == 0
        assert stats.failures("p", "m") == 2

    def test_record_candidate(self) -> None:
        stats = ModelExperienceStats()
        ok = ExecutionCandidate(
            id="CAND-1", run_id="R-1", provider="deepseek",
            model="deepseek-v4-flash",
        )
        fail = ExecutionCandidate(
            id="CAND-2", run_id="R-2", provider="deepseek",
            model="deepseek-v4-flash", failure_reason="token_limit",
        )
        stats.record_candidate(ok, task_type="bugfix")
        stats.record_candidate(fail, task_type="bugfix")
        assert stats.attempts("deepseek", "deepseek-v4-flash") == 2
        assert stats.successes("deepseek", "deepseek-v4-flash") == 1

    def test_record_candidates_batch(self) -> None:
        stats = ModelExperienceStats()
        candidates = [
            ExecutionCandidate(id=f"CAND-{i}", run_id=f"R-{i}",
                               provider="p", model="m")
            for i in range(3)
        ]
        assert stats.record_candidates(candidates) == 3
        assert stats.totals()["attempts"] == 3


# ================================================================ 禁自动改分强断言

class TestNoAutoScoreChange:
    """铁律: 能力评分唯一写入口 = CapabilityRegistry.register (人工/Benchmark)。

    经验统计/执行流程永不触碰评分 — 第一阶段禁自动改分。
    """

    def test_stats_record_does_not_change_scores(self) -> None:
        reg, stats = make_stats_registry()
        before = reg.get("deepseek", "deepseek-v4-flash").to_dict()
        for _ in range(10):
            stats.record(provider="deepseek", model="deepseek-v4-flash",
                         success=False)
        after = reg.get("deepseek", "deepseek-v4-flash").to_dict()
        assert after == before

    def test_stats_candidates_do_not_change_scores(self) -> None:
        reg, stats = make_stats_registry()
        before = reg.get("deepseek", "deepseek-v4-flash").scores
        candidates = [
            ExecutionCandidate(id=f"CAND-{i}", run_id=f"R-{i}",
                               provider="deepseek", model="deepseek-v4-flash",
                               failure_reason="token_limit")
            for i in range(50)
        ]
        stats.record_candidates(candidates)
        after = reg.get("deepseek", "deepseek-v4-flash").scores
        assert after == before
        assert stats.failures("deepseek", "deepseek-v4-flash") == 50

    def test_stats_class_has_no_registry_write_api(self) -> None:
        # 结构断言: 统计类不暴露任何注册表写入入口 (register 只属于 Registry)
        assert not hasattr(ModelExperienceStats, "register")
        assert not hasattr(ModelExperienceStats, "seed_defaults")

    def test_only_register_changes_scores(self) -> None:
        reg = CapabilityRegistry()
        reg.register(make_capability(coding_score=0.6))
        reg.register(make_capability(coding_score=0.8))  # 唯一合法更新途径
        assert reg.get("deepseek", "deepseek-v4-flash").coding_score == 0.8

    def test_snapshot_never_mutates_registry(self) -> None:
        reg = CapabilityRegistry()
        reg.register(make_capability())
        before = reg.get("deepseek", "deepseek-v4-flash").to_dict()
        reg.snapshot("deepseek", "deepseek-v4-flash")
        reg.snapshot("deepseek", "unknown")
        after = reg.get("deepseek", "deepseek-v4-flash").to_dict()
        assert after == before
        assert reg.count() == 1

    def test_capability_key_utility(self) -> None:
        assert capability_key("deepseek", "deepseek-v4-flash") == \
            "deepseek::deepseek-v4-flash"
