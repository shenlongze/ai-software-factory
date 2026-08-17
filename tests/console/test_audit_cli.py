"""S10-069 — Audit CLI + API + E2E 测试套件。

覆盖: 10 CLI action + intent / 10 API 端点 / 5 真实 E2E 场景 (含 Security)。
装配: tmp_path + fixtures; 禁真实网络。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

ACT = import_module("factory-console.session.actions")
INT = import_module("factory-console.session.intent")
API = import_module("factory-console.api.audit")
AE = import_module("factory-console.audit.audit_event")
ST = import_module("factory-console.audit.audit_store")


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _store(ws: Path) -> ST.AuditStore:
    store = ST.AuditStore(workspace=ws)
    store.append(AE.AuditEvent(
        event_type="PRODUCT_CREATED", project_id="demo", trace_id="tr-1",
        correlation_id="corr-1", actor_type="user", actor_id="alice",
        decision_reason="用户创建产品"))
    store.append(AE.AuditEvent(
        event_type="TASK_CREATED", project_id="demo", task_id="T1", trace_id="tr-1",
        correlation_id="corr-1", actor_type="system", actor_id="pm-1",
        decision_reason="由 PM 计划生成"))
    store.append(AE.AuditEvent(
        event_type="TASK_ASSIGNED", project_id="demo", task_id="T1",
        agent_id="backend-1", trace_id="tr-1", correlation_id="corr-1",
        actor_type="agent", actor_id="backend-1", decision="assign_backend"))
    return store


# ================================================================== 1. Intent


class TestIntent:
    def test_events(self):
        assert INT.KeywordIntentParser().parse("查看审计记录").intent_type == "audit_events"

    def test_trace(self):
        assert INT.KeywordIntentParser().parse("审计追踪").intent_type == "audit_trace"

    def test_chain(self):
        assert INT.KeywordIntentParser().parse("审计决策链").intent_type == "audit_chain"

    def test_explain_created(self):
        assert INT.KeywordIntentParser().parse("为什么创建这个任务").intent_type == "audit_explain"

    def test_explain_agent(self):
        assert INT.KeywordIntentParser().parse("为什么选择这个Agent").intent_type == "audit_explain"

    def test_explain_stopped(self):
        assert INT.KeywordIntentParser().parse("为什么项目停了").intent_type == "audit_explain"

    def test_task(self):
        assert INT.KeywordIntentParser().parse("审计任务").intent_type == "audit_task"

    def test_agent(self):
        assert INT.KeywordIntentParser().parse("审计Agent").intent_type == "audit_agent"

    def test_cost(self):
        assert INT.KeywordIntentParser().parse("查看项目成本审计").intent_type == "audit_cost"

    def test_export(self):
        assert INT.KeywordIntentParser().parse("导出审计").intent_type == "audit_export"

    def test_stats(self):
        assert INT.KeywordIntentParser().parse("审计统计").intent_type == "audit_stats"

    def test_old_kept(self):
        assert INT.KeywordIntentParser().parse("分析错误").intent_type == "debug_analyze"


# ================================================================== 2. CLI Actions


class TestCli:
    def _ctx(self, ws, params=None):
        class Ctx:
            def __init__(self, workspace, params):
                self.workspace = str(workspace)
                self.params = params or {}
                self.project = ""

            def require(self, level):
                pass

        return Ctx(ws, params)

    def test_audit_events(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        r = ACT.audit_events(self._ctx(ws))
        assert r.ok
        assert "PRODUCT_CREATED" in r.message or "审计" in r.message

    def test_audit_trace(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        r = ACT.audit_trace(self._ctx(ws, {"trace_id": "tr-1"}))
        assert r.ok

    def test_audit_chain(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        r = ACT.audit_chain(self._ctx(ws, {"trace_id": "tr-1"}))
        assert r.ok

    def test_audit_explain(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        r = ACT.audit_explain(self._ctx(ws, {"question": "为什么创建这个任务"}))
        assert r.ok

    def test_audit_task(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        r = ACT.audit_task(self._ctx(ws, {"task_id": "T1"}))
        assert r.ok

    def test_audit_agent(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        r = ACT.audit_agent(self._ctx(ws, {"agent_id": "backend-1"}))
        assert r.ok

    def test_audit_cost(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        r = ACT.audit_cost(self._ctx(ws, {"project_id": "demo"}))
        assert r.ok

    def test_audit_export(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        r = ACT.audit_export(self._ctx(ws))
        assert r.ok

    def test_audit_stats(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        r = ACT.audit_stats(self._ctx(ws))
        assert r.ok

    def test_registered(self, tmp_path):
        reg = ACT.build_default_actions()
        names = [a.name for a in reg.list()] if hasattr(reg, "list") else [a.name for a in getattr(reg, "actions", [])]
        for n in ("audit_events", "audit_trace", "audit_chain", "audit_decision",
                  "audit_explain", "audit_task", "audit_agent", "audit_cost",
                  "audit_export", "audit_stats"):
            assert n in names


# ================================================================== 3. API


class TestApi:
    def test_events(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        res = API.audit_events(workspace=ws)
        assert res.get("ok") is True
        assert len(res["data"]) == 3

    def test_events_filter_project(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        res = API.audit_events(workspace=ws, project="demo")
        assert len(res["data"]) == 3

    def test_trace(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        res = API.audit_trace(trace_id="tr-1", workspace=ws)
        assert res.get("ok") is True
        assert len(res["data"]) == 3

    def test_chain(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        res = API.audit_chain(trace_id="tr-1", workspace=ws)
        assert res.get("ok") is True
        assert "chain" in res["data"] or "events" in res["data"]

    def test_task(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        res = API.audit_task(task_id="T1", workspace=ws)
        assert res.get("ok") is True

    def test_agent(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        res = API.audit_agent(agent_id="backend-1", workspace=ws)
        assert res.get("ok") is True

    def test_decisions(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        res = API.audit_decisions(workspace=ws)
        assert res.get("ok") is True

    def test_explain(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        res = API.audit_explain("为什么创建这个任务", workspace=ws)
        assert res.get("ok") is True
        assert res["data"]["answer_type"] == "why_created"

    def test_cost(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        res = API.audit_cost(project_id="demo", workspace=ws)
        assert res.get("ok") is True

    def test_stats(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        res = API.audit_stats(workspace=ws)
        assert res.get("ok") is True
        assert "total" in res["data"] or "total_events" in res["data"]

    def test_export(self, tmp_path):
        ws = _ws(tmp_path)
        _store(ws)
        res = API.audit_export(workspace=ws)
        assert res.get("ok") is True
        assert len(res["data"]) == 3

    def test_registered(self, tmp_path):
        from importlib import import_module as _im
        init = _im("factory-console.api")
        for n in ("audit_events", "audit_trace", "audit_chain", "audit_task",
                  "audit_agent", "audit_decisions", "audit_explain", "audit_cost",
                  "audit_stats", "audit_export"):
            assert hasattr(init, n) or n in getattr(init, "__all__", [])


# ================================================================== 4. Real E2E 5 场景


class TestE2E:
    def test_case_a_full_chain(self, tmp_path):
        """CASE A: 完整生产链事件 → audit chain 可重建。"""
        from importlib import import_module as _im
        CH = _im("factory-console.audit.audit_chain")
        ws = _ws(tmp_path)
        store = ST.AuditStore(workspace=ws)
        # 全链事件 (同 correlation_id)
        events = [
            ("DISCOVERY_COMPLETED", "corr-1"), ("PRODUCT_INTELLIGENCE", "corr-1"),
            ("PLAN_CREATED", "corr-1"), ("TASK_CREATED", "corr-1"),
            ("TASK_ASSIGNED", "corr-1"), ("AGENT_STARTED", "corr-1"),
            ("AGENT_COMPLETED", "corr-1"), ("TEST_PASSED", "corr-1"),
            ("DELIVERY_CREATED", "corr-1"), ("USER_ACCEPTANCE", "corr-1"),
            ("PROJECT_DELIVERED", "corr-1"),
        ]
        for et, corr in events:
            store.append(AE.AuditEvent(
                event_type=et, project_id="demo", trace_id="tr-full",
                correlation_id=corr, actor_type="system", actor_id="pm-1"))
        chain = CH.AuditDecisionChain(store).get_chain("tr-full")
        assert len(chain["chain"]) >= 10

    def test_case_b_debug_chain(self, tmp_path):
        """CASE B: Debug 事件链 → explain 回答"为什么修/用了什么经验"。"""
        from importlib import import_module as _im
        EX = _im("factory-console.audit.audit_explain")
        ws = _ws(tmp_path)
        store = ST.AuditStore(workspace=ws)
        store.append(AE.AuditEvent(
            event_type="TEST_FAILED", project_id="demo", task_id="T1",
            debug_reference="dbg-1", decision_reason="计分 API 失败"))
        store.append(AE.AuditEvent(
            event_type="DEBUG_STARTED", project_id="demo", task_id="T1",
            debug_reference="dbg-1"))
        store.append(AE.AuditEvent(
            event_type="ROOT_CAUSE_IDENTIFIED", project_id="demo", task_id="T1",
            debug_reference="dbg-1", decision_reason="持久化缺失"))
        store.append(AE.AuditEvent(
            event_type="MEMORY_RETRIEVED", project_id="demo", task_id="T1",
            debug_reference="dbg-1", memory_reference="exp-7",
            decision_reason="命中历史经验"))
        store.append(AE.AuditEvent(
            event_type="DEBUG_STRATEGY_SELECTED", project_id="demo", task_id="T1",
            debug_reference="dbg-1", decision="FIX_CODE", decision_reason="历史成功经验"))
        store.append(AE.AuditEvent(
            event_type="REPAIR_COMPLETED", project_id="demo", task_id="T1",
            debug_reference="dbg-1", result="success"))
        result = EX.AuditExplain(store).why_debug("dbg-1")
        assert result["summary"] and "根因" in result["summary"]

    def test_case_c_governance(self, tmp_path):
        """CASE C: Governance 事件 → who_approved。"""
        from importlib import import_module as _im
        EX = _im("factory-console.audit.audit_explain")
        ws = _ws(tmp_path)
        store = ST.AuditStore(workspace=ws)
        store.append(AE.AuditEvent(
            event_type="BUDGET_BLOCKED", project_id="demo", task_id="T1",
            decision_reason="预算耗尽", policy="budget", policy_result="blocked"))
        store.append(AE.AuditEvent(
            event_type="REVIEW_REQUESTED", project_id="demo", task_id="T1"))
        store.append(AE.AuditEvent(
            event_type="REVIEW_APPROVED", project_id="demo", task_id="T1",
            approval={"reviewer": "alice", "decision": "approved"},
            actor_id="alice"))
        result = EX.AuditExplain(store).who_approved("demo")
        assert "alice" in str(result) or "approved" in str(result)

    def test_case_d_cost(self, tmp_path):
        """CASE D: 成本关联 (LLM_CALL 事件 + cost_reference)。"""
        ws = _ws(tmp_path)
        store = ST.AuditStore(workspace=ws)
        store.append(AE.AuditEvent(
            event_type="LLM_CALL", project_id="demo", agent_id="backend-1",
            cost_reference="cost-1", result={"cost": 0.5, "tokens": 100}))
        store.append(AE.AuditEvent(
            event_type="AGENT_STARTED", project_id="demo", agent_id="backend-1"))
        res = API.audit_agent(agent_id="backend-1", workspace=ws)
        assert res.get("ok") is True
        assert len(res["data"]) >= 2

    def test_case_e_security(self, tmp_path):
        """CASE E: 敏感信息不泄漏 (API_KEY/PASSWORD/SECRET)。"""
        ws = _ws(tmp_path)
        redacted = AE.redact({
            "api_key": "sk-test-123", "password": "p@ss",
            "secret": "s3cr3t", "safe_field": "ok",
            "nested": {"authorization": "Bearer x", "token_usage": 10},
        })
        assert "sk-test-123" not in json.dumps(redacted)
        assert "p@ss" not in json.dumps(redacted)
        assert "s3cr3t" not in json.dumps(redacted)
        assert "Bearer" not in json.dumps(redacted)
        assert redacted.get("safe_field") == "ok"
        assert redacted["nested"].get("token_usage") == 10  # 合法审计字段保留

    def test_case_e_hash_integrity(self, tmp_path):
        """Audit Integrity: 篡改检测。"""
        from importlib import import_module as _im
        INT = _im("factory-console.audit.audit_integrity")
        ws = _ws(tmp_path)
        store = ST.AuditStore(workspace=ws)
        store.append(AE.AuditEvent(event_type="TASK_CREATED", project_id="demo"))
        store.append(AE.AuditEvent(event_type="AGENT_STARTED", project_id="demo"))
        assert store.verify()["ok"] is True
        # 篡改: 改第一条 decision
        events = json.loads((ws / "audit" / "audit_events.json").read_text(encoding="utf-8"))
        events[0]["decision"] = "HACKED"
        (ws / "audit" / "audit_events.json").write_text(json.dumps(events), encoding="utf-8")
        store2 = ST.AuditStore(workspace=ws)
        assert store2.verify()["ok"] is False  # 检测到篡改
