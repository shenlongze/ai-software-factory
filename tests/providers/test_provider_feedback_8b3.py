"""test_provider_feedback_8b3.py — Provider 人工反馈接口预留 (Phase 8B-3, ADR-0025)。

覆盖 providers/feedback.py (Provider Intelligence Loop 最后一环: Human Feedback):
- ProviderFeedback 模型: 默认值 / rating 1-5 整数校验 (0/6/非 int/bool 拒绝) /
  comment strip 空串 → None / provider_id sane / id uuid / to_dict / created_at 默认
- FeedbackStore: add/list 升序/count/clear/list_for_provider/跨实例持久化/
  独立数据空间 feedback.json (与 catalog.json/usage.json 分离) / 原子写 /
  损坏失败安全三态 (JSON 坏/结构坏/单条坏跳过) / 从损坏文件重建
- record_provider_feedback 事件: provider.feedback.created payload 契约
  (provider_id/rating/approved + execution_id/task_id/comment 可选; logger None → None)
"""

from __future__ import annotations

import json

import pytest

from events.models import EventType
from providers.feedback import FeedbackStore, ProviderFeedback
from providers.events import record_provider_feedback
from providers.store import ProviderStore
from providers.usage import UsageStore


def make_feedback(
    provider_id: str = "openai",
    *,
    rating: int = 4,
    comment: str | None = "表现不错",
    approved: bool = False,
    execution_id: str | None = "EX-001",
    task_id: str | None = "T-001",
) -> ProviderFeedback:
    return ProviderFeedback(
        provider_id=provider_id,
        execution_id=execution_id,
        task_id=task_id,
        rating=rating,
        comment=comment,
        approved=approved,
    )


# ------------------------------------------------------------------ ProviderFeedback 模型


class TestFeedbackModel:
    def test_defaults(self):
        f = ProviderFeedback(provider_id="openai")
        assert f.rating == 3
        assert f.comment is None
        assert f.approved is False
        assert f.execution_id is None
        assert f.task_id is None
        assert f.created_at  # 默认生成 UTC 时间戳

    def test_id_generated_uuid_hex(self):
        f = ProviderFeedback(provider_id="openai")
        assert len(f.id) == 32
        assert all(c in "0123456789abcdef" for c in f.id)

    def test_rating_in_range(self):
        for r in (1, 5):
            assert ProviderFeedback(provider_id="x", rating=r).rating == r

    def test_rating_zero_rejected(self):
        with pytest.raises(Exception):
            ProviderFeedback(provider_id="x", rating=0)

    def test_rating_six_rejected(self):
        with pytest.raises(Exception):
            ProviderFeedback(provider_id="x", rating=6)

    def test_rating_float_rejected(self):
        with pytest.raises(Exception):
            ProviderFeedback(provider_id="x", rating=4.5)

    def test_rating_bool_rejected(self):
        """bool 是 int 子类 — 显式拒绝 (rating 契约: 1-5 整数)。"""
        with pytest.raises(Exception):
            ProviderFeedback(provider_id="x", rating=True)

    def test_provider_id_sane(self):
        with pytest.raises(Exception):
            ProviderFeedback(provider_id="../evil")

    def test_comment_whitespace_becomes_none(self):
        assert ProviderFeedback(provider_id="x", comment="   ").comment is None
        assert ProviderFeedback(provider_id="x", comment="").comment is None

    def test_comment_stripped(self):
        assert ProviderFeedback(provider_id="x", comment="  好评  ").comment == "好评"

    def test_to_dict(self):
        d = make_feedback().to_dict()
        assert d["provider_id"] == "openai"
        assert d["rating"] == 4
        assert d["approved"] is False
        assert d["comment"] == "表现不错"
        assert d["execution_id"] == "EX-001"
        assert d["task_id"] == "T-001"


# ------------------------------------------------------------------ FeedbackStore


class TestFeedbackStoreBasics:
    def test_add_returns_record(self, providers_dir):
        store = FeedbackStore(providers_dir)
        f = make_feedback()
        assert store.add(f) is f

    def test_list_sorted_by_created_at(self, providers_dir):
        store = FeedbackStore(providers_dir)
        store.add(make_feedback(provider_id="a"))
        store.add(make_feedback(provider_id="b"))
        assert [f.provider_id for f in store.list()] == ["a", "b"]

    def test_count(self, providers_dir):
        store = FeedbackStore(providers_dir)
        assert store.count() == 0
        store.add(make_feedback())
        assert store.count() == 1

    def test_clear(self, providers_dir):
        store = FeedbackStore(providers_dir)
        store.add(make_feedback())
        store.clear()
        assert store.count() == 0
        assert store.path.exists()

    def test_list_for_provider_filters(self, providers_dir):
        store = FeedbackStore(providers_dir)
        store.add(make_feedback(provider_id="openai"))
        store.add(make_feedback(provider_id="claude"))
        store.add(make_feedback(provider_id="openai"))
        assert len(store.list_for_provider("openai")) == 2
        assert len(store.list_for_provider("claude")) == 1
        assert store.list_for_provider("none") == []

    def test_persists_across_instances(self, providers_dir):
        FeedbackStore(providers_dir).add(make_feedback())
        assert FeedbackStore(providers_dir).count() == 1

    def test_independent_file(self, providers_dir):
        """feedback.json 独立于 catalog.json / usage.json (三数据空间分离)。"""
        from providers.models import ProviderDefinition
        from providers.usage import ProviderUsage

        ProviderStore(providers_dir).save_definition(
            ProviderDefinition(id="openai", name="OpenAI"),
        )
        UsageStore(providers_dir).record(ProviderUsage(provider_id="openai"))
        store = FeedbackStore(providers_dir)
        store.add(make_feedback())
        assert store.path.exists()
        assert (providers_dir / "catalog.json").exists()
        assert (providers_dir / "usage.json").exists()
        # 删除 feedback 文件 → 目录与用量不受影响
        store.path.unlink()
        assert ProviderStore(providers_dir).list_definitions()[0].id == "openai"
        assert UsageStore(providers_dir).count() == 1


