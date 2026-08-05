"""tests/runtimes/test_catalog_store.py — CatalogStore 持久化 (独立文件 + 原子写 + 损坏)。

覆盖: 独立 catalog.json 与 runtimes.json 不冲突 / 原子写 / 损坏报错 / round-trip /
删除幂等 / 目录自动创建。参照 test_runtime_store.py 模式。
"""

from __future__ import annotations

import json

import pytest

from runtimes.models import RuntimeDefinition
from runtimes.store import CatalogStore, CorruptCatalogStoreError

from catalog_helpers import make_definition


class TestIndependentFile:
    def test_filename_is_catalog_json(self, catalog_store):
        assert catalog_store.filename == "catalog.json"
        assert catalog_store.path.name == "catalog.json"

    def test_does_not_touch_runtimes_json(self, runtimes_dir, catalog_store):
        """catalog.json 与实例库 runtimes.json 独立 — 写目录不产生实例文件。"""
        catalog_store.save_definition(make_definition())
        assert catalog_store.path.exists()
        assert not (runtimes_dir / "runtimes.json").exists()

    def test_same_dir_dual_files_coexist(self, runtimes_dir, catalog_store):
        """同一目录下两文件可共存 (实例库由 RuntimeStore 写, 互不覆盖)。"""
        from runtime.store import RuntimeStore
        from runtime.models import RuntimeInfo

        runtime_store = RuntimeStore(runtimes_dir)
        runtime_store.save_runtime(RuntimeInfo(id="R-001", name="rt"))
        catalog_store.save_definition(make_definition("custom-rt"))
        assert (runtimes_dir / "runtimes.json").exists()
        assert (runtimes_dir / "catalog.json").exists()
        # 各自读回互不干扰
        assert runtime_store.get_runtime("R-001") is not None
        assert catalog_store.get_definition("custom-rt") is not None
        assert catalog_store.get_definition("R-001") is None


class TestRoundTrip:
    def test_save_and_get(self, catalog_store):
        d = make_definition()
        catalog_store.save_definition(d)
        got = catalog_store.get_definition("custom-rt")
        assert got is not None
        assert got.id == d.id
        assert got.capabilities == d.capabilities
        assert got.created_at == d.created_at  # 落盘读回保留原始时间戳

    def test_get_missing_returns_none(self, catalog_store):
        assert catalog_store.get_definition("nope") is None

    def test_save_overwrites_same_id(self, catalog_store):
        catalog_store.save_definition(make_definition(version="1.0.0"))
        catalog_store.save_definition(make_definition(version="2.0.0"))
        assert catalog_store.get_definition("custom-rt").version == "2.0.0"

    def test_list_sorted_by_id(self, catalog_store):
        for rid in ("rt-b", "rt-a", "rt-c"):
            catalog_store.save_definition(make_definition(rid))
        assert [d.id for d in catalog_store.list_definitions()] == ["rt-a", "rt-b", "rt-c"]

    def test_definition_ids(self, catalog_store):
        catalog_store.save_definition(make_definition("rt-a"))
        catalog_store.save_definition(make_definition("rt-b"))
        assert catalog_store.definition_ids() == ["rt-a", "rt-b"]

    def test_file_format_single_section(self, catalog_store):
        catalog_store.save_definition(make_definition("rt-a"))
        raw = json.loads(catalog_store.path.read_text(encoding="utf-8"))
        assert set(raw.keys()) == {"definitions"}
        assert "rt-a" in raw["definitions"]


class TestRemove:
    def test_remove_existing(self, catalog_store):
        catalog_store.save_definition(make_definition())
        assert catalog_store.remove_definition("custom-rt") is True
        assert catalog_store.get_definition("custom-rt") is None

    def test_remove_missing_returns_false(self, catalog_store):
        assert catalog_store.remove_definition("nope") is False


class TestAtomicWrite:
    def test_write_creates_dir_automatically(self, tmp_path):
        store = CatalogStore(tmp_path / "deep" / "nested" / "runtimes")
        store.save_definition(make_definition())
        assert store.path.exists()

    def test_no_tmp_leftover_after_write(self, catalog_store):
        catalog_store.save_definition(make_definition())
        leftovers = [p for p in catalog_store.dir.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []


class TestCorruption:
    def test_invalid_json_raises(self, catalog_store):
        catalog_store.path.parent.mkdir(parents=True, exist_ok=True)
        catalog_store.path.write_text("{not json", encoding="utf-8")
        with pytest.raises(CorruptCatalogStoreError, match="corrupt catalog store"):
            catalog_store.get_definition("rt-a")

    def test_non_object_root_raises(self, catalog_store):
        catalog_store.path.parent.mkdir(parents=True, exist_ok=True)
        catalog_store.path.write_text("[1, 2]", encoding="utf-8")
        with pytest.raises(CorruptCatalogStoreError, match="expected JSON object"):
            catalog_store.list_definitions()

    def test_missing_definitions_section_raises(self, catalog_store):
        catalog_store.path.parent.mkdir(parents=True, exist_ok=True)
        catalog_store.path.write_text('{"runtimes": {}}', encoding="utf-8")
        with pytest.raises(CorruptCatalogStoreError, match="missing or invalid section"):
            catalog_store.list_definitions()

    def test_invalid_definition_model_raises(self, catalog_store):
        catalog_store.path.parent.mkdir(parents=True, exist_ok=True)
        catalog_store.path.write_text(
            json.dumps({"definitions": {"bad": {"id": "bad", "name": ""}}}),
            encoding="utf-8",
        )
        with pytest.raises(CorruptCatalogStoreError):
            catalog_store.get_definition("bad")

    def test_missing_file_is_empty_catalog(self, catalog_store):
        assert catalog_store.list_definitions() == []
        assert catalog_store.definition_ids() == []

    def test_corrupt_store_never_silently_empty(self, catalog_store):
        """损坏文件绝不静默返回空 (工程规则: 损坏报错)。"""
        catalog_store.path.parent.mkdir(parents=True, exist_ok=True)
        catalog_store.path.write_text("garbage", encoding="utf-8")
        with pytest.raises(CorruptCatalogStoreError):
            catalog_store.list_definitions()


class TestTypeAnnotations:
    def test_load_returns_runtime_definition_type(self, catalog_store):
        catalog_store.save_definition(make_definition())
        got = catalog_store.get_definition("custom-rt")
        assert isinstance(got, RuntimeDefinition)
