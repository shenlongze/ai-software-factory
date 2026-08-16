"""S10-068 — Debug Intelligence CLI + API + Integration 测试套件。

覆盖: 4 CLI action + intent 关键词 / 4 API 端点 / 完整 Debug 闭环。
装配: tmp_path + fixtures; 禁真实网络。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

ACT = import_module("factory-console.session.actions")
INT = import_module("factory-console.session.intent")
API = import_module("factory-console.api.debug")


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "memory").mkdir(parents=True, exist_ok=True)
    return ws


class TestIntent:
    def test_debug_analyze(self):
        assert INT.KeywordIntentParser().parse("分析错误").intent_type == "debug_analyze"

    def test_debug_why_fail(self):
        assert INT.KeywordIntentParser().parse("为什么失败").intent_type == "debug_analyze"

    def test_debug_history(self):
        assert INT.KeywordIntentParser().parse("查看调试经验").intent_type == "debug_history"

    def test_debug_recommend(self):
        assert INT.KeywordIntentParser().parse("修复建议").intent_type == "debug_recommend"

    def test_debug_stats(self):
        assert INT.KeywordIntentParser().parse("debug统计").intent_type == "debug_stats"

    def test_old_commands_kept(self):
        assert INT.KeywordIntentParser().parse("准备开发").intent_type == "prepare_project"


class TestCliActions:
    def _ctx(self, ws, params=None):
        class Ctx:
            def __init__(self, workspace, params):
                self.workspace = str(workspace)
                self.params = params or {}
                self.project = ""

            def require(self, level):
                pass

        return Ctx(ws, params)

    def test_debug_analyze(self, tmp_path):
        r = ACT.debug_analyze(self._ctx(_ws(tmp_path),
                                        {"error_message": "test_login_timeout"}))
        assert r.ok
        assert "策略" in r.message or "strategy" in r.message or "FIX" in r.message

    def test_debug_history_empty(self, tmp_path):
        r = ACT.debug_history(self._ctx(_ws(tmp_path)))
        assert r.ok

    def test_debug_recommend(self, tmp_path):
        r = ACT.debug_recommend(self._ctx(_ws(tmp_path),
                                          {"error_message": "pytest failed"}))
        assert r.ok
        assert "FIX" in r.message or "策略" in r.message

    def test_debug_stats(self, tmp_path):
        ws = _ws(tmp_path)
        ACT.debug_analyze(self._ctx(ws, {"error_message": "timeout"}))
        r = ACT.debug_stats(self._ctx(ws))
        assert r.ok

    def test_registered(self, tmp_path):
        reg = ACT.build_default_actions()
        names = [a.name for a in reg.list()] if hasattr(reg, "list") else [a.name for a in getattr(reg, "actions", [])]
        for n in ("debug_analyze", "debug_history", "debug_recommend", "debug_stats"):
            assert n in names


class TestApi:
    def test_analyze(self, tmp_path):
        res = API.debug_analyze("test_login_timeout", workspace=_ws(tmp_path))
        assert res.get("ok") is True
        assert "data" in res
        assert "strategy" in res["data"]

    def test_analyze_strategy_value(self, tmp_path):
        res = API.debug_analyze("pytest failed: assertion", workspace=_ws(tmp_path))
        assert res["data"]["strategy"] in ("FIX_CODE", "FIX_TEST", "CHANGE_DESIGN",
                                          "ROLLBACK", "REQUEST_REVIEW")

    def test_recommend(self, tmp_path):
        res = API.debug_recommend("timeout", workspace=_ws(tmp_path))
        assert res.get("ok") is True
        assert "strategy" in res["data"]

    def test_history(self, tmp_path):
        ws = _ws(tmp_path)
        API.debug_analyze("timeout", workspace=ws)
        res = API.debug_history(workspace=ws)
        assert res.get("ok") is True
        assert isinstance(res["data"], list)

    def test_stats(self, tmp_path):
        ws = _ws(tmp_path)
        API.debug_analyze("timeout", workspace=ws)
        res = API.debug_stats(workspace=ws)
        assert res.get("ok") is True
        assert "total_cases" in res["data"]

    def test_analyze_no_error(self, tmp_path):
        res = API.debug_analyze("", workspace=_ws(tmp_path))
        assert "data" in res  # 失败安全

    def test_registered(self, tmp_path):
        from importlib import import_module as _im
        init = _im("factory-console.api")
        assert hasattr(init, "debug_analyze") or "debug_analyze" in getattr(init, "__all__", [])


class TestIntegration:
    def test_full_debug_loop(self, tmp_path):
        """错误 → analyze → Memory 检索 → 策略 → feedback → Memory 沉淀。"""
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        DE = _im("factory-console.session.debug.debug_engine")
        ws = _ws(tmp_path)
        # 预填历史经验 (同类型错误)
        store = MEM.ExperienceStore(ws / "memory" / "experience_store.json")
        store.add(MEM.ExperienceRecord(
            type="DEBUG_EXPERIENCE", problem="jwt refresh token missing",
            action="add token refresh logic", success=True, confidence=0.91,
            source="test", project="demo"))
        # 1. 失败 → DebugEngine
        engine = DE.DebugEngine()
        case = _im("factory-console.session.debug").DebugCase(
            error_message="jwt refresh token missing", task_id="T001")
        decision = engine.analyze(case, workspace=ws)
        assert decision.strategy is not None
        # 2. 修复 → feedback → Memory 沉淀
        engine.feedback(case, decision, {"success": True}, ws)
        # 3. 再次检索 → 新经验可用
        hits = _im("factory-console.session.debug.debug_memory").DebugExperienceRetriever().retrieve(
            case, top_k=5, memory_store=store)
        assert hits

    def test_debug_case_persisted(self, tmp_path):
        ws = _ws(tmp_path)
        API.debug_analyze("timeout", workspace=ws)
        assert (ws / "debug_cases.json").is_file()
