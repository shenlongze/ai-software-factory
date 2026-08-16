"""S10-067 — Memory Learning Integration 测试套件。

覆盖: 真实数据 (execution_records/repair/replanning/gap) → 完整学习循环:
extract_all → learn → search → recommendation。
装配: tmp_path + fixtures; 禁真实网络。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

MEM = import_module("factory-console.memory")
EXTR = import_module("factory-console.memory.extraction")
ENG = import_module("factory-console.memory.learning_engine")
API = import_module("factory-console.api.memory")


def _workspace(tmp_path: Path) -> Path:
    """真实结构 fixture: exec records + repair + replanning + gap。"""
    ws = tmp_path / "ws"
    (ws / "exec").mkdir(parents=True)
    (ws / "exec" / "execution_records.json").write_text(json.dumps([
        {"intent": "run_task", "action": "agent.execute_task",
         "agent": "backend-1", "task": "登录功能", "result": "failed",
         "error": "provider error: anthropic api key missing",
         "timestamp": "2026-08-14T00:00:00+00:00"},
        {"intent": "run_task", "action": "agent.execute_task",
         "agent": "backend-1", "task": "数据库设计", "result": "success",
         "timestamp": "2026-08-14T00:00:01+00:00"},
        {"intent": "run_task", "action": "agent.execute_task",
         "agent": "qa-agent", "task": "测试用例", "result": "failed",
         "error": "assertion error: expected 10 got 9",
         "timestamp": "2026-08-14T00:00:02+00:00"},
    ], ensure_ascii=False), encoding="utf-8")
    pd = ws / "projects" / "demo"
    pd.mkdir(parents=True, exist_ok=True)
    (pd / "repair_task.json").write_text(json.dumps(
        {"task_id": "T002", "error": "API contract mismatch",
         "plan": "add schema validation", "status": "completed"}),
        encoding="utf-8")
    (pd / "replanning_decisions.json").write_text(json.dumps([
        {"decision": "INSERT_TASK", "source_gap": "missing persistence",
         "reason": "persistence required", "timestamp": "2026-08-14T00:00:03+00:00"},
    ]), encoding="utf-8")
    (pd / "gap_analysis.json").write_text(json.dumps([
        {"gap_type": "missing_implementation", "source_task_id": "T003",
         "description": "排行榜缺持久化", "confidence": 0.8,
         "timestamp": "2026-08-14T00:00:04+00:00"},
    ]), encoding="utf-8")
    return ws


class TestExtractAll:
    def test_extract_all_count(self, tmp_path):
        ws = _workspace(tmp_path)
        records = EXTR.ExperienceExtractor().extract_all(ws)
        assert len(records) >= 6  # 3 records + 1 repair + 1 replan + 1 gap

    def test_failure_pattern_extracted(self, tmp_path):
        ws = _workspace(tmp_path)
        records = EXTR.ExperienceExtractor().extract_all(ws)
        assert any(r.type == MEM.FAILURE_PATTERN for r in records)

    def test_success_pattern_extracted(self, tmp_path):
        ws = _workspace(tmp_path)
        records = EXTR.ExperienceExtractor().extract_all(ws)
        assert any(r.type == MEM.SUCCESS_PATTERN for r in records)

    def test_debug_experience_extracted(self, tmp_path):
        ws = _workspace(tmp_path)
        records = EXTR.ExperienceExtractor().extract_all(ws)
        assert any(r.type == MEM.DEBUG_EXPERIENCE for r in records)

    def test_planning_experience_extracted(self, tmp_path):
        ws = _workspace(tmp_path)
        records = EXTR.ExperienceExtractor().extract_all(ws)
        assert any(r.type == MEM.PLANNING_EXPERIENCE for r in records)


class TestLearningLoop:
    def test_learn_loop(self, tmp_path):
        """失败→提取→学习→查询 完整循环。"""
        ws = _workspace(tmp_path)
        result = ENG.LearningEngine(workspace=ws).run(ws)
        assert result.extracted_count >= 6
        assert len(result.patterns) >= 1
        assert len(result.agent_profiles) >= 1

    def test_pattern_confidence(self, tmp_path):
        ws = _workspace(tmp_path)
        result = ENG.LearningEngine(workspace=ws).run(ws)
        for p in result.patterns:
            conf = p.get("confidence") if isinstance(p, dict) else getattr(p, "confidence", 0)
            assert 0.0 <= conf <= 1.0

    def test_agent_profile(self, tmp_path):
        ws = _workspace(tmp_path)
        result = ENG.LearningEngine(workspace=ws).run(ws)
        for a in result.agent_profiles:
            agent_id = a.get("agent_id") if isinstance(a, dict) else getattr(a, "agent_id", "")
            total = a.get("total_tasks") if isinstance(a, dict) else getattr(a, "total_tasks", 0)
            rate = a.get("success_rate") if isinstance(a, dict) else getattr(a, "success_rate", 0)
            assert agent_id
            assert total >= 0
            assert 0.0 <= rate <= 1.0

    def test_learning_trace(self, tmp_path):
        ws = _workspace(tmp_path)
        ENG.LearningEngine(workspace=ws).run(ws)
        trace_file = ws / "memory" / "learning_trace.json"
        assert trace_file.is_file()

    def test_trace_content(self, tmp_path):
        ws = _workspace(tmp_path)
        ENG.LearningEngine(workspace=ws).run(ws)
        traces = json.loads((ws / "memory" / "learning_trace.json").read_text(encoding="utf-8"))
        assert traces
        assert "source" in traces[0]
        assert "confidence" in traces[0]


class TestSearchAfterLearn:
    def test_search_problem(self, tmp_path):
        ws = _workspace(tmp_path)
        ENG.LearningEngine(workspace=ws).run(ws)
        res = API.memory_search(query="登录", workspace=ws)
        assert res["data"]

    def test_search_type(self, tmp_path):
        ws = _workspace(tmp_path)
        ENG.LearningEngine(workspace=ws).run(ws)
        res = API.memory_search(query="", type=MEM.FAILURE_PATTERN, workspace=ws)
        assert res["data"]
        assert all(r["type"] == MEM.FAILURE_PATTERN for r in res["data"])

    def test_recommend_for_debug(self, tmp_path):
        ws = _workspace(tmp_path)
        ENG.LearningEngine(workspace=ws).run(ws)
        rec = MEM.Recommender().recommend_for_debug("API contract mismatch")
        assert isinstance(rec, list)

    def test_recommend_for_planning(self, tmp_path):
        ws = _workspace(tmp_path)
        ENG.LearningEngine().run(ws)
        rec = MEM.Recommender().recommend_for_planning({"name": "台球计分", "core_features": ["计分", "排行榜"]})
        assert isinstance(rec, list)
