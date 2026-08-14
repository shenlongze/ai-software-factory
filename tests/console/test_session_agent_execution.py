"""tests/console/test_session_agent_execution.py — Agent Execution Kernel (S10-049 P0-P5)。

设计: docs/sprint10/S10-049-agent-execution-design.md §2
覆盖 (验收 A-K):
1. Agent Action 注册 (agent.execute_task 存在 + metadata sensitive/category)
2. Intent Router: run_task → agent.execute_task (+ execute_task 别名; 未路由仍报错)
3. Execution Context (AgentExecutionContext 继承 + task_id/agent_id/project_id)
4. Agent Runtime 薄调 (monkeypatch exec.cli.cmd_exec_run — 验证 root/args 参数)
5. 成功执行流程 (mock result → AgentExecutionResult success 统一结构)
6. 失败流程 (mock error/异常/缺参 → ActionResult error 明确)
7. Confirmation Gate (run_task 敏感 → 确认流; 拒绝 → 取消不执行)
8. select_agent (前端→flutter-dev / 默认 backend-1 / 显式 agent_id)
9. 审计记录 (record_execution 写文件 + load_records 读回 + execute_task 自动审计)
10. Conversation 澄清 (run_task 缺 project/task → CLARIFICATION)
11. Session 集成 (execute_task 摘要展示 agent/artifact/cost/duration)

全部 monkeypatch, 禁止真实 key/网络/真实 Runtime 执行。

basename 全仓库唯一 (test_session_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

ACT_MOD = importlib.import_module("factory-console.session.action")
ACTIONS_MOD = importlib.import_module("factory-console.session.actions")
ROUTER_MOD = importlib.import_module("factory-console.session.router")
INTENT_MOD = importlib.import_module("factory-console.session.intent")
CONF_MOD = importlib.import_module("factory-console.session.confirm")
CONV_MOD = importlib.import_module("factory-console.session.conversation")
AUDIT_MOD = importlib.import_module("factory-console.session.audit")
SESS_MOD = importlib.import_module("factory-console.session.session")
CTX_MOD = importlib.import_module("factory-console.session.context")


# ------------------------------------------------------------------ helpers


def _registry():
    """默认装配 (注册式: build_default_actions 一次性注册全部 Action)。"""
    return ACTIONS_MOD.build_default_actions()


def _intent(intent_type: str = "run_task", **params):
    return INTENT_MOD.IntentObject(intent_type=intent_type, params=params, raw="x")


def _exec_ctx(root: Path, intent=None, **kw):
    return ACT_MOD.ExecutionContext(
        workspace=root,
        session=CTX_MOD.SessionContext(workspace=str(root)),
        intent=intent,
        **kw,
    )


class _FakeExecCli:
    """exec.cli 桩 (monkeypatch _load_exec_cli 注入): 记录调用, 返回注入结果。"""

    def __init__(self, result: dict | None = None) -> None:
        self.calls: list[tuple[Path, Any]] = []
        self.result = result or {
            "ok": True,
            "command": "run",
            "result_id": "EXR-001",
            "status": "success",
            "error": None,
            "artifacts": [{"path": "/tmp/ws/patch.patch", "id": "art-1"}],
            "usage": {"cost_usd": "0.01", "total_tokens": 1234, "duration": "3.2s"},
            "exit_code": 0,
        }

    def cmd_exec_run(self, root, args):
        self.calls.append((root, args))
        return dict(self.result)


class _SpyGate:
    """Session 集成探针 gate: 记录 confirm 调用, 返回注入决策。"""

    def __init__(self, decision: bool = True) -> None:
        self.decision = decision
        self.calls: list[tuple[Any, Any, Any]] = []

    def confirm(self, action_name, intent, context):
        self.calls.append((action_name, intent, context))
        return self.decision


def _install_fake_exec(monkeypatch, result: dict | None = None) -> _FakeExecCli:
    fake = _FakeExecCli(result)
    monkeypatch.setattr(ACTIONS_MOD, "_load_exec_cli", lambda: fake)
    return fake


# ------------------------------------------------------------------ 1. Agent Action 注册 (验收 A/D)


def test_registry_has_execute_task_action():
    action = _registry().get("agent.execute_task")
    assert action is not None
    assert callable(action.handler)
    assert "Agent Runtime" in action.description


def test_execute_task_action_metadata():
    action = _registry().get("agent.execute_task")
    assert action.permission == "project"
    assert action.metadata.get("sensitive") is True
    assert action.metadata.get("category") == "execution"
    assert "cmd_exec_run" in action.metadata.get("service", "")


def test_default_registry_contains_all_actions():
    names = [a.name for a in _registry().list()]
    assert "agent.execute_task" in names
    assert set(names) >= {"create_project", "list_projects", "show_status"}


# ------------------------------------------------------------------ 2. Intent Router (验收 A)


def test_default_routes_maps_run_task():
    assert ROUTER_MOD.DEFAULT_ROUTES["run_task"] == "agent.execute_task"


def test_router_run_task_resolves_to_action():
    action = ROUTER_MOD.IntentRouter().route(_intent("run_task"), _registry())
    assert action.name == "agent.execute_task"


def test_router_execute_task_alias():
    action = ROUTER_MOD.IntentRouter().route(_intent("execute_task"), _registry())
    assert action.name == "agent.execute_task"


def test_full_chain_natural_language_to_execute_task():
    """A: \"帮我实现登录功能\" → run_task intent → agent.execute_task action。"""
    intent = INTENT_MOD.KeywordIntentParser().parse("帮我实现登录功能")
    assert intent is not None
    assert intent.intent_type == INTENT_MOD.INTENT_RUN_TASK
    assert intent.parameters.get("objective") == "登录功能"
    action = ROUTER_MOD.IntentRouter().route(intent, _registry())
    assert action.name == "agent.execute_task"


