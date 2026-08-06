"""test_provider_usage_8b2.py — ProviderUsage + UsageStore + PerformanceStats (Phase 8B-2, ADR-0024)。

覆盖:
- ProviderUsage 模型校验 (tokens/latency/cost 非负, provider_id sane, total_tokens)
- UsageStore: record/list 升序/count/clear/原子写 (临时文件 + os.replace)
- 损坏失败安全三态: JSON 坏 → 空; 结构坏 → 空; 单条坏 → 跳过保留他条
- append 从损坏文件重建 (失败安全)
- filter_by_period: day/week/all + 非法 period ValueError + 时间戳坏跳过
- stats_from_usage: 分组 (provider×model×version)/维度过滤/口径 (0 调用 0.0)
- 独立数据空间: usage.json 与 catalog.json 分离
"""

from __future__ import annotations

import json

import pytest

from providers.costs import ProviderCostModel
from providers.models import ProviderDefinition
from providers.store import ProviderStore
from providers.usage import (
    PERIODS,
    ProviderPerformanceStats,
    ProviderUsage,
    UsageStore,
    filter_by_period,
    stats_from_usage,
)


def make_usage(
    provider_id: str = "openai",
    *,
    model: str | None = "gpt-4o",
    version: str | None = "1.0",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    estimated_cost: float = 0.001,
    latency_ms: int = 250,
    success: bool = True,
    error: str | None = None,
    execution_id: str | None = "EX-001",
    recorded_at: str | None = None,
) -> ProviderUsage:
    return ProviderUsage(
        provider_id=provider_id,
        execution_id=execution_id,
        model=model,
        version=version,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost=estimated_cost,
        latency_ms=latency_ms,
        success=success,
        error=error,
        recorded_at=recorded_at or "2026-08-06T10:00:00.000000Z",
    )


class TestProviderUsageModel:
    def test_defaults(self):
        u = ProviderUsage(provider_id="x")
        assert u.success is True
        assert u.error is None
        assert u.execution_id is None
        assert u.model is None
        assert u.version is None
        assert u.prompt_tokens == 0
        assert u.completion_tokens == 0

    def test_total_tokens(self):
        u = make_usage(prompt_tokens=100, completion_tokens=50)
        assert u.total_tokens == 150

    def test_negative_tokens_rejected(self):
        with pytest.raises(Exception):
            make_usage(prompt_tokens=-1)

    def test_negative_latency_rejected(self):
        with pytest.raises(Exception):
            make_usage(latency_ms=-5)

    def test_negative_cost_rejected(self):
        with pytest.raises(Exception):
            make_usage(estimated_cost=-0.1)

    def test_provider_id_sane(self):
        with pytest.raises(Exception):
            ProviderUsage(provider_id="../evil")

    def test_id_generated(self):
        u = ProviderUsage(provider_id="x")
        assert len(u.id) == 32  # uuid4 hex

    def test_to_dict(self):
        d = make_usage().to_dict()
        assert d["provider_id"] == "openai"
        assert d["prompt_tokens"] == 100
        assert d["success"] is True

    def test_recorded_at_format(self):
        u = make_usage(recorded_at="2026-08-06T10:00:00.000000Z")
        assert u.recorded_at == "2026-08-06T10:00:00.000000Z"


class TestUsageStoreBasics:
    def test_record_appends_and_returns(self, providers_dir):
        store = UsageStore(providers_dir)
        u = make_usage(execution_id="EX-001")
        returned = store.record(u)
        assert returned is u
        assert store.count() == 1

    def test_list_sorted_by_recorded_at(self, providers_dir):
        store = UsageStore(providers_dir)
        store.record(make_usage(execution_id="A", recorded_at="2026-08-01T00:00:00.000000Z"))
        store.record(make_usage(execution_id="B", recorded_at="2026-08-03T00:00:00.000000Z"))
        store.record(make_usage(execution_id="C", recorded_at="2026-08-02T00:00:00.000000Z"))
        ids = [r.execution_id for r in store.list()]
        assert ids == ["A", "C", "B"]

    def test_count_empty(self, providers_dir):
        assert UsageStore(providers_dir).count() == 0

    def test_clear(self, providers_dir):
        store = UsageStore(providers_dir)
        store.record(make_usage())
        store.clear()
        assert store.count() == 0
        assert store.path.exists()

    def test_persists_across_instances(self, providers_dir):
        UsageStore(providers_dir).record(make_usage())
        assert UsageStore(providers_dir).count() == 1

    def test_file_format_single_section(self, providers_dir):
        store = UsageStore(providers_dir)
        store.record(make_usage(execution_id="EX-1"))
        raw = json.loads(store.path.read_text(encoding="utf-8"))
        assert set(raw.keys()) == {"records"}
        assert len(raw["records"]) == 1

    def test_independent_from_catalog(self, providers_dir):
        """usage.json 与 catalog.json 独立数据空间 — 删除 usage 不影响目录。"""
        pstore = ProviderStore(providers_dir)
        pstore.save_definition(ProviderDefinition(id="openai", name="OpenAI"))
        ustore = UsageStore(providers_dir)
        ustore.record(make_usage())
        assert ustore.path.exists()
        assert (providers_dir / "catalog.json").exists()
        # 删除 usage 文件 → ProviderStore 不受影响
        ustore.path.unlink()
        assert pstore.list_definitions()[0].id == "openai"


