"""S10-067 — Memory Learning API 测试套件。

覆盖: 5 端点 (search/learn/stats/agent/export) + schema (Pydantic 请求/响应)
+ error handling (非法 type / 空 agent_id / 未知 agent → {"ok": False}) +
注册 (api/__init__)。装配: tmp_path + fixtures; 禁真实网络。

设计: docs/sprint10/S10-067-memory-learning-design.md §7
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

MEM_API = import_module("factory-console.api.memory")
API_INIT = import_module("factory-console.api")
EXP = import_module("factory-console.memory.experience")
EXTR = import_module("factory-console.memory.extraction")


def _workspace(tmp_path: Path) -> Path:
    """fixture workspace (2 exec records + repair + gap)。"""
    ws = tmp_path / "ws"
    (ws / "exec").mkdir(parents=True)
    (ws / "exec" / EXTR.EXECUTION_RECORDS_FILE).write_text(
        json.dumps([
            {"intent": "run_task", "action": "agent.execute_task",
             "agent": "backend-1", "task": "登录功能", "result": "failed",
             "error": "provider error: anthropic api key missing",
             "timestamp": "2026-08-14T00:00:00+00:00"},
            {"intent": "run_task", "action": "agent.execute_task",
             "agent": "backend-1", "task": "数据库设计", "result": "success",
             "timestamp": "2026-08-14T00:00:01+00:00"},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    pd = ws / "projects" / "demo"
    pd.mkdir(parents=True)
    (pd / EXTR.REPAIR_TASK_FILE).write_text(
        json.dumps([
            {"repair_id": "repair-1", "original_task_id": "T1",
             "original_task_name": "登录功能",
             "failure_reason": "缺少 ANTHROPIC_API_KEY 配置",
             "status": "completed", "created_at": "2026-08-15T00:00:00+00:00"},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    (pd / EXTR.GAP_ANALYSIS_FILE).write_text(
        json.dumps([
            {"detected": True, "gap_type": "missing_implementation",
             "description": "缺少持久化实现", "recommended_action": "INSERT_TASK",
             "confidence": 0.8, "timestamp": "2026-08-16T00:00:00+00:00"},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    return ws


# ================================================================== 1. search 端点

class TestSearchEndpoint:
    def _learned(self, tmp_path):
        """learn 后 workspace (提取 fixture 数据到 store)。"""
        ws = _workspace(tmp_path)
        MEM_API.memory_learn(workspace=ws)
        return ws

    def test_ok(self, tmp_path):
        res = MEM_API.memory_search(query="登录", workspace=self._learned(tmp_path))
        assert res.get("ok") is True

    def test_data_is_list_of_records(self, tmp_path):
        res = MEM_API.memory_search(query="", workspace=self._learned(tmp_path))
        assert isinstance(res["data"], list)
        assert all("id" in r and "type" in r for r in res["data"])

    def test_keyword_hit(self, tmp_path):
        res = MEM_API.memory_search(query="登录", workspace=self._learned(tmp_path))
        assert res["data"]

    def test_project_filter(self, tmp_path):
        res = MEM_API.memory_search(query="", project="demo", workspace=self._learned(tmp_path))
        assert all(r["project"] == "demo" for r in res["data"])

    def test_type_filter(self, tmp_path):
        res = MEM_API.memory_search(query="", type=EXP.FAILURE_PATTERN,
                                    workspace=self._learned(tmp_path))
        assert res["data"] and all(r["type"] == EXP.FAILURE_PATTERN for r in res["data"])

    def test_invalid_type_error(self, tmp_path):
        res = MEM_API.memory_search(query="", type="BAD_TYPE", workspace=_workspace(tmp_path))
        assert res.get("ok") is False and "error" in res

    def test_empty_workspace_empty_result(self, tmp_path):
        ws = tmp_path / "none"
        ws.mkdir()
        res = MEM_API.memory_search(query="", workspace=ws)
        assert res.get("ok") is True and res["data"] == []

    def test_default_workspace_no_crash(self):
        # 缺省 workspace = ~/.factory — 真实数据空间, 只断言不裸抛
        res = MEM_API.memory_search(query="__no_such_keyword__")
        assert "ok" in res and "data" in res


# ================================================================== 2. learn 端点

class TestLearnEndpoint:
    def test_ok(self, tmp_path):
        res = MEM_API.memory_learn(workspace=_workspace(tmp_path))
        assert res.get("ok") is True

    def test_learning_result_keys(self, tmp_path):
        res = MEM_API.memory_learn(workspace=_workspace(tmp_path))
        for key in ("extracted_count", "patterns", "agent_profiles", "learned_items"):
            assert key in res["data"]

    def test_extracted_count(self, tmp_path):
        res = MEM_API.memory_learn(workspace=_workspace(tmp_path))
        assert res["data"]["extracted_count"] == 4  # 2 exec + 1 repair + 1 gap

    def test_patterns_learned(self, tmp_path):
        res = MEM_API.memory_learn(workspace=_workspace(tmp_path))
        assert res["data"]["patterns"]
        assert res["data"]["patterns"][0]["pattern_id"].endswith("_pattern")

    def test_agent_profiles(self, tmp_path):
        res = MEM_API.memory_learn(workspace=_workspace(tmp_path))
        assert any(p["agent_id"] == "backend-1" for p in res["data"]["agent_profiles"])

    def test_store_persisted(self, tmp_path):
        ws = _workspace(tmp_path)
        MEM_API.memory_learn(workspace=ws)
        store_path = ws / "memory" / "experience_store.json"
        assert store_path.is_file()

    def test_empty_workspace_ok(self, tmp_path):
        ws = tmp_path / "none"
        ws.mkdir()
        res = MEM_API.memory_learn(workspace=ws)
        assert res.get("ok") is True and res["data"]["extracted_count"] == 0


# ================================================================== 3. stats 端点

class TestStatsEndpoint:
    def test_ok(self, tmp_path):
        res = MEM_API.memory_stats(workspace=_workspace(tmp_path))
        assert res.get("ok") is True

    def test_total(self, tmp_path):
        ws = _workspace(tmp_path)
        MEM_API.memory_learn(workspace=ws)
        res = MEM_API.memory_stats(workspace=ws)
        assert res["data"]["total"] == 4

    def test_by_type(self, tmp_path):
        ws = _workspace(tmp_path)
        MEM_API.memory_learn(workspace=ws)
        res = MEM_API.memory_stats(workspace=ws)
        assert res["data"]["by_type"][EXP.FAILURE_PATTERN] >= 1

    def test_by_success(self, tmp_path):
        ws = _workspace(tmp_path)
        MEM_API.memory_learn(workspace=ws)
        res = MEM_API.memory_stats(workspace=ws)
        assert res["data"]["by_success"]["failed"] >= 1

    def test_empty_workspace_stats(self, tmp_path):
        ws = tmp_path / "none"
        ws.mkdir()
        res = MEM_API.memory_stats(workspace=ws)
        assert res.get("ok") is True and res["data"]["total"] == 0

    def test_file_path_in_stats(self, tmp_path):
        ws = _workspace(tmp_path)
        res = MEM_API.memory_stats(workspace=ws)
        assert str(ws / "memory") in res["data"]["file"]


# ================================================================== 4. agent 端点

class TestAgentEndpoint:
    def test_ok(self, tmp_path):
        res = MEM_API.memory_agent("backend-1", workspace=_workspace(tmp_path))
        assert res.get("ok") is True

    def test_profile_fields(self, tmp_path):
        res = MEM_API.memory_agent("backend-1", workspace=_workspace(tmp_path))
        for key in ("agent_id", "role", "total_tasks", "success_count",
                    "success_rate", "common_problems", "best_domains"):
            assert key in res["data"]

    def test_agent_metrics(self, tmp_path):
        res = MEM_API.memory_agent("backend-1", workspace=_workspace(tmp_path))
        assert res["data"]["total_tasks"] == 2
        assert res["data"]["success_count"] == 1
        assert res["data"]["success_rate"] == 0.5

    def test_empty_agent_id_error(self, tmp_path):
        res = MEM_API.memory_agent("", workspace=_workspace(tmp_path))
        assert res.get("ok") is False and "agent_id" in res["error"]

    def test_unknown_agent_error(self, tmp_path):
        res = MEM_API.memory_agent("ghost", workspace=_workspace(tmp_path))
        assert res.get("ok") is False and "未找到" in res["error"]

    def test_empty_workspace_error(self, tmp_path):
        ws = tmp_path / "none"
        ws.mkdir()
        res = MEM_API.memory_agent("backend-1", workspace=ws)
        assert res.get("ok") is False


# ================================================================== 5. export 端点

class TestExportEndpoint:
    def test_ok(self, tmp_path):
        res = MEM_API.memory_export(workspace=_workspace(tmp_path))
        assert res.get("ok") is True

    def test_export_all_sources(self, tmp_path):
        res = MEM_API.memory_export(workspace=_workspace(tmp_path))
        types = {r["type"] for r in res["data"]}
        assert EXP.FAILURE_PATTERN in types
        assert EXP.SUCCESS_PATTERN in types
        assert EXP.DEBUG_EXPERIENCE in types
        assert EXP.PLANNING_EXPERIENCE in types

    def test_export_count(self, tmp_path):
        res = MEM_API.memory_export(workspace=_workspace(tmp_path))
        assert len(res["data"]) == 4

    def test_export_empty_workspace(self, tmp_path):
        ws = tmp_path / "none"
        ws.mkdir()
        res = MEM_API.memory_export(workspace=ws)
        assert res.get("ok") is True and res["data"] == []


# ================================================================== 6. schema + 注册

class TestSchema:
    def test_search_request_model(self):
        req = MEM_API.MemorySearchRequest(query="登录", type=EXP.FAILURE_PATTERN)
        assert req.query == "登录" and req.type == EXP.FAILURE_PATTERN

    def test_search_request_defaults(self):
        req = MEM_API.MemorySearchRequest()
        assert req.query == "" and req.project is None and req.type is None

    def test_learn_request(self):
        req = MEM_API.MemoryLearnRequest(workspace="/tmp/x")
        assert req.workspace == "/tmp/x"

    def test_agent_request(self):
        req = MEM_API.MemoryAgentRequest(agent_id="backend-1")
        assert req.agent_id == "backend-1"

    def test_export_request(self):
        req = MEM_API.MemoryExportRequest()
        assert req.workspace is None

    def test_response_model(self):
        resp = MEM_API.MemoryResponse(ok=True, data=[1, 2])
        assert resp.ok is True and resp.data == [1, 2] and resp.error is None


class TestRegistration:
    def test_search_registered(self):
        assert hasattr(API_INIT, "memory_search") or "memory_search" in API_INIT.__all__

    def test_learn_registered(self):
        assert hasattr(API_INIT, "memory_learn") or "memory_learn" in API_INIT.__all__

    def test_stats_registered(self):
        assert hasattr(API_INIT, "memory_stats") or "memory_stats" in API_INIT.__all__

    def test_agent_registered(self):
        assert hasattr(API_INIT, "memory_agent") or "memory_agent" in API_INIT.__all__

    def test_export_registered(self):
        assert hasattr(API_INIT, "memory_export") or "memory_export" in API_INIT.__all__

    def test_module_all(self):
        for name in ("memory_search", "memory_learn", "memory_stats",
                     "memory_agent", "memory_export"):
            assert name in MEM_API.__all__