def test_unrouted_intent_still_raises():
    """回归: 未映射意图 (show_cost) 仍明确 UnknownIntentError (不静默)。"""
    with pytest.raises(ROUTER_MOD.UnknownIntentError):
        ROUTER_MOD.IntentRouter().route(_intent("show_cost"), _registry())


def test_keyword_parser_existing_rules_unaffected():
    """回归: 加 \"实现\" 关键词不破坏既有规则 (加/创建/未识别)。"""
    p = INTENT_MOD.KeywordIntentParser()
    assert p.parse("加测试").intent_type == INTENT_MOD.INTENT_RUN_TASK
    assert p.parse("创建一个APP").intent_type == INTENT_MOD.INTENT_CREATE_PROJECT
    assert p.parse("foobar") is None


# ------------------------------------------------------------------ 3. Execution Context / Result (验收 D)


def test_agent_execution_context_fields():
    ctx = ACTIONS_MOD.AgentExecutionContext(
        workspace=Path("tmp/ws"),
        session=CTX_MOD.SessionContext(workspace="tmp/ws"),
        user="alice",
        project="p1",
        task_id="T-1",
        agent_id="backend-1",
        project_id="p1",
    )
    assert ctx.workspace == Path("tmp/ws")
    assert ctx.user == "alice"
    assert ctx.project == "p1"
    assert ctx.task_id == "T-1"
    assert ctx.agent_id == "backend-1"
    assert ctx.project_id == "p1"


def test_agent_execution_context_defaults():
    ctx = ACTIONS_MOD.AgentExecutionContext(
        workspace=Path("w"), session=CTX_MOD.SessionContext()
    )
    assert ctx.task_id is None and ctx.agent_id is None and ctx.project_id is None
    assert ctx.intent is None  # 继承字段默认


def test_agent_execution_context_is_execution_context():
    """AgentExecutionContext 是 ExecutionContext 子类 (继承组合, 不破坏旧接口)。"""
    ctx = ACTIONS_MOD.AgentExecutionContext(
        workspace=Path("w"), session=CTX_MOD.SessionContext()
    )
    assert isinstance(ctx, ACT_MOD.ExecutionContext)
    ctx.require("user")  # 基线权限继承


def test_agent_execution_result_fields():
    result = ACTIONS_MOD.AgentExecutionResult(
        success=True,
        agent="backend-1",
        artifact="/tmp/p.patch",
        cost="0.01 · 1234 tokens",
        duration="3.2s",
        result_id="EXR-001",
        error=None,
    )
    assert result.success is True
    assert result.agent == "backend-1"
    assert result.artifact == "/tmp/p.patch"
    assert result.cost == "0.01 · 1234 tokens"
    assert result.duration == "3.2s"
    assert result.result_id == "EXR-001"
    assert result.error is None


