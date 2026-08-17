"""S10-072 — Retrieval 统一测试 (P0-A/B/C 反 bypass)。

验证: memory_search (action/API) / recommend / Debug 检索全部经
RetrievalOrchestrator, 不再直接调底层。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

UNI = import_module("factory-console.retrieval.unified")


def _store_with(tmp_path: Path, problems: list[str], project: str = "demo"):
    from importlib import import_module as _im
    MEM = _im("factory-console.memory")
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    store = MEM.ExperienceStore(ws / "memory" / "experience_store.json")
    for i, p in enumerate(problems):
        store.add(MEM.ExperienceRecord(
            id=f"rec-{i}", type="DEBUG_EXPERIENCE", problem=p, action="fix",
            success=True, confidence=0.9 - i * 0.1, source="test", project=project))
    return ws, store


# ================================================================== unified.retrieve_experience


class TestUnifiedRetrieve:
    def test_returns_records(self, tmp_path):
        ws, store = _store_with(tmp_path, ["计分 API 失败"])
        hits, stats = UNI.retrieve_experience("计分", store=store, top_k=5)
        assert hits
        assert hits[0].problem == "计分 API 失败"

    def test_stats_fields(self, tmp_path):
        ws, store = _store_with(tmp_path, ["计分", "登录"])
        hits, stats = UNI.retrieve_experience("计分", store=store, top_k=5)
        for k in ("candidates_count", "selected_count", "discarded_count",
                  "estimated_tokens", "max_tokens", "latency"):
            assert k in stats

    def test_project_filter(self, tmp_path):
        ws, store = _store_with(tmp_path, ["计分"], project="demo")
        store.add(store.__class__ if False else
                  __import__("factory-console.memory", fromlist=["ExperienceRecord"]).ExperienceRecord(
                      type="DEBUG_EXPERIENCE", problem="其他项目经验", action="fix",
                      success=True, confidence=0.9, source="test", project="other"))
        hits, _ = UNI.retrieve_experience("", store=store, top_k=10, project="demo")
        assert all(getattr(h, "project", "") == "demo" for h in hits)

    def test_records_source(self, tmp_path):
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        recs = [MEM.ExperienceRecord(type="DEBUG_EXPERIENCE", problem="登录失败",
                                     action="补配置", success=True, confidence=0.9,
                                     source="test", project="demo")]
        hits, _ = UNI.retrieve_experience("登录", records=recs, top_k=5)
        assert hits and hits[0].problem == "登录失败"

    def test_fail_safe_empty(self):
        hits, stats = UNI.retrieve_experience("x", store=None)
        assert hits == []


# ================================================================== 生产入口统一 (代码级)


class TestNoBypass:
    def test_actions_memory_search_unified(self):
        """memory_search action 不再直接调 ExperienceRetriever。"""
        c = Path("/Users/Shared/work/ai-software-factory/factory-console/session/actions.py")
        content = c.read_text(encoding="utf-8")
        # memory_search 函数体用 unified
        seg = content[content.find("def memory_search"):content.find("def memory_learn")]
        assert "retrieve_experience" in seg
        assert "ExperienceRetriever(ExperienceStore" not in seg

    def test_api_memory_search_unified(self):
        c = Path("/Users/Shared/work/ai-software-factory/factory-console/api/memory.py")
        content = c.read_text(encoding="utf-8")
        seg = content[content.find("def memory_search"):content.find("def memory_learn")]
        assert "retrieve_experience" in seg

    def test_recommend_debug_unified(self):
        c = Path("/Users/Shared/work/ai-software-factory/factory-console/memory/recommendation.py")
        content = c.read_text(encoding="utf-8")
        pos = content.find("def recommend_for_debug")
        assert pos >= 0
        seg = content[pos:pos + 2000]
        assert "retrieve_experience" in seg

    def test_debug_retrieval_policy_unified(self):
        c = Path("/Users/Shared/work/ai-software-factory/factory-console/session/debug/retrieval_policy.py")
        content = c.read_text(encoding="utf-8")
        assert "retrieve_experience" in content

    def test_retrieval_bypass_gone(self):
        """生产入口不再直接 new ExperienceRetriever (仅 Orchestrator/测试)。"""
        c = Path("/Users/Shared/work/ai-software-factory/factory-console/session/actions.py")
        content = c.read_text(encoding="utf-8")
        # 全仓: 生产代码只允许 retrieval/ 内部 + 测试使用旧 ExperienceRetriever
        assert "from ..memory.retrieval import ExperienceRetriever" not in content


# ================================================================== 真实检索 E2E


class TestRetrievalE2E:
    def test_real_request_flow(self, tmp_path):
        """真实 Request → Source Selection → Retriever → Rank → Dedup → Budget。"""
        from importlib import import_module as _im
        RO = _im("factory-console.retrieval")
        ws, store = _store_with(tmp_path, ["计分 API 失败", "计分 超时", "登录"])
        orch = RO.RetrievalOrchestrator()
        orch.register(RO.RetrievalSource.EXPERIENCE, RO.ExperienceRetriever(memory_store=store))
        req = RO.RetrievalRequest(query="计分", top_k=2, max_tokens=100)
        hits, stats = orch.retrieve(req)
        # Top-K 生效
        assert len(hits) <= 2
        # Budget 生效 (tokens ≤ 100)
        assert stats["estimated_tokens"] <= 100
        # Dedup 生效 (source_id 唯一)
        ids = [h.source_id for h in hits]
        assert len(ids) == len(set(ids))
