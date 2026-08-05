"""tests/runtimes/test_catalog_capability_search.py — find_by_capability 检索。

覆盖: 精确命中 (大小写不敏感) / 多命中排序 / 空与空白入参 / 未命中 / 合并视图
(默认 + 已注册) / 类型过滤组合。
"""

from __future__ import annotations

from catalog_helpers import make_definition


class TestFindByCapability:
    def test_hits_default_hermes(self, catalog):
        assert [d.id for d in catalog.find_by_capability("code-generation")] == ["hermes"]

    def test_case_insensitive(self, catalog):
        assert [d.id for d in catalog.find_by_capability("CODE-GENERATION")] == ["hermes"]
        assert [d.id for d in catalog.find_by_capability("Tool-Use")] == ["hermes"]

    def test_hits_default_echo_and_mock(self, catalog):
        """echo/mock 共享 testing 能力 → 双命中且按 id 排序。"""
        assert [d.id for d in catalog.find_by_capability("testing")] == ["echo", "mock"]

    def test_hits_registered_definition(self, catalog):
        catalog.register(make_definition("python-rt", capabilities=["code-generation", "python"]))
        hits = [d.id for d in catalog.find_by_capability("code-generation")]
        assert hits == ["hermes", "python-rt"]

    def test_miss_returns_empty(self, catalog):
        assert catalog.find_by_capability("quantum-computing") == []

    def test_empty_input_returns_empty(self, catalog):
        assert catalog.find_by_capability("") == []
        assert catalog.find_by_capability("   ") == []

    def test_partial_token_not_matched(self, catalog):
        """子串不命中 — 精确能力标签匹配。"""
        assert catalog.find_by_capability("code") == []

    def test_returns_sorted_by_id(self, catalog):
        catalog.register(make_definition("b-rt", capabilities=["zzz"]))
        catalog.register(make_definition("a-rt", capabilities=["zzz"]))
        assert [d.id for d in catalog.find_by_capability("zzz")] == ["a-rt", "b-rt"]

    def test_find_does_not_mutate_store(self, catalog_store, catalog):
        """检索是纯读 — 不写 catalog.json。"""
        catalog.find_by_capability("testing")
        assert not catalog_store.path.exists()
