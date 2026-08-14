"""tests/console/test_session_intent_execution.py — Intent 执行链端到端 (S10-048 P0+P1)。

设计: docs/sprint10/S10-048-intent-kernel-design.md §2.1 数据流
覆盖 (验收 A-F):
A. "创建一个APP" → IntentObject(create_project) → router → create_project Action
   执行 — monkeypatch Service Layer (org.cli.cmd_project_register) 验证完整调用链
B. list_projects 读真实 projects.json (tmp 工作区, org 规范格式)
C. show_status 显示 workspace/session 状态
D. 注册式: 默认装配 ActionRegistry register/get/list + IntentRouter 声明式映射
E. 未路由 Intent → 明确提示 (不静默)
F. Session._dispatch 自然语言输入 (非 "/") 触发 Action 执行 + Renderer 展示

basename 全仓库唯一 (test_session_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

ACT_MOD = importlib.import_module("factory-console.session.action")
ACTIONS_MOD = importlib.import_module("factory-console.session.actions")
ROUTER_MOD = importlib.import_module("factory-console.session.router")
INTENT_MOD = importlib.import_module("factory-console.session.intent")
SESS_MOD = importlib.import_module("factory-console.session.session")
CTX_MOD = importlib.import_module("factory-console.session.context")
RENDER_MOD = importlib.import_module("factory-console.session.renderer")


def _write_projects(root: Path, projects: dict) -> Path:
    """按 org 规范格式写 projects.json ({"projects": {id: {name}}} — FactoryCLI 同口径)。"""
    path = root / "org" / "projects.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"projects": projects}, ensure_ascii=False), encoding="utf-8")
    return path


def _registry():
    """默认装配 (验收 D: register/get/list 全来自 build_default_actions, 无硬编码 if)。"""
    return ACTIONS_MOD.build_default_actions()


def _exec_ctx(root: Path, **kw):
    return ACT_MOD.ExecutionContext(
        workspace=root,
        session=CTX_MOD.SessionContext(workspace=str(root)),
        **kw,
    )


class _FakeOrgCli:
    """Service Layer 桩 (monkeypatch _load_org_cli 注入): 记录调用, 返回规范结果。"""

    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    def cmd_project_register(self, root, args):
        self.calls.append((root, args))
        return {
            "ok": True,
            "project": {"id": "p1", "name": args.name or "APP"},
            "analysis_ref": None,
            "baseline_ref": None,
            "snapshot_ref": None,
            "exit_code": 0,
        }


class _FixedIntentParser(INTENT_MOD.IntentParser):
    """固定意图解析器 (测试注入: 产生无路由/定制意图)。"""

    def __init__(self, intent_type: str) -> None:
        self.intent_type = intent_type

    def parse(self, text: str):
        return INTENT_MOD.IntentObject(intent_type=self.intent_type, raw=text)


# ------------------------------------------------------------------ A: 调用链 (自然语言 → Action → Service)


def test_chain_create_project_executes_service_layer(monkeypatch, tmp_path):
    """A: "创建一个APP" → IntentObject(create_project) → router → Action → Service Layer。"""
    root = tmp_path / "ws"
    root.mkdir()
    # ① 解析
    intent = INTENT_MOD.KeywordIntentParser().parse("创建一个APP")
    assert intent.intent_type == INTENT_MOD.INTENT_CREATE_PROJECT
    assert intent.parameters["name"] == "一个APP"
    # ② 路由 (声明式映射 → Action 实例)
    registry = _registry()
    action = ROUTER_MOD.IntentRouter().route(intent, registry)
    assert action.name == "create_project"
    # ③ 执行 — monkeypatch Service Layer (真实 org.cli 模块属性替换, 验证调用链)
    org_cli = ACTIONS_MOD._load_org_cli()  # 触发 sys.path 挂载 (同 cli_factory 薄代理)
    calls: list[tuple[object, object]] = []

    def fake_register(root, args):
        calls.append((root, args))
        return {
            "ok": True,
            "project": {"id": "p1", "name": args.name},
            "analysis_ref": "an-1",
            "baseline_ref": "bl-1",
            "snapshot_ref": "sn-1",
            "exit_code": 0,
        }

    monkeypatch.setattr(org_cli, "cmd_project_register", fake_register)
    result = action.execute(_exec_ctx(root, intent=intent))
    # ④ 断言: Service Layer 收到 root=workspace, repo_path 默认 workspace, name 来自 intent
    assert len(calls) == 1
    assert calls[0][0] == root
    assert calls[0][1].repo_path == str(root)  # 设计 §2.3: workspace 作为 --repo-path 默认
    assert calls[0][1].name == "一个APP"  # intent 参数传递
    # ⑤ 结果结构化 → 渲染
    assert result.ok is True
    assert "APP" in result.message
    assert result.data["analysis_ref"] == "an-1"


def test_chain_create_project_error_result(monkeypatch, tmp_path):
    """Service Layer 返回失败 dict → ActionResult(ok=False) 明确携带 error (不吞)。"""
    root = tmp_path / "ws"
    root.mkdir()
    org_cli = ACTIONS_MOD._load_org_cli()
    monkeypatch.setattr(
        org_cli,
        "cmd_project_register",
        lambda root, args: {"ok": False, "error": "repo 不存在", "exit_code": 1},
    )
    intent = INTENT_MOD.KeywordIntentParser().parse("创建一个APP")
    action = ROUTER_MOD.IntentRouter().route(intent, _registry())
    result = action.execute(_exec_ctx(root, intent=intent))
    assert result.ok is False
    assert result.status == "error"
    assert "repo 不存在" in result.message
    assert result.error == "repo 不存在"


# ------------------------------------------------------------------ B: list_projects 读真实 projects.json


def test_list_projects_reads_real_projects_json(tmp_path):
    """B: list_projects 读真实 projects.json (tmp 工作区 org 数据空间)。"""
    root = tmp_path / "ws"
    root.mkdir()
    _write_projects(
        root,
        {"p1": {"name": "台球计分APP"}, "p2": {"name": "电商APP"}},
    )
    action = ROUTER_MOD.IntentRouter().route(
        INTENT_MOD.IntentObject(intent_type="list_projects"), _registry()
    )
    result = action.execute(_exec_ctx(root))
    assert result.ok is True
    assert result.data["count"] == 2
    assert result.data["rows"] == [["p1", "台球计分APP"], ["p2", "电商APP"]]
    # 渲染 → 表格展示 (data 键提升)
    out = RENDER_MOD.HumanRenderer().render(result.to_dict())
    assert "台球计分APP" in out and "电商APP" in out


def test_list_projects_missing_file_empty(tmp_path):
    """projects.json 缺失 → 空列表 (失败安全, 永不抛)。"""
    root = tmp_path / "ws"
    root.mkdir()
    action = ROUTER_MOD.IntentRouter().route(
        INTENT_MOD.IntentObject(intent_type="list_projects"), _registry()
    )
    result = action.execute(_exec_ctx(root))
    assert result.ok is True and result.data["count"] == 0
    assert result.data["rows"] == []


# ------------------------------------------------------------------ C: show_status 显示 workspace/session 状态


def test_show_status_displays_workspace_session(tmp_path):
    """C: show_status 显示 workspace/session/项目数/用户。"""
    root = tmp_path / "ws"
    root.mkdir()
    _write_projects(root, {"p1": {"name": "APP"}})
    cm = CTX_MOD.ContextManager(workspace=str(root))
    cm.update(current_project="p1", current_agent="backend-1")
    ctx = ACT_MOD.ExecutionContext(workspace=root, session=cm.get(), user="alice")
    action = ROUTER_MOD.IntentRouter().route(
        INTENT_MOD.IntentObject(intent_type="show_status"), _registry()
    )
    result = action.execute(ctx)
    assert result.ok is True
    data = result.data
    assert data["workspace"] == str(root)
    assert data["session_id"] == cm.get().session_id
    assert data["current_project"] == "p1"
    assert data["current_agent"] == "backend-1"
    assert data["project_count"] == 1
    assert data["user"] == "alice"
    # 渲染 → 表格含 workspace/session 字段
    out = RENDER_MOD.HumanRenderer().render(result.to_dict())
    assert str(root) in out and "session_id" in out


# ------------------------------------------------------------------ E: 未路由 Intent → 明确提示 (不静默)


def test_session_unrouted_intent_explicit_hint(capsys):
    """E: 未路由意图 (show_cost 无默认路由) → 明确提示, 含意图类型与指引。"""
    sess = SESS_MOD.InteractiveSession(intent_parser=_FixedIntentParser("show_cost"))
    sess._dispatch("看看成本")
    out = capsys.readouterr().out
    assert "未识别的意图" in out
    assert "show_cost" in out
    assert "创建项目" in out  # 指引


# ------------------------------------------------------------------ F: Session 自然语言输入触发 Action


def test_session_dispatch_natural_language_triggers_action(monkeypatch, capsys, tmp_path):
    """F: Session 内自然语言输入 (非 "/") → Intent → Action → Service → Render。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = _FakeOrgCli()
    monkeypatch.setattr(ACTIONS_MOD, "_load_org_cli", lambda: fake)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("创建一个APP")
    assert len(fake.calls) == 1
    assert fake.calls[0][0] == root  # root = workspace
    assert fake.calls[0][1].repo_path == str(root)
    out = capsys.readouterr().out
    assert "项目已注册" in out  # Renderer 展示 ActionResult 消息
    assert "✔" in out