def test_agent_execution_result_to_dict():
    result = ACTIONS_MOD.AgentExecutionResult(
        success=False, agent="backend-1", error="boom"
    )
    view = result.to_dict()
    assert view["success"] is False and view["agent"] == "backend-1"
    assert view["error"] == "boom"
    assert set(view) >= {"success", "agent", "artifact", "cost", "duration", "result_id", "error"}


# ------------------------------------------------------------------ 4. Agent Runtime 薄调 (验收 B)


def test_execute_task_calls_cmd_exec_run(monkeypatch, tmp_path):
    """B: execute_task 薄调 exec.cli.cmd_exec_run — root=workspace, args 逐项传递。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = _install_fake_exec(monkeypatch)
    intent = _intent("run_task", objective="登录功能")
    result = _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent))
    assert result.ok is True
    assert len(fake.calls) == 1
    call_root, args = fake.calls[0]
    assert call_root == root  # root = workspace (data_dir)
    assert args.project == str(root)  # 项目目录默认 workspace
    assert args.objective == "登录功能"
    assert args.agent == "backend-1"  # 默认 Agent (Selector)
    assert args.task == ""
    assert args.json is True


def test_execute_task_project_from_params(monkeypatch, tmp_path):
    """params.project 优先于 context.project/workspace (显式项目目录)。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = _install_fake_exec(monkeypatch)
    intent = _intent("run_task", objective="x", project="/tmp/explicit")
    result = _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent, project="ctx-p"))
    assert result.ok is True
    assert fake.calls[0][1].project == "/tmp/explicit"


def test_execute_task_project_from_context(monkeypatch, tmp_path):
    """context.project 次优先 (会话当前项目)。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = _install_fake_exec(monkeypatch)
    intent = _intent("run_task", objective="x")
    result = _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent, project="p1"))
    assert result.ok is True
    assert fake.calls[0][1].project == "p1"


def test_execute_task_project_default_workspace(monkeypatch, tmp_path):
    """无显式 project → workspace 兜底。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = _install_fake_exec(monkeypatch)
    intent = _intent("run_task", objective="x")
    result = _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent))
    assert result.ok is True
    assert fake.calls[0][1].project == str(root)


def test_execute_task_task_id_passthrough(monkeypatch, tmp_path):
    """task_id / task 参数传递到 args.task。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = _install_fake_exec(monkeypatch)
    intent = _intent("run_task", objective="x", task_id="T-42")
    _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent))
    assert fake.calls[0][1].task == "T-42"


def test_execute_task_provider_employee_test_cmd_passthrough(monkeypatch, tmp_path):
    """provider/employee/test_cmd 参数透传 (Runtime 定制, 不复制业务)。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = _install_fake_exec(monkeypatch)
    intent = _intent("run_task", objective="x", provider="deepseek", employee="e1", test_cmd="pytest")
    _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent))
    args = fake.calls[0][1]
    assert args.provider == "deepseek"
    assert args.employee == "e1"
    assert args.test_cmd == "pytest"


def test_execute_task_selects_frontend_agent(monkeypatch, tmp_path):
    """objective 含前端特征 → args.agent = flutter-dev (Selector 生效于薄调)。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = _install_fake_exec(monkeypatch)
    intent = _intent("run_task", objective="帮我实现登录界面")
    _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent))
    assert fake.calls[0][1].agent == "flutter-dev"


def test_execute_task_explicit_agent_id(monkeypatch, tmp_path):
    """显式 agent_id 覆盖 Selector 默认。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = _install_fake_exec(monkeypatch)
    intent = _intent("run_task", objective="x", agent_id="senior-9")
    _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent))
    assert fake.calls[0][1].agent == "senior-9"


# ------------------------------------------------------------------ 5. 成功流程 (验收 D)


def test_execute_task_success_result(monkeypatch, tmp_path):
    """D: mock 成功 → AgentExecutionResult success 统一结构 (全部字段)。"""
    root = tmp_path / "ws"
    root.mkdir()
    _install_fake_exec(monkeypatch)
    intent = _intent("run_task", objective="实现登录功能")
    result = _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent))
    assert result.ok is True
    assert result.status == "ok"
    assert result.error is None
    execution = result.data["execution"]
    assert execution["success"] is True
    assert execution["agent"] == "backend-1"
    assert execution["artifact"] == "/tmp/ws/patch.patch"
    assert "0.01" in execution["cost"]
    assert execution["duration"] == "3.2s"
    assert execution["result_id"] == "EXR-001"
    assert execution["error"] is None


