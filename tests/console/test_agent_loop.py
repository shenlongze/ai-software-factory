"""tests/console/test_agent_loop.py — 会话 Agent 循环 v2 (原生 FC + 计划→审批→执行)。

Founder: 计划→审批→执行→验证→交付 闭环。
覆盖:
- tool_schemas: 14 会话动作工具 (含 plan_development/execute_plan)
- classify_approval: 可以/开始=approve, 不行/调整=reject
- PendingPlanStore: 计划跨消息持久化
- execute_plan: 审批后真实建任务进 backlog
- run_agent_native: 模型 tool_calls → 执行 → 回喂 → 答案 (stub call_with_tools)
- HTTP: 计划→审批通过→执行
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# 端点相对导入用下划线包名 (factory_console.*); 连字符与下划线同文件但不同模块实例
_ag = importlib.import_module("factory_console.session.agent_loop")
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")

try:
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi 未安装")


def _service(tmp_path):
    return _adapter.build_console_service(tmp_path, event_logger=None)


class TestSchemas:
    def test_conversation_tools(self):
        ids = {t["function"]["name"] for t in _ag.tool_schemas()}
        assert {"code_scan", "project_scan", "task_action", "create_task",
                "plan_development", "execute_plan", "task_continue", "external_route"} <= ids


class TestApproval:
    def test_plan_to_text(self):
        text = _ag.plan_to_text({"goal": "登录", "tasks": [{"title": "注册接口", "priority": "P0"}],
                                 "order": ["注册接口"], "acceptance": ["自测通过"]})
        assert "登录" in text and "注册接口" in text and "自测通过" in text

    def test_pending_plan_store(self, tmp_path):
        store = _ag.PendingPlanStore(tmp_path)
        store.save("s1", {"goal": "登录"})
        assert store.get("s1")["goal"] == "登录"
        store.clear("s1")
        assert store.get("s1") is None


class TestExecutePlan:
    def test_execute_creates_tasks(self, tmp_path):
        svc = _service(tmp_path)
        proj = svc.create_project("plan demo", name="PlanDemo")
        plan = {"goal": "登录", "tasks": [
            {"title": "注册接口", "description": "POST /register", "priority": "P0"},
            {"title": "登录接口", "description": "POST /login", "priority": "P0"},
        ], "order": ["注册接口", "登录接口"], "acceptance": ["自测通过"]}
        r = _ag.execute_plan(plan, project_id=proj.id, service=svc)
        assert r["ok"] is True
        assert len(r["created"]) == 2
        tasks = svc.list_backlog(proj.id)["tasks"]
        assert any(t["title"] == "注册接口" for t in tasks)
        assert any(t["title"] == "登录接口" for t in tasks)


class TestRunAgentNative:
    def test_tool_call_loop_and_answer(self, tmp_path, monkeypatch):
        plan = {"goal": "登录", "tasks": [{"title": "注册接口", "priority": "P0"}],
                "order": ["注册接口"], "acceptance": ["自测通过"], "ask_approval": True}
        # 意图门固定为 develop (避免消费 call_with_tools stub)
        monkeypatch.setattr(_ag, "understand_intent",
                            lambda message, **kw: _intent("develop", summary=message))
        # plan_development 内部不再走 call_with_tools (确定性 stub)
        monkeypatch.setattr(_ag, "plan_development", lambda goal, detail, **kw: plan)
        responses = [
            {"content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {
                "name": "plan_development", "arguments": json.dumps({"goal": "登录", "detail": "注册+JWT"})}}]},
            {"content": "计划已给出，请审批。", "tool_calls": []},
        ]
        monkeypatch.setattr(_ag, "call_with_tools", lambda messages, tools, **kw: responses.pop(0))
        r = _ag.run_agent_native("把登录做完", data_dir=tmp_path, project_id="P-1", max_rounds=2)
        assert r["calls"][0]["tool"] == "plan_development"
        assert r["calls"][0]["pending_plan"] is True
        assert r["calls"][0]["plan"]["goal"] == "登录"
        assert "审批" in r["answer"]

    def test_llm_down_rejected(self, tmp_path, monkeypatch):
        def boom(messages, tools, **kw):
            raise RuntimeError("no key")
        monkeypatch.setattr(_ag, "call_with_tools", boom)
        r = _ag.run_agent_native("你好", data_dir=tmp_path, project_id="P-1")
        assert r.get("rejected") is True


@requires_fastapi
class TestPlanApprovalHttp:
    def test_plan_then_approve_executes(self, tmp_path, monkeypatch):
        """计划 → 用户「可以」→ 模型语义判断批准 → 真实建任务进 backlog。"""
        import importlib as _il
        AG = _il.import_module("factory_console.session.agent_loop")
        _AGH = _il.import_module("factory-console.session.agent_loop")  # 连字符实例 (端点可能用)

        svc = _service(tmp_path)
        proj = svc.create_project("plan demo", name="PlanDemo")

        plan = {"goal": "登录", "tasks": [{"title": "注册接口", "description": "r", "priority": "P0"}],
                "order": ["注册接口"], "acceptance": ["自测通过"], "ask_approval": True}
        store = AG.PendingPlanStore(tmp_path)
        captured: dict = {}

        def fake_run_agent(message, **kw):
            captured["msg"] = message
            if "待审批的开发计划" in message:
                # 模型语义判断: 用户同意 → 执行计划 (真实建任务)
                pending = store.get(kw.get("session_id") or "")
                if pending:
                    r = AG.execute_plan(pending, project_id=proj.id, service=svc)
                    store.clear(kw.get("session_id") or "")
                    return {"answer": "✅ 计划已审批并执行。\n" + str(r.get("output") or ""),
                            "calls": [{"tool": "execute_plan", "ok": True, "output": r.get("output")}]}
            # 首次: 出计划
            store.save(kw.get("session_id") or "", plan)
            return {"answer": "📋 开发计划 (请审批): 目标: 登录 ...",
                    "calls": [{"tool": "plan_development", "ok": True, "output": "plan", "plan": plan, "pending_plan": True}]}

        monkeypatch.setattr(AG, "run_agent", fake_run_agent)
        monkeypatch.setattr(_AGH, "run_agent", fake_run_agent)  # 双保险
        app = _adapter.build_app(svc, event_logger=None, factory_root=tmp_path)
        with TestClient(app) as c:
            r = c.post("/api/sessions", json={"scope": "project", "project_id": proj.id, "title": "plan"})
            sid = r.json()["id"]
            # 1) 发需求 → 出计划
            r = c.post(f"/api/sessions/{sid}/messages", json={"message": "把登录功能做完"})
            assert r.status_code == 200, r.text
            # 待审批计划已存
            assert store.get(sid) is not None
            # 2) 用户「可以，开始吧」→ 模型语义批准 → 执行计划 → 建任务
            r = c.post(f"/api/sessions/{sid}/messages", json={"message": "可以，开始吧"})
            assert r.status_code == 200, r.text
            assert "待审批的开发计划" in captured["msg"]  # 计划注入模型上下文 (语义判断)
            tasks = svc.list_backlog(proj.id)["tasks"]
            assert any(t["title"] == "注册接口" for t in tasks)
            assert store.get(sid) is None  # 已执行清计划


class TestHardConvergence:
    """护栏 (Founder: 3次loop后还不清醒就追问): 工具调用达上限 → 硬停, 最后强制一轮收敛。

    覆盖:
    - 到 MAX_TOOL_CALLS 硬停 (不再无限调研/无限重试), 与轮数无关
    - 强制收敛轮不再给工具 (tools=None) → 模型只能回答
    - 信息仍不足 → 明确追问 (澄清问题), 不继续调工具
    """

    def test_hard_stop_at_tool_limit(self, tmp_path, monkeypatch):
        loop_rounds = []
        final_round = []
        # 意图门固定为 question (避免意图理解消费 tools=None 分支)
        monkeypatch.setattr(_ag, "understand_intent",
                            lambda message, **kw: _intent("question"))

        def fake_call(messages, tools, **kw):
            if tools is None:
                final_round.append(messages)
                return {"content": "根据扫描结果: 项目共 3 个模块, 建议先做登录。", "tool_calls": []}
            loop_rounds.append(messages)
            # 每轮 2 个工具调用 → 3 轮即达 MAX_TOOL_CALLS=6
            return {"content": "", "tool_calls": [
                {"id": f"c{i}", "type": "function", "function": {
                    "name": "project_status", "arguments": "{}"}} for i in range(2)]}

        monkeypatch.setattr(_ag, "call_with_tools", fake_call)
        r = _ag.run_agent_native("扫描一下项目", data_dir=tmp_path, project_id="P-1", max_rounds=10)
        assert not r.get("rejected")
        # 硬停: 恰好 MAX_TOOL_CALLS 次工具调用, 不超限
        assert len(r["calls"]) == _ag.MAX_TOOL_CALLS
        assert all(c["tool"] == "project_status" for c in r["calls"])
        # 强制收敛轮确实执行 (且不给工具)
        assert len(final_round) == 1
        assert "禁止再调用任何工具" in final_round[0][-1]["content"]
        assert r["answer"] and "登录" in r["answer"]

    def test_insufficient_info_asks_clarification(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ag, "understand_intent",
                            lambda message, **kw: _intent("question"))
        def fake_call(messages, tools, **kw):
            if tools is None:
                return {"content": "我还需要澄清: 你要做的是 App 还是 Web? 目标用户是谁?",
                        "tool_calls": []}
            return {"content": "", "tool_calls": [
                {"id": f"c{i}", "type": "function", "function": {
                    "name": "project_status", "arguments": "{}"}} for i in range(2)]}

        monkeypatch.setattr(_ag, "call_with_tools", fake_call)
        r = _ag.run_agent_native("帮我做个应用", data_dir=tmp_path, project_id="P-1", max_rounds=10)
        assert not r.get("rejected")
        # 信息不足 → 追问 (不编造, 不继续调研)
        assert "澄清" in r["answer"] or "?" in r["answer"]
        assert len(r["calls"]) == _ag.MAX_TOOL_CALLS

    def test_round_limit_also_forces_convergence(self, tmp_path, monkeypatch):
        """未达工具上限但轮数用尽 → 同样强制收敛 (每轮 1 个工具, max_rounds=3)。"""
        monkeypatch.setattr(_ag, "understand_intent",
                            lambda message, **kw: _intent("question"))
        def fake_call(messages, tools, **kw):
            if tools is None:
                return {"content": "好的, 已确认项目状态。", "tool_calls": []}
            return {"content": "", "tool_calls": [
                {"id": "c1", "type": "function", "function": {
                    "name": "project_status", "arguments": "{}"}}]}

        monkeypatch.setattr(_ag, "call_with_tools", fake_call)
        r = _ag.run_agent_native("看下项目", data_dir=tmp_path, project_id="P-1", max_rounds=3)
        assert not r.get("rejected")
        # 3 轮 × 1 工具 = 3 < 6, 但轮数用尽 → 强制收敛轮已跑
        assert len(r["calls"]) == 3
        assert r["answer"] == "好的, 已确认项目状态。"



def _intent(intent: str, **over: Any) -> dict[str, Any]:
    """测试用固定意图结构。"""
    d = {"intent": intent, "target": {"type": "project", "id": None}, "need": "info",
         "emotion": "neutral", "summary": "测试意图", "followup": None, "source": "stub"}
    d.update(over)
    return d


class TestIntentCore:
    """IntentCore: 真正 get 用户意图 (LLM 结构化 + 规则兜底), 不堆关键词。"""

    def test_understand_intent_llm_json(self):
        intent = _ag.understand_intent(
            "把登录功能做完，包括注册和 JWT",
            llm_fn=lambda p: ('{"intent": "develop", "target": {"type": "project", "id": "P-1"}, '
                              '"need": "creation", "emotion": "neutral", '
                              '"summary": "用户要做登录+注册+JWT", "followup": null}'),
        )
        assert intent["intent"] == "develop"
        assert intent["target"]["type"] == "project"
        assert intent["need"] == "creation"
        assert intent["source"] == "llm"

    def test_understand_intent_llm_bad_output_falls_back(self):
        intent = _ag.understand_intent("你好", llm_fn=lambda p: "我无法理解")
        assert intent["intent"] == "chat"  # 规则兜底
        assert intent["source"] == "fallback"

    def test_fallback_rules(self):
        assert _ag.understand_intent("你好", llm_fn=None)["intent"] == "chat"
        assert _ag.understand_intent("这回答太不负责了吧", llm_fn=None)["intent"] == "challenge"
        assert _ag.understand_intent("把登录功能做完", llm_fn=None)["intent"] == "develop"
        assert _ag.understand_intent("项目进度怎么样了？", llm_fn=None)["intent"] == "question"
        assert _ag.understand_intent("把 P0 任务标记完成", llm_fn=None)["intent"] == "operate"
        assert _ag.understand_intent("", llm_fn=None)["intent"] == "clarify"

    def test_route_for(self):
        assert "project_status" in _ag.route_for("question")
        assert "重新查询真实数据" in _ag.route_for("challenge")
        assert "plan_development" in _ag.route_for("develop")
        assert "external_route" in _ag.route_for("external")
        assert "澄清" in _ag.route_for("clarify")

    def test_format_intent(self):
        text = _ag.format_intent(_intent("challenge", emotion="dissatisfied"))
        assert "意图理解" in text and "challenge" in text and "dissatisfied" in text

    def test_skeptical_verification(self):
        """怀疑/确认式质疑 (是真正影响项目的么/靠谱吗) → challenge 验证, 不误伤普通查询。"""
        for q in ("是真正影响项目的么", "你说的这些真的会影响项目吗",
                  "这些任务确实是关键的吗", "靠谱吗", "能确定吗", "数据是真的吗"):
            r = _ag.understand_intent(q, llm_fn=None)
            assert r["intent"] == "challenge", q
            assert r["need"] == "verification", q
            assert r["emotion"] == "skeptical", q
        # 普通查询/开发不受影响
        assert _ag.understand_intent("项目进度是多少？", llm_fn=None)["intent"] == "question"
        assert _ag.understand_intent("把登录做完", llm_fn=None)["intent"] == "develop"


class TestIntentGate:
    """意图门: 按意图注入路由约束; clarify 直接追问; challenge 强制自查。"""

    def test_clarify_direct_ask_no_tools(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ag, "understand_intent", lambda message, **kw: _intent("clarify"))
        got: dict = {}

        def fake_call(messages, tools, **kw):
            got["tools"] = tools
            got["sys"] = [m["content"] for m in messages if m["role"] == "system"]
            return {"content": "我还没理解，请补充你想做什么？", "tool_calls": []}

        monkeypatch.setattr(_ag, "call_with_tools", fake_call)
        r = _ag.run_agent_native("？？", data_dir=tmp_path, project_id="P-1")
        assert r["intent"]["intent"] == "clarify"
        assert got["tools"] is None  # 不给工具 → 只能追问
        assert r["calls"] == []  # 不调研
        assert "补充" in r["answer"]

    def test_clarify_llm_down_honest_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ag, "understand_intent", lambda message, **kw: _intent("clarify"))

        def boom(messages, tools, **kw):
            raise RuntimeError("no key")

        monkeypatch.setattr(_ag, "call_with_tools", boom)
        r = _ag.run_agent_native("？？", data_dir=tmp_path, project_id="P-1")
        assert r["intent"]["intent"] == "clarify"
        assert "补充" in r["answer"]  # 诚实兜底追问, 不编造

    def test_challenge_injects_last_answer(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ag, "understand_intent", lambda message, **kw: _intent("challenge"))
        history = [
            {"role": "user", "content": "项目进度？"},
            {"role": "assistant", "content": "进度 27%（旧数据）"},
        ]
        seen: dict = {}

        def fake_call(messages, tools, **kw):
            seen["content"] = "\n".join(m["content"] for m in messages if m["role"] == "system")
            return {"content": "我重新查了，实际进度 30%，之前数据过时了。", "tool_calls": []}

        monkeypatch.setattr(_ag, "call_with_tools", fake_call)
        r = _ag.run_agent_native("这回答不负责吧", data_dir=tmp_path, project_id="P-1", history=history)
        assert "用户质疑的上一轮回答" in seen["content"]
        assert "进度 27%" in seen["content"]
        assert "重新查询真实数据" in seen["content"]
        assert "过时" in r["answer"] or "修正" in r["answer"]

    def test_develop_route_injected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ag, "understand_intent", lambda message, **kw: _intent("develop"))
        seen: dict = {}

        def fake_call(messages, tools, **kw):
            seen["sys"] = [m["content"] for m in messages if m["role"] == "system"]
            return {"content": "好的", "tool_calls": []}

        monkeypatch.setattr(_ag, "call_with_tools", fake_call)
        r = _ag.run_agent_native("把登录做完", data_dir=tmp_path, project_id="P-1")
        joined = "\n".join(seen["sys"])
        assert "意图理解" in joined
        assert "plan_development" in joined  # 开发意图 → 必须出计划审批
        assert r["intent"]["intent"] == "develop"



class TestChallengeVerificationGate:
    """质疑自查加深: challenge 首轮只给验证工具 + 未验证前置强制再查。"""

    def test_challenge_first_round_only_verification_tools(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ag, "understand_intent", lambda message, **kw: _intent("challenge"))
        rounds: list[list[str]] = []

        def fake_call(messages, tools, **kw):
            rounds.append([t["function"]["name"] for t in (tools or [])])
            return {"content": "好", "tool_calls": []}

        monkeypatch.setattr(_ag, "call_with_tools", fake_call)
        _ag.run_agent_native("这回答不负责吧", data_dir=tmp_path, project_id="P-1")
        # 第一轮 (非收敛轮) 的工具面 = 验证工具子集
        names = set(next(r for r in rounds if r))
        assert {"project_status", "code_scan", "project_scan", "search_code"} <= names
        # 挑战轮不给动作/计划/外部工具 (只验证, 不执行)
        assert not (names & {"task_action", "create_task", "plan_development",
                             "execute_plan", "delegate_external", "external_route"})

    def test_challenge_no_tool_first_round_forces_recheck(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ag, "understand_intent", lambda message, **kw: _intent("challenge"))
        sys_msgs: list[list[str]] = []

        def fake_call(messages, tools, **kw):
            sys_msgs.append([m["content"] for m in messages if m["role"] == "system"])
            if tools is None:  # 强制收敛轮
                return {"content": "已重新核实: 数据无误。", "tool_calls": []}
            return {"content": "（直接回答不调工具）", "tool_calls": []}

        monkeypatch.setattr(_ag, "call_with_tools", fake_call)
        r = _ag.run_agent_native("数据不对吧", data_dir=tmp_path, project_id="P-1", max_rounds=3)
        joined = "\n".join(str(x) for sub in sys_msgs for x in sub)
        assert "没有调用任何验证工具" in joined  # 首轮直接答被驳回 → 强制先验证
        assert not r.get("rejected")
        assert "重新核实" in r["answer"]


class TestExternalTools:
    """外部能力动态工具面: 通用设计 — 新增外部 agent 无需改代码。"""

    def _seed_agents(self, tmp_path, agents=None):
        (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
        (tmp_path / "agents" / "agents.json").write_text(json.dumps(
            {"agents": agents or {
                "codex.architect": {"id": "codex.architect", "name": "Architect", "role": "architect",
                                    "description": "架构审查", "source": "codex", "kind": "agent"},
                "claude.security": {"id": "claude.security", "name": "Sec", "role": "security",
                                    "description": "安全评估", "source": "claude", "kind": "agent"},
            }}, ensure_ascii=False), encoding="utf-8")

    def test_external_tool_schema_with_agents(self, tmp_path):
        from factory_console.session import external_tools as et

        self._seed_agents(tmp_path)
        schema = et.external_tool_schema(tmp_path)
        assert schema is not None
        fn = schema["function"]
        assert fn["name"] == "delegate_external"
        assert "codex.architect" in fn["description"]
        assert "agent_id" in fn["parameters"]["properties"]
        assert "task" in fn["parameters"]["required"]

    def test_external_tool_schema_none_without_agents(self, tmp_path):
        from factory_console.session import external_tools as et

        assert et.external_tool_schema(tmp_path) is None

    def test_tool_schemas_includes_external_when_available(self, tmp_path):
        self._seed_agents(tmp_path)
        ids = {t["function"]["name"] for t in _ag.tool_schemas(tmp_path)}
        assert "delegate_external" in ids
        assert "plan_development" in ids

    def test_tool_schemas_no_external_without_data(self):
        ids = {t["function"]["name"] for t in _ag.tool_schemas(None)}
        assert "delegate_external" not in ids

    def test_delegate_external_missing_adapter(self, tmp_path):
        from factory_console.session import external_tools as et

        r = et.delegate_external(tmp_path, "nope.agent", "任务")
        assert r["ok"] is False
        assert "未注册" in r["error"]

    def test_delegate_external_runs(self, tmp_path, monkeypatch):
        from factory_console.session import external_tools as et
        import factory_console.external_executor.executor as ex

        self._seed_agents(tmp_path)
        monkeypatch.setattr(ex, "run", lambda adapter, prompt, project_dir="", **kw: {
            "exit_code": 0, "output": "架构审查完成: OK", "error": "", "command": "codex exec ..."})
        monkeypatch.setattr(ex, "record_invocation", lambda *a, **kw: {})
        r = et.delegate_external(tmp_path, "codex.architect", "审查这个架构", project_id="P-1")
        assert r["ok"] is True
        assert "架构审查完成" in r["output"]
        assert r["agent"] == "codex.architect"

    def test_delegate_external_failure_honest(self, tmp_path, monkeypatch):
        from factory_console.session import external_tools as et
        import factory_console.external_executor.executor as ex

        self._seed_agents(tmp_path)
        monkeypatch.setattr(ex, "run", lambda adapter, prompt, project_dir="", **kw: {
            "exit_code": 1, "output": "", "error": "沙箱拒绝", "command": "codex exec ..."})
        monkeypatch.setattr(ex, "record_invocation", lambda *a, **kw: {})
        r = et.delegate_external(tmp_path, "codex.architect", "审查")
        assert r["ok"] is False
        assert "沙箱拒绝" in r["error"]


class TestContextContinuity:
    """上下文连贯性 (v1.1.210): Agent 主循环注入历史 + 锚定任务; WebUI 旧路由历史注入。"""

    def test_history_injected_into_agent_loop(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ag, "understand_intent", lambda message, **kw: _intent("question"))
        history = [
            {"role": "user", "content": "我想做个记账App"},
            {"role": "assistant", "content": "好的，帮你梳理记账App需求"},
            {"role": "user", "content": "先做基础功能"},
        ]
        seen: dict = {}

        def fake_call(messages, tools, **kw):
            seen["sys"] = [m["content"] for m in messages if m["role"] == "system"]
            return {"content": "好的", "tool_calls": []}

        monkeypatch.setattr(_ag, "call_with_tools", fake_call)
        _ag.run_agent_native("继续", data_dir=tmp_path, project_id="P-1", history=history)
        joined = "\n".join(seen["sys"])
        assert "最近对话" in joined
        assert "记账App" in joined          # 前文内容可见 → 不失忆
        assert "先做基础功能" in joined

    def test_anchored_task_injected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ag, "understand_intent", lambda message, **kw: _intent("question"))
        svc = _service(tmp_path)
        proj = svc.create_project("ctx", name="CtxDemo")
        task = svc.create_task(proj.id, title="登录接口", description="POST /login", priority="P0")

        class _FakeStore:
            def get_session(self, sid):
                return {"id": sid, "task_id": task["id"]}

        seen: dict = {}

        def fake_call(messages, tools, **kw):
            seen["sys"] = [m["content"] for m in messages if m["role"] == "system"]
            return {"content": "继续任务", "tool_calls": []}

        monkeypatch.setattr(_ag, "call_with_tools", fake_call)
        _ag.run_agent_native("继续", data_dir=tmp_path, project_id=proj.id,
                             service=svc, session_store=_FakeStore(), session_id="s1")
        joined = "\n".join(seen["sys"])
        assert "当前锚定任务" in joined
        assert "登录接口" in joined

    def test_send_message_injects_history(self, tmp_path):
        from factory_console.console_sessions import SessionStore, send_message

        store = SessionStore(tmp_path / "sessions.json")
        s = store.create_session(scope="project", project_id="P-1", title="t")
        prompts: list[str] = []

        def llm(prompt):
            prompts.append(prompt)
            return "回复一"

        send_message(store, s["id"], "第一句", llm_fn=llm)
        send_message(store, s["id"], "第二句", llm_fn=llm)
        assert "AI:" not in prompts[0]           # 首轮无历史 AI 回答
        assert "当前话题" in prompts[1]          # 第二轮注入话题视图 (v1.1.211)
        assert "第一句" in prompts[1]            # 上一轮用户消息
        assert "回复一" in prompts[1]            # 上一轮 AI 回答


class TestTopicLedger:
    """话题账本 (v1.1.211): 会话级分块/取舍/压缩 — 聊B不带A细节, 回A切回。"""

    def _llm(self, prompt):
        """真实行为 stub: 首条B切走, 后续延续, 回A切回。"""
        msg = prompt.split("用户最新消息: ")[1].strip()
        if "回到记账" in msg:
            return '{"continue": false, "label": "记账App", "switch_to": "t1"}'
        if msg.startswith("关于台球计分的问题B0"):
            return '{"continue": false, "label": "台球计分", "switch_to": null}'
        if "台球" in msg or "记账" in msg:
            return '{"continue": true}'
        return '{"continue": true}'

    def test_topic_split_and_switch_back(self, tmp_path):
        from factory_console.session import topic_ledger as tl

        ledger = tl.TopicLedger("s1")
        for i in range(3):
            ledger.append("user", f"关于记账App的问题A{i}", llm_fn=self._llm)
            ledger.append("assistant", f"记账回复{i}", llm_fn=self._llm)
        ledger.append("user", "关于台球计分的问题B0", llm_fn=self._llm)
        ledger.append("assistant", "台球回复0", llm_fn=self._llm)
        ledger.append("user", "关于台球计分的问题B1", llm_fn=self._llm)
        ledger.append("assistant", "台球回复1", llm_fn=self._llm)
        ledger.append("user", "回到记账App继续", llm_fn=self._llm)

        assert len(ledger.topics) == 2  # A + B, 不碎片
        a = next(t for t in ledger.topics if "记账" in str(t.get("label")) or t.get("id") == "t1")
        b = next(t for t in ledger.topics if t is not a)
        # 回A后: A 是当前块 (未冻结), B 冻结
        assert a.get("frozen") is False
        assert b.get("frozen") is True
        # 切走时 B 只留最近2条原文
        assert len(b["messages"]) <= 2

    def test_build_view_tradeoff(self, tmp_path):
        from factory_console.session import topic_ledger as tl

        ledger = tl.TopicLedger("s1")
        for i in range(3):
            ledger.append("user", f"关于记账App的问题A{i}", llm_fn=self._llm)
            ledger.append("assistant", f"记账回复{i}", llm_fn=self._llm)
        ledger.append("user", "关于台球计分的问题B0", llm_fn=self._llm)
        view_b = ledger.build_view()
        # 聊B时: 当前话题=台球, A 只占一行 (其他话题)
        assert "台球计分" in view_b
        assert "其他话题" in view_b
        # 回到A: 视图切回
        ledger.append("assistant", "台球回复0", llm_fn=self._llm)
        ledger.append("user", "回到记账App继续", llm_fn=self._llm)
        view_a = ledger.build_view()
        assert "当前话题" in view_a
        # 记账是当前块 (最近消息可见), 台球在"其他话题"一行
        assert "回到记账App继续" in view_a
        assert "关于台球计分" not in view_a  # B 的细节不再注入 (只一行摘要)

    def test_rolling_compress(self, tmp_path):
        from factory_console.session import topic_ledger as tl

        ledger = tl.TopicLedger("s1")
        for i in range(tl.COMPRESS_AT + 2):
            ledger.append("user", f"连续聊话题X第{i}轮", llm_fn=lambda p: '{"continue": true}')
            ledger.append("assistant", f"回复{i}", llm_fn=lambda p: '{"continue": true}')
        cur = ledger._active()
        assert len(cur["messages"]) <= tl.COMPRESS_AT + 1  # 滚动压缩生效
        assert cur.get("summary")  # 有摘要 (兜底拼接)
        # 视图总大小受控 (不会随对话无限增长)
        assert len(ledger.build_view()) < 3000

    def test_persist_roundtrip(self, tmp_path):
        from factory_console.session import topic_ledger as tl

        ledger = tl.TopicLedger("s9")
        ledger.append("user", "聊聊记账App", llm_fn=lambda p: '{"continue": true}')
        ledger.append("assistant", "好的", llm_fn=lambda p: '{"continue": true}')
        ledger.save(tmp_path)
        loaded = tl.TopicLedger.load(tmp_path, "s9")
        assert len(loaded.topics) == 1
        assert loaded.topics[0]["label"]

    def test_llm_down_keeps_current_block(self, tmp_path):
        from factory_console.session import topic_ledger as tl

        ledger = tl.TopicLedger("s1")
        ledger.append("user", "第一句", llm_fn=None)
        ledger.append("assistant", "回复", llm_fn=None)
        ledger.append("user", "第二句", llm_fn=None)  # LLM 挂 → 归当前块
        assert len(ledger.topics) == 1


class TestContextViewInjection:
    """context_view (话题账本视图) 优先注入 Agent 主循环。"""

    def test_context_view_priority(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_ag, "understand_intent", lambda message, **kw: _intent("question"))
        seen: dict = {}

        def fake_call(messages, tools, **kw):
            seen["sys"] = [m["content"] for m in messages if m["role"] == "system"]
            return {"content": "好", "tool_calls": []}

        monkeypatch.setattr(_ag, "call_with_tools", fake_call)
        _ag.run_agent_native("继续", data_dir=tmp_path, project_id="P-1",
                             context_view="【当前话题 · 记账App】\n用户: 上一轮问题")
        joined = "\n".join(seen["sys"])
        assert "当前话题 · 记账App" in joined

    def test_send_message_topic_view(self, tmp_path):
        from factory_console.console_sessions import SessionStore, send_message

        store = SessionStore(tmp_path / "sessions.json")
        s = store.create_session(scope="project", project_id="P-1", title="t")
        prompts: list[str] = []

        def llm(prompt):
            prompts.append(prompt)
            return "回复一"

        send_message(store, s["id"], "我想做个记账App", llm_fn=llm)
        send_message(store, s["id"], "先做基础功能", llm_fn=llm)
        # 第二轮 prompt 含话题视图 (当前话题 + 第一轮内容)
        assert "当前话题" in prompts[1]
        assert "记账App" in prompts[1]


class TestProjectStructure:
    """项目结构 (v1.1.214): 目录树/模块分布 — "了解项目真实结构" 不再答进度状态。"""

    def test_scan_structure_real(self, tmp_path):
        from factory_console.session import code_scan as cs

        # 构造迷你仓库 + project.json 指向它
        repo = tmp_path / "myrepo"
        (repo / "src").mkdir(parents=True)
        (repo / "docs").mkdir()
        (repo / "target").mkdir()  # 构建产物应被忽略
        (repo / "src" / "main.py").write_text("print(1)\nprint(2)\n", encoding="utf-8")
        (repo / "src" / "util.py").write_text("x=1\n", encoding="utf-8")
        (repo / "docs" / "readme.md").write_text("# r\n", encoding="utf-8")
        (repo / "target" / "big.bin").write_bytes(b"0" * 100)
        proj_dir = tmp_path / "workspace" / "projects" / "P-1"
        proj_dir.mkdir(parents=True)
        (proj_dir / "project.json").write_text(
            '{"id": "P-1", "workspace_dir": "%s"}' % repo, encoding="utf-8")

        r = cs.scan_structure(tmp_path, "P-1")
        assert r["ok"] is True
        names = [d["name"] for d in r["dirs"]]
        assert "src" in names and "docs" in names
        assert "target" not in names  # 构建产物忽略
        src = next(d for d in r["dirs"] if d["name"] == "src")
        assert src["files"] == 2 and src["loc"] == 3
        text = cs.format_structure(r, "Demo")
        assert "src/" in text and "main.py" in (text) or "2 文件" in text

    def test_tool_schema_includes_structure(self, tmp_path):
        ids = {t["function"]["name"] for t in _ag.tool_schemas(tmp_path)}
        assert "project_structure" in ids
