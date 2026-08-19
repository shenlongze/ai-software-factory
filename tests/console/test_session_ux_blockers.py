"""test_session_ux_blockers.py — 2026-08-19 测试可继续性修复 (交互链路 UX 挡路点)。

覆盖:
1. 中文退出命令 ("退出") 真正退出会话 (原只有 exit/quit)
2. 确认取消提示不再误导 "退出会话" (原提示像是要退出整个会话)
3. 项目执行失败给出原因 (原 "10 任务失败" 黑盒)
basename 全仓库唯一 (test_session_* 前缀)。
"""

from __future__ import annotations

import json

from importlib import import_module

ACT = import_module("factory-console.session.actions")
CTX = import_module("factory-console.session.context")
ORCH = import_module("factory-console.session.orchestrator")
SESS = import_module("factory-console.session.session")


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