def test_execute_task_success_message_includes_artifact(monkeypatch, tmp_path):
    """成功消息含 agent + 产物路径 (可读摘要)。"""
    root = tmp_path / "ws"
    root.mkdir()
    _install_fake_exec(monkeypatch)
    intent = _intent("run_task", objective="x")
    result = _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent))
    assert "backend-1" in result.message
    assert "/tmp/ws/patch.patch" in result.message


def test_execute_task_no_artifacts_still_ok(monkeypatch, tmp_path):
    """无产物 → artifact 空串, 结果仍 ok (失败安全, 不崩溃)。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = _install_fake_exec(monkeypatch, result={"ok": True, "exit_code": 0, "usage": {}})
    intent = _intent("run_task", objective="x")
    result = _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent))
    assert result.ok is True
    assert result.data["execution"]["artifact"] == ""
    assert result.data["execution"]["cost"] == ""


# ------------------------------------------------------------------ 6. 失败流程 (验收 E)


def test_execute_task_failure_dict(monkeypatch, tmp_path):
    """E: Runtime 返回失败 dict → ActionResult error 明确 (不吞)。"""
    root = tmp_path / "ws"
    root.mkdir()
    _install_fake_exec(
        monkeypatch,
        result={"ok": False, "error": "project dir not found: /nope", "exit_code": 1},
    )
    intent = _intent("run_task", objective="x", project="/nope")
    result = _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent))
    assert result.ok is False
    assert result.status == "error"
    assert "project dir not found" in result.message
    assert "project dir not found" in result.error
    assert result.data["execution"]["success"] is False


def test_execute_task_exception_safe(monkeypatch, tmp_path):
    """E: cmd_exec_run 抛异常 → ActionResult(error) 明确, 不裸抛。"""
    root = tmp_path / "ws"
    root.mkdir()

    class _Boom:
        def cmd_exec_run(self, root, args):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(ACTIONS_MOD, "_load_exec_cli", lambda: _Boom())
    intent = _intent("run_task", objective="x")
    result = _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent))
    assert result.ok is False
    assert result.error == "provider unavailable"
    assert "provider unavailable" in result.message


def test_execute_task_missing_objective_error(tmp_path):
    """E: 无 objective 且无 task → 明确错误 (不发起空执行)。"""
    root = tmp_path / "ws"
    root.mkdir()
    intent = _intent("run_task")
    result = _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent))
    assert result.ok is False
    assert "缺少任务描述" in result.message
    assert "缺少任务描述" in result.error


# ------------------------------------------------------------------ 7. Confirmation Gate (验收 F)


def test_run_task_is_sensitive_action():
    """F: run_task ∈ ConfirmationGate 默认敏感集合 (需确认)。"""
    gate = CONF_MOD.ConfirmationGate()
    assert "run_task" in gate.sensitive_actions


def test_gate_confirms_run_task_with_plan(capsys):
    """F: gate.confirm(\"run_task\", intent) → 打印执行计划 + 确认流生效。"""
    gate = CONF_MOD.ConfirmationGate()
    approved = gate.confirm(
        "run_task", _intent("run_task", objective="登录功能"), confirm_fn=lambda: "y"
    )
    assert approved is True
    out = capsys.readouterr().out
    assert "将执行: run_task" in out
    assert "登录功能" in out


def test_session_run_task_invokes_gate(monkeypatch, capsys, tmp_path):
    """F: Session 派发 run_task → gate 收到 intent 类型 run_task (确认判定)。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = _install_fake_exec(monkeypatch)
    spy = _SpyGate(decision=True)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
        confirmation_gate=spy,
    )
    sess._dispatch("帮我实现登录功能")
    assert len(spy.calls) == 1
    assert spy.calls[0][0] == "run_task"  # 确认判定以 intent 类型为准
    assert len(fake.calls) == 1  # 确认通过 → 执行


def test_session_run_task_rejected_cancelled(monkeypatch, capsys, tmp_path):
    """F: gate 拒绝 → \"已取消\", cmd_exec_run 不被调用。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = _install_fake_exec(monkeypatch)
    spy = _SpyGate(decision=False)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
        confirmation_gate=spy,
    )
    sess._dispatch("帮我实现登录功能")
    assert len(spy.calls) == 1
    assert fake.calls == []  # 拒绝 → 不执行
    out = capsys.readouterr().out
    assert "已取消" in out


