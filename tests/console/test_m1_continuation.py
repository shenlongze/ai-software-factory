"""S1 第 5 刀 M1 — 执行不停死 (dependency-driven continuation) 测试。

构造"1 失败叶 + 无依赖叶 + 依赖失败叶"计划:
- 无依赖叶 COMPLETED (失败不阻断独立叶)
- 失败叶 FAILED (如实)
- 依赖失败叶的下游 → BLOCKED (有记录, 非 NOT_ATTEMPTED)
- 全部叶有状态记录 (不变式: 无 NOT_ATTEMPTED 无记录)
- run 终态 FAILED (含 failure 摘要)
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


from factory_console import golden_path as gp  # noqa: E402
from factory_console import production_run as pr  # noqa: E402
from factory_console import task_decomposition as td  # noqa: E402


def _wf_run(root: str, nodes: list[dict], cap_factory) -> dict:
    """注册 workflow + create run + execute, 返回 run。"""
    wf_id = f"WF-{abs(hash(str(nodes)))}"
    pr.register_workflow(root, workflow_id=wf_id, name="t",
                         project_id="p", nodes=nodes)
    r = pr.create_production_run(root, wf_id, input_data={"x": 1},
                                 trigger="test")
    return pr.execute_production_run(root, r["run_id"],
                                     executor_factory=cap_factory,
                                     artifact_root=str(root))


class TestDependencyDrivenContinuation:
    def test_independent_leaf_runs_after_failure(self, tmp_path: Path) -> None:
        """M1: 失败叶后无依赖的独立叶仍执行 (COMPLETED), 不再丢弃。"""
        root = str(tmp_path / "factory")
        nodes = [
            {"node_id": "A_fail", "depends_on": []},
            {"node_id": "B_independent", "depends_on": []},
        ]

        def factory(node_id: str):
            def fn(input_data: dict) -> dict:
                if node_id == "A_fail":
                    return {"ok": False, "error": "A 真实失败",
                            "output": {}, "artifact_type": "code_change"}
                return {"ok": True, "output": {"msg": "B ok"},
                        "artifact_type": "code_change"}
            return fn

        run = _wf_run(root, nodes, factory)
        states = {n["node_id"]: n["state"] for n in run["node_runs"]}
        assert states == {"A_fail": "FAILED", "B_independent": "COMPLETED"}, states
        # run 终态: 有 FAILED → FAILED
        assert run["state"] == "FAILED"
        assert "部分叶未成功" in str(run.get("failure", ""))

    def test_dependent_leaf_blocked_with_record(self, tmp_path: Path) -> None:
        """M1: 依赖失败叶的下游 → BLOCKED (有记录, reason=上游失败)。"""
        root = str(tmp_path / "factory")
        nodes = [
            {"node_id": "A_fail", "depends_on": []},
            {"node_id": "C_depends_on_A", "depends_on": ["A_fail"]},
        ]

        def factory(node_id: str):
            def fn(input_data: dict) -> dict:
                return {"ok": False, "error": "A 真实失败",
                        "output": {}, "artifact_type": "code_change"}
            return fn

        run = _wf_run(root, nodes, factory)
        states = {n["node_id"]: (n["state"], n.get("reason")) for n in run["node_runs"]}
        assert states["A_fail"][0] == "FAILED"
        assert states["C_depends_on_A"][0] == "BLOCKED"
        assert "依赖 A_fail 未成功" in states["C_depends_on_A"][1]
        # 不变式: 两叶都有记录 (无 NOT_ATTEMPTED)
        assert set(states) == {"A_fail", "C_depends_on_A"}

    def test_all_leaves_recorded_invariant(self, tmp_path: Path) -> None:
        """M1 不变式: 一次 execute 后每叶都有状态 (COMPLETED/FAILED/BLOCKED)。"""
        from factory_console import conversation_app as ca
        from factory_console import product_understanding as pu
        root = str(tmp_path / "factory")
        cid = ca.ConversationApplicationService(root).create(title="t")["id"]
        ca.ProductUnderstandingService(root).process_user_message(
            cid, "我想做一个飞机大战小游戏。")
        pu.upsert_fact(root, cid, fact_type="REQUIREMENT",
                       content="实现功能: 移动", source_message_id="",
                       confidence=1.0, provenance="test", status="CONFIRMED")
        prd = gp.generate_prd(root, cid)
        gp.approve_prd(root, cid, prd["id"])
        plan = gp.generate_plan(root, cid, decompose=True, decomposer=None)
        gp.approve_plan(root, plan["id"])
        tree = td.load_task_tree(root, plan["id"])
        n_leaves = len(td.tree_leaves(tree))

        fail_first = {"first": True}

        def cap(inp: dict) -> dict:
            t = (inp.get("task") or {}).get("title", "")
            if "移动" in str(t) and fail_first["first"]:
                fail_first["first"] = False
                return {"ok": False, "error": "真实失败",
                        "output": {}, "artifact_type": "code_change"}
            return {"ok": True, "output": {"msg": "ok"},
                    "artifact_type": "code_change"}

        out = gp.execute_approved(root, cid, capability_fn=cap)
        # 每个计划叶都有 executed 记录 (execute_approved 映射全覆盖)
        assert len(out["executed"]) == n_leaves, (
            f"{len(out['executed'])} != {n_leaves} (NOT_ATTEMPTED 无记录应消除)")
        states = [e["result"]["state"] for e in out["executed"]]
        assert "FAILED" in states  # 移动叶失败如实记录
        # 验证叶 (依赖移动) → BLOCKED, 但仍在 executed 中
        verify = next(e for e in out["executed"]
                      if "验证" in e["task"].get("title", ""))
        assert verify["result"]["state"] == "BLOCKED", verify["result"]
        # run 终态 FAILED
        assert out["state"] == "FAILED"