class TestFeedbackStoreAtomicWrite:
    def test_no_tmp_leftover(self, providers_dir):
        store = FeedbackStore(providers_dir)
        store.add(make_feedback())
        assert [p for p in providers_dir.iterdir() if p.name.endswith(".tmp")] == []

    def test_write_uses_replace(self, providers_dir, monkeypatch):
        import os

        store = FeedbackStore(providers_dir)
        calls = []
        real_replace = os.replace

        def fake_replace(src, dst):
            calls.append((str(src), str(dst)))
            return real_replace(src, dst)

        monkeypatch.setattr("providers.feedback.os.replace", fake_replace)
        store.add(make_feedback())
        assert len(calls) == 1
        assert calls[0][0].endswith(".tmp")
        assert calls[0][1].endswith("feedback.json")

    def test_file_format_single_section(self, providers_dir):
        store = FeedbackStore(providers_dir)
        store.add(make_feedback())
        raw = json.loads(store.path.read_text(encoding="utf-8"))
        assert set(raw.keys()) == {"records"}
        assert len(raw["records"]) == 1


class TestFeedbackStoreCorruptionFailSafe:
    @pytest.fixture(autouse=True)
    def _dir_ready(self, providers_dir):
        providers_dir.mkdir(parents=True, exist_ok=True)
        yield

    def test_missing_file_empty(self, providers_dir):
        assert FeedbackStore(providers_dir).list() == []

    def test_bad_json_returns_empty(self, providers_dir):
        (providers_dir / "feedback.json").write_text("{nope!!", encoding="utf-8")
        assert FeedbackStore(providers_dir).list() == []
        assert FeedbackStore(providers_dir).count() == 0

    def test_wrong_structure_returns_empty(self, providers_dir):
        (providers_dir / "feedback.json").write_text('{"items": []}', encoding="utf-8")
        assert FeedbackStore(providers_dir).list() == []

    def test_corrupt_record_skipped_others_kept(self, providers_dir):
        good = make_feedback(provider_id="GOOD").to_dict()
        bad = {"provider_id": "openai", "rating": 99}  # rating 越界校验失败
        (providers_dir / "feedback.json").write_text(
            json.dumps({"records": [good, bad]}, ensure_ascii=False),
            encoding="utf-8",
        )
        records = FeedbackStore(providers_dir).list()
        assert [f.provider_id for f in records] == ["GOOD"]

    def test_add_rebuilds_from_corrupt(self, providers_dir):
        (providers_dir / "feedback.json").write_text("garbage!!", encoding="utf-8")
        store = FeedbackStore(providers_dir)
        store.add(make_feedback(provider_id="NEW"))
        assert [f.provider_id for f in store.list()] == ["NEW"]

    def test_read_commands_never_fail(self, providers_dir):
        (providers_dir / "feedback.json").write_text("{broken", encoding="utf-8")
        store = FeedbackStore(providers_dir)
        assert store.count() == 0
        assert store.list() == []
        assert store.list_for_provider("openai") == []


# ------------------------------------------------------------------ provider.feedback.created 事件


class TestFeedbackEvent:
    def test_payload_contract(self, logger):
        f = make_feedback(rating=5, approved=True, comment="强烈推荐", execution_id="EX-9", task_id="T-9")
        ev = record_provider_feedback(logger, feedback=f)
        assert ev is not None
        assert ev.type is EventType.PROVIDER_FEEDBACK_CREATED
        assert ev.payload["provider_id"] == "openai"
        assert ev.payload["rating"] == 5
        assert ev.payload["approved"] is True
        assert ev.payload["execution_id"] == "EX-9"
        assert ev.payload["task_id"] == "T-9"
        assert ev.payload["comment"] == "强烈推荐"

    def test_optional_keys_omitted(self, logger):
        f = ProviderFeedback(provider_id="openai", rating=3)
        ev = record_provider_feedback(logger, feedback=f)
        assert "execution_id" not in ev.payload
        assert "task_id" not in ev.payload
        assert "comment" not in ev.payload
        assert ev.payload["rating"] == 3
        assert ev.payload["approved"] is False

    def test_none_logger_returns_none(self):
        assert record_provider_feedback(None, feedback=make_feedback()) is None

    def test_event_type_registered(self):
        assert EventType.PROVIDER_FEEDBACK_CREATED.value == "provider.feedback.created"

    def test_source_default_and_override(self, logger):
        ev = record_provider_feedback(logger, feedback=make_feedback())
        assert ev.source == "provider_registry"
        ev2 = record_provider_feedback(logger, feedback=make_feedback(), source="cli")
        assert ev2.source == "cli"

    def test_store_and_event_roundtrip(self, providers_dir, logger):
        """链: FeedbackStore.add → record_provider_feedback → 事件可查。"""
        store = FeedbackStore(providers_dir)
        f = store.add(make_feedback(rating=5, approved=True))
        ev = record_provider_feedback(logger, feedback=f)
        assert ev.payload["provider_id"] == "openai"
        assert store.list_for_provider("openai")[0].rating == 5
