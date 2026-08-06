"""test_provider_store.py — ProviderStore: 定义 JSON 持久化 (独立文件, 原子写)。

覆盖: 独立数据空间 (.factory/providers/catalog.json — 与 runtimes/catalog.json
分离) / 缺失文件空库 / 双节格式 (definitions + default) / 原子写 (os.replace,
无半写文件) / 损坏检测 (JSON 解析失败 / 结构不符 / 模型校验失败 →
CorruptProviderStoreError, 绝不静默返回空) / upsert 覆盖 / remove 不存在返回
False / default 读写 / 按 id 排序 (审计友好)。

设计依据: providers/store.py (Phase 8A, ADR-0022), 参照 runtimes/store.py 模式。
"""

from __future__ import annotations

import json

import pytest

from providers.models import ProviderDefinition, ProviderStatus
from providers.store import CorruptProviderStoreError, ProviderStore

from providers_helpers import make_definition


class TestDataSpace:
    def test_path_is_catalog_json_under_providers(self, providers_dir):
        store = ProviderStore(providers_dir)
        assert store.path == providers_dir / "catalog.json"

    def test_independent_from_runtimes(self, providers_dir):
        """数据空间分离: providers/ 目录独立, 不触碰 runtimes/ (删除隔离前提)。"""
        store = ProviderStore(providers_dir)
        store.save_definition(make_definition("openai"))
        assert (providers_dir / "catalog.json").exists()
        assert not (providers_dir.parent / "runtimes" / "catalog.json").exists()

    def test_missing_file_returns_empty(self, providers_dir):
        store = ProviderStore(providers_dir)
        assert store.list_definitions() == []
        assert store.get_default() is None
        assert store.definition_ids() == []


class TestRead:
    def test_roundtrip_definition(self, store):
        store.save_definition(make_definition("openai", capabilities=["chat", "code"]))
        d = store.get_definition("openai")
        assert d is not None
        assert d.id == "openai"
        assert d.capabilities == ["chat", "code"]
        assert d.status is ProviderStatus.ACTIVE

    def test_get_missing_returns_none(self, store):
        assert store.get_definition("ghost") is None

    def test_list_sorted(self, store):
        store.save_definition(make_definition("zebra"))
        store.save_definition(make_definition("alpha"))
        assert [d.id for d in store.list_definitions()] == ["alpha", "zebra"]

    def test_definition_ids_sorted(self, store):
        store.save_definition(make_definition("zebra"))
        store.save_definition(make_definition("alpha"))
        assert store.definition_ids() == ["alpha", "zebra"]

    def test_default_roundtrip(self, store):
        assert store.get_default() is None
        store.save_default("hermes")
        assert store.get_default() == "hermes"

    def test_file_format_two_sections(self, store):
        """文件格式 (双节, KISS): {definitions: {id: dict}, default: id|null}。"""
        store.save_definition(make_definition("openai"))
        store.save_default("hermes")
        raw = json.loads(store.path.read_text(encoding="utf-8"))
        assert set(raw) == {"definitions", "default"}
        assert raw["default"] == "hermes"
        assert "openai" in raw["definitions"]


class TestWrite:
    def test_upsert_overwrites(self, store):
        store.save_definition(make_definition("openai", version="1.0.0"))
        store.save_definition(make_definition("openai", version="2.0.0"))
        assert store.get_definition("openai").version == "2.0.0"
        assert len(store.definition_ids()) == 1

    def test_remove_ok(self, store):
        store.save_definition(make_definition("openai"))
        assert store.remove_definition("openai") is True
        assert store.definition_ids() == []

    def test_remove_missing_false(self, store):
        assert store.remove_definition("ghost") is False

    def test_atomic_write_no_tmp_leftover(self, store):
        """原子写: os.replace — 写后无 .tmp 残留文件。"""
        store.save_definition(make_definition("openai"))
        leftovers = [p for p in store.dir.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []

    def test_writes_sorted_by_id(self, store):
        store.save_definition(make_definition("zebra"))
        store.save_definition(make_definition("alpha"))
        raw = json.loads(store.path.read_text(encoding="utf-8"))
        assert list(raw["definitions"]) == ["alpha", "zebra"]

    def test_dir_created_on_first_write(self, providers_dir):
        """目录由首次原子写自动创建 (同 ADR-0006 决策 5)。"""
        assert not providers_dir.exists()
        ProviderStore(providers_dir).save_definition(make_definition("openai"))
        assert providers_dir.exists()


class TestCorruption:
    def _write_raw(self, store: ProviderStore, raw):
        store.dir.mkdir(parents=True, exist_ok=True)
        store.path.write_text(json.dumps(raw), encoding="utf-8")

    def test_invalid_json_raises(self, store):
        store.dir.mkdir(parents=True, exist_ok=True)
        store.path.write_text("{not json", encoding="utf-8")
        with pytest.raises(CorruptProviderStoreError, match="corrupt"):
            store.list_definitions()

    def test_non_object_root_raises(self, store):
        self._write_raw(store, [1, 2])
        with pytest.raises(CorruptProviderStoreError):
            store.list_definitions()

    def test_missing_definitions_section_raises(self, store):
        self._write_raw(store, {"default": "hermes"})
        with pytest.raises(CorruptProviderStoreError, match="definitions"):
            store.list_definitions()

    def test_invalid_default_type_raises(self, store):
        self._write_raw(store, {"definitions": {}, "default": 42})
        with pytest.raises(CorruptProviderStoreError, match="default"):
            store.get_default()

    def test_invalid_definition_model_raises(self, store):
        """模型校验失败 (缺 name) → CorruptProviderStoreError (绝不静默返回空)。"""
        self._write_raw(store, {"definitions": {"bad": {"id": "bad"}}, "default": None})
        with pytest.raises(CorruptProviderStoreError):
            store.list_definitions()

    def test_corruption_never_silently_empty(self, store):
        """损坏绝不静默返回空 — 与 runtimes/store.py 同哲学。"""
        self._write_raw(store, {"definitions": {}, "default": 3})
        with pytest.raises(CorruptProviderStoreError):
            store.get_default()
