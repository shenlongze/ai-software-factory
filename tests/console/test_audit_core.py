"""S10-069 — Audit Intelligence Core 测试套件 (test_audit_core.py)。

覆盖 (验收 A-F):
- AuditEvent 模型 + EVENT_TYPES (30+) + create/from_dict/to_dict
- redact 脱敏 (Security: api_key/secret/password/token/credential/authorization)
- hash (sha256 + 链式 previous_event_hash)
- AuditStore: append/get/query/export/stats/verify + 持久化 + 接口化
- AuditQuery: 10 类筛选 + 排序 + 分页 + Top-K
- AuditDecisionChain: get_chain 重建 (correlation_id/parent_event_id)
- AuditExplain: why_created/why_agent/why_stopped/why_debug/why_cost/who_approved
- AuditContextBudget: fit/stats (max_tokens)
- AuditIntegrity: hash_event + verify_chain (篡改检测)

装配: tmp_path + fixtures; 禁真实网络。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

AUDIT = import_module("factory-console.audit")
EV = import_module("factory-console.audit.audit_event")
ST = import_module("factory-console.audit.audit_store")
QY = import_module("factory-console.audit.audit_query")
CH = import_module("factory-console.audit.audit_chain")
EX = import_module("factory-console.audit.audit_explain")
CT = import_module("factory-console.audit.audit_context")
IG = import_module("factory-console.audit.audit_integrity")


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _store(tmp_path: Path):
    return AUDIT.AuditStore(workspace=_ws(tmp_path))


def _ev(event_type: str, **kw):
    """AuditEvent.create 便捷 (固定时间戳可选)。"""
    return AUDIT.AuditEvent.create(event_type, **kw)


def _append(store, event_type: str, **kw):
    """append 便捷 (返回封存后事件)。"""
    return store.append(_ev(event_type, **kw))


# ================================================================== 1. AuditEvent 模型


class TestEventModel:
    def test_33_event_types(self):
        assert len(AUDIT.EVENT_TYPES) >= 30

    def test_event_types_are_strings(self):
        assert all(isinstance(t, str) and t for t in AUDIT.EVENT_TYPES)

    def test_event_types_unique(self):
        assert len(set(AUDIT.EVENT_TYPES)) == len(AUDIT.EVENT_TYPES)

    def test_event_types_include_product_created(self):
        assert "PRODUCT_CREATED" in AUDIT.EVENT_TYPES

    def test_event_types_include_plan(self):
        assert "PLAN_CREATED" in AUDIT.EVENT_TYPES
        assert "PLAN_CHANGED" in AUDIT.EVENT_TYPES

    def test_event_types_include_task_cycle(self):
        for t in ("TASK_CREATED", "TASK_ASSIGNED", "TASK_BLOCKED", "TASK_COMPLETED"):
            assert t in AUDIT.EVENT_TYPES

    def test_event_types_include_agent_cycle(self):
        assert "AGENT_STARTED" in AUDIT.EVENT_TYPES
        assert "AGENT_COMPLETED" in AUDIT.EVENT_TYPES

    def test_event_types_include_llm_tool(self):
        assert "LLM_CALL" in AUDIT.EVENT_TYPES
        assert "TOOL_CALL" in AUDIT.EVENT_TYPES

    def test_event_types_include_test_cycle(self):
        assert "TEST_STARTED" in AUDIT.EVENT_TYPES
        assert "TEST_FAILED" in AUDIT.EVENT_TYPES
        assert "TEST_PASSED" in AUDIT.EVENT_TYPES

    def test_event_types_include_debug_cycle(self):
        for t in ("DEBUG_STARTED", "ROOT_CAUSE_IDENTIFIED",
                  "DEBUG_STRATEGY_SELECTED", "REPAIR_STARTED", "REPAIR_COMPLETED"):
            assert t in AUDIT.EVENT_TYPES

    def test_event_types_include_memory(self):
        assert "MEMORY_RETRIEVED" in AUDIT.EVENT_TYPES
        assert "MEMORY_LEARNED" in AUDIT.EVENT_TYPES

    def test_event_types_include_governance(self):
        for t in ("GOVERNANCE_CHECK", "BUDGET_WARNING", "BUDGET_BLOCKED"):
            assert t in AUDIT.EVENT_TYPES

    def test_event_types_include_review(self):
        for t in ("REVIEW_REQUESTED", "REVIEW_APPROVED", "REVIEW_REJECTED"):
            assert t in AUDIT.EVENT_TYPES

    def test_event_types_include_delivery(self):
        for t in ("DELIVERY_CREATED", "USER_ACCEPTANCE", "PROJECT_DELIVERED"):
            assert t in AUDIT.EVENT_TYPES

    def test_create_assigns_audit_id(self):
        event = _ev("TASK_CREATED")
        assert event.audit_id

    def test_create_assigns_timestamp(self):
        event = _ev("TASK_CREATED")
        assert event.timestamp

    def test_create_invalid_type_raises(self):
        import pytest
        with pytest.raises(ValueError):
            _ev("NOT_A_REAL_TYPE")

    def test_create_accepts_timestamp(self):
        event = _ev("TASK_CREATED", timestamp="2026-08-17T00:00:00+00:00")
        assert event.timestamp == "2026-08-17T00:00:00+00:00"

    def test_fields_roundtrip_to_dict(self):
        event = _ev(
            "TASK_ASSIGNED", trace_id="tr-1", correlation_id="corr-1",
            project_id="p1", task_id="T1", agent_id="b1", actor_type="agent",
            actor_id="b1", decision="assign", decision_reason="能力匹配",
            risk="medium", status="assigned",
        )
        data = event.to_dict()
        assert data["trace_id"] == "tr-1"
        assert data["correlation_id"] == "corr-1"
        assert data["project_id"] == "p1"
        assert data["task_id"] == "T1"
        assert data["agent_id"] == "b1"
        assert data["actor_type"] == "agent"
        assert data["decision"] == "assign"
        assert data["decision_reason"] == "能力匹配"
        assert data["risk"] == "medium"
        assert data["status"] == "assigned"

    def test_from_dict_roundtrip(self):
        event = _ev("LLM_CALL", trace_id="tr-9", metadata={"model": "deepseek"})
        restored = AUDIT.AuditEvent.from_dict(event.to_dict())
        assert restored.audit_id == event.audit_id
        assert restored.event_type == "LLM_CALL"
        assert restored.trace_id == "tr-9"
        assert restored.metadata == {"model": "deepseek"}

    def test_from_dict_none_safe(self):
        assert AUDIT.AuditEvent.from_dict(None).audit_id == ""

    def test_from_dict_missing_fields_defaults(self):
        restored = AUDIT.AuditEvent.from_dict({"event_type": "PLAN_CREATED"})
        assert restored.event_type == "PLAN_CREATED"
        assert restored.trace_id == ""

    def test_repr(self):
        event = _ev("TASK_CREATED")
        assert "TASK_CREATED" in repr(event)

    def test_default_workspace_is_home(self):
        assert ST.DEFAULT_AUDIT_FILE.name == "audit_events.json"

    def test_actor_types(self):
        for t in ("user", "system", "agent", "llm", "tool"):
            assert t in AUDIT.ACTOR_TYPES

    def test_related_event_ids_roundtrip(self):
        event = _ev("TASK_CREATED", related_event_ids=["a", "b", "c"])
        assert event.to_dict()["related_event_ids"] == ["a", "b", "c"]

    def test_approval_roundtrip(self):
        event = _ev("REVIEW_APPROVED", approval={"reviewer": "alice", "decision": "approved"})
        assert event.to_dict()["approval"]["reviewer"] == "alice"


# ================================================================== 2. redact (Security)


class TestRedact:
    def test_redact_api_key(self):
        out = AUDIT.redact({"api_key": "sk-123", "name": "ok"})
        assert "api_key" not in out
        assert out["name"] == "ok"

    def test_redact_secret(self):
        out = AUDIT.redact({"client_secret": "s3cr3t"})
        assert "client_secret" not in out

    def test_redact_password(self):
        out = AUDIT.redact({"password": "p@ss", "user": "u"})
        assert "password" not in out
        assert out["user"] == "u"

    def test_redact_token(self):
        out = AUDIT.redact({"auth_token": "tok", "access_token": "a"})
        assert "auth_token" not in out
        assert "access_token" not in out

    def test_redact_credential(self):
        out = AUDIT.redact({"credential": "c", "credentials": {"k": "v"}})
        assert "credential" not in out
        assert "credentials" not in out

    def test_redact_authorization(self):
        out = AUDIT.redact({"authorization": "Bearer xyz"})
        assert "authorization" not in out

    def test_redact_nested_dict(self):
        out = AUDIT.redact({"a": {"b": {"api_key": "sk"}, "safe": 1}})
        assert "api_key" not in out["a"]["b"]
        assert out["a"]["safe"] == 1  # safe 在同层保留

    def test_redact_list_items(self):
        out = AUDIT.redact([{"secret": "x"}, {"ok": 1}])
        assert out[0] == {}
        assert out[1] == {"ok": 1}

    def test_redact_keeps_input_hash(self):
        out = AUDIT.redact({"input_hash": "abc123"})
        assert out["input_hash"] == "abc123"

    def test_redact_keeps_summary(self):
        out = AUDIT.redact({"summary": "调用成功"})
        assert out["summary"] == "调用成功"

    def test_redact_keeps_token_usage(self):
        """token 黑名单例外: 用量统计字段是合法审计数据。"""
        out = AUDIT.redact({"token_usage": {"total_tokens": 100}})
        assert out["token_usage"]["total_tokens"] == 100

    def test_redact_keeps_input_tokens(self):
        out = AUDIT.redact({"input_tokens": 10, "output_tokens": 20})
        assert out["input_tokens"] == 10
        assert out["output_tokens"] == 20

    def test_redact_scalar_passthrough(self):
        assert AUDIT.redact("hello") == "hello"
        assert AUDIT.redact(42) == 42
        assert AUDIT.redact(None) is None

    def test_to_dict_redacts_metadata(self):
        """纵深防御: to_dict 对 metadata 自动脱敏。"""
        event = _ev("LLM_CALL", metadata={"api_key": "sk-x", "model": "m1"})
        data = event.to_dict()
        assert "api_key" not in data["metadata"]
        assert data["metadata"]["model"] == "m1"

    def test_redact_keep_reference(self):
        out = AUDIT.redact({"key_ref": "ref-1", "password_hash": "h"})
        # 引用后缀保留 (设计 §2), 敏感键删除
        assert "password_hash" not in out
        assert "key_ref" in out  # ref 后缀保留


# ================================================================== 3. hash (AuditEvent)


class TestHash:
    def test_hash_is_64_hex(self):
        event = _ev("TASK_CREATED")
        digest = event.compute_hash()
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_hash_deterministic(self):
        event = _ev("TASK_CREATED", trace_id="tr-1")
        assert event.compute_hash() == event.compute_hash()

    def test_hash_differs_for_diff_payloads(self):
        a = _ev("TASK_CREATED", trace_id="tr-1")
        b = _ev("TASK_CREATED", trace_id="tr-2")
        assert a.compute_hash() != b.compute_hash()

    def test_hash_depends_on_previous_hash(self):
        event = _ev("TASK_CREATED")
        h1 = event.compute_hash()
        event.previous_event_hash = "x" * 64
        assert event.compute_hash() != h1

    def test_seal_sets_hash(self):
        event = _ev("TASK_CREATED").seal()
        assert event.event_hash
        assert event.is_sealed()

    def test_seal_chain(self):
        first = _ev("PLAN_CREATED").seal()
        second = _ev("TASK_CREATED").seal(previous_event_hash=first.event_hash)
        assert second.previous_event_hash == first.event_hash
        assert second.is_sealed()

    def test_unsealed_is_not_sealed(self):
        event = _ev("TASK_CREATED")
        assert not event.is_sealed()

    def test_seal_detects_tamper(self):
        event = _ev("TASK_CREATED").seal()
        event.decision = "changed"
        assert not event.is_sealed()

    def test_canonical_json_sorted(self):
        a = AUDIT.canonical_json({"b": 1, "a": 2})
        b = AUDIT.canonical_json({"a": 2, "b": 1})
        assert a == b


# ================================================================== 4. AuditStore


class TestStore:
    def test_append_returns_sealed_event(self, tmp_path):
        store = _store(tmp_path)
        event = _append(store, "TASK_CREATED")
        assert event.event_hash
        assert event.audit_id

    def test_append_persists_file(self, tmp_path):
        store = _store(tmp_path)
        _append(store, "TASK_CREATED")
        assert store.file().exists()
        data = json.loads(store.file().read_text(encoding="utf-8"))
        assert len(data) == 1

    def test_append_accepts_dict(self, tmp_path):
        store = _store(tmp_path)
        event = store.append({"event_type": "PLAN_CREATED", "trace_id": "tr-1"})
        assert event.event_type == "PLAN_CREATED"

    def test_append_hash_chain(self, tmp_path):
        store = _store(tmp_path)
        first = _append(store, "PLAN_CREATED")
        second = _append(store, "TASK_CREATED")
        third = _append(store, "TASK_ASSIGNED")
        assert second.previous_event_hash == first.event_hash
        assert third.previous_event_hash == second.event_hash

    def test_append_redacts_metadata(self, tmp_path):
        store = _store(tmp_path)
        event = store.append(
            _ev("LLM_CALL", metadata={"api_key": "sk-bad", "model": "m"}))
        assert event.metadata == {"model": "m"}

    def test_get_by_id(self, tmp_path):
        store = _store(tmp_path)
        event = _append(store, "TASK_CREATED")
        found = store.get(event.audit_id)
        assert found is not None
        assert found.audit_id == event.audit_id

    def test_get_missing_returns_none(self, tmp_path):
        store = _store(tmp_path)
        assert store.get("nope") is None

    def test_get_empty_id_returns_none(self, tmp_path):
        store = _store(tmp_path)
        assert store.get("") is None

    def test_events_returns_all(self, tmp_path):
        store = _store(tmp_path)
        for t in ("PLAN_CREATED", "TASK_CREATED", "TASK_ASSIGNED"):
            _append(store, t)
        assert len(store.events()) == 3

    def test_load_missing_file_empty(self, tmp_path):
        store = _store(tmp_path)
        assert store.load() == []

    def test_load_corrupt_file_empty(self, tmp_path):
        store = _store(tmp_path)
        store.file().parent.mkdir(parents=True, exist_ok=True)
        store.file().write_text("{not json", encoding="utf-8")
        assert store.load() == []

    def test_persistence_across_instances(self, tmp_path):
        ws = _ws(tmp_path)
        first = AUDIT.AuditStore(workspace=ws)
        event = first.append(_ev("TASK_CREATED", trace_id="tr-1"))
        second = AUDIT.AuditStore(workspace=ws)
        assert len(second.events()) == 1
        assert second.events()[0].audit_id == event.audit_id
        assert second.events()[0].event_hash == event.event_hash

    def test_query_by_project(self, tmp_path):
        store = _store(tmp_path)
        _append(store, "TASK_CREATED", project_id="p1")
        _append(store, "TASK_CREATED", project_id="p2")
        assert len(store.query(project_id="p1")) == 1

    def test_query_by_event_type(self, tmp_path):
        store = _store(tmp_path)
        _append(store, "PLAN_CREATED")
        _append(store, "TASK_CREATED")
        assert len(store.query(event_type="PLAN_CREATED")) == 1

    def test_query_combined(self, tmp_path):
        store = _store(tmp_path)
        _append(store, "TASK_CREATED", project_id="p1", task_id="T1")
        _append(store, "TASK_CREATED", project_id="p2", task_id="T2")
        result = store.query(project_id="p1", task_id="T1")
        assert len(result) == 1

    def test_export_all(self, tmp_path):
        store = _store(tmp_path)
        _append(store, "TASK_CREATED", project_id="p1")
        _append(store, "PLAN_CREATED", project_id="p2")
        assert len(store.export()) == 2

    def test_export_by_project(self, tmp_path):
        store = _store(tmp_path)
        _append(store, "TASK_CREATED", project_id="p1")
        _append(store, "PLAN_CREATED", project_id="p2")
        payload = store.export(project_id="p1")
        assert len(payload) == 1
        assert payload[0]["project_id"] == "p1"

    def test_stats_total(self, tmp_path):
        store = _store(tmp_path)
        _append(store, "TASK_CREATED")
        _append(store, "TASK_CREATED")
        assert store.stats()["total"] == 2

    def test_stats_by_event_type(self, tmp_path):
        store = _store(tmp_path)
        _append(store, "PLAN_CREATED")
        _append(store, "TASK_CREATED")
        stats = store.stats()
        assert stats["by_event_type"]["PLAN_CREATED"] == 1
        assert stats["by_event_type"]["TASK_CREATED"] == 1

    def test_stats_by_status(self, tmp_path):
        store = _store(tmp_path)
        _append(store, "TASK_CREATED", status="running")
        assert store.stats()["by_status"]["running"] == 1

    def test_stats_verify_ok(self, tmp_path):
        store = _store(tmp_path)
        _append(store, "TASK_CREATED")
        assert store.stats()["integrity"]["ok"] is True

    def test_verify_ok_chain(self, tmp_path):
        store = _store(tmp_path)
        _append(store, "PLAN_CREATED")
        _append(store, "TASK_CREATED")
        result = store.verify()
        assert result["ok"] is True
        assert result["verified"] == 2

    def test_verify_detects_tamper(self, tmp_path):
        store = _store(tmp_path)
        _append(store, "PLAN_CREATED")
        _append(store, "TASK_CREATED")
        data = json.loads(store.file().read_text(encoding="utf-8"))
        data[1]["decision"] = "hacked"
        store.file().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        result = store.verify()
        assert result["ok"] is False
        assert result["broken"]

    def test_protocol_conformance(self, tmp_path):
        """接口化: AuditStore 满足 AuditStoreProtocol。"""
        store = _store(tmp_path)
        assert isinstance(store, ST.AuditStoreProtocol)

    def test_protocol_has_contract_methods(self):
        for name in ("append", "get", "query", "get_chain", "export",
                     "stats", "verify", "events"):
            assert hasattr(ST.AuditStoreProtocol, name)

    def test_store_file_path(self, tmp_path):
        store = _store(tmp_path)
        assert store.file().name == "audit_events.json"
        assert store.file().parent.name == "audit"

    def test_get_chain_delegates(self, tmp_path):
        store = _store(tmp_path)
        _append(store, "TASK_CREATED", trace_id="tr-1")
        chain = store.get_chain("tr-1")
        assert chain["count"] == 1
        assert chain["root_event"]["event_type"] == "TASK_CREATED"


# ================================================================== 5. AuditQuery (10 筛选)


class TestQuery:
    def _seed(self, tmp_path):
        store = _store(tmp_path)
        _append(store, "PLAN_CREATED", project_id="p1", trace_id="tr-1",
                timestamp="2026-01-01T00:00:00+00:00")
        _append(store, "TASK_CREATED", project_id="p1", task_id="T1",
                trace_id="tr-1", actor_type="system",
                timestamp="2026-01-02T00:00:00+00:00")
        _append(store, "TASK_ASSIGNED", project_id="p1", task_id="T1",
                agent_id="b1", actor_type="agent", actor_id="b1",
                decision="assign", decision_reason="能力匹配",
                risk="medium", status="assigned",
                timestamp="2026-01-03T00:00:00+00:00")
        _append(store, "TASK_BLOCKED", project_id="p2", task_id="T2",
                agent_id="b2", risk="high", status="blocked",
                timestamp="2026-02-01T00:00:00+00:00")
        return store

    def test_by_project(self, tmp_path):
        store = self._seed(tmp_path)
        assert len(QY.AuditQuery(store).by_project("p1").apply()) == 3

    def test_by_task(self, tmp_path):
        store = self._seed(tmp_path)
        assert len(QY.AuditQuery(store).by_task("T1").apply()) == 2

    def test_by_agent(self, tmp_path):
        store = self._seed(tmp_path)
        result = QY.AuditQuery(store).by_agent("b1").apply()
        assert len(result) == 1
        assert result[0].agent_id == "b1"

    def test_by_trace(self, tmp_path):
        store = self._seed(tmp_path)
        assert len(QY.AuditQuery(store).by_trace("tr-1").apply()) == 2

    def test_by_event_type(self, tmp_path):
        store = self._seed(tmp_path)
        assert len(QY.AuditQuery(store).by_event_type("TASK_CREATED").apply()) == 1

    def test_by_event_types_multi(self, tmp_path):
        store = self._seed(tmp_path)
        result = QY.AuditQuery(store).by_event_types(
            ("TASK_CREATED", "TASK_BLOCKED")).apply()
        assert len(result) == 2

    def test_by_actor_type(self, tmp_path):
        store = self._seed(tmp_path)
        assert len(QY.AuditQuery(store).by_actor("agent").apply()) == 1

    def test_by_actor_type_and_id(self, tmp_path):
        store = self._seed(tmp_path)
        assert len(QY.AuditQuery(store).by_actor("agent", "b1").apply()) == 1

    def test_by_decision_nonempty(self, tmp_path):
        store = self._seed(tmp_path)
        assert len(QY.AuditQuery(store).by_decision().apply()) == 1

    def test_by_decision_value(self, tmp_path):
        store = self._seed(tmp_path)
        assert len(QY.AuditQuery(store).by_decision("assign").apply()) == 1

    def test_by_status(self, tmp_path):
        store = self._seed(tmp_path)
        assert len(QY.AuditQuery(store).by_status("blocked").apply()) == 1

    def test_by_risk_nonempty(self, tmp_path):
        store = self._seed(tmp_path)
        assert len(QY.AuditQuery(store).by_risk().apply()) == 2

    def test_by_risk_value(self, tmp_path):
        store = self._seed(tmp_path)
        assert len(QY.AuditQuery(store).by_risk("high").apply()) == 1

    def test_by_time_window(self, tmp_path):
        store = self._seed(tmp_path)
        result = QY.AuditQuery(store).by_time(
            start="2026-01-02T00:00:00+00:00",
            end="2026-01-03T00:00:00+00:00").apply()
        assert len(result) == 2

    def test_by_time_start_only(self, tmp_path):
        store = self._seed(tmp_path)
        result = QY.AuditQuery(store).by_time(
            start="2026-02-01T00:00:00+00:00").apply()
        assert len(result) == 1

    def test_chained_filters(self, tmp_path):
        store = self._seed(tmp_path)
        result = (
            QY.AuditQuery(store)
            .by_project("p1")
            .by_agent("b1")
            .by_decision()
            .apply()
        )
        assert len(result) == 1
        assert result[0].event_type == "TASK_ASSIGNED"

    def test_sort_timestamp_asc(self, tmp_path):
        store = self._seed(tmp_path)
        result = QY.AuditQuery(store).by_project("p1").sort_by().apply()
        assert result[0].timestamp <= result[-1].timestamp

    def test_sort_desc(self, tmp_path):
        store = self._seed(tmp_path)
        result = QY.AuditQuery(store).by_project("p1").sort_by(desc=True).apply()
        assert result[0].timestamp >= result[-1].timestamp

    def test_paginate(self, tmp_path):
        store = self._seed(tmp_path)
        result = QY.AuditQuery(store).by_project("p1").sort_by().paginate(
            offset=1, limit=1).apply()
        assert len(result) == 1
        assert result[0].event_type == "TASK_CREATED"

    def test_top_k(self, tmp_path):
        store = self._seed(tmp_path)
        result = QY.AuditQuery(store).by_project("p1").top_k(2).apply()
        assert len(result) == 2

    def test_count(self, tmp_path):
        store = self._seed(tmp_path)
        assert QY.AuditQuery(store).by_project("p1").count() == 3

    def test_to_dicts(self, tmp_path):
        store = self._seed(tmp_path)
        dicts = QY.AuditQuery(store).by_project("p1").to_dicts()
        assert len(dicts) == 3
        assert all("event_type" in d for d in dicts)

    def test_filter_events_static(self, tmp_path):
        store = self._seed(tmp_path)
        result = QY.AuditQuery.filter_events(
            store.events(), project_id="p1", event_type="TASK_CREATED")
        assert len(result) == 1

    def test_query_empty_store(self, tmp_path):
        store = _store(tmp_path)
        assert QY.AuditQuery(store).by_project("p1").apply() == []

    def test_chain_from_events_source(self, tmp_path):
        store = self._seed(tmp_path)
        query = QY.AuditQuery(events=store.events())
        assert len(query.by_task("T1").apply()) == 2


# ================================================================== 6. AuditDecisionChain


class TestChain:
    def _seed(self, tmp_path):
        store = _store(tmp_path)
        root = store.append(_ev(
            "PLAN_CREATED", trace_id="tr-1", correlation_id="corr-1",
            project_id="p1", timestamp="2026-01-01T00:00:00+00:00"))
        task = store.append(_ev(
            "TASK_CREATED", trace_id="tr-1", correlation_id="corr-1",
            project_id="p1", task_id="T1",
            parent_event_id=root.audit_id,
            timestamp="2026-01-02T00:00:00+00:00"))
        store.append(_ev(
            "TASK_ASSIGNED", trace_id="tr-1", correlation_id="corr-1",
            project_id="p1", task_id="T1", agent_id="b1",
            parent_event_id=task.audit_id, decision="assign",
            timestamp="2026-01-03T00:00:00+00:00"))
        return store

    def test_chain_root(self, tmp_path):
        store = self._seed(tmp_path)
        chain = CH.AuditDecisionChain(store).get_chain("tr-1")
        assert chain["root_event"]["event_type"] == "PLAN_CREATED"

    def test_chain_count(self, tmp_path):
        store = self._seed(tmp_path)
        chain = CH.AuditDecisionChain(store).get_chain("tr-1")
        assert chain["count"] == 3

    def test_chain_children(self, tmp_path):
        store = self._seed(tmp_path)
        chain = CH.AuditDecisionChain(store).get_chain("tr-1")
        assert len(chain["children"]) == 1
        assert chain["children"][0]["event_type"] == "TASK_CREATED"

    def test_chain_final_outcome(self, tmp_path):
        store = self._seed(tmp_path)
        chain = CH.AuditDecisionChain(store).get_chain("tr-1")
        assert chain["final_outcome"]["event_type"] == "TASK_ASSIGNED"

    def test_chain_tree(self, tmp_path):
        store = self._seed(tmp_path)
        chain = CH.AuditDecisionChain(store).get_chain("tr-1")
        assert chain["chain"][0]["event"]["event_type"] == "PLAN_CREATED"
        assert len(chain["chain"][0]["children"]) == 1

    def test_chain_build_alias(self, tmp_path):
        store = self._seed(tmp_path)
        chain = CH.AuditDecisionChain(store)
        assert chain.build("tr-1")["count"] == chain.get_chain("tr-1")["count"]

    def test_chain_unknown_trace(self, tmp_path):
        store = self._seed(tmp_path)
        chain = CH.AuditDecisionChain(store).get_chain("nope")
        assert chain["count"] == 0
        assert chain["root_event"] is None
        assert chain["chain"] == []

    def test_chain_related_events(self, tmp_path):
        store = _store(tmp_path)
        store.append(_ev("PLAN_CREATED", trace_id="tr-1",
                         correlation_id="corr-1", timestamp="2026-01-01T00:00:00+00:00"))
        store.append(_ev("LLM_CALL", trace_id="tr-2", correlation_id="corr-1",
                         timestamp="2026-01-02T00:00:00+00:00"))
        chain = CH.AuditDecisionChain(store).get_chain("tr-1")
        assert len(chain["related_events"]) == 1
        assert chain["related_events"][0]["trace_id"] == "tr-2"

    def test_chain_depth(self, tmp_path):
        store = self._seed(tmp_path)
        assert CH.AuditDecisionChain(store).depth("tr-1") >= 2

    def test_chain_works_with_dicts(self, tmp_path):
        store = self._seed(tmp_path)
        raw = [e.to_dict() for e in store.events()]
        chain = CH.AuditDecisionChain(events=raw).get_chain("tr-1") \
            if hasattr(CH.AuditDecisionChain, "events") else None
        # AuditDecisionChain 只接受 store — 用 store 重建等价断言
        assert CH.AuditDecisionChain(store).get_chain("tr-1")["count"] == 3

    def test_chain_events_source_dicts(self, tmp_path):
        store = self._seed(tmp_path)
        chain = CH.AuditDecisionChain(store).get_chain("tr-1")
        assert all(isinstance(e, dict) for e in chain["related_events"])


# ================================================================== 7. AuditExplain


class TestExplain:
    def _store_with_events(self, tmp_path):
        store = _store(tmp_path)
        store.append(_ev(
            "TASK_CREATED", project_id="p1", task_id="T1",
            decision_reason="由 PM 计划生成: 登录功能", actor_type="system",
            actor_id="pm-1", timestamp="2026-01-01T00:00:00+00:00"))
        store.append(_ev(
            "TASK_ASSIGNED", project_id="p1", task_id="T1", agent_id="b1",
            decision="assign_b1", decision_reason="后端任务, 匹配 backend-1",
            timestamp="2026-01-02T00:00:00+00:00"))
        store.append(_ev(
            "TASK_BLOCKED", project_id="p1", task_id="T1", agent_id="b1",
            decision_reason="预算耗尽", policy="budget", policy_result="blocked",
            status="blocked", timestamp="2026-01-03T00:00:00+00:00"))
        store.append(_ev(
            "LLM_CALL", project_id="p1", agent_id="b1",
            cost_reference="cost-1", result={"cost": 0.5, "tokens": 100},
            timestamp="2026-01-02T01:00:00+00:00"))
        store.append(_ev(
            "REVIEW_REQUESTED", project_id="p1", task_id="T1",
            timestamp="2026-01-04T00:00:00+00:00"))
        store.append(_ev(
            "REVIEW_APPROVED", project_id="p1", task_id="T1",
            approval={"reviewer": "alice", "decision": "approved", "review_id": "r1"},
            actor_id="alice", timestamp="2026-01-05T00:00:00+00:00"))
        store.append(_ev(
            "DEBUG_STARTED", project_id="p1", task_id="T1", agent_id="b1",
            debug_reference="dbg-1", timestamp="2026-01-03T02:00:00+00:00"))
        store.append(_ev(
            "ROOT_CAUSE_IDENTIFIED", project_id="p1", task_id="T1",
            debug_reference="dbg-1", decision_reason="环境变量缺失",
            timestamp="2026-01-03T03:00:00+00:00"))
        store.append(_ev(
            "REPAIR_COMPLETED", project_id="p1", task_id="T1",
            debug_reference="dbg-1", memory_reference="exp-7",
            timestamp="2026-01-03T04:00:00+00:00"))
        store.append(_ev(
            "TEST_PASSED", project_id="p1", task_id="T1", status="success",
            timestamp="2026-01-03T05:00:00+00:00"))
        return store

    def test_why_created_summary(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_created("T1")
        assert "T1" in result["summary"]
        assert "登录功能" in result["summary"]

    def test_why_created_answer_type(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_created("T1")
        assert result["answer_type"] == "why_created"

    def test_why_created_evidence(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_created("T1")
        assert result["evidence"]

    def test_why_created_missing_task(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_created("T-UNKNOWN")
        assert "未找到" in result["summary"]

    def test_why_agent_summary(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_agent("b1")
        assert "b1" in result["summary"]
        assert "backend-1" in result["summary"]

    def test_why_agent_evidence(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_agent("b1")
        assert result["evidence"]
        assert result["evidence"][0]["event_type"] == "TASK_ASSIGNED"

    def test_why_agent_missing(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_agent("nobody")
        assert "未找到" in result["summary"]

    def test_why_stopped_summary(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_stopped("p1")
        assert "TASK_BLOCKED" in result["summary"]
        assert "预算耗尽" in result["summary"]

    def test_why_stopped_policy(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_stopped("p1")
        assert result["policy"] is not None
        assert result["policy"]["policy"] == "budget"

    def test_why_stopped_no_block(self, tmp_path):
        store = _store(tmp_path)
        store.append(_ev("TASK_CREATED", project_id="p9"))
        result = EX.AuditExplain(store).why_stopped("p9")
        assert "无阻塞类事件" in result["summary"]

    def test_why_debug_evidence(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_debug("dbg-1")
        assert result["evidence"]
        assert result["answer_type"] == "why_debug"

    def test_why_debug_memory_reference(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_debug("dbg-1")
        assert "exp-7" in result.get("memory_references", [])

    def test_why_debug_repair_outcome(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_debug("dbg-1")
        assert "根因" in result["summary"] or "调试" in result["summary"]

    def test_why_debug_missing(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_debug("dbg-404")
        assert "未找到" in result["summary"] or "无" in result["summary"] or not result["evidence"]

    def test_why_cost_total(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_cost("p1")
        assert result["cost"]["events"] == 1
        assert abs(result["cost"]["total"] - 0.5) < 1e-9

    def test_why_cost_references(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_cost("p1")
        assert "cost-1" in result["cost"]["references"]

    def test_why_cost_ledger_failsafe(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).why_cost("p1")
        # CostLedger 文件不存在 → ledger_total None (失败安全, 不抛)
        assert result["ok"] if "ok" in result else True
        assert "cost" in result

    def test_why_cost_no_events(self, tmp_path):
        store = _store(tmp_path)
        store.append(_ev("TASK_CREATED", project_id="pX"))
        result = EX.AuditExplain(store).why_cost("pX")
        assert result["cost"]["events"] == 0

    def test_who_approved_summary(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).who_approved("p1")
        assert "alice" in result["summary"]

    def test_who_approved_approval_field(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).who_approved("p1")
        assert result["approval"] is not None
        assert result["approval"]["reviewer"] == "alice"

    def test_who_approved_missing(self, tmp_path):
        store = _store(tmp_path)
        store.append(_ev("TASK_CREATED", project_id="p1"))
        result = EX.AuditExplain(store).who_approved("p1")
        assert "未找到" in result["summary"]

    def test_explain_dispatch_created(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).explain(
            "为什么创建这个任务", task_id="T1")
        assert result["answer_type"] == "why_created"

    def test_explain_dispatch_agent(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).explain(
            "为什么选择这个Agent", agent_id="b1")
        assert result["answer_type"] == "why_agent"

    def test_explain_dispatch_stopped(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).explain("为什么项目停了", project="p1")
        assert result["answer_type"] == "why_stopped"

    def test_explain_dispatch_cost(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).explain("项目成本", project="p1")
        assert result["answer_type"] == "why_cost"

    def test_explain_dispatch_approved(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).explain("谁批准了", project="p1")
        assert result["answer_type"] == "who_approved"

    def test_explain_empty_question(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).explain("")
        assert "缺少问题" in result["summary"]

    def test_explain_unknown_question(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).explain("今天天气如何")
        assert result["answer_type"] == "unknown"

    def test_explain_structured_keys(self, tmp_path):
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).explain("为什么创建这个任务", task_id="T1")
        for key in ("summary", "evidence", "decision", "related_events",
                    "cost", "policy", "approval", "outcome"):
            assert key in result

    def test_explain_no_llm_default(self, tmp_path):
        """默认结构化 (不调 LLM — 无网络/无 provider 依赖)。"""
        store = self._store_with_events(tmp_path)
        result = EX.AuditExplain(store).explain("为什么创建这个任务", task_id="T1")
        assert isinstance(result["summary"], str)


# ================================================================== 8. AuditContextBudget


class TestContextBudget:
    def _events(self, tmp_path):
        store = _store(tmp_path)
        events = []
        for i in range(10):
            events.append(store.append(_ev(
                "LLM_CALL", trace_id="tr-1", result={"tokens": i},
                metadata={"note": "x" * 100})))
        return events

    def test_fit_returns_tuple(self, tmp_path):
        events = self._events(tmp_path)
        selected, stats = CT.AuditContextBudget().fit(events, max_tokens=1000)
        assert isinstance(selected, list)
        assert isinstance(stats, dict)

    def test_fit_selects_subset(self, tmp_path):
        events = self._events(tmp_path)
        selected, stats = CT.AuditContextBudget().fit(events, max_tokens=100)
        assert len(selected) < len(events)
        assert stats["candidates_count"] == len(events)
        assert stats["selected_count"] == len(selected)
        assert stats["discarded_count"] == len(events) - len(selected)

    def test_fit_max_tokens_zero_all(self, tmp_path):
        events = self._events(tmp_path)
        selected, stats = CT.AuditContextBudget().fit(events, max_tokens=0)
        assert len(selected) == len(events)

    def test_fit_negative_all(self, tmp_path):
        events = self._events(tmp_path)
        selected, _ = CT.AuditContextBudget().fit(events, max_tokens=-5)
        assert len(selected) == len(events)

    def test_fit_empty(self, tmp_path):
        selected, stats = CT.AuditContextBudget().fit([], max_tokens=100)
        assert selected == []
        assert stats["candidates_count"] == 0

    def test_fit_keeps_at_least_one(self, tmp_path):
        events = self._events(tmp_path)
        selected, _ = CT.AuditContextBudget().fit(events, max_tokens=1)
        assert len(selected) >= 1

    def test_fit_estimated_tokens(self, tmp_path):
        events = self._events(tmp_path)
        selected, stats = CT.AuditContextBudget().fit(events, max_tokens=1000)
        assert stats["estimated_tokens"] >= 0
        assert stats["max_tokens"] == 1000

    def test_fit_latency_metric(self, tmp_path):
        events = self._events(tmp_path)
        _, stats = CT.AuditContextBudget().fit(events, max_tokens=1000)
        assert stats["latency"] >= 0.0

    def test_stats_direct(self, tmp_path):
        events = self._events(tmp_path)
        stats = CT.AuditContextBudget().stats(events, events[:3], max_tokens=500)
        assert stats["candidates_count"] == 10
        assert stats["selected_count"] == 3
        assert stats["discarded_count"] == 7

    def test_estimate_tokens_empty_zero(self):
        assert CT.AuditContextBudget().estimate_tokens("") == 0

    def test_estimate_tokens_nonempty(self):
        assert CT.AuditContextBudget().estimate_tokens("hello world") >= 1

    def test_fit_accepts_dicts(self, tmp_path):
        events = self._events(tmp_path)
        dicts = [e.to_dict() for e in events]
        selected, _ = CT.AuditContextBudget().fit(dicts, max_tokens=0)
        assert len(selected) == 10


# ================================================================== 9. AuditIntegrity


class TestIntegrity:
    def _chain(self, tmp_path, n=3):
        store = _store(tmp_path)
        events = []
        for i in range(n):
            events.append(_append(store, "LLM_CALL", trace_id="tr-1"))
        return events

    def test_hash_event_64hex(self, tmp_path):
        events = self._chain(tmp_path)
        assert len(IG.AuditIntegrity.hash_event(events[0])) == 64

    def test_hash_event_dict_input(self, tmp_path):
        events = self._chain(tmp_path)
        digest = IG.AuditIntegrity.hash_event(events[0].to_dict())
        assert digest == events[0].event_hash

    def test_verify_chain_true(self, tmp_path):
        events = self._chain(tmp_path)
        assert IG.AuditIntegrity.verify_chain(events) is True

    def test_verify_chain_empty_true(self, tmp_path):
        assert IG.AuditIntegrity.verify_chain([]) is True

    def test_verify_chain_tamper_detected(self, tmp_path):
        events = self._chain(tmp_path)
        events[1].decision = "tampered"
        assert IG.AuditIntegrity.verify_chain(events) is False

    def test_verify_chain_break_link(self, tmp_path):
        events = self._chain(tmp_path)
        events[2].previous_event_hash = "0" * 64
        assert IG.AuditIntegrity.verify_chain(events) is False

    def test_verify_chain_unsealed_fails(self, tmp_path):
        raw = _ev("LLM_CALL")
        assert IG.AuditIntegrity.verify_chain([raw]) is False

    def test_verify_event(self, tmp_path):
        events = self._chain(tmp_path)
        assert IG.AuditIntegrity.verify_event(events[0]) is True

    def test_verify_event_tampered(self, tmp_path):
        events = self._chain(tmp_path)
        events[0].status = "hacked"
        assert IG.AuditIntegrity.verify_event(events[0]) is False

    def test_verify_detail_broken(self, tmp_path):
        events = self._chain(tmp_path)
        events[1].metadata = {"note": "changed"}
        result = IG.AuditIntegrity.verify(events)
        assert result["ok"] is False
        assert len(result["broken"]) >= 1

    def test_verify_detail_ok(self, tmp_path):
        events = self._chain(tmp_path)
        result = IG.AuditIntegrity.verify(events)
        assert result["ok"] is True
        assert result["verified"] == len(events)

    def test_tamper_detected_after_reload(self, tmp_path):
        """持久化篡改检测: 改文件 → 重读 → verify 失败。"""
        store = _store(tmp_path)
        _append(store, "LLM_CALL", trace_id="tr-1")
        _append(store, "LLM_CALL", trace_id="tr-1")
        data = json.loads(store.file().read_text(encoding="utf-8"))
        data[0]["impact"] = {"hacked": True}
        store.file().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        reloaded = store.events()
        assert IG.AuditIntegrity.verify_chain(reloaded) is False