class TestUsageStoreAtomicWrite:
    def test_atomic_write_no_tmp_leftover(self, providers_dir):
        store = UsageStore(providers_dir)
        store.record(make_usage())
        leftovers = [p for p in providers_dir.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []
        assert store.path.exists()

    def test_write_uses_replace(self, providers_dir, monkeypatch):
        """原子写: 临时文件 + os.replace (同 ProviderStore 模式)。"""
        import os

        store = UsageStore(providers_dir)
        calls = []

        real_replace = os.replace

        def fake_replace(src, dst):
            calls.append((str(src), str(dst)))
            return real_replace(src, dst)

        monkeypatch.setattr("providers.usage.os.replace", fake_replace)
        store.record(make_usage())
        assert len(calls) == 1
        assert calls[0][0].endswith(".tmp")
        assert calls[0][1].endswith("usage.json")


class TestUsageStoreCorruptionFailSafe:
    @pytest.fixture(autouse=True)
    def _corrupt_dir_ready(self, providers_dir):
        """损坏文件须真实存在才测得到失败安全 — 预建目录 (backend-developer
        skill 陷阱: 损坏文件测试先 mkdir(parents=True); 父目录缺失时
        Path.write_text 直接 FileNotFoundError)。类内 autouse, 不影响
        TestWrite::test_dir_created_on_first_write 对 providers_dir
        不存在的断言 (目录由首次原子写自动创建)。"""
        providers_dir.mkdir(parents=True, exist_ok=True)
        yield

    def test_missing_file_empty(self, providers_dir):
        assert UsageStore(providers_dir).list() == []

    def test_bad_json_returns_empty(self, providers_dir):
        (providers_dir / "usage.json").write_text("{not json!!", encoding="utf-8")
        assert UsageStore(providers_dir).list() == []

    def test_wrong_structure_returns_empty(self, providers_dir):
        (providers_dir / "usage.json").write_text('{"items": []}', encoding="utf-8")
        assert UsageStore(providers_dir).list() == []

    def test_corrupt_record_skipped_others_kept(self, providers_dir):
        """单条校验失败 → 跳过该条, 保留可读部分 (失败安全不拖垮整库)。"""
        good = make_usage(execution_id="GOOD").to_dict()
        bad = {"provider_id": "openai", "prompt_tokens": -5}  # 负 tokens 校验失败
        (providers_dir / "usage.json").write_text(
            json.dumps({"records": [good, bad]}, ensure_ascii=False),
            encoding="utf-8",
        )
        records = UsageStore(providers_dir).list()
        assert [r.execution_id for r in records] == ["GOOD"]

    def test_append_rebuilds_from_corrupt(self, providers_dir):
        """损坏文件上 append → 从空重建 (失败安全), 新记录可读。"""
        (providers_dir / "usage.json").write_text("garbage!!", encoding="utf-8")
        store = UsageStore(providers_dir)
        store.record(make_usage(execution_id="NEW"))
        records = store.list()
        assert [r.execution_id for r in records] == ["NEW"]

    def test_read_commands_never_fail_on_corrupt(self, providers_dir):
        """读命令永不因 usage 文件失败 (count/list 全走失败安全)。"""
        (providers_dir / "usage.json").write_text("{broken", encoding="utf-8")
        store = UsageStore(providers_dir)
        assert store.count() == 0
        assert store.list() == []


class TestFilterByPeriod:
    def test_periods_enum(self):
        assert PERIODS == ("day", "week", "all")

    def test_all_no_filter(self):
        records = [make_usage(recorded_at="2026-01-01T00:00:00.000000Z")]
        assert filter_by_period(records, "all") == records

    def test_invalid_period_raises(self):
        with pytest.raises(ValueError):
            filter_by_period([], "month")

    def test_day_today_included(self):
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        records = [make_usage(recorded_at=today)]
        assert len(filter_by_period(records, "day")) == 1

    def test_day_old_excluded(self):
        records = [make_usage(recorded_at="2020-01-01T00:00:00.000000Z")]
        assert filter_by_period(records, "day") == []

    def test_week_includes_recent(self):
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        recent = (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        records = [make_usage(recorded_at=recent)]
        assert len(filter_by_period(records, "week")) == 1

    def test_week_excludes_old(self):
        records = [make_usage(recorded_at="2020-01-01T00:00:00.000000Z")]
        assert filter_by_period(records, "week") == []

    def test_unparseable_timestamp_skipped(self):
        records = [make_usage(recorded_at="not-a-timestamp")]
        assert filter_by_period(records, "day") == []
        assert filter_by_period(records, "all") == records  # all 不过滤


class TestStatsFromUsage:
    def test_empty_records(self):
        assert stats_from_usage([]) == []

    def test_single_group(self):
        records = [make_usage(latency_ms=100, prompt_tokens=10, completion_tokens=20, estimated_cost=0.5)]
        stats = stats_from_usage(records)
        assert len(stats) == 1
        s = stats[0]
        assert s.provider_id == "openai"
        assert s.model == "gpt-4o"
        assert s.version == "1.0"
        assert s.calls == 1
        assert s.success_rate == 1.0
        assert s.avg_latency_ms == 100.0
        assert s.total_tokens == 30
        assert s.total_cost == 0.5

    def test_groups_by_provider_model_version(self):
        """(provider, model, version) 三维度分组。"""
        records = [
            make_usage(provider_id="openai", model="gpt-4o", version="1.0"),
            make_usage(provider_id="openai", model="gpt-4o-mini", version="1.0"),
            make_usage(provider_id="openai", model="gpt-4o", version="2.0"),
            make_usage(provider_id="claude", model="sonnet", version="1.0"),
        ]
        stats = stats_from_usage(records)
        keys = [(s.provider_id, s.model, s.version) for s in stats]
        assert len(stats) == 4
        assert ("openai", "gpt-4o", "1.0") in keys
        assert ("claude", "sonnet", "1.0") in keys

    def test_none_model_bucket(self):
        """model/version None → 归入 None 桶。"""
        records = [make_usage(model=None, version=None)]
        stats = stats_from_usage(records)
        assert stats[0].model is None
        assert stats[0].version is None

    def test_success_rate_mixed(self):
        records = [
            make_usage(success=True),
            make_usage(success=False, error="boom"),
            make_usage(success=True),
        ]
        stats = stats_from_usage(records)
        assert stats[0].calls == 3
        assert stats[0].success_rate == round(2 / 3, 4)

    def test_failure_recorded(self):
        """失败调用也记录 (success=False + error) — 成功率聚合数据基础。"""
        records = [make_usage(success=False, error="timeout")]
        stats = stats_from_usage(records)
        assert stats[0].calls == 1
        assert stats[0].success_rate == 0.0

    def test_avg_latency(self):
        records = [make_usage(latency_ms=100), make_usage(latency_ms=300)]
        stats = stats_from_usage(records)
        assert stats[0].avg_latency_ms == 200.0

    def test_provider_filter(self):
        records = [
            make_usage(provider_id="openai"),
            make_usage(provider_id="claude"),
        ]
        stats = stats_from_usage(records, provider_id="openai")
        assert [s.provider_id for s in stats] == ["openai"]

    def test_model_filter(self):
        records = [
            make_usage(model="gpt-4o"),
            make_usage(model="gpt-4o-mini"),
        ]
        stats = stats_from_usage(records, model="gpt-4o-mini")
        assert [s.model for s in stats] == ["gpt-4o-mini"]

    def test_version_filter(self):
        records = [
            make_usage(version="1.0"),
            make_usage(version="2.0"),
        ]
        stats = stats_from_usage(records, version="2.0")
        assert [s.version for s in stats] == ["2.0"]

    def test_period_filter_applied(self):
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        records = [
            make_usage(provider_id="openai", recorded_at=today),
            make_usage(provider_id="openai", recorded_at="2020-01-01T00:00:00.000000Z"),
        ]
        stats = stats_from_usage(records, period="day")
        assert len(stats) == 1
        assert stats[0].period == "day"

    def test_sorted_by_group_key(self):
        records = [
            make_usage(provider_id="claude"),
            make_usage(provider_id="openai"),
            make_usage(provider_id="anthropic"),
        ]
        stats = stats_from_usage(records)
        assert [s.provider_id for s in stats] == ["anthropic", "claude", "openai"]

    def test_total_cost_accumulates(self):
        records = [
            make_usage(estimated_cost=0.1),
            make_usage(estimated_cost=0.2),
            make_usage(estimated_cost=0.3),
        ]
        stats = stats_from_usage(records)
        assert stats[0].total_cost == 0.6

    def test_period_field_reflected(self):
        records = [make_usage()]
        stats = stats_from_usage(records, period="week")
        assert stats[0].period == "week"


class TestStatsModel:
    def test_to_dict(self):
        s = ProviderPerformanceStats(provider_id="openai", calls=2)
        d = s.to_dict()
        assert d["provider_id"] == "openai"
        assert d["calls"] == 2
        assert d["success_rate"] == 0.0
