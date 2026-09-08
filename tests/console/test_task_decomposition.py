"""S1 第 2 刀 — task_decomposition 多级任务树域测试。

验证 (任务书 §四.1):
- 模板树多级正确 (Project → Domain → Leaf + 验证交付叶)
- LLM 注入树正确 (interpreter 注入)
- LLM 失败 → 模板兜底 degraded
- 空 PRD 诚实 (goal 兜底 ≥1 叶)
- 持久化往返 (save/load)
- tree_to_plan 拓扑序 (依赖先于依赖者)
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from factory_console import task_decomposition as td  # noqa: E402


def _prd(*, feats: list[str] | None = None, goal: str = "飞机大战小游戏") -> dict:
    return {
        "id": "prd-test-1",
        "version": 1,
        "content": {
            "overview": {"name": "飞机大战", "problem": goal},
            "functional_requirements": feats if feats is not None
            else ["玩家飞机可以移动", "发射子弹", "敌机出现"],
        },
    }


class TestTemplateDecompose:
    def test_multi_level_tree(self) -> None:
        tree = td.decompose_prd(_prd())
        kinds = {n["kind"] for n in tree["nodes"]}
        assert kinds == {"project", "domain", "task"}
        assert not tree["degraded"]
        # 功能叶 + 验证叶
        leaves = td.tree_leaves(tree)
        assert len(leaves) == 4  # 3 功能 + 1 验证交付
        titles = " ".join(n["title"] for n in leaves)
        assert "发射子弹" in titles and "验证与交付" in titles
        # 验证叶 depends_on 全部功能叶
        vleaf = next(n for n in leaves if n["title"] == "验证与交付")
        f_leaves = [n for n in leaves if n["title"] != "验证与交付"]
        assert set(vleaf["depends_on"]) == {n["id"] for n in f_leaves}
        # 有 domain 中间层 (深度 3)
        domains = [n for n in tree["nodes"] if n["kind"] == "domain"]
        assert len(domains) >= 2  # 功能域 + 验证域

    def test_empty_prd_goal_fallback(self) -> None:
        """空功能条款 → goal 兜底 ≥1 叶 (诚实, 不产空树)。"""
        tree = td.decompose_prd(_prd(feats=[]))
        leaves = td.tree_leaves(tree)
        assert len(leaves) >= 1
        assert tree["goal"]  # 非空 goal


class TestLlmInjection:
    def test_llm_tree_used(self) -> None:
        def fake_llm(prompt: str) -> str:
            return ('{"domains":[{"title":"玩法","tasks":['
                    '{"title":"实现移动","change_type":"NEW_FILE",'
                    '"expected_files":["move.js"]}]}]}')
        interp = td.build_llm_decomposer(llm_fn=fake_llm)
        tree = td.decompose_prd(_prd(), interpreter=interp)
        assert tree["decomposer"] == "llm"
        assert not tree["degraded"]
        titles = [n["title"] for n in td.tree_leaves(tree)]
        assert "实现移动" in titles

    def test_llm_failure_falls_back_degraded(self) -> None:
        def bad_llm(prompt: str) -> str:
            raise RuntimeError("llm down")
        interp = td.build_llm_decomposer(llm_fn=bad_llm)
        tree = td.decompose_prd(_prd(), interpreter=interp)
        assert tree["degraded"] is True
        assert tree["decomposer"] == "template-after-llm-failure"
        assert len(td.tree_leaves(tree)) >= 1  # 模板兜底非空

    def test_llm_invalid_json_falls_back(self) -> None:
        def junk_llm(prompt: str) -> str:
            return "不是 JSON"
        interp = td.build_llm_decomposer(llm_fn=junk_llm)
        tree = td.decompose_prd(_prd(), interpreter=interp)
        assert tree["degraded"] is True


class TestPersistence:
    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        tree = td.decompose_prd(_prd())
        td.save_task_tree(str(tmp_path), "PLAN-1", tree)
        loaded = td.load_task_tree(str(tmp_path), "PLAN-1")
        assert loaded is not None
        assert loaded["plan_id"] == tree["plan_id"]
        assert len(loaded["nodes"]) == len(tree["nodes"])
        # 缺失 → None
        assert td.load_task_tree(str(tmp_path), "PLAN-none") is None

    def test_tree_summary(self, tmp_path: Path) -> None:
        tree = td.decompose_prd(_prd())
        td.save_task_tree(str(tmp_path), "PLAN-2", tree)
        s = td.tree_summary(td.load_task_tree(str(tmp_path), "PLAN-2"))
        assert s["exists"] and s["leaf_count"] >= 1
        assert "goal" in s and "degraded" in s
        assert td.tree_summary(None)["exists"] is False


class TestTreeToPlan:
    def test_topological_order(self) -> None:
        """验证叶 depends_on 全部功能叶 → 拓扑序中功能叶先于验证叶。"""
        tree = td.decompose_prd(_prd(feats=["A", "B"]))
        summaries, order = td.tree_to_plan(tree)
        assert len(summaries) == 3  # A + B + verify
        # 每个叶带 change_type/expected_files/depends_on
        for s in summaries:
            assert s["change_type"] in td.CHANGE_TYPES
            assert "depends_on" in s
        # verify 在 order 最后 (依赖 A/B)
        by_id = {s["id"]: s for s in summaries}
        vid = next(s["id"] for s in summaries if "验证" in s["title"])
        assert order[-1] == vid
        for dep in by_id[vid]["depends_on"]:
            assert order.index(dep) < order.index(vid)
