"""test_session_ux_blockers.py — 2026-08-19 测试可继续性修复 (交互链路 UX 挡路点)。

覆盖:
1. 中文退出命令 ("退出") 真正退出会话 (原只有 exit/quit)
2. 确认取消提示不再误导 "退出会话" (原提示像是要退出整个会话)
3. 项目执行失败给出原因 (原 "10 任务失败" 黑盒)
basename 全仓库唯一 (test_session_* 前缀)。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from importlib import import_module

ACT = import_module("factory-console.session.actions")
CTX = import_module("factory-console.session.context")
ORCH = import_module("factory-console.session.orchestrator")
SESS = import_module("factory-console.session.session")
INT = import_module("factory-console.session.intent")


class _FakeChat:
    def answer(self, question, **kw):
        return f"AI: 测试回答 {question}"

    def is_fallback(self, a):
        return False


class FakeOrgCli:
    """org CLI 桩: 记录调用, 返回规范结果 (同 test_session_product 模式)。"""

    def cmd_project_register(self, root, args):
        return {
            "ok": True,
            "project": {"id": "p1", "name": args.name, "slug": "scorepocket"},
            "analysis_ref": None,
            "baseline_ref": None,
            "snapshot_ref": None,
            "exit_code": 0,
        }


class _DenyGate:
    """确认门桩: 永远拒绝 (取消路径)。"""

    def confirm(self, action_name, intent, context=None, **kw):
        return False


class _FakeOrchestrator:
    """ExecutionOrchestrator 桩: 执行返回失败 + 错误原因。"""

    def __init__(self, *a, **k):
        pass

    def needs_resume(self, slug):
        return False

    def execute_project(self, slug):
        return ORCH.ExecutionResult(
            project=slug,
            status="failed",
            completed_tasks=0,
            failed_tasks=2,
            errors=["task-1: provider error: openai request failed: network down"],
        )


def _session(workspace=None, **kw):
    return SESS.InteractiveSession(
        chat_service=_FakeChat(),
        context_manager=CTX.ContextManager(workspace=workspace) if workspace else None,
        **kw,
    )


def test_chinese_exit_command_exits(monkeypatch, capsys):
    """'退出' 结束会话 (原只有 exit/quit; '退出' 会被聊天兜底吞掉)。"""
    sess = _session()
    monkeypatch.setattr("builtins.input", lambda prompt="> ": "退出")
    assert sess.run() == 0
    out = capsys.readouterr().out
    assert "已退出会话" in out


def test_cancel_message_not_exit_hint(capsys):
    """确认取消提示: '已取消本次操作', 不再误导 '输入 exit 或 quit 退出会话'。"""
    sess = _session(confirmation_gate=_DenyGate())
    sess._dispatch("创建一个测试项目")
    out = capsys.readouterr().out
    assert "已取消本次操作" in out
    assert "退出会话" not in out


def test_execute_failure_shows_reason(monkeypatch, capsys, tmp_path):
    """执行失败给出示例原因 + 诊断指引 (原黑盒 'N 任务失败')。"""
    org = FakeOrgCli()
    monkeypatch.setattr(ACT, "_load_org_cli", lambda: org)
    monkeypatch.setattr(ACT, "ExecutionOrchestrator", _FakeOrchestrator)
    root = tmp_path / "ws"
    root.mkdir()
    sess = _session(workspace=str(root))
    # 创建产品 (命名 → FakeOrg slug=scorepocket)
    sess._dispatch("我想开发一个台球计分APP")
    sess._dispatch("计分麻烦")
    sess._dispatch("台球爱好者")
    sess._dispatch("计分、记录")
    sess._dispatch("y")
    capsys.readouterr()
    # 定位产品目录 → 状态置为 execution_ready (execute_project 允许执行的前提)
    prod_dirs = list((root / "projects").glob("*/product.json"))
    assert prod_dirs, "product.json 未落盘"
    proj_json = prod_dirs[0].parent / "project.json"
    existing = json.loads(proj_json.read_text(encoding="utf-8")) if proj_json.is_file() else {}
    proj_json.write_text(
        json.dumps({**existing, "status": "execution_ready"}), encoding="utf-8"
    )
    # 执行 → 失败原因可见
    sess._dispatch("开始开发")
    out = capsys.readouterr().out
    assert "2 任务失败" in out
    assert "失败示例" in out
    assert "network down" in out
    assert "factory doctor" in out


# ================================================================== 2026-08-19 第二轮: 流程信息量/名称解析/文档查询

class _FakeChat2:
    def answer(self, question, **kw):
        return "AI: 测试回答"

    def is_fallback(self, a):
        return False


def test_resume_with_project_name_switches_and_resumes(monkeypatch, capsys, tmp_path):
    """'继续 旅行记账' → 解析项目名并切换当前项目 (不再报'没有正在开发的项目')。"""
    org = FakeOrgCli()
    monkeypatch.setattr(ACT, "_load_org_cli", lambda: org)
    root = tmp_path / "ws"
    root.mkdir()
    sess = SESS.InteractiveSession(
        context_manager=CTX.ContextManager(workspace=str(root)),
        chat_service=_FakeChat2(),
    )
    sess._dispatch("我想做一个旅行记账软件")
    sess._dispatch("出差报销对账麻烦")
    sess._dispatch("旅行者")
    sess._dispatch("记账、分类")
    sess._dispatch("y")
    capsys.readouterr()
    # 模拟真实 org 落盘 (FakeOrg 不写数据文件)
    org_dir = root / "org"
    org_dir.mkdir(exist_ok=True)
    (org_dir / "projects.json").write_text(
        json.dumps({"projects": {"P-001": {"name": "旅行记账"}}}), encoding="utf-8"
    )
    # 新会话 (无 current_project) → "继续 旅行记账" 应解析名称
    sess2 = SESS.InteractiveSession(
        context_manager=CTX.ContextManager(workspace=str(root)),
        chat_service=_FakeChat2(),
    )
    sess2._dispatch("继续 旅行记账")
    out = capsys.readouterr().out
    assert "已切换到项目" in out
    assert sess2.context.current_project  # 已设置当前项目
    assert "当前没有正在开发的项目" not in out


def test_resume_unknown_name_guides(capsys, tmp_path):
    """'继续 不存在的项目' → 明确未找到, 不猜。"""
    root = tmp_path / "ws"
    root.mkdir()
    sess = SESS.InteractiveSession(
        context_manager=CTX.ContextManager(workspace=str(root)),
        chat_service=_FakeChat2(),
    )
    sess._dispatch("继续 不存在的项目")
    out = capsys.readouterr().out
    assert "未找到项目" in out


def test_project_docs_intent_and_real_data(monkeypatch, capsys, tmp_path):
    """'哪些项目有PRD' → 真实数据表 (不再让 LLM 猜)。"""
    org = FakeOrgCli()
    monkeypatch.setattr(ACT, "_load_org_cli", lambda: org)
    root = tmp_path / "ws"
    root.mkdir()
    sess = SESS.InteractiveSession(
        context_manager=CTX.ContextManager(workspace=str(root)),
        chat_service=_FakeChat2(),
    )
    sess._dispatch("我想开发一个台球计分APP")
    sess._dispatch("计分麻烦")
    sess._dispatch("台球爱好者")
    sess._dispatch("计分、记录")
    sess._dispatch("y")
    capsys.readouterr()
    sess._dispatch("哪些项目有PRD")
    out = capsys.readouterr().out
    assert "PRD" in out
    assert "管线资产" in out
    assert "台球计分" in out or "scorepocket" in out


def test_chat_persona_honesty_constraints():
    """人设 prompt 禁止虚构未实现能力 / 禁止猜项目状态。"""
    chat = import_module("factory-console.session.chat")
    prompt = chat._CHAT_PROMPT
    assert "不要虚构未实现能力" in prompt
    assert "不要代替系统查询项目/文档状态" in prompt


# ================================================================== 2026-08-19 第三轮: 项目清理改名 + 会话记忆

def _write_org_project(workspace: Path, pid: str, name: str) -> None:
    org_dir = workspace / "org"
    org_dir.mkdir(parents=True, exist_ok=True)
    path = org_dir / "projects.json"
    data = {"projects": {pid: {"id": pid, "name": name}}}
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        existing.setdefault("projects", {})[pid] = {"id": pid, "name": name}
        data = existing
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_rename_project_action_updates_org_and_product(tmp_path):
    """改名 action: org/projects.json + product.json 名称同步 (任何状态可改)。"""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_org_project(workspace, "P-001", "未命名产品-123")
    pdir = workspace / "projects" / "P-001"
    pdir.mkdir(parents=True)
    (pdir / "product.json").write_text(
        json.dumps({"name": "未命名产品-123", "problem": "x"}), encoding="utf-8"
    )
    ctx = SimpleNamespace(
        workspace=str(workspace),
        user="user",
        project="P-001",
        intent=SimpleNamespace(
            intent_type=INT.INTENT_RENAME_PROJECT,
            parameters={"project_id": "P-001", "name": "旅行账本"},
            raw="",
        ),
    )
    ctx.require = lambda level: None  # type: ignore[attr-defined]

    result = ACT.rename_project(ctx)
    assert result.ok
    assert "P-001 → 旅行账本" in result.message
    org = json.loads((workspace / "org" / "projects.json").read_text(encoding="utf-8"))
    assert org["projects"]["P-001"]["name"] == "旅行账本"
    product = json.loads((pdir / "product.json").read_text(encoding="utf-8"))
    assert product["name"] == "旅行账本"


def test_nl_rename_with_project_id(monkeypatch, capsys, tmp_path):
    """'P-xxx 改名叫 新名' → 解析 ID 并改名 (不再要求先选当前项目)。"""
    root = tmp_path / "ws"
    root.mkdir()
    _write_org_project(root, "P-001", "未命名产品-123")
    sess = SESS.InteractiveSession(
        context_manager=CTX.ContextManager(workspace=str(root)),
        chat_service=_FakeChat2(),
    )
    sess._dispatch("P-001 改名叫 旅行账本")
    out = capsys.readouterr().out
    assert "✅ 项目改名成功" in out
    assert "P-001 → 旅行账本" in out


def test_session_state_restores_current_project(tmp_path):
    """会话记忆: 保存 current_project → 新会话自动恢复。"""
    root = tmp_path / "ws"
    root.mkdir()
    sess1 = SESS.InteractiveSession(
        context_manager=CTX.ContextManager(workspace=str(root)),
        chat_service=_FakeChat2(),
    )
    sess1.context.current_project = "P-001"
    sess1._save_session_state()
    state_file = root / "session_state.json"
    assert state_file.is_file()
    sess2 = SESS.InteractiveSession(
        context_manager=CTX.ContextManager(workspace=str(root)),
        chat_service=_FakeChat2(),
    )
    sess2._restore_session_state()
    assert sess2.context.current_project == "P-001"
