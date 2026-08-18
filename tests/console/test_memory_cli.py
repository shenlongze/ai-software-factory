"""S10-067 — Memory Learning CLI 测试套件。

覆盖: 5 个 memory action (search/learn/stats/analyze-agent/export) + 注册 +
intent 关键词 ("搜索经验"/"学习经验"/"经验统计"/"分析Agent"/"导出经验") +
缺省参数 + 失败安全。
装配: tmp_path + FakeContext (同 test_session_governance_cli.py 模式); 禁真实网络。

设计: docs/sprint10/S10-067-memory-learning-design.md §8
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

ACT = import_module("factory-console.session.actions")
INT = import_module("factory-console.session.intent")
EXP = import_module("factory-console.memory.experience")
EXTR = import_module("factory-console.memory.extraction")


def _ctx(ws: Path, params: dict | None = None, intent=None) -> object:
    """构造最小 Action 上下文 (FakeContext: workspace/params/intent/require)。"""

    class FakeContext:
        def __init__(self, workspace, params, intent):
            self.workspace = str(workspace)
            self.params = params or {}
            self.intent = intent
            self._required = False

        def require(self, level):
            self._required = True

    return FakeContext(ws, params, intent)


def _workspace(tmp_path: Path, with_data: bool = True) -> Path:
    """fixture workspace (exec records + memory store 预填)。"""
    ws = tmp_path / "ws"
    (ws / "exec").mkdir(parents=True)
    if with_data:
        (ws / "exec" / "execution_records.json").write_text(
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
    return ws


# ================================================================== 1. 注册

class TestRegistration:
    def test_search_registered(self):
        names = [a.name for a in ACT.build_default_actions().list()]
        assert "memory_search" in names

    def test_learn_registered(self):
        names = [a.name for a in ACT.build_default_actions().list()]
        assert "memory_learn" in names

    def test_stats_registered(self):
        names = [a.name for a in ACT.build_default_actions().list()]
        assert "memory_stats" in names

    def test_analyze_agent_registered(self):
        names = [a.name for a in ACT.build_default_actions().list()]
        assert "memory_analyze_agent" in names

    def test_export_registered(self):
        names = [a.name for a in ACT.build_default_actions().list()]
        assert "memory_export" in names

    def test_metadata_phase(self):
        actions = {a.name: a for a in ACT.build_default_actions().list()}
        for name in ("memory_search", "memory_learn", "memory_stats",
                     "memory_analyze_agent", "memory_export"):
            assert actions[name].metadata.get("phase") == "S10-067"

    def test_permission_user(self):
        actions = {a.name: a for a in ACT.build_default_actions().list()}
        assert actions["memory_search"].permission == "user"

    def test_handlers_bound(self):
        actions = {a.name: a for a in ACT.build_default_actions().list()}
        for name in ("memory_search", "memory_learn", "memory_stats",
                     "memory_analyze_agent", "memory_export"):
            assert callable(actions[name].handler)


# ================================================================== 2. Intent 关键词

class TestIntent:
    def test_search_keyword(self):
        it = INT.KeywordIntentParser().parse("搜索经验 数据库")
        assert it.intent_type == INT.INTENT_MEMORY_SEARCH

    def test_search_query_param(self):
        it = INT.KeywordIntentParser().parse("搜索经验 数据库")
        assert it.params.get("query") == "数据库"

    def test_search_find_keyword(self):
        it = INT.KeywordIntentParser().parse("查找经验 登录")
        assert it.intent_type == INT.INTENT_MEMORY_SEARCH

    def test_learn_keyword(self):
        it = INT.KeywordIntentParser().parse("学习经验")
        assert it.intent_type == INT.INTENT_MEMORY_LEARN

    def test_learn_alt_keyword(self):
        it = INT.KeywordIntentParser().parse("经验学习")
        assert it.intent_type == INT.INTENT_MEMORY_LEARN

    def test_learn_bare_keyword(self):
        # S10-082: 裸"学习" → 不匹配 memory_learn (闲聊进 Chat); "学习经验" → 触发
        it = INT.KeywordIntentParser().parse("学习")
        assert it is None or it.intent_type != INT.INTENT_MEMORY_LEARN
        it2 = INT.KeywordIntentParser().parse("学习经验")
        assert it2.intent_type == INT.INTENT_MEMORY_LEARN

    def test_stats_keyword(self):
        it = INT.KeywordIntentParser().parse("经验统计")
        assert it.intent_type == INT.INTENT_MEMORY_STATS

    def test_analyze_agent_keyword(self):
        it = INT.KeywordIntentParser().parse("分析Agent")
        assert it.intent_type == INT.INTENT_MEMORY_ANALYZE_AGENT

    def test_analyze_agent_param(self):
        it = INT.KeywordIntentParser().parse("分析Agent backend-1")
        assert it.params.get("agent_id") == "backend-1"

    def test_agent_growth_keyword(self):
        it = INT.KeywordIntentParser().parse("Agent成长")
        assert it.intent_type == INT.INTENT_MEMORY_ANALYZE_AGENT

    def test_export_keyword(self):
        it = INT.KeywordIntentParser().parse("导出经验")
        assert it.intent_type == INT.INTENT_MEMORY_EXPORT

    def test_prefixed_search_not_hijacked(self):
        # "我想搜索经验" — memory 规则在 create_product ("我想") 之前
        it = INT.KeywordIntentParser().parse("我想搜索经验")
        assert it.intent_type == INT.INTENT_MEMORY_SEARCH

    def test_prefixed_learn_not_hijacked(self):
        it = INT.KeywordIntentParser().parse("我想学习经验")
        assert it.intent_type == INT.INTENT_MEMORY_LEARN

    def test_existing_intents_unchanged(self):
        parser = INT.KeywordIntentParser()
        assert parser.parse("我想做一个台球APP").intent_type == INT.INTENT_CREATE_PRODUCT
        assert parser.parse("创建电商项目").intent_type == INT.INTENT_CREATE_PROJECT
        assert parser.parse("分析产品").intent_type == INT.INTENT_PRODUCT_INTELLIGENCE
        assert parser.parse("修复失败任务").intent_type == INT.INTENT_REPAIR_TASK

    def test_confidence_one(self):
        it = INT.KeywordIntentParser().parse("搜索经验")
        assert it.confidence == 1.0


# ================================================================== 3. memory_search action

class TestMemorySearchAction:
    def test_search_happy_path(self, tmp_path):
        ws = _workspace(tmp_path)
        res = ACT.memory_search(_ctx(ws, {"query": "登录"}))
        assert res.ok and res.status == "ok"

    def test_search_mentions_query(self, tmp_path):
        ws = _workspace(tmp_path)
        res = ACT.memory_search(_ctx(ws, {"query": "登录"}))
        assert "经验检索「登录」" in res.message

    def test_search_empty_store(self, tmp_path):
        ws = _workspace(tmp_path, with_data=False)
        res = ACT.memory_search(_ctx(ws, {"query": "登录"}))
        assert res.ok and "无记录" in res.message

    def test_search_from_intent_params(self, tmp_path):
        ws = _workspace(tmp_path)
        intent = INT.KeywordIntentParser().parse("搜索经验 数据库")
        res = ACT.memory_search(_ctx(ws, intent=intent))
        assert res.ok and "数据库" in res.message

    def test_search_requires_user(self, tmp_path):
        ws = _workspace(tmp_path)
        c = _ctx(ws, {"query": "登录"})
        ACT.memory_search(c)
        assert c._required

    def test_search_corrupt_store_fail_safe(self, tmp_path):
        ws = _workspace(tmp_path)
        store_path = ws / "memory" / "experience_store.json"
        store_path.parent.mkdir(parents=True)
        store_path.write_text("corrupt!!", encoding="utf-8")
        res = ACT.memory_search(_ctx(ws, {"query": "登录"}))
        assert res.ok  # 失败安全


# ================================================================== 4. memory_learn action

class TestMemoryLearnAction:
    def test_learn_happy_path(self, tmp_path):
        ws = _workspace(tmp_path)
        res = ACT.memory_learn(_ctx(ws))
        assert res.ok and "学习完成" in res.message

    def test_learn_writes_store(self, tmp_path):
        ws = _workspace(tmp_path)
        ACT.memory_learn(_ctx(ws))
        store_path = ws / "memory" / "experience_store.json"
        assert store_path.is_file()
        data = json.loads(store_path.read_text(encoding="utf-8"))
        assert len(data) == 2  # 2 条 exec 记录

    def test_learn_mentions_patterns(self, tmp_path):
        ws = _workspace(tmp_path)
        res = ACT.memory_learn(_ctx(ws))
        assert "模式" in res.message and "Agent" in res.message

    def test_learn_empty_workspace(self, tmp_path):
        ws = _workspace(tmp_path, with_data=False)
        res = ACT.memory_learn(_ctx(ws))
        assert res.ok and "0 条" in res.message

    def test_learn_writes_trace(self, tmp_path):
        ws = _workspace(tmp_path)
        ACT.memory_learn(_ctx(ws))
        assert (ws / "memory" / "learning_trace.json").is_file()

    def test_learn_requires_user(self, tmp_path):
        ws = _workspace(tmp_path)
        c = _ctx(ws)
        ACT.memory_learn(c)
        assert c._required


# ================================================================== 5. memory_stats action

class TestMemoryStatsAction:
    def test_stats_empty(self, tmp_path):
        ws = _workspace(tmp_path, with_data=False)
        res = ACT.memory_stats(_ctx(ws))
        assert res.ok and "共 0 条" in res.message

    def test_stats_with_records(self, tmp_path):
        ws = _workspace(tmp_path)
        ACT.memory_learn(_ctx(ws))
        res = ACT.memory_stats(_ctx(ws))
        assert res.ok and "成功 1" in res.message and "失败 1" in res.message

    def test_stats_by_type(self, tmp_path):
        ws = _workspace(tmp_path)
        ACT.memory_learn(_ctx(ws))
        res = ACT.memory_stats(_ctx(ws))
        assert "SUCCESS_PATTERN" in res.message or "FAILURE_PATTERN" in res.message

    def test_stats_corrupt_store_fail_safe(self, tmp_path):
        ws = _workspace(tmp_path)
        store_path = ws / "memory" / "experience_store.json"
        store_path.parent.mkdir(parents=True)
        store_path.write_text("corrupt!!", encoding="utf-8")
        res = ACT.memory_stats(_ctx(ws))
        assert res.ok

    def test_stats_requires_user(self, tmp_path):
        ws = _workspace(tmp_path)
        c = _ctx(ws)
        ACT.memory_stats(c)
        assert c._required


# ================================================================== 6. memory_analyze_agent action

class TestMemoryAnalyzeAgentAction:
    def test_analyze_agent_happy(self, tmp_path):
        ws = _workspace(tmp_path)
        res = ACT.memory_analyze_agent(_ctx(ws, {"agent_id": "backend-1"}))
        assert res.ok and "backend-1" in res.message

    def test_analyze_agent_default_first(self, tmp_path):
        ws = _workspace(tmp_path)
        res = ACT.memory_analyze_agent(_ctx(ws))
        assert res.ok and "Agent 画像" in res.message

    def test_analyze_agent_not_found(self, tmp_path):
        ws = _workspace(tmp_path)
        res = ACT.memory_analyze_agent(_ctx(ws, {"agent_id": "ghost"}))
        assert not res.ok and "未找到" in res.message

    def test_analyze_agent_metrics(self, tmp_path):
        ws = _workspace(tmp_path)
        res = ACT.memory_analyze_agent(_ctx(ws, {"agent_id": "backend-1"}))
        assert "任务数: 2" in res.message

    def test_analyze_agent_empty_workspace(self, tmp_path):
        ws = _workspace(tmp_path, with_data=False)
        res = ACT.memory_analyze_agent(_ctx(ws, {"agent_id": "backend-1"}))
        assert not res.ok  # 无经验 → 明确失败

    def test_analyze_agent_requires_user(self, tmp_path):
        ws = _workspace(tmp_path)
        c = _ctx(ws, {"agent_id": "backend-1"})
        ACT.memory_analyze_agent(c)
        assert c._required


# ================================================================== 7. memory_export action

class TestMemoryExportAction:
    def test_export_writes_file(self, tmp_path):
        ws = _workspace(tmp_path)
        ACT.memory_learn(_ctx(ws))
        res = ACT.memory_export(_ctx(ws))
        assert res.ok and "已导出 2 条" in res.message
        export_path = ws / "memory" / "experience_export.json"
        assert export_path.is_file()

    def test_export_data_count(self, tmp_path):
        ws = _workspace(tmp_path)
        ACT.memory_learn(_ctx(ws))
        res = ACT.memory_export(_ctx(ws))
        assert res.data["count"] == 2

    def test_export_empty(self, tmp_path):
        ws = _workspace(tmp_path, with_data=False)
        res = ACT.memory_export(_ctx(ws))
        assert res.ok and "已导出 0 条" in res.message

    def test_export_requires_user(self, tmp_path):
        ws = _workspace(tmp_path)
        c = _ctx(ws)
        ACT.memory_export(c)
        assert c._required

    def test_export_content_valid(self, tmp_path):
        ws = _workspace(tmp_path)
        ACT.memory_learn(_ctx(ws))
        ACT.memory_export(_ctx(ws))
        data = json.loads((ws / "memory" / "experience_export.json").read_text(encoding="utf-8"))
        assert all("type" in r and "problem" in r for r in data)