# ------------------------------------------------------------------ 8. select_agent (验收 C)


def test_select_agent_explicit_agent_id():
    assert ACTIONS_MOD.select_agent(_intent("run_task", agent_id="custom-1")) == "custom-1"


@pytest.mark.parametrize(
    "objective,expected",
    [
        ("实现前端页面", "flutter-dev"),
        ("写个 flutter 组件", "flutter-dev"),
        ("修复 ui 布局", "flutter-dev"),
        ("优化界面交互", "flutter-dev"),
    ],
)
def test_select_agent_frontend_keywords(objective, expected):
    assert ACTIONS_MOD.select_agent(_intent("run_task", objective=objective)) == expected


def test_select_agent_default_backend():
    assert ACTIONS_MOD.select_agent(_intent("run_task", objective="实现登录功能")) == "backend-1"
    assert ACTIONS_MOD.select_agent(_intent("run_task", objective="")) == "backend-1"


def test_select_agent_none_intent_safe():
    assert ACTIONS_MOD.select_agent(None) == "backend-1"  # 失败安全


# ------------------------------------------------------------------ 9. 审计记录 (验收 G)


def test_record_execution_writes_and_reads(tmp_path):
    """G: record_execution 写文件 + load_records 读回 (append 语义)。"""
    records_file = tmp_path / "exec" / "execution_records.json"
    AUDIT_MOD.record_execution({"intent": "run_task", "agent": "backend-1"}, records_file)
    AUDIT_MOD.record_execution({"intent": "run_task", "agent": "flutter-dev"}, records_file)
    records = AUDIT_MOD.load_records(records_file)
    assert len(records) == 2
    assert records[0]["intent"] == "run_task"
    assert records[1]["agent"] == "flutter-dev"


def test_load_records_missing_file_empty(tmp_path):
    assert AUDIT_MOD.load_records(tmp_path / "nope.json") == []


def test_load_records_corrupt_file_empty(tmp_path):
    bad = tmp_path / "records.json"
    bad.write_text("not-json{{{", encoding="utf-8")
    assert AUDIT_MOD.load_records(bad) == []


def test_load_records_non_list_file_empty(tmp_path):
    bad = tmp_path / "records.json"
    bad.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    assert AUDIT_MOD.load_records(bad) == []


def test_record_execution_creates_parent_dirs(tmp_path):
    """目录不存在 → 自动创建 (失败安全写)。"""
    records_file = tmp_path / "a" / "b" / "c.json"
    AUDIT_MOD.record_execution({"intent": "run_task"}, records_file)
    assert records_file.is_file()
    assert AUDIT_MOD.load_records(records_file) == [{"intent": "run_task"}]


def test_execute_task_writes_audit_record(monkeypatch, tmp_path):
    """G: execute_task 成功后自动写审计记录 (workspace/exec/execution_records.json)。"""
    root = tmp_path / "ws"
    root.mkdir()
    _install_fake_exec(monkeypatch)
    intent = _intent("run_task", objective="实现登录功能", task_id="T-9")
    _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent))
    records = AUDIT_MOD.load_records(root / "exec" / "execution_records.json")
    assert len(records) == 1
    record = records[0]
    assert record["intent"] == "run_task"
    assert record["action"] == "agent.execute_task"
    assert record["agent"] == "backend-1"
    assert record["task"] == "实现登录功能"
    assert record["result"] == "success"
    assert record["result_id"] == "EXR-001"
    assert record["timestamp"]
    assert record["error"] is None


def test_execute_task_failure_still_audited(monkeypatch, tmp_path):
    """失败执行同样入审计 (result=failed + error) — 完整审计链。"""
    root = tmp_path / "ws"
    root.mkdir()
    _install_fake_exec(
        monkeypatch,
        result={"ok": False, "error": "project dir not found", "exit_code": 1},
    )
    intent = _intent("run_task", objective="x", project="/nope")
    _registry().get("agent.execute_task").execute(_exec_ctx(root, intent=intent))
    records = AUDIT_MOD.load_records(root / "exec" / "execution_records.json")
    assert len(records) == 1
    assert records[0]["result"] == "failed"
    assert "project dir not found" in records[0]["error"]


