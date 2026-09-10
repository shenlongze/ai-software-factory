"""S1 第 6 刀 — 项目级敏捷管理闭环测试 (project_agile)。

A. 项目锚点: conversation attach project / 反查。
B. Backlog: PRD 入 backlog 幂等; approve_prd 自动入 (attach 时)。
C. Sprint 生命周期: planned→active→review→closed; 未完成回 backlog。
D. Golden Path 挂接: approved Plan 绑 active sprint; execute 回写叶统计。
E. 视图: project_view/sprint_view; trace 带 sprint 上下文。
"""
from __future__ import annotations

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
from factory_console import project_os as po  # noqa: E402
from factory_console import project_agile as pa  # noqa: E402


@pytest.fixture()
def root(tmp_path: Path) -> str:
    return str(tmp_path / "factory")


def _make_project_conv(root: str) -> tuple[str, str]:
    """建项目 + conversation + attach; 返回 (project_id, conversation_id)。"""
    proj = po.create_project(root, title="电商系统")
    cid = ca.ConversationApplicationService(root).create(title="积分")["id"]
    pa.attach_project(root, cid, proj["id"])
    return proj["id"], cid


class TestAProjectAnchor:
    def test_attach_and_reverse_lookup(self, root: str) -> None:
        pid, cid = _make_project_conv(root)
        got = pa.get_project_by_conversation(root, cid)
        assert got is not None and got["project_id"] == pid
        assert got["title"] == "电商系统"

    def test_no_attach_returns_none(self, root: str) -> None:
        cid = ca.ConversationApplicationService(root).create(title="x")["id"]
        assert pa.get_project_by_conversation(root, cid) is None


class TestBBacklog:
    def test_add_idempotent(self, root: str) -> None:
        pid, _ = _make_project_conv(root)
        pa.add_prd_to_backlog(root, pid, "PRD-1", "conv-1")
        r = pa.add_prd_to_backlog(root, pid, "PRD-1", "conv-1")
        assert r["added"] is False  # 幂等
        assert len(pa.list_backlog(root, pid)) == 1

    def test_approve_prd_auto_adds_to_backlog(self, root: str) -> None:
        """B: approve_prd 成功后 conversation attach 项目 → 自动入 backlog。"""
        pid, cid = _make_project_conv(root)
        ca.ProductUnderstandingService(root).process_user_message(
            cid, "我想做一个会员积分系统。")
        prd = gp.generate_prd(root, cid)
        gp.approve_prd(root, cid, prd["id"])
        bl = pa.list_backlog(root, pid)
        assert any(b["prd_id"] == prd["id"] for b in bl)
        # 幂等: 再次 approve (同 prd 已 approved 会报错; 验证不重复即可)
        assert sum(1 for b in pa.list_all_backlog(root, pid)
                   if b["prd_id"] == prd["id"]) == 1

    def test_approve_prd_without_project_no_backlog(self, root: str) -> None:
        """未 attach 项目 → approve 不进任何 backlog (兼容)。"""
        cid = ca.ConversationApplicationService(root).create(title="x")["id"]
        ca.ProductUnderstandingService(root).process_user_message(
            cid, "我想做一个小工具。")
        prd = gp.generate_prd(root, cid)
        gp.approve_prd(root, cid, prd["id"])  # 不应抛
        # 无 project_agile 目录
        assert not (Path(root) / "project_agile").exists()


class TestCSprintLifecycle:
    def test_full_lifecycle(self, root: str) -> None:
        pid, _ = _make_project_conv(root)
        pa.add_prd_to_backlog(root, pid, "PRD-1", "conv-1")
        pa.add_prd_to_backlog(root, pid, "PRD-2", "conv-1")
        sp = pa.create_sprint(root, pid, title="S1")
        assert sp["status"] == "planned"
        assert set(sp["prd_ids"]) == {"PRD-1", "PRD-2"}
        # planned → active → review → closed
        pa.start_sprint(root, pid, sp["sprint_id"])
        assert pa.get_sprint(root, pid, sp["sprint_id"])["status"] == "active"
        pa.mark_review(root, pid, sp["sprint_id"])
        assert pa.get_sprint(root, pid, sp["sprint_id"])["status"] == "review"
        pa.close_sprint(root, pid, sp["sprint_id"])
        assert pa.get_sprint(root, pid, sp["sprint_id"])["status"] == "closed"

    def test_unfinished_returns_to_backlog_on_close(self, root: str) -> None:
        """C: closed 时未完成 PRD (无 per_prd_stats 完成) 回 backlog。"""
        pid, _ = _make_project_conv(root)
        pa.add_prd_to_backlog(root, pid, "PRD-1", "conv-1")
        sp = pa.create_sprint(root, pid, title="S1")
        pa.start_sprint(root, pid, sp["sprint_id"])
        pa.mark_review(root, pid, sp["sprint_id"])
        # 无执行 → 未完成 → close 后回 backlog
        pa.close_sprint(root, pid, sp["sprint_id"])
        bl = pa.list_backlog(root, pid)
        assert any(b["prd_id"] == "PRD-1" for b in bl)

    def test_done_prd_not_returned(self, root: str) -> None:
        pid, _ = _make_project_conv(root)
        pa.add_prd_to_backlog(root, pid, "PRD-1", "conv-1")
        sp = pa.create_sprint(root, pid, title="S1")
        pa.start_sprint(root, pid, sp["sprint_id"])
        # plan 绑 sprint (与 golden_path 挂接同路径)
        pa.bind_plan_to_sprint(root, pid, "PLAN-1", "PRD-1")
        # 模拟执行完成回写
        pa.update_sprint_leaf_stats(
            root, pid, "PLAN-1", "PRD-1",
            executed=[{"result": {"state": "COMPLETED"}}])
        pa.mark_review(root, pid, sp["sprint_id"])
        pa.close_sprint(root, pid, sp["sprint_id"])
        bl = pa.list_backlog(root, pid)
        assert not any(b["prd_id"] == "PRD-1" for b in bl)  # 完成不回


