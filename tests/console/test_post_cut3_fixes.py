"""S1 C1-C3 修复回归测试 (post-cut3)。

- C1: /plan 对 pending (已生成未确认) 计划显示树摘要 (exists/leaf_count)。
- C2: execute_approved 把叶上下文写入 NodeRun input (task.title/scope 可追溯)。
- C3: understanding_statement 到 approved PRD/Plan 后无重复条目 + 无缺口追问。
"""
from __future__ import annotations

import glob
import json  # noqa: F401
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from factory_console import conversation_app as ca  # noqa: E402
from factory_console import golden_path as gp  # noqa: E402
from factory_console import product_understanding as pu  # noqa: E402
from factory_console.canonical_golden_path import CanonicalGoldenPath  # noqa: E402


@pytest.fixture()
def root(tmp_path: Path) -> str:
    return str(tmp_path / "factory")


def _seed_approved(root: str, cid: str) -> dict:
    """理解→PRD→approve→Plan(不 approve, 留 pending 验证 C1)。"""
    svc = ca.ProductUnderstandingService(root, semantic=False)
    svc.process_user_message(cid, "我想做一个飞机大战小游戏。")
    svc.process_user_message(cid, "手机端。")
    prd = gp.generate_prd(root, cid)
    gp.approve_prd(root, cid, prd["id"])
    plan = gp.generate_plan(root, cid, decompose=True, decomposer=None)
    return plan


class TestC1PendingPlanTree:
    def test_pending_plan_tree_visible(self, root: str) -> None:
        """C1: 生成计划后、确认前, plan_tree 可见 (非 approved 也可)。"""
        cgp = CanonicalGoldenPath(root, semantic=False)
        cid = cgp.create_conversation(title="t")["id"]
        _seed_approved(root, cid)  # plan 生成但未 approve → pending
        t = cgp.plan_tree(cid)
        assert t.get("exists") is True
        assert t.get("leaf_count", 0) >= 1
        assert "domains" in t


class TestC2NodeRunLeafContext:
    def test_run_input_has_leaf_context(self, root: str) -> None:
        """C2: execute 后 NodeRun input.task 含 title/scope (非 None)。"""
        cid = ca.ConversationApplicationService(root).create(title="t")["id"]
        svc = ca.ProductUnderstandingService(root, semantic=False)
        svc.process_user_message(cid, "我想做一个飞机大战小游戏。")
        pu.upsert_fact(root, cid, fact_type="REQUIREMENT",
                       content="实现功能: 移动", source_message_id="",
                       confidence=1.0, provenance="test", status="CONFIRMED")
        prd = gp.generate_prd(root, cid)
        gp.approve_prd(root, cid, prd["id"])
        plan = gp.generate_plan(root, cid, decompose=True, decomposer=None)
        gp.approve_plan(root, plan["id"])

        def cap(inp: dict) -> dict:
            return {"ok": True, "output": {"msg": "ok"},
                    "artifact_type": "code_change"}

        gp.execute_approved(root, cid, capability_fn=cap)
        runs = glob.glob(os.path.join(root, "nodes", "runs", "*.json"))
        found = False
        for r in runs:
            d = json.load(open(r))
            task = (d.get("input") or {}).get("task") or {}
            if task.get("title") and task.get("scope"):
                found = True
        assert found  # 至少一个 NodeRun input 含叶 title+scope


class TestC3StatementClean:
    def test_no_duplicate_no_gap_after_plan(self, root: str) -> None:
        """C3: approved PRD+Plan 后 statement 无重复条目、无"还有一个问题"。"""
        cid = ca.ConversationApplicationService(root).create(title="t")["id"]
        _seed_approved(root, cid)
        # approve plan 使进入确认态
        prds = gp.path_status(root, cid)
        plan_id = prds["plans"][-1]["id"]
        gp.approve_plan(root, plan_id)
        svc = ca.ProductUnderstandingService(root, semantic=False)
        st = svc.understanding_statement(cid)
        # 无重复 (手机端仅出现 1 次)
        assert st.count("运行平台: 手机端") <= 1, st
        # 无缺口追问
        assert "还有一个问题" not in st, st
        assert "你想做什么" not in st, st