def test_audit_records_default_path_is_factory_dir():
    """缺省审计文件 = ~/.factory/exec/execution_records.json (workspace 缺省即 data_dir)。"""
    assert AUDIT_MOD.DEFAULT_RECORDS_FILE == Path.home() / ".factory" / "exec" / "execution_records.json"


# ------------------------------------------------------------------ 10. Conversation 澄清 (验收 H)


def test_conversation_run_task_missing_target_clarification():
    """H: \"帮我实现登录功能\" (缺 project/task) → CLARIFICATION + 指引消息。"""
    mgr = CONV_MOD.ConversationManager()
    resp = mgr.handle("帮我实现登录功能", INTENT_MOD.KeywordIntentParser())
    assert resp.state == CONV_MOD.ConversationState.CLARIFICATION
    assert resp.needs_input is True
    assert "需要指定项目或任务" in resp.message
    assert mgr.pending_intent is None  # 目标未明确 → 不挂起


def test_conversation_run_task_with_project_confirmation():
    """run_task 带 project 参数 → 正常 CONFIRMATION (不误澄清)。"""
    mgr = CONV_MOD.ConversationManager()
    resp = mgr.handle("给 p1 项目实现登录", _FixedParser(_intent("run_task", project="p1", objective="登录")))
    assert resp.state == CONV_MOD.ConversationState.CONFIRMATION
    assert mgr.pending_intent is not None


def test_conversation_run_task_with_task_confirmation():
    """run_task 带 task_id → 正常 CONFIRMATION。"""
    mgr = CONV_MOD.ConversationManager()
    resp = mgr.handle("执行任务 T-42", _FixedParser(_intent("run_task", task_id="T-42")))
    assert resp.state == CONV_MOD.ConversationState.CONFIRMATION
    assert mgr.pending_intent.parameters["task_id"] == "T-42"


def test_conversation_other_intents_unaffected():
    """回归: create_project 等其它 intent 不受澄清分支影响。"""
    mgr = CONV_MOD.ConversationManager()
    resp = mgr.handle("创建一个APP", INTENT_MOD.KeywordIntentParser())
    assert resp.state == CONV_MOD.ConversationState.CONFIRMATION


# ------------------------------------------------------------------ 11. Session 集成 (验收 P5)


def test_session_execute_task_renders_summary(monkeypatch, capsys, tmp_path):
    """P5: Session 展示 AgentExecutionResult 摘要 (agent/artifact/cost/duration)。"""
    root = tmp_path / "ws"
    root.mkdir()
    _install_fake_exec(monkeypatch)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("帮我实现登录功能")
    out = capsys.readouterr().out
    assert "✔ 任务执行完成" in out
    assert "agent: backend-1" in out
    assert "artifact: /tmp/ws/patch.patch" in out
    assert "cost: 0.01 · 1234 tokens" in out
    assert "duration: 3.2s" in out


def test_session_execute_task_failure_renders_error(monkeypatch, capsys, tmp_path):
    """E+P5: 失败 → ❌ 明确错误展示 (不崩溃会话)。"""
    root = tmp_path / "ws"
    root.mkdir()
    _install_fake_exec(
        monkeypatch,
        result={"ok": False, "error": "project dir not found: /nope", "exit_code": 1},
    )
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("帮我实现登录功能")
    out = capsys.readouterr().out
    assert "❌ 任务执行失败" in out
    assert "project dir not found" in out


def test_session_execute_task_audit_written(monkeypatch, capsys, tmp_path):
    """端到端: Session 派发 → 执行 → 审计记录落盘 (workspace 隔离)。"""
    root = tmp_path / "ws"
    root.mkdir()
    _install_fake_exec(monkeypatch)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("帮我实现登录功能")
    records = AUDIT_MOD.load_records(root / "exec" / "execution_records.json")
    assert len(records) == 1
    assert records[0]["action"] == "agent.execute_task"
    capsys.readouterr()


# ------------------------------------------------------------------ helpers (conversation)


class _FixedParser(INTENT_MOD.IntentParser):
    """固定意图解析器 (注入带参 run_task intent 验证澄清分支)。"""

    def __init__(self, intent) -> None:
        self._intent = intent

    def parse(self, text: str):
        return self._intent
