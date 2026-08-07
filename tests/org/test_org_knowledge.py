"""tests/org/test_org_knowledge.py — 企业知识入库与公司隔离 (Phase 16A, ADR-0036)。

覆盖 (任务清单: knowledge isolation A↔B):
- add_knowledge: 入库 (org.knowledge.bound 事件, payload 契约)
- 公司隔离铁律: A 公司知识 B 公司不可见 (store 过滤 + lifecycle 检索)
- 不存在公司 → NotFoundError; 重复 id → DuplicateError
- 版本化 (默认 version 1); 只读检索零事件
"""

from __future__ import annotations

import pytest

from org.lifecycle import DuplicateError, NotFoundError, OrgLifecycle
from org.store import OrgStore

from org_helpers import event_sequence, last_event, payload_of


@pytest.fixture
def lifecycle(org_store: OrgStore, logger) -> OrgLifecycle:
    return OrgLifecycle(org_store, logger=logger)


def _seed_two_companies(lifecycle: OrgLifecycle) -> tuple[str, str]:
    a = lifecycle.create_company("Acme", template="solo", company_id="C-A").id
    b = lifecycle.create_company("Beta", template="solo", company_id="C-B").id
    return a, b


class TestAddKnowledge:
    def test_add_basic(self, lifecycle, org_store):
        a, _ = _seed_two_companies(lifecycle)
        item = lifecycle.add_knowledge(
            a, "docs", "coding guidelines", knowledge_id="K-1",
        )
        assert item.company_id == a
        assert item.domain == "docs"
        assert item.content == "coding guidelines"
        assert item.version == 1
        assert org_store.get_knowledge("K-1") is not None

    def test_bound_event_payload(self, lifecycle, event_store):
        a, _ = _seed_two_companies(lifecycle)
        lifecycle.add_knowledge(a, "tech", "python idioms", knowledge_id="K-1")
        payload = payload_of(event_store, "org.knowledge.bound")
        assert payload["knowledge_id"] == "K-1"
        assert payload["company_id"] == a
        assert payload["domain"] == "tech"
        assert payload["version"] == 1

    def test_unknown_company_raises(self, lifecycle):
        with pytest.raises(NotFoundError):
            lifecycle.add_knowledge("C-999", "docs", "x")

    def test_duplicate_id_raises(self, lifecycle):
        a, _ = _seed_two_companies(lifecycle)
        lifecycle.add_knowledge(a, "docs", "first", knowledge_id="K-1")
        with pytest.raises(DuplicateError):
            lifecycle.add_knowledge(a, "docs", "second", knowledge_id="K-1")

    def test_auto_id_generated(self, lifecycle, org_store):
        a, _ = _seed_two_companies(lifecycle)
        item = lifecycle.add_knowledge(a, "docs", "auto id")
        assert item.id.startswith("K-")
        assert org_store.get_knowledge(item.id) is not None


class TestKnowledgeIsolation:
    def test_company_scoped_list(self, lifecycle, org_store):
        a, b = _seed_two_companies(lifecycle)
        lifecycle.add_knowledge(a, "docs", "A secret", knowledge_id="K-A1")
        lifecycle.add_knowledge(b, "docs", "B secret", knowledge_id="K-B1")
        lifecycle.add_knowledge(a, "tech", "A tech", knowledge_id="K-A2")
        got_a = org_store.list_knowledge_by_company(a)
        got_b = org_store.list_knowledge_by_company(b)
        assert {k.id for k in got_a} == {"K-A1", "K-A2"}
        assert {k.id for k in got_b} == {"K-B1"}
        # 隔离铁律: A 的清单里绝无 B 的知识
        assert all(k.company_id == a for k in got_a)
        assert all(k.company_id == b for k in got_b)

    def test_cross_company_get_requires_company_scope(self, lifecycle, org_store):
        """get_knowledge 按 id 全局取 (存储层哑查询); 隔离由公司过滤保证 —
        B 公司业务方只能经 list_knowledge_by_company(B) 访问自身知识。"""
        a, b = _seed_two_companies(lifecycle)
        lifecycle.add_knowledge(a, "docs", "A secret", knowledge_id="K-A1")
        # 业务路径: B 公司视角看不到 A 的知识 (经公司过滤)
        assert org_store.list_knowledge_by_company(b) == []

    def test_knowledge_space_company_scoped(self, lifecycle, org_store):
        """Company.knowledge_space 即 company_id — 知识空间 Layer 2 根。"""
        a, b = _seed_two_companies(lifecycle)
        assert org_store.get_company(a).knowledge_space == a
        assert org_store.get_company(b).knowledge_space == b

    def test_list_read_only_no_events(self, lifecycle, org_store, event_store):
        a, _ = _seed_two_companies(lifecycle)
        lifecycle.add_knowledge(a, "docs", "x", knowledge_id="K-1")
        before = len(event_sequence(event_store))
        org_store.list_knowledge_by_company(a)
        org_store.get_knowledge("K-1")
        assert len(event_sequence(event_store)) == before

    def test_sorted_by_id(self, lifecycle, org_store):
        a, _ = _seed_two_companies(lifecycle)
        lifecycle.add_knowledge(a, "docs", "two", knowledge_id="K-2")
        lifecycle.add_knowledge(a, "docs", "one", knowledge_id="K-1")
        assert [k.id for k in org_store.list_knowledge_by_company(a)] == ["K-1", "K-2"]
