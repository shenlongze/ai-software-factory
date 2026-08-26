"""S10-120 — K-4 trace_id 贯穿契约测试 (test_s10_120_trace_chain.py)。

覆盖 (设计 docs/sprint10/S10-120-k4-trace-plan.md §2 契约 1-9):
1. CLI 贯穿一致: 一次 _dispatch 输入 → 该请求全部审计事件 trace_id 非空且相同
2. API 贯穿一致: TestClient 请求 → 事件 trace_id 一致 (X-Trace-ID 可选覆盖)
3. audit_trace 可用: trace_id → 返回该链路全部事件; 决策链可用
4. 无上下文零变化: 直接 emit 不设 context → trace_id="" (旧行为)
5. 父子关联: 子动作 correlation_id 关联 trace (get_chain 含子链)
6. execution_records 带 trace_id
7. cost_records 带 trace_id
8. 失败安全: contextvar 异常 → "" 不崩
9. exec runtime 入口: 无上下文生成 trace; 有上下文继承同一 trace; 策略子任务
   correlation 关联 (agent_runtime)
+ 版本 v1.1.95 断言 (pyproject / CHANGELOG / FEATURES)

装配: tmp_path 隔离工作区 + importlib (包名含连字符); 禁真实网络/LLM。
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest

AUDIT = import_module("factory-console.audit")
ACT = import_module("factory-console.session.action")
ACTIONS = import_module("factory-console.session.actions")
COST = import_module("factory-console.session.cost_ledger")
CTX = import_module("factory-console.session.context")
EM = import_module("factory-console.audit.audit_emitter")
INTENT = import_module("factory-console.session.intent")
ROUTER = import_module("factory-console.session.router")
S = import_module("factory-console.session.session")
TC = import_module("factory-console.audit.trace_context")

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _ws(tmp_path: Path, name: str = "ws") -> Path:
    ws = tmp_path / name
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _emit_events(store_ws: Path, count: int = 3) -> list:
    """经真实 AuditEmitter 发射 count 个事件 (返回封存后事件列表)。"""
    emitter = EM.AuditEmitter(workspace=store_ws)
    events = []
    for i in range(count):
        ev = emitter.emit(
            ("TASK_STARTED", "AGENT_STARTED", "LLM_CALL")[i],
            project_id="p1",
            actor_type="user",
            actor_id="u1",
        )
        assert ev is not None
        events.append(ev)
    return events


class _FixedIntentParser:
    """固定意图解析器 (测试: 避免真实 LLM; 契约只测 trace 贯穿)。"""

    def __init__(self, intent_type: str = "test_emit") -> None:
        self.intent_type = intent_type

    def parse(self, text: str):
        return INTENT.IntentObject(
            intent_type=self.intent_type, params={}, raw=text, source="session"
        )


# ================================================================== 1. CLI 贯穿一致


class TestCliTraceConsistent:
    def _session(self, ws: Path, store_ws: Path) -> S.InteractiveSession:
        def _handler(ctx):
            _emit_events(store_ws, count=3)
            return ACT.ActionResult(
                ok=True, status=ACT.STATUS_OK, message="ok", data={}
            )

        registry = ACT.ActionRegistry()
        registry.register(
            ACT.Action(name="test.emit", description="", handler=_handler, permission="user")
        )
        router = ROUTER.IntentRouter()
        router.register_route("test_emit", "test.emit")
        return S.InteractiveSession(
            context_manager=CTX.ContextManager(workspace=str(ws)),
            action_registry=registry,
            intent_router=router,
            intent_parser=_FixedIntentParser(),
            confirmation_gate=None,
        )

    def test_dispatch_events_same_trace_per_input(self, tmp_path: Path):
        """契约 1: 一次 _dispatch 输入 → 全部审计事件 trace_id 非空且相同;
        两次输入 → 不同 trace_id; dispatch 后上下文不泄漏。"""
        ws = _ws(tmp_path)
        store_ws = _ws(tmp_path, "audit")
        session = self._session(ws, store_ws)
        with contextlib.redirect_stdout(io.StringIO()):
            session._dispatch("任务一")
        with contextlib.redirect_stdout(io.StringIO()):
            session._dispatch("任务二")
        store = AUDIT.AuditStore(workspace=store_ws)
        events = store.events()
        assert len(events) == 6
        first, second = events[:3], events[3:]
        t1 = {e.trace_id for e in first}
        t2 = {e.trace_id for e in second}
        assert len(t1) == 1 and len(t2) == 1  # 每次输入内全部事件同 trace
        (tid1,), (tid2,) = t1, t2
        assert tid1 and tid2 and tid1 != tid2  # 不同输入不同 trace
        assert all(len(t) == 32 for t in (tid1, tid2))  # uuid4 hex
        assert all(e.correlation_id == "" for e in events)  # 根事件无 correlation
        assert TC.get_trace_id() == ""  # with 退出自动恢复 — 不跨请求泄漏

    def test_dispatch_within_outer_trace_keeps_same_trace(self, tmp_path: Path):
        """嵌套语义: 已有外部 trace (宿主/API 调 _dispatch) → 保持同一 trace。"""
        ws = _ws(tmp_path)
        store_ws = _ws(tmp_path, "audit")
        session = self._session(ws, store_ws)
        outer = TC.new_trace_id()
        with TC.trace_context(outer):
            with contextlib.redirect_stdout(io.StringIO()):
                session._dispatch("嵌套分发")
        store = AUDIT.AuditStore(workspace=store_ws)
        events = store.events()
        assert len(events) == 3
        assert {e.trace_id for e in events} == {outer}
        assert TC.get_trace_id() == ""


# ================================================================== 2. API 贯穿一致


class TestApiTraceConsistent:
    def _app(self, tmp_path: Path, store_ws: Path):
        adapter = import_module("factory-console.web.backend.fastapi_adapter")
        app = adapter.build_app(SimpleNamespace(), factory_root=tmp_path)

        @app.get("/api/_test_trace")
        def _trace_ep():
            ev = EM.AuditEmitter(workspace=store_ws).emit(
                "GOVERNANCE_CHECK", project_id="api", actor_type="api"
            )
            return {
                "trace_id": ev.trace_id if ev else "",
                "correlation_id": ev.correlation_id if ev else "",
            }

        return app

    def test_request_trace_consistent_and_header_override(self, tmp_path: Path):
        """契约 2: TestClient 请求 → 事件 trace_id 与响应一致; X-Trace-ID 可选覆盖。"""
        from fastapi.testclient import TestClient  # noqa: E402

        store_ws = _ws(tmp_path, "audit")
        app = self._app(tmp_path, store_ws)
        with TestClient(app) as c:
            r1 = c.get("/api/_test_trace")
            body1 = r1.json()
            assert body1["trace_id"] and r1.headers.get("X-Trace-ID") == body1["trace_id"]
            r2 = c.get("/api/_test_trace", headers={"X-Trace-ID": "my-trace-123"})
            body2 = r2.json()
            assert body2["trace_id"] == "my-trace-123"
            assert r2.headers.get("X-Trace-ID") == "my-trace-123"
            # 两次请求 trace 不同 (中间件不跨请求泄漏)
            assert body1["trace_id"] != body2["trace_id"]
        store = AUDIT.AuditStore(workspace=store_ws)
        events = store.events()
        assert len(events) == 2
        assert events[0].trace_id == body1["trace_id"]
        assert events[1].trace_id == "my-trace-123"


# ================================================================== 3. audit_trace 可用


class TestAuditTraceAction:
    def _ctx(self, ws: Path, params: dict):
        return ACT.ExecutionContext(
            workspace=ws,
            session=CTX.SessionContext(),
            intent=INTENT.IntentObject(
                intent_type="audit_trace", params=params, raw="审计追踪", source="test"
            ),
        )

    def test_audit_trace_returns_all_chain_events(self, tmp_path: Path):
        """契约 3: trace_id → 返回该链路全部事件; 决策链可用 (audit_chain)。"""
        ws = _ws(tmp_path)
        tid = TC.new_trace_id()
        with TC.trace_context(tid):
            _emit_events(ws, count=3)
        result = ACTIONS.audit_trace(self._ctx(ws, {"trace_id": tid}))
        assert result.ok
        assert result.data["count"] == 3
        assert tid in result.message
        chain = ACTIONS.audit_chain(self._ctx(ws, {"trace_id": tid}))
        assert chain.ok
        data = chain.data
        assert data["count"] == 3
        assert data["root_event"]["trace_id"] == tid
        assert data["final_outcome"]["event_type"] == "LLM_CALL"
        # 缺 trace_id → 明确错误 (失败安全)
        missing = ACTIONS.audit_trace(self._ctx(ws, {}))
        assert not missing.ok and "trace_id" in missing.message


# ================================================================== 4. 无上下文零变化


class TestNoContextZeroChange:
    def test_emit_without_context_empty(self, tmp_path: Path):
        """契约 4: 直接 emit 不设 context → trace_id="" (旧行为零变化)。"""
        ws = _ws(tmp_path)
        ev = EM.AuditEmitter(workspace=ws).emit("TASK_STARTED", project_id="p1")
        assert ev is not None
        assert ev.trace_id == "" and ev.correlation_id == ""

    def test_explicit_wins_not_overridden(self, tmp_path: Path):
        """显式 trace_id/correlation_id 优先 (不覆盖)。"""
        ws = _ws(tmp_path)
        tid = TC.new_trace_id()
        with TC.trace_context(tid, "ctx-corr"):
            ev = EM.AuditEmitter(workspace=ws).emit(
                "TASK_STARTED", project_id="p1",
                trace_id="explicit", correlation_id="explicit-corr",
            )
        assert ev is not None
        assert ev.trace_id == "explicit"
        assert ev.correlation_id == "explicit-corr"


# ================================================================== 5. 父子关联


class TestParentChildCorrelation:
    def test_child_correlation_and_get_chain(self, tmp_path: Path):
        """契约 5: 子动作 correlation_id 关联 trace (get_chain 含子链 + 跨 trace 相关)。"""
        ws = _ws(tmp_path)
        tid = TC.new_trace_id()
        emitter = EM.AuditEmitter(workspace=ws)
        with TC.trace_context(tid, "root-corr"):
            root = emitter.emit("TASK_STARTED", project_id="p1")
        assert root is not None and root.correlation_id == "root-corr"
        child_corr = TC.child_correlation(tid)
        assert child_corr == f"{tid}:1"
        assert TC.child_correlation(tid) == f"{tid}:2"  # 递增唯一
        with TC.trace_context(tid, child_corr):
            child = emitter.emit(
                "AGENT_STARTED", project_id="p1", parent_event_id=root.audit_id
            )
        assert child is not None and child.correlation_id == child_corr
        # 跨 trace 相关事件: 另一 trace 共享根 correlation → related_events
        tid2 = TC.new_trace_id()
        with TC.trace_context(tid2, "root-corr"):
            related = emitter.emit("TOOL_CALL", project_id="p1")
        assert related is not None
        chain = AUDIT.AuditStore(workspace=ws).get_chain(tid)
        assert chain["count"] == 2
        assert [c["audit_id"] for c in chain["children"]] == [child.audit_id]
        assert [r["audit_id"] for r in chain["related_events"]] == [related.audit_id]


# ================================================================== 6. execution_records 带 trace_id


class TestExecutionRecordsTrace:
    def _record_context(self, ws: Path) -> SimpleNamespace:
        return SimpleNamespace(
            intent=SimpleNamespace(intent_type="agent.execute_task"),
            task_id="t1",
            workspace=str(ws),
            project="p1",
            agent_id="backend-1",
            user="user",
        )

    @staticmethod
    def _execution() -> SimpleNamespace:
        return SimpleNamespace(
            agent="backend-1", success=True, result_id="EXS-1", error=None, quality=None
        )

    def test_execution_record_carries_trace(self, tmp_path: Path):
        """契约 6: execution_records 带 trace_id (contextvar); 无上下文 → ""。"""
        ws = _ws(tmp_path)
        context = self._record_context(ws)
        execution = self._execution()
        tid = TC.new_trace_id()
        with TC.trace_context(tid):
            rec = ACTIONS._record_execution(context, execution, {"objective": "任务"}, {})
        assert rec["trace_id"] == tid
        records = json.loads(
            (ws / "exec" / "execution_records.json").read_text(encoding="utf-8")
        )
        assert records[0]["trace_id"] == tid
        # 无上下文 → "" (旧行为零变化)
        rec2 = ACTIONS._record_execution(context, execution, {"objective": "任务"}, {})
        assert rec2["trace_id"] == ""
        records = json.loads(
            (ws / "exec" / "execution_records.json").read_text(encoding="utf-8")
        )
        assert records[1]["trace_id"] == ""


# ================================================================== 7. cost_records 带 trace_id


class TestCostRecordsTrace:
    def test_cost_record_carries_trace(self, tmp_path: Path):
        """契约 7: cost_records 带 trace_id (contextvar 缺省); 显式优先; 无上下文零变化。"""
        ws = _ws(tmp_path)
        ledger = COST.CostLedger(file=ws / "cost_records.json")
        tid = TC.new_trace_id()
        with TC.trace_context(tid):
            rec = ledger.record({"project_id": "p1", "estimated_cost": 0.01})
        assert rec["trace_id"] == tid
        rec2 = ledger.record({"project_id": "p1"}, trace_id="explicit")
        assert rec2["trace_id"] == "explicit"
        rec3 = ledger.record({"project_id": "p1"})
        assert rec3["trace_id"] == ""
        records = ledger.load()
        assert [r["trace_id"] for r in records] == [tid, "explicit", ""]


# ================================================================== 8. 失败安全


class TestFailSafe:
    def test_contextvar_broken_returns_empty(self, tmp_path: Path):
        """契约 8: contextvar 读取异常 → "" 不崩 (emit/执行/成本链路不受影响)。"""
        ws = _ws(tmp_path)
        orig_t = TC._trace_var
        orig_c = TC._correlation_var

        class _Broken:
            """ContextVar 替身: get 抛异常 (模拟 contextvar 底层故障)。"""

            def get(self, *args, **kwargs):
                raise RuntimeError("contextvar broken")

            def set(self, *args, **kwargs):
                raise RuntimeError("contextvar broken")

        TC._trace_var = _Broken()
        TC._correlation_var = _Broken()
        try:
            assert TC.get_trace_id() == ""
            assert TC.get_correlation_id() == ""
            ev = EM.AuditEmitter(workspace=ws).emit("TASK_STARTED", project_id="p1")
            assert ev is not None and ev.trace_id == ""  # 审计不崩
            ledger = COST.CostLedger(file=ws / "cost_records.json")
            rec = ledger.record({"project_id": "p1", "estimated_cost": 0.01})
            assert rec["trace_id"] == ""  # 成本不崩
        finally:
            TC._trace_var = orig_t
            TC._correlation_var = orig_c


# ================================================================== 9. exec runtime 入口


class TestExecRuntimeTrace:
    """契约 9: agent_runtime 执行入口 — 无上下文生成 trace; 有上下文继承;
    策略子任务 correlation 关联。"""

    @pytest.fixture(autouse=True)
    def _exec_path(self):
        _FACTORY_EXEC = _REPO_ROOT / "factory-exec"
        if str(_FACTORY_EXEC) not in sys.path:
            sys.path.insert(0, str(_FACTORY_EXEC))
        yield

    @staticmethod
    def _runtime() -> "object":
        from exec.agent_runtime import AgentRuntime  # noqa: E402

        rt = object.__new__(AgentRuntime)
        rt._execution_strategy_enabled = False
        return rt

    def test_standalone_generates_trace(self):
        """无上下文执行入口 → 生成新 trace_id (全程同一, 退出后不泄漏)。"""
        rt = self._runtime()
        seen: dict[str, str] = {}

        def _fake_execute(request, employee=None, agent_instance=None):
            seen["trace"] = TC.get_trace_id()
            return "RESULT"

        rt._execute = _fake_execute
        result = rt.execute(SimpleNamespace(task_id="t1"))
        assert result == "RESULT"
        assert len(seen["trace"]) == 32
        assert TC.get_trace_id() == ""

    def test_inherits_outer_trace(self):
        """已有 trace 上下文 (session/API 调用) → 继承同一 trace (链路不分裂)。"""
        rt = self._runtime()
        seen: dict[str, str] = {}

        def _fake_execute(request, employee=None, agent_instance=None):
            seen["trace"] = TC.get_trace_id()
            return "RESULT"

        rt._execute = _fake_execute
        outer = TC.new_trace_id()
        with TC.trace_context(outer):
            rt.execute(SimpleNamespace(task_id="t1"))
        assert seen["trace"] == outer

    def test_strategy_child_correlation(self, monkeypatch):
        """策略路径: 每个候选 Run 为子动作 (correlation = trace:n, 唯一可排序)。"""
        from exec import candidate as cand  # noqa: E402
        from exec.agent_runtime import AgentRuntime  # noqa: E402

        rt = object.__new__(AgentRuntime)
        runs: list[tuple[str, str]] = []

        def _fake_legacy(request, employee=None, agent_instance=None):
            runs.append((TC.get_trace_id(), TC.get_correlation_id()))
            return "R"

        rt._execute_legacy = _fake_legacy
        rt._execution_strategy_enabled = True
        rt._execution_strategy_runs = 3
        rt._developer = SimpleNamespace(
            provider=SimpleNamespace(provider_id="p", model="m")
        )
        orig_run = cand.SequentialRunner.run
        orig_select = cand.SequentialRunner.select_result
        monkeypatch.setattr(
            cand.SequentialRunner,
            "run",
            lambda self, request=None: [self._executor(i) for i in range(1, self._runs_count + 1)],
        )
        monkeypatch.setattr(cand.SequentialRunner, "select_result", lambda self: "SELECTED")
        try:
            with TC.trace_context("strat-trace"):
                rt.execute(SimpleNamespace(task_id="t1"))
        finally:
            monkeypatch.setattr(cand.SequentialRunner, "run", orig_run)
            monkeypatch.setattr(cand.SequentialRunner, "select_result", orig_select)
        assert [c for _, c in runs] == [
            "strat-trace:1", "strat-trace:2", "strat-trace:3",
        ]
        assert {t for t, _ in runs} == {"strat-trace"}


# ================================================================== 版本断言


class TestVersionBump:
    def test_v1_1_90_synced(self):
        """版本 v1.1.95: pyproject + CHANGELOG + FEATURES 同步。"""
        pyproject = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert re.search(r'^version\s*=\s*"1\.1\.161"', pyproject, re.M)
        changelog = (_REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        assert "## [v1.1.161]" in changelog
        features = (_REPO_ROOT / "docs" / "FEATURES.md").read_text(encoding="utf-8")
        assert "v1.1.161" in features