def test_session_dispatch_list_projects_natural_language(tmp_path, capsys):
    """F: "项目列表" → list_projects Action → 渲染真实 projects.json 数据。"""
    root = tmp_path / "ws"
    root.mkdir()
    _write_projects(root, {"p1": {"name": "台球计分APP"}})
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("项目列表")
    out = capsys.readouterr().out
    assert "台球计分APP" in out  # 表格渲染真实数据


def test_session_dispatch_show_status_natural_language(tmp_path, capsys):
    """F: "状态" → show_status Action → 渲染 workspace/session。"""
    root = tmp_path / "ws"
    root.mkdir()
    _write_projects(root, {"p1": {"name": "APP"}})
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("状态")
    out = capsys.readouterr().out
    assert "workspace" in out
    assert str(root) in out


def test_session_dispatch_unrecognized_input_hint(capsys):
    """未识别输入 → 明确提示 (含 未知命令 + 未识别意图 + 指引; 基线不回归)。"""
    sess = SESS_MOD.InteractiveSession()
    sess._dispatch("foobar")
    out = capsys.readouterr().out
    assert "未知命令" in out and "foobar" in out
    assert "未识别意图" in out
    assert "创建项目" in out


def test_session_sets_intent_source_session(monkeypatch, capsys, tmp_path):
    """设计 §2.2: 会话派发注入 intent.source="session" (审计)。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = _FakeOrgCli()
    monkeypatch.setattr(ACTIONS_MOD, "_load_org_cli", lambda: fake)
    seen: dict[str, object] = {}

    class _SpyParser(INTENT_MOD.IntentParser):
        def parse(self, text):
            seen["intent"] = INTENT_MOD.IntentObject(
                intent_type="create_project", params={"name": "x"}, raw=text
            )
            return seen["intent"]

    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
        intent_parser=_SpyParser(),
    )
    sess._dispatch("创建一个APP")
    assert seen["intent"].source == "session"