class TestDGoldenPathAttach:
    def test_plan_binds_to_active_sprint(self, root: str) -> None:
        pid, cid = _make_project_conv(root)
        ca.ProductUnderstandingService(root).process_user_message(
            cid, "我想做一个会员积分系统。")
        prd = gp.generate_prd(root, cid)
        gp.approve_prd(root, cid, prd["id"])  # → backlog
        sp = pa.create_sprint(root, pid, title="S1")
        pa.start_sprint(root, pid, sp["sprint_id"])
        plan = gp.generate_plan(root, cid, decompose=True, decomposer=None)
        gp.approve_plan(root, plan["id"])
        # plan 已绑 active sprint
        sp2 = pa.get_sprint(root, pid, sp["sprint_id"])
        assert plan["id"] in sp2["plan_ids"]
        # 无 active sprint 时不绑 (关掉后再生成)
        pa.mark_review(root, pid, sp["sprint_id"])
        pa.close_sprint(root, pid, sp["sprint_id"])

    def test_execute_writes_sprint_stats(self, root: str) -> None:
        pid, cid = _make_project_conv(root)
        ca.ProductUnderstandingService(root).process_user_message(
            cid, "我想做一个积分系统。")
        pu.upsert_fact(root, cid, fact_type="REQUIREMENT",
                       content="实现功能: 积分账户", source_message_id="",
                       confidence=1.0, provenance="test", status="CONFIRMED")
        prd = gp.generate_prd(root, cid)
        gp.approve_prd(root, cid, prd["id"])
        sp = pa.create_sprint(root, pid, title="S1")
        pa.start_sprint(root, pid, sp["sprint_id"])
        plan = gp.generate_plan(root, cid, decompose=True, decomposer=None)
        gp.approve_plan(root, plan["id"])

        fail_first = {"first": True}

        def cap(inp: dict) -> dict:
            t = (inp.get("task") or {}).get("title", "")
            if "积分账户" in str(t) and fail_first["first"]:
                fail_first["first"] = False
                return {"ok": False, "error": "失败",
                        "output": {}, "artifact_type": "code_change"}
            return {"ok": True, "output": {"m": "ok"},
                    "artifact_type": "code_change"}

        gp.execute_approved(root, cid, capability_fn=cap)
        sp2 = pa.get_sprint(root, pid, sp["sprint_id"])
        st = sp2["stats"]
        assert st["total_leaves"] >= 2
        # M1 语义: 积分叶 FAILED (cap 注入失败) → 依赖它的验证叶 BLOCKED
        assert st["failed"] == 1, st
        assert st["blocked"] >= 1, st  # 验证叶被阻断
        assert st["completed"] == 0, st


class TestEViews:
    def test_project_and_sprint_views(self, root: str) -> None:
        from factory_console.canonical_golden_path import CanonicalGoldenPath
        cgp = CanonicalGoldenPath(root, semantic=False)
        pid, cid = _make_project_conv(root)
        v = cgp.project_view(cid)
        assert v["attached"] and v["project_id"] == pid
        s = cgp.sprint_view(cid)
        assert s["attached"] and s["sprint_id"] is None  # 无 sprint
        # 无项目会话
        cid2 = cgp.create_conversation(title="x")["id"]
        assert cgp.project_view(cid2)["attached"] is False

    def test_trace_includes_project_context(self, root: str) -> None:
        from factory_console.trace_query import build_trace
        pid, cid = _make_project_conv(root)
        ca.ProductUnderstandingService(root).process_user_message(
            cid, "我想做积分系统。")
        prd = gp.generate_prd(root, cid)
        gp.approve_prd(root, cid, prd["id"])
        t = build_trace(root, cid)
        assert t["project"] is not None
        assert t["project"]["project_id"] == pid
        assert t["project"]["backlog_count"] >= 1
