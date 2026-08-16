"""S10-068 — Debug Intelligence API 测试套件。

覆盖: 4 端点 (analyze/recommend/history/stats) + schema + error handling + 注册。
装配: tmp_path + fixtures; 禁真实网络。
"""

from __future__ import annotations

from pathlib import Path

from importlib import import_module

API = import_module("factory-console.api.debug")


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "memory").mkdir(parents=True, exist_ok=True)
    return ws


class TestAnalyzeEndpoint:
    def test_ok(self, tmp_path):
        res = API.debug_analyze("test_login_timeout", workspace=_ws(tmp_path))
        assert res.get("ok") is True
        assert "data" in res

    def test_strategy(self, tmp_path):
        res = API.debug_analyze("timeout after 30s", workspace=_ws(tmp_path))
        assert res["data"]["strategy"] in (
            "FIX_CODE", "FIX_TEST", "CHANGE_DESIGN", "ROLLBACK", "REQUEST_REVIEW")

    def test_confidence(self, tmp_path):
        res = API.debug_analyze("timeout", workspace=_ws(tmp_path))
        assert 0.0 <= res["data"]["confidence"] <= 1.0

    def test_reason(self, tmp_path):
        res = API.debug_analyze("timeout", workspace=_ws(tmp_path))
        assert res["data"]["reason"]

    def test_evidence(self, tmp_path):
        res = API.debug_analyze("timeout", workspace=_ws(tmp_path))
        assert isinstance(res["data"]["evidence"], list)

    def test_task_id_passthrough(self, tmp_path):
        res = API.debug_analyze("timeout", task_id="T9", workspace=_ws(tmp_path))
        assert res["data"]["strategy"] in (
            "FIX_CODE", "FIX_TEST", "CHANGE_DESIGN", "ROLLBACK", "REQUEST_REVIEW")

    def test_empty_message(self, tmp_path):
        """空 error_message → 失败安全。"""
        res = API.debug_analyze("", workspace=_ws(tmp_path))
        assert "data" in res


class TestRecommendEndpoint:
    def test_ok(self, tmp_path):
        res = API.debug_recommend("pytest failed: assert", workspace=_ws(tmp_path))
        assert res.get("ok") is True
        assert "strategy" in res["data"]

    def test_strategy_value(self, tmp_path):
        res = API.debug_recommend("assertion error", workspace=_ws(tmp_path))
        assert res["data"]["strategy"] in (
            "FIX_CODE", "FIX_TEST", "CHANGE_DESIGN", "ROLLBACK", "REQUEST_REVIEW")


class TestHistoryEndpoint:
    def test_empty(self, tmp_path):
        res = API.debug_history(workspace=_ws(tmp_path))
        assert res.get("ok") is True
        assert res["data"] == []

    def test_after_analyze(self, tmp_path):
        ws = _ws(tmp_path)
        API.debug_analyze("timeout", workspace=ws)
        res = API.debug_history(workspace=ws)
        assert len(res["data"]) == 1

    def test_limit(self, tmp_path):
        ws = _ws(tmp_path)
        API.debug_analyze("timeout", workspace=ws)
        API.debug_analyze("pytest failed", workspace=ws)
        res = API.debug_history(limit=1, workspace=ws)
        assert len(res["data"]) == 1


class TestStatsEndpoint:
    def test_ok(self, tmp_path):
        res = API.debug_stats(workspace=_ws(tmp_path))
        assert res.get("ok") is True
        assert "total_cases" in res["data"]

    def test_after_analyze(self, tmp_path):
        ws = _ws(tmp_path)
        API.debug_analyze("timeout", workspace=ws)
        res = API.debug_stats(workspace=ws)
        assert res["data"]["total_cases"] == 1

    def test_by_error_type(self, tmp_path):
        ws = _ws(tmp_path)
        API.debug_analyze("timeout", workspace=ws)
        res = API.debug_stats(workspace=ws)
        assert "by_error_type" in res["data"]


class TestRegistration:
    def test_analyze_registered(self):
        from importlib import import_module as _im
        init = _im("factory-console.api")
        assert hasattr(init, "debug_analyze") or "debug_analyze" in getattr(init, "__all__", [])

    def test_recommend_registered(self):
        from importlib import import_module as _im
        init = _im("factory-console.api")
        assert hasattr(init, "debug_recommend") or "debug_recommend" in getattr(init, "__all__", [])

    def test_history_registered(self):
        from importlib import import_module as _im
        init = _im("factory-console.api")
        assert hasattr(init, "debug_history") or "debug_history" in getattr(init, "__all__", [])

    def test_stats_registered(self):
        from importlib import import_module as _im
        init = _im("factory-console.api")
        assert hasattr(init, "debug_stats") or "debug_stats" in getattr(init, "__all__", [])
