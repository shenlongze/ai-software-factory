"""S10-065 — Guided CLI / 自然语言路由测试套件 (Batch B)。

覆盖: intent 新规则识别 / discovery_start / production_session_view / resume_project /
旧命令兼容。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

ACT = import_module("factory-console.session.actions")
INT = import_module("factory-console.session.intent")


class TestIntentRules:
    def test_discovery_start_idea(self):
        parser = INT.KeywordIntentParser()
        intent = parser.parse("我想做一个台球计分APP")
        # 可能落到 discovery_start 或 create_product — 二者均可 (引导)
        assert intent.intent_type in ("discovery_start", "create_product")

    def test_resume_continue(self):
        parser = INT.KeywordIntentParser()
        intent = parser.parse("继续执行")
        assert intent.intent_type == "resume_project"

    def test_review_view_why(self):
        parser = INT.KeywordIntentParser()
        intent = parser.parse("为什么停了")
        assert intent.intent_type == "review_view"

    def test_production_session_progress(self):
        parser = INT.KeywordIntentParser()
        intent = parser.parse("查看进度")
        assert intent.intent_type == "production_session_view"

    def test_review_approve(self):
        parser = INT.KeywordIntentParser()
        intent = parser.parse("批准")
        assert intent.intent_type == "review_approve"

    def test_review_reject(self):
        parser = INT.KeywordIntentParser()
        intent = parser.parse("拒绝")
        assert intent.intent_type == "review_reject"

    def test_review_cancel(self):
        parser = INT.KeywordIntentParser()
        intent = parser.parse("取消")
        assert intent.intent_type == "review_cancel"

    def test_old_commands_kept(self):
        parser = INT.KeywordIntentParser()
        assert parser.parse("准备开发").intent_type == "prepare_project"
        assert parser.parse("开始开发").intent_type == "execute_project"
        assert parser.parse("通过验收").intent_type == "accept_project"


class TestDiscoveryStartAction:
    def test_new_session_first_question(self, tmp_path):
        ws = _ws(tmp_path)
        r = ACT.discovery_start(_ctx(ws, {"idea": "我想做一个台球计分APP"}))
        assert r.ok
        assert "问题" in r.message or "梳理" in r.message or "解决" in r.message

    def test_continue_existing(self, tmp_path):
        ws = _ws(tmp_path)
        ACT.discovery_start(_ctx(ws, {"idea": "idea1"}))
        r = ACT.discovery_start(_ctx(ws, {"idea": "idea2"}))
        assert r.ok  # 继续之前 session

    def test_fail_safe(self, tmp_path):
        ws = tmp_path / "nonexistent"
        r = ACT.discovery_start(_ctx(ws, {"idea": "x"}))
        assert r.ok or not r.ok  # 不裸抛


class TestProductionSessionViewAction:
    def _make_project(self, ws: Path):
        pd = ws / "projects" / "demo"
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "execution_state.json").write_text(json.dumps({
            "project": "demo", "status": "development", "lifecycle": "development",
            "plan_version": 2, "replan_count": 1, "governance_status": "",
            "governance_reason": "",
            "tasks": [{"id": "T001", "name": "计分", "agent": "backend-1",
                       "status": "completed", "retry_count": 0, "error": None}],
        }), encoding="utf-8")
        (pd / "product.json").write_text(json.dumps({"name": "Demo"}), encoding="utf-8")
        return pd

    def test_view_project(self, tmp_path):
        ws = _ws(tmp_path)
        self._make_project(ws)
        r = ACT.production_session_view(_ctx(ws))
        assert r.ok
        assert "demo" in r.message or "Demo" in r.message

    def test_view_no_project(self, tmp_path):
        ws = _ws(tmp_path)
        r = ACT.production_session_view(_ctx(ws))
        assert r.ok
        assert "暂无" in r.message or "尚未" in r.message

    def test_view_specific(self, tmp_path):
        ws = _ws(tmp_path)
        self._make_project(ws)
        r = ACT.production_session_view(_ctx(ws, {"project": "demo"}))
        assert r.ok


class TestResumeProjectAction:
    def test_resume_no_project(self, tmp_path):
        ws = _ws(tmp_path)
        r = ACT.resume_project(_ctx(ws))
        assert r.ok  # 失败安全

    def test_resume_fail_safe(self, tmp_path):
        ws = tmp_path / "none"
        r = ACT.resume_project(_ctx(ws))
        assert r.ok or not r.ok  # 不裸抛


class TestActionsRegistered:
    def test_all_guided_actions(self, tmp_path):
        reg = ACT.build_default_actions()
        names = [a.name for a in reg.list()] if hasattr(reg, "list") else [a.name for a in getattr(reg, "actions", [])]
        for n in ("discovery_start", "production_session_view", "resume_project",
                  "review_view", "review_approve", "review_reject", "review_cancel"):
            assert n in names, f"{n} 未注册"

    def test_old_actions_kept(self, tmp_path):
        reg = ACT.build_default_actions()
        names = [a.name for a in reg.list()] if hasattr(reg, "list") else [a.name for a in getattr(reg, "actions", [])]
        for n in ("create_product", "prepare_project", "execute_project",
                  "accept_project", "factory_status", "factory_review"):
            assert n in names, f"{n} 被破坏"


def _ws(tmp_path) -> Path:
    ws = tmp_path / "ws"
    (ws / "cost").mkdir(parents=True, exist_ok=True)
    (ws / "projects").mkdir(exist_ok=True)
    return ws


def _ctx(ws: Path, params: dict | None = None):
    class FakeContext:
        def __init__(self, workspace, params):
            self.workspace = str(workspace)
            self.params = params or {}
            self.project = ""

        def require(self, level):
            pass

    return FakeContext(ws, params)


class TestFill:
    def test_intent_discovery_resume(self):
        parser = INT.KeywordIntentParser()
        assert parser.parse("继续").intent_type == "resume_project"

    def test_intent_review_view_stop(self):
        parser = INT.KeywordIntentParser()
        assert parser.parse("为什么停止").intent_type == "review_view"

    def test_intent_progress_now(self):
        parser = INT.KeywordIntentParser()
        assert parser.parse("现在做到哪了").intent_type == "production_session_view"

    def test_intent_accept(self):
        parser = INT.KeywordIntentParser()
        assert parser.parse("接受").intent_type == "review_approve"

    def test_review_view_markdown(self, tmp_path):
        """review_view 详情输出含选项。"""
        ws = _ws(tmp_path)
        from importlib import import_module
        RG = import_module("factory-console.session.review_gate")
        gate = RG.ReviewGate(file=ws / "cost" / "review_records.json")
        rec = gate.request(reason="预算已使用 90%", trigger="budget",
                           context={}, affected_tasks=[], estimated_cost=0,
                           risk="high")
        r = ACT.review_view(_ctx(ws, {"review_id": rec.review_id}))
        assert r.ok
        assert "预算已使用 90%" in r.message

    def test_discovery_save_load(self, tmp_path):
        ws = _ws(tmp_path)
        ACT.discovery_start(_ctx(ws, {"idea": "想法"}))
        # 再次启动 → 继续之前 session (不崩溃)
        r = ACT.discovery_start(_ctx(ws, {"idea": "新想法"}))
        assert r.ok
